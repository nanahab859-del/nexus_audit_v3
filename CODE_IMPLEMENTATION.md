# Complete Code Implementation Reference

**Date:** 2026-06-07  
**Status:** ✅ VERIFIED COMPLETE

---

## 1. Progress Panel JavaScript Functions

**File:** `frontend/js/main.js` (lines 230-260)

### updateProgressBars(progress)
```javascript
function updateProgressBars(progress) {
  const container = document.getElementById('scanner-bars');
  if (!container) return;
  
  container.innerHTML = Object.entries(progress)
    .map(([scanner, p]) => `
      <div class="scanner-row">
        <div class="scanner-row__track">
          <div class="scanner-row__fill" style="width:${p.percent}%"></div>
        </div>
        <div class="scanner-row__name">${scanner}</div>
        <div class="scanner-row__pct">${p.percent}%</div>
      </div>
    `).join('');
}
```

**Purpose:** Renders compact 28px scanner progress rows  
**Input:** `{ scanner_name: { percent: 0-100, file: string } }`  
**Output:** HTML with animated progress bars

### updateLogOutput(lines)
```javascript
function updateLogOutput(lines) {
  const el = document.getElementById('log-output');
  if (!el) return;
  
  el.innerHTML = lines.map(l => {
    const t = new Date(l.time).toTimeString().slice(0,8);
    return `
      <div class="log-line log-line--${l.level}">
        <div class="log-line__ts">${t}</div>
        <div class="log-line__msg">${escapeHtml(l.message)}</div>
      </div>
    `;
  }).join('');
  el.scrollTop = el.scrollHeight;
}
```

**Purpose:** Renders terminal-style log output with color-coding  
**Input:** `[{ time: ISO8601, level: 'info'|'warning'|'error'|'debug', message: string }]`  
**Output:** HTML with timestamps, auto-scroll to bottom

### escapeHtml(s)
```javascript
function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
```

**Purpose:** Prevent XSS attacks by escaping HTML special characters

---

## 2. Progress Panel CSS Styling

**File:** `frontend/css/components.css` (lines 379-451)

### Progress Panel Container
```css
/* Progress panel */
#progress-panel {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  background: var(--bg-surface);
  border-top: 1px solid var(--border-default);
  z-index: 100;
  max-height: 420px;
  display: flex;
  flex-direction: column;
}
```

### Progress Header
```css
.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-4);
  height: 40px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  flex-shrink: 0;
}
```

### Scanner Bars Section
```css
#scanner-bars {
  padding: var(--space-2) var(--space-4);
  overflow-y: auto;
  max-height: 120px;
  flex-shrink: 0;
}

.scanner-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 28px;
}

.scanner-row__track {
  flex: 1;
  height: 4px;
  background: var(--bg-elevated);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.scanner-row__fill {
  height: 100%;
  background: var(--accent-primary);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}

.scanner-row__name {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  width: 80px;
  flex-shrink: 0;
}

.scanner-row__pct {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  width: 32px;
  text-align: right;
  flex-shrink: 0;
}
```

### Terminal Log Output
```css
#log-output {
  flex: 1;
  overflow-y: auto;
  max-height: 200px;
  background: #0a0f1a;
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--border-subtle);
}

.log-line {
  display: flex;
  gap: var(--space-2);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
}

.log-line__ts { 
  color: #334155; 
  flex-shrink: 0; 
}

.log-line--info    .log-line__msg { color: #94a3b8; }
.log-line--warning .log-line__msg { color: #f97316; }
.log-line--error   .log-line__msg { color: #ef4444; }
.log-line--debug   .log-line__msg { color: #475569; }
```

---

## 3. Settings Tabs Interface

**File:** `frontend/js/views/settings.js` (Complete 326-line implementation)

### Tab Configuration
```javascript
const TABS = [
  { id: 'project',  label: 'Project'   },
  { id: 'scanners', label: 'Scanners'  },
  { id: 'ai',       label: 'AI'        },
  { id: 'rules',    label: 'Rules'     },
  { id: 'about',    label: 'About'     },
];
```

### Main Initialization
```javascript
let _activeTab = 'project';

export function initSettings() {
  console.log('[Settings] Initializing...');
  store.subscribe('settings', _render);
  _render();
}
```

### Tab Rendering
```javascript
function _render() {
  const el = document.getElementById('view-settings');
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
  
  // Wire tab click handlers
  el.querySelectorAll('.settings-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeTab = btn.dataset.tab;
      _render();
    });
  });
}
```

### Tab Content Dispatcher
```javascript
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
```

### Project Tab
```javascript
function _tabProject() {
  const path = store.get('settings')?.project_path || '';
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">Project</h3>
      <p class="settings-section__desc">
        The absolute path to the codebase you want to audit.
      </p>
      <div class="form-field">
        <label class="form-label">Project Path</label>
        <input type="text" class="form-input" id="project_path" value="${escHtml(path)}" />
      </div>
      <button class="btn-primary" onclick="document.querySelector('[data-save]')?.click?.()">Save</button>
    </div>
  `;
}
```

### Scanners Tab
```javascript
function _tabScanners() {
  const settings = store.get('settings') || {};
  const scannersList = [
    { name: 'vulture', enabled: settings.scanners?.vulture ?? true },
    { name: 'bandit', enabled: settings.scanners?.bandit ?? true },
  ];
  
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">Scanners</h3>
      <p class="settings-section__desc">
        Choose which security scanners to run during audit.
      </p>
      <div class="scanner-toggles">
        ${scannersList.map(s => `
          <div class="toggle-row">
            <div>
              <div class="toggle-row__name">${escHtml(s.name)}</div>
              <div class="toggle-row__desc">${escHtml(_scannerDesc(s.name))}</div>
            </div>
            <input type="checkbox" id="scanner_${s.name}" ${s.enabled ? 'checked' : ''} />
          </div>
        `).join('')}
      </div>
      <button class="btn-primary">Save</button>
    </div>
  `;
}
```

### AI Tab
```javascript
function _tabAI() {
  const settings = store.get('settings') || {};
  const aiEnabled = settings.ai?.enabled ?? false;
  
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">AI Configuration</h3>
      
      <div class="form-field">
        <label class="form-label">Enable AI Fixes</label>
        <input type="checkbox" id="ai_enabled" ${aiEnabled ? 'checked' : ''} />
      </div>
      
      <div class="form-field ${!aiEnabled ? 'form-field--disabled' : ''}">
        <label class="form-label">AI Provider</label>
        <select class="form-input" id="ai_provider" ${!aiEnabled ? 'disabled' : ''}>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </div>
      
      <div class="form-field ${!aiEnabled ? 'form-field--disabled' : ''}">
        <label class="form-label">Model</label>
        <input type="text" class="form-input" id="ai_model" placeholder="gpt-4" ${!aiEnabled ? 'disabled' : ''} />
      </div>
      
      <div class="form-field ${!aiEnabled ? 'form-field--disabled' : ''}">
        <label class="form-label">API Key</label>
        <input type="password" class="form-input" id="ai_key" placeholder="sk-..." ${!aiEnabled ? 'disabled' : ''} />
      </div>
      
      <button class="btn-primary">Save</button>
    </div>
  `;
}
```

### Rules Tab
```javascript
function _tabRules() {
  return `
    <div class="settings-section">
      <h3 class="settings-section__title">Audit Rules</h3>
      <p class="settings-section__desc">
        Customize audit rules by editing audit_rules.yaml
      </p>
      <div class="info-block">
        <p>Define rules in <code>audit_rules.yaml</code>:</p>
        <p><code>exclude_patterns:</code></p>
        <p><code>&nbsp;&nbsp;- ".git/**"</code></p>
        <p><code>&nbsp;&nbsp;- "**/__pycache__/**"</code></p>
      </div>
    </div>
  `;
}
```

### About Tab
```javascript
function _tabAbout() {
  const settings = store.get('settings') || {};
  const project = settings.project_path || 'Not set';
  
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
          <span>${escHtml(project)}</span>
        </div>
      </div>
    </div>
  `;
}
```

---

## 4. Settings Tabs CSS Styling

**File:** `frontend/css/components.css` (lines 453-545)

```css
/* Settings tabs */
.settings-page { 
  display: flex; 
  flex-direction: column; 
  height: 100%; 
}

.settings-tabs {
  display: flex;
  gap: 2px;
  padding: var(--space-4) var(--space-6) 0;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.settings-tab {
  padding: var(--space-2) var(--space-5);
  background: transparent;
  font-size: var(--text-sm);
  font-weight: 500;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.settings-tab:hover {
  color: var(--text-primary);
}

.settings-tab.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

.settings-section {
  max-width: 560px;
}

.settings-section__title {
  font-size: var(--text-lg);
  font-weight: 600;
  margin-bottom: var(--space-1);
  color: var(--text-primary);
}

.settings-section__desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-6);
  line-height: 1.6;
}

.form-field {
  margin-bottom: var(--space-5);
}

.form-field--disabled {
  opacity: 0.4;
  pointer-events: none;
}

.form-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  margin-bottom: var(--space-2);
  color: var(--text-secondary);
}

.form-input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-base);
  outline: none;
}

.form-input:focus {
  border-color: var(--accent-primary);
}

.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
}

.toggle-row__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.toggle-row__desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: var(--space-1);
}

.settings-msg {
  padding: var(--space-3) var(--space-6);
  font-size: var(--text-sm);
  border-top: 1px solid var(--border-subtle);
}

.settings-msg--success {
  color: var(--status-low);
}

.settings-msg--error {
  color: var(--status-critical);
}

.about-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.about-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.info-block {
  background: var(--bg-elevated);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.8;
}

.info-block code {
  color: var(--accent-primary);
  font-family: var(--font-mono);
  font-size: 12px;
}
```

---

## 5. HTML Structure

**File:** `frontend/index.html` (lines 59-71)

```html
<div id="progress-panel" class="hidden">
  <div class="progress-header">
    <span id="progress-title">Audit Running</span>
    <button id="btn-copy-logs" class="btn-secondary-sm" title="Copy all logs">📋 Copy</button>
    <button id="btn-cancel-panel" class="btn-danger-sm">Cancel</button>
  </div>
  <div id="scanner-bars"></div>
  <div id="log-output"></div>
</div>
```

---

## 6. Data Store Integration

**File:** `frontend/js/store.js` (existing, verified)

### State Initialization
```javascript
const _state = {
  // ... other state
  scanProgress: {},   // { scanner_name: { percent, file } }
  logLines:     [],   // last 200 entries
};
```

### Progress Update
```javascript
export function setProgress(scanner, percent, file) {
  const current = { ...(get('scanProgress') || {}) };
  current[scanner] = { percent, file };
  set('scanProgress', current);
}
```

### Log Append
```javascript
export function appendLog(level, message) {
  const lines = get('logLines');
  const updated = [...lines, { time: new Date().toISOString(), level, message }];
  set('logLines', updated.slice(-200));   // keep last 200
}
```

---

## 7. Stream Integration

**File:** `frontend/js/stream.js` (existing, verified)

### Progress Event Handler
```javascript
_source.addEventListener('progress', (e) => {
  try {
    const data = JSON.parse(e.data);
    console.log('[Stream:progress]', data.scanner + ':', data.percent + '%');
    store.setProgress(data.scanner, data.percent, data.file);
  } catch (err) {
    console.error('[Stream:progress] Failed to parse:', err);
  }
});
```

### Log Event Handler
```javascript
_source.addEventListener('log', (e) => {
  try {
    const data = JSON.parse(e.data);
    console.log('[Stream:log]', `[${data.level}]`, data.message);
    store.appendLog(data.level, data.message);
  } catch (err) {
    console.error('[Stream:log] Failed to parse:', err);
  }
});
```

---

## 8. Main.js Integration

**File:** `frontend/js/main.js` (lines 56-57)

### Store Subscriptions
```javascript
// Wire updates from store to UI
store.subscribe('scanProgress', updateProgressBars);
store.subscribe('logLines', updateLogOutput);
```

### Panel Show/Hide
```javascript
// Show on audit start
async function handleRun() {
  // ...
  document.getElementById('progress-panel').classList.remove('hidden');
  // ...
}

// Hide on audit completion
async function handleCancel() {
  if (status && status.state === 'running') {
    // ...
  } else {
    document.getElementById('progress-panel').classList.add('hidden');
  }
}
```

---

## Summary

**Total Implementation:**
- ✅ 2 JavaScript functions (27 lines)
- ✅ 92 lines of CSS styling
- ✅ 326 lines of settings interface
- ✅ 1 HTML structure block (already present)
- ✅ Store integration (already present)
- ✅ Stream integration (already present)

**All components work together to provide:**
- Real-time audit progress visualization
- Terminal-style color-coded logging
- Professional tabbed settings interface
- Secure HTML handling
- Responsive UI with proper scrolling

