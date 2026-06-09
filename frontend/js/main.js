// js/main.js
import * as store from './store.js';
import * as api   from './api.js';
import * as router from './router.js';
import { initStream } from './stream.js';
import { initDashboard } from './views/dashboard.js';
import { initIssues } from './views/issues.js';
import { initPlaceholderViews } from './views/placeholder.js';
import { initSettings } from './views/settings.js';
import { initConsole, showConsole, hideConsole, toggleConsole, focusConsole, _applyConsolePrefs } from './views/console.js';

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
  document.getElementById('btn-copy-log')?.addEventListener('click', () => {
    const lines = store.get('logLines') || [];
    const text = lines.map(l => `${new Date(l.time).toTimeString().slice(0,8)} ${l.message}`).join('\n');
    navigator.clipboard.writeText(text).catch(() => {});
  });

  // Global hotkey for Audit Console (Ctrl+Shift+A)
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toUpperCase() === 'A') {
      e.preventDefault();
      const el = document.getElementById('audit-console');
      const pane = document.getElementById('con-pane');
      if (!el || el.style.display === 'none') {
        showConsole();
        focusConsole();
      } else if (el.classList.contains('is-minimized')) {
        // Un-minimize and focus
        el.classList.remove('is-minimized');
        document.getElementById('con-min').textContent = '▂';
        focusConsole();
      } else if (document.activeElement !== pane) {
        focusConsole();
      } else {
        hideConsole();
      }
    }
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
  console.log('[INIT] Initializing dashboard, issues, placeholder views, settings, and audit console...');
  initDashboard();
  initIssues();
  initPlaceholderViews();
  initSettings();

  // Initialize the new Audit Console V3 overlay
  initConsole();
  _applyConsolePrefs();

  // Mirror logLines → logs so console.js has a clean key to subscribe
  store.subscribe('logLines', lines => store.set('logs', lines));

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
    store.set('logs', []);
    store.set('scanProgress', {});

    // Open the new Audit Console V3
    showConsole();

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

// copyLogs function removed because it's wired locally in init()

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
        
        // Reset filters when completed
        if (status.state === 'completed') {
          store.set('filters', { severity: null, scanner: null, category: null, search: '' });
        }
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
    
    // After the run completes, populate the status bar
    if (status.state === 'completed' || status.state === 'failed') {
      const bar = document.getElementById('console-status-bar');
      const names = document.getElementById('status-bar-scanners');
      if (bar && names) {
        const progress = store.get('scanProgress') || {};
        names.innerHTML = Object.keys(progress).map(name =>
          `<span class="status-badge">${name} <span style="color:#8b949e">(DONE)</span></span>`
        ).join(' | ');
        bar.classList.remove('hidden');
      }
    }
  }
}

function updateProgressBars(progress) {
  const container = document.getElementById('scanner-bars');
  if (!container) return;
  const entries = Object.entries(progress);
  if (!entries.length) { container.innerHTML = ''; return; }
  container.innerHTML = entries.map(([name, p]) => `
    <div class="scanner-row">
      <span class="scanner-row__name">${name}</span>
      <div class="scanner-row__track">
        <div class="scanner-row__fill" style="width:${p.percent ?? 0}%"></div>
      </div>
      <span class="scanner-row__pct">${p.percent ?? 0}%</span>
    </div>
  `).join('');
}

function updateLogOutput(lines) {
  const el = document.getElementById('log-output');
  if (!el) return;

  const SCANNER_NAMES = new Set(['vulture','bandit','radon','lizard','semgrep','safety','django_settings']);

  el.innerHTML = lines.map(l => {
    const t   = new Date(l.time).toTimeString().slice(0,8);
    const msg = l.message || '';

    // Extract [TAG] if present
    const tagMatch = msg.match(/^\[([A-Z_a-z0-9 ]+)\]\s*/);
    let tag = '', body = msg;
    if (tagMatch) {
      tag  = tagMatch[1];
      body = msg.slice(tagMatch[0].length);
    }

    // Determine CSS modifier
    const lv  = (l.level || 'info').toLowerCase();
    const isScanner = SCANNER_NAMES.has(tag.toLowerCase());
    const isSuccess = body.includes('✓') || body.toLowerCase().includes('success');
    const mod = isScanner ? 'scanner'
              : isSuccess ? 'success'
              : tag === 'DEBUG' ? 'debug'
              : lv === 'error' ? 'error'
              : lv === 'warning' ? 'warning'
              : tag ? tag.toLowerCase().replace(/\s+/g,'-')
              : 'info';

    const tagHtml = tag
      ? `<span class="log-line__tag">[${esc(tag)}]</span>`
      : '';

    return `<div class="log-line log-line--${mod}">
      <span class="log-line__ts">${t}</span>
      ${tagHtml}
      <span class="log-line__msg">${esc(body)}</span>
    </div>`;
  }).join('');

  el.scrollTop = el.scrollHeight;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Restore saved theme
const savedTheme = localStorage.getItem('nexus-theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

document.addEventListener('DOMContentLoaded', init);
