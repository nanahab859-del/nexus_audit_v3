# Nexus Audit V3 — Full Bug Report & Precision Fix Plan
**Date:** 2026-06-03  
**Status:** Dashboard broken. Audits crash before completion. Settings disconnected.  
**Method:** Every file read line by line.

---

## THE ACTUAL STATE OF THE CODEBASE

The directory listing shown earlier was STALE. The real JS files on disk right now:
```
frontend/js/
  api.js          (1.8KB)   — real file, mostly correct
  dashboard.js    (1.1KB)   — placeholder JSON dump, not a real UI
  main.js         (2.8KB)   — real file, has bugs
  state.js        (2.4KB)   — real file, mostly correct
  settings.js     (4.0KB)   — never imported by main.js, dead
  settings-api.js           — dead code, never imported
  settings-app.js           — dead code, never imported
  settings-tabs.js          — dead code, never imported
  settings-validators.js    — dead code, never imported
  settings-yaml-editor.js   — dead code, never imported
```

`stream.js`, `router.js`, `command-palette.js`, `utils.js` — DO NOT EXIST.

---

## BUG INVENTORY — EXACT FILE AND LINE

### BUG 1 — CRITICAL: `dashboard.js` is a raw JSON dump
**File:** `frontend/js/dashboard.js`  
**What it does:** Calls `getData()` and renders `JSON.stringify(data)` inside a `<pre>` tag. That is all. No metrics, no cards, no tables. This is why the dashboard shows "nonsense."  
**Fix:** Rewrite entirely. See Fix Plan Step 1.

---

### BUG 2 — CRITICAL: Orchestrator crashes on JSON serialization
**File:** `orchestrator.py` lines ~140–160  
**Root cause:** These three lines:
```python
security_findings = [finding.__dict__ for finding in all_findings if finding.category.value == "security"]
quality_findings  = [finding.__dict__ for finding in all_findings if finding.category.value == "quality"]
architecture_findings = [finding.__dict__ for finding in all_findings if finding.category.value == "architecture"]
```
`finding.__dict__` contains `severity: Severity.HIGH` (IntEnum) and `category: Category.SECURITY` (Enum). `write_json` calls `json.dumps`. `json.dumps` cannot serialize Enum objects. **Every audit run crashes before writing the result file.** The JSON file is never written.  
**Fix:** Replace `finding.__dict__` with a helper function. See Fix Plan Step 2.

---

### BUG 3 — CRITICAL: Orchestrator only runs Bandit; all other scanners ignored
**File:** `orchestrator.py` lines ~82–97  
**Root cause:**
```python
try:
    from plugins.security.bandit_plugin import BanditScanner
    scanner = BanditScanner()
    bandit_findings = await scanner.scan(...)
    scanner_findings.extend(bandit_findings)
except Exception as e:
    await bus.publish_log("warning", f"Failed to run BanditScanner: {e}")
```
After this block: nothing. Vulture, Radon, Safety, Lizard, Semgrep, DjangoSettings — never called. The `PluginRegistry` exists but is never used.  
**Fix:** Replace hardcoded Bandit block with PluginRegistry dispatch. See Fix Plan Step 3.

---

### BUG 4 — CRITICAL: Progress event payload keys are wrong
**File:** `frontend/js/main.js` line ~42  
**Root cause:**
```javascript
document.getElementById('scanner-progress').innerText = 
  `${prog.scanner}: ${prog.progress}% - ${prog.message}`;
```
The SSE `publish_progress` sends `{"scanner": ..., "percent": ..., "file": ...}`.  
`prog.progress` is `undefined`. `prog.message` is `undefined`.  
Progress panel shows: `"bandit: undefined% - undefined"`.  
**Fix:** Change to `prog.percent` and `prog.file`. See Fix Plan Step 4.

---

### BUG 5 — CRITICAL: Settings button is a dead link, not a modal
**File:** `frontend/index.html` line 14  
**Root cause:**
```html
<a href="/settings" class="icon-btn" title="Settings">⚙️</a>
```
This navigates to `/settings` which hits the SPA fallback and reloads `index.html`. No settings modal appears. The settings UI is completely inaccessible.  
**Fix:** Change to a `<button>` that wires to a settings modal. See Fix Plan Step 5.

---

### BUG 6 — HIGH: `Job` dataclass missing `git_context` field
**File:** `core/models.py`  
**Root cause:** `Job` has no `git_context` field. Orchestrator does `job.git_context = git_ctx` — works at runtime but:
- `markdown_report.py` does `if job.git_context:` which raises `AttributeError` if the orchestrator crashes before setting it
- Mypy strict fails on the assignment  
**Fix:** Add `git_context: dict = field(default_factory=dict)` to Job dataclass. See Fix Plan Step 6.

---

### BUG 7 — HIGH: SSE `Last-Event-ID` replay is semantically broken
**File:** `api/routes_stream.py` lines 26–30  
**Root cause:**
```python
since_index = int(request.headers["Last-Event-ID"])
history = bus.history(since_index)
```
`bus.history(n)` returns events from index `n` in the list (slice `[n:]`).  
But the SSE sends `id: 0`, `id: 1`, `id: 2`... and these IDs are LOCAL to the connection. A reconnecting client sends `Last-Event-ID: 47` meaning "I've seen 47 events." The history buffer has at most 100 entries. `bus.history(47)` returns events from position 47 onward, which could be any event — not the right ones.  
The fix is to use the actual sequential bus event counter, or simply replay the full history on reconnect.  
**Fix:** On reconnect, replay all buffered history. See Fix Plan Step 7.

---

### BUG 8 — HIGH: `default_rules.yaml` uses wrong schema
**File:** `default_rules.yaml`  
**Root cause:** The YAML uses keys the rules engine does not understand:
- Rule `R001` has no `id`, `name`, `severity`, `languages` fields — `rules_engine.py` skips rules without `id` and `type`
- Rule `R002` uses `pattern:` at top level — engine expects `config.expression:`  
- Rule `R002` uses `message:` — engine expects `description:`
- `boundaries:` section — not read by `boundary_engine.py` (reads `communication:`)
- Apps use `pattern:` — boundary engine reads `paths:`  
Result: zero rules load correctly. Ghost file and regex rules never fire.  
**Fix:** Rewrite `default_rules.yaml` to match the actual schema. See Fix Plan Step 8.

---

### BUG 9 — MEDIUM: `metric` rule type does nothing
**File:** `core/rules_engine.py` lines ~120–129  
**Root cause:**
```python
elif rule.type == "metric":
    metric_name = rule.config.get("metric")
    threshold = rule.config.get("threshold", 0)
    for f in scanner_findings:
        pass  # does nothing
```
This block is an empty stub. Complexity and dead-code thresholds never fire.  
**Fix:** Implement metric matching against scanner findings. See Fix Plan Step 9.

---

### BUG 10 — MEDIUM: `audit_new.json` fallback pollutes data endpoint
**File:** `api/routes_data.py` lines 17–19  
**Root cause:**
```python
data = await read_json(Path("audit_data_complete.json"))
if data is None:
    data = await read_json(Path("audit_new.json"))
```
`audit_new.json` (118.5KB) exists from a previous session. If `audit_data_complete.json` doesn't exist yet, the stale `audit_new.json` is served. This shows old data.  
**Fix:** Remove the `audit_new.json` fallback. See Fix Plan Step 10.

---

### BUG 11 — MEDIUM: Dead JS files confuse the codebase
**Files:** `settings-api.js`, `settings-app.js`, `settings-tabs.js`, `settings-validators.js`, `settings-yaml-editor.js`  
**Root cause:** These five files are never imported by anything. They appear to be artifacts of a failed refactoring attempt (29KB of dead code in `settings-tabs.js` alone).  
**Fix:** Delete all five. See Fix Plan Step 11.

---

### BUG 12 — MEDIUM: Recursive DFS will crash on large projects
**File:** `core/rules_engine.py` lines ~170–193  
**Root cause:**
```python
def dfs(node: Any) -> None:
    ...
    for neighbor in graph.get(node, []):
        if neighbor in dna.modules:
            dfs(neighbor)  # recursive call
```
Python default recursion limit is 1000. A project with 200+ modules and deep import chains will hit this.  
**Fix:** Convert to iterative DFS using an explicit stack. See Fix Plan Step 12.

---

## PRECISION FIX PLAN

Each step is one commit. Steps are ordered: critical first.

---

### STEP 1 — Rewrite `frontend/js/dashboard.js`

Delete the file completely. Write from scratch. The new file must:

1. NOT call `getData()` directly — read from `state.getState()`
2. Subscribe to state changes: when `findings`, `healthScores`, or `status` change, re-render
3. Render these exact sections in order:

**Section A: Severity summary cards**
```javascript
const counts = { CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0, INFO:0 };
findings.forEach(f => { if (counts[f.severity] !== undefined) counts[f.severity]++; });
// Render one card per severity. Click card → filter findings (future).
```

**Section B: App health scores** (read from `state.getState().healthScores`)
```javascript
// For each app in healthScores: render app name + score as a bar
// Score 80-100 = green, 50-79 = amber, 0-49 = red
```

**Section C: Latest findings table** (top 10 from `state.getState().findings`, sorted by severity)
```javascript
// Columns: severity badge, scanner, title, file, line
// Each row clickable (future)
```

**Section D: Empty state** — shown only when `findings.length === 0` AND `status.state === 'idle'`
```javascript
container.innerHTML = `<div style="text-align:center;padding:60px;">
  <h2 style="color:var(--text-secondary)">No audit has run yet</h2>
  <p style="margin-top:8px;color:var(--text-muted)">Click ▶ Run Audit to start</p>
</div>`;
```

The module export must be:
```javascript
export function initDashboard() { /* subscribe to state changes, initial render */ }
export function renderDashboard() { /* render the actual HTML */ }
```

`main.js` calls `initDashboard()` once in `init()`. State subscriptions inside `initDashboard` trigger `renderDashboard()` automatically.

After a run completes, `main.js` calls `setData(await getData())` from state, which triggers the subscribers, which triggers `renderDashboard()`. Dashboard updates without `main.js` needing to call render directly.

---

### STEP 2 — Fix Finding serialization in `orchestrator.py`

Add a helper function at the top of `orchestrator.py`:

```python
def _finding_to_dict(f: Finding) -> dict[str, Any]:
    return {
        "id": f.id,
        "scanner": f.scanner,
        "file": f.file,
        "line": f.line,
        "column": f.column,
        "severity": f.severity.name,       # e.g. "HIGH" not 4
        "category": f.category.value,      # e.g. "security" not <Category.SECURITY>
        "title": f.title,
        "description": f.description,
        "suggestion": f.suggestion,
        "cwe": f.cwe,
        "cvss_score": f.cvss_score,
    }
```

Then replace every occurrence of `finding.__dict__` in `orchestrator.py` with `_finding_to_dict(finding)`:

```python
# Replace these three lines:
security_findings = [finding.__dict__ for finding in all_findings if finding.category.value == "security"]
quality_findings  = [finding.__dict__ for finding in all_findings if finding.category.value == "quality"]
architecture_findings = [finding.__dict__ for finding in all_findings if finding.category.value == "architecture"]
ghost_files = [finding.__dict__ for finding in all_findings if "exists on disk but is never imported" in finding.description]
cycles = [finding.__dict__ for finding in all_findings if "Circular dependency" in finding.description]

# With:
security_findings = [_finding_to_dict(f) for f in all_findings if f.category.value == "security"]
quality_findings  = [_finding_to_dict(f) for f in all_findings if f.category.value == "quality"]
architecture_findings = [_finding_to_dict(f) for f in all_findings if f.category.value == "architecture"]
ghost_files = [_finding_to_dict(f) for f in all_findings if "never imported" in (f.description or "")]
cycles = [_finding_to_dict(f) for f in all_findings if "Circular dependency" in (f.title or "")]
```

Also add persistence and fix_status to the findings list serialization using `_finding_to_dict` as the base:
```python
"findings": [
    {
        **_finding_to_dict(f),
        "persistence": persistence.get(f.id, "new"),
        "fix_status": (fix_queue.get_status(f.id).status 
                       if fix_queue.get_status(f.id) is not None else "open"),
    }
    for f in all_findings
],
```

---

### STEP 3 — Wire PluginRegistry in `orchestrator.py`

Replace the hardcoded Bandit block entirely. The new scanner dispatch:

```python
# Load enabled scanners via PluginRegistry
from core.registry import PluginRegistry
from pathlib import Path as _Path

registry = PluginRegistry(plugins_dir=_Path("plugins"))
registry.load()

scanner_findings: list[Finding] = []
enabled_scanners = settings.scanners  # dict[str, bool]

for scanner_name, enabled in enabled_scanners.items():
    if not enabled:
        continue
    scanner_cls = registry.get(scanner_name)
    if scanner_cls is None:
        await bus.publish_log("warning", f"Scanner '{scanner_name}' not found in registry")
        continue
    try:
        await bus.publish_log("info", f"Running scanner: {scanner_name}")
        await bus.publish_progress(scanner_name, 0, "")
        scanner = scanner_cls()
        scanner_config = raw_config.get("scanner_configs", {}).get(scanner_name, {})
        findings = await asyncio.wait_for(
            scanner.scan(working_path, scanner_config, bus),
            timeout=scanner_cls.timeout
        )
        scanner_findings.extend(findings)
        await bus.publish_progress(scanner_name, 100, "")
        await bus.publish_log("info", f"{scanner_name}: {len(findings)} findings")
        job.scan_results.append(ScanResult(
            scanner=scanner_name,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            findings=findings
        ))
    except asyncio.TimeoutError:
        await bus.publish_log("warning", f"{scanner_name} timed out")
    except Exception as e:
        await bus.publish_log("error", f"{scanner_name} failed: {e}")
```

IMPORTANT: The scanner `name` attribute on each plugin class must match the keys in `settings.json scanners`. Verify the plugin name attributes:
- `BanditScanner.name = "bandit"` ✓
- `VulturePlugin.name = "vulture"` — check this matches `settings.json`
- Same for radon, safety, lizard, semgrep, django_settings

If any `name` attribute doesn't match the `settings.json` key, the scanner won't load. Check all 7 scanner files and confirm `name` matches the key in `settings.json`.

---

### STEP 4 — Fix progress event keys in `main.js`

Find this line in `main.js`:
```javascript
document.getElementById('scanner-progress').innerText = `${prog.scanner}: ${prog.progress}% - ${prog.message}`;
```
Replace with:
```javascript
document.getElementById('scanner-progress').innerText = `${prog.scanner}: ${prog.percent ?? 0}% — ${prog.file || ''}`;
```

---

### STEP 5 — Fix settings button in `index.html` and wire modal

**In `index.html`:** Change the settings anchor to a button:
```html
<!-- REMOVE: -->
<a href="/settings" class="icon-btn" title="Settings">&#9881;&#65039;</a>

<!-- ADD: -->
<button id="btn-settings" class="icon-btn" title="Settings">&#9881;&#65039;</button>
```

**In `main.js`:** Add event listener after the other button wires:
```javascript
document.getElementById('btn-settings').addEventListener('click', () => {
  // Simple inline settings: open a dialog or redirect
  // For now: show a prompt for project path as minimum viable settings
  const currentPath = (window.__auditSettings && window.__auditSettings.project_path) || '';
  const newPath = prompt('Project path:', currentPath);
  if (newPath && newPath !== currentPath) {
    saveSettings({ project_path: newPath })
      .then(() => alert('Settings saved. Re-run audit to use new path.'))
      .catch(e => alert('Failed: ' + e.message));
  }
});
```
Note: `saveSettings` must be imported from `api.js` in `main.js`. Add it to the import:
```javascript
import { getStatus, getData, startRun, cancelRun, openStream, getSettings, saveSettings } from './api.js';
```

Also after `init()`, load and store settings:
```javascript
try {
  const s = await getSettings();
  window.__auditSettings = s;
} catch(e) {}
```

---

### STEP 6 — Add `git_context` field to `Job` in `core/models.py`

Find the `Job` dataclass. Add ONE line:
```python
@dataclass
class Job:
    project_path: Path
    started_at: datetime
    id: str = field(init=False)
    finished_at: datetime | None = None
    state: Literal["running", "completed", "cancelled", "failed"] = "running"
    scan_results: list[ScanResult] = field(default_factory=list)
    git_context: dict = field(default_factory=dict)   # ← ADD THIS LINE
```

---

### STEP 7 — Fix SSE replay in `api/routes_stream.py`

The `since_index` from `Last-Event-ID` cannot reliably map to history positions across connections. Simplest correct fix: always replay ALL history on connect, ignore `Last-Event-ID`.

Replace:
```python
since_index = 0
if "Last-Event-ID" in request.headers:
    try:
        since_index = int(request.headers["Last-Event-ID"])
    except ValueError:
        pass
```
With:
```python
since_index = 0  # always replay full history
```

And replace:
```python
history = bus.history(since_index)
for event in history:
    await _send_sse_event(response, event, event_id)
    event_id += 1
```
With:
```python
for event in bus.history(0):
    await _send_sse_event(response, event, event_id)
    event_id += 1
```

---

### STEP 8 — Rewrite `default_rules.yaml` to match the actual schema

Delete the file. Write from scratch with the schema `rules_engine.py` actually reads:

```yaml
# Nexus Audit V3 — Default Rules
# Schema: each rule needs id, type, severity, name, category
# Rule types: ghost | cycle | boundary | regex | pattern | metric

rules:
  - id: ghost-file
    name: "Ghost file"
    type: ghost
    severity: LOW
    category: quality
    description: "File exists on disk but is never imported by any other module"
    suggestion: "Remove unused file or add an import from an entry point"

  - id: no-circular-import
    name: "Circular dependency"
    type: cycle
    severity: CRITICAL
    category: architecture
    description: "Circular import chain detected"
    suggestion: "Refactor to remove the cycle — extract shared code to a neutral module"

  - id: no-cross-app-import
    name: "Direct cross-app import"
    type: boundary
    severity: HIGH
    category: architecture
    description: "App '{source_app}' directly imports from '{target_app}'"
    suggestion: "Use an allowed communication pattern instead"

  - id: no-print-statements
    name: "print() in production code"
    type: regex
    severity: LOW
    category: quality
    languages: ["python"]
    description: "print() statement found — use logging instead"
    suggestion: "Replace with logging.info() or logging.debug()"
    config:
      expression: '^\s*print\('

apps: []         # empty = auto-detect from DNA
communication:
  allowed_patterns:
    - name: "Django signals"
      import_pattern: "*.signals"
    - name: "Celery tasks"
      import_pattern: "*.tasks"
  bootstrap_files:
    - asgi
    - wsgi
    - settings
    - celery
    - manage
    - routing
    - apps
    - admin

scoring:
  penalties:
    violation_default: 5
    violation_hub: 3
    security_high: 12
    security_medium: 6
    security_low: 3
    complexity_above: 10
    complexity_factor: 2
    complexity_max: 20
    dead_code_per: 3
    dead_code_max: 15
    ghost_file_per: 2
    ghost_file_max: 10
  bonuses:
    hub_app: 10
  exclude_tests: true
```

---

### STEP 9 — Implement `metric` rule type in `core/rules_engine.py`

Find the empty `elif rule.type == "metric":` block. Replace with:

```python
elif rule.type == "metric":
    metric_name = rule.config.get("metric", "")
    threshold = float(rule.config.get("threshold", 0))
    scanner_name = rule.config.get("scanner", "")
    
    for finding in scanner_findings:
        # Match scanner if specified
        if scanner_name and finding.scanner != scanner_name:
            continue
        # Extract numeric value from finding title using regex
        import re as _re
        numbers = _re.findall(r'\d+(?:\.\d+)?', finding.title)
        if numbers:
            value = float(numbers[-1])  # take last number in title
            if value > threshold:
                violations.append(Finding(
                    scanner="rules_engine",
                    file=finding.file,
                    line=finding.line,
                    column=finding.column,
                    severity=rule.severity,
                    category=rule.category,
                    title=f"{rule.name}: {value} (threshold: {threshold})",
                    description=rule.description or finding.description,
                    suggestion=rule.suggestion,
                ))
```

---

### STEP 10 — Remove `audit_new.json` fallback from `api/routes_data.py`

Find:
```python
data = await read_json(Path("audit_data_complete.json"))
if data is None:
    # Try fallback
    data = await read_json(Path("audit_new.json"))
```
Replace with:
```python
data = await read_json(Path("audit_data_complete.json"))
```

Also delete `audit_new.json` from the project root.

---

### STEP 11 — Delete dead JS files

Delete these five files from `frontend/js/`:
```
settings-api.js
settings-app.js
settings-tabs.js
settings-validators.js
settings-yaml-editor.js
```
They are never imported by anything. 29KB of dead code.

---

### STEP 12 — Convert recursive DFS to iterative in `core/rules_engine.py`

Find the `dfs` function inside `rules_engine.py` `evaluate()`. Replace:

```python
visited: set[str] = set()
path: list[str] = []
cycles: list[list[str]] = []

def dfs(node: Any) -> None:
    if node in path:
        cycle_start = path.index(node)
        cycles.append(path[cycle_start:] + [node])
        return
    if node in visited:
        return
    visited.add(node)
    path.append(node)
    for neighbor in graph.get(node, []):
        if neighbor in dna.modules:
            dfs(neighbor)
    path.pop()

for node in graph:
    dfs(node)
```

With iterative version:

```python
cycles: list[list[str]] = []
global_visited: set[str] = set()

for start_node in list(graph.keys()):
    if start_node in global_visited:
        continue
    # Iterative DFS with explicit stack
    # Stack entries: (node, path_so_far)
    stack: list[tuple[str, list[str]]] = [(start_node, [])]
    local_visited: set[str] = set()
    
    while stack:
        node, path = stack.pop()
        
        if node in path:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            continue
            
        if node in local_visited:
            continue
            
        local_visited.add(node)
        global_visited.add(node)
        new_path = path + [node]
        
        for neighbor in graph.get(node, []):
            if neighbor in dna.modules and neighbor not in local_visited:
                stack.append((neighbor, new_path))
```

---

### STEP 13 — Update `main.js` to wire data loading into state

After `renderDashboard()` and after a run completes, `main.js` must load data into state so the dashboard subscriptions fire:

Add to imports:
```javascript
import { getData, getSettings, startRun, cancelRun, openStream, saveSettings } from './api.js';
import { setStatus, setProgress, appendLog, clearLogsAndProgress, setData } from './state.js';
```

In `init()`, after starting the stream, load initial data:
```javascript
try {
  const data = await getData();
  setData(data);
} catch(e) { /* no data yet, fine */ }
```

In `startStreaming()` `onStatus` handler, when state is `completed`:
```javascript
onStatus: (st) => {
  setStatus(st);
  updateStatusUI(st);
  if (st.state === 'completed' || st.state === 'failed' || st.state === 'cancelled') {
    _stream.close();
    _stream = null;
    setTimeout(async () => {
      document.getElementById('progress-panel').style.display = 'none';
      try {
        const data = await getData();  // reload fresh data
        setData(data);                 // push into state → triggers dashboard re-render
      } catch(e) {}
    }, 1500);
  }
},
```

---

## COMMIT ORDER

Execute these commits in exact order. Do not combine steps:

```
git commit -m "fix(frontend): rewrite dashboard.js — real UI, not JSON dump"
git commit -m "fix(orchestrator): finding serialization — replace __dict__ with _finding_to_dict()"
git commit -m "fix(orchestrator): wire PluginRegistry — all enabled scanners run"
git commit -m "fix(frontend): progress event key prog.percent not prog.progress"
git commit -m "fix(frontend): settings button — button not dead link, wire modal"
git commit -m "fix(models): add git_context field to Job dataclass"
git commit -m "fix(sse): replay full history on connect — ignore unreliable Last-Event-ID"
git commit -m "fix(rules): rewrite default_rules.yaml to match actual schema"
git commit -m "fix(rules): implement metric rule type — not empty stub"
git commit -m "fix(api): remove audit_new.json fallback, delete stale file"
git commit -m "chore(frontend): delete 5 dead settings-*.js files"
git commit -m "fix(rules): convert recursive DFS to iterative — no stack overflow"
git commit -m "fix(frontend): wire setData() in main.js — state drives dashboard"
git tag v0.4.1-fixes
```

---

## VERIFICATION — HOW TO CONFIRM EACH FIX WORKED

After all fixes:

1. Start server: `python server.py`
2. Open `http://localhost:8421`  
   **Expected:** Dark dashboard, topbar with "idle" badge, "Run Audit" button. NOT a JSON dump.

3. Click Run Audit  
   **Expected:** Progress panel appears at bottom. Scanner names appear with % progress.

4. Wait for completion  
   **Expected:** Progress panel hides. Dashboard shows severity cards, app scores, findings table.

5. Click ⚙ Settings  
   **Expected:** A prompt or modal appears. NOT a page reload.

6. Check `audit_data_complete.json` was written (not `audit_new.json`)  
   **Expected:** File exists, contains valid JSON with `findings`, `apps`, `violations` keys.

7. Check for no exceptions in server terminal  
   **Expected:** No `TypeError: Object of type Severity is not JSON serializable`

---

*Audit date: 2026-06-03 | Every file read before writing this report*
