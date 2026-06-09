// frontend/js/views/project.js
// Self-contained Project View — mounts into a DOM element.
// No global state. No page reloads. Every input wired to backend.

import * as api from '../api.js';

const TIERS      = ['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4'];
const AUTH_TYPES = ['none', 'ssh', 'token'];
const TELEMETRY  = ['none', 'datadog', 'opentelemetry'];
const REMEDIATION= ['suggest', 'draft_pr', 'auto_merge'];
const NOTIFY_ON  = ['completion', 'failure', 'critical_only', 'new_findings'];
const VEX_FMTS   = ['CycloneDX', 'CSAF'];
const OUT_FMTS   = ['json', 'html', 'pdf', 'markdown'];

// State local to this view instance
let _el      = null;
let _s       = {};          // working copy of settings
let _caps    = {};          // capabilities from /api/capabilities
let _dirty   = false;
let _onSave  = null;        // callback(updatedSettings)

/**
 * Mount the project view into `element`.
 * @param element  DOM node to render into
 * @param settings current Settings object (from store)
 * @param onSave   async callback(updatedSettings) — called on Save
 */
export function mountProject(element, settings, onSave) {
  _el     = element;
  _s      = deepClone(settings);
  _onSave = onSave;
  _caps   = {}; // reset

  api.getCapabilities().then(c => { _caps = c || {}; _render(); }).catch(() => _render());
}

// ── Render ────────────────────────────────────────────────────────────────────
function _render() {
  if (!_el) return;

  _el.innerHTML = `
<div class="pv">

  ${_section('Project Identity', `
    <div class="pv-row3">
      ${_field('Project Name', _input('project_name', _s.project_name, 'My Project', true))}
      ${_field('Project Key', _input('project_key', _s.project_key, 'my-project'))}
      ${_field('Version', _input('project_version', _s.project_version, 'v1.0.0'))}
    </div>
    <div class="pv-row3">
      ${_field('Primary Stack', _multicheck('primary_stack',
          (_caps.stacks || ['Python','Go','JavaScript','TypeScript','Rust','Java','C++']),
          _s.primary_stack || []))}
      ${_field('Criticality', _select('project_criticality_tier', TIERS, _s.project_criticality_tier || 'Tier 3'))}
      ${_field('Owner', _input('project_owner', _s.project_owner, 'team-name'))}
    </div>
    ${_field('Description', _input('project_description', _s.project_description, 'One-line description of this project'))}
  `)}

  ${_section('Source', `
    <div class="pv-source-tabs">
      <button class="pv-stab${_s.source_type !== 'remote' ? ' active':''}" data-src="local">Local Filesystem</button>
      <button class="pv-stab${_s.source_type === 'remote' ? ' active':''}" data-src="remote">Remote Repository</button>
    </div>

    <div id="pv-local" class="${_s.source_type === 'remote' ? 'hidden' : ''}">
      <div class="pv-path-row">
        ${_field('Codebase Path', `
          <div class="pv-path-group">
            <input class="pv-input pv-input--mono" id="pv-project_path"
                   value="${esc(_s.project_path || '')}" placeholder="/absolute/path/to/project"
                   data-key="project_path">
            <button class="pv-btn pv-btn--sm" id="pv-browse">Browse</button>
            <button class="pv-btn pv-btn--ping" id="pv-ping">⚡ Ping Project</button>
            <input type="file" id="pv-dir-picker" webkitdirectory directory style="display:none">
          </div>
          <div id="pv-path-status" class="pv-status"></div>
        `)}
      </div>
    </div>

    <div id="pv-remote" class="${_s.source_type !== 'remote' ? 'hidden' : ''}">
      <div class="pv-row2">
        ${_field('Repository URL', `
          <div class="pv-path-group">
            <input class="pv-input pv-input--mono" id="pv-source_remote_url"
                   value="${esc(_s.source_remote_url || '')}" placeholder="https://github.com/org/repo"
                   data-key="source_remote_url">
            <button class="pv-btn pv-btn--sm" id="pv-validate-remote">Validate</button>
          </div>
          <div id="pv-remote-status" class="pv-status"></div>
        `)}
        ${_field('Branch', _input('source_remote_branch', _s.source_remote_branch || 'main', 'main'))}
      </div>
      <div class="pv-row2">
        ${_field('Authentication', _select('source_remote_auth_type', AUTH_TYPES, _s.source_remote_auth_type || 'none'))}
        ${_field('Token Env Var', _input('source_remote_token_env', _s.source_remote_token_env, '$GIT_TOKEN'))}
      </div>
    </div>
  `)}

  ${_section('Audit Scope', `
    <div class="pv-row2">
      <div>
        ${_field('Include Patterns', _listbox('inclusions', _s.inclusions || []))}
      </div>
      <div>
        ${_field('Exclude Patterns', _listbox('exclusions', _s.exclusions || []))}
      </div>
    </div>
    <div class="pv-row2">
      ${_field('Enabled File Extensions',
        _extchecks('enabled_extensions',
          ['.py','.js','.ts','.jsx','.tsx','.go','.rs','.java','.rb','.php','.json','.yaml'],
          _s.enabled_extensions || ['.py'])
      )}
      <div>
        ${_field('Test File Pattern', _input('test_pattern', _s.test_pattern, 'test_*.py'))}
        ${_field('Max File Size (KB)', _numInput('max_file_size_kb', _s.max_file_size_kb || 500))}
      </div>
    </div>
  `)}

  ${_section('Reporting', `
    <div class="pv-row2">
      ${_field('Output Formats', _multicheck('output_formats', OUT_FMTS, _s.output_formats || ['json','html']))}
      ${_field('VEX Formats', _multicheck('vex_formats', VEX_FMTS, _s.vex_formats || []))}
    </div>
    <div class="pv-row2">
      ${_field('Output Directory', _input('report_output_dir', _s.report_output_dir, './audit_reports'))}
      ${_field('Retention (days, 0=forever)', _numInput('report_retention_days', _s.report_retention_days ?? 0))}
    </div>
    <div class="pv-row2">
      ${_field('', `
        <label class="pv-check-label">
          <input type="checkbox" class="pv-check" data-key="include_suppressions"
            ${_s.include_suppressions ? 'checked':''}>
          Include suppressions log in report
        </label>
      `)}
    </div>
    ${_field('Custom Metadata', _kvTable('custom_metadata', _s.custom_metadata || []))}
  `)}

  ${_section('AI Agent', `
    <div class="pv-row2">
      ${_field('Remediation Authority', _select('ai_remediation_level', REMEDIATION, _s.ai_remediation_level || 'suggest'))}
      ${_field('', `
        <label class="pv-check-label">
          <input type="checkbox" class="pv-check" data-key="ai_verify_with_tests"
            ${_s.ai_verify_with_tests ? 'checked':''}>
          Verify fixes with test suite
        </label>
        <div class="pv-conditional ${_s.ai_verify_with_tests ? '' : 'hidden'}" id="pv-testcmd-wrap">
          ${_input('ai_test_command', _s.ai_test_command, 'pytest')}
        </div>
      `)}
    </div>
  `)}

  ${_section('Integrations', `
    ${_field('Webhook URL', _input('webhook_url', _s.webhook_url, 'https://hooks.slack.com/services/…'))}
    ${_field('Notify On', _multicheck('notify_on', NOTIFY_ON, _s.notify_on || []))}
    <label class="pv-check-label">
      <input type="checkbox" class="pv-check" data-key="ci_mode"
        ${_s.ci_mode ? 'checked':''}>
      CI/CD mode — fail build on critical issues
    </label>
    ${_field('Editor URL Scheme', _input('editor_url_scheme', _s.editor_url_scheme, 'vscode://file/{path}:{line}'))}
    <div class="pv-collapsible">
      <button class="pv-collapse-btn" id="pv-quality-gate-toggle">
        Quality Gate <span class="pv-arrow">▼</span>
      </button>
      <div id="pv-quality-gate-body" class="hidden">
        <div class="pv-row2" style="margin-top:8px">
          ${_field('Max CRITICAL findings', _numInput('quality_gate.max_critical', (_s.quality_gate||{}).max_critical ?? 0))}
          ${_field('Min health score', _numInput('quality_gate.min_score', (_s.quality_gate||{}).min_score ?? 0))}
        </div>
      </div>
    </div>
  `)}

  ${_section('Context & Priority', `
    <div class="pv-row2">
      <label class="pv-check-label">
        <input type="checkbox" class="pv-check" data-key="reachability_enabled"
          ${(_s.reachability_enabled !== false) ? 'checked':''}>
        Reachability analysis (trace data flow from entry points)
      </label>
      ${_field('Runtime Telemetry Source', _select('telemetry_source', TELEMETRY, _s.telemetry_source || 'none'))}
    </div>
  `)}

  ${_section('Environment & Secrets', `
    ${_field('Environment Variables', _kvTable('environment_vars', _s.environment_vars || []))}
    ${_field('Secret References', _kvTable('secret_refs', _s.secret_refs || [], 'Name', 'Env Var'))}
  `)}

  <div class="pv-footer">
    <span class="pv-msg" id="pv-msg"></span>
    <button class="pv-btn pv-btn--ghost" id="pv-discard">Discard</button>
    <button class="pv-btn pv-btn--primary" id="pv-save">Save Configuration</button>
  </div>

</div>
  `;

  _wire();
}

// ── HTML helpers ─────────────────────────────────────────────────────────────
function _section(title, content) {
  return `<div class="pv-section">
    <div class="pv-section-title">${title}</div>
    <div class="pv-section-body">${content}</div>
  </div>`;
}

function _field(label, control) {
  return `<div class="pv-field">
    ${label ? `<label class="pv-label">${label}</label>` : ''}
    ${control}
  </div>`;
}

function _input(key, value = '', placeholder = '', required = false) {
  return `<input class="pv-input" data-key="${key}"
    value="${esc(value)}" placeholder="${esc(placeholder)}"
    ${required ? 'required' : ''}>`;
}

function _numInput(key, value = 0) {
  return `<input class="pv-input pv-input--num" type="number" data-key="${key}"
    value="${Number(value) || 0}" min="0">`;
}

function _select(key, options, current) {
  return `<select class="pv-select" data-key="${key}">
    ${options.map(o => `<option${o===current?' selected':''}>${o}</option>`).join('')}
  </select>`;
}

function _multicheck(key, options, selected) {
  return `<div class="pv-multichk" data-multikey="${key}">
    ${options.map(o => `
      <label class="pv-check-label">
        <input type="checkbox" class="pv-check" data-key="${key}[]" value="${o}"
          ${selected.map(s=>s.toLowerCase()).includes(o.toLowerCase()) ? 'checked':''}>
        ${o}
      </label>`).join('')}
  </div>`;
}

function _extchecks(key, options, selected) {
  return `<div class="pv-extchk" data-multikey="${key}">
    ${options.map(o => `
      <label class="pv-extlabel">
        <input type="checkbox" data-key="${key}[]" value="${o}"
          ${selected.includes(o) ? 'checked':''}>
        ${o}
      </label>`).join('')}
  </div>`;
}

function _listbox(key, items) {
  const id = `pv-list-${key}`;
  return `<div class="pv-listbox" id="${id}" data-listkey="${key}">
    ${items.map((item, i) => `
      <div class="pv-list-row" data-idx="${i}">
        <span class="pv-list-item">${esc(item)}</span>
        <button class="pv-list-del" data-listkey="${key}" data-idx="${i}">×</button>
      </div>`).join('')}
  </div>
  <div class="pv-list-add-row">
    <input class="pv-input pv-input--mono pv-list-input" data-listkey="${key}"
           placeholder="Add pattern (Enter to add)">
    <button class="pv-btn pv-btn--sm pv-list-confirm" data-listkey="${key}">+</button>
  </div>`;
}

function _kvTable(key, rows, kLabel = 'Key', vLabel = 'Value') {
  return `<div class="pv-kvtable" data-kvkey="${key}">
    <div class="pv-kvheader"><span>${kLabel}</span><span>${vLabel}</span><span></span></div>
    ${rows.map((r, i) => `
      <div class="pv-kvrow">
        <input class="pv-input" data-kvkey="${key}" data-idx="${i}" data-col="key"
               value="${esc(r.key || '')}">
        <input class="pv-input" data-kvkey="${key}" data-idx="${i}" data-col="value"
               value="${esc(r.value || '')}">
        <button class="pv-list-del" data-kvkey="${key}" data-idx="${i}">×</button>
      </div>`).join('')}
  </div>
  <button class="pv-btn pv-btn--sm pv-kv-add" data-kvkey="${key}">+ Add</button>`;
}

// ── Event wiring ─────────────────────────────────────────────────────────────
function _wire() {
  if (!_el) return;

  // All simple inputs → update _s on change
  _el.querySelectorAll('.pv-input[data-key], .pv-select[data-key]').forEach(inp => {
    inp.addEventListener('input', () => {
      if (inp.type === 'number') {
        _setDeep(inp.dataset.key, Number(inp.value) || 0);
      } else {
        _setKey(inp.dataset.key, inp.value);
      }
    });
  });

  // Checkboxes (single boolean)
  _el.querySelectorAll('.pv-check[data-key]:not([data-key$="[]"])').forEach(cb => {
    cb.addEventListener('change', () => {
      _setKey(cb.dataset.key, cb.checked);
      // Conditional visibility
      if (cb.dataset.key === 'ai_verify_with_tests') {
        _el.querySelector('#pv-testcmd-wrap')?.classList.toggle('hidden', !cb.checked);
      }
    });
  });

  // Multi-checkboxes (array)
  _el.querySelectorAll('.pv-check[data-key$="[]"]').forEach(cb => {
    cb.addEventListener('change', () => {
      const key = cb.dataset.key.slice(0, -2);
      const all = [..._el.querySelectorAll(`.pv-check[data-key="${key}[]"]`)]
        .filter(c => c.checked).map(c => c.value);
      _setKey(key, all);
    });
  });

  // Source type tabs
  _el.querySelectorAll('.pv-stab').forEach(btn => {
    btn.addEventListener('click', () => {
      _setKey('source_type', btn.dataset.src);
      _el.querySelectorAll('.pv-stab').forEach(b => b.classList.toggle('active', b === btn));
      _el.querySelector('#pv-local')?.classList.toggle('hidden', btn.dataset.src === 'remote');
      _el.querySelector('#pv-remote')?.classList.toggle('hidden', btn.dataset.src !== 'remote');
    });
  });

  // Browse
  _el.querySelector('#pv-browse')?.addEventListener('click', () => {
    _el.querySelector('#pv-dir-picker')?.click();
  });
  _el.querySelector('#pv-dir-picker')?.addEventListener('change', e => {
    const first = e.target.files?.[0];
    if (first) {
      // webkitRelativePath gives "dirname/file" — extract root folder name
      const parts = (first.webkitRelativePath || first.name).split('/');
      const dirName = parts[0];
      const inp = _el.querySelector('#pv-project_path');
      if (inp) { inp.value = dirName; _setKey('project_path', dirName); }
    }
  });

  // Ping — on button click and on blur of path field
  _el.querySelector('#pv-ping')?.addEventListener('click', _pingProject);
  _el.querySelector('#pv-project_path')?.addEventListener('blur', () => {
    const v = (_s.project_path || '').trim();
    if (v) _pingProject();
  });

  // Validate remote
  _el.querySelector('#pv-validate-remote')?.addEventListener('click', _validateRemote);
  _el.querySelector('[data-key="source_remote_url"]')?.addEventListener('input', e => {
    _setKey('source_remote_url', e.target.value);
  });

  // List boxes
  _el.querySelectorAll('.pv-list-input').forEach(inp => {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); _listAdd(inp.dataset.listkey, inp.value); inp.value = ''; }
    });
  });
  _el.querySelectorAll('.pv-list-confirm').forEach(btn => {
    btn.addEventListener('click', () => {
      const inp = _el.querySelector(`.pv-list-input[data-listkey="${btn.dataset.listkey}"]`);
      if (inp) { _listAdd(btn.dataset.listkey, inp.value); inp.value = ''; }
    });
  });
  _el.querySelectorAll('.pv-list-del[data-listkey]').forEach(btn => {
    btn.addEventListener('click', () => _listDel(btn.dataset.listkey, parseInt(btn.dataset.idx)));
  });

  // KV tables
  _el.querySelectorAll('.pv-kvrow input').forEach(inp => {
    inp.addEventListener('input', () => {
      const key = inp.dataset.kvkey;
      const idx = parseInt(inp.dataset.idx);
      const col = inp.dataset.col;
      if (!_s[key]) _s[key] = [];
      if (!_s[key][idx]) _s[key][idx] = {key:'',value:''};
      _s[key][idx][col] = inp.value;
      _dirty = true;
    });
  });
  _el.querySelectorAll('.pv-kv-add').forEach(btn => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.kvkey;
      if (!_s[k]) _s[k] = [];
      _s[k].push({key:'', value:''});
      _render();
    });
  });
  _el.querySelectorAll('.pv-list-del[data-kvkey]').forEach(btn => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.kvkey;
      const idx = parseInt(btn.dataset.idx);
      if (_s[k]) { _s[k].splice(idx, 1); _render(); }
    });
  });

  // Quality gate toggle
  _el.querySelector('#pv-quality-gate-toggle')?.addEventListener('click', () => {
    const body  = _el.querySelector('#pv-quality-gate-body');
    const arrow = _el.querySelector('#pv-quality-gate-toggle .pv-arrow');
    body?.classList.toggle('hidden');
    if (arrow) arrow.textContent = body?.classList.contains('hidden') ? '▼' : '▲';
  });

  // Footer
  _el.querySelector('#pv-save')?.addEventListener('click',    _save);
  _el.querySelector('#pv-discard')?.addEventListener('click', _discard);
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function _pingProject() {
  const path = _s.project_path?.trim();
  if (!path) return;

  const statusEl = _el?.querySelector('#pv-path-status');
  if (statusEl) { statusEl.textContent = '⏳ Pinging…'; statusEl.className = 'pv-status pv-status--info'; }

  try {
    const result = await api.pingProject(path);
    if (!result.valid) {
      if (statusEl) { statusEl.textContent = `✗ ${result.error}`; statusEl.className = 'pv-status pv-status--error'; }
      return;
    }
    if (statusEl) { statusEl.textContent = `✓ ${result.path}`; statusEl.className = 'pv-status pv-status--ok'; }

    // Auto-fill only empty fields — never overwrite user-set values
    const autofill = (key, val) => { if (val && !_s[key]) _setKey(key, val); };
    autofill('project_name',    result.project_name);
    autofill('project_key',     result.project_key);
    autofill('project_version', result.project_version);

    if (result.primary_stack?.length && !(_s.primary_stack?.length)) {
      _setKey('primary_stack', result.primary_stack);
    }
    if (result.suggested_exclusions?.length && !_s.exclusions?.length) {
      _setKey('exclusions', result.suggested_exclusions);
    }
    if (result.suggested_extensions?.length && !_s.enabled_extensions?.length) {
      _setKey('enabled_extensions', result.suggested_extensions);
    }
    if (result.suggested_test_pattern && !_s.test_pattern) {
      _setKey('test_pattern', result.suggested_test_pattern);
    }

    _render(); // re-render to show auto-filled values
  } catch(e) {
    if (statusEl) { statusEl.textContent = `✗ ${e.message}`; statusEl.className = 'pv-status pv-status--error'; }
  }
}

async function _validateRemote() {
  const url      = _s.source_remote_url?.trim();
  const branch   = _s.source_remote_branch || 'main';
  const authType = _s.source_remote_auth_type || 'none';
  const tokenEnv = _s.source_remote_token_env || '';
  const statusEl = _el?.querySelector('#pv-remote-status');

  if (!url) {
    if (statusEl) { statusEl.textContent = '✗ Enter a URL first'; statusEl.className = 'pv-status pv-status--error'; }
    return;
  }
  if (statusEl) { statusEl.textContent = '⏳ Checking…'; statusEl.className = 'pv-status pv-status--info'; }

  try {
    const result = await api.validateRemote(url, branch, authType, tokenEnv);
    if (result.reachable) {
      if (statusEl) { statusEl.textContent = '✓ Reachable'; statusEl.className = 'pv-status pv-status--ok'; }
    } else {
      if (statusEl) { statusEl.textContent = `✗ ${result.error || 'Not reachable'}`; statusEl.className = 'pv-status pv-status--error'; }
    }
  } catch(e) {
    if (statusEl) { statusEl.textContent = `✗ ${e.message}`; statusEl.className = 'pv-status pv-status--error'; }
  }
}

async function _save() {
  const msgEl = _el?.querySelector('#pv-msg');
  if (msgEl) { msgEl.textContent = '⏳ Saving…'; msgEl.className = 'pv-msg pv-msg--info'; }
  try {
    await _onSave({ ..._s });
    _dirty = false;
    if (msgEl) { msgEl.textContent = '✓ Saved'; msgEl.className = 'pv-msg pv-msg--ok'; }
    setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 3000);
  } catch(e) {
    if (msgEl) { msgEl.textContent = `✗ ${e.message}`; msgEl.className = 'pv-msg pv-msg--error'; }
  }
}

function _discard() {
  api.getSettings().then(s => {
    _s = deepClone(s);
    _dirty = false;
    _render();
  });
}

// ── State helpers ─────────────────────────────────────────────────────────────
function _setKey(key, value) {
  _s[key] = value;
  _dirty = true;
}

function _setDeep(dotKey, value) {
  // Handles keys like "quality_gate.max_critical"
  const parts = dotKey.split('.');
  if (parts.length === 1) { _s[parts[0]] = value; }
  else {
    if (!_s[parts[0]] || typeof _s[parts[0]] !== 'object') _s[parts[0]] = {};
    _s[parts[0]][parts[1]] = value;
  }
  _dirty = true;
}

function _listAdd(key, value) {
  const val = (value || '').trim();
  if (!val) return;
  if (!_s[key]) _s[key] = [];
  if (!_s[key].includes(val)) { _s[key].push(val); _render(); }
}

function _listDel(key, idx) {
  if (_s[key]) { _s[key].splice(idx, 1); _render(); }
}

function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
