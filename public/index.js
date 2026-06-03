// Session management
let sessionId = localStorage.getItem('sessionId');
if (!sessionId) {
    sessionId = generateUUID();
    localStorage.setItem('sessionId', sessionId);
}
document.getElementById('session-id').textContent = sessionId;

// Load history on page load
async function loadHistory() {
    try {
        const response = await fetch(`/api/chat/history?session_id=${sessionId}`);
        if (!response.ok) {
            console.log('No history for new session');
            return;
        }
        const data = await response.json();
        const history = document.getElementById('history');
        history.innerHTML = '';
        data.history.forEach(msg => {
            const div = document.createElement('div');
            div.className = `message ${msg.role}`;
            div.textContent = msg.content;
            history.appendChild(div);
        });
        history.scrollTop = history.scrollHeight;
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

async function sendQuery() {
    const input = document.getElementById('query-input');
    const message = input.value.trim();
    if (!message) return;

    // Disable submit while processing
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    input.disabled = true;

    try {
        // Add user message to UI
        const history = document.getElementById('history');
        const userDiv = document.createElement('div');
        userDiv.className = 'message user';
        userDiv.textContent = message;
        history.appendChild(userDiv);

        // Clear input
        input.value = '';

        // Show loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message assistant loading';
        loadingDiv.textContent = '🤔 Researching...';
        history.appendChild(loadingDiv);
        history.scrollTop = history.scrollHeight;

        // Send request
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, session_id: sessionId })
        });

        // Remove loading indicator
        history.removeChild(loadingDiv);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();
        sessionId = data.session_id;
        localStorage.setItem('sessionId', sessionId);
        document.getElementById('session-id').textContent = sessionId;

        // Add assistant response
        const assistantDiv = document.createElement('div');
        assistantDiv.className = 'message assistant';
        assistantDiv.textContent = data.response;
        history.appendChild(assistantDiv);
        history.scrollTop = history.scrollHeight;

        // Clear status
        document.getElementById('status').textContent = '';
    } catch (error) {
        document.getElementById('status').textContent = `❌ Error: ${error.message}`;
        console.error('Error:', error);
    } finally {
        submitBtn.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Event listeners
document.getElementById('submit-btn').addEventListener('click', sendQuery);
document.getElementById('query-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuery();
    }
});

// Load history when page loads
document.addEventListener('DOMContentLoaded', loadHistory);
