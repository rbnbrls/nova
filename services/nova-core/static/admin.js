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
    document.getElementById('admin-error-banner').setAttribute('hidden', '');
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
    document.getElementById('admin-error-banner').removeAttribute('hidden');
};
