import { getData, getSettings, startRun, cancelRun, openStream, saveSettings } from './api.js';
import { setDataFromJob, setSettings, setStatus, subscribe, getState, setProgress, appendLog, appendFinding } from './state.js';
import { initDashboard } from './dashboard.js';

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

// Load initial data and settings
async function init() {
  try {
    const data = await getData();
    // Data now comes in format: { findings, job, apps, violations, ... }
    // Call setDataFromJob with the entire response
    if (data) {
      setDataFromJob(data);
    }
  } catch (e) { 
    console.warn('Could not load audit data:', e.message);
    // Data will be empty state template, which is fine
  }

  try {
    const s = await getSettings();
    setSettings(s);
    window.__auditSettings = s;
  } catch (e) { 
    console.warn('Could not load settings:', e.message);
  }

  // Start dashboard and SSE stream
  initDashboard();

  openStream({
    onStatus: async (s) => {
      setStatus(s);
      if (s && s.state === 'completed') {
        try {
          const data = await getData();
          if (data) setDataFromJob(data);
        } catch (err) {
          console.warn('Could not reload data after completion', err.message);
        }
      }
      if (s && s.state === 'running') {
        // clear logs/progress handled elsewhere if needed
      }
    },
    onProgress: (p) => setProgress(p.scanner, p.percent ?? 0, p.file || ''),
    onLog: (l) => appendLog(l.level || 'info', l.message || ''),
    onFinding: (ev) => {
      const f = ev.finding || ev;
      appendFinding(f);
    }
  });

  // Settings button handler (simple prompt for project path)
  const btnSettings = document.getElementById('btn-settings');
  if (btnSettings) {
    btnSettings.addEventListener('click', async () => {
      const currentPath = (window.__auditSettings && window.__auditSettings.project_path) || '';
      const newPath = prompt('Project path:', currentPath);
      if (newPath && newPath !== currentPath) {
        try {
          await saveSettings({ project_path: newPath });
          window.__auditSettings = { ...(window.__auditSettings || {}), project_path: newPath };
          setSettings(window.__auditSettings);
          alert('Settings saved');
        } catch (err) {
          alert('Failed to save settings: ' + err.message);
        }
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', init);
