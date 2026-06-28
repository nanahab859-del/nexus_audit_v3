// frontend/js/main.js
import { connectStream } from './stream.js';
import { renderFindingsTable } from './dashboard.js';

async function loadInitialData() {
    try {
        const resp = await fetch('/api/data');
        if (resp.ok) {
            const data = await resp.json();
            document.getElementById('data-output').innerHTML = renderFindingsTable(data);
        }
    } catch (e) { 
        console.error('Error loading initial data:', e);
    }
}

async function runAudit() {
    try {
        const resp = await fetch('/api/run', { method: 'POST' });
        const result = await resp.json();
        const job_id = result.job_id || result.id;
        
        document.getElementById('progress-panel').style.display = 'block';
        document.getElementById('log-output').textContent = '';
        document.getElementById('scanner-progress').textContent = 'Starting...';

        connectStream(
            (scanner, percent, file) => {
                document.getElementById('scanner-progress').textContent =
                    `${scanner}: ${percent}% (${file})`;
            },
            (level, message) => {
                const logEl = document.getElementById('log-output');
                logEl.textContent += message + '\n';
                logEl.scrollTop = logEl.scrollHeight;
            },
            async (state) => {
                if (state === 'completed') {
                    // Fetch final data
                    const dataResp = await fetch('/api/data');
                    const data = await dataResp.json();
                    document.getElementById('data-output').innerHTML =
                        renderFindingsTable(data);
                    document.getElementById('progress-panel').style.display = 'none';
                }
            }
        );
    } catch (err) {
        alert('Error starting audit: ' + err.message);
    }
}

// Wire up button
document.getElementById('run-btn').addEventListener('click', runAudit);

// Load initial data on page load
window.addEventListener('DOMContentLoaded', loadInitialData);
