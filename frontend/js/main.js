// js/main.js
import * as store from './store.js';
import * as api   from './api.js';
import * as router from './router.js';
import { initStream } from './stream.js';
import { initDashboard } from './views/dashboard.js';
import { initPlaceholderViews } from './views/placeholder.js';

async function init() {
  console.log('[INIT] Starting application initialization...');
  
  // 1. Wire router
  console.log('[INIT] Wiring router...');
  router.init();

  // 2. Wire theme toggle
  console.log('[INIT] Wiring theme toggle...');
  document.getElementById('btn-theme').addEventListener('click', () => {
    console.log('[BUTTON] Theme toggle clicked');
    toggleTheme();
  });

  // 3. Wire run/cancel buttons
  console.log('[INIT] Wiring run/cancel buttons...');
  document.getElementById('btn-run').addEventListener('click', () => {
    console.log('[BUTTON] Run button clicked');
    handleRun();
  });
  document.getElementById('btn-cancel').addEventListener('click', () => {
    console.log('[BUTTON] Cancel button clicked');
    handleCancel();
  });
  document.getElementById('btn-cancel-panel').addEventListener('click', () => {
    console.log('[BUTTON] Cancel panel button clicked');
    handleCancel();
  });
  document.getElementById('btn-copy-logs').addEventListener('click', () => {
    console.log('[BUTTON] Copy logs button clicked');
    copyLogs();
  });

  // 4. Wire settings button
  console.log('[INIT] Wiring settings button...');
  document.getElementById('btn-settings').addEventListener('click', () => {
    console.log('[BUTTON] Settings button clicked');
    router.navigate('settings');
  });

  // 5. Wire status update from store to Topbar
  console.log('[INIT] Subscribing to status updates...');
  store.subscribe('status', updateTopbarFromStatus);

  // 6. Wire progress panel from store
  console.log('[INIT] Subscribing to progress updates...');
  store.subscribe('scanProgress', updateProgressBars);
  store.subscribe('logLines', updateLogOutput);

  // 7. Init all views
  console.log('[INIT] Initializing dashboard and placeholder views...');
  initDashboard();
  initPlaceholderViews();

  // 8. Start SSE stream
  console.log('[INIT] Starting SSE stream...');
  initStream();

  // 9. Load initial data
  console.log('[INIT] Loading initial data from API...');
  try {
    const [statusData, auditData, settingsData] = await Promise.all([
      api.getStatus().then(d => { console.log('[API] Status loaded:', d); return d; }),
      api.getData().catch(err => { console.warn('[API] getData() failed (expected if no audit yet):', err); return null; }).then(d => { if (d) console.log('[API] Audit data loaded:', d.metadata); return d; }),
      api.getSettings().catch(err => { console.warn('[API] getSettings() failed:', err); return {}; }).then(d => { console.log('[API] Settings loaded'); return d; }),
    ]);
    
    if (statusData) {
      console.log('[INIT] Setting status from API');
      store.set('status', statusData);
    }
    if (auditData) {
      console.log('[INIT] Setting audit data from API');
      store.setAuditData(auditData);
    }
    if (settingsData) {
      console.log('[INIT] Setting settings from API');
      store.set('settings', settingsData);
    }
    
    console.log('[INIT] ✓ Initialization complete!');
  } catch (err) {
    console.error('[INIT] ✗ Failed to load initial data:', err);
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('nexus-theme', next);
}

async function handleRun() {
  console.log('[handleRun] Run button handler started');
  try {
    console.log('[handleRun] Clearing logs and progress...');
    store.set('logLines', []);
    store.set('scanProgress', {});
    
    console.log('[handleRun] Showing progress panel...');
    document.getElementById('progress-panel').classList.remove('hidden');
    
    console.log('[handleRun] Calling api.startRun()...');
    await api.startRun();
    console.log('[handleRun] ✓ api.startRun() succeeded');
  } catch (err) {
    console.error('[handleRun] ✗ Error:', err);
    alert('Failed to start: ' + (err.body?.error || err.message || 'unknown error'));
  }
}

async function handleCancel() {
  console.log('[handleCancel] Cancel button handler started');
  const status = store.get('status');
  console.log('[handleCancel] Current status:', status);
  
  // If running: cancel the audit
  if (status && status.state === 'running') {
    console.log('[handleCancel] Audit is running, sending cancel request...');
    try { 
      await api.cancelRun();
      console.log('[handleCancel] ✓ Cancel request sent');
    } catch (err) {
      console.error('[handleCancel] ✗ Failed to cancel:', err);
    }
  } 
  // If completed/failed/cancelled: close the progress panel
  else {
    console.log('[handleCancel] Audit not running, closing progress panel...');
    document.getElementById('progress-panel').classList.add('hidden');
  }
}

function copyLogs() {
  console.log('[copyLogs] Attempting to copy logs...');
  const logOutput = document.getElementById('log-output');
  if (!logOutput) {
    console.warn('[copyLogs] Log output element not found!');
    return;
  }
  
  // Get all log lines as text
  const logText = Array.from(logOutput.querySelectorAll('.log-line'))
    .map(el => el.textContent)
    .join('\n');
  
  if (!logText) {
    console.warn('[copyLogs] No logs to copy');
    alert('No logs to copy');
    return;
  }
  
  console.log('[copyLogs] Copying', logText.split('\n').length, 'lines to clipboard...');
  
  // Copy to clipboard
  navigator.clipboard.writeText(logText).then(() => {
    console.log('[copyLogs] ✓ Successfully copied to clipboard');
    const btn = document.getElementById('btn-copy-logs');
    const originalText = btn.textContent;
    btn.textContent = '✓ Copied!';
    setTimeout(() => {
      btn.textContent = originalText;
    }, 2000);
  }).catch(err => {
    console.error('[copyLogs] ✗ Failed to copy:', err);
    alert('Failed to copy: ' + err.message);
  });
}

function updateTopbarFromStatus(status) {
  console.log('[updateTopbarFromStatus] Status changed:', status);
  if (!status) return;
  const badge = document.getElementById('status-badge');
  badge.textContent = status.state;
  badge.className = `badge badge-${status.state}`;
  console.log('[updateTopbarFromStatus] Updated badge to:', status.state);

  const isRunning = status.state === 'running';
  document.getElementById('btn-run').classList.toggle('hidden', isRunning);
  document.getElementById('btn-cancel').classList.toggle('hidden', !isRunning);

  // Update progress panel button
  const panelCancelBtn = document.getElementById('btn-cancel-panel');
  if (panelCancelBtn) {
    if (isRunning) {
      panelCancelBtn.textContent = '⏹ Cancel';
      panelCancelBtn.classList.remove('hidden');
    } else if (status.state === 'completed' || status.state === 'failed' || status.state === 'cancelled') {
      panelCancelBtn.textContent = '✕ Close';
    }
  }

  if (status.state === 'completed' || status.state === 'failed' || status.state === 'cancelled') {
    console.log('[updateTopbarFromStatus] Audit finished, reloading data in 2 seconds...');
    // Reload audit data into store — this triggers all view re-renders automatically
    // BUT KEEP PROGRESS PANEL OPEN so user can read/copy logs
    setTimeout(async () => {
      try {
        console.log('[updateTopbarFromStatus] Reloading audit data...');
        const data = await api.getData();
        console.log('[updateTopbarFromStatus] ✓ Audit data reloaded');
        store.setAuditData(data);
      } catch (err) {
        console.error('[updateTopbarFromStatus] ✗ Failed to reload data:', err);
      }
    }, 2000);
    
    // Update panel title to show it's done
    const titleEl = document.getElementById('progress-title');
    if (titleEl) {
      const statusText = status.state === 'completed' ? 'Audit Complete' : 
                        status.state === 'failed' ? 'Audit Failed' : 'Audit Cancelled';
      titleEl.textContent = statusText;
      console.log('[updateTopbarFromStatus] Updated panel title:', statusText);
    }
  }
}

function updateProgressBars(progress) {
  console.log('[updateProgressBars] Progress update:', Object.keys(progress).length, 'scanners');
  const container = document.getElementById('scanner-bars');
  if (!container) {
    console.warn('[updateProgressBars] Container not found!');
    return;
  }
  
  container.innerHTML = Object.entries(progress).map(([scanner, p]) => `
    <div class="scanner-bar">
      <span class="scanner-name">${scanner}</span>
      <div class="progress-track">
        <div class="progress-fill" style="width:${p.percent}%"></div>
      </div>
      <span class="progress-pct">${p.percent}%</span>
      <span class="progress-file">${p.file || ''}</span>
    </div>
  `).join('');
}

function updateLogOutput(lines) {
  console.log('[updateLogOutput] Log update:', lines.length, 'total lines (showing last 50)');
  const el = document.getElementById('log-output');
  if (!el) {
    console.warn('[updateLogOutput] Container not found!');
    return;
  }
  
  el.innerHTML = lines.slice(-50).map(l =>
    `<div class="log-line log-${l.level}">${escapeHtml(l.message)}</div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Restore saved theme
const savedTheme = localStorage.getItem('nexus-theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

document.addEventListener('DOMContentLoaded', init);
