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

const STACKS = ['Python','Go','JavaScript','TypeScript','Python/Go','Rust','Java','C++'];
const FORMATS = ['JSON','HTML','PDF','HTML, PDF, JSON'];

const SCANNER_META = {
  vulture:         { label: 'Vulture',        category: 'Quality',       badge: 'Dead Code'     },
  bandit:          { label: 'Bandit',         category: 'Security',      badge: 'Vulnerability' },
  radon:           { label: 'Radon',          category: 'Quality',       badge: 'Complexity'    },
  pylint:          { label: 'Pylint',         category: 'Quality',       badge: 'Linting'       },
  semgrep:         { label: 'Semgrep',        category: 'Security',      badge: 'Patterns'      },
  'pip-audit':     { label: 'pip-audit',      category: 'Supply Chain',  badge: 'CVE'           },
  'npm-audit':     { label: 'npm-audit',      category: 'Supply Chain',  badge: 'CVE'           },
  lizard:          { label: 'Lizard',         category: 'Architecture',  badge: 'Structure'     },
  django_settings: { label: 'Django Config',  category: 'Security',      badge: 'Config'        },
};

let _activeTab     = 'project';
let _expandedScan  = null;   // which scanner's advanced panel is open
let _settings      = {};

export function initSettings() {
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
        <button class="btn-secondary" id="cfg-discard">Discard Changes</button>
        <button class="btn-primary"   id="cfg-save">Save Configuration</button>
      </div>
      <div class="cfg-msg hidden" id="cfg-msg"></div>
    </div>
  `;

  el.querySelectorAll('.cfg-tab').forEach(b =>
    b.addEventListener('click', () => { _activeTab = b.dataset.tab; _render(); })
  );
  el.querySelector('#cfg-save')?.addEventListener('click',    _save);
  el.querySelector('#cfg-discard')?.addEventListener('click', _render);

  // Show footer only on tabs that have saveable content
  if (['project','scanners','ai'].includes(_activeTab)) {
    el.querySelector('#cfg-footer')?.classList.remove('hidden');
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
}

// ── Tab routing ──────────────────────────────────────────
function _renderTab(tab) {
  switch(tab) {
    case 'project':  return _tabProject();
    case 'scanners': return _tabScanners();
    case 'ai':       return _tabAI();
    case 'rules':    return _tabRules();
    case 'about':    return _tabAbout();
    default:         return '';
  }
}

// ── Project tab — 4-card grid ────────────────────────────
function _tabProject() {
  const s = _settings;
  return `
    <div class="cfg-section-header">
      <h2>Audit Configuration Dashboard</h2>
      <p>Ensure all audit parameters are correctly configured before running an audit.</p>
    </div>
    <div class="cfg-cards">

      <!-- Card 1: Identity -->
      <div class="cfg-card">
        <div class="cfg-card__head">
          <span class="cfg-card__icon">🏗</span>
          <span class="cfg-card__title">Project Identity &amp; Metadata</span>
        </div>
        <div class="cfg-card__body">
          <div class="form-field">
            <label class="form-label">Project Name</label>
            <input class="form-input" id="s-project-name" type="text"
                   value="${esc(s.project_name || '')}" placeholder="My Project">
          </div>
          <div class="form-field">
            <label class="form-label">Project Version</label>
            <input class="form-input" id="s-project-version" type="text"
                   value="${esc(s.project_version || '')}" placeholder="v1.0.0">
          </div>
          <div class="form-field">
            <label class="form-label">Primary Stack</label>
            <select class="form-input" id="s-primary-stack">
              ${STACKS.map(st => `<option${st===s.primary_stack?' selected':''}>${st}</option>`).join('')}
            </select>
          </div>
        </div>
      </div>

      <!-- Card 2: Repository -->
      <div class="cfg-card">
        <div class="cfg-card__head">
          <span class="cfg-card__icon">◈</span>
          <span class="cfg-card__title">Repository &amp; Codebase Configuration</span>
        </div>
        <div class="cfg-card__body">
          <div class="repo-tabs">
            <button class="repo-tab active" data-repo="local">Local Filesystem</button>
            <button class="repo-tab"        data-repo="remote">Remote Repository</button>
          </div>
          <div id="repo-local">
            <div class="form-field">
              <label class="form-label">Codebase Path</label>
              <div class="input-with-btn">
                <input class="form-input" id="s-project-path" type="text"
                       value="${esc(s.project_path || '')}"
                       placeholder="/home/user/my-project">
                <button class="btn-secondary-sm">Browse Files…</button>
              </div>
            </div>
          </div>
          <div id="repo-remote" class="hidden">
            <div class="form-field">
              <label class="form-label">Repository URL</label>
              <input class="form-input" type="text" placeholder="https://github.com/org/repo">
            </div>
            <div class="form-field">
              <label class="form-label">Token</label>
              <input class="form-input" type="password" placeholder="Token">
            </div>
            <div class="form-field">
              <label class="form-label">Branch</label>
              <input class="form-input" type="text" placeholder="main">
            </div>
          </div>
        </div>
      </div>

      <!-- Card 3: Audit Scope -->
      <div class="cfg-card">
        <div class="cfg-card__head">
          <span class="cfg-card__icon">▽</span>
          <span class="cfg-card__title">Audit Scope &amp; Exclusions</span>
        </div>
        <div class="cfg-card__body">
          <div class="form-field">
            <label class="form-label">File &amp; Directory Inclusions</label>
            <textarea class="form-input form-textarea" id="s-inclusions"
                      placeholder="src/**&#10;config/**">${(s.inclusions||[]).join('\n')}</textarea>
            <div class="path-actions">
              <button class="btn-tag-add" data-target="s-inclusions">+ Add Path</button>
              <button class="btn-tag-remove" data-target="s-inclusions">− Remove Selected</button>
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">File &amp; Directory Exclusions</label>
            <textarea class="form-input form-textarea" id="s-exclusions"
                      placeholder="node_modules/**&#10;tests/**">${(s.exclusions||[]).join('\n')}</textarea>
            <div class="path-actions">
              <button class="btn-tag-add" data-target="s-exclusions">+ Add Path</button>
              <button class="btn-tag-remove" data-target="s-exclusions">− Remove Selected</button>
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">Enabled File Extensions</label>
            <div class="ext-checkboxes">
              ${['.py','.js','.ts','.json','.go','.cpp','.rs','.rb'].map(ext => `
                <label class="ext-check">
                  <input type="checkbox" value="${ext}"
                    ${(s.enabled_extensions||['.py']).includes(ext) ? 'checked' : ''}>
                  ${ext}
                </label>
              `).join('')}
            </div>
          </div>
        </div>
      </div>

      <!-- Card 4: Reporting -->
      <div class="cfg-card">
        <div class="cfg-card__head">
          <span class="cfg-card__icon">📄</span>
          <span class="cfg-card__title">Reporting &amp; Metadata</span>
        </div>
        <div class="cfg-card__body">
          <div class="form-field">
            <label class="form-label">Output Format</label>
            <select class="form-input" id="s-output-format">
              ${FORMATS.map(f=>`<option${f===s.output_format?' selected':''}>${f}</option>`).join('')}
            </select>
          </div>
          <div class="form-field">
            <label class="form-label">Report Output Directory</label>
            <input class="form-input" id="s-report-dir" type="text"
                   value="${esc(s.report_output_dir||'')}"
                   placeholder="Report Output Directory">
          </div>
          <div class="form-field">
            <label class="form-label">Custom Metadata</label>
            <div class="metadata-rows" id="metadata-rows">
              ${(s.custom_metadata||[]).map((m,i)=>`
                <div class="metadata-row">
                  <input class="form-input meta-key"   type="text" value="${esc(m.key||'')}"   placeholder="Key">
                  <input class="form-input meta-value" type="text" value="${esc(m.value||'')}" placeholder="Value">
                  <button class="btn-icon-del" data-meta-idx="${i}">🗑</button>
                </div>
              `).join('')}
            </div>
            <button class="btn-tag-add" id="meta-add">+ Add</button>
          </div>

          <!-- Integrations collapsible -->
          <div class="collapsible-section">
            <button class="collapsible-trigger" id="integrations-toggle">
              ⚙ Integrations &amp; Advanced
              <span class="collapsible-arrow">▲</span>
            </button>
            <div id="integrations-body">
              <label class="ext-check" style="margin-bottom:8px">
                <input type="checkbox" id="s-webhook-on"
                  ${s.webhook_url ? 'checked':''}>
                Slack Webhook Notifications
              </label>
              <div class="form-field">
                <label class="form-label">Webhook</label>
                <input class="form-input" id="s-webhook-url" type="text"
                       value="${esc(s.webhook_url||'')}"
                       placeholder="https://hooks.slack.com/services/…">
              </div>
            </div>
          </div>
        </div>
      </div>

    </div><!-- /cfg-cards -->
  `;

  // Wire repo tab switching
  setTimeout(() => {
    const el = document.getElementById('view-settings');
    el?.querySelectorAll('.repo-tab').forEach(b => {
      b.addEventListener('click', () => {
        el.querySelectorAll('.repo-tab').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        el.querySelector('#repo-local')?.classList.toggle('hidden',  b.dataset.repo !== 'local');
        el.querySelector('#repo-remote')?.classList.toggle('hidden', b.dataset.repo !== 'remote');
      });
    });
    el?.querySelector('#integrations-toggle')?.addEventListener('click', () => {
      const body  = el.querySelector('#integrations-body');
      const arrow = el.querySelector('.collapsible-arrow');
      body?.classList.toggle('hidden');
      if (arrow) arrow.textContent = body?.classList.contains('hidden') ? '▼' : '▲';
    });
    el?.querySelector('#meta-add')?.addEventListener('click', () => {
      if (!_settings.custom_metadata) _settings.custom_metadata = [];
      _settings.custom_metadata.push({key:'',value:''});
      _render();
    });
  }, 0);
}

// ── Scanners tab — grouped by category ──────────────────
function _tabScanners() {
  const scanners = _settings.scanners || {};
  const configs  = _settings.scanner_configs || {};

  // Group scanners by category
  const groups = {};
  for (const [name, enabled] of Object.entries(scanners)) {
    const meta = SCANNER_META[name] || { label: name, category: 'Other', badge: '' };
    if (!groups[meta.category]) groups[meta.category] = [];
    groups[meta.category].push({ name, enabled, meta, cfg: configs[name] || {} });
  }
  // Add known scanners not yet in settings
  for (const [name, meta] of Object.entries(SCANNER_META)) {
    if (!(name in scanners)) {
      if (!groups[meta.category]) groups[meta.category] = [];
      groups[meta.category].push({ name, enabled: false, meta, cfg: {} });
    }
  }

  const CATEGORY_ICONS = {
    'Quality':'⚙','Security':'🛡','Supply Chain':'🔗',
    'Architecture':'🏗','Performance':'⚡','Other':'📦',
  };

  return `
    <div class="scanners-pane">
      <p class="cfg-hint">Advanced configuration overrides backend YAML defaults.</p>
      ${Object.entries(groups).map(([cat, items]) => `
        <div class="scanner-group">
          <div class="scanner-group__header">
            <span class="scanner-group__icon">${CATEGORY_ICONS[cat]||'📦'}</span>
            <span class="scanner-group__name">${cat}</span>
          </div>
          ${items.map(({ name, enabled, meta, cfg }) => _renderScannerRow(name, enabled, meta, cfg)).join('')}
        </div>
      `).join('')}
    </div>
  `;
}

function _renderScannerRow(name, enabled, meta, cfg) {
  const isExpanded = _expandedScan === name;
  const excludePaths = (cfg.exclude_paths || []).join(', ');
  const strictness   = cfg.strictness || 'Medium';

  return `
    <div class="scanner-card${enabled ? ' scanner-card--enabled' : ''}">
      <div class="scanner-card__row">
        <label class="scanner-toggle">
          <input type="checkbox" class="scanner-toggle-input"
                 data-scanner="${name}" ${enabled ? 'checked' : ''}>
          <span class="scanner-toggle__track"></span>
        </label>
        <span class="scanner-toggle-label">${enabled ? 'Enabled' : ''}</span>
        <span class="scanner-name">${meta.label}</span>
        <span class="scanner-badge">${meta.badge}</span>
        ${enabled ? `
          <label class="scanner-strictness-label">Strictness</label>
          <select class="scanner-strictness" data-scanner="${name}" data-key="strictness">
            ${['Low','Medium','High'].map(l=>`<option${l===strictness?' selected':''}>${l}</option>`).join('')}
          </select>
          <button class="scanner-expand-btn" data-scanner="${name}"
                  title="Advanced configuration">⚙</button>
        ` : `<button class="scanner-expand-btn" data-scanner="${name}" disabled>⚙</button>`}
      </div>

      ${isExpanded && enabled ? `
        <div class="scanner-advanced">
          <div class="advanced-row">
            <label class="form-label">Exclude Paths</label>
            <input class="form-input" type="text"
                   data-scanner="${name}" data-key="exclude_paths"
                   value="${esc(excludePaths)}"
                   placeholder="/tests, /migrations, /manotes">
            <span class="form-hint">Comma-separated paths</span>
          </div>
          <div class="advanced-row">
            <label class="form-label">Checks to Skip</label>
            <div class="checks-list">
              ${_scannerChecks(name).map(c=>`
                <label class="check-item">
                  <input type="checkbox" data-scanner="${name}" data-check="${c.id}"
                    ${(cfg.skip_checks||[]).includes(c.id) ? 'checked' : ''}>
                  ${c.label}
                </label>
              `).join('')}
            </div>
          </div>
          <button class="yaml-preview-btn">📄 View Raw YAML Snippet</button>
        </div>
      ` : ''}
    </div>
  `;
}

function _scannerChecks(name) {
  const checks = {
    vulture: [
      {id:'V001', label:'unused-variable (V001)'},
      {id:'V002', label:'unused-import (V002)'},
      {id:'V003', label:'unread-variable (V003)'},
    ],
    bandit: [
      {id:'B101', label:'assert-used (B101)'},
      {id:'B105', label:'hardcoded-password (B105)'},
      {id:'B201', label:'flask-debug-true (B201)'},
    ],
  };
  return checks[name] || [];
}

// ── AI tab ────────────────────────────────────────────────
function _tabAI() {
  const s = _settings;
  const ai = s.ai_enabled || false;
  return `
    <div class="cfg-section-header">
      <h2>AI Configuration</h2>
      <p>AI-powered recommendations require an API key. The AI referee analyses findings and suggests exact code fixes.</p>
    </div>
    <div class="cfg-card" style="max-width:520px">
      <div class="cfg-card__body">
        <label class="toggle-row">
          <div class="toggle-row__info">
            <span class="toggle-row__name">Enable AI</span>
            <span class="toggle-row__desc">Generate AI fix recommendations after each scan</span>
          </div>
          <input type="checkbox" id="s-ai-enabled" ${ai ? 'checked' : ''}>
        </label>
        <div class="form-field ${!ai ? 'form-field--disabled' : ''}">
          <label class="form-label">Provider</label>
          <select class="form-input" id="s-ai-provider" ${!ai ? 'disabled' : ''}>
            <option value="claude"  ${s.ai_provider==='claude' ? 'selected':''}>Claude (Anthropic)</option>
            <option value="gemini" ${s.ai_provider==='gemini' ? 'selected':''}>Gemini (Google)</option>
          </select>
        </div>
        <div class="form-field ${!ai ? 'form-field--disabled' : ''}">
          <label class="form-label">Model</label>
          <input class="form-input" id="s-ai-model" type="text"
                 value="${esc(s.ai_model||'')}" ${!ai ? 'disabled' : ''}>
        </div>
        <div class="form-field ${!ai ? 'form-field--disabled' : ''}">
          <label class="form-label">API Key</label>
          <input class="form-input" id="s-api-key" type="password"
                 placeholder="${s.api_key ? '••••••••' : 'Enter API key'}"
                 ${!ai ? 'disabled' : ''}>
          <span class="form-hint">Leave blank to keep existing key.</span>
        </div>
      </div>
    </div>
  `;
}

// ── Rules tab ─────────────────────────────────────────────
function _tabRules() {
  return `
    <div class="cfg-section-header">
      <h2>Audit Rules</h2>
      <p>Define custom architectural boundaries, violation patterns, and scoring weights in YAML.</p>
    </div>
    <div class="cfg-card">
      <div class="cfg-card__body">
        <div class="rules-info">
          <div class="info-block">
            <p>Default rules: <code>nexus_audit_v3/default_rules.yaml</code></p>
            <p>Project override: <code>{project_path}/audit_rules.yaml</code></p>
            <p>Advanced configuration in this file overrides backend YAML defaults.</p>
          </div>
        </div>
        <div class="form-field">
          <label class="form-label">Custom Rules (YAML)</label>
          <textarea class="form-input form-textarea form-textarea--code"
                    id="s-custom-rules" rows="14"
                    placeholder="# Example: boundary rule&#10;rules:&#10;  - id: no-cross-app-import&#10;    type: boundary&#10;    severity: HIGH"></textarea>
        </div>
      </div>
    </div>
  `;
}

// ── About tab ─────────────────────────────────────────────
function _tabAbout() {
  return `
    <div class="cfg-section-header">
      <h2>About</h2>
    </div>
    <div class="cfg-card" style="max-width:480px">
      <div class="cfg-card__body">
        <div class="about-grid">
          <div class="about-row"><span>Tool</span><span>Nexus Audit V3</span></div>
          <div class="about-row"><span>Version</span><span>3.0.0</span></div>
          <div class="about-row"><span>Server</span><span>127.0.0.1:8421</span></div>
          <div class="about-row"><span>Project</span><span>${esc(_settings.project_path||'—')}</span></div>
          <div class="about-row"><span>License</span><span>MIT</span></div>
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

  // Project tab fields
  if (g('s-project-name'))    p.project_name    = g('s-project-name').value.trim();
  if (g('s-project-version')) p.project_version = g('s-project-version').value.trim();
  if (g('s-primary-stack'))   p.primary_stack   = g('s-primary-stack').value;
  if (g('s-project-path'))    p.project_path    = g('s-project-path').value.trim();
  if (g('s-inclusions'))      p.inclusions      = g('s-inclusions').value.split('\n').filter(Boolean);
  if (g('s-exclusions'))      p.exclusions      = g('s-exclusions').value.split('\n').filter(Boolean);
  if (g('s-output-format'))   p.output_format   = g('s-output-format').value;
  if (g('s-report-dir'))      p.report_output_dir = g('s-report-dir').value.trim();
  if (g('s-webhook-url'))     p.webhook_url     = g('s-webhook-url').value.trim();

  const exts = el?.querySelectorAll('.ext-check input[type=checkbox]');
  if (exts?.length) p.enabled_extensions = [...exts].filter(c=>c.checked).map(c=>c.value);

  // AI tab fields
  if (g('s-ai-enabled')) p.ai_enabled  = g('s-ai-enabled').checked;
  if (g('s-ai-provider'))p.ai_provider = g('s-ai-provider')?.value || p.ai_provider;
  if (g('s-ai-model'))   p.ai_model    = g('s-ai-model')?.value    || p.ai_model;
  if (g('s-api-key') && g('s-api-key').value) p.api_key = g('s-api-key').value;

  // Scanner configs from advanced panels
  el?.querySelectorAll('[data-scanner][data-key]').forEach(input => {
    const sn  = input.dataset.scanner;
    const key = input.dataset.key;
    if (!p.scanner_configs) p.scanner_configs = {};
    if (!p.scanner_configs[sn]) p.scanner_configs[sn] = {};
    p.scanner_configs[sn][key] = input.value;
  });

  try {
    const result = await api.saveSettings(p);
    store.set('settings', result);
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
  setTimeout(() => { el.className = 'cfg-msg hidden'; }, 3000);
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
