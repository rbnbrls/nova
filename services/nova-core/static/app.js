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
        if (typeof renderTraces === 'function') renderTraces(data.traces);
        document.querySelector('.status-text').textContent = 'Live Connected';
        document.querySelector('.pulse-dot').style.backgroundColor = '#10b981';
    } catch (e) {
        console.error('Failed to parse SSE event:', e);
    }
};

// Periodic trace fetch (independent from SSE poll cadence)
fetchTraces();
setInterval(fetchTraces, 30000);

eventSource.addEventListener('progress', function(event) {
    try {
        const data = JSON.parse(event.data);
        const indicator = document.getElementById('chat-loading-indicator');
        if (indicator && data.step && data.elapsed_s !== undefined) {
            const stepNames = {
                'llm': 'Nova is thinking',
                'add_task': 'Adding task',
                'complete_task': 'Completing task',
                'create_event': 'Creating event',
                'update_event': 'Updating event',
                'delete_event': 'Deleting event',
                'ha_call_service': 'Controlling home',
                'remember': 'Remembering',
                'forget': 'Forgetting',
                'send_email': 'Sending email',
                'read_email': 'Reading email',
            };
            const pretty = stepNames[data.step] || data.step.replace(/_/g, ' ');
            indicator.textContent = pretty + ' (' + data.elapsed_s + 's)';
            indicator.classList.remove('hidden');
        }
    } catch (e) {
        console.error('Failed to parse progress event:', e);
    }
});

eventSource.onerror = function(err) {
    console.error('SSE connection lost, reconnecting...', err);
    document.querySelector('.status-text').textContent = 'Disconnected (Reconnecting...)';
    document.querySelector('.pulse-dot').style.backgroundColor = '#ef4444';
};

const LABEL_COLORS = {
    'groceries': '#10b981',
    'weekly': '#8b5cf6',
    'urgent': '#ef4444',
    'chore': '#f59e0b',
    'errand': '#3b82f6',
    'home': '#06b6d4',
    'admin': '#ec4899',
    'shopping': '#14b8a6',
    'health': '#f97316',
    'finance': '#84cc16',
};

function getLabelColor(label) {
    return LABEL_COLORS[label.toLowerCase()] || '#6b7280';
}

let activeLabelFilter = '';
let allTasksData = [];

// Render Label Filter Bar
function updateLabelFilters(tasks) {
    const dynamicContainer = document.getElementById('label-filter-dynamic');
    if (!dynamicContainer) return;

    const labelSet = new Set();
    tasks.forEach(t => {
        if (t.labels && t.labels.length) {
            t.labels.forEach(l => labelSet.add(l));
        }
    });
    const sortedLabels = Array.from(labelSet).sort();

    let html = '';
    sortedLabels.forEach(label => {
        const active = activeLabelFilter === label ? ' active' : '';
        html += `<button class="label-filter-pill${active}" data-label="${escapeHtml(label)}" style="${active ? 'background:' + getLabelColor(label) + ';border-color:' + getLabelColor(label) + ';' : ''}">${escapeHtml(label)}</button>`;
    });
    dynamicContainer.innerHTML = html;

    document.querySelectorAll('.label-filter-pill').forEach(btn => {
        btn.addEventListener('click', () => {
            const label = btn.getAttribute('data-label');
            activeLabelFilter = activeLabelFilter === label ? '' : label;
            document.querySelectorAll('.label-filter-pill').forEach(b => {
                const isActive = b.getAttribute('data-label') === activeLabelFilter;
                b.classList.toggle('active', isActive);
                const lbl = b.getAttribute('data-label');
                if (isActive && lbl) {
                    b.style.background = getLabelColor(lbl);
                    b.style.borderColor = getLabelColor(lbl);
                } else {
                    b.style.background = '';
                    b.style.borderColor = '';
                }
            });
            applyTaskFilter();
        });
    });
}

function applyTaskFilter() {
    const filtered = activeLabelFilter
        ? allTasksData.filter(t => t.labels && t.labels.includes(activeLabelFilter))
        : allTasksData;
    renderTaskCards(filtered);
}

// Render Tasks (enhanced)
function updateTasks(tasks) {
    allTasksData = tasks || [];
    updateLabelFilters(allTasksData);
    applyTaskFilter();
}

function renderTaskCards(tasks) {
    const container = document.getElementById('tasks-content');
    const countBadge = document.getElementById('tasks-count');

    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="placeholder-loader">No active tasks.</div>';
        countBadge.textContent = '0';
        return;
    }

    countBadge.textContent = tasks.length;

    const groups = {};
    tasks.forEach(t => {
        const name = t.assignee.toLowerCase();
        if (!groups[name]) groups[name] = [];
        groups[name].push(t);
    });

    let html = '';
    const now = new Date();

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
                dueHtml = `<span class="${overdueClass}" onclick="event.stopPropagation()">${isOverdue ? 'Overdue: ' : ''}${formattedTime}</span>`;
            }

            const overdueBadge = task.overdue
                ? `<span class="badge badge-warning">OVERDUE</span> `
                : '';

            // Label pills
            let labelHtml = '';
            if (task.labels && task.labels.length) {
                labelHtml = '<span class="task-label-pills">';
                task.labels.forEach(l => {
                    labelHtml += `<span class="task-label-pill" style="background:${getLabelColor(l)}20;color:${getLabelColor(l)};border-color:${getLabelColor(l)}40;">${escapeHtml(l)}</span>`;
                });
                labelHtml += '</span>';
            }

            // Planning state dot
            let planningDot = '';
            if (task.planning_state && task.planning_state !== 'unscheduled') {
                const stateColors = {
                    'scheduled': '#8b5cf6',
                    'in_progress': '#10b981',
                    'completed': '#6b7280',
                    'blocked': '#ef4444',
                };
                planningDot = `<span class="planning-dot" style="background:${stateColors[task.planning_state] || '#6b7280'}" title="${task.planning_state.replace('_', ' ')}"></span>`;
            }

            // Blocker icon
            let blockerIcon = '';
            if (task.blocked_by && task.blocked_by.length) {
                blockerIcon = `<span class="blocker-icon" title="Blocked by: ${task.blocked_by.join(', ')}">\u26D4</span>`;
            }

            // Notes badge
            let notesBadge = '';
            if (task.note_count > 0) {
                notesBadge = `<span class="notes-badge" title="${task.note_count} note(s)">\uD83D\uDCC4 ${task.note_count}</span>`;
            }

            // Template badge
            let templateBadge = '';
            if (task.is_template) {
                templateBadge = `<span class="template-badge">\uD83D\uDCCB Template</span>`;
            }

            html += `
                <li class="todo-item${task.overdue ? ' overdue-flag' : ''}" data-task-id="${task.id}" onclick="openTaskDetail('${task.id}')">
                    <div class="todo-main">
                        <div class="todo-title-row">
                            ${planningDot}
                            ${overdueBadge}
                            <span class="todo-title">${escapeHtml(task.title)}</span>
                            ${templateBadge}
                        </div>
                        <div class="todo-meta-row">
                            ${labelHtml}
                            ${blockerIcon}
                            ${notesBadge}
                        </div>
                    </div>
                    <div class="todo-actions">
                        ${dueHtml}
                    </div>
                </li>
            `;
        });

        html += `
                </ul>
            </div>
        `;
    });

    container.innerHTML = html;

    // Inline reassign via assignee section click
    document.querySelectorAll('.assignee-name').forEach(el => {
        el.addEventListener('click', function() {
            // Highlight, no inline reassign yet — detail panel covers it
        });
    });
}

// Task Detail Panel
async function openTaskDetail(taskId) {
    const overlay = document.getElementById('task-detail-overlay');
    const body = document.getElementById('task-detail-body');
    const title = document.getElementById('task-detail-title');
    overlay.classList.remove('hidden');
    title.textContent = 'Loading...';
    body.innerHTML = '<div class="placeholder-loader">Loading task detail...</div>';

    try {
        const resp = await fetch('/dashboard/task/' + taskId);
        if (!resp.ok) {
            body.innerHTML = '<div class="placeholder-loader">Failed to load task detail.</div>';
            return;
        }
        const data = await resp.json();
        title.textContent = escapeHtml(data.title);

        let html = '';
        html += `<div class="detail-field"><span class="detail-label">Status</span><span class="detail-value">${escapeHtml(data.status)}</span></div>`;
        html += `<div class="detail-field"><span class="detail-label">Assignee</span><span class="detail-value">${escapeHtml(data.assignee)}</span></div>`;
        html += `<div class="detail-field"><span class="detail-label">Priority</span><span class="detail-value priority-${data.priority}">${escapeHtml(data.priority)}</span></div>`;
        if (data.due_at) {
            html += `<div class="detail-field"><span class="detail-label">Due</span><span class="detail-value">${new Date(data.due_at).toLocaleString()}</span></div>`;
        }
        if (data.planning_state) {
            html += `<div class="detail-field"><span class="detail-label">Planning State</span><span class="detail-value">${escapeHtml(data.planning_state.replace('_', ' '))}</span></div>`;
        }
        if (data.labels && data.labels.length) {
            const labelPills = data.labels.map(l =>
                `<span class="task-label-pill" style="background:${getLabelColor(l)}20;color:${getLabelColor(l)};border-color:${getLabelColor(l)}40;">${escapeHtml(l)}</span>`
            ).join(' ');
            html += `<div class="detail-field"><span class="detail-label">Labels</span><span class="detail-value">${labelPills}</span></div>`;
        }
        if (data.is_template) {
            html += `<div class="detail-field"><span class="detail-label">Template</span><span class="detail-value">\uD83D\uDCCB This task is a template</span></div>`;
        }
        if (data.template_title) {
            html += `<div class="detail-field"><span class="detail-label">From Template</span><span class="detail-value template-source" onclick="openTaskDetail('${data.template_id}')">\uD83D\uDD17 ${escapeHtml(data.template_title)}</span></div>`;
        }

        // Blockers
        if (data.blockers && data.blockers.length) {
            html += `<div class="detail-field"><span class="detail-label">Blocked By</span><span class="detail-value blocker-list">`;
            data.blockers.forEach(b => {
                html += `<span class="blocker-item" onclick="openTaskDetail('${b.id}')">\u26D4 ${escapeHtml(b.title)}</span> `;
            });
            html += `</span></div>`;
        }

        // Dependents
        if (data.dependents && data.dependents.length) {
            html += `<div class="detail-field"><span class="detail-label">Blocks</span><span class="detail-value">`;
            data.dependents.forEach(d => {
                html += `<span class="blocker-item" onclick="openTaskDetail('${d.id}')">${escapeHtml(d.title)}</span> `;
            });
            html += `</span></div>`;
        }

        // Notes
        html += `<div class="detail-notes-section"><h4 class="detail-section-title">Notes (${data.notes.length})</h4>`;
        if (data.notes.length === 0) {
            html += `<p class="detail-empty">No notes yet.</p>`;
        } else {
            html += `<div class="detail-notes-list">`;
            data.notes.forEach(n => {
                const author = n.author ? escapeHtml(n.author) : 'system';
                const ts = n.created_at ? new Date(n.created_at).toLocaleString() : '';
                html += `<div class="detail-note-item"><span class="detail-note-meta">${author} \u2014 ${ts}</span><div class="detail-note-content">${escapeHtml(n.content)}</div></div>`;
            });
            html += `</div>`;
        }
        html += `</div>`;

        body.innerHTML = html;
    } catch (err) {
        body.innerHTML = '<div class="placeholder-loader">Error loading task detail.</div>';
        console.error('Failed to load task detail:', err);
    }
}

function closeTaskDetail() {
    document.getElementById('task-detail-overlay').classList.add('hidden');
}

// Close task detail on overlay click
document.getElementById('task-detail-overlay').addEventListener('click', (e) => {
    if (e.target === document.getElementById('task-detail-overlay')) {
        closeTaskDetail();
    }
});
document.getElementById('task-detail-close').addEventListener('click', closeTaskDetail);

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
        const statusClass = entry.status === 'denied' ? 'status-denied' : entry.status === 'pending_confirmation' ? 'status-pending' : 'status-completed';
        const statusLabel = entry.status === 'denied' ? '\u{1F6AB} Denied' : entry.status === 'pending_confirmation' ? '\u23F3 Pending' : '\u2705 Done';
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

// --- Traces Panel: Response Time Monitoring ---
let lastTracesData = [];

async function fetchTraces() {
    try {
        const resp = await fetch('/dashboard/traces?limit=15');
        if (resp.ok) {
            const data = await resp.json();
            renderTraces(data.traces || []);
        }
    } catch (e) {
        console.error('Failed to fetch traces:', e);
    }
}

function renderTraces(traces) {
    const container = document.getElementById('traces-content');
    const countBadge = document.getElementById('traces-count');
    if (!container) return;

    lastTracesData = traces;

    if (!traces || traces.length === 0) {
        container.innerHTML = '<div class="placeholder-loader">No agent traces yet.</div>';
        if (countBadge) countBadge.textContent = '0';
        return;
    }

    if (countBadge) countBadge.textContent = traces.length;

    let html = '<table class="traces-table"><thead><tr><th>Time</th><th>User</th><th>Total</th><th>Iters</th><th>Breakdown</th></tr></thead><tbody>';
    traces.forEach(function(trace) {
        const ts = trace.created_at ? new Date(trace.created_at) : new Date();
        const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
        const totalSec = (trace.total_latency_ms / 1000).toFixed(1);
        const stuckClass = trace.got_stuck ? ' trace-stuck' : '';
        const errClass = trace.error_count > 0 ? ' trace-error' : '';

        html += '<tr class="trace-turn' + stuckClass + errClass + '" onclick="toggleTraceDetail(\'' + escapeHtml(trace.id) + '\')">';
        html += '<td class="trace-time">' + timeStr + '</td>';
        html += '<td class="trace-user">' + escapeHtml(trace.user) + '</td>';
        html += '<td class="trace-total">' + totalSec + 's</td>';
        html += '<td class="trace-iters">' + (trace.iteration_count || 1) + '</td>';
        html += '<td class="trace-toggle">' + (trace.got_stuck ? '\u26A0\uFE0F' : '\u25BC') + '</td>';
        html += '</tr>';

        // Detail row (hidden by default, shown via toggleTraceDetail)
        if (trace.iterations && trace.iterations.length) {
            var detailId = 'trace-detail-' + trace.id.replace(/[^a-zA-Z0-9]/g, '');
            html += '<tr id="' + detailId + '" class="trace-detail-row hidden">';
            html += '<td colspan="5"><div class="trace-detail-inner">';
            html += '<div class="trace-summary">' + trace.token_count + ' tokens total';
            if (trace.error_count > 0) html += ' \u00B7 ' + trace.error_count + ' error(s)';
            html += '</div>';
            html += '<table class="trace-iter-table"><thead><tr><th>#</th><th>Step</th><th>LLM (s)</th><th>Tool (s)</th><th>Tool</th><th>Tokens</th></tr></thead><tbody>';
            trace.iterations.forEach(function(it, idx) {
                const llmSec = (it.llm_time_ms / 1000).toFixed(1);
                const toolSec = it.tool_time_ms ? (it.tool_time_ms / 1000).toFixed(1) : '-';
                const toolName = it.tool_name || '-';
                html += '<tr>';
                html += '<td>' + (idx + 1) + '</td>';
                html += '<td>' + (toolName !== '-' ? 'Tool' : 'Final') + '</td>';
                html += '<td class="timing-num' + (it.llm_time_ms > 10000 ? ' timing-slow' : '') + '">' + llmSec + '</td>';
                html += '<td class="timing-num' + (it.tool_time_ms > 3000 ? ' timing-slow' : '') + '">' + toolSec + '</td>';
                html += '<td>' + escapeHtml(toolName) + '</td>';
                html += '<td class="timing-num">' + it.prompt_tokens + '\u2192' + it.completion_tokens + '</td>';
                html += '</tr>';
            });
            html += '</tbody></table></div></td></tr>';
        }
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

function toggleTraceDetail(traceId) {
    var detailId = 'trace-detail-' + traceId.replace(/[^a-zA-Z0-9]/g, '');
    var row = document.getElementById(detailId);
    if (row) row.classList.toggle('hidden');
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
            updateChat(sentMessage, data.reply, data.trace || null);
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

function updateChat(userMessage, novaReply, trace) {
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
    let novaHtml = '<div class="chat-message-label">Nova</div><div class="chat-message-text">' + escapeHtml(novaReply) + '</div>';
    // Append timing breakdown if available
    if (trace) {
        const total = trace.total_latency_ms || 0;
        const iters = trace.iteration_count || 1;
        novaHtml += '<div class="chat-timing">';
        if (total > 1000) {
            novaHtml += (total / 1000).toFixed(1) + 's total';
        } else {
            novaHtml += total + 'ms total';
        }
        novaHtml += ' \u00b7 ' + iters + ' iteration(s)';
        if (trace.iterations && trace.iterations.length) {
            novaHtml += '<span class="chat-timing-breakdown" onclick="this.classList.toggle(\'expanded\')"> \u25BC breakdown</span>';
            novaHtml += '<div class="chat-timing-detail">';
            trace.iterations.forEach(function(it, idx) {
                const llmSec = (it.llm_time_ms / 1000).toFixed(1);
                const toolSec = it.tool_time_ms ? (it.tool_time_ms / 1000).toFixed(1) : '-';
                novaHtml += '<div class="timing-row">';
                novaHtml += '<span class="timing-step">#' + (idx + 1) + '</span>';
                novaHtml += '<span class="timing-llm">LLM ' + llmSec + 's</span>';
                if (it.tool_name) {
                    novaHtml += '<span class="timing-tool">' + escapeHtml(it.tool_name) + ' ' + toolSec + 's</span>';
                }
                novaHtml += '<span class="timing-tokens">' + it.prompt_tokens + '\u2192' + it.completion_tokens + ' tok</span>';
                novaHtml += '</div>';
            });
            novaHtml += '</div>';
        }
        novaHtml += '</div>';
    }
    novaDiv.innerHTML = novaHtml;
    area.appendChild(novaDiv);

    // Scroll to bottom
    area.scrollTop = area.scrollHeight;
}

function showChatLoading(visible) {
    const indicator = document.getElementById('chat-loading-indicator');

    if (visible) {
        if (indicator) {
            indicator.textContent = 'Nova is thinking...';
            indicator.classList.remove('hidden');
        }
    } else if (indicator) {
        indicator.classList.add('hidden');
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

// --- Voice Input (press-and-hold mic button) ---
// Records audio via MediaRecorder (HTTPS) or falls back to file upload (HTTP).
(function initVoiceInput() {
    const btnMic = document.getElementById('chat-btn-mic');
    const chatInput = document.getElementById('chat-input');
    const chatBtnSend = document.getElementById('chat-btn-send');
    if (!btnMic || !chatInput || !chatBtnSend) return;

    var canUseMediaRecorder = !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    var httpFallbackShown = false;

    if (!canUseMediaRecorder) {
        // --- HTTP fallback: file upload instead of live recording ---
        btnMic.disabled = false;
        btnMic.title = 'Select an audio file to transcribe';

        var fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'audio/*';
        fileInput.style.display = 'none';
        document.body.appendChild(fileInput);

        fileInput.addEventListener('change', function () {
            var file = fileInput.files[0];
            if (!file) return;

            btnMic.classList.add('recording');
            chatInput.disabled = true;
            chatBtnSend.disabled = true;
            clearChatError();

            var reader = new FileReader();
            reader.onload = async function (e) {
                var blob = new Blob([e.target.result], { type: file.type || 'audio/wav' });
                await transcribeAndSubmit(blob);
                btnMic.classList.remove('recording');
                if (!chatInFlight) {
                    chatInput.disabled = false;
                    chatBtnSend.disabled = false;
                }
            };
            reader.onerror = function () {
                showChatError('Failed to read audio file. Try again or type your message.');
                btnMic.classList.remove('recording');
                chatInput.disabled = false;
                chatBtnSend.disabled = false;
            };
            reader.readAsArrayBuffer(file);

            // Reset so same file can be re-selected
            fileInput.value = '';
        });

        btnMic.addEventListener('click', function () {
            if (chatInFlight) return;
            if (!httpFallbackShown) {
                showChatError('\uD83C\uDFA4 Voice input uses file upload over HTTP. Select an audio file to transcribe.');
                httpFallbackShown = true;
                setTimeout(clearChatError, 5000);
            }
            fileInput.click();
        });

        return;
    }

    // --- Original MediaRecorder path (HTTPS only) ---
    let mediaRecorder = null;
    let audioChunks = [];
    let recording = false;
    let stream = null;

    function resetRecordingUI() {
        btnMic.classList.remove('recording');
        recording = false;
        if (!chatInFlight) {
            chatInput.disabled = false;
            chatBtnSend.disabled = false;
        }
    }

    // --- Press-and-hold handlers ---
    async function startHold(e) {
        e.preventDefault();
        if (chatInFlight || recording) return;
        clearChatError();

        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            btnMic.classList.add('recording');
            chatInput.disabled = true;
            chatBtnSend.disabled = true;

            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.ondataavailable = function (e) {
                if (e.data.size > 0) audioChunks.push(e.data);
            };
            mediaRecorder.onstop = async function () {
                if (stream) {
                    stream.getTracks().forEach(function (t) { t.stop(); });
                    stream = null;
                }
                try {
                    const blob = new Blob(audioChunks);
                    const wavBlob = await audioBlobToWav(blob, 16000);
                    await transcribeAndSubmit(wavBlob);
                } catch (err) {
                    console.warn('Voice processing failed:', err);
                    showChatError('Voice processing failed. Try again or type your message.');
                }
                resetRecordingUI();
            };

            recording = true;
            mediaRecorder.start();
        } catch (err) {
            console.warn('Microphone access error:', err);
            if (err.name === 'NotAllowedError') {
                showChatError('Microphone access blocked. Grant microphone permission or use HTTPS (https://nova.local).');
            } else if (err.name === 'NotFoundError') {
                showChatError('No microphone found.');
            } else {
                showChatError('Could not access microphone: ' + (err.message || err));
            }
            resetRecordingUI();
        }
    }

    function endHold(e) {
        if (!recording || !mediaRecorder) return;
        if (e) e.preventDefault();
        if (mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
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

    // Enable the mic button (MediaRecorder is available)
    btnMic.disabled = false;
})();

// --- WAV conversion helper ---
// Decodes the recorded blob (WebM/Opus/etc) via AudioContext, resamples to the
// target sample rate (16 kHz), and exports as a standard WAV file.
async function audioBlobToWav(blob, targetSampleRate) {
    var arrayBuffer = await blob.arrayBuffer();
    var audioContext = new (window.AudioContext || window.webkitAudioContext)();
    var audioBuffer;
    try {
        audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    } catch (e) {
        audioContext.close();
        throw new Error('Audio decoding failed: ' + e.message);
    }

    // Resample via OfflineAudioContext
    var offlineCtx = new OfflineAudioContext(
        1,
        Math.ceil(audioBuffer.length * targetSampleRate / audioBuffer.sampleRate),
        targetSampleRate
    );
    var source = offlineCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineCtx.destination);
    source.start();
    var renderedBuffer = await offlineCtx.startRendering();

    // Float32 → 16-bit PCM
    var channelData = renderedBuffer.getChannelData(0);
    var pcm16 = new Int16Array(channelData.length);
    for (var i = 0; i < channelData.length; i++) {
        var s = Math.max(-1, Math.min(1, channelData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Build WAV header (44 bytes) + PCM data
    var dataLength = pcm16.length * 2;
    var headerBuf = new ArrayBuffer(44);
    var dv = new DataView(headerBuf);
    function wavStr(view, offset, str) {
        for (var j = 0; j < str.length; j++) view.setUint8(offset + j, str.charCodeAt(j));
    }
    wavStr(dv, 0, 'RIFF');
    dv.setUint32(4, 36 + dataLength, true);
    wavStr(dv, 8, 'WAVE');
    wavStr(dv, 12, 'fmt ');
    dv.setUint32(16, 16, true);
    dv.setUint16(20, 1, true);       // PCM
    dv.setUint16(22, 1, true);       // mono
    dv.setUint32(24, targetSampleRate, true);
    dv.setUint32(28, targetSampleRate * 2, true);
    dv.setUint16(32, 2, true);       // block align
    dv.setUint16(34, 16, true);      // bits per sample
    wavStr(dv, 36, 'data');
    dv.setUint32(40, dataLength, true);

    audioContext.close();
    return new Blob([headerBuf, pcm16.buffer], { type: 'audio/wav' });
}

// --- Upload WAV to backend and submit transcript ---
async function transcribeAndSubmit(wavBlob) {
    var formData = new FormData();
    formData.append('audio', wavBlob, 'recording.wav');

    try {
        var resp = await fetch('/dashboard/transcribe', { method: 'POST', body: formData });
        var data = await resp.json();
        if (resp.ok && data.transcript) {
            var input = document.getElementById('chat-input');
            if (input) {
                input.value = data.transcript;
                handleChatSubmit();
            }
        } else {
            showChatError(data.detail || 'Transcription failed. Please try again.');
        }
    } catch (err) {
        showChatError('Network error during transcription. Please try again.');
    }
}

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

// --- Hamburger Menu Navigation ---

function toggleNavMenu(forceState) {
    const menu = document.getElementById('nav-menu');
    const backdrop = document.getElementById('nav-backdrop');
    const btn = document.getElementById('btn-hamburger');
    if (!menu || !backdrop || !btn) return;

    const isOpen = forceState !== undefined ? forceState : !menu.classList.contains('visible');

    menu.classList.toggle('visible', isOpen);
    backdrop.classList.toggle('visible', isOpen);
    btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    btn.setAttribute('aria-label', isOpen ? 'Close navigation menu' : 'Open navigation menu');

    if (isOpen) {
        // Focus trap: focus first nav item
        const firstItem = menu.querySelector('.nav-item');
        if (firstItem) firstItem.focus();
        document.body.style.overflow = 'hidden';
    } else {
        btn.focus();
        document.body.style.overflow = '';
    }
}

function closeNavMenu() {
    toggleNavMenu(false);
}

function initNavMenu() {
    const menu = document.getElementById('nav-menu');
    const backdrop = document.getElementById('nav-backdrop');
    const btn = document.getElementById('btn-hamburger');
    if (!menu || !backdrop || !btn) return;

    // Remove hidden class so CSS transitions work (element is invisible via translateX/opacity)
    menu.classList.remove('hidden');
    backdrop.classList.remove('hidden');

    // Hamburger click
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleNavMenu();
    });

    // Backdrop click
    backdrop.addEventListener('click', closeNavMenu);

    // Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && menu.classList.contains('visible')) {
            closeNavMenu();
        }
    });

    // Menu item clicks: page links close menu, scroll items keep menu open
    menu.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            const navType = item.getAttribute('data-nav-type');

            if (navType === 'page' || navType === 'back') {
                // Page navigation items close the menu
                closeNavMenu();
            } else if (navType === 'scroll') {
                // Section scroll: keep menu open, smooth-scroll to target
                const targetId = item.getAttribute('data-scroll-to');
                if (targetId) {
                    const target = document.getElementById(targetId);
                    if (target) {
                        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }
                // Do NOT close the menu
            } else if (navType === 'modal') {
                // Open the modal referenced by data-modal-id
                const modalId = item.getAttribute('data-modal-id');
                if (modalId === 'settings-modal') {
                    closeNavMenu();
                    showSettingsModal();
                }
            }
            // External links (nav-type="external") open in new tab via <a target="_blank"> — default browser behavior, no JS needed
        });
    });

    // Focus trap: loop focus within menu when open
    menu.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;
        const focusable = menu.querySelectorAll('.nav-item');
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', initNavMenu);


