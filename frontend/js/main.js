// js/main.js
import * as store from './store.js';
import * as api   from './api.js';
import * as router from './router.js';
import { initStream } from './stream.js';
import { initDashboard } from './views/dashboard.js';

async function init() {
  // 1. Wire router
  router.init();

  // 2. Wire theme toggle
  document.getElementById('btn-theme').addEventListener('click', toggleTheme);

  // 3. Wire run/cancel buttons
  document.getElementById('btn-run').addEventListener('click', handleRun);
  document.getElementById('btn-cancel').addEventListener('click', handleCancel);
  document.getElementById('btn-cancel-panel').addEventListener('click', handleCancel);

  // 4. Wire settings button
  document.getElementById('btn-settings').addEventListener('click', () => router.navigate('settings'));

  // 5. Wire status update from store to Topbar
  store.subscribe('status', updateTopbarFromStatus);

  // 6. Wire progress panel from store
  store.subscribe('scanProgress', updateProgressBars);
  store.subscribe('logLines', updateLogOutput);

  // 7. Init all views
  initDashboard();

  // 8. Start SSE stream
  initStream();

  // 9. Load initial data
  try {
    const [statusData, auditData, settingsData] = await Promise.all([
      api.getStatus(),
      api.getData().catch(() => null), // Silently handle if audit_data_complete.json is missing
      api.getSettings().catch(() => ({})),
    ]);
    
    if (statusData) store.set('status', statusData);
    if (auditData) store.setAuditData(auditData);
    if (settingsData) store.set('settings', settingsData);
    
  } catch (err) {
    console.error('Failed to load initial data:', err);
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('nexus-theme', next);
}

async function handleRun() {
  try {
    store.set('logLines', []);
    store.set('scanProgress', {});
    document.getElementById('progress-panel').classList.remove('hidden');
    await api.startRun();
  } catch (err) {
    alert('Failed to start: ' + (err.body?.error || err.message || 'unknown error'));
  }
}

async function handleCancel() {
  try { await api.cancelRun(); } catch (err) {
      console.error('Failed to cancel:', err);
  }
}

function updateTopbarFromStatus(status) {
  if (!status) return;
  const badge = document.getElementById('status-badge');
  badge.textContent = status.state;
  badge.className = `badge badge-${status.state}`;

  const isRunning = status.state === 'running';
  document.getElementById('btn-run').classList.toggle('hidden', isRunning);
  document.getElementById('btn-cancel').classList.toggle('hidden', !isRunning);

  if (status.state === 'completed' || status.state === 'failed' || status.state === 'cancelled') {
    setTimeout(async () => {
      document.getElementById('progress-panel').classList.add('hidden');
      // Reload audit data into store — this triggers all view re-renders automatically
      try {
        const data = await api.getData();
        store.setAuditData(data);
      } catch (err) {}
    }, 2000);
  }
}

function updateProgressBars(progress) {
  const container = document.getElementById('scanner-bars');
  if (!container) return;
  
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
  const el = document.getElementById('log-output');
  if (!el) return;
  
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
