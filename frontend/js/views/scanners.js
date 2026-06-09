// frontend/js/views/scanners.js
// Self-contained Scanners View

import * as api from '../api.js';

let _el = null;
let _s = {}; // Working copy of settings
let _dirty = false;
let _onSave = null;

let _scannersData = null; // live list from /api/scanners
let _isLoading = true;
let _error = null;

/**
 * Mount the scanners view into `element`.
 */
export function mountScanners(element, settings, onSave) {
  _el = element;
  _s = deepClone(settings);
  _onSave = onSave;
  _isLoading = true;
  _error = null;
  _scannersData = null;

  if (!_s.scanners) _s.scanners = {};
  if (!_s.scanner_configs) _s.scanner_configs = {};

  _render();
  _fetchScanners();
}

async function _fetchScanners() {
  _isLoading = true;
  _error = null;
  _render();
  try {
    _scannersData = await api.getScanners();
  } catch (e) {
    _error = e.message;
  } finally {
    _isLoading = false;
    _render();
  }
}

// ── Render ────────────────────────────────────────────────────────────────────
function _render() {
  if (!_el) return;

  if (_isLoading) {
    _el.innerHTML = `
      <div class="sv-header">
        <h2 style="margin:0;font-size:16px;">Scanners & Rules</h2>
        <button class="pv-btn" id="sv-refresh" disabled>⏳ Loading...</button>
      </div>
      <div class="sv-skeleton">Loading scanners...</div>
    `;
    return;
  }

  if (_error) {
    _el.innerHTML = `
      <div class="sv-header">
        <h2 style="margin:0;font-size:16px;">Scanners & Rules</h2>
        <button class="pv-btn" id="sv-refresh">🔄 Retry</button>
      </div>
      <div class="pv-status pv-status--error" style="padding: 10px; background: rgba(255,0,0,0.1); border-radius: 4px;">
        ✗ Failed to load scanners: ${_error}
      </div>
    `;
    _wireHeader();
    return;
  }

  // Group scanners by category (only non-custom ones)
  const groups = {};
  const customScanners = [];

  for (const s of _scannersData || []) {
    if (s.custom) {
      customScanners.push(s);
      continue;
    }
    const cat = s.category || 'Other';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(s);
  }

  const hasVex = !!(_s.ui && _s.ui.vex_manifest);

  _el.innerHTML = `
    <div class="sv">
      <div class="sv-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <h2 style="margin:0;font-size:16px;">Scanners & Rules</h2>
        <div style="display:flex; align-items:center; gap:8px;">
          <span id="sv-refresh-status" class="pv-status"></span>
          <button class="pv-btn" id="sv-refresh">🔄 Refresh</button>
        </div>
      </div>

      <!-- VEX Manifest Section -->
      <div class="sv-section sv-vex-section">
        <div class="sv-vex-header" id="sv-vex-toggle" style="cursor:pointer; display:flex; justify-content:space-between; align-items:center;">
          <h3 style="margin:0; font-size:13px;">🛡 VEX Manifest</h3>
          <span class="sv-arrow">▼</span>
        </div>
        <div class="sv-vex-body hidden" style="margin-top:10px;">
          ${hasVex ? `
            <div style="display:flex; align-items:center; justify-content:space-between; background:var(--bg-elevated); padding:10px; border-radius:4px; border:1px solid var(--border-default);">
              <span style="font-size:12px;">✅ VEX loaded: ${(_s.ui.vex_manifest.cve_count || 0)} CVEs suppressed</span>
              <div style="display:flex; gap:6px;">
                <button class="pv-btn pv-btn--sm" id="sv-vex-view">View</button>
                <button class="pv-btn pv-btn--sm" id="sv-vex-replace">Replace</button>
                <button class="pv-btn pv-btn--sm" style="color:var(--status-critical);" id="sv-vex-clear">Clear</button>
              </div>
            </div>
          ` : `
            <div style="border:1px dashed var(--border-subtle); padding:20px; text-align:center; border-radius:4px; font-size:12px; color:var(--text-muted);">
              <p style="margin:0 0 10px;">Drop a VEX document (JSON/XML) here to suppress false positives globally.</p>
              <button class="pv-btn" id="sv-vex-browse">Browse Files</button>
              <input type="file" id="sv-vex-file" accept=".json,.xml" style="display:none">
              <div id="sv-vex-status" style="margin-top:8px;" class="pv-status"></div>
            </div>
          `}
        </div>
      </div>

      <!-- Scanner Groups -->
      <div class="sv-groups">
        ${Object.keys(groups).sort().map(cat => `
          <div class="sv-category">
            <h3 class="sv-category-title" style="font-size:12px; text-transform:uppercase; color:var(--text-secondary); margin:16px 0 8px; border-bottom:1px solid var(--border-subtle); padding-bottom:4px;">${esc(cat)}</h3>
            <div class="sv-grid" style="display:grid; grid-template-columns:1fr; gap:10px;">
              ${groups[cat].map(sc => _renderScannerCard(sc)).join('')}
            </div>
          </div>
        `).join('')}
      </div>

      <!-- Custom Plugins Section -->
      <div class="sv-section" style="margin-top:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h3 style="margin:0; font-size:13px;">🔌 Custom Plugins</h3>
          <button class="pv-btn pv-btn--sm" id="sv-add-custom">+ Add Plugin</button>
        </div>
        <div class="sv-custom-list" style="display:flex; flex-direction:column; gap:8px;">
          ${customScanners.length === 0 ? '<div style="font-size:12px; color:var(--text-muted);">No custom plugins registered.</div>' : ''}
          ${customScanners.map(cs => `
            <div class="sv-custom-item" style="background:var(--bg-elevated); padding:8px 12px; border-radius:4px; border:1px solid var(--border-default); display:flex; justify-content:space-between; align-items:center;">
              <div>
                <strong style="font-size:12px;">${esc(cs.name)}</strong>
                <div style="font-size:11px; font-family:var(--font-mono); color:var(--text-secondary);">${esc(cs.executable)}</div>
              </div>
              <div style="display:flex; align-items:center; gap:12px;">
                <label class="pv-check-label">
                  <input type="checkbox" class="sv-custom-toggle pv-check" data-name="${esc(cs.name)}" ${!!_s.scanners[cs.name] ? 'checked' : ''}> Enabled
                </label>
                <button class="pv-list-del sv-custom-remove" data-name="${esc(cs.name)}">×</button>
              </div>
            </div>
          `).join('')}
        </div>
      </div>

      <div class="pv-footer">
        <span class="pv-msg" id="sv-msg">${_dirty ? '<span style="color:var(--status-warning)">⚠️ Unsaved changes</span>' : ''}</span>
        <button class="pv-btn pv-btn--ghost" id="sv-discard">Discard</button>
        <button class="pv-btn pv-btn--primary" id="sv-save">Save Configuration</button>
      </div>

    </div>
  `;

  _wireAll();
}

function _renderScannerCard(sc) {
  const name = sc.name;
  const isInstalled = sc.status === 'installed';
  const enabled = !!_s.scanners[name];
  const cfg = _s.scanner_configs[name] || {};
  const checks = sc.checks || [];

  return `
    <div class="sv-card" data-scanner="${esc(name)}" style="background:var(--bg-input); border:1px solid var(--border-default); border-radius:4px; overflow:hidden;">
      <div class="sv-card-head" style="padding:10px 12px; display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; flex-direction:column; gap:2px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <strong style="font-size:13px;">${esc(sc.display_name || sc.name)}</strong>
            <span class="sv-badge" style="font-size:10px; background:var(--bg-elevated); padding:2px 6px; border-radius:10px;">${esc(sc.category)}</span>
          </div>
          <div style="font-size:11px; color:var(--text-secondary);">${esc(sc.description)}</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          ${isInstalled ? `
            <span style="font-size:11px; color:var(--status-low);">✅ ${esc(sc.version || 'installed')}</span>
            <select class="pv-select sv-strictness" data-name="${esc(name)}" style="${!enabled ? 'opacity:0.5; pointer-events:none;' : ''}">
              ${['Low', 'Medium', 'High'].map(l => `<option ${cfg.strictness === l ? 'selected' : ''}>${l}</option>`).join('')}
            </select>
            <label class="pv-check-label">
              <input type="checkbox" class="pv-check sv-toggle" data-name="${esc(name)}" ${enabled ? 'checked' : ''}>
            </label>
          ` : `
            <span style="font-size:11px; color:var(--status-warning);">⚠️ Not Installed</span>
            <button class="pv-btn pv-btn--sm pv-btn--primary sv-install" data-name="${esc(name)}">Install</button>
          `}
          <button class="pv-btn pv-btn--ghost pv-btn--sm sv-expand" data-name="${esc(name)}" style="padding:0 6px;">▶</button>
        </div>
      </div>
      
      <!-- Inline install terminal -->
      <div class="sv-install-out hidden" id="sv-install-out-${esc(name)}" style="background:#0d1117; font-family:var(--font-mono); font-size:11px; padding:8px; color:#d0d7de; max-height:100px; overflow-y:auto; border-top:1px solid var(--border-default);"></div>

      <!-- Advanced Panel -->
      <div class="sv-panel hidden" id="sv-panel-${esc(name)}" style="background:var(--bg-elevated); padding:12px; border-top:1px solid var(--border-subtle); border-left:3px solid var(--accent-primary); display:flex; flex-direction:column; gap:10px;">
        
        <div class="pv-field">
          <label class="pv-label">Exclude paths (glob)</label>
          <div class="pv-listbox" style="min-height:30px; height:auto;">
            ${(cfg.exclude_paths || []).map((path, idx) => `
              <div class="pv-list-row">
                <span class="pv-list-item">${esc(path)}</span>
                <button class="pv-list-del sv-exclude-del" data-name="${esc(name)}" data-idx="${idx}">×</button>
              </div>
            `).join('')}
          </div>
          <div class="pv-list-add-row" style="margin-top:4px;">
            <input class="pv-input pv-input--mono sv-exclude-input" data-name="${esc(name)}" placeholder="Add glob pattern and press Enter">
          </div>
        </div>

        ${checks.length > 0 ? `
          <div class="pv-field">
            <label class="pv-label">Skip checks</label>
            <div class="pv-multichk" style="max-height:80px; overflow-y:auto; padding:4px; border:1px solid var(--border-subtle); border-radius:3px;">
              ${checks.map(chk => {
                const checked = (cfg.skip_checks || []).includes(chk.id);
                return `
                <label class="pv-check-label" style="width:48%;" title="${esc(chk.label)}">
                  <input type="checkbox" class="pv-check sv-skipchk" data-name="${esc(name)}" value="${esc(chk.id)}" ${checked ? 'checked' : ''}>
                  ${esc(chk.id)}
                </label>`;
              }).join('')}
            </div>
          </div>
        ` : ''}

        ${sc.category === 'Security' ? `
          <div class="pv-row2">
            <label class="pv-check-label">
              <input type="checkbox" class="pv-check sv-cfg-chk" data-name="${esc(name)}" data-key="reachability_enabled" ${cfg.reachability_enabled ? 'checked' : ''}>
              Enable reachability analysis
            </label>
            <div class="pv-field">
              <label class="pv-label">Telemetry source</label>
              <select class="pv-select sv-cfg-sel" data-name="${esc(name)}" data-key="telemetry_source">
                ${['none', 'datadog', 'opentelemetry'].map(o => `<option ${cfg.telemetry_source === o ? 'selected' : ''}>${o}</option>`).join('')}
              </select>
            </div>
          </div>
        ` : ''}

        ${['Security', 'Quality'].includes(sc.category) ? `
          <div class="pv-row2">
            <label class="pv-check-label">
              <input type="checkbox" class="pv-check sv-cfg-chk" data-name="${esc(name)}" data-key="ai_triage_enabled" ${cfg.ai_triage_enabled ? 'checked' : ''}>
              AI false-positive filter
            </label>
            <div class="pv-field">
              <label class="pv-label">Auto-remediation</label>
              <select class="pv-select sv-cfg-sel" data-name="${esc(name)}" data-key="agentic_remediation">
                ${['Off', 'Suggest Only', 'Draft PR'].map(o => `<option ${cfg.agentic_remediation === o ? 'selected' : ''}>${o}</option>`).join('')}
              </select>
            </div>
          </div>
        ` : ''}

        ${Object.keys(cfg).length > 0 ? `
          <div style="display:flex; justify-content:flex-end; margin-top:4px;">
            <button class="pv-btn pv-btn--ghost pv-btn--sm sv-yaml-btn" data-name="${esc(name)}">View Raw YAML Snippet</button>
          </div>
        ` : ''}

      </div>
    </div>
  `;
}

function _wireHeader() {
  _el.querySelector('#sv-refresh')?.addEventListener('click', async () => {
    const statusEl = _el.querySelector('#sv-refresh-status');
    if (statusEl) statusEl.textContent = '⏳';
    try {
      await api.reloadRegistry();
      await _fetchScanners();
    } catch (e) {
      if (statusEl) statusEl.textContent = '✗';
    }
  });
}

function _wireAll() {
  if (!_el) return;

  _wireHeader();

  // VEX
  _el.querySelector('#sv-vex-toggle')?.addEventListener('click', () => {
    const body = _el.querySelector('.sv-vex-body');
    const arrow = _el.querySelector('#sv-vex-toggle .sv-arrow');
    body.classList.toggle('hidden');
    arrow.textContent = body.classList.contains('hidden') ? '▼' : '▲';
  });

  const vexFile = _el.querySelector('#sv-vex-file');
  _el.querySelector('#sv-vex-browse')?.addEventListener('click', () => vexFile?.click());
  _el.querySelector('#sv-vex-replace')?.addEventListener('click', () => vexFile?.click());
  
  vexFile?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const status = _el.querySelector('#sv-vex-status');
    if (status) { status.textContent = '⏳ Uploading...'; status.className = 'pv-status pv-status--info'; }
    try {
      const form = new FormData();
      form.append('file', file);
      // Fallback if endpoint doesn't exist
      const res = await fetch('/api/vex/upload', { method: 'POST', body: form });
      if (res.status === 404) throw new Error("VEX endpoints not yet implemented");
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (!_s.ui) _s.ui = {};
      _s.ui.vex_manifest = { cve_count: data.cve_count || 1 }; // mockup
      _dirty = true;
      _render();
    } catch (err) {
      if (status) { status.textContent = `✗ ${err.message}`; status.className = 'pv-status pv-status--error'; }
      // Show "Not implemented" without crashing
    }
  });

  _el.querySelector('#sv-vex-clear')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/vex', { method: 'DELETE' });
      if (res.status === 404) throw new Error("VEX endpoints not yet implemented");
    } catch (e) {
      console.warn(e.message);
    }
    if (_s.ui && _s.ui.vex_manifest) delete _s.ui.vex_manifest;
    _dirty = true;
    _render();
  });

  // Enable toggles
  _el.querySelectorAll('.sv-toggle, .sv-custom-toggle').forEach(cb => {
    cb.addEventListener('change', () => {
      const name = cb.dataset.name;
      _s.scanners[name] = cb.checked;
      _dirty = true;
      _render();
    });
  });

  // Strictness
  _el.querySelectorAll('.sv-strictness').forEach(sel => {
    sel.addEventListener('change', () => {
      _ensureCfg(sel.dataset.name).strictness = sel.value;
      _dirty = true;
      _render();
    });
  });

  // Expand
  _el.querySelectorAll('.sv-expand').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      const panel = _el.querySelector(`#sv-panel-${CSS.escape(name)}`);
      panel?.classList.toggle('hidden');
      btn.textContent = panel?.classList.contains('hidden') ? '▶' : '▼';
    });
  });

  // Exclude glob list
  _el.querySelectorAll('.sv-exclude-input').forEach(inp => {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const val = inp.value.trim();
        if (val) {
          const cfg = _ensureCfg(inp.dataset.name);
          if (!cfg.exclude_paths) cfg.exclude_paths = [];
          if (!cfg.exclude_paths.includes(val)) cfg.exclude_paths.push(val);
          _dirty = true;
          _render();
        }
      }
    });
  });
  _el.querySelectorAll('.sv-exclude-del').forEach(btn => {
    btn.addEventListener('click', () => {
      const cfg = _ensureCfg(btn.dataset.name);
      if (cfg.exclude_paths) {
        cfg.exclude_paths.splice(parseInt(btn.dataset.idx), 1);
        _dirty = true;
        _render();
      }
    });
  });

  // Skip checks
  _el.querySelectorAll('.sv-skipchk').forEach(cb => {
    cb.addEventListener('change', () => {
      const name = cb.dataset.name;
      const chk = cb.value;
      const cfg = _ensureCfg(name);
      if (!cfg.skip_checks) cfg.skip_checks = [];
      if (cb.checked) {
        if (!cfg.skip_checks.includes(chk)) cfg.skip_checks.push(chk);
      } else {
        cfg.skip_checks = cfg.skip_checks.filter(c => c !== chk);
      }
      _dirty = true;
      _render();
    });
  });

  // Config checkboxes & selects
  _el.querySelectorAll('.sv-cfg-chk').forEach(cb => {
    cb.addEventListener('change', () => {
      _ensureCfg(cb.dataset.name)[cb.dataset.key] = cb.checked;
      _dirty = true;
      _render();
    });
  });
  _el.querySelectorAll('.sv-cfg-sel').forEach(sel => {
    sel.addEventListener('change', () => {
      _ensureCfg(sel.dataset.name)[sel.dataset.key] = sel.value;
      _dirty = true;
      _render();
    });
  });

  // Install
  _el.querySelectorAll('.sv-install').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      btn.disabled = true;
      btn.textContent = 'Installing...';
      const out = _el.querySelector(`#sv-install-out-${CSS.escape(name)}`);
      out.classList.remove('hidden');
      out.innerHTML = '';
      
      try {
        const res = await fetch('/api/scanners/install', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name })
        });
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const lines = decoder.decode(value).split('\n').filter(Boolean);
          for (const line of lines) {
            try {
              const data = JSON.parse(line);
              out.innerHTML += `<div>${esc(data.line)}</div>`;
              out.scrollTop = out.scrollHeight;
              if (data.done) {
                if (data.status === 'ok') {
                  out.innerHTML += `<div style="color:var(--status-low);">✓ Install complete</div>`;
                  // Update scanner data locally to reflect installed
                  const sc = _scannersData.find(s => s.name === name);
                  if (sc) { sc.status = 'installed'; sc.version = 'latest'; }
                  setTimeout(() => _render(), 1000);
                } else {
                  out.innerHTML += `<div style="color:var(--status-critical);">✗ Install failed</div>`;
                  btn.disabled = false;
                  btn.textContent = 'Retry Install';
                }
              }
            } catch(e) {}
          }
        }
      } catch (e) {
        out.innerHTML += `<div style="color:var(--status-critical);">✗ Network error</div>`;
        btn.disabled = false;
        btn.textContent = 'Retry Install';
      }
    });
  });

  // Custom remove
  _el.querySelectorAll('.sv-custom-remove').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      try {
        const res = await fetch(`/api/scanners/custom/${encodeURIComponent(name)}`, { method: 'DELETE' });
        if (res.status === 404) throw new Error("Endpoint missing");
      } catch (e) {
        // Fallback local remove
        if (_s.ui && _s.ui.custom_scanners && _s.ui.custom_scanners[name]) {
          delete _s.ui.custom_scanners[name];
        }
      }
      delete _s.scanners[name];
      _fetchScanners(); // Re-fetch to get updated list
    });
  });

  // Custom add
  _el.querySelector('#sv-add-custom')?.addEventListener('click', () => {
    const name = prompt("Enter custom plugin name:");
    if (!name) return;
    const exe = prompt("Enter executable path:");
    if (!exe) return;
    
    fetch('/api/scanners/custom', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name, executable: exe, output_pattern: '' })
    }).then(res => {
      _fetchScanners();
    }).catch(e => alert("Failed to add custom plugin: " + e));
  });

  // YAML View
  _el.querySelectorAll('.sv-yaml-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      const cfg = _s.scanner_configs[name] || {};
      const yaml = `scanners:\n  ${name}: ${!!_s.scanners[name]}\nscanner_configs:\n  ${name}:\n` + 
                   Object.entries(cfg).map(([k,v]) => `    ${k}: ${Array.isArray(v) ? JSON.stringify(v) : v}`).join('\n');
      
      const overlay = document.getElementById('modal-overlay');
      const container = document.getElementById('modal-container');
      if (overlay && container) {
        container.innerHTML = `
          <h3 style="margin:0 0 12px">📄 YAML Snippet: ${esc(name)}</h3>
          <pre id="yaml-snippet" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;font-family:var(--font-mono);font-size:0.82rem;color:#d0d7de;white-space:pre-wrap;">${esc(yaml)}</pre>
          <div style="display:flex;justify-content:flex-end;margin-top:12px;gap:8px;">
            <button class="pv-btn" onclick="navigator.clipboard.writeText(document.getElementById('yaml-snippet').textContent)">📋 Copy</button>
            <button class="pv-btn pv-btn--primary" onclick="document.getElementById('modal-overlay').classList.add('hidden');document.getElementById('modal-container').classList.add('hidden')">Close</button>
          </div>
        `;
        overlay.classList.remove('hidden');
        container.classList.remove('hidden');
      } else {
        alert(yaml); // fallback if modal elements missing
      }
    });
  });

  // Footer
  _el.querySelector('#sv-save')?.addEventListener('click', async () => {
    const msg = _el.querySelector('#sv-msg');
    if (msg) msg.innerHTML = '⏳ Saving...';
    try {
      await _onSave({..._s});
      _dirty = false;
      if (msg) msg.innerHTML = '<span style="color:var(--status-low)">✓ Saved</span>';
      setTimeout(() => _render(), 2000);
    } catch (e) {
      if (msg) msg.innerHTML = `<span style="color:var(--status-critical)">✗ ${e.message}</span>`;
    }
  });

  _el.querySelector('#sv-discard')?.addEventListener('click', () => {
    api.getSettings().then(fresh => {
      _s = deepClone(fresh);
      _dirty = false;
      _render();
    });
  });
}

function _ensureCfg(name) {
  if (!_s.scanner_configs[name]) _s.scanner_configs[name] = {};
  return _s.scanner_configs[name];
}

function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
