# Nexus Audit V3 — Phase 4: Frontend SPA
**Status:** Planning  
**Depends on:** Phase 3.2 complete (`v0.3.2` tag exists)  
**Goal:** Build the "Command Center" UI — a keyboard-driven, information-dense
single-page application that consumes the Phase 2 API and displays real scanner
output from Phase 3 in real time. After Phase 4, a developer opens a browser,
clicks Run, and watches their audit happen live.

---

## What Phase 4 Delivers

| File | What it is |
|------|-----------|
| `frontend/index.html` | Shell: layout, navigation, modal containers, script/style imports |
| `frontend/css/variables.css` | Design tokens — colours, spacing, typography, shadow, radius |
| `frontend/css/layout.css` | Page skeleton, sidebar, content area, responsive grid |
| `frontend/css/components.css` | Cards, buttons, badges, tables, modals, progress bars, toasts |
| `frontend/css/themes.css` | Light and dark theme using CSS custom properties |
| `frontend/js/api.js` | Fetch wrappers for every REST endpoint + EventSource SSE connection |
| `frontend/js/state.js` | Application state manager — single source of truth for all UI data |
| `frontend/js/router.js` | Hash-based SPA router — every view and filter is deep-linkable |
| `frontend/js/stream.js` | SSE event handler — updates progress bars, appends log lines, injects findings |
| `frontend/js/dashboard.js` | Overview: severity cards, issue trend sparkline, top-files list, latest findings table |
| `frontend/js/settings.js` | Settings modal + first-run onboarding wizard |
| `frontend/js/command-palette.js` | CMD+K global palette — run audit, navigate, jump to finding |
| `frontend/js/utils.js` | Shared helpers: date formatting, severity colours, DOM utilities |
| `frontend/assets/logo.svg` | Tool logo |
| `frontend/assets/icons/` | SVG icons for severities, categories, status indicators |

The API server's static-file catch-all routes (already stubbed in Phase 2) are
upgraded to serve `frontend/` for real.

---

## Design Principles (Non-Negotiable)

These come directly from the V3 design doc and must be respected in every
component built in Phase 4.

1. **Keyboard-driven:** `CMD+K` (or `CTRL+K` on Windows/Linux) opens the command
   palette from anywhere. `ESC` closes modals. Arrow keys navigate the palette.
2. **Real-time feedback:** The progress panel is always visible during an audit.
   The developer sees which scanner is running and at what percentage — never
   a spinner that spins for minutes.
3. **Deep-linkable:** Every view, every filter, and every individual finding has a
   URL hash. `#/issues?severity=high&scanner=bandit` is a valid shareable URL.
4. **Empty states that teach:** No blank pages. When no audit has run, the UI
   shows the onboarding wizard. When a scanner returns zero findings, it says why.
5. **Light + Dark themes:** Toggle with one click. Preference persisted in
   `localStorage`. Default follows `prefers-color-scheme`.
6. **No framework:** Vanilla ES6 modules + Web Components where appropriate.
   No React, Vue, or bundler. The browser loads `index.html` and that is it.

---

## Folder Layout After Phase 4

```
nexus_audit_v3/
├── frontend/
│   ├── index.html
│   ├── css/
│   │   ├── variables.css
│   │   ├── layout.css
│   │   ├── components.css
│   │   └── themes.css
│   ├── js/
│   │   ├── api.js
│   │   ├── state.js
│   │   ├── router.js
│   │   ├── stream.js
│   │   ├── dashboard.js
│   │   ├── settings.js
│   │   ├── command-palette.js
│   │   └── utils.js
│   └── assets/
│       ├── logo.svg
│       └── icons/
│           ├── critical.svg
│           ├── high.svg
│           ├── medium.svg
│           ├── low.svg
│           ├── info.svg
│           ├── security.svg
│           ├── quality.svg
│           ├── dependency.svg
│           └── architecture.svg
├── api/
│   └── server.py    ← EDIT: upgrade static file serving
└── tests/
    └── test_frontend_serve.py  ← NEW: verify static files are served correctly
```

---

## Step-by-Step Implementation Order

---

### Step 1 — Design tokens: `frontend/css/variables.css`

All colours, spacing, and typography defined as CSS custom properties.
Every other CSS file uses these variables — never raw hex values or pixel sizes.

**Colour palette (dark theme base, light theme overrides in `themes.css`):**

```css
:root {
  /* Background layers */
  --bg-base:       #0d0f14;
  --bg-surface:    #161920;
  --bg-elevated:   #1e2128;
  --bg-overlay:    #252830;

  /* Borders */
  --border-subtle:  rgba(255,255,255,0.06);
  --border-default: rgba(255,255,255,0.12);
  --border-strong:  rgba(255,255,255,0.24);

  /* Text */
  --text-primary:   #e8eaf0;
  --text-secondary: #9099aa;
  --text-muted:     #5a6272;
  --text-inverse:   #0d0f14;

  /* Severity colours */
  --severity-critical: #ff4444;
  --severity-high:     #ff8c00;
  --severity-medium:   #ffd700;
  --severity-low:      #4caf50;
  --severity-info:     #5b9bd5;

  /* Category accent colours */
  --cat-security:     #ff6b6b;
  --cat-quality:      #74c0fc;
  --cat-dependency:   #ff9f43;
  --cat-architecture: #a29bfe;

  /* Interactive */
  --accent-primary:  #5b9bd5;
  --accent-hover:    #74aee0;
  --accent-active:   #4a8ac4;

  /* Spacing scale */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  /* Typography */
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --text-xs:   11px;
  --text-sm:   13px;
  --text-base: 15px;
  --text-lg:   17px;
  --text-xl:   20px;
  --text-2xl:  24px;

  /* Radii */
  --radius-sm:  4px;
  --radius-md:  8px;
  --radius-lg:  12px;
  --radius-xl:  16px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.5);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.6);
}
```

**Rules:**
- No hardcoded values in `layout.css` or `components.css` — always `var(--...)`.
- Inter and JetBrains Mono loaded from Google Fonts in `index.html` with
  `display=swap` and `<link rel="preconnect">`.

**Commit:** `feat(frontend): design tokens — CSS custom properties`

---

### Step 2 — `frontend/css/themes.css`

Light theme overrides. Dark is the default (`:root` in variables.css).

```css
[data-theme="light"] {
  --bg-base:       #f4f5f7;
  --bg-surface:    #ffffff;
  --bg-elevated:   #f0f1f4;
  --bg-overlay:    #e8eaed;

  --border-subtle:  rgba(0,0,0,0.06);
  --border-default: rgba(0,0,0,0.12);
  --border-strong:  rgba(0,0,0,0.24);

  --text-primary:   #1a1d23;
  --text-secondary: #4a5568;
  --text-muted:     #9aa0aa;
  --text-inverse:   #ffffff;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.12);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.16);
}
```

Theme toggle: `document.documentElement.setAttribute('data-theme', 'light' | 'dark')`.
Persisted in `localStorage` under key `nexus-audit-theme`.
Default: `window.matchMedia('(prefers-color-scheme: dark)').matches`.

**Commit:** `feat(frontend): light/dark theme system`

---

### Step 3 — `frontend/css/layout.css` + `frontend/index.html` shell

The page structure. Built once; individual views are shown/hidden by the router.

**HTML shell structure:**

```html
<body data-theme="dark">
  <div id="app">

    <!-- Top navigation bar -->
    <header id="topbar">
      <div class="topbar-left">
        <img src="assets/logo.svg" class="logo" alt="Nexus Audit">
        <span class="app-name">Nexus Audit</span>
      </div>
      <div class="topbar-right">
        <button id="btn-palette" title="CMD+K">⌘K</button>
        <button id="btn-settings" title="Settings">⚙</button>
        <button id="btn-theme" title="Toggle theme">🌙</button>
        <button id="btn-run" class="btn-primary">▶ Run</button>
      </div>
    </header>

    <!-- Main content area — router swaps views here -->
    <main id="view-container">
      <div id="view-dashboard" class="view"></div>
      <div id="view-issues"    class="view hidden"></div>
      <div id="view-history"   class="view hidden"></div>
    </main>

    <!-- Progress panel — slides up from bottom during audit -->
    <div id="progress-panel" class="hidden">
      <div class="progress-header">
        <span id="progress-title">Audit Running</span>
        <button id="btn-cancel">Cancel</button>
      </div>
      <div id="progress-scanners"></div>
      <div id="progress-log"></div>
    </div>

    <!-- Modals (rendered but hidden) -->
    <div id="modal-settings" class="modal hidden"></div>
    <div id="modal-issue"    class="modal hidden"></div>
    <div id="modal-overlay"  class="modal-overlay hidden"></div>

    <!-- Command palette -->
    <div id="command-palette" class="hidden"></div>

  </div>
</body>
```

**`layout.css`** defines:
- `#topbar`: fixed top, `display: flex`, `justify-content: space-between`,
  `height: 52px`, `border-bottom: 1px solid var(--border-subtle)`.
- `#view-container`: full height minus topbar, scrollable.
- `.view.hidden`: `display: none`.
- `#progress-panel`: fixed bottom, slides up with CSS transition on `.visible` class.
- `.modal-overlay`: fixed full-screen semi-transparent backdrop.

**Commit:** `feat(frontend): layout shell and index.html`

---

### Step 4 — `frontend/js/api.js`

Fetch wrappers for every REST endpoint and the SSE connection.
This is the only file that knows the server's base URL.

```javascript
const BASE = 'http://127.0.0.1:8421';

// REST wrappers — all return parsed JSON or throw ApiError
export async function getStatus()          { return get('/api/status'); }
export async function getData()            { return get('/api/data'); }
export async function getHistory()         { return get('/api/history'); }
export async function getHistoryItem(id)   { return get(`/api/history/${id}`); }
export async function getSettings()        { return get('/api/settings'); }
export async function saveSettings(data)   { return post('/api/settings', data); }
export async function startRun()           { return post('/api/run'); }
export async function cancelRun()          { return post('/api/cancel'); }

// SSE connection — returns an EventSource with auto-reconnect
export function openStream(handlers) {
  // handlers: { onStatus, onProgress, onLog, onFinding, onError }
  // Uses Last-Event-ID automatically (native EventSource behaviour)
  const es = new EventSource(`${BASE}/api/stream`);
  es.addEventListener('status',   e => handlers.onStatus?.(JSON.parse(e.data)));
  es.addEventListener('progress', e => handlers.onProgress?.(JSON.parse(e.data)));
  es.addEventListener('log',      e => handlers.onLog?.(JSON.parse(e.data)));
  es.addEventListener('finding',  e => handlers.onFinding?.(JSON.parse(e.data)));
  es.onerror = e => handlers.onError?.(e);
  return es;
}

class ApiError extends Error {
  constructor(status, body) {
    super(body.message || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}
```

**Rules:**
- No UI logic in `api.js` — it only fetches and returns data.
- `ApiError` carries `status` and the full parsed error body so callers can
  show specific messages (409 Conflict, 400 Bad Request, etc.).
- The `EventSource` uses native `Last-Event-ID` — no manual tracking needed
  because the browser sends it automatically on reconnect.

**Commit:** `feat(frontend): api.js — REST wrappers and SSE connection`

---

### Step 5 — `frontend/js/state.js`

Single source of truth. All UI data lives here. No component reads from the API
directly — it reads from state and subscribes to state changes.

```javascript
// The state shape
const _state = {
  status:   { state: 'idle', job_id: null },
  data:     { findings: [], job: null },
  history:  [],
  settings: null,
  // UI-only state
  activeView:      'dashboard',
  filters:         { severity: null, scanner: null, category: null, search: '' },
  selectedFinding: null,
  scanProgress:    {},   // { scanner_name: { percent, file } }
  logLines:        [],   // last 100 log entries
};

// Subscribe to state slices
export function subscribe(key, callback) { /* ... */ }
export function unsubscribe(token) { /* ... */ }

// Setters — each notifies subscribers of that key
export function setStatus(s)    { _set('status', s); }
export function setData(d)      { _set('data', d); }
export function setHistory(h)   { _set('history', h); }
export function setSettings(s)  { _set('settings', s); }
export function setActiveView(v){ _set('activeView', v); }
export function setFilters(f)   { _set('filters', { ..._state.filters, ...f }); }
export function setProgress(scanner, pct, file) { /* update scanProgress */ }
export function appendLog(line) { /* append to logLines, trim to 100 */ }
export function selectFinding(f){ _set('selectedFinding', f); }

// Getters
export function getState() { return { ..._state }; }
export function getFilteredFindings() {
  // Applies _state.filters to _state.data.findings
  // Returns sorted, filtered array
}
```

**Rules:**
- State is never mutated directly — always through setters.
- Subscribers receive the new value; they do not receive the old value.
- `getFilteredFindings()` is the only place filter logic lives.

**Commit:** `feat(frontend): state.js — application state manager`

---

### Step 6 — `frontend/js/router.js`

Hash-based routing. Every URL hash maps to a view + optional filter params.

**Supported routes:**

```
#/                          → dashboard view
#/issues                    → issues table, no filter
#/issues?severity=high      → issues table, severity=high
#/issues?scanner=bandit     → issues table, scanner=bandit
#/issues?id=abc12345        → issues table, finding modal open
#/history                   → history list
#/history/2026-05-27T14-30  → history detail for that run
```

**Implementation:**

```javascript
const routes = {
  '/':           () => showView('dashboard'),
  '/issues':     (params) => showView('issues', params),
  '/history':    () => showView('history'),
  '/history/:id':(params) => showView('history', params),
};

function navigate(hash) {
  // Parse hash → route + params
  // Update state.activeView
  // Push to browser history
}

window.addEventListener('hashchange', () => navigate(location.hash));
```

**Rules:**
- The router does not fetch data — it sets filters in state and the view
  components react to state changes.
- Every programmatic navigation uses `navigate()`, never `location.hash =`.
- Direct URL entry (user types a hash) is handled by `hashchange`.
- `#/issues?id=abc12345` opens the finding modal — the router sets
  `state.selectedFinding` and the modal component reacts.

**Commit:** `feat(frontend): router.js — hash-based SPA routing`

---

### Step 7 — `frontend/js/stream.js`

Opens the SSE connection on page load and routes events to state.

```javascript
import * as api from './api.js';
import * as state from './state.js';

export function initStream() {
  const es = api.openStream({
    onStatus:   (data) => state.setStatus(data),
    onProgress: (data) => state.setProgress(data.scanner, data.percent, data.file),
    onLog:      (data) => state.appendLog(data),
    onFinding:  (data) => {
      // Inject finding into state.data without a full reload
      const current = state.getState().data;
      state.setData({
        ...current,
        findings: [...current.findings, data.finding],
      });
    },
    onError: (e) => {
      console.warn('SSE connection error, browser will retry', e);
    },
  });
  return es;
}
```

**Rules:**
- `initStream()` is called once on page load. The `EventSource` handles
  reconnection automatically.
- New findings from `onFinding` are injected into state incrementally —
  the table re-renders the new row without a full data reload.
- `onError` logs a warning; no toast is shown for SSE reconnects (they are
  normal and silent).

**Commit:** `feat(frontend): stream.js — SSE event handler`

---

### Step 8 — `frontend/js/utils.js`

Shared helpers used by every view component.

```javascript
// Severity → CSS class and icon
export function severityClass(severity) {
  return `severity-${severity.toLowerCase()}`;
}
export function severityIcon(severity) {
  return `<img src="assets/icons/${severity.toLowerCase()}.svg" 
               class="severity-icon" alt="${severity}">`;
}

// Relative time ("2 minutes ago")
export function relativeTime(isoString) { /* ... */ }

// Truncate long strings
export function truncate(str, max = 80) { /* ... */ }

// Format finding count with colour coding
export function countBadge(n, severity) {
  return `<span class="badge ${severityClass(severity)}">${n}</span>`;
}

// Escape HTML (used before innerHTML)
export function escapeHtml(str) { /* ... */ }

// Debounce (used for search input)
export function debounce(fn, delay = 200) { /* ... */ }
```

**Rules:**
- No DOM manipulation in `utils.js` — pure functions only.
- `escapeHtml` is used everywhere user-controlled strings are injected into HTML.
  Never skip it.

**Commit:** `feat(frontend): utils.js — shared helpers`

---

### Step 9 — `frontend/js/dashboard.js`

The main overview screen. Rendered into `#view-dashboard`.

**Sub-components:**

**Severity cards (top row):**
```
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 🔴 Critical  │ │ 🟠 High      │ │ 🟡 Medium    │ │ 🟢 Low       │
│     12       │ │     47       │ │     132      │ │     89       │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```
Click on a card → navigate to `#/issues?severity=critical`.

**Issue trend sparkline:**
- Pulls `GET /api/history` to get finding counts across last 10 runs.
- Renders as an inline SVG bar chart (no external library).
- Shows count on hover.

**Top offending files:**
- Derived from `state.data.findings` — group by `finding.file`, count per file.
- Top 6 files shown as horizontal progress bars, scaled to the max count.
- Click → navigate to `#/issues?file={path}`.

**Latest findings table:**
- Most recent 10 findings from `state.data.findings`, sorted by severity.
- Columns: severity icon, scanner badge, title, file:line.
- Click row → open finding detail modal.
- "View all →" link → navigate to `#/issues`.

**Empty state:**
- When `state.data.findings` is empty and `state.status.state` is `"idle"`:
  show onboarding card ("No audit has run yet. Click ▶ Run to start.").

**Commit:** `feat(frontend): dashboard.js — overview screen`

---

### Step 10 — `frontend/js/settings.js`

Settings modal + first-run onboarding wizard.

**Settings modal (`#modal-settings`):**

```
┌─────────────────────────────────────┐
│ Settings                        [✕] │
├─────────────────────────────────────┤
│ Project Path  [/home/user/myapp  ] [Browse] │
│ API Key       [••••••••••••••••  ] [Test]   │
│ AI Provider   [● Gemini  ○ Claude]          │
│ AI Model      [gemini-2.5-pro    ▼]         │
├─────────────────────────────────────┤
│ Scanners                            │
│ [✓] Bandit    [✓] Vulture  [✓] Radon│
│ [✓] pip-audit [✓] Lizard  [○] Semgrep│
├─────────────────────────────────────┤
│              [Cancel]  [Save]       │
└─────────────────────────────────────┘
```

**First-run onboarding wizard:**
Shown when `GET /api/settings` returns no `project_path`.
Three steps:
1. "Where is your project?" — path input with validation.
2. "Add an API key for AI recommendations?" — optional, skippable.
3. "You're ready. Click Run to start your first audit."

**Rules:**
- `Browse` button uses `<input type="file" webkitdirectory>` hidden, triggered on click.
- `Test` button for API key calls a lightweight validation (try `GET /api/status`
  with the key; if server responds it's reachable, show ✓).
- On `Save`: call `api.saveSettings()`, close modal, show success toast.
- On save error: show inline error below the field that failed validation.
- The wizard advances with `Next` and allows `Back` — state is local to the
  component, not in `state.js`.

**Commit:** `feat(frontend): settings.js — settings modal and onboarding wizard`

---

### Step 11 — `frontend/js/command-palette.js`

`CMD+K` global command palette.

**Appearance:**
```
┌──────────────────────────────────────────┐
│  🔍 Type a command or search findings... │
├──────────────────────────────────────────┤
│  ▶ Run Audit                             │
│  ⏹ Cancel Audit                          │
│  ⚙ Open Settings                        │
│  📋 View All Issues                      │
│  📈 View History                         │
│  🌙 Toggle Theme                         │
│  ── Recent findings ──                   │
│  🔴 Hardcoded password in config.py:42  │
│  🟠 Unused function `old_handler`        │
└──────────────────────────────────────────┘
```

**Keyboard behaviour:**
- `CMD+K` / `CTRL+K` → open, focus input.
- `ESC` → close.
- `↑` / `↓` → navigate items.
- `Enter` → execute highlighted item.
- Typing filters items by fuzzy match on label text.

**Implementation:**
```javascript
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    togglePalette();
  }
});
```

**Commands:**
- "Run Audit" → `api.startRun()`.
- "Cancel Audit" → `api.cancelRun()`.
- "Open Settings" → open settings modal.
- "View All Issues" → `router.navigate('#/issues')`.
- "Toggle Theme" → flip `data-theme` attribute.
- Finding items → `state.selectFinding(f)` → open finding modal.

**Rules:**
- Finding items in the palette are drawn from `state.getFilteredFindings()`,
  limited to the 5 most severe.
- The palette is rendered into `#command-palette` which is always in the DOM
  (just hidden). No dynamic creation on open.

**Commit:** `feat(frontend): command-palette.js — CMD+K global palette`

---

### Step 12 — Progress panel (wired in `stream.js` + `dashboard.js`)

The bottom panel that slides up during an audit.

```
┌──────────────────────────────────────────────────────────┐
│  🔄 Audit Running — /home/user/myapp/       [Cancel]      │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ ✅ discovery    ████████████████████  100%            │ │
│  │ 🔄 bandit       ████████████░░░░░░░░   62%  auth.py  │ │
│  │ ⏳ vulture      ░░░░░░░░░░░░░░░░░░░░    0%           │ │
│  └──────────────────────────────────────────────────────┘ │
│  [12:34:05] Starting Bandit security scan                  │
│  [12:34:02] Found 5 issues in config.py                   │
└──────────────────────────────────────────────────────────┘
```

**State-driven:**
- Panel is `hidden` when `status.state === "idle"` or `"completed"`.
- Panel is `visible` (slides up) when `status.state === "running"`.
- Each `PROGRESS` SSE event updates `state.scanProgress[scanner]`.
- Each `LOG` SSE event appends to `state.logLines` (capped at 100 lines).
- The log is a scrolling `<div>` with `overflow-y: auto` and `font-family: var(--font-mono)`.

**Commit:** `feat(frontend): progress panel — live audit feedback`  
*(This commit is part of `dashboard.js` wiring — no separate file needed)*

---

### Step 13 — Upgrade static file serving in `api/server.py`

Replace the Phase 2 "Frontend coming in Phase 4" placeholder with real static serving.

```python
# In create_app():
frontend_dir = Path(__file__).parent.parent / "frontend"

# Replace placeholder routes with:
app.router.add_get('/', lambda r: serve_file(frontend_dir / 'index.html'))
app.router.add_static('/assets', frontend_dir / 'assets')
app.router.add_static('/css',    frontend_dir / 'css')
app.router.add_static('/js',     frontend_dir / 'js')

# SPA fallback: any unmatched GET → index.html (for direct hash navigation)
app.router.add_get('/{tail:.*}', lambda r: serve_file(frontend_dir / 'index.html'))
```

```python
async def serve_file(path: Path) -> web.Response:
    if not path.exists():
        raise web.HTTPNotFound()
    content_type = _mime_type(path.suffix)
    return web.Response(body=path.read_bytes(), content_type=content_type)
```

**Rules:**
- `add_static` for CSS/JS/assets enables proper `Content-Type` and
  `Last-Modified` headers (aiohttp handles this automatically).
- The SPA fallback must come last (lowest priority route) — never before the
  `/api/*` routes.
- `_mime_type` maps `.html → text/html`, `.js → text/javascript`,
  `.css → text/css`, `.svg → image/svg+xml`.

**Update `tests/test_frontend_serve.py`:**
- `GET /` returns 200 with `text/html`.
- `GET /css/variables.css` returns 200 with `text/css`.
- `GET /js/api.js` returns 200 with `text/javascript`.
- `GET /nonexistent-route` returns the SPA fallback (`index.html`), not 404.
- `GET /api/status` still returns JSON (API routes not shadowed by static serving).

**Commit:** `feat(api): upgrade static file serving for frontend`

---

### Step 14 — Final commit and tag

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q        # must exit 0
ruff check .
git add -A
git commit -m "feat: Phase 4 complete — frontend SPA"
git tag v0.4.0
```

Note: `mypy --strict` does not apply to JavaScript files. Python-side changes
(Step 13) must still pass mypy.

---

## What Phase 4 Does NOT Include

| Excluded | Reason |
|----------|--------|
| Issues table full implementation | Phase 5 — the table needs the scoring system and fix queue to be useful |
| Run history diff view | Phase 6 |
| AI recommendations tab | Phase 7 |
| Coupling map / graph visualization | Phase 5 |
| Scanner toggle per-run overrides | Phase 5 |
| Finding detail modal full implementation | Phase 5 (needs code snippet viewer) |
| Caching / `force_rescan` UI toggle | Phase 5/6 |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Vanilla ES6, no framework | No build step, no bundler, no dependency churn. The SPA is simple enough that a framework would add more complexity than it removes |
| CSS custom properties for theming | One attribute on `<html>` toggles the entire theme. No class toggling on every element |
| Hash-based routing | No server-side routing needed. Works with the static file catch-all. Deep links work without a server restart |
| State manager (not Redux) | A simple pub-sub over a plain object is sufficient. Redux or Zustand would be overkill for a single-developer tool |
| Inline SVG sparkline | No chart library for the trend chart — an inline SVG with a few `<rect>` elements avoids a 200kb dependency |
| Progress panel always in DOM | CSS transition from `hidden` to `visible` is smoother than dynamically inserting/removing the element |
| `EventSource` native reconnect | The browser handles `Last-Event-ID` automatically. No manual reconnection logic needed |

---

## Definition of Done — Phase 4

- [ ] `python server.py` then open `http://localhost:8421` → the dashboard loads
- [ ] Dark theme is default; light theme toggle works and persists
- [ ] `CMD+K` / `CTRL+K` opens command palette; `ESC` closes it
- [ ] "Run Audit" button starts a job; progress panel slides up
- [ ] Progress panel shows per-scanner progress bars updating in real time via SSE
- [ ] Log lines appear in the progress panel as they stream in
- [ ] After completion, severity cards show correct counts
- [ ] Clicking a severity card navigates to `#/issues?severity=X`
- [ ] Top offending files list is populated
- [ ] Latest findings table shows rows; clicking a row opens a finding modal
- [ ] Empty state is shown when no audit has run
- [ ] Settings modal opens, saves, and closes correctly
- [ ] First-run onboarding wizard shown when no project path is configured
- [ ] `GET /css/variables.css` → HTTP 200 (static files served)
- [ ] `GET /api/status` → JSON (API not shadowed)
- [ ] `pytest --tb=short -q` exits 0
- [ ] `ruff check .` exits 0
- [ ] `git tag v0.4.0` exists

---

*Plan written: 2026-05-28 | Follows: Phase 3.2 (`v0.3.2`) | Precedes: Phase 5 (Scoring, Fix Queue, Graph)*
