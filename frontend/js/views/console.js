// frontend/js/views/console.js
// Audit Console V3 — Floating real-time overlay.
// Self-contained: mounts a <div class="audit-console"> into document.body.
// Consumes the global store (logs, status, scanners) via store.subscribe().
// Keyboard-first, draggable, minimizable, resizable.

import * as store  from '../store.js';
import * as api    from '../api.js';

// ── Constants ────────────────────────────────────────────────────────────────
const LS_KEY  = 'nexus.console.v3';
const AI_ENABLED = () => store.get('settings')?.ai_enabled === true;

// Regex: matches "/abs/path/to/file.py:42" or "relative/path.py:42"
const FILE_LINE_RE = /((?:\.{0,2}\/|[A-Za-z]:\\|\/)[^\s:'"]+\.[a-zA-Z]{1,6}):(\d+)/g;

// Tag → CSS class mapping (fallback: scanner name)
const TAG_CLASS = {
  'SYSTEM':       'system',
  'CORE':         'core',
  'ENGINES':      'engines',
  'PRE-FLIGHT':   'preflight',
  'PREFLIGHT':    'preflight',
  'ORCHESTRATOR': 'orchestrator',
  'DEBUG':        'debug',
  'FILES':        'files',
  'INFO':         'info',
  'SUCCESS':      'success',
  'ERROR':        'error',
  'WARNING':      'warn',
  'SKIPPED':      'skipped',
};

// Scanner chip state from orchestrator log keywords
const CHIP_ICONS = { running:'⚡', clean:'🛡', error:'✗', skipped:'⊘', idle:'○' };

// ── Module state ─────────────────────────────────────────────────────────────
let _el      = null;   // root .audit-console DOM node
let _pane    = null;   // .con-pane scrollable area
let _focused = -1;     // currently keyboard-focused log line index
let _lines   = [];     // rendered log line elements (NodeList snapshot)
let _drag    = null;   // drag state { startX, startY, origRight, origBottom }
let _chipMap = {};     // { scannerName: { state, findings } }
let _visible = false;
let _minimized = false;
let _editorScheme = '';  // e.g. "vscode://file/{path}:{line}"

// ── Public API ────────────────────────────────────────────────────────────────
export function initConsole() {
  _loadPrefs();
  _build();
  _wireStore();
  // Start hidden; the Run button / hotkey reveals it
  _setVisible(false);
}

export function showConsole() { _setVisible(true); }
export function hideConsole() { _setVisible(false); }
export function toggleConsole() { _setVisible(!_visible); }
export function focusConsole() { if (_pane) _pane.focus(); }

// ── Build DOM ─────────────────────────────────────────────────────────────────
function _build() {
  _el = document.createElement('div');
  _el.className = 'audit-console';
  _el.setAttribute('role', 'region');
  _el.setAttribute('aria-label', 'Audit Console');
  _el.id = 'audit-console';

  _el.innerHTML = `
<div class="con-header" id="con-header">
  <span class="con-title" id="con-title">Audit Console</span>
  <span class="con-shortcut-hint">Ctrl+Shift+A</span>
  <button class="con-btn con-btn--copy" id="con-copy" title="Copy all logs">⎘ Copy</button>
  <button class="con-btn con-btn--min"  id="con-min"  title="Minimize / expand">▂</button>
  <button class="con-btn con-btn--close" id="con-close" title="Close console">✕ Close</button>
</div>
<div class="con-status-bar" id="con-status-bar">
  <span class="con-status-label">Scan Status:</span>
  <div class="con-scanner-chips" id="con-chips"></div>
</div>
<div class="con-pane" id="con-pane" tabindex="0" aria-live="polite" aria-label="Audit log output"></div>
  `;

  document.body.appendChild(_el);
  _pane = _el.querySelector('#con-pane');

  const fab = document.createElement('button');
  fab.id = 'con-fab';
  fab.className = 'con-fab hidden';
  fab.title = 'Open Audit Console (Ctrl+Shift+A)';
  fab.innerHTML = '📝';
  document.body.appendChild(fab);
  fab.addEventListener('click', () => showConsole());

  _wireDrag();
  _wirePaneKeys();
  _el.querySelector('#con-copy').addEventListener('click',  _copyLogs);
  _el.querySelector('#con-min').addEventListener('click',   _toggleMinimized);
  _el.querySelector('#con-close').addEventListener('click',  () => _setVisible(false));
}

// ── Store subscriptions ──────────────────────────────────────────────────────
function _wireStore() {
  store.subscribe('logs',     _renderLogs);
  store.subscribe('status',   _onStatus);
  store.subscribe('settings', _onSettings);
}

function _onSettings() {
  const s = store.get('settings') || {};
  _editorScheme = s.editor_url_scheme || s.ui?.editor_url_scheme || '';
}

function _onStatus() {
  const st = store.get('status') || {};
  const titleEl = _el?.querySelector('#con-title');
  if (!titleEl) return;

  const stateLabels = {
    running:   'Running Audit…',
    completed: 'Audit Complete',
    failed:    'Audit Failed',
    cancelled: 'Audit Cancelled',
    idle:      'Audit Console',
  };
  titleEl.textContent = stateLabels[st.state] || 'Audit Console';

  // Auto-show when a run starts
  if (st.state === 'running') _setVisible(true);
}

// ── Log rendering ─────────────────────────────────────────────────────────────
function _renderLogs() {
  if (!_pane) return;
  const logs = store.get('logs') || [];
  if (!logs.length) {
    _pane.innerHTML = '<div class="con-empty">No logs yet — click ▶ Run to start an audit.</div>';
    _chipMap = {};
    _refreshChips();
    return;
  }

  const wasBottom = _pane.scrollHeight - _pane.scrollTop - _pane.clientHeight < 40;
  _focused = -1;

  _pane.innerHTML = logs.map((entry, i) => _buildLine(entry, i)).join('');

  // Wire AI buttons
  _pane.querySelectorAll('.con-ai-btn[data-idx]').forEach(btn => {
    btn.addEventListener('click', () => _analyzeError(parseInt(btn.dataset.idx)));
  });

  // Wire file path links
  _pane.querySelectorAll('.con-link[data-path]').forEach(a => {
    a.addEventListener('click', () => _openLink(a.dataset.path, a.dataset.line));
  });

  _lines = [..._pane.querySelectorAll('.con-line')];
  _refreshChips();

  if (wasBottom) _pane.scrollTop = _pane.scrollHeight;
}

function _buildLine(entry, i) {
  const ts      = _fmtTime(entry.timestamp || new Date().toISOString());
  const level   = (entry.level || 'info').toLowerCase();
  const rawMsg  = entry.message || '';
  const isError = level === 'error';

  const body    = _colorizeMessage(rawMsg, i);
  const aiBtn   = isError && AI_ENABLED()
    ? `<button class="con-ai-btn" data-idx="${i}" title="Analyze with AI (Ctrl+Enter)">🤖</button>`
    : '';

  return `
<div class="con-line" data-idx="${i}" data-level="${level}" data-raw="${_esc(rawMsg)}">
  <span class="con-line-ts">${ts}</span>
  <span class="con-line-body">${body}</span>
  <span class="con-line-meta">${aiBtn}</span>
</div>`;
}

// ── Message colorization ─────────────────────────────────────────────────────
function _colorizeMessage(raw, lineIdx) {
  // Extract leading [TAG] if present
  let html = raw;
  html = html.replace(/^\[([^\]]+)\]/, (_, tag) => {
    const key   = tag.toUpperCase();
    const cls   = TAG_CLASS[key] || _slugify(tag);
    // Track scanner chip state from tags
    _updateChipFromTag(tag, raw);
    return `<span class="con-tag con-tag--${cls}">[${_esc(tag)}]</span>`;
  });

  // Highlight PASS / NO FINDINGS / CLEAN / SUCCESS
  html = html.replace(/\b(PASS|CLEAN|SUCCESS|NO FINDINGS)\b/g,
    m => `<span class="con-pass">${m}</span>`);

  // Highlight FAIL / ERROR / TIMEOUT
  html = html.replace(/\b(FAIL|FAILED|TIMEOUT|TIMED OUT)\b/g,
    m => `<span class="con-fail">${m}</span>`);

  // Highlight numbers in parentheses: "(0 findings)" "(3)"
  html = html.replace(/\((\d+[^)]*)\)/g,
    (_, inner) => `(<span class="con-num">${inner}</span>)`);

  // Highlight bare numbers prefixed by ":" — line numbers in scanners
  // But avoid double-processing file paths. We do file paths last.
  html = _linkifyPaths(html, raw);

  return html;
}

function _linkifyPaths(html, rawMsg) {
  // We operate on the raw message so we don't corrupt HTML tags above
  // Strategy: find all matches in rawMsg, replace those same substrings in html
  let offset = 0;
  let result = html;
  FILE_LINE_RE.lastIndex = 0;
  let match;
  const replacements = [];
  while ((match = FILE_LINE_RE.exec(rawMsg)) !== null) {
    replacements.push({ full: match[0], path: match[1], line: match[2] });
  }
  // Replace all occurrences in the html string (which may have extra tags around)
  for (const { full, path, line } of replacements) {
    const escapedFull = _esc(full);
    const anchor = `<span class="con-link" data-path="${_esc(path)}" data-line="${_esc(line)}" tabindex="-1" title="${_esc(path)}:${line}">${escapedFull}</span>`;
    // Replace only the first un-processed occurrence
    result = result.replace(escapedFull, anchor);
  }
  return result;
}

// ── Scanner chip state ────────────────────────────────────────────────────────
function _updateChipFromTag(tag, msg) {
  const lowerTag = tag.toLowerCase();
  // Ignore known system tags
  if (['system','core','engines','orchestrator','debug','files','info',
       'success','error','pre-flight','preflight','skipped','warning'].includes(lowerTag)) return;

  // It's likely a scanner name
  if (!_chipMap[lowerTag]) _chipMap[lowerTag] = { state: 'running', findings: 0 };
  const chip = _chipMap[lowerTag];

  if (/scan complete.*SUCCESS/i.test(msg) || /CLEAN/i.test(msg)) {
    chip.state = 'clean';
    const m = msg.match(/(\d+)\s+findings?/i);
    chip.findings = m ? parseInt(m[1]) : 0;
  } else if (/error|fail|timeout/i.test(msg)) {
    chip.state = 'error';
  }
}

function _refreshChips() {
  const el = _el?.querySelector('#con-chips');
  if (!el) return;
  const scanners = store.get('scanners') || {};
  // Merge registry scanners into chipMap for those not yet seen in logs
  for (const name of Object.keys(scanners)) {
    if (!_chipMap[name]) _chipMap[name] = { state: 'idle', findings: 0 };
  }
  if (!Object.keys(_chipMap).length) {
    el.innerHTML = '<span style="color:var(--con-text-dim);font-size:10px;">—</span>';
    return;
  }
  el.innerHTML = Object.entries(_chipMap).map(([name, { state, findings }]) => {
    const icon  = CHIP_ICONS[state] || '●';
    const label = state === 'clean'
      ? `(<span class="con-pass">CLEAN</span>)`
      : state === 'error'
        ? `(<span class="con-fail">ERROR</span>)`
        : state === 'running'
          ? `(<span style="color:var(--con-text-info)">RUNNING</span>)`
          : state === 'skipped'
            ? `(<span class="con-warn-t">SKIPPED</span>)`
            : '';
    return `<span class="con-chip is-${state}">
      <span class="con-chip-icon">${icon}</span>
      <span class="con-chip-name">${_esc(name)}</span>
      <span class="con-chip-state"> ${label}</span>
    </span>`;
  }).join('');
}

// ── Keyboard navigation ───────────────────────────────────────────────────────
function _wirePaneKeys() {
  _pane.addEventListener('keydown', e => {
    if (!_lines.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _moveFocus(1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _moveFocus(-1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        // Ctrl+Enter → AI analyze focused error line
        if (_focused >= 0) _analyzeError(_focused);
      } else {
        _activateLine(_focused);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      _pane.blur();
      _focused = -1;
      _lines.forEach(l => l.classList.remove('is-focused'));
    }
  });
}

function _moveFocus(delta) {
  const next = Math.max(0, Math.min(_lines.length - 1, _focused + delta));
  if (_focused >= 0 && _lines[_focused]) _lines[_focused].classList.remove('is-focused');
  _focused = next;
  const el = _lines[_focused];
  if (el) {
    el.classList.add('is-focused');
    el.scrollIntoView({ block: 'nearest' });
  }
}

function _activateLine(idx) {
  if (idx < 0 || !_lines[idx]) return;
  const el = _lines[idx];
  // If the line has a file path link, trigger it
  const link = el.querySelector('.con-link[data-path]');
  if (link) {
    _openLink(link.dataset.path, link.dataset.line);
    return;
  }
  // Else copy the raw text
  const raw = el.dataset.raw || el.textContent;
  _copyText(raw);
  _flashLine(el);
}

// ── File path open / copy ─────────────────────────────────────────────────────
function _openLink(path, line) {
  const full = `${path}:${line}`;
  if (_editorScheme) {
    const url = _editorScheme
      .replace('{path}', path)
      .replace('{line}', line);
    window.location.href = url;
  } else {
    _copyText(full);
    // Show a tiny tooltip
    _showToast(`📋 Copied: ${full}`);
  }
}

// ── AI Diagnostics ────────────────────────────────────────────────────────────
async function _analyzeError(lineIdx) {
  const logs = store.get('logs') || [];
  const entry = logs[lineIdx];
  if (!entry) return;

  // Find the AI button on this line and mark loading
  const lineEl = _lines[lineIdx];
  const btn = lineEl?.querySelector('.con-ai-btn');
  if (btn) { btn.classList.add('is-loading'); btn.textContent = '⏳'; }

  // Gather surrounding context (up to 5 lines before)
  const contextLogs = logs
    .slice(Math.max(0, lineIdx - 5), lineIdx)
    .map(e => e.message || '');

  // Extract scanner name from message e.g. "[vulture] error..."
  const scannerMatch = (entry.message || '').match(/\[([a-z0-9_-]+)\]/i);
  const scannerName  = scannerMatch ? scannerMatch[1].toLowerCase() : 'unknown';

  try {
    const res  = await fetch('/api/ai/diagnose-scanner-error', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        scanner_name:  scannerName,
        error_message: entry.message || '',
        context_logs:  contextLogs,
      }),
    });
    const data = await res.json();
    const analysis = data.analysis || data.error || 'No analysis available.';

    // Inject AI result as a new log line directly after the error
    _injectAiLine(lineIdx, analysis);
  } catch (err) {
    _injectAiLine(lineIdx, `Could not reach AI endpoint: ${err.message}`);
  } finally {
    if (btn) { btn.classList.remove('is-loading'); btn.textContent = '🤖'; }
  }
}

function _injectAiLine(afterIdx, text) {
  if (!_lines[afterIdx]) return;
  const sibling = _lines[afterIdx].nextSibling;
  const div = document.createElement('div');
  div.className = 'con-line is-ai-analysis';
  div.innerHTML = `
    <span class="con-line-ts"></span>
    <span class="con-line-body">🤖 ${_esc(text)}</span>
    <span class="con-line-meta"></span>`;
  _pane.insertBefore(div, sibling);
  // Refresh lines array
  _lines = [..._pane.querySelectorAll('.con-line')];
}

// ── Dragging ──────────────────────────────────────────────────────────────────
function _wireDrag() {
  const header = _el.querySelector('#con-header');
  header.addEventListener('mousedown', e => {
    if (e.target.classList.contains('con-btn')) return;
    const rect = _el.getBoundingClientRect();
    _drag = {
      startX:   e.clientX,
      startY:   e.clientY,
      origLeft: rect.left,
      origTop:  rect.top,
    };
    
    // Switch to absolute left/top anchoring to avoid conflicts with resize handles
    _el.style.right = 'auto';
    _el.style.bottom = 'auto';
    _el.style.left = `${rect.left}px`;
    _el.style.top = `${rect.top}px`;
    
    document.addEventListener('mousemove', _onDragMove);
    document.addEventListener('mouseup',   _onDragEnd, { once: true });
    e.preventDefault();
  });
}

function _onDragMove(e) {
  if (!_drag) return;
  const dx = e.clientX - _drag.startX;
  const dy = e.clientY - _drag.startY;
  
  // Bound to screen edges
  const maxLeft = window.innerWidth - _el.offsetWidth;
  const maxTop  = window.innerHeight - _el.offsetHeight;
  
  const newLeft = Math.max(0, Math.min(maxLeft, _drag.origLeft + dx));
  const newTop  = Math.max(0, Math.min(maxTop, _drag.origTop + dy));
  
  _el.style.left = `${newLeft}px`;
  _el.style.top  = `${newTop}px`;
}

function _onDragEnd() {
  _drag = null;
  document.removeEventListener('mousemove', _onDragMove);
  _savePrefs();
}

// ── Minimize / visibility ─────────────────────────────────────────────────────
function _toggleMinimized() {
  _minimized = !_minimized;
  _el.classList.toggle('is-minimized', _minimized);
  _el.querySelector('#con-min').textContent = _minimized ? '▲' : '▂';
  _savePrefs();
}

function _setVisible(v) {
  _visible = v;
  _el.style.display = v ? 'flex' : 'none';
  const fab = document.getElementById('con-fab');
  if (fab) fab.classList.toggle('hidden', v);
  if (v && _minimized) {
    _minimized = false;
    _el.classList.remove('is-minimized');
    _el.querySelector('#con-min').textContent = '▂';
  }
  _savePrefs();
}

// ── Copy logs ─────────────────────────────────────────────────────────────────
function _copyLogs() {
  const logs = store.get('logs') || [];
  const text = logs.map(e => `${_fmtTime(e.timestamp)} [${e.level}] ${e.message}`).join('\n');
  _copyText(text);
  _showToast('📋 Logs copied to clipboard');
}

// ── Global hotkey ─────────────────────────────────────────────────────────────
// Moved to main.js per spec

// ── Persistence ───────────────────────────────────────────────────────────────
function _savePrefs() {
  try {
    const rect = _el.getBoundingClientRect();
    localStorage.setItem(LS_KEY, JSON.stringify({
      left:      _el.style.left,
      top:       _el.style.top,
      right:     _el.style.right,
      bottom:    _el.style.bottom,
      width:     _el.offsetWidth + 'px',
      height:    _el.offsetHeight + 'px',
      minimized: _minimized,
      visible:   _visible,
    }));
  } catch (_) {}
}

function _loadPrefs() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const p = JSON.parse(raw);
    if (p.right)     { /* applied after build */ }
    // We apply after _build() — store for post-build
    _pendingPrefs = p;
  } catch (_) {}
}

let _pendingPrefs = null;
const _origBuild = _build;

// Wrap build to apply prefs after DOM exists
function _applyPrefs() {
  const p = _pendingPrefs;
  if (!p || !_el) {
    // Default initial position if no prefs
    _el.style.right = '24px';
    _el.style.bottom = '24px';
    _el.style.width = '600px';
    _el.style.height = '400px';
    return;
  }
  
  if (p.left && p.left !== 'auto') { 
    _el.style.left = p.left; 
    _el.style.right = 'auto'; 
  } else if (p.right) {
    _el.style.right = p.right;
    _el.style.left = 'auto';
  }
  
  if (p.top && p.top !== 'auto') { 
    _el.style.top = p.top; 
    _el.style.bottom = 'auto'; 
  } else if (p.bottom) {
    _el.style.bottom = p.bottom;
    _el.style.top = 'auto';
  }

  if (p.width && parseInt(p.width) > 0)   _el.style.width  = p.width;
  if (p.height && parseInt(p.height) > 0) _el.style.height = p.height;
  
  _minimized = !!p.minimized;
  _el.classList.toggle('is-minimized', _minimized);
  _el.querySelector('#con-min').textContent = _minimized ? '▲' : '▂';
  // Don't auto-restore visible — only show when run starts
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toTimeString().slice(0,8);
  } catch (_) { return '--:--:--'; }
}

function _esc(s) {
  return String(s||'')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function _slugify(s) { return s.toLowerCase().replace(/[^a-z0-9]/g,'-'); }

function _copyText(text) {
  navigator.clipboard?.writeText(text).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  });
}

function _flashLine(el) {
  el.style.transition = 'background .05s';
  el.style.background = 'rgba(88,166,255,.25)';
  setTimeout(() => { el.style.background = ''; }, 300);
}

function _showToast(msg) {
  let t = document.getElementById('con-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'con-toast';
    Object.assign(t.style, {
      position:'fixed', bottom:'80px', right:'24px', zIndex:'10000',
      background:'#161b22', color:'#d0d7de', border:'1px solid #30363d',
      borderRadius:'6px', padding:'6px 12px', fontSize:'11px',
      fontFamily:'var(--con-font)', boxShadow:'0 4px 12px rgba(0,0,0,.5)',
      transition:'opacity .3s', pointerEvents:'none',
    });
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.opacity = '0'; }, 2500);
}

// Re-export internal init hook for main.js
export { _applyPrefs as _applyConsolePrefs };
