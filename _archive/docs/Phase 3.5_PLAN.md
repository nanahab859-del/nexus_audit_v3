## Nexus Audit V3 — Phase 3.5: Architecture Engine

**Status:** Planning  
**Depends on:** Phase 3 complete (`v0.3.0` tag exists)  
**Goal:** Replace the old tool’s monolithic `audit_engine.py` with a clean, modular **Architecture Engine** that generates the import graph, coupling matrix, circular dependency reports, ghost file detection, app health scores, and Django config kernel audit. All outputs become standard `Finding` objects and structured data in `audit_data_complete.json`. After this phase, the dashboard (Phase 4/5) will have real nodes, edges, and architectural metrics to render – no more blank graph.

---

## What Phase 3.5 Delivers

| Module | What it is |
|--------|-------------|
| `core/ast_parser.py` | Parse all Python files, extract imports, classify by type (first‑party, third‑party, Django internals) |
| `core/architecture_analyzer.py` | Builds the dependency graph, detects circular dependencies (DFS), finds ghost files, computes health scores per app, constructs coupling matrix |
| `plugins/security/django_settings_plugin.py` | Dedicated scanner for Django project kernel security (SECRET_KEY, DEBUG, etc.) |
| `orchestrator.py` | **Edit** — integrate the architecture analysis step into `_run_job` after file discovery |
| `core/models.py` | **Possible extension** — add dataclasses for `ArchitectureGraph`, `CouplingMatrix`, `AppHealth` if needed (or reuse existing structures) |
| Tests | `test_ast_parser.py`, `test_architecture_analyzer.py`, `test_django_settings_plugin.py`, updated `test_orchestrator.py` |

All analysis is pure Python – no external CLI tools required. The engine runs synchronously inside the orchestrator’s async flow (using `asyncio.to_thread` if heavy, but AST parsing is fast enough to run directly).

---

## Folder Layout After Phase 3.5

```
nexus_audit_v3/
├── core/
│   ├── ast_parser.py              ← NEW
│   ├── architecture_analyzer.py   ← NEW
│   └── models.py                  ← possibly extended
├── plugins/
│   └── security/
│       └── django_settings_plugin.py ← NEW
├── orchestrator.py                ← EDIT: add architecture step
├── tests/
│   ├── test_ast_parser.py         ← NEW
│   ├── test_architecture_analyzer.py ← NEW
│   ├── test_django_settings.py    ← NEW
│   └── test_orchestrator.py       ← EDIT: update tests
└── docs/
    └── PHASE3_5_PLAN.md          ← this file
```

No changes to the API, frontend, or existing scanner plugins.

---

## Step‑by‑Step Implementation Order

### Step 0 — Define data structures (if needed)

Extend `core/models.py` with lightweight containers for architecture data. These will be serialised into `audit_data_complete.json` alongside the existing `ScanResult` and `Finding` lists.

**New dataclasses:**

```python
@dataclass
class GraphNode:
    id: str               # app/module name
    label: str
    group: str            # "first_party", "django", "external"
    health_score: float   # 0–100
    issues: int

@dataclass
class GraphEdge:
    from_node: str
    to_node: str
    connection_type: str  # "internal", "django_bootstrap", "cross_app_violation", etc.
    weight: int           # number of imports

@dataclass
class CouplingMatrix:
    apps: list[str]
    matrix: list[list[int]]  # matrix[i][j] = number of imports from apps[i] to apps[j]
    violations: list[dict]   # list of {from, to, count, allowed: bool}

@dataclass
class ArchitectureResult:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    coupling_matrix: CouplingMatrix | None
    health_scores: dict[str, float]   # app_name → score
    ghost_files: list[str]            # relative paths
    circular_dependencies: list[list[str]]  # each inner list is a cycle
```

(These can be defined in `core/models.py` or in a new `core/architecture_models.py` – whichever keeps the module clean.)

**Commit:** `feat(models): add architecture graph and matrix data structures`

---

### Step 1 — `core/ast_parser.py`

Parses all `.py` files in the project and extracts import statements. The output is a detailed import map.

**Interface:**

```python
@dataclass
class ImportInfo:
    importer: str          # relative path of the file doing the import
    imported: str          # full dotted module name being imported
    line: int
    import_type: str       # "import", "from_import"
    classification: str    # "first_party", "third_party", "stdlib", "django"

def parse_project_imports(
    project_root: Path,
    discovered_files: list[DiscoveredFile],
) -> list[ImportInfo]:
    """
    Parse every Python file found by file_discovery.
    Uses the `ast` module (stdlib) to walk each file's AST.
    Classification: if the imported module matches a known first-party app name
    (from settings/scanner_configs or derived from the project structure), mark it
    'first_party'. 'django' for django.* imports. Else check against stdlib list
    and pip list; fallback to 'third_party'.
    """
```

**Classification strategy:**
- Maintain a set of first‑party app names by scanning the project root for top‑level directories that contain `models.py` or `views.py` (Django convention).
- Use `sys.stdlib_module_names` (Python 3.10+) for stdlib.
- For third‑party vs first‑party disambiguation: after identifying first‑party apps, anything else not stdlib is third‑party.

**Rules:**
- Uses `ast.parse()` with `type_comments=False` – fast and safe.
- Skips files that cause `SyntaxError` (log warning, continue).
- `importlib` imports are resolved as best‑effort.
- The function is synchronous; no I/O except reading files (use `aiofiles`? Actually, the orchestrator can call it inside `asyncio.to_thread` to avoid blocking. We'll design it as a sync function and wrap it in `_run_job` with `asyncio.to_thread`).

**Commit:** `feat(core): AST parser — extract and classify all imports`

---

### Step 2 — `core/architecture_analyzer.py`

The central module that digests `ImportInfo` into all architectural metrics.

**Interface:**

```python
def analyze_architecture(
    project_root: Path,
    imports: list[ImportInfo],
) -> ArchitectureResult:
    """
    1. Build a directed graph (networkx.DiGraph or custom dict-based graph).
    2. Detect circular dependencies using iterative DFS (Tarjan's SCC or simple DFS with recursion tracking).
    3. Identify ghost files: files present in project_root but NOT appearing in any import (importer or imported).
    4. Compute coupling matrix: cross-app imports between first-party apps.
    5. Calculate health scores: for each app, score based on:
       - Number of circular dependencies (penalty)
       - Cross-app violation count (penalty)
       - Number of ghost files (penalty)
       - Average complexity from radon findings (later combined, but here we only have architecture data; health score can be computed later when all scanners finish. We'll compute a preliminary architecture score: 100 - (penalties).
    6. Return ArchitectureResult with nodes, edges, coupling_matrix, health_scores, ghost_files, circular_dependencies.
    """
```

**Detailed behaviour:**

- **Graph building:**  
  For each `ImportInfo` with `classification == "first_party"`, create an edge from the importing app (extracted from importer path) to the imported app (first part of dotted name before the first dot). Weight = number of such imports.  
  Also create edges for Django bootstrap imports (e.g., `django.apps`) to model the framework wiring.  
  The graph is then simplified into `nodes` (unique apps) and `edges` (aggregated).

- **Circular dependency detection:**  
  Implement the **same iterative DFS** the old tool used: for each node, traverse recursively, track a `path` list, if a neighbour is already in `path`, record the cycle. Break cycles at the first repeated node.  
  Output each cycle as a list of app names.

- **Ghost files:**  
  Gather all `.py` files from `discovered_files` that are not referenced as `importer` in any `ImportInfo` (i.e., no other file imports them) AND do not import anything themselves – those are disconnected. Also files that are never imported but import others are still "connected" outward; the old tool flagged those that are entirely disconnected. We'll follow the old logic: a ghost file is one that has zero incoming imports and zero outgoing imports. This avoids false positives on entry points.

- **Coupling matrix:**  
  Build a square matrix of first‑party apps. For each cross‑app import that violates architectural rules (e.g., apps importing across domain boundaries that are not allowed), mark it as a violation. The matrix can store total imports; the violations list provides details.  
  *We need an allowed‑connection configuration.* For now, we can assume all cross‑app imports are violations unless they are explicit "shared" modules. The old tool used a config list of allowed pairs. We'll add a config key in `scanner_configs` under a hypothetical `architecture` scanner (or globally).  
  Simple default: all cross‑app imports are flagged as “potential violations” with a `WARNING` severity. This can be refined later.

- **Health scores:**  
  Start each app at 100. Subtract points for:
  - Each circular dependency cycle the app participates in (–5 per cycle)
  - Each cross‑app violation originating from the app (–2 per violation)
  - Each ghost file in the app’s directory (–3 per file)
  
  Clamp to 0–100. This provides a meaningful architecture score that the dashboard can display immediately.

**Rules:**
- Use `networkx` for graph operations? The old tool used custom dict‑based graphs to keep dependencies zero. We'll do the same – no extra dependency required. We'll implement a simple `DiGraph` class inside this module if needed.
- All analysis is deterministic.
- No async needed; the orchestrator will call it inside `asyncio.to_thread` to keep the event loop free.

**Commit:** `feat(core): architecture analyzer — graph, cycles, ghosts, matrix, scores`

---

### Step 3 — `plugins/security/django_settings_plugin.py`

A scanner plugin that audits the Django settings module for critical security misconfigurations. It runs only if the project is Django (detected by presence of `manage.py` or a settings module).

**Metadata:**  
- `name = "django_settings"`  
- `languages = ["python"]`  
- `category = Category.SECURITY` (or a new `Category.CONFIG` if we add one; SECURITY fits)  
- `requires_ai = False`

**Scan logic:**
1. Check if `manage.py` exists in project root, or locate `settings.py` by heuristics.
2. Read the settings file (and local settings if any).
3. Check for the following rules:
   - `SECRET_KEY` present and not `'...'` placeholder.
   - `DEBUG = False` (if True → HIGH severity).
   - `ALLOWED_HOSTS` not empty and not `['*']`.
   - `SECURE_SSL_REDIRECT = True`.
   - `SESSION_COOKIE_SECURE = True`.
   - `CSRF_COOKIE_SECURE = True`.
   - `SECURE_HSTS_SECONDS` > 0.
   - `SECURE_CONTENT_TYPE_NOSNIFF = True`.
4. For each failed check, create a `Finding` with severity based on risk.

**Finding details:**
- `title` = "Django security misconfiguration: <setting>"
- `description` = explanation of the risk
- `suggestion` = recommended value
- `cwe` = CWE-16 (Configuration)

**Config:** none needed, but could be toggled via `scanners` like any other plugin.

**Rules:**
- If no Django settings found, return `[]` and log info.
- Parse the settings file safely – use `ast.literal_eval` for simple assignments; if parsing fails, skip that check.

**Commit:** `feat(plugins): Django settings security scanner`

---

### Step 4 — Integrate into `orchestrator.py`

Modify `_run_job` to include the architecture analysis phase after file discovery and before scanners.

**New algorithm order in `_run_job`:**

1. **Discovery** (already exists)
2. **Architecture analysis** (NEW)
   - Wrap `file_discovery.discover()` and `ast_parser.parse_project_imports()` and `architecture_analyzer.analyze_architecture()` inside `asyncio.to_thread()` to avoid blocking.
   - Publish log/progress events.
   - Store the `ArchitectureResult` in the `Job` object (or attach it as a scan result). We'll add an optional field in `Job`: `architecture: ArchitectureResult | None`. Or we can emit the architecture data as a special `ScanResult` with scanner name `"architecture"`. The second approach is cleaner – it becomes another `ScanResult` in `job.scan_results`, so the frontend can treat it uniformly.
   - Convert architecture findings (circular dependencies, ghost files, cross‑app violations, security misconfigs) into `Finding` objects and add them to that `ScanResult`. This way the issues table shows them alongside scanner findings.
2. **Scanner dispatch** (existing)

**Implementation details:**
- Create a `ScanResult` with `scanner="architecture"` and populate its `findings` with:
  - For each circular dependency cycle: a Finding (severity MEDIUM, category ARCHITECTURE, title "Circular dependency: A → B → C")
  - For each ghost file: a Finding (severity LOW, category ARCHITECTURE, title "Ghost file: path/to/file.py has no imports")
  - For each cross‑app violation: a Finding (severity MEDIUM or LOW depending on severity, category ARCHITECTURE)
- The `ArchitectureResult` data (graph nodes/edges, coupling matrix) must also be serialized into `audit_data_complete.json` so the dashboard can render the graph and heatmap. We can store it as a separate key in the JSON alongside `scan_results`. When writing the final JSON, we'll include an `"architecture"` key with the `ArchitectureResult` as a dict.

**Commit:** `feat(orchestrator): integrate architecture analysis into audit pipeline`

---

### Step 5 — Tests

**`test_ast_parser.py`**  
- Parse a minimal Python project with a few files and imports.  
- Verify that imports are classified correctly (first‑party vs third‑party vs django).  
- Handle syntax error files gracefully.  
- Empty project returns empty list.

**`test_architecture_analyzer.py`**  
- Build a synthetic import list with a circular dependency (A→B→C→A). Verify that `circular_dependencies` contains the cycle.  
- Introduce a disconnected file → it appears in `ghost_files`.  
- Create cross‑app imports → they appear in coupling matrix violations.  
- Health scores are computed and clamped correctly.  
- Graph edges aggregate weights correctly.

**`test_django_settings.py`**  
- Create a fake `settings.py` with `DEBUG=True` → must produce a HIGH finding.  
- A fully hardened settings file → returns `[]`.  
- Non‑Django project → returns `[]` with log.

**`test_orchestrator.py` (update)**  
- Full job run now includes architecture findings in the output.  
- `audit_data_complete.json` contains an `"architecture"` section with graph data and the architecture `ScanResult`.  
- Cancellation still works midway.

**Commit:** `test: Phase 3.5 test suite`

---

### Step 6 — Final commit and tag

```bash
pytest --tb=short -q
mypy core/ plugins/ api/ orchestrator.py server.py --strict
ruff check .
git add -A
git commit -m "feat: Phase 3.5 complete — architecture engine"
git tag v0.3.5
```

---

## What Phase 3.5 Does NOT Include

- Frontend rendering of the graph/heatmap (Phase 5)
- AI‑powered architecture recommendations (Phase 7)
- Historical trends of architecture scores (Phase 6)
- Dynamic configuration of allowed cross‑app connections via UI (can be added later; defaults to flagging all cross‑app imports as warnings)

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Architecture findings are standard `Finding` objects | They appear in the same issues table and fix queue, no special UI path |
| Graph/coupling data stored separately in JSON | Dashboard needs structured `nodes`/`edges` for vis‑network; this keeps it clean |
| Sync analysis wrapped in `asyncio.to_thread` | AST parsing is CPU‑bound but fast; threading avoids event loop blocking |
| No external graph library | Zero new dependencies; our graph is small enough for custom dict‑based implementation |
| Health scores computed solely from architecture data for now | Later phases can merge complexity metrics; the architecture score provides immediate value |

---

## Definition of Done — Phase 3.5

- [ ] `core/ast_parser.py` correctly classifies imports
- [ ] `core/architecture_analyzer.py` produces complete `ArchitectureResult`
- [ ] Circular dependency detection works on known cycles
- [ ] Ghost file detection catches disconnected files
- [ ] Coupling matrix filled with cross‑app import counts and violations
- [ ] Django settings plugin reports misconfigurations
- [ ] Orchestrator job run includes architecture phase
- [ ] `audit_data_complete.json` contains `"architecture"` key with graph data
- [ ] All architecture findings appear in `scan_results` under `"architecture"` scanner
- [ ] `mypy --strict` clean
- [ ] `pytest` passes all new + old tests
- [ ] `git tag v0.3.5` exists

---

Now you have a complete blueprint for Phase 3.5. When you’ve implemented it, the backend will be generating rich architectural data that your Phase 4 frontend can already begin consuming. For Phase 4, you can safely design the dashboard to render the graph, heatmap, and architecture scores knowing the JSON contract is set.  
Once you share the old HTML and your Phase 4 draft, I’ll help you map the theme, colors, and animations onto the new advanced layout.