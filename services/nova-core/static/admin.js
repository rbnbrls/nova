// Live Clock Update
function updateClock() {
    const clock = document.getElementById('live-clock');
    if (clock) {
        const now = new Date();
        clock.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
}
setInterval(updateClock, 1000);
updateClock();

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Tab selector wiring
document.querySelectorAll('.chat-user-tab').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.chat-user-tab').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        const user = btn.getAttribute('data-user');
        document.querySelectorAll('.admin-channel-cell').forEach(cell => {
            if (cell.getAttribute('data-user') === user) {
                cell.removeAttribute('hidden');
            } else {
                cell.setAttribute('hidden', '');
            }
        });
    });
});

// Copy maps for service status display
const SERVICE_COPY = {
    ollama: { ok: 'Ready', down: 'Not ready' },
    postgres: { ok: 'Connected', down: 'Disconnected' },
    caldav: { ok: 'Reachable', down: 'Unreachable' },
    ha: { ok: 'Ready', down: 'Unreachable' },
    email: { ok: 'Connected', down: 'Disconnected' },
};

function renderServices(services) {
    for (const [key, newStatus] of Object.entries(services)) {
        const cell = document.getElementById(`service-${key}`);
        if (!cell) continue;
        const currentStatus = cell.getAttribute('data-status');
        if (currentStatus === newStatus.status) continue;

        cell.setAttribute('data-status', newStatus.status);
        const statusEl = cell.querySelector('.admin-service-status');
        const detailEl = cell.querySelector('.admin-service-detail');
        const copy = SERVICE_COPY[key] || { ok: 'Ready', down: 'Down' };
        statusEl.textContent = newStatus.status === 'ok' ? copy.ok : copy.down;
        statusEl.className = 'admin-service-status ' + newStatus.status;
        detailEl.textContent = newStatus.detail || '—';
        cell.classList.remove('fadeIn');
        void cell.offsetWidth;
        cell.classList.add('fadeIn');
    }
}

function renderChannels(channels) {
    for (const [user, userChannels] of Object.entries(channels)) {
        for (const [channel, chData] of Object.entries(userChannels)) {
            const cells = document.querySelectorAll(
                `.admin-channel-cell[data-user="${user}"][data-channel="${channel}"]`
            );
            for (const cell of cells) {
                const currentLinked = cell.getAttribute('data-linked');
                const newLinked = chData.linked ? 'true' : 'false';
                if (currentLinked === newLinked) continue;

                cell.setAttribute('data-linked', newLinked);
                cell.classList.toggle('linked', chData.linked);
                cell.classList.toggle('unlinked', !chData.linked);

                const statusValue = cell.querySelector('.status-value');
                if (chData.linked) {
                    const identifier = chData.identifier || '';
                    statusValue.textContent = identifier ? `Linked · ${identifier}` : 'Linked';
                } else {
                    statusValue.textContent = 'Not linked';
                }
            }
        }
    }
}

function renderState(state) {
    renderServices(state.services);
    renderChannels(state.channels);
    // Phase 41 — model state from SSE
    if (state.models && state.models.pulling) {
        renderPullProgress(state.models.pulling);
    }
    // Update current model from services.ollama.model
    const ollamaState = state.services && state.services.ollama;
    if (ollamaState && ollamaState.model) {
        currentActiveModel = ollamaState.model.active || '';
        if (ollamaState.models) {
            renderModelDropdown(ollamaState.models);
            renderDeleteButtons(ollamaState.models);
        }
        // Auto-close modal when model is ready (D-05)
        const modal = document.getElementById('switch-modal');
        if (modal && !modal.classList.contains('hidden')) {
            if (!ollamaState.model.loading && ollamaState.status === 'ok') {
                hideModal();
            }
        }
    }
    const banner = document.getElementById('admin-error-banner');
    if (banner) banner.setAttribute('hidden', '');
}

// SSE listener
const eventSource = new EventSource('/admin/stream');
eventSource.addEventListener('status', (event) => {
    try {
        const data = JSON.parse(event.data);
        renderState(data);
    } catch (e) {
        console.error('Failed to parse admin SSE event:', e);
    }
});
eventSource.onerror = () => {
    const banner = document.getElementById('admin-error-banner');
    if (banner) banner.removeAttribute('hidden');
};

window.addEventListener('beforeunload', () => eventSource.close());

// Phase 41 — Model management state
let currentActiveModel = '';
let currentLocalModels = [];

function showModal(state, message) {
    const modal = document.getElementById('switch-modal');
    const loadingState = document.getElementById('modal-loading-state');
    const errorState = document.getElementById('modal-error-state');
    const title = document.getElementById('modal-title');
    const modelName = document.getElementById('switch-model-name');
    const statusText = document.getElementById('modal-status-text');

    modal.classList.remove('hidden');
    loadingState.classList.remove('hidden');
    errorState.classList.add('hidden');
    if (modelName) modelName.textContent = message || '';
    if (title) title.textContent = 'Switching model…';
}

function hideModal() {
    document.getElementById('switch-modal').classList.add('hidden');
}

function showModelError(message) {
    const loadingState = document.getElementById('modal-loading-state');
    const errorState = document.getElementById('modal-error-state');
    loadingState.classList.add('hidden');
    errorState.classList.remove('hidden');
    errorState.textContent = 'Error: ' + message;
}

function handleModelSwitch() {
    const dropdown = document.getElementById('model-select');
    const switchBtn = document.getElementById('model-switch-btn');
    const model = dropdown.value;
    if (!model || !switchBtn) return;

    switchBtn.disabled = true;
    showModal('loading', `Switching to ${model}…`);

    fetch('/admin/model/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'switched') {
            // SSE will update the UI when the model is ready
        } else {
            hideModal();
            showModelError(data.detail || 'Switch failed');
        }
    })
    .catch(err => {
        hideModal();
        showModelError('Switch failed: ' + err.message);
    })
    .finally(() => {
        if (switchBtn) switchBtn.disabled = false;
    });
}

function handlePull(modelName) {
    const pullBtns = document.querySelectorAll(`[data-pull-model="${modelName}"]`);
    pullBtns.forEach(btn => btn.disabled = true);

    fetch('/admin/model/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: modelName }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'started') {
            // SSE will push progress updates via renderPullProgress()
        } else {
            pullBtns.forEach(btn => btn.disabled = false);
            showModelError(data.detail || 'Pull failed to start');
        }
    })
    .catch(err => {
        pullBtns.forEach(btn => btn.disabled = false);
        showModelError('Pull failed: ' + err.message);
    });
}

function handleModelDelete(modelName) {
    if (modelName === currentActiveModel) return;
    fetch('/admin/model/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: modelName }),
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'deleted') {
            refreshModelList();
        }
    })
    .catch(err => console.error('Model delete failed:', err));
}

function refreshModelList() {
    fetch('/admin/model/list')
    .then(r => r.json())
    .then(data => {
        currentLocalModels = data.local || [];
        renderModelDropdown(currentLocalModels);
        updateModelStore(currentLocalModels);
    })
    .catch(err => console.error('Failed to refresh model list:', err));
}

function renderModelDropdown(models) {
    const dropdown = document.getElementById('model-select');
    if (!dropdown) return;
    const currentValue = dropdown.value;
    dropdown.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select model…';
    dropdown.appendChild(placeholder);

    for (const m of models) {
        const opt = document.createElement('option');
        opt.value = m.name;
        opt.textContent = m.name;
        if (m.name === currentActiveModel) {
            opt.selected = true;
        }
        dropdown.appendChild(opt);
    }
    if (currentValue && Array.from(dropdown.options).some(o => o.value === currentValue)) {
        dropdown.value = currentValue;
    }
    updateSwitchButton();
}

function updateSwitchButton() {
    const dropdown = document.getElementById('model-select');
    const switchBtn = document.getElementById('model-switch-btn');
    if (!dropdown || !switchBtn) return;
    switchBtn.disabled = !dropdown.value;
}

function updateModelStore(localModels) {
    const localNames = new Set(localModels.map(m => m.name));
    document.querySelectorAll('[data-pull-model]').forEach(btn => {
        const name = btn.getAttribute('data-pull-model');
        if (localNames.has(name)) {
            btn.textContent = 'Downloaded';
            btn.disabled = true;
            btn.classList.remove('btn-primary');
            btn.classList.add('btn-secondary');
        }
    });
}

function renderPullProgress(pullingModels) {
    const progressArea = document.getElementById('model-pull-progress-area');
    if (!progressArea) return;

    for (const pm of pullingModels) {
        let progressEl = document.querySelector(`[data-pull-progress="${pm.name}"]`);
        if (!progressEl) {
            progressEl = document.createElement('div');
            progressEl.className = 'pull-progress-item';
            progressEl.setAttribute('data-pull-progress', pm.name);
            progressEl.innerHTML = `
                <div class="pull-progress-header">
                    <span class="pull-progress-name">${escapeHtml(pm.name)}</span>
                    <span class="progress-status">${escapeHtml(pm.message || pm.status)}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-bar-fill" style="width: ${Math.round(pm.progress * 100)}%"></div>
                </div>
            `;
            progressArea.appendChild(progressEl);
        } else {
            const fill = progressEl.querySelector('.progress-bar-fill');
            const statusText = progressEl.querySelector('.progress-status');
            if (fill) fill.style.width = `${Math.round(pm.progress * 100)}%`;
            if (statusText) statusText.textContent = pm.message || pm.status;
        }

        if (pm.status === 'done') {
            setTimeout(() => {
                if (progressEl && progressEl.parentNode) progressEl.remove();
                refreshModelList();
            }, 2000);
        } else if (pm.status === 'error') {
            const statusText = progressEl.querySelector('.progress-status');
            if (statusText) {
                statusText.textContent = 'Error: ' + (pm.error || pm.message || 'Unknown error');
                statusText.className = 'progress-status error';
            }
            document.querySelectorAll(`[data-pull-model="${pm.name}"]`).forEach(btn => {
                btn.disabled = false;
            });
        }
    }
}

function renderDeleteButtons(models) {
    const deleteArea = document.getElementById('model-delete-area');
    if (!deleteArea) return;
    deleteArea.innerHTML = '';
    for (const m of models) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-small btn-danger model-delete-btn';
        btn.textContent = 'Delete ' + m.name;
        btn.setAttribute('data-delete-model', m.name);
        if (m.name === currentActiveModel) {
            btn.disabled = true;
            btn.title = 'Cannot delete the active model';
        }
        btn.addEventListener('click', () => handleModelDelete(m.name));
        deleteArea.appendChild(btn);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const switchBtn = document.getElementById('model-switch-btn');
    if (switchBtn) switchBtn.addEventListener('click', handleModelSwitch);
    const modelSelect = document.getElementById('model-select');
    if (modelSelect) modelSelect.addEventListener('change', updateSwitchButton);

    const customPullBtn = document.getElementById('model-custom-pull-btn');
    const customInput = document.getElementById('model-custom-name');
    if (customPullBtn && customInput) {
        customPullBtn.addEventListener('click', () => {
            const name = customInput.value.trim();
            if (name) handlePull(name);
        });
        customInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const name = customInput.value.trim();
                if (name) handlePull(name);
            }
        });
    }

    document.querySelectorAll('.model-pull-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const modelName = btn.getAttribute('data-pull-model');
            if (modelName) handlePull(modelName);
        });
    });

    refreshModelList();
});
