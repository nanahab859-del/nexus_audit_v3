# Nexus Audit V3 — Phase 3: Scanner Plugins
**Status:** Planning  
**Depends on:** Phase 2.2 complete (`v0.2.2` tag exists)  
**Goal:** Replace the Phase 2 stub scan with real scanner plugins, wire them into
the orchestrator, and produce a genuine audit result end-to-end. After Phase 3,
`POST /api/run` on a real Python project returns real findings.

---

## What Phase 3 Delivers

### Pre-step: Fix `save()` double-encryption guard

Before any scanner work, fix the fragile `startswith("gAAAAA")` check identified
in Phase 2.2 verification. This is Step 0 — it touches `core/settings.py` only.

### Scanner plugins (6 total)

| Plugin file | Tool wrapped | Category | Languages |
|------------|-------------|----------|-----------|
| `plugins/security/bandit_plugin.py` | Bandit | SECURITY | Python |
| `plugins/quality/vulture_plugin.py` | Vulture | QUALITY | Python |
| `plugins/quality/radon_plugin.py` | Radon | QUALITY | Python |
| `plugins/dependency/safety_plugin.py` | pip-audit | DEPENDENCY | Python |
| `plugins/architecture/lizard_plugin.py` | Lizard | ARCHITECTURE | Python |
| `plugins/quality/semgrep_plugin.py` | Semgrep | QUALITY | `["*"]` |

### Orchestrator upgrade

Replace the stub `_run_job` with real parallel scanner dispatch.

### Supporting infrastructure

| File | What it is |
|------|-----------|
| `core/file_discovery.py` | Walk project tree, classify files by language, respect `.gitignore` |
| `plugins/security/__init__.py` | Package marker |
| `plugins/quality/__init__.py` | Package marker |
| `plugins/dependency/__init__.py` | Package marker |
| `plugins/architecture/__init__.py` | Package marker |

---

## Folder Layout After Phase 3

```
nexus_audit_v3/
├── core/
│   ├── file_discovery.py     ← NEW
│   └── settings.py           ← EDIT (Step 0: save() fix)
├── plugins/
│   ├── __init__.py
│   ├── base.py
│   ├── security/
│   │   ├── __init__.py       ← NEW
│   │   └── bandit_plugin.py  ← NEW
│   ├── quality/
│   │   ├── __init__.py       ← NEW
│   │   ├── vulture_plugin.py ← NEW
│   │   ├── radon_plugin.py   ← NEW
│   │   └── semgrep_plugin.py ← NEW
│   ├── dependency/
│   │   ├── __init__.py       ← NEW
│   │   └── safety_plugin.py  ← NEW
│   └── architecture/
│       ├── __init__.py       ← NEW
│       └── lizard_plugin.py  ← NEW
├── orchestrator.py            ← EDIT: replace stub with real dispatch
├── tests/
│   ├── test_file_discovery.py ← NEW
│   ├── test_plugin_bandit.py  ← NEW
│   ├── test_plugin_vulture.py ← NEW
│   ├── test_plugin_radon.py   ← NEW
│   ├── test_plugin_safety.py  ← NEW
│   ├── test_plugin_lizard.py  ← NEW
│   ├── test_plugin_semgrep.py ← NEW
│   └── test_orchestrator.py   ← NEW
└── docs/
    └── PHASE3_PLAN.md         ← this file
```

---

## Step-by-Step Implementation Order

---

### Step 0 — Fix `save()` double-encryption guard in `core/settings.py`

**The problem:**  
The current guard `if not api_key_to_save.startswith("gAAAAA")` relies on a
Fernet implementation detail. It will silently double-encrypt if Fernet ever
changes its token prefix, or fail to encrypt a legitimate API key that happens
to start with those characters.

**The correct approach — always decrypt on load, always encrypt on save:**

Since `load()` already decrypts, the `Settings` object in memory always holds
plaintext. `save()` therefore receives plaintext every time — no pre-encrypted
value will ever reach it. The fragile prefix check can be removed entirely.

**Replace the entire `save()` function body with:**

```python
async def save(settings: Settings, path: Path = Path("settings.json")) -> None:
    """
    Serialize Settings to dict and write atomically.
    api_key is always plaintext in the Settings object (load() decrypts it).
    Encrypt unconditionally before writing to disk.
    """
    api_key_to_save = settings.api_key
    if api_key_to_save:
        try:
            from core.security import encrypt
            api_key_to_save = encrypt(api_key_to_save)
        except Exception:
            # Encryption failure: save plaintext rather than lose the key.
            # This should only happen if cryptography is not installed.
            import warnings
            warnings.warn(
                "api_key could not be encrypted before saving — "
                "storing in plaintext. Install 'cryptography' to fix this.",
                stacklevel=2,
            )

    data: dict[str, Any] = {
        "project_path": str(settings.project_path),
        "api_key": api_key_to_save,
        "ai_enabled": settings.ai_enabled,
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "force_rescan": settings.force_rescan,
        "scanners": settings.scanners,
        "scanner_configs": settings.scanner_configs,
        "ui": settings.ui,
    }
    await write_json(path, data)
```

**Update `tests/test_settings.py`:**
- Add test: call `save()` twice with the same plaintext key → both writes produce
  valid Fernet tokens; `load()` after each returns the original plaintext
  (proves no double-encryption).
- Existing round-trip tests must still pass.

**Commit:** `fix(settings): remove fragile Fernet prefix guard in save()`

---

### Step 1 — `core/file_discovery.py`

All scanners need a filtered, classified list of files. Centralising this
prevents each scanner from walking the tree independently.

**Interface:**

```python
@dataclass
class DiscoveredFile:
    path: Path           # absolute path
    relative: str        # relative to project root (used in Finding.file)
    language: str        # "python", "javascript", "unknown", etc.
    size_bytes: int

def discover(
    project_root: Path,
    respect_gitignore: bool = True,
) -> list[DiscoveredFile]:
    """
    Walk project_root recursively.
    Skips: .git/, __pycache__/, node_modules/, *.pyc, binary files.
    Classifies files by extension + shebang line.
    Respects .gitignore if present and respect_gitignore=True.
    Returns sorted list (by relative path) for deterministic output.
    """

LANGUAGE_MAP: dict[str, str] = {
    ".py":   "python",
    ".js":   "javascript",
    ".ts":   "typescript",
    ".jsx":  "javascript",
    ".tsx":  "typescript",
    ".java": "java",
    ".go":   "go",
    ".rs":   "rust",
    ".rb":   "ruby",
    ".php":  "php",
    ".cs":   "csharp",
    ".cpp":  "cpp",
    ".c":    "c",
    ".sh":   "shell",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md":   "markdown",
}
```

**Rules:**
- `.gitignore` parsing uses the `pathspec` library (`pip install pathspec`).
  Add `pathspec` to `pyproject.toml` runtime deps.
- If `.gitignore` does not exist, `respect_gitignore=True` is a no-op.
- Binary files (detected by reading first 8192 bytes and checking for null bytes)
  are skipped and never returned.
- Shebangs (`#!/usr/bin/env python3`) override the extension classification.
- `discover()` is synchronous — it is called once per job before the async
  scanner tasks are launched.

**Commit:** `feat(core): file_discovery — walk, classify, gitignore`

---

### Step 2 — `plugins/security/bandit_plugin.py`

Wraps the `bandit` CLI tool. Bandit is the primary security scanner for Python —
it detects hardcoded passwords, SQL injection risks, use of `eval`, insecure
hashing, and more. The old V2 tool used Bandit; we carry it forward.

**Scanner metadata:**
```python
name = "bandit"
version = "1.0.0"
languages = ["python"]
category = Category.SECURITY
requires_ai = False
timeout = 120
```

**`scan()` implementation:**

```
1. Filter target files to Python only (language == "python")
2. If no Python files: return []
3. Run: bandit -r {project_root} -f json -q
   --exclude {comma-separated exclude_dirs from config}
4. Parse JSON output → list[Finding]
5. Emit progress events at 0%, 50%, 100%
6. Return findings
```

**Bandit JSON → Finding mapping:**

```
bandit result.issue_severity → Severity:
    HIGH   → Severity.HIGH
    MEDIUM → Severity.MEDIUM
    LOW    → Severity.LOW

bandit result.issue_confidence → stored in Finding.description

Finding fields:
    scanner     = "bandit"
    file        = result.filename (made relative to project_root)
    line        = result.line_number
    column      = 0  (bandit does not report columns)
    severity    = mapped above
    category    = Category.SECURITY
    title       = result.issue_text
    description = f"Confidence: {result.issue_confidence}. {result.issue_text}"
    suggestion  = result.more_info  (URL to bandit docs)
    cwe         = result.issue_cwe.id if present else None
    cvss_score  = None  (bandit does not provide CVSS)
```

**Config keys (from `settings.scanner_configs["bandit"]`):**
```
exclude_dirs: list[str]   default: ["tests", "migrations", "venv", ".venv"]
severity_filter: str      default: "low"  (low | medium | high)
```

**Rules:**
- Run bandit via `asyncio.create_subprocess_exec` — never `subprocess.run` (blocks).
- If bandit is not installed: emit a LOG warning and return `[]` — never crash.
- Test files (paths containing `/test` or `_test.py`) have their security findings
  downgraded one severity level (matches V2 behaviour).
- Timeout via `asyncio.wait_for(proc.communicate(), timeout=self.timeout)`.

**Commit:** `feat(plugins): bandit security scanner`

---

### Step 3 — `plugins/quality/vulture_plugin.py`

Detects dead code: unused functions, classes, variables, and imports.
Carried forward from V2.

**Scanner metadata:**
```python
name = "vulture"
version = "1.0.0"
languages = ["python"]
category = Category.QUALITY
requires_ai = False
timeout = 60
```

**`scan()` implementation:**

```
1. Filter to Python files only
2. Run: vulture {project_root} --min-confidence {min_confidence}
3. Parse line-by-line text output (vulture has no JSON mode)
4. Each line format: "{file}:{line}: {message} ({confidence}% confidence)"
5. Map to Finding
```

**Vulture line → Finding mapping:**
```
severity    = LOW for all dead code findings
category    = Category.QUALITY
title       = message (e.g. "unused function 'old_handler'")
description = f"{confidence}% confidence this code is unused"
suggestion  = "Remove this code or add a # noqa comment if intentional"
cwe         = None
cvss_score  = None
```

**Config keys:**
```
min_confidence: int   default: 60  (0-100; higher = fewer false positives)
whitelist_path: str   default: None
```

**Rules:**
- Parse errors on individual lines are skipped (log warning), not fatal.
- If vulture is not installed: LOG warning, return `[]`.

**Commit:** `feat(plugins): vulture dead code scanner`

---

### Step 4 — `plugins/quality/radon_plugin.py`

Measures cyclomatic complexity. High-complexity functions are harder to test
and maintain. Carried forward from V2 (previously via `lizard`; radon is
Python-native and more accurate for Python code).

**Scanner metadata:**
```python
name = "radon"
version = "1.0.0"
languages = ["python"]
category = Category.QUALITY
requires_ai = False
timeout = 60
```

**`scan()` implementation:**

```
1. Filter to Python files only
2. Run: radon cc {project_root} --json --min C
   (--min C = only report complexity rank C or worse: C, D, E, F)
3. Parse JSON output
4. Map each function/method entry to a Finding
```

**Radon complexity rank → Severity mapping:**
```
A, B  → skip (not reported)
C     → Severity.LOW
D     → Severity.MEDIUM
E, F  → Severity.HIGH
```

**Finding fields:**
```
title       = f"High complexity in {function_name} (rank {rank}, score {complexity})"
description = f"Cyclomatic complexity {complexity} — consider refactoring"
suggestion  = "Break this function into smaller units or reduce branching"
```

**Config keys:**
```
min_rank: str   default: "C"   (A | B | C | D | E | F)
```

**Rules:**
- `__init__` methods are reported but at one rank lower than calculated
  (constructor complexity is expected to be higher).
- If radon is not installed: LOG warning, return `[]`.

**Commit:** `feat(plugins): radon complexity scanner`

---

### Step 5 — `plugins/dependency/safety_plugin.py`

Checks installed packages against known CVE databases. Uses `pip-audit`
(successor to `safety`) as the underlying tool.

**Scanner metadata:**
```python
name = "safety"
version = "1.0.0"
languages = ["python"]
category = Category.DEPENDENCY
requires_ai = False
timeout = 120
```

**`scan()` implementation:**

```
1. Look for requirements.txt, pyproject.toml, or setup.py in project_root
2. If none found: emit LOG info "No dependency files found" and return []
3. Run: pip-audit --format json --requirement {requirements_file}
   OR:   pip-audit --format json  (scans current environment)
4. Parse JSON output → list[Finding]
```

**pip-audit JSON → Finding mapping:**
```
vuln.fix_versions present → Severity.HIGH
vuln.fix_versions empty   → Severity.MEDIUM  (no fix available — still serious)

Finding fields:
    title       = f"{package} {installed_version} has known vulnerability"
    description = vuln.description
    suggestion  = f"Upgrade to {fix_version}" if fix available else
                  "No fix available — consider replacing this dependency"
    cwe         = None
    cvss_score  = vuln.aliases first CVSS score if present else None
```

**Config keys:**
```
requirements_file: str   default: None  (auto-detected)
skip_packages: list[str] default: []
```

**Rules:**
- If `pip-audit` is not installed: LOG warning, return `[]`.
- Network calls are made by `pip-audit` itself — the plugin has no timeout
  responsibility beyond `asyncio.wait_for(proc, timeout=self.timeout)`.
- One Finding per vulnerability, not per package (a package with 3 CVEs → 3 Findings).

**Commit:** `feat(plugins): pip-audit dependency vulnerability scanner`

---

### Step 6 — `plugins/architecture/lizard_plugin.py`

Measures code structure metrics: lines of code, parameter count, token count.
Complements radon (which measures complexity); lizard catches functions that are
too long or have too many parameters even if not branchy. Carried forward from V2.

**Scanner metadata:**
```python
name = "lizard"
version = "1.0.0"
languages = ["python", "javascript", "typescript", "java", "cpp", "c", "go"]
requires_ai = False
timeout = 120
```

**`scan()` implementation:**

```
1. Filter files to lizard's supported languages
2. Run: lizard {project_root} --csv -l {lang1} -l {lang2} ...
3. Parse CSV output
4. Apply thresholds → emit Findings only for functions exceeding them
```

**Thresholds and Severity:**
```
Lines of code (LOC) per function:
    > 100  → Severity.HIGH
    > 50   → Severity.MEDIUM
    > 30   → Severity.LOW

Parameter count:
    > 7    → Severity.HIGH
    > 5    → Severity.MEDIUM

Token count:
    > 1000 → Severity.HIGH
    > 500  → Severity.MEDIUM
```

**Finding fields:**
```
title       = f"Function '{name}' exceeds {metric} threshold ({value} > {limit})"
description = f"LOC={loc}, params={params}, tokens={tokens}, complexity={complexity}"
suggestion  = "Consider splitting this function or reducing its responsibilities"
category    = Category.ARCHITECTURE
```

**Config keys:**
```
loc_threshold_high:    int  default: 100
loc_threshold_medium:  int  default: 50
param_threshold_high:  int  default: 7
param_threshold_medium:int  default: 5
```

**Rules:**
- One Finding per threshold violation per function (a function exceeding both LOC
  and param limits → two Findings).
- If lizard is not installed: LOG warning, return `[]`.

**Commit:** `feat(plugins): lizard code structure scanner`

---

### Step 7 — `plugins/quality/semgrep_plugin.py`

Runs Semgrep with a curated rule set. Unlike the other scanners, Semgrep is
language-agnostic (`languages = ["*"]`) and catches higher-level patterns:
hardcoded secrets, insecure function calls, anti-patterns.

**Scanner metadata:**
```python
name = "semgrep"
version = "1.0.0"
languages = ["*"]   # runs on all files
category = Category.SECURITY
requires_ai = False
timeout = 180
```

**`scan()` implementation:**

```
1. Build ruleset: use custom rules_path from config if provided,
   else default to "p/python p/security-audit"
2. Run: semgrep --config {ruleset} {project_root} --json --quiet
3. Parse JSON output → list[Finding]
```

**Semgrep JSON → Finding mapping:**
```
result.extra.severity:
    ERROR   → Severity.HIGH
    WARNING → Severity.MEDIUM
    INFO    → Severity.LOW

Finding fields:
    title       = result.check_id (rule ID, e.g. "python.lang.security.insecure-hash")
    description = result.extra.message
    suggestion  = result.extra.fix if present else None
    cwe         = first CWE in result.extra.metadata.cwe if present
    cvss_score  = None
```

**Config keys:**
```
rules_path:  str        default: "p/python"
extra_rules: list[str]  default: []
timeout:     int        default: 180
```

**Rules:**
- If semgrep is not installed: LOG warning, return `[]` — this scanner is
  optional, not required.
- Semgrep can be slow on large codebases — emit progress events every 10 files.
- Deduplicate: if a finding has the same `file + line + check_id` as a Bandit
  finding, the `Finding.id` hash will match and the orchestrator's dedup pass
  will collapse them automatically.

**Commit:** `feat(plugins): semgrep multi-language scanner`

---

### Step 8 — Upgrade `orchestrator.py`

Replace the Phase 2 stub `_run_job` with real parallel scanner dispatch.

**New `_run_job` algorithm:**

```
Phase 1: Discovery
  discovered = file_discovery.discover(job.project_path)
  publish_log("info", f"Discovered {len(discovered)} files")
  publish_progress("discovery", 100, "")

Phase 2: Load plugins
  registry = PluginRegistry(plugins_dir=Path("plugins"))
  registry.load()
  enabled_scanners = [
      registry.get(name)
      for name, enabled in settings.scanners.items()
      if enabled and registry.get(name) is not None
  ]
  If no enabled scanners: publish_log("warning", "No scanners enabled") → complete

Phase 3: Parallel scan
  scanner_config = settings.scanner_configs
  tasks = [
      asyncio.create_task(
          _run_single_scanner(scanner_cls, job, discovered, scanner_config, bus)
      )
      for scanner_cls in enabled_scanners
  ]
  results: list[ScanResult] = await asyncio.gather(*tasks, return_exceptions=True)

Phase 4: Merge and write
  job.scan_results = [r for r in results if isinstance(r, ScanResult)]
  job.state = "completed"
  job.finished_at = datetime.now(UTC)
  await write_results(job)
  await bus.publish_status("completed", job.id)
```

**`_run_single_scanner` helper:**

```python
async def _run_single_scanner(
    scanner_cls: type[BaseScanner],
    job: Job,
    discovered: list[DiscoveredFile],
    config: dict,
    bus: EventBus,
) -> ScanResult:
    scanner = scanner_cls()
    result = ScanResult(
        scanner=scanner.name,
        started_at=datetime.now(UTC),
        finished_at=None,
        findings=[],
        error=None,
    )
    await bus.publish_log("info", f"Starting {scanner.name} scanner")
    try:
        findings = await asyncio.wait_for(
            scanner.scan(job.project_path, config.get(scanner.name, {}), bus),
            timeout=scanner.timeout,
        )
        result.findings = findings
    except asyncio.TimeoutError:
        result.error = f"Scanner {scanner.name} timed out after {scanner.timeout}s"
        await bus.publish_log("warning", result.error)
    except Exception as e:
        result.error = str(e)
        await bus.publish_log("error", f"Scanner {scanner.name} failed: {e}")
    finally:
        result.finished_at = datetime.now(UTC)
    return result
```

**Write results helper:**

```python
async def _write_results(self, job: Job) -> None:
    data = _job_to_dict(job)
    await write_json(Path("audit_data_complete.json"), data)
    history_dir = Path("audit_history")
    history_dir.mkdir(exist_ok=True)
    timestamp = job.started_at.strftime("%Y-%m-%dT%H-%M-%S")
    await write_json(history_dir / f"{timestamp}.json", data)
```

**Rules:**
- Scanners run concurrently — no sequential bottleneck.
- One scanner crashing does not abort the others (`return_exceptions=True`).
- The job writes partial results even if some scanners failed (their `ScanResult.error`
  is non-None and `findings` is empty, but the other scanners' results are present).
- `asyncio.CancelledError` from `cancel_job()` propagates cleanly — the `finally`
  block in `_run_job` sets `state = "cancelled"` and writes whatever partial results exist.

**Commit:** `feat(orchestrator): replace stub with real parallel scanner dispatch`

---

### Step 9 — `core/file_discovery.py` tests + scanner tests

**`test_file_discovery.py`:**
- `discover()` on a temp dir with known files returns the correct list
- Binary files are excluded
- `.pyc` files are excluded
- `.git/` directory is excluded
- Shebang `#!/usr/bin/env python3` on a `.sh` file classifies it as Python
- With a `.gitignore` containing `*.log`, `.log` files are excluded
- Empty directory returns `[]`

**Per-scanner tests (one file each):**

Each scanner test file follows the same pattern:
```
1. Create a minimal Python project in tmp_path with a known bad file
   (e.g. a file with a hardcoded password for bandit, a dead function for vulture)
2. Instantiate the plugin, call scan()
3. Assert at least one Finding is returned
4. Assert Finding fields are populated correctly (file, line, severity, category)
5. Assert Finding.id is a 16-char hex string
6. Test the "tool not installed" path: mock subprocess to return exit code 127
   → scan() returns [] without raising
```

**`test_orchestrator.py`:**
- Full job lifecycle: `start_job` → `asyncio.sleep(0)` yield → `current_job().state == "completed"`
- `start_job` while running → `ConflictError`
- `cancel_job` → state becomes `"cancelled"`
- `audit_data_complete.json` written after completion
- `audit_history/` entry created after completion
- Scanner crash → job still completes with that scanner's `ScanResult.error` set

**Commit:** `test: Phase 3 test suite — file discovery, scanners, orchestrator`

---

### Step 10 — Update `pyproject.toml` dependencies

Add scanner tools as optional dependencies so they can be installed in one command:

```toml
[project.optional-dependencies]
scanners = [
    "bandit>=1.7",
    "vulture>=2.10",
    "radon>=6.0",
    "pip-audit>=2.7",
    "lizard>=1.17",
    "semgrep>=1.60",
    "pathspec>=0.12",
]
```

Install all scanners: `pip install -e ".[scanners]"`

**Commit:** `chore: add scanner optional dependencies to pyproject.toml`

---

### Step 11 — Final commit and tag

```bash
cd ~/my_tools/nexus_audit_v3
pip install -e ".[scanners]"
pytest --tb=short -q        # must exit 0
mypy core/ plugins/ api/ orchestrator.py server.py --strict
ruff check .
git add -A
git commit -m "feat: Phase 3 complete — real scanner plugins"
git tag v0.3.0
```

---

## What Phase 3 Does NOT Include

| Excluded | Reason |
|----------|--------|
| Frontend | Phase 4 |
| SQLite result cache / `force_rescan` honour | Phase 5 — `force_rescan` is accepted in settings but currently a no-op; every run is a full scan. |
| AI-powered recommendations | Phase 7 |
| Scoring system (0–100 per app) | Phase 5 |
| Fix queue (mark findings Done/Snoozed) | Phase 5 |
| Cross-app coupling map | Phase 5 |
| Run history diff | Phase 6 |
| Custom Semgrep rules from the old V2 tool | Can be referenced from `nexus_audit/` and ported later |

---

## Scanner Tool Availability Policy

Every scanner plugin must follow this contract:

```
Tool installed  → scan() runs normally, returns findings
Tool missing    → scan() emits one LOG warning and returns []
Tool times out  → orchestrator cancels task, ScanResult.error is set
Tool crashes    → exception caught in _run_single_scanner, ScanResult.error is set
```

**No scanner is ever required.** A user with only `bandit` installed gets security
findings. A user with nothing installed gets an empty result with a LOG warning per
missing tool. The tool never fails to complete a job because a scanner is absent.

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `pip-audit` instead of `safety` | `safety` requires a paid API key for current CVE data; `pip-audit` is free and actively maintained |
| Parallel scanner execution | Most scanners are I/O-bound (subprocess); parallel reduces total job time from sum to max |
| One `ScanResult` per scanner | Clean separation; a scanner crash doesn't corrupt other results |
| `asyncio.create_subprocess_exec` not `subprocess.run` | Non-blocking; essential since scanners run concurrently in the same event loop |
| `pathspec` for `.gitignore` | Battle-tested library used by `black`, `mypy`, and others; handles all `.gitignore` glob patterns correctly |
| Scanner tools as optional deps | Users can install only what they need; the tool never hard-fails on a missing scanner |
| Thresholds in config, not hardcoded | Phase 5's settings UI will expose them; Phase 3 just reads from `scanner_configs` |

---

## Definition of Done — Phase 3

- [ ] `save()` in `core/settings.py` has no `startswith("gAAAAA")` guard
- [ ] `save()` round-trip test (save twice, load once, get original plaintext) passes
- [ ] `core/file_discovery.py` implemented and tested
- [ ] All 6 scanner plugins present in correct sub-directories
- [ ] Each sub-directory has an `__init__.py`
- [ ] Each scanner returns `[]` gracefully when its tool is not installed
- [ ] `orchestrator._run_job` uses real scanner dispatch (no `asyncio.sleep` stub)
- [ ] `audit_data_complete.json` written after a real scan
- [ ] `audit_history/` entry created after a real scan
- [ ] `mypy ... --strict` exits 0
- [ ] `pytest --tb=short -q` exits 0 (all Phase 1 + 2 + 2.2 + 3 tests)
- [ ] `ruff check .` exits 0
- [ ] `pip install -e ".[scanners]"` installs all tools without conflict
- [ ] `git tag v0.3.0` exists
- [ ] No file in `plugins/` imports from `api/` or `frontend/`

---

*Plan written: 2026-05-28 | Follows: Phase 2.2 (`v0.2.2`) | Precedes: Phase 4 (Frontend)*
