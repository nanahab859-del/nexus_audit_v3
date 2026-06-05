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
    <div class="settings-section">
      <label>Audit Rules (YAML)</label>
      <textarea id="set-rules-yaml" rows="10" style="width: 100%; font-family: monospace;"></textarea>
      <div style="margin-top: 5px;">
        <button id="validate-rules" class="secondary-btn">Validate Rules</button>
        <span id="rules-validation-msg" style="margin-left: 10px; font-size: 0.9em;"></span>
      </div>
    </div>
    <div style="text-align:right; margin-top: 20px;">
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
      
      // We don't have an endpoint to save the rules directly to disk from the UI yet, 
      // but in a real app we'd POST the YAML content to the server to write `audit_rules.yaml`.
      
      modal.classList.remove('active');
      overlay.classList.remove('active');
    } catch (e) {
      alert('Failed to save settings: ' + e.message);
    }
  };
  
  // Validation logic
  document.getElementById('validate-rules').onclick = async () => {
    const yamlContent = document.getElementById('set-rules-yaml').value;
    const msgEl = document.getElementById('rules-validation-msg');
    msgEl.textContent = 'Validating...';
    try {
      const { getRules, validateRules } = await import('./api.js');
      const res = await validateRules({ content: yamlContent });
      if (res.errors && res.errors.length > 0) {
        msgEl.textContent = '❌ Errors: ' + res.errors.join(', ');
        msgEl.style.color = 'var(--status-critical)';
      } else {
        msgEl.textContent = '✅ Valid YAML and rule format!';
        msgEl.style.color = 'var(--status-healthy)';
      }
    } catch (e) {
      msgEl.textContent = '❌ Request failed';
      msgEl.style.color = 'var(--status-critical)';
    }
  };
  
  // Fetch rules
  import('./api.js').then(api => {
    api.getRules().then(data => {
      document.getElementById('set-rules-yaml').value = data.content || '';
    }).catch(e => console.error('Failed to load rules', e));
  });

  overlay.onclick = () => {
    modal.classList.remove('active');
    overlay.classList.remove('active');
  };
}
