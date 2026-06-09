// frontend/js/views/settings.js
import * as store from '../store.js';
import * as api   from '../api.js';

const TABS = [
  { id: 'project',  label: 'Project'  },
  { id: 'scanners', label: 'Scanners' },
  { id: 'ai',       label: 'AI'       },
  { id: 'rules',    label: 'Rules'    },
  { id: 'about',    label: 'About'    },
];

// ── Dynamic capabilities (populated from /api/capabilities on init) ────────────
let _caps = {
  stacks:  ['Python','Go','JavaScript','TypeScript','Rust','Java','C++'],
  output_formats: ['JSON','HTML','PDF','Markdown'],
  version: '…',
};

let _activeTab     = 'project';
let _expandedScan  = null;   // which scanner's advanced panel is open
let _settings      = {};

export function initSettings() {
  // Fetch dynamic capabilities once and cache them
  api.getCapabilities().then(caps => {
    if (caps) {
      _caps = caps;
      _render();
    }
  }).catch(() => {});

  store.subscribe('settings', s => { _settings = s || {}; _render(); });
}

// ── Main render ───────────────────────────────────────────
function _render() {
  const el = document.getElementById('view-settings');
  if (!el) return;

  el.innerHTML = `
    <div class="cfg-page">
      <div class="cfg-tabs">
        ${TABS.map(t => `
          <button class="cfg-tab${t.id === _activeTab ? ' active' : ''}"
                  data-tab="${t.id}">${t.label}</button>
        `).join('')}
      </div>
      <div class="cfg-body">
        ${_renderTab(_activeTab)}
      </div>
      <div class="cfg-footer hidden" id="cfg-footer">
        <button class="btn-ghost" id="cfg-discard">Discard Changes</button>
        <button class="btn-primary" id="cfg-save">💾 Save Configuration</button>
      </div>
      <div class="cfg-msg hidden" id="cfg-msg"></div>
    </div>
  `;

  el.querySelectorAll('.cfg-tab').forEach(b =>
    b.addEventListener('click', () => { _activeTab = b.dataset.tab; _render(); })
  );
  el.querySelector('#cfg-save')?.addEventListener('click',    _save);
  el.querySelector('#cfg-discard')?.addEventListener('click', _render);

  // Show footer only on tabs that have saveable content (not 'project' or 'scanners' — they have their own)
  if (['ai'].includes(_activeTab)) {
    el.querySelector('#cfg-footer')?.classList.remove('hidden');
  }

  // Mount the self-contained project view after the HTML is in the DOM
  if (_activeTab === 'project') {
    import('./project.js').then(m => m.mountProject(
      document.getElementById('project-view-mount'),
      _settings,
      async (updated) => {
        _settings = updated;
        await api.updateSettings(updated);
        const fresh = await api.getSettings();
        store.set('settings', fresh);
        _showMsg('success', '✓ Saved');
      }
    ));
  }

  // Mount the self-contained scanners view
  if (_activeTab === 'scanners') {
    const mount = el.querySelector('#scanners-view-mount');
    if (mount) {
      import('./scanners.js').then(m => {
        m.mountScanners(mount, _settings, async (updated) => {
          await api.updateSettings(updated);
          const fresh = await api.getSettings();
          store.set('settings', fresh);
          _settings = { ...fresh };
        });
      });
    }
  }

  // Wire scanner expand/collapse toggles
  el.querySelectorAll('.scanner-expand-btn').forEach(b => {
    b.addEventListener('click', () => {
      const name = b.dataset.scanner;
      _expandedScan = _expandedScan === name ? null : name;
      _render();
    });
  });

  // Wire scanner toggles
  el.querySelectorAll('.scanner-toggle-input').forEach(cb => {
    cb.addEventListener('change', () => {
      const name = cb.dataset.scanner;
      if (!_settings.scanners) _settings.scanners = {};
      _settings.scanners[name] = cb.checked;
    });
  });

  // Wire Install buttons
  el.querySelectorAll('.btn-install').forEach(btn => {
    btn.addEventListener('click', () => _installScanner(btn.dataset.install, btn));
  });

  // Wire Add Custom Plugin button
  el.querySelector('#btn-add-custom-scanner')?.addEventListener('click', _showCustomScannerModal);

  // Wire Refresh Scanners button
  el.querySelector('#sv-refresh')?.addEventListener('click', async () => {
    // capture status element BEFORE any render
    const statusEl = _el?.querySelector('#sv-refresh-status');
    if (statusEl) { statusEl.textContent = '⏳'; }
    try {
      await api.reloadRegistry();
      const scanners = await api.getScanners();
      store.set('scanners', scanners);
      // re-render happens via store subscription — don't call _render() here
    } catch(e) {
      // statusEl is a reference we captured, not a live DOM query
      if (statusEl?.isConnected) statusEl.textContent = '✗';
    }
  });

  // Wire scanner YAML preview buttons (one per expanded scanner card)
  el.querySelectorAll('.yaml-preview-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.scanner;
      const cfg  = (_settings.scanner_configs || {})[name] || {};
      const enabled = (_settings.scanners || {})[name] || false;
      _showYamlModal(name, enabled, cfg);
    });
  });

  // Wire Rules tab: Validate + View YAML
  el.querySelector('#btn-validate-yaml')?.addEventListener('click', async () => {
    const yamlText = el.querySelector('#s-custom-rules')?.value || '';
    try {
      const result = await api.validateConfig({ custom_rules_yaml: yamlText });
      if (result.valid) {
        _showMsg('success', '\u2713 YAML is valid');
      } else {
        _showMsg('error', '\u2717 ' + (result.errors || []).join('; '));
      }
    } catch(e) { _showMsg('error', 'Validate failed: ' + e.message); }
  });
  el.querySelector('#btn-view-yaml')?.addEventListener('click', async () => {
    try {
      const yaml = await api.getConfigYaml();
      // Use modal instead of window.open (Issue 4)
      const overlay = document.getElementById('modal-overlay') || _createModalOverlay();
      const container = document.getElementById('modal-container');
      const escapedYaml = esc(yaml);
      container.innerHTML = `
        <h3 style="margin:0 0 12px">📄 Full Configuration YAML</h3>
        <pre id="yaml-snippet" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;overflow-x:auto;font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:#d0d7de;line-height:1.5;max-height:60vh;overflow-y:auto">${escapedYaml}</pre>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
          <button class="btn-secondary" onclick="navigator.clipboard.writeText(document.getElementById('yaml-snippet').textContent).then(()=>this.textContent='\u2713 Copied!').catch(()=>this.textContent='\u2717 Failed')">📋 Copy</button>
          <button class="btn-primary" onclick="document.getElementById('modal-overlay').classList.add('hidden');document.getElementById('modal-container').classList.add('hidden')">Close</button>
        </div>
      `;
      overlay.classList.remove('hidden');
      container.classList.remove('hidden');
    } catch(e) { _showMsg('error', 'Could not load YAML: ' + e.message); }
  });
}

// ── Tab routing ──────────────────────────────────────────
function _renderTab(tab) {
  switch(tab) {
    case 'project':  return _renderProjectFrame();
    case 'scanners': return _tabScanners();
    case 'ai':       return _tabAI();
    case 'rules':    return _tabRules();
    case 'about':    return _tabAbout();
    default:         return '';
  }
}

function _renderProjectFrame() {
  return '<div id="project-view-mount"></div>';
}

function _tabScanners() {
  return '<div id="scanners-view-mount"></div>';
}


function _tabAI() {
  const s = _settings;
  const ai = s.ai_enabled || false;
  const html = `
    <div class="cfg-section-header">
      <h2>AI Configuration</h2>
      <p>AI-powered recommendations require an API key. The AI referee analyses findings and suggests exact code fixes.</p>
    </div>
    <div class="cfg-card" style="max-width:560px; margin:0 auto">
      <div class="cfg-card__head">
        <span class="cfg-card__icon">🤖</span>
        <span class="cfg-card__title">AI Fix Engine</span>
      </div>
      <div class="cfg-card__body">
        <!-- Enable toggle row using scanner-style switch -->
        <div class="ai-toggle-row">
          <div>
            <div style="font-size:var(--text-sm); font-weight:600">Enable AI</div>
            <div style="font-size:var(--text-xs); color:var(--text-muted)">Generate AI fix recommendations after each scan</div>
          </div>
          <label class="scanner-toggle" style="flex-shrink:0">
            <input type="checkbox" class="scanner-toggle-input" id="s-ai-enabled" ${ai ? 'checked' : ''}>
            <span class="scanner-toggle__track"></span>
          </label>
        </div>
        <!-- Fields section — dims when AI disabled -->
        <div id="ai-fields-section" class="${!ai ? 'ai-fields--disabled' : ''}">
          <div class="form-field">
            <label class="form-label">Provider</label>
            <select class="form-input" id="s-ai-provider" ${!ai ? 'disabled' : ''}>
              <option value="claude"  ${s.ai_provider==='claude'  ? 'selected':''}>Claude (Anthropic)</option>
              <option value="gemini" ${s.ai_provider==='gemini'  ? 'selected':''}>Gemini (Google)</option>
              <option value="openai" ${s.ai_provider==='openai'  ? 'selected':''}>GPT-4 (OpenAI)</option>
            </select>
          </div>
          <div class="form-field">
            <label class="form-label">Model</label>
            <input class="form-input" id="s-ai-model" type="text"
                   value="${esc(s.ai_model||'')}" ${!ai ? 'disabled' : ''}
                   placeholder="claude-3-5-sonnet, gemini-2.0-flash, gpt-4o…">
          </div>
          <div class="form-field">
            <label class="form-label">API Key</label>
            <div class="input-with-btn">
              <input class="form-input" id="s-api-key" type="password"
                     placeholder="${s.api_key ? '••••••••' : 'Enter API key'}" ${!ai ? 'disabled' : ''}>
              <button class="btn-secondary-sm" id="btn-toggle-apikey" type="button" title="Show/hide key">👁</button>
            </div>
            <span class="form-hint">Leave blank to keep existing key.</span>
          </div>
        </div>
      </div>
    </div>
  `;

  // Wire live AI toggle
  setTimeout(() => {
    const el = document.getElementById('view-settings');
    el?.querySelector('#s-ai-enabled')?.addEventListener('change', function() {
      const on = this.checked;
      const section = el.querySelector('#ai-fields-section');
      section?.classList.toggle('ai-fields--disabled', !on);
      ['s-ai-provider', 's-ai-model', 's-api-key'].forEach(id => {
        const f = el.querySelector('#' + id);
        if (f) f.disabled = !on;
      });
    });
    // Eye toggle for API key
    el?.querySelector('#btn-toggle-apikey')?.addEventListener('click', () => {
      const inp = el.querySelector('#s-api-key');
      if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
    });
  }, 0);

  return html;
}

// ── Rules tab ─────────────────────────────────────────────
function _tabRules() {
  const rulesYaml = _settings.custom_rules_yaml || '';
  return `
    <div class="cfg-section-header">
      <h2>Audit Rules</h2>
      <p>Define custom architectural boundaries, violation patterns, and scoring weights in YAML.</p>
    </div>
    <div class="cfg-card">
      <div class="cfg-card__body">
        <div class="rules-info-block">
          <div class="rules-info-row">
            <span class="rules-info-icon">📄</span>
            <div>
              <div style="font-size:var(--text-xs); font-weight:600">Default rules</div>
              <code style="font-size:var(--text-xs)">nexus_audit_v3/default_rules.yaml</code>
            </div>
          </div>
          <div class="rules-info-row">
            <span class="rules-info-icon">📁</span>
            <div>
              <div style="font-size:var(--text-xs); font-weight:600">Project override</div>
              <code style="font-size:var(--text-xs)">{project_path}/audit_rules.yaml</code>
            </div>
          </div>
          <div style="font-size:var(--text-xs); color:var(--text-muted); margin-top:var(--space-2)">
            Available rule types: <strong>boundary</strong>, <strong>ghost</strong>, <strong>cycle</strong>, <strong>regex</strong>, <strong>pattern</strong>, <strong>metric</strong>
          </div>
        </div>
        <div class="form-field">
          <label class="form-label">Custom Rules (YAML)</label>
          <div class="code-editor-wrap">
            <div class="code-editor-gutter" id="rules-gutter"></div>
            <textarea class="form-input form-textarea form-textarea--code code-editor-textarea"
                      id="s-custom-rules" rows="16"
                      placeholder="# Example: boundary rule&#10;rules:&#10;  - id: no-cross-app-import&#10;    type: boundary&#10;    severity: HIGH">${esc(rulesYaml)}</textarea>
          </div>
          <div class="rules-actions">
            <button class="btn-secondary" id="btn-view-yaml">📄 View Full YAML</button>
            <button class="btn-primary"   id="btn-validate-yaml">✓ Validate</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── About tab ────────────────────────────────────────────
function _tabAbout() {
  const serverUrl = _caps.server_url || '127.0.0.1:8421';
  const version   = _caps.version   || '3.0.0';
  return `
    <div class="cfg-section-header" style="margin-bottom:var(--space-3)">
      <h2 style="font-size:var(--text-md)">About Nexus Audit</h2>
    </div>
    <div class="cfg-card" style="border:none; background:transparent">
      <div class="cfg-card__body" style="padding:0">
        <div class="about-grid" style="gap:4px">
          <div class="about-row" style="padding:4px 0"><span>Tool</span><span>Nexus Audit V3</span></div>
          <div class="about-row" style="padding:4px 0"><span>Version</span><span>${esc(version)}</span></div>
          <div class="about-row" style="padding:4px 0"><span>Server</span><span>${esc(serverUrl)}</span></div>
          <div class="about-row" style="padding:4px 0"><span>Project Path</span><span>${esc(_settings.project_path||'—')}</span></div>
          <div class="about-row" style="padding:4px 0"><span>License</span><span>MIT</span></div>
          <div class="about-row" style="padding:4px 0; border-bottom:none"><span>Stack</span><span>${esc(_settings.primary_stack||'Python')}</span></div>
        </div>
      </div>
    </div>
  `;
}

// ── Save ──────────────────────────────────────────────────
async function _save() {
  const el = document.getElementById('view-settings');
  const p  = { ..._settings };

  const g = id => el?.querySelector('#' + id);

  // Note: Project tab is handled by project.js which has its own save callback.
  // AI tab fields
  if (g('s-ai-enabled')) p.ai_enabled  = g('s-ai-enabled').checked;
  if (g('s-ai-provider'))p.ai_provider = g('s-ai-provider')?.value || p.ai_provider;
  if (g('s-ai-model'))   p.ai_model    = g('s-ai-model')?.value    || p.ai_model;
  // Only send api_key if user actually typed something
  if (g('s-api-key') && g('s-api-key').value) p.api_key = g('s-api-key').value;

  // Rules tab
  if (g('s-custom-rules')) p.custom_rules_yaml = g('s-custom-rules').value;

  // Scanner toggle states from UI
  el?.querySelectorAll('.scanner-toggle-input').forEach(cb => {
    const name = cb.dataset.scanner;
    if (!p.scanners) p.scanners = {};
    p.scanners[name] = cb.checked;
  });

  // Scanner configs from advanced panels
  el?.querySelectorAll('[data-scanner][data-key]').forEach(input => {
    const sn  = input.dataset.scanner;
    const key = input.dataset.key;
    if (!p.scanner_configs) p.scanner_configs = {};
    if (!p.scanner_configs[sn]) p.scanner_configs[sn] = {};
    p.scanner_configs[sn][key] = input.value;
  });

  _showMsg('info', '⏳ Saving…');
  try {
    // BUG FIX 0.1 + 0.2: use api.updateSettings (not saveSettings) and
    // re-fetch canonical state from server instead of storing the response.
    await api.updateSettings(p);
    const fresh = await api.getSettings();
    store.set('settings', fresh);         // triggers _render() via subscription
    _showMsg('success', '✓ Configuration saved');
  } catch(e) {
    _showMsg('error', '✗ Failed: ' + e.message);
  }
}

function _showMsg(type, text) {
  const el = document.getElementById('cfg-msg');
  if (!el) return;
  el.textContent = text;
  el.className   = `cfg-msg cfg-msg--${type}`;
  if (type !== 'info') setTimeout(() => { el.className = 'cfg-msg hidden'; }, 4000);
}

// ── Install scanner via pip ──────────────────────────────
async function _installScanner(name, btn) {
  if (!name) return;
  btn.disabled = true;
  btn.textContent = '\u23f3 Installing\u2026';
  _showMsg('info', `Installing ${name}\u2026`);
  try {
    await api.installScanner(name, ({ line, done, status }) => {
      if (done) {
        if (status === 'ok') {
          _showMsg('success', `\u2713 ${name} installed`);
          _scannerRegistry = null;   // reset cache so next render re-fetches
          _render();
        } else {
          _showMsg('error', `\u2717 Install failed — check console`);
          btn.disabled = false;
          btn.textContent = '\u2b07 Install';
        }
      }
    });
  } catch(e) {
    _showMsg('error', '\u2717 ' + e.message);
    btn.disabled = false;
    btn.textContent = '\u2b07 Install';
  }
}

// ── Custom scanner modal ─────────────────────────────────
function _showCustomScannerModal() {
  const overlay = document.getElementById('modal-overlay') || _createModalOverlay();
  const container = document.getElementById('modal-container');

  container.innerHTML = `
    <h3 style="margin:0 0 16px">🔌 Register Custom Plugin</h3>
    <div class="form-field" style="margin-bottom:12px">
      <label class="form-label">Scanner Name <span style="color:#f85149">*</span></label>
      <input class="form-input" id="custom-name" type="text" placeholder="my-linter"
             style="width:100%;box-sizing:border-box">
    </div>
    <div class="form-field" style="margin-bottom:12px">
      <label class="form-label">Executable Path <span style="color:#f85149">*</span></label>
      <input class="form-input" id="custom-exe" type="text"
             placeholder="/usr/local/bin/my-linter or /path/to/script.sh"
             style="width:100%;box-sizing:border-box">
      <span class="form-hint">Must be an executable file on the server filesystem.</span>
    </div>
    <div class="form-field" style="margin-bottom:20px">
      <label class="form-label">Output Pattern (regex, optional)</label>
      <input class="form-input" id="custom-pattern" type="text"
             placeholder="SEVERITY:file:LINE:message"
             style="width:100%;box-sizing:border-box">
      <span class="form-hint">Named groups: <code>severity</code>, <code>file</code>, <code>line</code>, <code>message</code>. Leave blank for default.</span>
    </div>
    <div id="custom-scanner-error" style="color:#f85149;font-size:0.82rem;margin-bottom:12px;display:none"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn-secondary" id="modal-cancel">Cancel</button>
      <button class="btn-primary" id="modal-register">Register Scanner</button>
    </div>
  `;

  overlay.classList.remove('hidden');
  container.classList.remove('hidden');

  const close = () => {
    overlay.classList.add('hidden');
    container.classList.add('hidden');
  };

  container.querySelector('#modal-cancel').addEventListener('click', close);

  container.querySelector('#modal-register').addEventListener('click', async () => {
    const name    = container.querySelector('#custom-name').value.trim();
    const exe     = container.querySelector('#custom-exe').value.trim();
    const pattern = container.querySelector('#custom-pattern').value.trim();
    const errEl   = container.querySelector('#custom-scanner-error');

    if (!name || !exe) {
      errEl.textContent = 'Scanner Name and Executable Path are required.';
      errEl.style.display = 'block';
      return;
    }
    errEl.style.display = 'none';

    const btn = container.querySelector('#modal-register');
    btn.disabled = true;
    btn.textContent = '⏳ Registering…';
    try {
      await api.registerCustomScanner(name, exe, pattern);
      _showMsg('success', `✓ ${name} registered`);
      close();
      _scannerRegistry = null;   // force re-fetch so new scanner appears
      _render();
    } catch(e) {
      errEl.textContent = '✗ ' + (e.body?.error || e.message);
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Register Scanner';
    }
  });
}


function _showYamlModal(name, enabled, cfg) {
  const lines = [
    'scanners:',
    `  ${name}:`,
    `    enabled: ${!!enabled}`,
    `    strictness: ${cfg.strictness || 'medium'}`,
  ];
  const excludePaths = Array.isArray(cfg.exclude_paths) ? cfg.exclude_paths
    : (cfg.exclude_paths ? cfg.exclude_paths.split(',').map(s => s.trim()).filter(Boolean) : []);
  if (excludePaths.length) {
    lines.push('    exclude_paths:');
    excludePaths.forEach(p => lines.push(`      - ${p}`));
  }
  if ((cfg.skip_checks || []).length) {
    lines.push('    skip_checks:');
    cfg.skip_checks.forEach(c => lines.push(`      - ${c}`));
  }
  const yaml = lines.join('\n');

  const overlay = document.getElementById('modal-overlay') || _createModalOverlay();
  const container = document.getElementById('modal-container');
  const escapedYaml = esc(yaml);
  container.innerHTML = `
    <h3 style="margin:0 0 12px">📄 YAML Snippet — ${esc(name)}</h3>
    <pre id="yaml-snippet" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;overflow-x:auto;font-family:'Fira Code',monospace;font-size:0.82rem;color:#d0d7de;line-height:1.5">${escapedYaml}</pre>
    <p style="font-size:0.78rem;color:#8b949e;margin:8px 0 14px">Paste this into your <code>audit_config.yaml</code> to persist scanner settings in version control.</p>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn-secondary" onclick="
        navigator.clipboard.writeText(document.getElementById('yaml-snippet').textContent)
          .then(() => this.textContent = '\u2713 Copied!')
          .catch(() => this.textContent = '\u2717 Failed');
      ">📋 Copy to Clipboard</button>
      <button class="btn-primary" onclick="
        document.getElementById('modal-overlay').classList.add('hidden');
        document.getElementById('modal-container').classList.add('hidden');
      ">Close</button>
    </div>
  `;
  overlay.classList.remove('hidden');
  container.classList.remove('hidden');
}

function _createModalOverlay() {
  const overlay = document.createElement('div');
  overlay.id = 'modal-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;display:flex;align-items:center;justify-content:center';
  const container = document.createElement('div');
  container.id = 'modal-container';
  container.style.cssText = 'background:#161b22;border:1px solid #30363d;border-radius:10px;padding:24px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;position:relative';
  overlay.appendChild(container);
  overlay.addEventListener('click', e => {
    if (e.target === overlay) {
      overlay.classList.add('hidden');
      container.classList.add('hidden');
    }
  });
  document.body.appendChild(overlay);
  return overlay;
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
