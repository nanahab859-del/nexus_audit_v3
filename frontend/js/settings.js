import { getSettings, saveSettings } from './api.js';
import { setSettings, getState } from './state.js';
import { renderDashboard } from './dashboard.js';

export async function showSettingsModal() {
  const modal = document.getElementById('modal-settings');
  const overlay = document.getElementById('modal-overlay');
  const settings = getState().settings || {};

  modal.innerHTML = `
    <h3>Settings</h3>
    <div class="settings-section">
      <label>Project Path</label>
      <input type="text" id="set-path" value="${settings.project_path || ''}">
    </div>
    <div class="settings-section">
      <label>API Key</label>
      <input type="password" id="set-api-key" value="${settings.api_key || ''}">
    </div>
    <div class="settings-section">
      <label>Scanners</label>
      <div class="scanner-toggles" id="scanner-toggles"></div>
    </div>
    <div style="text-align:right;">
      <button id="save-settings" class="primary-btn">Save</button>
    </div>
  `;

  // Populate scanner toggles
  const togglesDiv = document.getElementById('scanner-toggles');
  const knownScanners = ['bandit','vulture','radon','safety','lizard','semgrep','django_settings'];
  const activeScanners = settings.scanners || {};
  knownScanners.forEach(name => {
    const checked = activeScanners[name] !== false ? 'checked' : '';
    togglesDiv.innerHTML += `<label class="scanner-toggle">
      <input type="checkbox" value="${name}" ${checked}> ${name}
    </label>`;
  });

  modal.classList.add('active');
  overlay.classList.add('active');

  document.getElementById('save-settings').onclick = async () => {
    const newSettings = {
      project_path: document.getElementById('set-path').value,
      api_key: document.getElementById('set-api-key').value,
      scanners: {}
    };
    document.querySelectorAll('#scanner-toggles input').forEach(cb => {
      newSettings.scanners[cb.value] = cb.checked;
    });
    try {
      await saveSettings(newSettings);
      setSettings(newSettings);
      modal.classList.remove('active');
      overlay.classList.remove('active');
    } catch (e) {
      alert('Failed to save settings: ' + e.message);
    }
  };

  overlay.onclick = () => {
    modal.classList.remove('active');
    overlay.classList.remove('active');
  };
}
