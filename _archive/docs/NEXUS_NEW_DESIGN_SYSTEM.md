# Nexus Audit Dashboard — NEW Design System Extraction
**Source:** `visuals/index.html` + `visuals/css/styles.css` + `visuals/js/**`
**Date captured:** 2026-05-30
**Architecture:** ES Module multi-file SPA (replaces monolithic single HTML file)

---

## FILE MAP

```
visuals/
├── index.html                        (14 KB)  HTML shell — no embedded data or scripts
├── css/
│   └── styles.css                    (12 KB)  All styles with CSS custom properties
└── js/
    ├── main.js                        (1.7 KB) ES module entry point
    ├── state.js                       (2.5 KB) Centralised reactive state + helpers
    ├── api.js                         (5.1 KB) Data loading + audit runner + SSE + polling
    ├── physics.worker.js              (4.1 KB) Web Worker — Fruchterman-Reingold layout
    ├── vis-network.min.js             (643 KB) Bundled vis-network (local fallback)
    └── components/
        ├── dashboard.js              (10.6 KB) Header, metrics, app cards, change summary
        ├── graph.js                  (31.4 KB) Vis-network init, interactions, SVG overlay
        ├── tabs.js                   (13.6 KB) All tab content generators incl. Config Health
        ├── trends.js                  (4.7 KB) Canvas-based trend chart (no Chart.js dependency)
        └── recommendations.js        (12.6 KB) Fix-queue, effort buckets, filtering, GitHub links
```

---

## SECTION 1 — CSS CUSTOM PROPERTIES & COLOUR PALETTE

### `:root` block (css/styles.css, lines 1–20)

```css
:root {
  /* Colors */
  --bg-primary: #0f172a;
  --bg-secondary: rgba(30, 41, 59, 0.9);
  --bg-tertiary: rgba(15, 23, 42, 0.6);
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --accent-primary: #38bdf8;
  --accent-secondary: #818cf8;

  /* Status Colors */
  --status-critical: #ef4444;
  --status-warning:  #f59e0b;
  --status-healthy:  #10b981;

  /* Borders */
  --border-color: #334155;

  /* Fonts */
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 Roboto, Oxygen, Ubuntu, sans-serif;
}
```

### Dark / Light mode
No `[data-theme]` switching — **dark-only** design.

### Hard-coded colours still used (in components and inline styles)

| Usage | Value | Note |
|---|---|---|
| Grade A badge bg | `#064e3b` | unchanged |
| Grade B badge bg | `#1e3a5f` | unchanged |
| Grade C badge bg | `#78350f` | unchanged |
| Grade D badge bg | `#7c2d12` | unchanged |
| Grade F badge bg | `#7f1d1d` | unchanged |
| Blue accent | `#3b82f6` | medium severity |
| Indigo button | `#6366f1` / `#4f46e5` | Run Audit button |
| Teal button | `#0f766e` / `#0d9488` | secondary btn |
| Amber text | `#fcd34d` | snoozed status |
| Blue text | `#93c5fd` | in-progress status |
| Config node | `#b45309` bg / `#f59e0b` border | hex node on graph |
| Graph bg | `rgba(10,15,30,0.5)` | network canvas |
| Log bg | `#020617` | live output pre |
| Trends grid | `#94a3b8` + `rgba(51,65,85,.8)` | canvas drawn |
| Score bar track | `#1e293b` | not tokenised |

---

## SECTION 2 — FONT FAMILY & TYPOGRAPHY

### Font stack
```css
/* :root variable */
--font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
               Roboto, Oxygen, Ubuntu, sans-serif;

/* Applied on body */
body {
  font-family: var(--font-family);
}
```

> **Note:** `'Inter'` is NEW in the refactored version. The old file did not include it.
> The dashboard will render in Inter if the user's system has it installed; otherwise falls
> back to system fonts. There is NO `@import` from Google Fonts — local system font only.

### Size / weight tokens (class definitions)
```css
.header h1      { font-size: 2.5rem; font-weight: 700 }
.metric-value   { font-size: 2.5rem; font-weight: 700 }
.metric-label   { font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.5px }
.app-name       { font-size: 1.3rem; font-weight: 700 }
.app-score      { font-size: 2rem;   font-weight: 700 }
.app-details    { font-size: 0.85rem }
.tab            { font-size: 0.9rem }
.grade-badge    { font-size: 0.75rem; font-weight: 700 }
.badge          { font-size: 0.72rem; font-weight: 700 }
.tier-badge     { font-size: 0.78rem; font-weight: 600 }
.island-label   { font-size: 0.68rem; font-weight: 600 }
.island-sidebar-title { font-size: 0.6rem }
.node-info-bar  { font-size: 0.85rem }
.legend-item    { font-size: 0.82rem }
th, td          { font-size: 0.87rem }
.status-btn     { font-size: 0.72rem; font-weight: 600 }
```

Monospace overrides (inline):
```css
font-family: monospace; font-size: 0.78rem; /* audit log pre */
font-family: monospace; font-size: 0.8rem;  /* security findings file column */
```

---

## SECTION 3 — ANIMATIONS & TRANSITIONS

### @keyframes rules

```css
/* Tab content fade-in — NEW in refactored version */
@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Tier badge dot pulse */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
```

### Classes with animation applied

```css
.tab-content {
  display: none;
  animation: fadeIn 0.3s ease;   /* fires whenever content becomes display:block */
}

.tier-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.8s infinite;
}
```

### Transitions on interactive elements

```css
.metric-card    { transition: transform 0.3s ease, border-color 0.3s ease; }
.app-card       { transition: all 0.3s ease; }
.score-fill     { transition: width 1s ease; }
.tab            { transition: all 0.3s ease; }
.ctrl-btn       { transition: all 0.2s; }
.island-pill    { transition: all 0.2s; }
.island-dot     { transition: transform 0.2s, box-shadow 0.2s; }
.island-label   { transition: color 0.2s; }
.legend-item    { transition: all 0.2s; }
.status-btn     { transition: all 0.15s ease; }
.primary-btn    { transition: opacity 0.2s; }
.secondary-btn  { transition: opacity 0.2s; }
```

### Hover transforms

```css
/* metric-card */
.metric-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent-primary);
  box-shadow: 0 4px 15px rgba(56,189,248,0.1);   /* NEW — not in old file */
}

/* app-card */
.app-card:hover {
  border-color: var(--accent-primary);
  transform: translateY(-4px);                    /* was -2px in old file */
  box-shadow: 0 8px 25px rgba(0,0,0,0.3);         /* NEW */
}

/* island pill active dot */
.island-pill.pill-active .island-dot {
  transform: scale(1.4);
  box-shadow: 0 0 6px currentColor;
}
```

---

## SECTION 4 — LAYOUT SKELETON (HTML Structure)

```html
<body>
  <div class="dashboard">

    <!-- ── Header ── -->
    <div class="header">
      <h1 style="display:flex;align-items:center;">🛡️ Nexus Architecture Audit
        <span id="tier-badge" class="tier-badge tier-offline">
          <span class="tier-dot"></span> Loading…
        </span>
      </h1>
      <p style="color:var(--text-secondary);">...</p>
      <p style="color:var(--status-healthy);">✅ STRICT MODULARITY...</p>
      <div id="change-summary-container"></div>
      <div class="metrics-grid" id="metrics-grid"></div>
    </div>

    <!-- ── Control Panel ── (always visible in new; was display:none in old) -->
    <div id="control-panel">
      <div> <!-- flex row: title + toggles + run button -->
        <label><input type="checkbox" id="tog-deps" checked> Dependencies</label>
        <label><input type="checkbox" id="tog-security" checked> Security</label>
        <label><input type="checkbox" id="tog-ai" checked> AI</label>
        <label><input type="checkbox" id="tog-deadcode" checked> Dead Code</label>
        <label><input type="checkbox" id="tog-complexity" checked> Complexity</label>
        <label><input type="checkbox" id="tog-ghosts" checked> Ghosts</label>
        <label><input type="checkbox" id="tog-config" checked> Config</label>
        <label><input type="checkbox" id="tog-cycles" checked> Cycles</label>
        <label><input type="checkbox" id="tog-force-rescan"> Force Rescan</label>
        <select id="tog-app"><option value="">All apps</option></select>
        <button id="run-audit-btn" class="primary-btn" onclick="runAuditFromUI()">
          ▶ Run Audit
        </button>
        <!-- "Download Full Report" button REMOVED in new version -->
      </div>
      <div id="audit-log-wrapper" style="display:none;">
        <pre id="audit-log-content"></pre>
      </div>
    </div>

    <!-- ── App Health Grid ── -->
    <h2>🏥 Application Health</h2>
    <div class="app-grid" id="app-grid"></div>

    <!-- ── Detail Tabs ── -->
    <div class="tab-container">
      <div class="tabs">
        <button class="tab active" onclick="showTab('violations')">🚨 Violations</button>
        <button class="tab" onclick="showTab('test-debt')">🧪 Test Debt</button>
        <button class="tab" onclick="showTab('allowed')">🔗 Allowed Comms</button>
        <button class="tab" onclick="showTab('security')">🔒 Security</button>
        <button class="tab" onclick="showTab('config-health')">⚙️ Config Health</button><!-- NEW -->
        <button class="tab" onclick="showTab('complexity')">📊 Complexity</button>
        <button class="tab" onclick="showTab('ghost')">👻 Ghost Files</button>
        <button class="tab" onclick="showTab('cycles')">🔄 Cycles</button>
        <button class="tab" id="dep-tab-btn" onclick="showTab('dependencies')" style="display:none;">📦 Dependencies</button>
        <button class="tab" onclick="showTab('trends')">📈 Trends</button>
        <button class="tab" onclick="showTab('coupling-map')">🔥 Coupling Map</button>
        <button class="tab" onclick="showTab('recommendations')">💡 Recommendations</button>
        <!-- 📋 Manifest tab REMOVED in new version -->
      </div>
      <div id="violations"      class="tab-content active"></div>
      <div id="test-debt"       class="tab-content"></div>
      <div id="allowed"         class="tab-content"></div>
      <div id="security"        class="tab-content"></div>
      <div id="config-health"   class="tab-content"></div><!-- NEW -->
      <div id="complexity"      class="tab-content"></div>
      <div id="ghost"           class="tab-content"></div>
      <div id="cycles"          class="tab-content"></div>
      <div id="dependencies"    class="tab-content"></div>
      <div id="trends"          class="tab-content"></div>
      <div id="coupling-map"    class="tab-content"></div>
      <div id="recommendations" class="tab-content">
        <div id="effort-summary"></div>
        <div> <!-- filter bar -->
          <input type="text" id="rec-search" placeholder="Search...">
          <select id="rec-filter-type">...</select>
          <select id="rec-filter-priority">...</select>
          <select id="rec-sort">...</select>
          <span id="rec-counter"></span>
        </div>
        <div id="recommendations-list"></div><!-- NEW — dedicated list container -->
      </div>
    </div>

    <!-- ── Network Graph ── -->
    <div class="network-section">
      <h2>🌐 Dependency Network</h2>
      <div class="network-controls"> ... </div>
      <div class="network-wrap">
        <div class="island-sidebar" id="island-sidebar">
          <div class="island-sidebar-title">Islands</div>
        </div>
        <!-- overflow:hidden added to graph div (new) -->
        <div id="network" style="flex:1;height:540px;min-height:540px;overflow:hidden;position:relative;">
          <div id="graph-loading">Waiting for data<span id="graph-dots">...</span></div>
          <!-- Floating panels INSIDE the graph container (new) -->
          <div id="edge-info-panel" aria-live="polite" style="display:none; position:absolute; ..."></div>
          <div id="bundle-panel"    style="display:none; position:absolute; ..."></div><!-- NEW -->
        </div>
      </div>
      <div class="node-info-bar" id="node-info">...</div>
      <!-- edge-info-panel moved INSIDE #network; no longer outside it -->
      <div class="legend" id="legend"></div>
    </div>

  </div><!-- /.dashboard -->
</body>
```

---

## SECTION 5 — KEY UI COMPONENT SNIPPETS

### 5a — Metric Card

**CSS (styles.css):**
```css
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-top: 20px;
}
.metric-card {
  background: var(--bg-tertiary);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid var(--border-color);
  transition: transform 0.3s ease, border-color 0.3s ease;
}
.metric-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent-primary);
  box-shadow: 0 4px 15px rgba(56,189,248,0.1);
}
.metric-value { font-size: 2.5rem; font-weight: 700; margin: 10px 0; }
.metric-label { color: var(--text-secondary); font-size: 0.9rem;
                text-transform: uppercase; letter-spacing: 0.5px; }
```

**HTML (generated by `renderMetrics()` in dashboard.js):**
```html
<div class="metric-card">
  <div class="metric-label">Overall Health</div>
  <div class="metric-value" style="color:#10b981">78.4%</div>
  <div style="font-size:0.85rem;">Grade: B</div>
</div>
```

---

### 5b — Progress / Audit Log Panel (Live Output Drawer)

**HTML (index.html):**
```html
<div id="audit-log-wrapper"
     style="display:none; margin-top:18px; background:#020617;
            border:1px solid #1e293b; border-radius:10px;
            padding:14px 16px; max-height:280px; overflow-y:auto;">
  <div style="font-size:0.72rem; color:#475569; margin-bottom:8px;
              font-weight:600; text-transform:uppercase; letter-spacing:1px;">
    Live Output
  </div>
  <pre id="audit-log-content"
       style="font-family:monospace; font-size:0.78rem; color:#94a3b8;
              white-space:pre-wrap; margin:0;"></pre>
</div>
```

**JS — reveals the panel and streams via SSE (api.js):**
```javascript
logWrapper.style.display = 'block';

const es = new EventSource('/api/stream');
es.addEventListener('log', (e) => {
    const d = JSON.parse(e.data);
    logEl.textContent += d.message + '\n';
    logWrapper.scrollTop = logWrapper.scrollHeight;
});
es.addEventListener('status', (e) => {
    const d = JSON.parse(e.data);
    if (d.state === 'completed') {
        es.close();
        // reload in 3s via CustomEvent 'reload-data'
    }
});
```
> **Important architectural change:** Old file used `setInterval` polling against `/api/run_audit/log`.
> New file uses **Server-Sent Events** via `EventSource('/api/stream')`.
> The API endpoint also changed: old = `POST /api/run_audit`, new = `POST /api/run`.

---

### 5c — Issues Table (structure + column headers)

**CSS:**
```css
table { width: 100%; border-collapse: collapse; }
th, td { padding: 11px 14px; text-align: left;
         border-bottom: 1px solid #1e293b; font-size: 0.87rem; }
th { background: var(--bg-tertiary); font-weight: 600; color: var(--accent-primary);
     position: sticky; top: 0; z-index: 1; }
tr:hover { background: rgba(56,189,248,0.04); }
```

**HTML (generated by `generateViolationsTable()` in tabs.js):**
```html
<table>
  <thead>
    <tr>
      <th>Source</th>
      <th>Target</th>
      <th>Type</th>
      <th>Penalty</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="color:#fca5a5;">nexus_social.views</td>
      <td style="color:#fcd34d;">nexus_core.models</td>
      <td><span class="badge badge-high">Cross-App Import</span></td>
      <td>10</td>
    </tr>
  </tbody>
</table>
```

---

### 5d — Architecture Graph Legend

**CSS:**
```css
.legend {
  display: flex; flex-wrap: wrap; gap: 16px; padding: 14px;
  background: var(--bg-tertiary); border-radius: 8px; margin-top: 12px;
}
.legend-item {
  display: flex; align-items: center; gap: 8px; font-size: 0.82rem;
  cursor: pointer; padding: 5px 10px; border-radius: 6px;
  transition: all 0.2s; border: 1px solid transparent;
}
.legend-item:hover  { background: rgba(255,255,255,0.07); }
.legend-item.active { background: rgba(56,189,248,0.12); border-color: #38bdf833; }
.legend-color       { width: 22px; height: 4px; border-radius: 2px; flex-shrink: 0; }
.legend-color.dashed {
  background: repeating-linear-gradient(
    90deg, currentColor, currentColor 5px, transparent 5px, transparent 10px);
}
```

**HTML (generated by `buildLegend()` in graph.js):**
```html
<div class="legend" id="legend">
  <div class="legend-item" data-edge-type="internal">
    <div class="legend-color" style="background:#5DADE2;color:#5DADE2;"></div>
    <span>Internal Import</span>
  </div>
  <div class="legend-item" data-edge-type="violation">
    <div class="legend-color" style="background:#FF3333;color:#FF3333;"></div>
    <span>Cross-App Violation</span>
  </div>
  <div class="legend-item" data-edge-type="bootstrap">
    <div class="legend-color dashed" style="background:#94a3b8;color:#94a3b8;"></div>
    <span>Django Bootstrap (Exempt)</span>
  </div>
  <div class="legend-item" data-edge-type="allowed">
    <div class="legend-color dashed" style="background:#2ECC71;color:#2ECC71;"></div>
    <span>Signal/Receiver (Allowed)</span>
  </div>
  <div class="legend-item" data-edge-type="celery">
    <div class="legend-color dashed" style="background:#A29BFE;color:#A29BFE;"></div>
    <span>Celery Task (Allowed)</span>
  </div>
  <div class="legend-item" data-edge-type="warning">
    <div class="legend-color" style="background:#f59e0b;color:#f59e0b;"></div>
    <span>Implicit Coupling</span>
  </div>
</div>
```

---

## SECTION 6 — DARK/LIGHT MODE TOGGLE LOGIC

**Not present.** The dashboard is dark-only. No `data-theme` switching, no toggle button, no `localStorage` theme key.

**`localStorage` is used only for Fix Queue state** (recommendation card statuses):

```javascript
// state.js
const FIX_QUEUE_STORAGE_KEY = 'nexus-audit-fix-queue';

export function getFixQueueState() {
    let saved = {};
    try {
        saved = JSON.parse(localStorage.getItem(FIX_QUEUE_STORAGE_KEY) || '{}') || {};
    } catch (err) { saved = {}; }
    return Object.assign({}, State.fixQueueData || {}, saved);
}

export function persistFixQueueState(recId, status) {
    fixQueueState = Object.assign({}, fixQueueState, {
        [recId]: { ...fixQueueState[recId], status, updated_at: new Date().toISOString() }
    });
    try {
        localStorage.setItem(FIX_QUEUE_STORAGE_KEY, JSON.stringify(fixQueueState));
    } catch (err) {}
    // Also syncs to server if localhost
    if (USE_FIX_QUEUE_SERVER) {
        fetch('/fix-queue', { method: 'PUT', ... });
    }
    window.dispatchEvent(new CustomEvent('fix-queue-updated'));
}
```

---

## SECTION 7 — GLOBAL STYLE RESETS

```css
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-family);
  background: linear-gradient(135deg, var(--bg-primary) 0%, #1e293b 100%);
  color: var(--text-primary);
  min-height: 100vh;
  padding: 20px;
}
```

No `*::before` / `*::after` resets. No custom scrollbar styling.

---

## SECTION 8 — STATE MANAGEMENT (NEW — not in old file)

The new dashboard introduces a centralised state object (`state.js`):

```javascript
export const State = {
    // Data
    apps: {},            modules: {},          violations: [],
    securityFindings: [], metrics: {},          cycles: [],
    recommendations: [], metadata: {},          ghostFiles: [],
    allowedComms: [],    trendData: {},         timelineData: {},
    depScan: {},         capabilities: {},      changeSummary: {},
    fixQueueData: {},    configHealth: {},      couplingMatrix: {},
    gitContext: {},
    // UI State
    activeFilter: null,  graphInitialized: false, auditRunning: false,
    selectedEdge: null,  inspectMode: false
};
```

**Dynamic app colour helper** (replaces per-app hard-coded colours):
```javascript
export const APP_SCHEME = {};
export function appScheme(name) {
    if (APP_SCHEME[name]) return APP_SCHEME[name];
    const hash = Array.from(name).reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 0);
    const hue = Math.abs(hash) % 360;
    APP_SCHEME[name] = {
        bg:   `hsl(${hue}, 65%, 25%)`,
        border:`hsl(${hue}, 70%, 45%)`,
        text: `hsl(${hue}, 80%, 90%)`
    };
    return APP_SCHEME[name];
}
```

---

## SECTION 9 — API & DATA LOADING (NEW architecture)

```javascript
// api.js — Data source changed from embedded JSON to fetched endpoint
export async function loadAuditData() {
    const resp = await fetch('/data.json');  // External file — NOT embedded in HTML
    const data = await resp.json();
    Object.assign(State, {
        apps: data.applications || {},
        modules: data.modules || {},
        // ... all fields mapped
        configHealth: data.config_health || {},   // new data field
        couplingMatrix: data.coupling_matrix || {},// new data field
        gitContext: data.git_context || {}         // new data field (GitHub links)
    });
}
```

**Audit runner — changed from polling to SSE:**
```javascript
// OLD: setInterval polling to /api/run_audit/log
// NEW: Server-Sent Events via EventSource
const es = new EventSource('/api/stream');
es.addEventListener('log', e => { /* stream lines to log */ });
es.addEventListener('status', e => {
    if (d.state === 'completed') {
        es.close();
        window.dispatchEvent(new CustomEvent('reload-data'));
    }
});
```

**Live auto-refresh — clean re-render instead of full page reload:**
```javascript
// OLD: location.reload() after 3s
// NEW: CustomEvent triggers state reload + re-render without page refresh
window.addEventListener('reload-data', async () => {
    const ok = await loadAuditData();
    if (ok) { State.graphInitialized = false; renderAll(); }
});
```

---

## SECTION 10 — WEB WORKER (NEW — not in old file)

`physics.worker.js` runs Fruchterman-Reingold graph layout off the main thread:

```javascript
// graph.js — spawn the worker
if (window.Worker && !physicsWorker) {
    physicsWorker = new Worker('js/physics.worker.js');
    physicsWorker.onmessage = (e) => {
        if (e.data.type === 'LAYOUT_COMPLETE') {
            applyWorkerPositions(e.data.payload.nodePositions);
        }
    };
}

// Send layout request
physicsWorker.postMessage({
    type: 'CALCULATE_LAYOUT',
    payload: { islands, appList, weight }
});
```

Worker algorithm: 150-iteration FR layout with attraction weighted by cross-app connection count.

---

## SECTION 11 — NEW FEATURES (not in old file)

| Feature | Location | Description |
|---|---|---|
| ⚙️ Config Health tab | `tabs.js::generateConfigHealthTab()` | Displays Django settings checks with severity, expandable explanations |
| 🔗 GitHub links on recs | `recommendations.js` | `gitContext.github_base` + `branch` + module path → direct GitHub URL |
| 📦 Bundle SVG overlay | `graph.js::buildBundleOverlay()` | Inspect mode draws SVG paths over vis-network canvas; hover fans out |
| 📦 Bundle panel | `#bundle-panel` in `index.html` | Floating panel listing all edges in a bundle |
| `aria-live="polite"` | `#edge-info-panel` | Accessibility attribute for screen readers |
| `overflow:hidden` on graph div | `index.html` | Prevents SVG overlay bleed |
| Effort bucket filter | `recommendations.js` | Quick / Half-day / Multi-day / Major filter buttons |
| `appScheme()` helper | `state.js` | Dynamic colour generation per app name (hash-based HSL) |
| Config card in app grid | `dashboard.js::renderAppGrid()` | ⚙️ kernel card with hexagon graph node |
| Coupling drilldown | `tabs.js::generateCouplingMapTab()` | Click matrix cell → detailed violation list |
| No-refresh data reload | `main.js` + `api.js` | CustomEvent-based re-render on audit completion |
| `#recommendations-list` | `index.html` | Dedicated container for rec cards (was inline in old) |
| `.primary-btn` / `.secondary-btn` | `styles.css` | Named button classes (old used inline styles) |
| `box-shadow` on header | `styles.css` | `0 4px 20px rgba(0,0,0,0.2)` — improves depth |
| `fadeIn` on tab switch | `styles.css` | `animation: fadeIn 0.3s ease` on `.tab-content` |

---

## SECTION 12 — PRIMARY BUTTON CLASSES (NEW)

```css
.primary-btn {
  padding: 10px 22px;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s;
  box-shadow: 0 2px 12px rgba(99,102,241,0.4);
}
.primary-btn:hover { opacity: 0.85; }

.secondary-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s;
  box-shadow: 0 2px 12px rgba(13,148,136,0.4);
}
.secondary-btn:hover { opacity: 0.85; }
```
