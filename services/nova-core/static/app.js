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

// Connect to SSE Stream
const eventSource = new EventSource('/dashboard/stream');

eventSource.onmessage = function(event) {
    try {
        const data = JSON.parse(event.data);
        updateTasks(data.tasks);
        updateEvents(data.events);
        updateAudit(data.audit);
        document.querySelector('.status-text').textContent = 'Live Connected';
        document.querySelector('.pulse-dot').style.backgroundColor = '#10b981';
    } catch (e) {
        console.error('Failed to parse SSE event:', e);
    }
};

eventSource.onerror = function(err) {
    console.error('SSE connection lost, reconnecting...', err);
    document.querySelector('.status-text').textContent = 'Disconnected (Reconnecting...)';
    document.querySelector('.pulse-dot').style.backgroundColor = '#ef4444';
};

// Render Tasks
function updateTasks(tasks) {
    const container = document.getElementById('tasks-content');
    const countBadge = document.getElementById('tasks-count');
    
    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="placeholder-loader">No active tasks.</div>';
        countBadge.textContent = '0';
        return;
    }
    
    countBadge.textContent = tasks.length;
    
    // Group by assignee
    const groups = {};
    tasks.forEach(t => {
        const name = t.assignee.toLowerCase();
        if (!groups[name]) groups[name] = [];
        groups[name].push(t);
    });
    
    let html = '';
    const now = new Date();
    
    // Render order: ruben, meral, household, others
    const sortedKeys = Object.keys(groups).sort((a, b) => {
        if (a === 'ruben') return -1;
        if (b === 'ruben') return 1;
        if (a === 'meral') return -1;
        if (b === 'meral') return 1;
        if (a === 'household') return -1;
        if (b === 'household') return 1;
        return a.localeCompare(b);
    });
    
    sortedKeys.forEach(name => {
        const groupTasks = groups[name];
        const displayName = name.charAt(0).toUpperCase() + name.slice(1);
        const sectionClass = name === 'household' ? 'assignee-section household' : 'assignee-section';
        
        html += `
            <div class="${sectionClass}">
                <div class="assignee-name">${displayName}</div>
                <ul class="todo-list">
        `;
        
        groupTasks.forEach(task => {
            let dueHtml = '';
            if (task.due_at) {
                const due = new Date(task.due_at);
                const isOverdue = due < now;
                const overdueClass = isOverdue ? 'todo-due overdue' : 'todo-due';
                const formattedTime = due.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + due.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                dueHtml = `<span class="${overdueClass}">${isOverdue ? 'Overdue: ' : ''}${formattedTime}</span>`;
            }
            
            const overdueBadge = task.overdue
                ? `<span class="badge badge-warning">OVERDUE</span> `
                : '';
            
            html += `
                <li class="todo-item${task.overdue ? ' overdue-flag' : ''}">
                    <span class="todo-title">${overdueBadge}${escapeHtml(task.title)}</span>
                    ${dueHtml}
                </li>
            `;
        });
        
        html += `
                </ul>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Render Events
function updateEvents(events) {
    const container = document.getElementById('events-content');
    const countBadge = document.getElementById('events-count');
    
    if (!events || events.length === 0) {
        container.innerHTML = '<div class="placeholder-loader">No upcoming events.</div>';
        countBadge.textContent = '0';
        return;
    }
    
    countBadge.textContent = events.length;
    
    let html = '';
    events.forEach(event => {
        let dayBox = '<div class="event-time-box"><span class="event-day">ALL</span><span class="event-time">DAY</span></div>';
        let timeRange = 'All Day';
        
        if (event.start) {
            const start = new Date(event.start);
            const dayStr = start.toLocaleDateString([], { weekday: 'short' });
            const timeStr = start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            
            dayBox = `
                <div class="event-time-box">
                    <span class="event-day">${dayStr}</span>
                    <span class="event-time">${timeStr}</span>
                </div>
            `;
            
            if (event.end) {
                const end = new Date(event.end);
                timeRange = `${timeStr} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
            } else {
                timeRange = timeStr;
            }
        }
        
        const locationStr = event.location ? `<span class="event-meta">📍 ${event.location}</span>` : '';
        
        html += `
            <div class="event-item">
                ${dayBox}
                <div class="event-details">
                    <span class="event-title">${event.title}</span>
                    <span class="event-meta">🕒 ${timeRange}</span>
                    ${locationStr}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Render Audit Activity Feed
function updateAudit(entries) {
    const container = document.getElementById('audit-content');
    const countBadge = document.getElementById('audit-count');

    if (!entries || entries.length === 0) {
        container.innerHTML = '<div class="placeholder-loader">No recent activity.</div>';
        countBadge.textContent = '0';
        return;
    }

    countBadge.textContent = entries.length;

    let html = '<table class="audit-table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Status</th></tr></thead><tbody>';
    entries.forEach(entry => {
        const ts = entry.timestamp ? new Date(entry.timestamp) : new Date();
        const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
        const statusClass = entry.status === 'denied' ? 'status-denied' : 'status-completed';
        const statusLabel = entry.status === 'denied' ? '\u{1F6AB} Denied' : '\u2705 Done';
        const confirmIcon = entry.confirmation_required ? '\u{1F6E1}\uFE0F ' : '';
        html += `<tr>
            <td class="audit-time">${timeStr}</td>
            <td class="audit-user">${entry.user_name || 'system'}</td>
            <td class="audit-action">${confirmIcon}${escapeHtml(entry.action_summary)}</td>
            <td class="audit-status"><span class="${statusClass}">${statusLabel}</span></td>
        </tr>`;
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// --- Preferences & Onboarding Settings ---
let preferencesCache = {};
let activeSettingsUser = 'Ruben';

async function fetchPreferences() {
    try {
        const resp = await fetch('/api/preferences');
        if (resp.ok) {
            preferencesCache = await resp.json();
            updateSettingsUI();
        }
    } catch (err) {
        console.error('Failed to fetch preferences:', err);
    }
}

function updateSettingsUI() {
    const userPrefs = preferencesCache[activeSettingsUser] || { 
        whatsapp_number: '', 
        morning_enabled: true, 
        morning_time: '07:00',
        weekly_enabled: true,
        weekly_day: 1,
        weekly_time: '09:00',
        dnd_enabled: false,
        dnd_start: '22:00',
        dnd_end: '07:00'
    };
    const linkedVal = document.getElementById('linked-number-val');
    if (linkedVal) {
        linkedVal.textContent = userPrefs.whatsapp_number ? '+' + userPrefs.whatsapp_number : 'None Linked';
    }

    const telegramStatus = document.getElementById('telegram-status-val');
    if (telegramStatus) {
        const channels = userPrefs.channels_enabled || [];
        telegramStatus.textContent = channels.includes('telegram') ? 'Linked' : 'Not Linked';
        telegramStatus.style.color = channels.includes('telegram') ? 'var(--success-color)' : 'var(--text-secondary)';
    }
    
    const morningEnabled = document.getElementById('morning-enabled');
    const morningTime = document.getElementById('morning-time');
    const weeklyEnabled = document.getElementById('weekly-enabled');
    const weeklyDay = document.getElementById('weekly-day');
    const weeklyTime = document.getElementById('weekly-time');
    const dndEnabled = document.getElementById('dnd-enabled');
    const dndStart = document.getElementById('dnd-start');
    const dndEnd = document.getElementById('dnd-end');
    
    if (morningEnabled) morningEnabled.checked = userPrefs.morning_enabled;
    if (morningTime) morningTime.value = userPrefs.morning_time;
    if (weeklyEnabled) weeklyEnabled.checked = userPrefs.weekly_enabled;
    if (weeklyDay) weeklyDay.value = userPrefs.weekly_day;
    if (weeklyTime) weeklyTime.value = userPrefs.weekly_time;
    if (dndEnabled) dndEnabled.checked = userPrefs.dnd_enabled;
    if (dndStart) dndStart.value = userPrefs.dnd_start;
    if (dndEnd) dndEnd.value = userPrefs.dnd_end;
}

// User tab switching
document.querySelectorAll('.settings-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        activeSettingsUser = tab.getAttribute('data-user');
        
        updateSettingsUI();
    });
});

function showMsg(text, isError = false) {
    const msgDiv = document.getElementById('settings-msg');
    if (msgDiv) {
        msgDiv.textContent = text;
        msgDiv.className = isError ? 'settings-message error' : 'settings-message success';
        msgDiv.style.display = 'block';
    }
}

function clearMsg() {
    const msgDiv = document.getElementById('settings-msg');
    if (msgDiv) {
        msgDiv.textContent = '';
        msgDiv.style.display = 'none';
    }
}

// --- WhatsApp Linking Modal ---
let modalActiveUser = 'Ruben';
let modalState = 'number';  // 'number' | 'code' | 'result'
let modalPendingNumber = '';

function showModalState(state) {
    // Hide all state divs
    document.getElementById('modal-state-number').classList.add('hidden');
    document.getElementById('modal-state-code').classList.add('hidden');
    document.getElementById('modal-state-result').classList.add('hidden');

    const title = document.getElementById('modal-title');
    if (state === 'number') {
        title.textContent = 'Link WhatsApp';
        document.getElementById('modal-state-number').classList.remove('hidden');
    } else if (state === 'code') {
        title.textContent = 'Verify Code';
        document.getElementById('modal-state-code').classList.remove('hidden');
    } else if (state === 'result') {
        title.textContent = 'Linking Complete';
        document.getElementById('modal-state-result').classList.remove('hidden');
    }
    modalState = state;
}

function hideModal() {
    document.getElementById('link-modal').classList.add('hidden');
    document.getElementById('modal-phone-input').value = '';
    document.getElementById('modal-code-input').value = '';
    clearModalErrors();
    showModalState('number');
}

function showModalError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = message;
        el.classList.remove('hidden');
    }
}

function clearModalErrors() {
    ['modal-error-msg', 'modal-code-error-msg'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
}

// Open modal button
document.getElementById('btn-open-link-modal').addEventListener('click', () => {
    // Set active user from settings tabs
    modalActiveUser = activeSettingsUser;
    // Reset identity tab highlights
    document.querySelectorAll('.modal-user-tab').forEach(tab => {
        tab.classList.toggle('active', tab.getAttribute('data-user') === modalActiveUser);
    });
    clearModalErrors();
    document.getElementById('modal-phone-input').value = '';
    document.getElementById('modal-code-input').value = '';
    showModalState('number');
    document.getElementById('link-modal').classList.remove('hidden');
});

// Modal identity tabs
document.querySelectorAll('.modal-user-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.modal-user-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        modalActiveUser = tab.getAttribute('data-user');
    });
});

// Send Code button
document.getElementById('modal-btn-send-code').addEventListener('click', async () => {
    clearModalErrors();
    const number = document.getElementById('modal-phone-input').value.trim();
    if (!number) {
        showModalError('modal-error-msg', 'Please enter a phone number');
        return;
    }
    if (!/^\d{8,}$/.test(number.replace(/^\+/, ''))) {
        showModalError('modal-error-msg', 'Invalid phone number. Use E.164 format (e.g. 31612345678)');
        return;
    }

    const cleanNumber = number.replace(/^\+/, '');
    try {
        const resp = await fetch('/dashboard/link-whatsapp/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: modalActiveUser, number: cleanNumber })
        });
        const data = await resp.json();
        if (resp.ok) {
            modalPendingNumber = cleanNumber;
            document.getElementById('modal-sent-to').textContent = '+' + cleanNumber;
            document.getElementById('modal-code-input').value = '';
            clearModalErrors();
            showModalState('code');
        } else if (resp.status === 429) {
            showModalError('modal-error-msg', data.detail || 'Rate limit reached. Please wait 5 minutes.');
        } else {
            showModalError('modal-error-msg', data.detail || 'Failed to send code. Please try again.');
        }
    } catch (err) {
        showModalError('modal-error-msg', 'Network error. Please check your connection and try again.');
    }
});

// Verify & Link button
document.getElementById('modal-btn-verify').addEventListener('click', async () => {
    clearModalErrors();
    const code = document.getElementById('modal-code-input').value.trim();
    if (!code || code.length !== 6) {
        showModalError('modal-code-error-msg', 'Please enter the 6-digit code');
        return;
    }

    try {
        const resp = await fetch('/dashboard/link-whatsapp/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: modalActiveUser, code: code })
        });
        const data = await resp.json();
        if (resp.ok) {
            // Success state
            const resultMsg = document.getElementById('modal-result-msg');
            resultMsg.innerHTML = '✅ Successfully linked +' + data.linked_number + '!';
            resultMsg.className = 'modal-result-success';
            document.getElementById('modal-btn-retry').classList.add('hidden');
            showModalState('result');
            // Auto-refresh preferences to update the linked number display
            fetchPreferences();
            // Auto-close after 3 seconds
            setTimeout(() => {
                hideModal();
                // Reset retry visibility for next time
                document.getElementById('modal-btn-retry').classList.remove('hidden');
            }, 3000);
        } else {
            showModalError('modal-code-error-msg', data.detail || 'Incorrect or expired code');
        }
    } catch (err) {
        showModalError('modal-code-error-msg', 'Network error. Please try again.');
    }
});

// Resend Code button
document.getElementById('modal-btn-resend').addEventListener('click', async () => {
    clearModalErrors();
    const number = modalPendingNumber;
    if (!number) {
        showModalState('number');
        return;
    }

    try {
        const resp = await fetch('/dashboard/link-whatsapp/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: modalActiveUser, number: number })
        });
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('modal-code-input').value = '';
            clearModalErrors();
            showModalError('modal-code-error-msg', 'A new code has been sent.');
        } else if (resp.status === 429) {
            showModalError('modal-code-error-msg', data.detail || 'Please wait before requesting a new code.');
        } else {
            showModalError('modal-code-error-msg', data.detail || 'Failed to resend. Please try again.');
        }
    } catch (err) {
        showModalError('modal-code-error-msg', 'Network error. Please try again.');
    }
});

// Try Again button (from error state)
document.getElementById('modal-btn-retry').addEventListener('click', () => {
    clearModalErrors();
    showModalState('number');
});

// Cancel / Close buttons
document.getElementById('modal-btn-cancel').addEventListener('click', hideModal);
document.getElementById('modal-btn-close-result').addEventListener('click', hideModal);

// Click on overlay background closes modal
document.getElementById('link-modal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('link-modal')) {
        hideModal();
    }
});

// --- Telegram Linking Modal ---
let telegramModalActiveUser = 'Ruben';
let telegramModalState = 'start';  // 'start' | 'code' | 'result'

function showTelegramModalState(state) {
    document.getElementById('telegram-state-start').classList.add('hidden');
    document.getElementById('telegram-state-code').classList.add('hidden');
    document.getElementById('telegram-state-result').classList.add('hidden');

    const title = document.getElementById('telegram-modal-title');
    if (state === 'start') {
        title.textContent = 'Link Telegram';
        document.getElementById('telegram-state-start').classList.remove('hidden');
    } else if (state === 'code') {
        title.textContent = 'Verify Code';
        document.getElementById('telegram-state-code').classList.remove('hidden');
    } else if (state === 'result') {
        title.textContent = 'Linking Complete';
        document.getElementById('telegram-state-result').classList.remove('hidden');
    }
    telegramModalState = state;
}

function hideTelegramModal() {
    document.getElementById('link-telegram-modal').classList.add('hidden');
    document.getElementById('telegram-code-input').value = '';
    clearTelegramModalErrors();
    showTelegramModalState('start');
}

function showTelegramModalError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = message;
        el.classList.remove('hidden');
    }
}

function clearTelegramModalErrors() {
    ['telegram-error-msg', 'telegram-code-error-msg'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
}

// Open Telegram modal button
document.getElementById('btn-open-telegram-modal').addEventListener('click', () => {
    telegramModalActiveUser = activeSettingsUser;
    document.querySelectorAll('.telegram-user-tab').forEach(tab => {
        tab.classList.toggle('active', tab.getAttribute('data-user') === telegramModalActiveUser);
    });
    clearTelegramModalErrors();
    document.getElementById('telegram-code-input').value = '';
    showTelegramModalState('start');
    document.getElementById('link-telegram-modal').classList.remove('hidden');
});

// Telegram modal identity tabs
document.querySelectorAll('.telegram-user-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.telegram-user-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        telegramModalActiveUser = tab.getAttribute('data-user');
    });
});

// Send Code button
document.getElementById('telegram-btn-send-code').addEventListener('click', async () => {
    clearTelegramModalErrors();
    try {
        const resp = await fetch('/dashboard/link-telegram/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: telegramModalActiveUser })
        });
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('telegram-code-input').value = '';
            clearTelegramModalErrors();
            showTelegramModalState('code');
        } else if (resp.status === 429) {
            showTelegramModalError('telegram-error-msg', data.detail || 'Rate limit reached. Please wait 5 minutes.');
        } else if (resp.status === 502) {
            showTelegramModalError('telegram-error-msg', data.detail || 'Failed to send code. Please try again.');
        } else {
            showTelegramModalError('telegram-error-msg', data.detail || 'Failed to send code. Please try again.');
        }
    } catch (err) {
        showTelegramModalError('telegram-error-msg', 'Network error. Please check your connection and try again.');
    }
});

// Verify & Link button
document.getElementById('telegram-btn-verify').addEventListener('click', async () => {
    clearTelegramModalErrors();
    const code = document.getElementById('telegram-code-input').value.trim();
    if (!code || code.length !== 6) {
        showTelegramModalError('telegram-code-error-msg', 'Please enter the 6-digit code');
        return;
    }

    try {
        const resp = await fetch('/dashboard/link-telegram/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: telegramModalActiveUser, code: code })
        });
        const data = await resp.json();
        if (resp.ok) {
            const resultMsg = document.getElementById('telegram-result-msg');
            resultMsg.innerHTML = '✅ Successfully linked Telegram!';
            resultMsg.className = 'modal-result-success';
            document.getElementById('telegram-btn-retry').classList.add('hidden');
            showTelegramModalState('result');
            // Auto-refresh preferences to update the Telegram status display
            fetchPreferences();
            // Auto-close after 3 seconds
            setTimeout(() => {
                hideTelegramModal();
                document.getElementById('telegram-btn-retry').classList.remove('hidden');
            }, 3000);
        } else {
            showTelegramModalError('telegram-code-error-msg', data.detail || 'Incorrect or expired code');
        }
    } catch (err) {
        showTelegramModalError('telegram-code-error-msg', 'Network error. Please try again.');
    }
});

// Resend Code button
document.getElementById('telegram-btn-resend').addEventListener('click', async () => {
    clearTelegramModalErrors();
    try {
        const resp = await fetch('/dashboard/link-telegram/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: telegramModalActiveUser })
        });
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('telegram-code-input').value = '';
            clearTelegramModalErrors();
            showTelegramModalError('telegram-code-error-msg', 'A new code has been sent.');
        } else if (resp.status === 429) {
            showTelegramModalError('telegram-code-error-msg', data.detail || 'Please wait before requesting a new code.');
        } else {
            showTelegramModalError('telegram-code-error-msg', data.detail || 'Failed to resend. Please try again.');
        }
    } catch (err) {
        showTelegramModalError('telegram-code-error-msg', 'Network error. Please try again.');
    }
});

// Try Again button (from error/result state)
document.getElementById('telegram-btn-retry').addEventListener('click', () => {
    clearTelegramModalErrors();
    showTelegramModalState('start');
});

// Cancel / Close buttons
document.getElementById('telegram-btn-cancel').addEventListener('click', hideTelegramModal);
document.getElementById('telegram-btn-close-result').addEventListener('click', hideTelegramModal);

// Click on overlay background closes modal
document.getElementById('link-telegram-modal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('link-telegram-modal')) {
        hideTelegramModal();
    }
});

// Save Briefing Settings button click
const btnSaveSettings = document.getElementById('btn-save-settings');
if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', async () => {
        clearMsg();
        
        const morningEnabled = document.getElementById('morning-enabled').checked;
        const morningTime = document.getElementById('morning-time').value;
        const weeklyEnabled = document.getElementById('weekly-enabled').checked;
        const weeklyDay = parseInt(document.getElementById('weekly-day').value, 10);
        const weeklyTime = document.getElementById('weekly-time').value;
        
        try {
            const resp = await fetch('/api/preferences/briefings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user: activeSettingsUser,
                    morning_enabled: morningEnabled,
                    morning_time: morningTime,
                    weekly_enabled: weeklyEnabled,
                    weekly_day: weeklyDay,
                    weekly_time: weeklyTime
                })
            });
            const data = await resp.json();
            if (resp.ok) {
                showMsg('Briefing settings saved successfully!');
                fetchPreferences();
            } else {
                showMsg(data.detail || 'Failed to save settings', true);
            }
        } catch (err) {
            showMsg('Network error saving briefing settings', true);
        }
    });
}

// Save DND Settings button click
const btnSaveDnd = document.getElementById('btn-save-dnd');
if (btnSaveDnd) {
    btnSaveDnd.addEventListener('click', async () => {
        clearMsg();
        
        const dndEnabled = document.getElementById('dnd-enabled').checked;
        const dndStart = document.getElementById('dnd-start').value;
        const dndEnd = document.getElementById('dnd-end').value;
        
        try {
            const resp = await fetch('/api/preferences/dnd', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user: activeSettingsUser,
                    dnd_enabled: dndEnabled,
                    dnd_start: dndStart,
                    dnd_end: dndEnd
                })
            });
            const data = await resp.json();
            if (resp.ok) {
                showMsg('DND settings saved successfully!');
                fetchPreferences();
            } else {
                showMsg(data.detail || 'Failed to save DND settings', true);
            }
        } catch (err) {
            showMsg('Network error saving DND settings', true);
        }
    });
}

// Initial fetch
fetchPreferences();

// --- Chat Section (Phase 39) ---
let activeChatUser = 'Ruben';
let chatInFlight = false;

// Chat user selector tabs
document.querySelectorAll('.chat-user-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.chat-user-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        activeChatUser = tab.getAttribute('data-user');
    });
});

// Send message on button click
document.getElementById('chat-btn-send').addEventListener('click', handleChatSubmit);

// Send message on Enter key - no wrapping <form> to avoid page reload
document.getElementById('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        handleChatSubmit();
    }
});

async function handleChatSubmit() {
    if (chatInFlight) return;  // Concurrent-send guard

    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    chatInFlight = true;
    input.disabled = true;
    document.getElementById('chat-btn-send').disabled = true;
    clearChatError();
    showChatLoading(true);

    // Store sent message before clearing input (keep on error)
    const sentMessage = message;
    input.value = '';

    try {
        const resp = await fetch('/dashboard/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: activeChatUser, message: sentMessage })
        });
        const data = await resp.json();
        if (resp.ok) {
            updateChat(sentMessage, data.reply);
        } else {
            showChatError(data.detail || 'Something went wrong. Please try again.');
        }
    } catch (err) {
        showChatError('Network error. Please check your connection and try again.');
    } finally {
        chatInFlight = false;
        input.disabled = false;
        document.getElementById('chat-btn-send').disabled = false;
        showChatLoading(false);
        input.focus();
    }
}

function updateChat(userMessage, novaReply) {
    const area = document.getElementById('chat-reply-area');
    const emptyMsg = document.getElementById('chat-empty');
    if (emptyMsg) emptyMsg.style.display = 'none';

    // Single-turn: show only the last exchange
    area.innerHTML = '';

    // User message — escapeHtml() prevents XSS
    const userDiv = document.createElement('div');
    userDiv.className = 'chat-message user';
    userDiv.innerHTML = '<div class="chat-message-label">You</div><div class="chat-message-text">' + escapeHtml(userMessage) + '</div>';
    area.appendChild(userDiv);

    // Nova reply — escapeHtml() prevents XSS from LLM-generated content
    const novaDiv = document.createElement('div');
    novaDiv.className = 'chat-message nova';
    novaDiv.innerHTML = '<div class="chat-message-label">Nova</div><div class="chat-message-text">' + escapeHtml(novaReply) + '</div>';
    area.appendChild(novaDiv);

    // Scroll to bottom
    area.scrollTop = area.scrollHeight;
}

function showChatLoading(visible) {
    const area = document.getElementById('chat-reply-area');
    const existing = document.getElementById('chat-loading-indicator');

    if (visible) {
        if (!existing) {
            const div = document.createElement('div');
            div.id = 'chat-loading-indicator';
            div.className = 'chat-loading';
            div.textContent = 'Nova is thinking...';
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
        }
    } else if (existing) {
        existing.remove();
    }
}

function showChatError(msg) {
    const el = document.getElementById('chat-error');
    if (el) {
        el.textContent = msg;
        el.classList.remove('hidden');
    }
}

function clearChatError() {
    const el = document.getElementById('chat-error');
    if (el) el.classList.add('hidden');
}

// --- Voice Input (quick task) ---
// Press-and-hold mic button using the browser Web Speech API. Transcript flows
// into the existing #chat-input / handleChatSubmit() path — no backend changes.
(function initVoiceInput() {
    const btnMic = document.getElementById('chat-btn-mic');
    const chatInput = document.getElementById('chat-input');
    const chatBtnSend = document.getElementById('chat-btn-send');
    if (!btnMic || !chatInput || !chatBtnSend) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    // Graceful degradation: leave the mic button disabled on unsupported browsers
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    let voiceInFlight = false;      // recognition currently active
    let didTranscribe = false;       // a final transcript was captured this press

    function resetRecordingUI() {
        btnMic.classList.remove('recording');
        voiceInFlight = false;
        // Re-enable inputs unless an existing chat submission is in flight
        if (!chatInFlight) {
            chatInput.disabled = false;
            chatBtnSend.disabled = false;
        }
    }

    // --- Recognition lifecycle handlers ---
    recognition.onresult = function (event) {
        const last = event.results[event.results.length - 1];
        if (last && last[0] && last[0].transcript) {
            const transcript = String(last[0].transcript).trim();
            if (transcript) {
                chatInput.value = transcript;
                didTranscribe = true;
            }
        }
    };

    recognition.onerror = function (event) {
        console.warn('Speech recognition error:', (event && event.error) || event);
        resetRecordingUI();
        showChatError('Voice input failed. Try again or type your message.');
    };

    recognition.onend = function () {
        resetRecordingUI();
    };

    // --- Press-and-hold handlers (mouse + touch + pointer) ---
    function startHold(e) {
        e.preventDefault();
        if (chatInFlight || voiceInFlight) return;
        voiceInFlight = true;
        didTranscribe = false;
        btnMic.classList.add('recording');
        chatInput.disabled = true;
        chatBtnSend.disabled = true;
        clearChatError();
        try {
            recognition.start();
        } catch (err) {
            // recognition may throw if started twice in quick succession
            console.warn('recognition.start() threw:', err);
            resetRecordingUI();
        }
    }

    function endHold(e) {
        if (!voiceInFlight) return;
        if (e) e.preventDefault();
        try {
            recognition.stop();
        } catch (err) {
            console.warn('recognition.stop() threw:', err);
        }
        // Capture the transcript locally before reset (recognition.onend will reset UI)
        const transcript = chatInput.value.trim();
        resetRecordingUI();
        if (didTranscribe || transcript) {
            // Submit through existing /dashboard/chat path
            handleChatSubmit();
        }
    }

    btnMic.addEventListener('mousedown', startHold);
    btnMic.addEventListener('touchstart', startHold, { passive: false });
    btnMic.addEventListener('pointerdown', startHold);

    btnMic.addEventListener('mouseup', endHold);
    btnMic.addEventListener('mouseleave', endHold);
    btnMic.addEventListener('touchend', endHold);
    btnMic.addEventListener('pointerup', endHold);
    btnMic.addEventListener('pointercancel', endHold);

    // Enable the mic button only on supported browsers
    btnMic.disabled = false;
})();

// --- Settings Modal (cog icon) ---
const settingsModal = document.getElementById('settings-modal');
const settingsCog = document.getElementById('btn-settings-cog');
const settingsClose = document.getElementById('btn-settings-close');

function showSettingsModal() {
    if (settingsModal) {
        settingsModal.classList.remove('hidden');
        fetchPreferences();  // Refresh data when opening
    }
}

function hideSettingsModal() {
    if (settingsModal) {
        settingsModal.classList.add('hidden');
    }
}

if (settingsCog) {
    settingsCog.addEventListener('click', showSettingsModal);
}

if (settingsClose) {
    settingsClose.addEventListener('click', hideSettingsModal);
}

// Click overlay background to close
if (settingsModal) {
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            hideSettingsModal();
        }
    });
}


