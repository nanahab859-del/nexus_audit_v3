# Nexus Audit Dashboard — Comparison Report & Implementer Guide
**Old file:** `NEXUS_AUDIT_DASHBOARD.html` (monolithic, ~1 MB)
**New files:** `index.html` + `css/styles.css` + `js/**` (~108 KB total)
**Rule:** Where OLD and NEW clash → **take NEW**. Where features only exist in OLD → restore them.
**Date:** 2026-05-30

---

## QUICK SUMMARY

The new dashboard is a major improvement in architecture. It is NOT yet complete — several
CSS classes and features from the old file are missing from the new CSS. This document tells
the implementer exactly what to do with each difference.

| Area | Verdict | Action |
|---|---|---|
| CSS Design Tokens (`:root`) | ✅ NEW is better | Use `styles.css` — it has real variables |
| Font Stack | ✅ NEW adds 'Inter' | Use NEW `--font-family` |
| Animation `fadeIn` | ✅ NEW only | Keep NEW |
| Animation `pulse` | ✅ Both have it | Same; use NEW |
| `app-card:hover` transform | ✅ NEW is better (-4px vs -2px + shadow) | Use NEW |
| `metric-card:hover` shadow | ✅ NEW only | Keep NEW |
| `primary-btn` / `secondary-btn` | ✅ NEW only | Keep NEW |
| Architecture (modules) | ✅ NEW is far better | Keep NEW structure |
| Audit streaming (SSE) | ✅ NEW is better | Keep NEW SSE approach |
| Web Worker physics | ✅ NEW only | Keep NEW |
| Config Health tab | ✅ NEW only | Keep NEW |
| GitHub links on recs | ✅ NEW only | Keep NEW |
| Bundle SVG overlay | ✅ NEW only | Keep NEW |
| `appScheme()` dynamic colours | ✅ NEW only | Keep NEW |
| Missing CSS classes | ⚠️ OLD has them | RESTORE from OLD (full list below) |
| Manifest tab | ⚠️ OLD only | Evaluate — add back if needed |
| Download Full Report btn | ⚠️ OLD only | RESTORE — useful feature |
| Control Panel visibility | ⚠️ Behaviour changed | See note below |

---

## PART 1 — WHAT TO TAKE FROM NEW (No Change Needed)

These are features/changes in the NEW dashboard that are improvements over OLD.
The implementer should keep these exactly as they are.

### 1.1 CSS Custom Properties
**Old:** Hard-coded hex values scattered throughout every class.
**New:** Proper `:root` with semantic tokens.

```css
/* NEW — keep this */
:root {
  --bg-primary: #0f172a;
  --bg-secondary: rgba(30, 41, 59, 0.9);
  --bg-tertiary: rgba(15, 23, 42, 0.6);
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --accent-primary: #38bdf8;
  --accent-secondary: #818cf8;
  --status-critical: #ef4444;
  --status-warning:  #f59e0b;
  --status-healthy:  #10b981;
  --border-color: #334155;
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 Roboto, Oxygen, Ubuntu, sans-serif;
}
```

### 1.2 Tab Switch Animation
**Old:** No animation when switching tabs.
**New:** Smooth fade-in.

```css
/* NEW — keep this */
.tab-content {
  display: none;
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}
```

### 1.3 Improved hover effects
```css
/* NEW — better than old */
.metric-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent-primary);
  box-shadow: 0 4px 15px rgba(56,189,248,0.1);   /* was missing in old */
}

.app-card:hover {
  border-color: var(--accent-primary);
  transform: translateY(-4px);                    /* old was -2px */
  box-shadow: 0 8px 25px rgba(0,0,0,0.3);         /* was missing in old */
}
```

### 1.4 Named Button Classes
```css
/* NEW — replaces scattered inline button styles */
.primary-btn   { ... linear-gradient(#6366f1, #4f46e5) ... }
.secondary-btn { ... linear-gradient(#0f766e, #0d9488) ... }
```

### 1.5 Header shadow
```css
/* NEW — adds visual depth */
.header { box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2); }
```

### 1.6 ES Module architecture
The new JS is split into clean modules. This should be kept. Do not merge back into a single file.

### 1.7 SSE streaming for audit logs
```javascript
// NEW — real-time streaming, better than interval polling
const es = new EventSource('/api/stream');
```

### 1.8 Web Worker for graph layout
`physics.worker.js` — keeps graph layout off the main thread. Keep as-is.

### 1.9 Config Health tab
New `⚙️ Config Health` tab with Django settings checks — valuable new feature. Keep.

### 1.10 Bundle SVG overlay in inspect mode
Proper inter-app edge bundling with hover/click drill-down. Keep.

### 1.11 `appScheme()` dynamic colours
Generates HSL colours per app name — handles any number of apps. Keep.

### 1.12 GitHub links on recommendations
```javascript
// gitContext.github_base + module path → GitHub URL
const githubLink = gitBase && relativePath ? gitBase + '/blob/' + gitBranch + '/' + relativePath : '';
```

### 1.13 `aria-live="polite"` on edge info panel
Accessibility improvement. Keep.

### 1.14 `overflow:hidden` on graph div
Prevents SVG overlay from bleeding outside the graph container. Keep.

---

## PART 2 — WHAT TO RESTORE FROM OLD (Missing in New)

These features/CSS classes exist in the OLD file but are **missing** from the new `styles.css`.
The implementer must add them. Full CSS to paste is provided below.

---

### 2.1 ⚠️ Missing CSS Classes — MUST ADD to `styles.css`

These classes are used by the new JavaScript (tabs.js, recommendations.js) but not defined in the new styles.css. Without them the UI will break.

#### Status Badge Classes

Used in `recommendations.js` for fix queue status display.

```css
/* ADD to styles.css */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border: 1px solid rgba(148, 163, 184, 0.25);
}
.status-open        { background: rgba(30, 41, 59, 0.8);   color: #cbd5e1; }
.status-in_progress { background: rgba(29, 78, 216, 0.18); color: #93c5fd; }
.status-done        { background: rgba(6, 78, 59, 0.22);   color: #6ee7b7; }
.status-snoozed     { background: rgba(120, 53, 15, 0.22); color: #fcd34d; }
```

#### Recommendation Layout Rows

Used in `recommendations.js` for the action row at the right of each card.

```css
/* ADD to styles.css */
.rec-status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-left: auto;
}
.status-btn-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 12px;
}
```

#### Dependency Cards

Used in `tabs.js::generateDependencyTable()`.

```css
/* ADD to styles.css */
.dep-card {
    background: rgba(15,23,42,.5);
    border-radius: 10px;
    padding: 12px 14px;
    border: 1px solid #1e293b;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.dep-name   { font-size: .85rem; font-weight: 600; color: #f1f5f9; }
.dep-meta   { font-size: .75rem; color: #64748b; }
.dep-badges { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.dep-badge  { padding: 2px 8px; border-radius: 12px; font-size: .7rem; font-weight: 600; }
.dep-ok     { background: #064e3b; color: #6ee7b7; }
.dep-warn   { background: #78350f; color: #fcd34d; }
.dep-vuln   { background: #7f1d1d; color: #fca5a5; }
.dep-na     { background: #1e293b; color: #64748b; }
```

#### Cycle Item

Used in `tabs.js::generateCyclesTable()`.

```css
/* ADD to styles.css */
.cycle-item {
    padding: 8px 12px;
    background: rgba(239,68,68,0.1);
    border-left: 3px solid #ef4444;
    border-radius: 0 6px 6px 0;
    margin-bottom: 6px;
    font-size: 0.82rem;
    cursor: pointer;
    color: #fca5a5;
}
.cycle-item:hover { background: rgba(239,68,68,0.2); }
```

#### App Card Highlight States

Used in `graph.js::highlightApp()` for synced card/graph highlighting.
These need to be added back to support the island sidebar interaction.

```css
/* ADD to styles.css */
.app-card.panel-highlight {
    border-color: #38bdf8 !important;
    background: rgba(30,41,59,1) !important;
    box-shadow: 0 0 0 2px #38bdf822;
}
.app-card.panel-dimmed {
    opacity: 0.55;
    filter: grayscale(30%);
}
```

#### Confidence Bar (used by old recommendations; may still be needed)

```css
/* ADD to styles.css — used if confidence field is rendered */
.confidence-wrap   { margin: 8px 0 10px; }
.confidence-track  { height: 4px; border-radius: 999px;
                     background: rgba(148,163,184,0.18); overflow: hidden; }
.confidence-bar    { height: 100%; border-radius: 999px;
                     background: linear-gradient(90deg, #ef4444 0%, #f59e0b 50%, #10b981 100%); }
.confidence-meta   { margin-top: 5px; display: flex; flex-wrap: wrap; gap: 8px;
                     align-items: center; font-size: 0.72rem; color: #94a3b8; }
.confidence-warning { color: #fca5a5; font-weight: 700; }
```

#### Tier Badge (already in new CSS — verify only)
```css
/* Verify these are in styles.css — they should be */
.tier-badge   { display: inline-flex; align-items: center; gap: 6px; ... }
.tier-online  { color: var(--status-healthy); ... }
.tier-offline { color: var(--status-warning); ... }
.tier-dot     { ... animation: pulse 1.8s infinite; }
```

---

### 2.2 ⚠️ Download Full Report Button — RESTORE

The old file had a "⬇ Full MD Report" button that called `downloadReport('full')`.
This was removed from the new `index.html` control panel. It should be added back next to the Run Audit button:

```html
<!-- ADD inside control-panel, next to run-audit-btn -->
<button class="secondary-btn" onclick="downloadReport('full')"
        title="Download the full comprehensive markdown report">
    &#11015; Full MD Report
</button>
```

And restore the `downloadReport` function (it was in the old monolith's JS block).
Add it to `api.js` or a new `utils.js`:

```javascript
export function downloadReport(type) {
    fetch('/api/report?type=' + type)
        .then(r => r.blob())
        .then(blob => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'AUDIT_REPORT_' + new Date().toISOString().slice(0,10) + '.md';
            a.click();
            URL.revokeObjectURL(url);
        });
}
window.downloadReport = downloadReport;
```

---

### 2.3 ⚠️ Manifest Tab — EVALUATE

The old dashboard had a `📋 Manifest` tab (`id="manifest"`). It has been **removed** from the new HTML.

**Recommendation:** Add it back as a low-cost option since the tab slot already exists in the data.

```html
<!-- ADD to .tabs section in index.html -->
<button class="tab" onclick="showTab('manifest')">📋 Manifest</button>

<!-- ADD tab-content div -->
<div id="manifest" class="tab-content"></div>
```

```javascript
// ADD to renderTabs() in tabs.js
'manifest': generateManifestTab,

function generateManifestTab() {
    // Render State.modules as a readable manifest
    const mods = Object.keys(State.modules || {});
    if (!mods.length) return '<p class="status-warning">No manifest data.</p>';
    return `<table><thead><tr><th>Module</th><th>Imports</th></tr></thead><tbody>
        ${mods.map(m => `<tr><td style="font-family:monospace;">${m}</td>
        <td>${(State.modules[m].imports||[]).length}</td></tr>`).join('')}
    </tbody></table>`;
}
```

---

### 2.4 ⚠️ Control Panel Visibility Behaviour — FIX

**Old:** `<div id="control-panel" style="display:none;">`
The panel was hidden by default and only shown in server mode (when the JS detected `localhost`).

**New:** `<div id="control-panel">` — always visible (no `display:none`).

**Recommendation:** Restore the conditional visibility. It is confusing to show the control panel in static/offline mode. Add this to `dashboard.js`:

```javascript
// ADD to renderTierBadge() in dashboard.js
function renderTierBadge() {
    // ... existing code ...
    const panel = document.getElementById('control-panel');
    if (panel) {
        // Only show the control panel in server/online mode
        const isServerMode = window.location.hostname === 'localhost'
                          || window.location.hostname === '127.0.0.1';
        panel.style.display = isServerMode ? '' : 'none';
    }
}
```

---

## PART 3 — FEATURE COMPARISON TABLE (FULL)

| Feature | Old File | New Files | Decision |
|---|---|---|---|
| CSS design tokens (`:root`) | ❌ Hardcoded everywhere | ✅ Full `:root` | **USE NEW** |
| Font 'Inter' | ❌ Not included | ✅ First in stack | **USE NEW** |
| `@keyframes fadeIn` | ❌ Not present | ✅ On `.tab-content` | **USE NEW** |
| `@keyframes pulse` | ✅ Present | ✅ Present | Same |
| `app-card:hover -4px` | ❌ -2px only | ✅ -4px + shadow | **USE NEW** |
| `metric-card:hover` shadow | ❌ No shadow | ✅ Has shadow | **USE NEW** |
| `.primary-btn` class | ❌ Inline style | ✅ CSS class | **USE NEW** |
| `.secondary-btn` class | ❌ Inline style | ✅ CSS class | **USE NEW** |
| Header `box-shadow` | ❌ Not present | ✅ Present | **USE NEW** |
| ES module architecture | ❌ Monolith | ✅ Modular | **USE NEW** |
| State management | ❌ Global vars | ✅ `State` object | **USE NEW** |
| Audit streaming | ❌ setInterval polling | ✅ SSE EventSource | **USE NEW** |
| Data loading | ❌ Embedded in HTML | ✅ `fetch('/data.json')` | **USE NEW** |
| Page reload on completion | ❌ `location.reload()` | ✅ CustomEvent re-render | **USE NEW** |
| Web Worker physics | ❌ Not present | ✅ physics.worker.js | **USE NEW** |
| Config Health tab | ❌ Not present | ✅ Full implementation | **USE NEW** |
| GitHub links on recs | ❌ Not present | ✅ Via `gitContext` | **USE NEW** |
| Bundle SVG overlay | ❌ Not present | ✅ In inspect mode | **USE NEW** |
| Bundle panel | ❌ Not present | ✅ `#bundle-panel` | **USE NEW** |
| `appScheme()` colours | ❌ Not present | ✅ Hash-based HSL | **USE NEW** |
| Config card in app grid | ❌ Not present | ✅ `⚙️ KERNEL` card | **USE NEW** |
| Coupling map drilldown | ✅ Present | ✅ Improved | **USE NEW** |
| `aria-live` on edge panel | ❌ Not present | ✅ Present | **USE NEW** |
| `overflow:hidden` on graph | ❌ Not present | ✅ Present | **USE NEW** |
| `.status-badge` CSS class | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.status-open/in_progress/done/snoozed` | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.rec-status-row` CSS | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.status-btn-row` CSS | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.dep-card` / `.dep-name` CSS | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.dep-badge` variants CSS | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.cycle-item` CSS | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.app-card.panel-highlight` | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.app-card.panel-dimmed` | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| `.confidence-*` CSS | ✅ Present | ❌ **MISSING** | **RESTORE FROM OLD** |
| Download Full Report button | ✅ Present | ❌ **REMOVED** | **RESTORE** |
| Manifest tab | ✅ Present | ❌ **REMOVED** | **RESTORE (recommended)** |
| Control panel hidden by default | ✅ Present | ❌ **Always visible** | **FIX** |
| Embedded audit data | ✅ Present (standalone) | ❌ Requires server | Architecture choice |
| `vis-network` local fallback | ✅ Bundled in HTML | ✅ Bundled in `js/` | Same |

---

## PART 4 — IMPLEMENTER CHECKLIST

Work through this in order:

### Phase 1 — Copy the CSS additions (15 min)

Open `css/styles.css` and append the following blocks at the end:

- [ ] `.status-badge` + `.status-open/in_progress/done/snoozed`
- [ ] `.rec-status-row` + `.status-btn-row`
- [ ] `.dep-card` + `.dep-name` + `.dep-meta` + `.dep-badges` + `.dep-badge` + `.dep-ok/warn/vuln/na`
- [ ] `.cycle-item` + `.cycle-item:hover`
- [ ] `.app-card.panel-highlight` + `.app-card.panel-dimmed`
- [ ] `.confidence-wrap` + `.confidence-track` + `.confidence-bar` + `.confidence-meta` + `.confidence-warning`

All the CSS to paste is in Part 2 of this document above.

### Phase 2 — Restore the Download button (10 min)

- [ ] Add `.secondary-btn` button next to Run Audit in `index.html`
- [ ] Add `downloadReport()` function to `api.js` and expose on `window`

### Phase 3 — Fix control panel visibility (5 min)

- [ ] Add server-mode detection to `renderTierBadge()` in `dashboard.js`
- [ ] Panel hides itself unless `localhost`

### Phase 4 — Restore Manifest tab (optional, 20 min)

- [ ] Add tab button + div to `index.html`
- [ ] Add `generateManifestTab()` to `tabs.js`
- [ ] Register in `renderTabs()` map

### Phase 5 — Verify the app card highlight sync (10 min)

- [ ] Test: click an island pill in the sidebar
- [ ] Confirm: matching app card gets `.panel-highlight`, others get `.panel-dimmed`
- [ ] If not working, check `graph.js::highlightApp()` is also updating app card DOM elements

### Phase 6 — Verify the dependency tab renders (5 min)

- [ ] Navigate to 📦 Dependencies tab
- [ ] Confirm `.dep-card` items render correctly

### Phase 7 — Verify recommendations fix queue (5 min)

- [ ] Load recommendations tab
- [ ] Confirm status badges show (Open / In Progress / Done / Snooze)
- [ ] Click a status button and verify `localStorage` update

---

## PART 5 — ARCHITECTURAL NOTES FOR THE IMPLEMENTER

### Why the new architecture is better

The old file was a ~1 MB single HTML file that embedded vis-network, all CSS, all JS,
and all audit data in one place. This means:
- Every code change required re-generating the entire file
- No code reuse or testing
- Browser had to parse 1 MB of JS before rendering anything

The new architecture separates:
- **Data** → `/data.json` (loaded async at startup)
- **Styles** → `css/styles.css` (cacheable, tokenised)
- **State** → `js/state.js` (single source of truth)
- **API** → `js/api.js` (all server communication)
- **Components** → `js/components/*.js` (one file per UI section)

### Data API requirements

The new dashboard expects these server endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/data.json` | GET | Full audit data JSON |
| `/api/run` | POST | Start audit (replaces `/api/run_audit`) |
| `/api/stream` | GET | SSE stream for audit logs (replaces `/api/run_audit/log`) |
| `/api/status` | GET | Polling endpoint — returns `{status, mtime}` |
| `/fix-queue` | GET/PUT | Fix queue persistence (server mode) |
| `/api/report` | GET | Markdown report download |

### The `data.json` schema

The server must produce a `data.json` that includes these top-level keys
(all used by `loadAuditData()` in `api.js`):

```json
{
  "applications": {},
  "modules": {},
  "violations": [],
  "security_findings": [],
  "metrics": {},
  "circular_dependencies": [],
  "recommendations": [],
  "metadata": {
    "ghost_files": [],
    "trend": {},
    "capabilities": {}
  },
  "allowed_communications": [],
  "timeline": {},
  "dependency_scan": {},
  "change_summary": {},
  "fix_queue": {},
  "config_health": {},
  "coupling_matrix": {},
  "git_context": {}
}
```

New keys compared to old embedded data: `config_health`, `coupling_matrix`, `git_context`.
If these are missing from the server response, the new components will silently render nothing
(they check `|| {}` before rendering).

---

## PART 6 — COMPLETE CSS ADDITIONS (Ready to Paste)

Copy everything below and append to the end of `css/styles.css`:

```css
/* ====================================================
   ADDITIONS RESTORED FROM OLD DASHBOARD
   Add to end of styles.css
   ==================================================== */

/* Status Badge */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border: 1px solid rgba(148, 163, 184, 0.25);
}
.status-open        { background: rgba(30, 41, 59, 0.8);   color: #cbd5e1; }
.status-in_progress { background: rgba(29, 78, 216, 0.18); color: #93c5fd; }
.status-done        { background: rgba(6, 78, 59, 0.22);   color: #6ee7b7; }
.status-snoozed     { background: rgba(120, 53, 15, 0.22); color: #fcd34d; }

/* Rec layout rows */
.rec-status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-left: auto;
}
.status-btn-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 12px;
}

/* Dependency cards */
.dep-card {
    background: rgba(15,23,42,.5);
    border-radius: 10px;
    padding: 12px 14px;
    border: 1px solid #1e293b;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.dep-name   { font-size: .85rem; font-weight: 600; color: #f1f5f9; }
.dep-meta   { font-size: .75rem; color: #64748b; }
.dep-badges { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.dep-badge  { padding: 2px 8px; border-radius: 12px; font-size: .7rem; font-weight: 600; }
.dep-ok     { background: #064e3b; color: #6ee7b7; }
.dep-warn   { background: #78350f; color: #fcd34d; }
.dep-vuln   { background: #7f1d1d; color: #fca5a5; }
.dep-na     { background: #1e293b; color: #64748b; }

/* Cycle items */
.cycle-item {
    padding: 8px 12px;
    background: rgba(239,68,68,0.1);
    border-left: 3px solid #ef4444;
    border-radius: 0 6px 6px 0;
    margin-bottom: 6px;
    font-size: 0.82rem;
    cursor: pointer;
    color: #fca5a5;
}
.cycle-item:hover { background: rgba(239,68,68,0.2); }

/* App card highlight (synced with graph selection) */
.app-card.panel-highlight {
    border-color: #38bdf8 !important;
    background: rgba(30,41,59,1) !important;
    box-shadow: 0 0 0 2px #38bdf822;
}
.app-card.panel-dimmed {
    opacity: 0.55;
    filter: grayscale(30%);
}

/* Confidence bar */
.confidence-wrap    { margin: 8px 0 10px; }
.confidence-track   { height: 4px; border-radius: 999px;
                      background: rgba(148,163,184,0.18); overflow: hidden; }
.confidence-bar     { height: 100%; border-radius: 999px;
                      background: linear-gradient(90deg,#ef4444 0%,#f59e0b 50%,#10b981 100%); }
.confidence-meta    { margin-top: 5px; display: flex; flex-wrap: wrap; gap: 8px;
                      align-items: center; font-size: 0.72rem; color: #94a3b8; }
.confidence-warning { color: #fca5a5; font-weight: 700; }
```
