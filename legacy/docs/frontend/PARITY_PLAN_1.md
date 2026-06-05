# Nexus Audit V3 — Configuration-First Parity Plan
**Status:** Planning  
**Depends on:** Phase 4 complete (`v0.4.0` tag exists)  
**Target tag:** `v1.0.0`

---

## The Core Philosophy

V1 is a 200KB single Python file hardcoded for one project.
Every rule, every boundary, every violation classification is written in Python
and cannot be changed without editing the source.

V3 is a **configurable audit platform**. The tool itself knows nothing about
your project. You tell it what to look for, what constitutes a violation,
how to score, what your app boundaries are — and it enforces exactly that.

This is the same philosophy that made Semgrep, ESLint, and SonarQube successful.
A developer picks up V3, points it at any project, and configures it to understand
that project's architecture. The tool then produces audit output as targeted as
V1 produces for Nexus — because the developer has told V3 what matters in their
codebase.

**V1 behaviour is not ported. It is replicated by configuration.**
A developer who wants V1-equivalent output for their Django project writes a
`nexus_audit.yaml` config that defines Django's app boundaries, allowed
communication patterns, and scoring weights. The engine enforces it.
No Python required, no source editing required.

---

## What Needs To Be Built

The Phase 1–4 foundation gives us: scanners, API, SSE, basic frontend.
What is missing is the **intelligence layer** — the part that transforms raw
scanner findings into architectural understanding. That layer must be fully
configurable by the developer.

| Component | What it enables |
|-----------|----------------|
| `core/rules_engine.py` | YAML-defined custom rules evaluated against the live AST |
| `core/dna_builder.py` | Live module registry built from AST on every run |
| `core/boundary_engine.py` | Configurable app boundary enforcement |
| `core/scoring_engine.py` | Profile-driven health scoring (0–100) |
| `core/coupling.py` | Cross-app coupling matrix |
| `core/fix_queue.py` | Persistent finding status tracking |
| `core/timeline.py` | Score history, violation persistence |
| `core/git_context.py` | Git remote, branch, commit |
| `core/key_pool.py` | Multi-key AI rotation |
| `core/fast_check.py` | Git-diff incremental scan |
| `core/dep_cache.py` | Dependency result cache with TTL |
| `core/source_sync.py` | Optional pre-audit source copy (V1 Phase 0 pattern) |
| `core/reports/markdown_report.py` | Standalone markdown report |
| `ai/prompts.py` | Config-driven AI prompts for any project |
| Frontend intelligence tabs | All 12 V1 tabs, data-driven from config |

---

## Step-by-Step Implementation

---

### Step 1 — `core/dna_builder.py` — Live Module Registry

The DNA builder replaces V1's `pydeps` pipeline (pulse.sh phases 1–3).
It runs on every audit, needs nothing pre-installed, works on any project.

**What it builds:**

```python
@dataclass
class ModuleEntry:
    module_path: str       # "nexus_core.models.user"
    file_path: str         # absolute path
    relative_path: str     # relative to project root
    app: str               # first path segment — "nexus_core"
    imports: list[str]     # all imported dotted paths
    defined_names: list[str]
    is_test: bool
    lines_of_code: int

@dataclass
class ProjectDNA:
    modules: dict[str, ModuleEntry]
    apps: list[str]           # auto-discovered first-party app names
    physical_files: list[str] # every .py file path relative to root
    built_at: datetime
    project_root: Path
```

**Algorithm — one AST pass, no subprocess:**
```
1. Walk project root (file_discovery.discover())
2. For each .py file:
   a. Derive dotted module path from relative file path
   b. ast.parse() the file
   c. Extract: all imports (ast.Import + ast.ImportFrom)
      including relative imports resolved to absolute dotted paths
   d. Extract: all defined names (ClassDef, FunctionDef, Assign targets)
   e. Count non-blank non-comment lines
   f. Build ModuleEntry
3. Derive apps list: unique first segments of all module paths
4. Return ProjectDNA
```

**Rules:**
- Syntax errors in individual files: caught, file added with `imports=[]`,
  warning published to bus. Never crashes the build.
- `migrations/`, `__pycache__/`, `*.pyc` always skipped.
- Relative imports (`.models`, `..utils`) resolved to absolute dotted paths
  using the current module's own path as the base.
- Synchronous — runs once before async scanner tasks launch.

**The DNA is stored in `ScanResult.metadata["dna"]`** so every plugin can
consume it without rebuilding it.

**Commit:** `feat(core): dna_builder — live AST module registry`

---

### Step 2 — `core/rules_engine.py` — YAML Custom Rules

This is the heart of configurability. Instead of hardcoded Python violation
detection, the developer writes rules in YAML. The engine evaluates them
against the live DNA and AST.

**Rule file format (`audit_rules.yaml`):**

```yaml
# Example: enforce cross-app boundary rules for a Django project
rules:

  - id: no-cross-app-import
    name: "Direct cross-app import"
    description: "App '{source_app}' directly imports from '{target_app}'"
    severity: HIGH
    category: ARCHITECTURE
    type: boundary               # boundary | pattern | metric | dependency
    config:
      scope: cross_app           # cross_app | cross_layer | custom
      allow:
        - type: signal           # imports ending in 'signals'
          pattern: "*.signals"
        - type: task             # imports ending in 'tasks'
          pattern: "*.tasks"
        - type: bootstrap        # known framework bootstrap files
          files: ["asgi", "wsgi", "settings", "celery", "manage",
                  "routing", "apps", "admin"]
      exclude_tests: true        # test files don't count as violations
    suggestion: "Use Django signals, Celery tasks, or a REST call instead."

  - id: no-circular-import
    name: "Circular dependency"
    severity: CRITICAL
    category: ARCHITECTURE
    type: cycle
    config:
      cross_app_only: false      # detect all cycles, not just cross-app

  - id: ghost-file
    name: "Ghost file"
    description: "File exists on disk but is never imported"
    severity: LOW
    category: QUALITY
    type: ghost

  - id: high-complexity
    name: "High cyclomatic complexity"
    severity: MEDIUM
    category: QUALITY
    type: metric
    config:
      metric: cyclomatic_complexity
      threshold: 10
      scanner: radon             # delegate to this scanner plugin

  - id: no-eval
    name: "Use of eval()"
    severity: HIGH
    category: SECURITY
    type: pattern                # AST pattern match
    config:
      language: python
      pattern: "eval(...)"       # Semgrep-style pattern syntax

  - id: hardcoded-secret
    name: "Potential hardcoded secret"
    severity: HIGH
    category: SECURITY
    type: regex
    config:
      expression: '(password|secret|api_key)\s*=\s*["\'][^"\']{8,}["\']'
      exclude: ["test_", "_test.py", "example"]
```

**Rule types:**

| Type | What it does |
|------|-------------|
| `boundary` | Uses DNA import graph to detect cross-boundary imports |
| `cycle` | Iterative DFS cycle detection on the DNA import graph |
| `ghost` | Finds files in `physical_files` with no `imported_by` entries |
| `metric` | Delegates to a scanner plugin, applies a threshold |
| `pattern` | AST pattern match (Semgrep-style syntax, evaluated via `ast` module) |
| `regex` | Regex match against source text |
| `dependency` | CVE/freshness check against package list |

**`RulesEngine` class:**

```python
class RulesEngine:
    def __init__(self, rules_file: Path): ...

    def load(self) -> list[RuleDefinition]: ...

    async def evaluate(
        self,
        dna: ProjectDNA,
        scanner_findings: list[Finding],
        bus: EventBus,
    ) -> list[Finding]:
        """
        Evaluate all loaded rules against the DNA and scanner output.
        Returns Finding objects for each rule violation.
        """

    def validate(self) -> list[str]:
        """Return list of validation errors in the rules file. [] = valid."""
```

**New API endpoints:**
```
GET  /api/rules           → current rules file contents
POST /api/rules/validate  → validate a rules YAML string, return errors or []
GET  /api/rules/evaluate  → dry-run evaluate rules, return matching findings
```

**Commit:** `feat(core): rules_engine — YAML-defined custom rules evaluated against live DNA`

---

### Step 3 — `core/boundary_engine.py` — Configurable App Boundaries

The boundary engine reads the app structure from the DNA and evaluates
boundary rules specifically. Separated from the general rules engine because
boundary analysis needs the full import graph, not just individual files.

**Config section in `audit_rules.yaml`:**

```yaml
apps:
  - name: nexus_core
    paths: ["nexus_core/"]
    role: "User auth, core models, tokens, middleware"
    hub: true           # hub apps get bonus score, reduced violation penalty

  - name: nexus_economy
    paths: ["nexus_economy/"]
    role: "Wallets, payments, Celery tasks"
    hub: false

communication:
  allowed_patterns:
    - name: "Django signals"
      import_pattern: "*.signals"     # glob against the imported module path
    - name: "Celery tasks"
      import_pattern: "*.tasks"
    - name: "Shared utilities"
      import_pattern: "shared.*"      # anything in the shared/ package is OK

  bootstrap_files:
    - asgi
    - wsgi
    - settings
    - celery
    - manage
    - routing
    - apps
    - admin
```

**If the developer does not configure apps:**
- Apps are auto-detected from the DNA (unique first path segments).
- All apps are treated as equal (no hub bonus).
- Default allowed patterns: signals, tasks.
- Default bootstrap files: V1 list.
- This means V3 works usefully out of the box with zero configuration.

**`classify_import(source, target, config) → Classification`:**

```python
class Classification(Enum):
    INTERNAL = "internal"          # same app
    FRAMEWORK = "framework"        # stdlib or framework package
    BOOTSTRAP = "bootstrap"        # exempt bootstrap file
    ALLOWED = "allowed"            # matches an allowed_pattern
    TEST_CROSS_APP = "test_cross_app"  # test file cross-app import
    VIOLATION = "violation"        # everything else
```

This replaces V1's hardcoded `classify_connection()` with a fully
configurable equivalent.

**Commit:** `feat(core): boundary_engine — configurable app boundary classification`

---

### Step 4 — `core/scoring_engine.py` — Configurable Health Scoring

The scoring formula from V1 is kept because it is sound. But every constant
becomes configurable.

**Scoring config section in `audit_rules.yaml`:**

```yaml
scoring:
  penalties:
    violation_default: 5     # penalty per cross-app violation
    violation_hub: 3         # reduced penalty for hub-app violations
    security_high: 12
    security_medium: 6
    security_low: 3
    complexity_above: 10     # threshold above which complexity adds penalty
    complexity_factor: 2     # penalty per unit above threshold
    complexity_max: 20       # cap
    dead_code_per: 3         # per dead code finding
    dead_code_max: 15
    ghost_file_per: 2
    ghost_file_max: 10

  bonuses:
    hub_app: 10              # bonus for apps marked hub: true

  exclude_tests: true        # test files excluded from violation/security counts
```

**Formula (identical to V1 when using V1's defaults):**
```
score = 100
  − violations × (hub_penalty if hub else default_penalty)
  − security_high × 12, medium × 6, low × 3
  − max(0, (avg_complexity − threshold) × factor), capped
  − dead_code × per_item, capped
  − ghost_files × per_item, capped
  + hub_bonus if hub app
  = clamp(0, 100)
```

**Interface:**
```python
def calculate_scores(
    dna: ProjectDNA,
    findings: list[Finding],
    config: ScoringConfig,
) -> dict[str, AppScore]:
    """Returns one AppScore per discovered app plus fleet_average."""

@dataclass
class AppScore:
    app: str
    score: float
    breakdown: dict     # {"violations": -15, "security": -12, ...}
    is_hub: bool
    finding_counts: dict
```

**Commit:** `feat(core): scoring_engine — configurable 0–100 health scoring`

---

### Step 5 — `core/source_sync.py` — Pre-audit Source Copy

V1 never scans the live codebase. `pulse.sh` Phase 0 rsyncs the source into
a working copy before every audit. V3 makes this configurable.

```yaml
# In audit_rules.yaml or settings.json
source_sync:
  enabled: false
  source_path: "/home/user/nexus-gaming"
  working_path: "/home/user/nexus-gaming-copy"
  exclude:
    - ".git/"
    - ".venv/"
    - "__pycache__/"
    - "*.pyc"
    - "node_modules/"
    - ".env"
    - "*.log"
```

**`core/source_sync.py`:**
```python
async def sync(config: SyncConfig, bus: EventBus) -> Path:
    """
    If enabled: rsync source → working_path, return working_path.
    If disabled: return project_path from Settings.
    Uses asyncio subprocess for rsync (POSIX) or shutil.copytree (Windows).
    Emits PROGRESS events so the UI shows sync progress.
    """
```

**Commit:** `feat(core): source_sync — configurable pre-audit copy`

---

### Step 6 — `core/fix_queue.py` — Finding Status Tracking

Developers need to track which findings they have addressed. The fix queue
persists status across runs.

```python
class FixQueue:
    """
    Tracks status of findings across audit runs.
    Status: open | in_progress | done | snoozed
    
    When a finding that was marked 'done' reappears in a new run,
    it is flagged as 'reappeared' so the developer is alerted.
    """
    def get_status(self, finding_id: str) -> str | None: ...
    def update_status(self, finding_id: str, status: str, note: str = "") -> None: ...
    def sync(self, current_findings: list[Finding]) -> SyncResult: ...

@dataclass
class SyncResult:
    reappeared: list[str]     # finding IDs marked done but back in current run
    new_count: int
    resolved_count: int
```

**New API endpoints:**
```
GET  /api/fixqueue              → all statuses
POST /api/fixqueue/{finding_id} → {"status": "done", "note": "Fixed in PR #42"}
```

**Commit:** `feat(core): fix_queue — persistent finding status tracking`

---

### Step 7 — `core/timeline.py` — Score History & Violation Persistence

```python
def load_score_history(history_dir: Path, max_runs: int = 30) -> dict:
    """
    Reads audit_history/ to build trend data.
    Returns: {"labels": [...], "apps": {app: [scores]}, "fleet_avg": [...]}
    """

def compute_violation_persistence(
    history_dir: Path,
    current_findings: list[Finding],
    max_runs: int = 5,
) -> dict[str, str]:
    """
    Returns per-finding-id persistence trend:
    "new" | "persistent" | "intermittent" | "resolved"
    
    Consumed by the rules engine to annotate findings before AI analysis.
    """
```

**New API endpoint:** `GET /api/trends`

**Commit:** `feat(core): timeline — score history and violation persistence`

---

### Step 8 — `core/git_context.py` — Git Context

```python
async def get_git_context(project_path: Path) -> dict:
    """
    Returns {"remote_url": str, "branch": str, "commit": str}
    SSH remotes converted to HTTPS. Returns {} silently on any failure.
    """
```

Stored in `Job.git_context`. Shown in the dashboard audit header.
Links findings to their exact commit so developers can share a link to
the exact state of the code that produced a violation.

**Commit:** `feat(core): git_context — remote, branch, commit`

---

### Step 9 — `core/key_pool.py` — Multi-Key AI Rotation

```python
class KeyPool:
    """
    Manages up to 20 API keys per provider.
    Keys loaded from: GEMINI_API_KEY ... GEMINI_API_KEY_20
                      ANTHROPIC_API_KEY ... ANTHROPIC_API_KEY_20
    Rotates to next key on HTTP 429 (rate limit).
    Re-enables exhausted keys after a cooldown period.
    """
    def next_key(self, provider: str) -> str: ...
    def mark_exhausted(self, provider: str, key: str) -> None: ...
```

**Commit:** `feat(core): key_pool — multi-key AI rotation`

---

### Step 10 — `core/fast_check.py` — Git-Diff Incremental Scan

```python
def get_changed_files(project_path: Path) -> list[Path] | None:
    """
    Returns files changed since last commit via git diff.
    Returns None if git unavailable.
    """
```

When `POST /api/run` includes `{"fast": true}`:
- DNA is still built fully (cheap, needed for graph).
- Scanner file lists filtered to changed files only.
- Log: "Fast mode: {N} changed files scanned, {M} unchanged skipped."
- Falls back to full scan if git unavailable, with a warning.

**Commit:** `feat(core): fast_check — git-diff incremental scan`

---

### Step 11 — `core/dep_cache.py` — Dependency Cache

```python
class DepCache:
    """
    Caches PyPI/OSV results keyed by (package, version). TTL: 24h.
    force_rescan=True in Settings bypasses cache entirely.
    This is the first feature that honours the force_rescan flag.
    """
    def get(self, package: str, version: str) -> dict | None: ...
    def set(self, package: str, version: str, data: dict) -> None: ...
```

**Commit:** `feat(core): dep_cache — dependency result cache with TTL`

---

### Step 12 — `ai/prompts.py` — Config-Driven AI Prompts

V1's prompts are hardcoded for Nexus. V3's prompts are built from the
developer's own config — specifically the `role` and `arch_description`
they wrote for their apps.

```python
def build_system_prompt(config: AuditConfig) -> str:
    """
    Builds the AI system prompt dynamically from the audit config.
    If the developer wrote app roles and an arch description,
    those go in here — making the AI as project-aware as V1 is for Nexus.
    """

def build_violation_prompt(
    finding: Finding,
    persistence: str,          # "new" | "persistent" | "intermittent"
    config: AuditConfig,
) -> tuple[str, str]:          # (system, user)
    """Deep analysis of a single boundary violation."""

def build_health_prompt(
    app: str,
    score: AppScore,
    config: AuditConfig,
) -> tuple[str, str]:
    """4-sentence health narrative for one app."""

def build_upgrade_prompt(packages: list[dict]) -> tuple[str, str]:
    """Package upgrade advisor — returns structured JSON."""

def build_cve_prompt(cves: list[dict]) -> tuple[str, str]:
    """CVE security advisor — returns structured JSON."""
```

**The key difference from V1:** `build_system_prompt()` generates
the architecture context from the developer's config, not from hardcoded
Nexus knowledge. A developer who fills in their app roles and writes
an `arch_description` in their config gets AI output as targeted as V1's.

**Commit:** `feat(ai): prompts — config-driven AI prompts for any project`

---

### Step 13 — Orchestrator upgrade

Update `orchestrator._run_job()` to run the full intelligence pipeline:

```
1.  Source sync (if enabled)
2.  Build ProjectDNA (dna_builder)
3.  Load audit config (rules file + scoring config + app boundaries)
4.  Parallel scanner execution (existing Phase 3 scanners)
5.  Rules engine evaluation (boundary, cycle, ghost, pattern, metric)
6.  Scoring (per-app AppScore + fleet average)
7.  Coupling matrix
8.  Fix queue sync
9.  Violation persistence (timeline)
10. Git context
11. AI recommendations (if enabled)
12. Change summary vs previous run
13. Write audit_data_complete.json (all of the above)
14. Write audit_history/{timestamp}.json
15. Generate markdown report
16. Publish STATUS "completed"
```

**audit_data_complete.json shape** (everything V1 produces, plus more):
```json
{
  "metadata":             { timestamp, project, capabilities, git_context },
  "dna":                  { module_path: ModuleEntry },
  "apps":                 { app_name: AppScore },
  "fleet_average":        float,
  "findings":             [ Finding ],
  "violations":           [ Finding (category=ARCHITECTURE) ],
  "allowed_comms":        [ AllowedCommunication ],
  "cycles":               [ CycleDict ],
  "ghost_files":          [ Finding ],
  "security_findings":    [ Finding (category=SECURITY) ],
  "quality_findings":     [ Finding (category=QUALITY) ],
  "dependency_scan":      { packages, cves, outdated },
  "coupling_matrix":      CouplingMatrix,
  "recommendations":      [ RecommendationDict ],
  "fix_queue":            { finding_id: StatusEntry },
  "change_summary":       { new, resolved, score_deltas },
  "timeline":             { labels, apps, fleet_avg },
  "config_health":        ConfigHealthResult,
  "rules_evaluated":      [ RuleSummary ]
}
```

**Commit:** `feat(orchestrator): full intelligence pipeline`

---

### Step 14 — Rules UI and all frontend intelligence tabs

**Rules editor (new Settings tab):**
```
┌─────────────────────────────────────────────────────────┐
│ Audit Rules                               [Load Default] │
├─────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────────┐   │
│ │ rules:                                            │   │
│ │   - id: no-cross-app-import                       │   │
│ │     severity: HIGH                                │   │
│ │     type: boundary                                │   │
│ │     ...                                           │   │
│ └───────────────────────────────────────────────────┘   │
│                          [Validate]  [Save Rules]        │
├─────────────────────────────────────────────────────────┤
│ Apps (auto-detected — annotate below)                    │
│  nexus_core    [Hub ✓] [User auth, core models      ]   │
│  nexus_economy [Hub ○] [Wallets, payments           ]   │
│  [+ Add app]                     [Auto-detect apps]      │
└─────────────────────────────────────────────────────────┘
```

**Intelligence tabs (all 12 from V1, data-driven):**

| Tab | Data source | Key V1 feature replicated |
|-----|-------------|--------------------------|
| App Scores | `/api/scores` | 0–100 cards with ↑↓→ trend arrows |
| Config Health | `/api/data`.config_health | Banner + per-check table |
| Violations | `/api/data`.violations | Cross-app table + persistence badges |
| Security | `/api/data`.security_findings | Bandit/semgrep findings |
| Dependencies | `/api/data`.dependency_scan | CVE + upgrade commands |
| Recommendations | `/api/data`.recommendations | AI cards + fix queue buttons |
| Graph | `/api/data`.dna + violations | vis-network, 3 modes |
| Trends | `/api/trends` | Score history line chart |
| Coupling Map | `/api/coupling` | NxN heatmap, click to drill down |
| Ghost Files | `/api/data`.ghost_files | Files never imported |
| Cycles | `/api/data`.cycles | Circular dependency chains |
| Manifest | `/api/data`.dna | Full module registry, searchable |

**Commit:** `feat(frontend): intelligence tabs + rules editor UI`

---

### Step 15 — Markdown report

```python
def generate_markdown_report(
    job: Job,
    scores: dict[str, AppScore],
    config: AuditConfig,
    output_path: Path,
) -> None:
```

Output: `audit_report.md` in the project root.
Sections: metadata, fleet scores, per-app cards, violations table,
security table, dependencies, AI recommendations.

`GET /api/report/markdown` → serve as download.

**Commit:** `feat(core): markdown_report`

---

### Step 16 — Default rules bundle

Ship V3 with a default `default_rules.yaml` that encodes sensible defaults:

```yaml
# nexus_audit_v3/rules/default_rules.yaml
# General-purpose audit rules. Works out of the box for any Python project.
# Override any rule in your own audit_rules.yaml.

rules:
  - id: no-circular-import
    severity: CRITICAL
    type: cycle

  - id: ghost-file
    severity: LOW
    type: ghost

  - id: high-complexity
    severity: MEDIUM
    type: metric
    config: { metric: cyclomatic_complexity, threshold: 10 }

  - id: dead-code
    severity: LOW
    type: metric
    config: { metric: dead_code, scanner: vulture }

scoring:
  penalties:
    violation_default: 5
    security_high: 12
    security_medium: 6
    security_low: 3
    complexity_max: 20
    dead_code_max: 15
  bonuses:
    hub_app: 10
  exclude_tests: true
```

A developer starting with a new project gets meaningful output immediately.
They then add their own boundary rules as they learn their codebase.

A developer who wants V1-equivalent output for their Nexus project creates
`nexus_audit.yaml` extending the defaults with the cross-app boundary rules.
No source code editing required.

**Commit:** `feat(rules): default rules bundle + example nexus config`

---

### Step 17 — Final integration and tag

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q
ruff check .
mypy core/ plugins/ api/ orchestrator.py server.py --strict
git add -A
git commit -m "feat: v1.0.0 — full intelligence pipeline, configurable rules engine"
git tag v1.0.0
```

---

## How a Developer Produces V1-Equivalent Output on Their Project

1. Point V3 at the project: configure `project_path` in settings.
2. Click "Auto-detect apps" — V3 reads the DNA, lists every first-party app.
3. Annotate each app: name, role description, mark hub apps.
4. Add boundary rules to `audit_rules.yaml` matching the project's conventions.
5. Run the audit.

The output is architecturally aware, scored per app, with AI recommendations
that know what each app is supposed to own — because the developer told V3.
No Python source editing. No hardcoded constants. No locked-to-one-project.

---

## Definition of Done

- [ ] DNA built from AST on every run, no pre-existing files required
- [ ] `audit_rules.yaml` loads, validates, and is enforced by the rules engine
- [ ] Default rules work with zero configuration
- [ ] Boundary rules classify imports using `allowed_patterns` and `bootstrap_files`
  from config, not hardcoded constants
- [ ] Scoring uses config weights; defaults produce same numbers as V1
- [ ] Source sync works when enabled
- [ ] All 12 dashboard tabs populated with real data
- [ ] Rules editor in UI: edit, validate, save YAML rules
- [ ] App annotator in UI: auto-detect, name, role, hub flag
- [ ] Fix queue persists across runs; reappearance banner works
- [ ] Score history trends populated from audit_history/
- [ ] vis-network graph renders in 3 modes
- [ ] Violation persistence badges shown (new/persistent/intermittent/resolved)
- [ ] AI prompts built from config, not hardcoded strings
- [ ] Multi-key pool rotates on 429
- [ ] `--fast` git-diff mode works
- [ ] `force_rescan` bypasses dep_cache
- [ ] Markdown report generated after every run
- [ ] `pytest`, `ruff`, `mypy --strict` all exit 0
- [ ] `git tag v1.0.0` exists

---

*Plan written: 2026-05-31 | Follows: Phase 4 (`v0.4.0`) | Target: `v1.0.0`*
*Philosophy: V1 behaviour replicated by configuration, not by copying code.*
