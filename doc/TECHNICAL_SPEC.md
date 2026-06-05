# Nexus Audit V3 — Complete Technical Specification
**Version:** 1.0  
**Date:** 2026-06-04  
**Purpose:** Single source of truth for all implementation decisions.
Before writing any code, an implementor must read this entire document.
This document supersedes all previous implementation plans.

---

## 1. What This System Is

A local-first developer audit tool. One command starts it. A browser opens.
The developer clicks Run. Real-time results appear. That is the entire user
story. Nothing connects to the internet except optional AI calls and scanner
CVE lookups.

**Two processes, one machine:**
```
[ Browser ]  ←HTTP/SSE→  [ Python server on 127.0.0.1:8421 ]
```
No database. No message queue. No Redis. No worker processes.
Everything lives in one Python asyncio event loop.

---

## 2. System Layers — What They Are and What They Are Not

```
┌─────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                  │
│  frontend/  — pure HTML + CSS + vanilla ES modules  │
│  Served by Python as static files                   │
│  Talks ONLY to /api/* endpoints                     │
├─────────────────────────────────────────────────────┤
│  API LAYER                                           │
│  api/  — aiohttp route handlers                     │
│  Translates HTTP ↔ Python objects                   │
│  No business logic. No direct scanner calls.         │
├─────────────────────────────────────────────────────┤
│  ORCHESTRATION LAYER                                 │
│  orchestrator.py — single class, single job          │
│  Owns: job lifecycle, scanner dispatch, result write │
│  Uses: plugins/, core/dna_builder, core/rules_engine │
├─────────────────────────────────────────────────────┤
│  INTELLIGENCE LAYER                                  │
│  core/ — pure Python, no HTTP, no HTML               │
│  dna_builder, rules_engine, scoring, coupling, etc.  │
├─────────────────────────────────────────────────────┤
│  SCANNER LAYER                                       │
│  plugins/ — one class per tool                      │
│  Each scanner: receives a Path, returns [Finding]   │
│  No scanner knows about other scanners               │
└─────────────────────────────────────────────────────┘
```

**Hard rules — these are never violated:**
- Layers only communicate downward. `api/` never imports from `plugins/`.
- `plugins/` never imports from `api/` or `orchestrator.py`.
- `core/` modules never import from `api/`, `orchestrator.py`, or `plugins/`.
- `frontend/` talks only to `/api/*`. Never imports Python.

---

## 3. The Single Source of Truth: `audit_data_complete.json`

Every component in the system revolves around this file. The orchestrator
writes it. The API reads it. The frontend displays it. Its schema is fixed.

```json
{
  "metadata": {
    "job_id": "string (uuid4)",
    "project_path": "string (absolute path)",
    "started_at": "string (ISO 8601 UTC)",
    "finished_at": "string (ISO 8601 UTC)",
    "total_findings": "integer",
    "total_violations": "integer",
    "git_context": {
      "remote_url": "string | null",
      "branch": "string | null",
      "commit": "string | null"
    }
  },

  "findings": [
    {
      "id": "string (16-char hex sha256)",
      "scanner": "string",
      "file": "string (relative path from project root)",
      "line": "integer",
      "column": "integer",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW | INFO",
      "category": "security | quality | performance | dependency | architecture",
      "title": "string",
      "description": "string",
      "suggestion": "string | null",
      "cwe": "string | null",
      "cvss_score": "number | null",
      "persistence": "new | persistent | intermittent | resolved",
      "fix_status": "open | in_progress | done | snoozed"
    }
  ],

  "apps": {
    "app_name": {
      "score": "number (0.0 to 100.0)",
      "is_hub": "boolean",
      "finding_count": "integer",
      "violation_count": "integer",
      "security_high": "integer",
      "security_medium": "integer",
      "security_low": "integer",
      "dead_code_count": "integer",
      "ghost_file_count": "integer",
      "avg_complexity": "number",
      "penalty_breakdown": {
        "violations": "number",
        "security": "number",
        "complexity": "number",
        "dead_code": "number",
        "ghost_files": "number",
        "hub_bonus": "number"
      }
    }
  },

  "fleet_average": "number (0.0 to 100.0)",

  "coupling_matrix": {
    "apps": ["string"],
    "matrix": [[0]],
    "details": {
      "source_app|target_app": [
        {"from": "string", "to": "string", "file": "string", "line": "integer"}
      ]
    }
  },

  "dna": {
    "module_path": {
      "file_path": "string",
      "relative_path": "string",
      "app": "string",
      "imports": ["string"],
      "defined_names": ["string"],
      "is_test": "boolean",
      "lines_of_code": "integer"
    }
  },

  "config_health": [
    {
      "id": "string",
      "file": "string",
      "check": "string",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW",
      "passed": "boolean",
      "message": "string"
    }
  ],

  "dependency_scan": [
    {
      "package": "string",
      "installed_version": "string",
      "latest_version": "string | null",
      "vulnerabilities": [
        {
          "cve_id": "string",
          "description": "string",
          "severity": "string",
          "fix_version": "string | null"
        }
      ]
    }
  ],

  "recommendations": [
    {
      "id": "string",
      "type": "violation | health | upgrade | cve",
      "app": "string | null",
      "title": "string",
      "body": "string",
      "priority": "high | medium | low",
      "fix_status": "open | in_progress | done | snoozed"
    }
  ],

  "change_summary": {
    "first_run": "boolean",
    "new_violations": "integer",
    "resolved_violations": "integer",
    "score_deltas": {"app_name": "number"}
  },

  "rules_summary": [
    {
      "rule_id": "string",
      "rule_name": "string",
      "findings_count": "integer"
    }
  ]
}
```

**This schema is the contract.** The orchestrator MUST write every field.
The API MUST return every field. The frontend MUST handle every field,
including null/empty values gracefully.

---

## 4. Backend Architecture

### 4.1 Static File Serving — The Correct Pattern

The single biggest source of subtle bugs is how aiohttp serves the SPA.
The correct pattern, tested against aiohttp docs:

```python
# In api/server.py create_app()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# API routes registered FIRST (highest priority)
app.router.add_get('/api/status', routes_data.get_status)
# ... all other /api/* routes ...

# Static asset directories (CSS, JS, assets)
# These return 404 if the file does not exist — correct behavior
app.router.add_static('/static/css',    FRONTEND_DIR / 'css')
app.router.add_static('/static/js',     FRONTEND_DIR / 'js')
app.router.add_static('/static/assets', FRONTEND_DIR / 'assets')

# SPA catch-all — MUST be last
# Any path not matched above returns index.html
async def spa_fallback(request: web.Request) -> web.FileResponse:
    return web.FileResponse(FRONTEND_DIR / 'index.html')

app.router.add_get('/', spa_fallback)
app.router.add_get('/{tail:.*}', spa_fallback)
```

**Why this order matters:** aiohttp resolves routes in registration order.
If the SPA fallback is registered before `/api/*`, ALL requests return index.html.
API routes first. Static directories second. SPA fallback last.

**Why `/static/` prefix on assets:** The HTML file references
`/static/css/variables.css` not `/css/variables.css`. The prefix makes the
router unambiguous — requests to `/static/*` are never caught by the fallback.

### 4.2 SSE Architecture — The Correct Pattern

The SSE endpoint has two responsibilities: replay history on connect,
then stream new events in real time.

**The correct history model:**

The `EventBus` maintains a ring buffer of the last N events as
`(sequential_id, Event)` tuples. The `sequential_id` is a monotonically
increasing integer that starts at 1 when the server starts and NEVER resets.

```python
# EventBus internal state
_event_counter: int = 0          # never resets
_history: deque[tuple[int, Event]]  # maxlen=500, stores (id, event)
```

When an event is published:
```python
self._event_counter += 1
self._history.append((self._event_counter, event))
```

When a client connects with `Last-Event-ID: 42`:
```python
since_id = int(request.headers.get("Last-Event-ID", "0"))
# Return all events with id > since_id
missed = [(eid, ev) for eid, ev in self._history if eid > since_id]
```

When a client connects fresh (no `Last-Event-ID`):
```python
since_id = 0  # returns full history
```

**The SSE wire format — exact bytes:**
```
id: 47\n
event: progress\n
data: {"scanner":"bandit","percent":62,"file":"auth.py"}\n
\n
```
Each event is terminated by a BLANK LINE (`\n\n`). No exceptions.

**The per-connection queue pattern:**
Each SSE connection creates its own `asyncio.Queue`. The bus callback puts
events into that queue. The send loop drains it. This decouples publisher
speed from network speed and supports multiple simultaneous browser tabs.

```python
queue: asyncio.Queue[tuple[int, Event]] = asyncio.Queue()

async def on_event(event_id: int, event: Event) -> None:
    await queue.put((event_id, event))

# Subscribe once per EventType — 4 subscriptions total
tokens = [bus.subscribe(et, lambda ev, eid=...: on_event(eid, ev)) for et in EventType]
```

Wait — this pattern has a problem: the lambda captures `eid` from bus internals.
The correct pattern is to subscribe to a callback that receives the (id, event)
directly. The `bus.subscribe` signature must be changed to pass the event_id
to the callback alongside the event, OR the SSE route uses `bus.subscribe_all`
which receives every event with its ID.

**Correct bus interface for SSE:**
```python
class EventBus:
    def subscribe_all(self, callback: Callable[[int, Event], Awaitable]) -> str:
        """Subscribe to ALL event types. Callback receives (event_id, event)."""
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], Awaitable]) -> str:
        """Subscribe to one event type. Callback receives event only."""
```

The SSE route uses `subscribe_all`. All other callers use `subscribe`.

### 4.3 Orchestrator — The Exact Execution Order

```
async def _run_job(job, settings):

    # ── Phase 0: Source sync (if enabled in settings) ──────────────
    working_path = await source_sync.sync(settings, bus)
    # working_path is either the synced copy or settings.project_path

    # ── Phase 1: Build DNA ──────────────────────────────────────────
    # DNA is ALWAYS built fully, even in fast mode.
    # The module graph is cheap to build and required for rules evaluation.
    await bus.publish_log("info", "Building module registry...")
    dna = dna_builder.build(working_path)
    await bus.publish_progress("dna", 100, f"{len(dna.modules)} modules")

    # ── Phase 1.5: Fast mode file filter (optional) ─────────────────
    # fast_mode is set by POST /api/run body {"fast": true} OR settings.force_rescan=false
    # When fast_mode=True: get git-changed files and pass as a filter to scanners.
    # Scanners that receive a non-None file_filter skip unchanged files.
    # DNA is still full (built from all files above) — only scanner input is filtered.
    # If git is unavailable, fast_mode falls back to full scan with a log warning.
    # fast_mode=False (default): file_filter=None, scanners see all files.
    fast_mode = job.metadata.get("fast", False)   # set from POST /api/run body
    file_filter: list[Path] | None = None
    if fast_mode:
        file_filter = fast_check.get_changed_files(working_path)
        if file_filter is None:
            await bus.publish_log("warning", "Fast mode: git unavailable, running full scan")
        else:
            await bus.publish_log("info", f"Fast mode: {len(file_filter)} changed files")

    # ── Phase 2: Load rules ─────────────────────────────────────────
    rules_file = working_path / "audit_rules.yaml"
    if not rules_file.exists():
        rules_file = Path(__file__).parent / "default_rules.yaml"
    engine = RulesEngine(rules_file)

    # ── Phase 3: Run scanners in parallel ───────────────────────────
    registry = PluginRegistry(Path("plugins"))
    registry.load()
    scanner_tasks = []
    for name, enabled in settings.scanners.items():
        if not enabled:
            continue
        cls = registry.get(name)
        if cls is None:
            await bus.publish_log("warning", f"Scanner not found: {name}")
            continue
        config = settings.scanner_configs.get(name, {})
        if file_filter is not None:
            config = {**config, "_file_filter": [str(f) for f in file_filter]}
        # Scanner checks for "_file_filter" in config and restricts its file list.
        # If "_file_filter" is absent or None, scanner scans everything.
        # force_rescan=True in settings bypasses dep_cache (handled inside safety_plugin).
        config["_force_rescan"] = settings.force_rescan
        task = asyncio.create_task(
            _run_single_scanner(cls, working_path, config, bus)
        )
        scanner_tasks.append((name, task))
    
    results = await asyncio.gather(
        *[t for _, t in scanner_tasks], return_exceptions=True
    )
    scanner_findings: list[Finding] = []
    for i, result in enumerate(results):
        if isinstance(result, list):
            scanner_findings.extend(result)
            job.scan_results.append(ScanResult(
                scanner=scanner_tasks[i][0],
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                findings=result
            ))
        elif isinstance(result, Exception):
            await bus.publish_log("error", f"Scanner failed: {result}")

    # ── Phase 4: Run rules engine ───────────────────────────────────
    rule_findings = await engine.evaluate(dna, scanner_findings, bus)
    all_findings = scanner_findings + rule_findings

    # ── Phase 5: Score apps ─────────────────────────────────────────
    scores = scoring_engine.calculate_scores(dna, all_findings, engine.scoring_config)

    # ── Phase 6: Build coupling matrix ─────────────────────────────
    coupling = coupling.build_coupling_matrix(
        violations=[f for f in all_findings if f.category.value == "architecture"],
        dna=dna
    )

    # ── Phase 7: Timeline & persistence ────────────────────────────
    history_dir = working_path / "audit_history"
    persistence = timeline.compute_violation_persistence(history_dir, all_findings)
    trends = timeline.load_score_history(history_dir)

    # ── Phase 8: Fix queue sync ─────────────────────────────────────
    queue_file = working_path / ".nexus_fix_queue.json"
    fq = FixQueue(queue_file)
    sync_result = fq.sync(all_findings)

    # ── Phase 9: Git context ────────────────────────────────────────
    git_ctx = await git_context.get_git_context(working_path)
    job.git_context = git_ctx

    # ── Phase 10: AI recommendations (if enabled) ──────────────────
    recommendations = []
    if settings.ai_enabled and settings.api_key:
        recommendations = await ai.generate_recommendations(
            all_findings, scores, engine.arch_context, settings, bus
        )

    # ── Phase 11: Write result ──────────────────────────────────────
    result = _build_result(
        job, all_findings, scores, coupling, dna, sync_result,
        persistence, recommendations, git_ctx
    )
    await write_json(Path("audit_data_complete.json"), result)
    history_file = history_dir / f"{job.started_at.strftime('%Y%m%dT%H%M%S')}.json"
    history_dir.mkdir(exist_ok=True)
    await write_json(history_file, result)

    # ── Phase 12: Markdown report ───────────────────────────────────
    markdown_report.generate(job, scores, git_ctx, working_path / "audit_report.md")

    # ── Phase 13: Complete ──────────────────────────────────────────
    job.state = "completed"
    job.finished_at = datetime.now(UTC)
    await bus.publish_status("completed", job.id)
```

### 4.4 Finding Serialization — The Only Correct Method

**Never use `finding.__dict__` or `dataclasses.asdict()` directly.**
Both will embed Python enum objects that crash `json.dumps`.

The single canonical function for serializing a Finding to dict:

```python
def finding_to_dict(f: Finding, persistence: str = "new", fix_status: str = "open") -> dict:
    return {
        "id":          f.id,
        "scanner":     f.scanner,
        "file":        f.file,
        "line":        f.line,
        "column":      f.column,
        "severity":    f.severity.name,     # "HIGH" not 4
        "category":    f.category.value,    # "security" not <Category.SECURITY>
        "title":       f.title,
        "description": f.description,
        "suggestion":  f.suggestion,
        "cwe":         f.cwe,
        "cvss_score":  f.cvss_score,
        "persistence": persistence,
        "fix_status":  fix_status,
    }
```

This function lives in `core/models.py` alongside the `Finding` dataclass.
Every component that serializes a Finding uses this function. No exceptions.

### 4.5 API Contract — What `/api/data` Returns

`GET /api/data` reads `audit_data_complete.json` and returns it AS-IS.
No transformation. No renaming. The file is the response.

```python
async def get_data(request):
    data = await read_json(Path("audit_data_complete.json"))
    if data is None:
        return web.json_response(_EMPTY_DATA_RESPONSE)
    return web.json_response(data)

_EMPTY_DATA_RESPONSE = {
    "metadata": {"job_id": None, "project_path": "", "started_at": None,
                 "finished_at": None, "total_findings": 0, "total_violations": 0,
                 "git_context": {}},
    "findings": [],
    "apps": {},
    "fleet_average": 0.0,
    "coupling_matrix": {"apps": [], "matrix": [], "details": {}},
    "dna": {},
    "config_health": [],
    "dependency_scan": [],
    "recommendations": [],
    "change_summary": {"first_run": True, "new_violations": 0,
                      "resolved_violations": 0, "score_deltas": {}},
    "rules_summary": []
}
```

**Why no transformation:** Every transformation in `routes_data.py` is a bug
waiting to happen. The frontend schema and the file schema must be identical.

---

## 5. Frontend Architecture

### 5.1 File Structure — Final, No More Changes

```
frontend/
├── index.html               — shell, navigation, ALL view divs pre-rendered
├── css/
│   ├── variables.css        — ALL design tokens (colors, spacing, fonts)
│   ├── layout.css           — page skeleton, topbar, sidebar, main, progress panel
│   ├── components.css       — buttons, cards, badges, tables, modals, forms
│   └── themes.css           — [data-theme="light"] overrides only
└── js/
    ├── store.js             — single reactive store (Proxy-based)
    ├── api.js               — all fetch/SSE, nothing else
    ├── stream.js            — opens SSE, routes events into store
    ├── router.js            — hash routing, shows/hides views
    ├── main.js              — initialisation only, wires everything
    ├── utils.js             — pure functions: format, escape, colors
    └── views/
        ├── dashboard.js     — severity cards, app scores, latest findings
        ├── issues.js        — sortable/filterable full findings table
        ├── violations.js    — architecture violations table
        ├── security.js      — security findings
        ├── dependencies.js  — dependency scan results
        ├── recommendations.js — AI fix cards + fix queue buttons
        ├── graph.js         — vis-network dependency graph
        ├── trends.js        — score history chart
        ├── coupling.js      — NxN heatmap
        ├── manifest.js      — module registry table
        ├── config-health.js — django/config audit
        └── settings.js      — settings form, rules editor, app profile
```

**Rules:**
- `views/*.js` reads ONLY from `store.js`. Never calls `api.js` directly.
- `stream.js` is the ONLY file that calls `api.openStream()`.
- `main.js` is the ONLY file that calls `api.getData()`, `api.getStatus()`, `api.getSettings()` at startup.
- `store.js` is the single source of truth. There are no other stateful variables.

### 5.2 Store Design — Proxy-Based Reactive State

The store uses a JavaScript `Proxy` to detect mutations and notify subscribers
automatically. This is the pattern used by Vue 3's reactivity system, simplified.

```javascript
// js/store.js

const _initial = {
  // Server state (from /api/status and SSE)
  status:        { state: 'idle', job_id: null },

  // Audit data (from /api/data)
  metadata:      { job_id: null, project_path: '', started_at: null,
                   finished_at: null, total_findings: 0, git_context: {} },
  findings:      [],   // flat list, all findings
  apps:          {},   // { app_name: AppScore }
  fleet_average: 0.0,
  coupling:      { apps: [], matrix: [], details: {} },
  dna:           {},
  config_health: [],
  dependencies:  [],
  recommendations: [],
  change_summary: { first_run: true, new_violations: 0, resolved_violations: 0, score_deltas: {} },
  rules_summary:  [],

  // UI state (local only, not from server)
  activeView:    'dashboard',
  filters:       { severity: null, scanner: null, category: null, search: '' },
  selectedFinding: null,
  scanProgress:  {},   // { scanner_name: { percent, file } }
  logLines:      [],   // last 200 entries
  settings:      {},
};

const _subscribers = new Map();   // key → Set<callback>

function _notify(key) {
  (_subscribers.get(key) || []).forEach(cb => cb(_state[key]));
}

// The reactive state object — any property assignment triggers _notify
const _state = new Proxy({ ..._initial }, {
  set(target, key, value) {
    target[key] = value;
    _notify(key);
    return true;
  }
});

// Public API
export function get(key) { return _state[key]; }

export function set(key, value) {
  _state[key] = value;   // triggers Proxy setter → _notify
}

export function subscribe(key, callback) {
  if (!_subscribers.has(key)) _subscribers.set(key, new Set());
  _subscribers.get(key).add(callback);
  return () => _subscribers.get(key).delete(callback);  // returns unsubscribe fn
}

// Convenience setters
export function setAuditData(data) {
  // Called once when /api/data returns
  // Maps the exact JSON schema to store keys
  set('metadata',      data.metadata       ?? _initial.metadata);
  set('findings',      data.findings       ?? []);
  set('apps',          data.apps           ?? {});
  set('fleet_average', data.fleet_average  ?? 0);
  set('coupling',      data.coupling_matrix ?? { apps: [], matrix: [], details: {} });
  set('dna',           data.dna            ?? {});
  set('config_health', data.config_health  ?? []);
  set('dependencies',  data.dependency_scan ?? []);
  set('recommendations', data.recommendations ?? []);
  set('change_summary',  data.change_summary  ?? _initial.change_summary);
  set('rules_summary',   data.rules_summary   ?? []);
}

export function appendFinding(finding) {
  // Called when SSE 'finding' event arrives during a live scan
  set('findings', [...get('findings'), finding]);
}

export function setProgress(scanner, percent, file) {
  const current = { ...(get('scanProgress') || {}) };
  current[scanner] = { percent, file };
  set('scanProgress', current);
}

export function appendLog(level, message) {
  const lines = get('logLines');
  const updated = [...lines, { level, message, time: new Date().toISOString() }];
  set('logLines', updated.slice(-200));   // keep last 200
}

export function getFilteredFindings() {
  const filters = get('filters');
  return get('findings').filter(f => {
    if (filters.severity && f.severity !== filters.severity) return false;
    if (filters.scanner  && f.scanner  !== filters.scanner)  return false;
    if (filters.category && f.category !== filters.category) return false;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      if (!f.title.toLowerCase().includes(q) &&
          !f.file.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}
```

**Why Proxy:** When any property of `_state` is assigned, the Proxy intercepts
it and calls `_notify` automatically. A view subscribes to `'findings'` and
is called whenever `findings` changes — whether from a full data load or a
streaming finding injected during a live scan.

### 5.3 `index.html` — Exact Shell Structure

The HTML shell pre-renders all view containers. The router shows/hides them
by toggling the `hidden` class. No DOM creation in the router.

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus Audit — Command Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/css/variables.css">
  <link rel="stylesheet" href="/static/css/layout.css">
  <link rel="stylesheet" href="/static/css/components.css">
  <link rel="stylesheet" href="/static/css/themes.css">
  <script type="module" src="/static/js/main.js"></script>
</head>
<body>

<header id="topbar">
  <div class="topbar-left">
    <span class="app-name">⚡ Nexus Audit</span>
    <span id="status-badge" class="badge badge-idle">idle</span>
  </div>
  <nav id="tab-nav">
    <button class="tab-btn active" data-view="dashboard">Dashboard</button>
    <button class="tab-btn" data-view="issues">Issues</button>
    <button class="tab-btn" data-view="violations">Violations</button>
    <button class="tab-btn" data-view="security">Security</button>
    <button class="tab-btn" data-view="dependencies">Dependencies</button>
    <button class="tab-btn" data-view="recommendations">AI Fixes</button>
    <button class="tab-btn" data-view="graph">Graph</button>
    <button class="tab-btn" data-view="trends">Trends</button>
    <button class="tab-btn" data-view="coupling">Coupling</button>
    <button class="tab-btn" data-view="manifest">Manifest</button>
    <button class="tab-btn" data-view="config-health">Config</button>
  </nav>
  <div class="topbar-right">
    <button id="btn-theme" class="icon-btn" title="Toggle theme">🌙</button>
    <button id="btn-settings" class="icon-btn" title="Settings">⚙️</button>
    <button id="btn-run" class="btn-primary">▶ Run</button>
    <button id="btn-cancel" class="btn-danger hidden">⏹ Cancel</button>
  </div>
</header>

<main id="app-main">
  <div id="view-dashboard"     class="view active"></div>
  <div id="view-issues"        class="view hidden"></div>
  <div id="view-violations"    class="view hidden"></div>
  <div id="view-security"      class="view hidden"></div>
  <div id="view-dependencies"  class="view hidden"></div>
  <div id="view-recommendations" class="view hidden"></div>
  <div id="view-graph"         class="view hidden"></div>
  <div id="view-trends"        class="view hidden"></div>
  <div id="view-coupling"      class="view hidden"></div>
  <div id="view-manifest"      class="view hidden"></div>
  <div id="view-config-health" class="view hidden"></div>
  <div id="view-settings"      class="view hidden"></div>
</main>

<div id="progress-panel" class="hidden">
  <div class="progress-header">
    <span id="progress-title">Audit Running</span>
    <button id="btn-cancel-panel" class="btn-danger-sm">Cancel</button>
  </div>
  <div id="scanner-bars"></div>
  <div id="log-output"></div>
</div>

<div id="modal-overlay" class="hidden"></div>
<div id="modal-container" class="hidden"></div>

</body>
</html>
```

### 5.4 Router — Hash-Based, View Toggle Only

The router is NOT responsible for loading data. It only shows/hides view divs
and updates the active tab button. Data loading is the view's responsibility.

```javascript
// js/router.js
import * as store from './store.js';

const VIEWS = ['dashboard','issues','violations','security','dependencies',
               'recommendations','graph','trends','coupling','manifest',
               'config-health','settings'];

export function navigate(viewName) {
  if (!VIEWS.includes(viewName)) viewName = 'dashboard';
  store.set('activeView', viewName);

  // Show/hide view divs
  VIEWS.forEach(v => {
    document.getElementById(`view-${v}`)?.classList.toggle('hidden', v !== viewName);
  });

  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });

  // Update URL hash without triggering hashchange
  history.replaceState(null, '', `#/${viewName}`);
}

export function init() {
  // Wire tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.view));
  });

  // Handle direct navigation or page refresh
  window.addEventListener('hashchange', () => {
    const view = location.hash.replace('#/', '') || 'dashboard';
    navigate(view);
  });

  // Initial view from URL hash
  const initial = location.hash.replace('#/', '') || 'dashboard';
  navigate(initial);
}
```

### 5.5 `main.js` — Wiring Only, No Logic

```javascript
// js/main.js — this file does nothing except wire things together

import * as store from './store.js';
import * as api   from './api.js';
import * as router from './router.js';
import { initStream } from './stream.js';
import { initDashboard } from './views/dashboard.js';
import { initIssues } from './views/issues.js';
// ... import all other views ...

async function init() {
  // 1. Wire router
  router.init();

  // 2. Wire theme toggle
  document.getElementById('btn-theme').addEventListener('click', toggleTheme);

  // 3. Wire run/cancel buttons
  document.getElementById('btn-run').addEventListener('click', handleRun);
  document.getElementById('btn-cancel').addEventListener('click', handleCancel);
  document.getElementById('btn-cancel-panel').addEventListener('click', handleCancel);

  // 4. Wire settings button
  document.getElementById('btn-settings').addEventListener('click', () => router.navigate('settings'));

  // 5. Wire tab update from store
  store.subscribe('status', updateTopbarFromStatus);

  // 6. Wire progress panel from store
  store.subscribe('scanProgress', updateProgressBars);
  store.subscribe('logLines', updateLogOutput);

  // 7. Init all views (each view registers its own store subscriptions)
  initDashboard();
  initIssues();
  // ... init all other views ...

  // 8. Start SSE stream
  initStream();

  // 9. Load initial data
  try {
    const [statusData, auditData, settingsData] = await Promise.all([
      api.getStatus(),
      api.getData(),
      api.getSettings(),
    ]);
    store.set('status', statusData);
    store.setAuditData(auditData);
    store.set('settings', settingsData);
    updateTopbarFromStatus(statusData);
  } catch (err) {
    console.error('Failed to load initial data:', err);
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('nexus-theme', next);
}

async function handleRun() {
  try {
    store.set('logLines', []);
    store.set('scanProgress', {});
    document.getElementById('progress-panel').classList.remove('hidden');
    await api.startRun();
  } catch (err) {
    alert('Failed to start: ' + (err.message || 'unknown error'));
  }
}

async function handleCancel() {
  try { await api.cancelRun(); } catch (err) {}
}

function updateTopbarFromStatus(status) {
  const badge = document.getElementById('status-badge');
  badge.textContent = status.state;
  badge.className = `badge badge-${status.state}`;

  document.getElementById('btn-run').classList.toggle('hidden', status.state === 'running');
  document.getElementById('btn-cancel').classList.toggle('hidden', status.state !== 'running');

  if (status.state === 'completed' || status.state === 'failed' || status.state === 'cancelled') {
    setTimeout(async () => {
      document.getElementById('progress-panel').classList.add('hidden');
      // Reload audit data into store — this triggers all view re-renders automatically
      try {
        const data = await api.getData();
        store.setAuditData(data);
      } catch (err) {}
    }, 1500);
  }
}

function updateProgressBars(progress) {
  const container = document.getElementById('scanner-bars');
  container.innerHTML = Object.entries(progress).map(([scanner, p]) => `
    <div class="scanner-bar">
      <span class="scanner-name">${scanner}</span>
      <div class="progress-track">
        <div class="progress-fill" style="width:${p.percent}%"></div>
      </div>
      <span class="progress-pct">${p.percent}%</span>
      <span class="progress-file">${p.file || ''}</span>
    </div>
  `).join('');
}

function updateLogOutput(lines) {
  const el = document.getElementById('log-output');
  el.innerHTML = lines.slice(-50).map(l =>
    `<div class="log-line log-${l.level}">${escapeHtml(l.message)}</div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Restore saved theme
const savedTheme = localStorage.getItem('nexus-theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

document.addEventListener('DOMContentLoaded', init);
```

### 5.6 View Pattern — How Every View Is Built

Every view follows the same pattern. Dashboard is the canonical example.

```javascript
// js/views/dashboard.js

import * as store from '../store.js';
import * as utils from '../utils.js';

const CONTAINER = 'view-dashboard';

export function initDashboard() {
  // Subscribe to the data keys this view cares about
  store.subscribe('findings',     () => render());
  store.subscribe('apps',         () => render());
  store.subscribe('fleet_average',() => render());
  store.subscribe('status',       () => render());

  // Initial render (may show empty state)
  render();
}

function render() {
  const el = document.getElementById(CONTAINER);
  if (!el) return;

  const findings    = store.get('findings');
  const apps        = store.get('apps');
  const fleet       = store.get('fleet_average');
  const status      = store.get('status');
  const changeSummary = store.get('change_summary');

  if (findings.length === 0 && status.state === 'idle') {
    el.innerHTML = _renderEmptyState();
    return;
  }

  el.innerHTML = `
    ${_renderChangeBanner(changeSummary)}
    ${_renderSeverityCards(findings)}
    ${_renderFleetScore(fleet)}
    ${_renderAppScores(apps)}
    ${_renderLatestFindings(findings.slice(0, 10))}
  `;
}

function _renderSeverityCards(findings) {
  const counts = { CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0, INFO:0 };
  findings.forEach(f => { if (f.severity in counts) counts[f.severity]++; });

  return `<div class="severity-cards">
    ${Object.entries(counts).map(([sev, n]) => `
      <div class="sev-card sev-${sev.toLowerCase()}" onclick="window.location.hash='#/issues?severity=${sev}'">
        <div class="sev-count">${n}</div>
        <div class="sev-label">${sev}</div>
      </div>
    `).join('')}
  </div>`;
}

function _renderAppScores(apps) {
  const entries = Object.entries(apps);
  if (!entries.length) return '';

  return `<div class="app-scores-section">
    <h3>App Health</h3>
    <div class="app-score-grid">
      ${entries.map(([name, data]) => `
        <div class="app-score-card ${utils.scoreClass(data.score)}">
          <div class="app-score-value">${Math.round(data.score)}
            <span class="score-unit">%</span>
          </div>
          <div class="app-score-name">${utils.escapeHtml(name)}</div>
          ${data.is_hub ? '<span class="hub-badge">HUB</span>' : ''}
        </div>
      `).join('')}
    </div>
  </div>`;
}

function _renderLatestFindings(findings) {
  if (!findings.length) return '';
  return `<div class="latest-findings">
    <h3>Latest Findings</h3>
    <table class="findings-table">
      <thead>
        <tr><th></th><th>Scanner</th><th>Title</th><th>File</th><th>Line</th></tr>
      </thead>
      <tbody>
        ${findings.map(f => `
          <tr class="finding-row" data-id="${f.id}">
            <td>${utils.severityBadge(f.severity)}</td>
            <td><span class="scanner-badge">${f.scanner}</span></td>
            <td>${utils.escapeHtml(f.title)}</td>
            <td class="file-cell">${utils.escapeHtml(f.file)}</td>
            <td>${f.line}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  </div>`;
}

function _renderEmptyState() {
  return `<div class="empty-state">
    <div class="empty-icon">⚡</div>
    <h2>No audit has run yet</h2>
    <p>Click <strong>▶ Run</strong> to start your first audit.</p>
  </div>`;
}

function _renderChangeBanner(summary) {
  if (summary.first_run || !summary.new_violations) return '';
  return `<div class="change-banner">
    <strong>${summary.new_violations} new violations</strong> since last run.
    ${summary.resolved_violations} resolved.
  </div>`;
}
```

**Every other view follows this exact pattern:**
1. `init*()` subscribes to store keys and calls `render()`
2. `render()` reads from store, builds HTML string, sets `innerHTML`
3. No async calls inside render. No direct API calls.
4. All data comes from the store.

---

## 6. Data Flow Diagram — End to End

```
                      ┌──────────────────────────────────┐
                      │           BROWSER                  │
  User clicks Run     │                                    │
         │            │  main.js                           │
         ▼            │    └── api.startRun()              │
  POST /api/run ──────┼──────────────────────────────────── ──▶ orchestrator.start_job()
                      │                                         │
  SSE /api/stream ◀───┼─────────────────────────────────────── │ (runs in background)
         │            │                                         │
         │  events    │                                         ├─ Phase 0: source sync
         ▼            │                                         ├─ Phase 1: build DNA
  stream.js           │                                         ├─ Phase 2: load rules
    onProgress ──────▶ store.setProgress()                      ├─ Phase 3: run scanners
    onLog      ──────▶ store.appendLog()                        ├─ Phase 4: rules engine
    onFinding  ──────▶ store.appendFinding()                    ├─ Phase 5: score apps
    onStatus   ──────▶ store.set('status')                      ├─ Phase 6: coupling
         │            │  └── when 'completed':                  ├─ Phase 7: timeline
         │            │      api.getData()                      ├─ Phase 8: fix queue
         │            │        └── store.setAuditData()         ├─ Phase 9: git context
         │            │              │                          ├─ Phase 10: AI recs
         │            │              ▼                          └─ Phase 11: write JSON
         │            │        ALL VIEWS                                │
         │            │        re-render automatically                  │
         │            │        via store subscriptions                  │
         │            │                                    ◀──────── audit_data_complete.json
         │            └──────────────────────────────────────┘
         │
         └── GET /api/stream ──▶ routes_stream.py
                                  └── bus.subscribe_all()
                                       └── queue per connection
```

---

## 7. CSS Architecture

### 7.1 Variable Naming Convention

All CSS variables follow this pattern:
```
--{property-category}-{variant}
```

Categories: `bg` (background), `text`, `border`, `accent`, `status`, `radius`, `space`, `font`

```css
/* variables.css — complete token set */
:root {
  /* Backgrounds */
  --bg-base:      #0f172a;
  --bg-surface:   #1e293b;
  --bg-elevated:  #253348;
  --bg-overlay:   #334155;
  --bg-input:     #1e293b;
  --bg-hover:     rgba(56,189,248,0.06);

  /* Text */
  --text-primary:   #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted:     #64748b;
  --text-inverse:   #0f172a;

  /* Borders */
  --border-subtle:  rgba(255,255,255,0.06);
  --border-default: rgba(255,255,255,0.14);
  --border-strong:  rgba(255,255,255,0.28);

  /* Accent */
  --accent-primary:   #38bdf8;
  --accent-secondary: #818cf8;
  --accent-hover:     #7dd3fc;

  /* Status (finding severities) */
  --status-critical: #ef4444;
  --status-high:     #f97316;
  --status-medium:   #eab308;
  --status-low:      #22c55e;
  --status-info:     #38bdf8;

  /* Category colors */
  --cat-security:     #ef4444;
  --cat-quality:      #38bdf8;
  --cat-dependency:   #f97316;
  --cat-architecture: #818cf8;
  --cat-performance:  #22c55e;

  /* Spacing (4px base unit) */
  --space-1: 4px;  --space-2: 8px;   --space-3: 12px;
  --space-4: 16px; --space-5: 20px;  --space-6: 24px;
  --space-8: 32px; --space-12: 48px; --space-16: 64px;

  /* Typography */
  --font-sans: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --text-xs: 11px; --text-sm: 13px; --text-base: 14px;
  --text-lg: 16px; --text-xl: 18px; --text-2xl: 22px;

  /* Radii */
  --radius-sm: 4px; --radius-md: 8px;
  --radius-lg: 12px; --radius-full: 9999px;
}
```

### 7.2 CSS Class Naming Convention

BEM-style for components, utility classes for layout:

```
.{component}                    — e.g. .sev-card
.{component}--{modifier}        — e.g. .sev-card--critical
.{component}__{element}         — e.g. .sev-card__count
.view                           — all view containers
.view.active                    — currently visible view
.view.hidden                    — display: none
.hidden                         — utility: display: none
.badge                          — severity/status badges
.badge-{severity}               — e.g. .badge-critical
```

---

## 8. Plugin Contract — Canonical Interface

Every scanner plugin MUST satisfy this exact interface. If it doesn't,
the PluginRegistry silently skips it with a warning.

```python
class BaseScanner(ABC):
    # These MUST be class-level attributes
    name:      ClassVar[str]         # slug: [a-z0-9_-]+ matching settings.json key
    version:   ClassVar[str]         # semver: "1.0.0"
    languages: ClassVar[list[str]]   # ["python"] or ["*"] for any
    category:  ClassVar[Category]    # from core.models.Category
    requires_ai: ClassVar[bool] = False
    timeout:   ClassVar[int]  = 120  # seconds

    @abstractmethod
    async def scan(
        self,
        target: Path,           # absolute path to project root
        config: dict,           # from settings.scanner_configs[self.name]
        bus: EventBus,          # publish progress/log events here
    ) -> list[Finding]:         # list may be empty, never None
        ...
```

**Scanner name MUST match the key in `settings.json`:**
```json
{
  "scanners": {
    "bandit":          true,
    "vulture":         true,
    "radon":           true,
    "safety":          true,
    "lizard":          true,
    "semgrep":         true,
    "django_settings": true
  }
}
```

Each scanner's `name` attribute must exactly equal the key above.

**What a scanner MUST do:**
- Return `[]` (not crash) when the underlying tool is not installed
- Catch all subprocess errors
- Publish `publish_progress(self.name, 0, "")` at start
- Publish `publish_progress(self.name, 100, "")` at end
- Convert findings to `Finding` objects with `finding_to_dict`-compatible fields
- Use `asyncio.create_subprocess_exec` — never `subprocess.run`

---

## 9. Error Handling Contract

### 9.1 Backend Errors

Every unhandled exception in an orchestrator phase:
1. Is caught by the outer `try/except` in `_run_job`
2. Sets `job.state = "failed"`
3. Publishes `STATUS "failed"` event to SSE
4. Is logged to stderr with full traceback

Every unhandled exception in a scanner:
1. Is caught by `_run_single_scanner`
2. Scanner's findings are empty, `ScanResult.error` is set
3. Is logged as a warning
4. Job continues with other scanners

### 9.2 Frontend Errors

Every `fetch()` failure in `api.js`:
- Throws an `ApiError(status, body)` object, never swallows silently
- The view that called the API catches it and renders an inline error div

Every store subscription:
- Is wrapped in `try/catch`
- A render error in one view NEVER crashes other views

---

## 10. Settings and Configuration Contract

### 10.1 `settings.json` Keys — Canonical

```json
{
  "project_path":   "/absolute/path (string, required)",
  "api_key":        "string or null",
  "ai_enabled":     "boolean, default false",
  "ai_provider":    "gemini | claude, default claude",
  "ai_model":       "string, default claude-opus-4-7",
  "force_rescan":   "boolean, default false",
  "scanners": {
    "bandit":          true,
    "vulture":         true,
    "radon":           true,
    "safety":          true,
    "lizard":          true,
    "semgrep":         true,
    "django_settings": true
  },
  "scanner_configs": {},
  "ui": {}
}
```

### 10.2 `audit_rules.yaml` Schema — Canonical

```yaml
# Top-level sections
rules:       # list of rule definitions
apps:        # list of app definitions (empty = auto-detect)
communication:  # allowed patterns and bootstrap files
scoring:        # score formula parameters
```

**Rule definition:**
```yaml
- id: string (required, slug)
  name: string (required)
  type: ghost | cycle | boundary | regex | pattern | metric (required)
  severity: CRITICAL | HIGH | MEDIUM | LOW | INFO (required)
  category: security | quality | architecture | dependency | performance
  languages: ["python"] or ["*"] (optional, default ["*"])
  description: string
  suggestion: string
  config:
    # type-specific config — see rules_engine.py for each type
```

---

## 11. What MUST NOT Change Without a Spec Update

These decisions are locked. Changing them without updating this spec first
is how things break:

1. **`audit_data_complete.json` schema** — adding fields is OK, removing or renaming is not
2. **`finding_to_dict()` function** — it is the single serialization point
3. **`/static/` URL prefix** for frontend assets
4. **Store key names** in `store.js` — `findings`, `apps`, `fleet_average`, etc.
5. **`name` attribute on scanner plugins** — must exactly match the key in `settings.json.scanners`. A mismatch causes silent skip. Always verify both when adding or renaming a scanner.
6. **SSE event type names** — `status`, `progress`, `log`, `finding`
7. **SSE payload shapes** — `{state, job_id}`, `{scanner, percent, file}`, `{level, message}`, `{finding}`
8. **Port 8421** — hardcoded default, used in settings and tests
9. **Reserved config keys injected by orchestrator** — `_file_filter` and `_force_rescan` are injected into every scanner's config dict by the orchestrator. Scanner plugins MUST NOT use these key names for their own config. They read `_file_filter` to restrict file scope and `_force_rescan` to bypass caching.

---

## 12. Implementation Order for a Fresh Build

If starting from a broken state, build in this exact order. Each step is independently testable:

**Backend (test with `curl` after each):**
1. `core/models.py` — `Finding`, `Job`, `ScanResult`, `Settings`, `finding_to_dict()`
2. `core/events.py` — `EventBus` with `subscribe_all`, ring buffer, sequential IDs
3. `core/atomic.py` — `write_json`, `read_json`
4. `core/settings.py` — `load()`, `save()`
5. `orchestrator.py` — stub only (no scanners, publish fake progress events)
6. `api/server.py` — static files + all routes wired, SSE working end-to-end
7. `plugins/` — one scanner at a time, verify with `curl /api/run`
8. `core/dna_builder.py`, `core/rules_engine.py`, `core/scoring_engine.py` — in that order
9. Remaining `core/` modules — `coupling`, `fix_queue`, `timeline`, `git_context`

**Frontend (test in browser after each):**
1. `css/variables.css`, `css/layout.css`, `css/components.css` — open browser, see styled shell
2. `js/store.js` — test in browser console: `store.set('x', 1)`, subscribe fires
3. `js/api.js` — test with `api.getStatus()`
4. `js/stream.js` — test SSE connection opens, heartbeat arrives
5. `js/router.js` — test tab switching works, URL hash updates
6. `js/main.js` — test full init, run/cancel buttons wire correctly
7. `js/views/dashboard.js` — test with empty state, then with real data
8. Remaining views — one at a time

---

*Spec version: 1.1 | Date: 2026-06-04*  
*This document must be read in full before any implementation work begins.*
*Approved by: technical review 2026-06-04*
