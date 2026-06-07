// js/views/settings.js

import * as store from '../store.js';
import * as api from '../api.js';

const TABS = [
  { id: 'project',  label: 'Project'   },
  { id: 'scanners', label: 'Scanners'  },
  { id: 'ai',       label: 'AI'        },
  { id: 'rules',    label: 'Rules'     },
  { id: 'about',    label: 'About'     },
];

let _activeTab = 'project';
let _settings = {};

export function initSettings() {
  store.subscribe('settings', (s) => {
    _settings = s || {};
    _render();
  });
  _render();
}

function _render() {
  const el = document.getElementById('view-settings');
  if (!el) return;

  el.innerHTML = `
    <div class="settings-page">
      <div class="settings-tabs">
        ${TABS.map(t => `
          <button class="settings-tab ${t.id === _activeTab ? 'active' : ''}" data-tab="${t.id}">
            ${t.label}
          </button>
        `).join('')}
      </div>

      <div class="settings-content">
        ${_renderTabContent(_activeTab)}
      </div>

      <div id="settings-msg" class="settings-msg hidden"></div>
    </div>
  `;

  // Wire tab clicks
  el.querySelectorAll('.settings-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeTab = btn.dataset.tab;
      _render();
    });
  });

  // Wire save button if present
  const saveBtn = el.querySelector('#settings-save');
  if (saveBtn) saveBtn.addEventListener('click', _handleSave);
}

function _renderTabContent(tab) {
  switch(tab) {
    case 'project':  return _tabProject();
    case 'scanners': return _tabScanners();
    case 'ai':       return _tabAI();
    case 'rules':    return _tabRules();
    case 'about':    return _tabAbout();
    default:         return '';
  }
}

function _tabProject() {
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">Project</h3>
      <p class="settings-section__desc">The absolute path to the codebase you want to audit.</p>
      <div class="form-field">
        <label class="form-label" for="s-project-path">Project Path</label>
        <input type="text" id="s-project-path" class="form-input" value="${escHtml(_settings.project_path || '')}" />
      </div>
      <button id="settings-save" class="btn-primary">Save</button>
    </div>
  `;
}

function _tabScanners() {
  const scanners = _settings.scanners || {};
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">Scanners</h3>
      <p class="settings-section__desc">Enable or disable individual scanners. Disabled scanners are skipped entirely.</p>
      <div class="scanner-toggles">
        ${Object.entries(scanners).map(([name, enabled]) => `
          <div class="toggle-row">
            <div>
              <div class="toggle-row__name">${name}</div>
              <div class="toggle-row__desc">${_scannerDesc(name)}</div>
            </div>
            <input type="checkbox" id="scanner-${name}" class="toggle-checkbox" data-scanner="${name}" ${enabled ? 'checked' : ''} />
          </div>
        `).join('')}
      </div>
      <button id="settings-save" class="btn-primary">Save</button>
    </div>
  `;
}

function _tabAI() {
  const aiEnabled = _settings.ai_enabled || false;
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">AI Configuration</h3>
      <p class="settings-section__desc">AI-powered recommendations require an API key from Gemini or Anthropic.</p>
      <div class="form-field">
        <label class="toggle-row">
          <div>
            <div class="toggle-row__name">Enable AI</div>
            <div class="toggle-row__desc">Generate AI fix recommendations after each scan</div>
          </div>
          <input type="checkbox" id="s-ai-enabled" ${aiEnabled ? 'checked' : ''} />
        </label>
      </div>
      <div class="form-field ${!aiEnabled ? 'form-field--disabled' : ''}">
        <label class="form-label" for="s-ai-provider">Provider</label>
        <select id="s-ai-provider" class="form-input" ${!aiEnabled ? 'disabled' : ''}>
          <option value="claude" ${_settings.ai_provider === 'claude' ? 'selected' : ''}>Claude (Anthropic)</option>
          <option value="gemini" ${_settings.ai_provider === 'gemini' ? 'selected' : ''}>Gemini (Google)</option>
        </select>
      </div>
      <div class="form-field ${!aiEnabled ? 'form-field--disabled' : ''}">
        <label class="form-label" for="s-ai-model">Model</label>
        <input type="text" id="s-ai-model" class="form-input" value="${escHtml(_settings.ai_model || '')}" placeholder="claude-opus-4-7" ${!aiEnabled ? 'disabled' : ''} />
      </div>
      <div class="form-field ${!aiEnabled ? 'form-field--disabled' : ''}">
        <label class="form-label" for="s-api-key">API Key</label>
        <input type="password" id="s-api-key" class="form-input" placeholder="Paste your API key here" ${!aiEnabled ? 'disabled' : ''} />
        <small class="form-hint">Leave blank to keep existing key.</small>
      </div>
      <button id="settings-save" class="btn-primary">Save</button>
    </div>
  `;
}

function _tabRules() {
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">Audit Rules</h3>
      <p class="settings-section__desc">
        Place an <code>audit_rules.yaml</code> file in your project root to define
        custom boundary rules, scoring weights, and violation patterns.
        If absent, the default rules apply.
      </p>
      <div class="info-block">
        <div>Default rules file: <code>nexus_audit_v3/default_rules.yaml</code></div>
        <div>Project override: <code>{project_path}/audit_rules.yaml</code></div>
      </div>
    </div>
  `;
}

function _tabAbout() {
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">About</h3>
      <div class="about-grid">
        <div class="about-row">
          <span>Version</span>
          <span>3.0.0</span>
        </div>
        <div class="about-row">
          <span>Server</span>
          <span>127.0.0.1:8421</span>
        </div>
        <div class="about-row">
          <span>Project</span>
          <span>${escHtml(_settings.project_path || '—')}</span>
        </div>
      </div>
    </div>
  `;
}

async function _handleSave() {
  const el = document.getElementById('view-settings');
  const payload = { ..._settings };

  // Read whichever fields are visible in the active tab
  const pp = el.querySelector('#s-project-path');
  if (pp) payload.project_path = pp.value.trim();

  // Scanners
  el.querySelectorAll('.toggle-checkbox[id^="scanner-"]').forEach(cb => {
    const name = cb.id.replace('scanner-', '');
    if (!payload.scanners) payload.scanners = {};
    payload.scanners[name] = cb.checked;
  });

  // AI
  const aiEnabled = el.querySelector('#s-ai-enabled');
  if (aiEnabled) payload.ai_enabled = aiEnabled.checked;
  const provider = el.querySelector('#s-ai-provider');
  if (provider) payload.ai_provider = provider.value;
  const model = el.querySelector('#s-ai-model');
  if (model && model.value) payload.ai_model = model.value;
  const key = el.querySelector('#s-api-key');
  if (key && key.value) payload.api_key = key.value;

  try {
    const result = await api.updateSettings(payload);
    store.set('settings', result);
    _showMsg('success', 'Settings saved');
  } catch(e) {
    _showMsg('error', 'Failed: ' + e.message);
  }
}

function _showMsg(type, text) {
  const el = document.getElementById('settings-msg');
  if (!el) return;
  el.textContent = text;
  el.className = `settings-msg settings-msg--${type}`;
  setTimeout(() => { el.className = 'settings-msg hidden'; }, 3000);
}

function _scannerDesc(name) {
  const descs = {
    vulture: 'Dead code detection',
    bandit:  'Python security issues',
    radon:   'Cyclomatic complexity',
    lizard:  'Code structure metrics',
    semgrep: 'Custom pattern rules',
    safety:  'Dependency CVE scan',
  };
  return descs[name] || '';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
