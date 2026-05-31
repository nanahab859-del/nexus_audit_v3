import { getData, getSettings, startRun, cancelRun } from './api.js';
import { setDataFromJob, setSettings, setStatus, subscribe, getState } from './state.js';
import { initStream } from './stream.js';
import { renderDashboard } from './dashboard.js';
import { showSettingsModal } from './settings.js';
import { initCommandPalette } from './command-palette.js';

// Initialize theme
const savedTheme = localStorage.getItem('nexus-audit-theme') ||
  (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
document.documentElement.setAttribute('data-theme', savedTheme);
document.getElementById('btn-theme').addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('nexus-audit-theme', next);
});

// Wire topbar buttons
document.getElementById('btn-run').addEventListener('click', async () => {
  try {
    const { job_id } = await startRun();
    setStatus({ state: 'running', job_id });
  } catch (e) {
    alert('Could not start audit: ' + e.message);
  }
});

document.getElementById('btn-cancel').addEventListener('click', async () => {
  await cancelRun();
});

document.getElementById('btn-settings').addEventListener('click', showSettingsModal);

// Load initial data and settings
async function init() {
  try {
    const data = await getData();
    if (data && data.scan_results) setDataFromJob(data);
  } catch (e) { /* no data yet */ }

  try {
    const s = await getSettings();
    setSettings(s);
  } catch (e) { /* ignore */ }

  // Start SSE stream
  initStream();

  // Render the active view
  subscribe('activeView', () => {
    const view = getState().activeView;
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    const active = document.getElementById(`view-${view}`);
    if (active) active.classList.remove('hidden');
  });

  subscribe('job', () => renderDashboard());
  subscribe('findings', () => renderDashboard());
  subscribe('healthScores', () => renderDashboard());

  // Initial render
  renderDashboard();

  // Command palette
  initCommandPalette();
}

document.addEventListener('DOMContentLoaded', init);
