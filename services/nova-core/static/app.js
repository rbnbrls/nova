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
