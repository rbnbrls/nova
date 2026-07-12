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
            
            html += `
                <li class="todo-item">
                    <span class="todo-title">${task.title}</span>
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


