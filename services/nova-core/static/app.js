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
    const phoneInput = document.getElementById('phone-input');
    
    if (linkedVal) {
        linkedVal.textContent = userPrefs.whatsapp_number ? '+' + userPrefs.whatsapp_number : 'None Linked';
    }
    if (phoneInput && document.getElementById('verify-code-row').classList.contains('hidden')) {
        phoneInput.value = userPrefs.whatsapp_number || '';
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
        
        // Reset verify view
        cancelVerifyState();
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

function cancelVerifyState() {
    document.getElementById('verify-code-row').classList.add('hidden');
    document.getElementById('request-code-row').classList.remove('hidden');
    document.getElementById('code-input').value = '';
    clearMsg();
}

// Request verification code button click
const btnRequestCode = document.getElementById('btn-request-code');
if (btnRequestCode) {
    btnRequestCode.addEventListener('click', async () => {
        clearMsg();
        const number = document.getElementById('phone-input').value.trim();
        if (!number) {
            showMsg('Please enter a WhatsApp phone number', true);
            return;
        }
        
        try {
            const resp = await fetch('/api/preferences/request-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user: activeSettingsUser, number: number })
            });
            const data = await resp.json();
            if (resp.ok) {
                showMsg('Verification code sent successfully!');
                document.getElementById('request-code-row').classList.add('hidden');
                document.getElementById('verify-code-row').classList.remove('hidden');
            } else {
                showMsg(data.detail || 'Failed to request verification code', true);
            }
        } catch (err) {
            showMsg('Network error requesting verification code', true);
        }
    });
}

// Verify and Link button click
const btnVerifyCode = document.getElementById('btn-verify-code');
if (btnVerifyCode) {
    btnVerifyCode.addEventListener('click', async () => {
        clearMsg();
        const code = document.getElementById('code-input').value.trim();
        if (!code) {
            showMsg('Please enter the 6-digit code', true);
            return;
        }
        
        try {
            const resp = await fetch('/api/preferences/verify-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user: activeSettingsUser, code: code })
            });
            const data = await resp.json();
            if (resp.ok) {
                showMsg(`Successfully linked +${data.linked_number}!`);
                setTimeout(() => {
                    cancelVerifyState();
                    fetchPreferences();
                }, 2000);
            } else {
                showMsg(data.detail || 'Incorrect or expired code', true);
            }
        } catch (err) {
            showMsg('Network error verifying code', true);
        }
    });
}

// Cancel verification
const btnCancelVerify = document.getElementById('btn-cancel-verify');
if (btnCancelVerify) {
    btnCancelVerify.addEventListener('click', () => {
        cancelVerifyState();
    });
}

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


