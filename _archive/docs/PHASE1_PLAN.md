# Nexus Audit V3 — Phase 1: Core Foundation
**Status:** Planning  
**Goal:** Build the structural skeleton every later phase plugs into.  
Nothing in Phase 1 runs an audit. Everything in Phase 1 makes auditing possible.

> **Important:** `nexus_audit_v3/` is a clean-slate rewrite.  
> The old tool lives at `my_tools/nexus_audit/` and is referenced only — never modified.  
> If something from the old tool is useful (a scoring formula, a prompt, a scanner config),
> it is read and reimplemented here. The old code is never imported or patched.

---

## What Phase 1 Delivers

Six self-contained modules — five inside `core/`, one inside `plugins/`:

| Module | What it is |
|--------|-----------|
| `core/models.py` | Every shared data structure (`Finding`, `ScanResult`, `Job`, `Settings`) |
| `core/events.py` | In-process async pub-sub (`EventBus`) |
| `core/registry.py` | Plugin discovery, import, validation |
| `core/atomic.py` | Safe file writes (tmp → rename, never corrupts) |
| `core/settings.py` | Load / validate / save `settings.json` |
| `plugins/base.py` | `BaseScanner` abstract class + `Severity` / `Category` enums |

Plus the project scaffold: `pyproject.toml`, `.gitignore`, `settings.schema.json`, `README.md`, and a full test suite.

---

## Folder Layout After Phase 1

```
my_tools/
├── nexus_audit/          ← OLD TOOL — do not touch (reference only)
└── nexus_audit_v3/       ← NEW TOOL — everything below is ours
    ├── core/
    │   ├── __init__.py
    │   ├── models.py
    │   ├── events.py
    │   ├── registry.py
    │   ├── atomic.py
    │   └── settings.py
    ├── plugins/
    │   ├── __init__.py
    │   └── base.py
    ├── tests/
    │   ├── __init__.py
    │   ├── test_models.py
    │   ├── test_events.py
    │   ├── test_registry.py
    │   ├── test_atomic.py
    │   └── test_settings.py
    ├── docs/
    │   └── PHASE1_PLAN.md   ← this file
    ├── settings.schema.json
    ├── pyproject.toml
    ├── .gitignore
    └── README.md
```

**Flat nesting rule:** During Phase 1, Python code lives at most one level deep
from the project root (`core/` and `plugins/` only).  
`api/`, `frontend/`, `orchestrator.py` do not exist yet — those are Phase 2 and later.

---

## Step-by-Step Implementation Order

Each step is one git commit. The order is load-bearing: each step's output is an input to the next.

---

### Step 1 — Project scaffold

**Files:** `pyproject.toml`, `.gitignore`, `README.md`

**`pyproject.toml`** declares:
- `name = "nexus-audit-v3"`, `version = "0.1.0"`, `requires-python = ">=3.11"`
- Runtime deps: `aiohttp`, `aiofiles`, `jsonschema`, `cryptography`
- Dev deps: `pytest`, `pytest-asyncio`, `mypy`, `ruff`
- `[tool.pytest.ini_options]` sets `asyncio_mode = "auto"`
- Entry point stubbed: `nexus-audit = "core.__main__:main"`

**`.gitignore`** covers:
`__pycache__/`, `*.pyc`, `.env`, `settings.json`, `audit_history/`,
`*.tmp`, `.mypy_cache/`, `.ruff_cache/`, `dist/`, `.venv/`

**`README.md`** — single paragraph: what this is, what the old tool is, and that this is V3.

**Commit:** `chore: project scaffold`

---

### Step 2 — `core/models.py`

Single source of truth for every data shape in the system.
No other module defines data structures — they all import from here.

**`Severity` enum** (ordered, lowest → highest for comparison):
`INFO | LOW | MEDIUM | HIGH | CRITICAL`

**`Category` enum:**
`SECURITY | QUALITY | PERFORMANCE | DEPENDENCY | ARCHITECTURE`

**`Finding` dataclass** (`frozen=True` — immutable after creation):
```
id: str               # computed in __post_init__: sha256(scanner+file+line+rule_id)[:16]
scanner: str
file: str             # relative path from project root
line: int
column: int
severity: Severity
category: Category
title: str
description: str
suggestion: str | None
cwe: str | None       # e.g. "CWE-89"
cvss_score: float | None
```

**`ScanResult` dataclass** (mutable — findings accumulate):
```
scanner: str
started_at: datetime
finished_at: datetime | None
findings: list[Finding]
error: str | None     # set if the scanner crashed; findings may be partial
```

**`Job` dataclass** (mutable — state changes as the audit runs):
```
id: str               # uuid4, generated in __post_init__
project_path: Path
started_at: datetime
finished_at: datetime | None
state: Literal["running", "completed", "cancelled", "failed"]
scan_results: list[ScanResult]
```

**`Settings` dataclass**:
```
project_path: Path
api_key: str | None
ai_enabled: bool
ai_provider: str          # "gemini" | "claude"
ai_model: str
force_rescan: bool
scanners: dict[str, bool] # scanner_name → enabled
scanner_configs: dict[str, dict]
ui: dict
```

**Rules:**
- `Finding.id` is deterministic — the same issue discovered by two scanners gets the same id, enabling deduplication.
- `Finding` is `frozen=True` — mutations after emit are bugs, caught at runtime.
- `datetime` fields always store UTC-aware datetimes (`datetime.now(UTC)`).

**Commit:** `feat(core): models — Finding, ScanResult, Job, Settings`

---

### Step 3 — `core/events.py`

In-process async pub-sub. Every scanner and every API route communicates through the bus — they never import each other.

**`EventType` enum:** `STATUS | PROGRESS | LOG | FINDING`

**`Event` dataclass** (`frozen=True`):
```
type: EventType
payload: dict
timestamp: datetime
```

**Payload shapes** (documented in docstrings, not enforced by types at this stage):
```
STATUS   → {"state": str, "job_id": str | None}
PROGRESS → {"scanner": str, "percent": int, "file": str}
LOG      → {"level": str, "message": str}
FINDING  → {"finding": Finding}   ← Finding as dict for JSON-safe transport
```

**`EventBus` class:**
```
subscribe(event_type, callback) → token (str)
    # callback: async def fn(event: Event) → None
    # returns opaque token used for unsubscribing

unsubscribe(token) → None

async publish(event: Event) → None
    # delivers to all subscribers for event.type
    # subscriber exceptions are caught, logged to stderr, never re-raised
    # uses asyncio.gather(return_exceptions=True)

# Convenience publishers:
async publish_status(state: str, job_id: str | None) → None
async publish_progress(scanner: str, percent: int, file: str) → None
async publish_log(level: str, message: str) → None
async publish_finding(finding: Finding) → None
```

**Module-level singleton:** `bus = EventBus()`  
All code does `from core.events import bus` — one bus for the whole process.

**Rules:**
- `asyncio.Lock` protects the subscriber dict (thread-safe for sync callers).
- Subscriber callbacks must be async — sync functions are rejected with a clear error.
- `unsubscribe` with an unknown token is a no-op (no KeyError).

**Commit:** `feat(core): EventBus with async pub-sub`

---

### Step 4 — `plugins/base.py`

The contract every scanner must satisfy. Phase 1 defines the abstract class only — no concrete scanners yet (those are Phase 3).

**`BaseScanner` abstract class:**
```python
class BaseScanner(ABC):
    name: ClassVar[str]             # slug: [a-z0-9_-]+
    version: ClassVar[str]          # semver string
    languages: ClassVar[list[str]]  # ["python"], ["*"] for language-agnostic
    category: ClassVar[Category]
    requires_ai: ClassVar[bool] = False
    timeout: ClassVar[int] = 300    # seconds before the scan is killed

    @abstractmethod
    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]: ...
```

**Why `ClassVar`:** the registry reads scanner metadata without instantiating.
Instantiation happens only when a scan actually runs.

**`validate_scanner_class(cls: type) → list[str]`**  
Returns a list of error strings (empty = valid). Used by the registry.
Checks: all `ClassVar` fields present, `name` matches `[a-z0-9_-]+` regex,
`languages` is non-empty, `scan` is implemented, `category` is a `Category` enum value.

**Commit:** `feat(plugins): BaseScanner protocol`

---

### Step 5 — `core/registry.py`

Discovers and loads every valid scanner plugin at startup.

**Algorithm:**
```
1. Accept plugins_dir: Path (default: ./plugins/)
2. Walk every .py file in plugins_dir (max depth 2 — flat nesting rule)
3. importlib.import_module each file by its dotted path
4. Inspect every class defined in that module
5. For each class that is a subclass of BaseScanner (and not BaseScanner itself):
     errors = validate_scanner_class(cls)
     if errors is empty → register under cls.name
     if errors non-empty → log warning with each error, skip
6. ImportError or SyntaxError in a plugin file → log warning, skip, never crash
```

**`PluginRegistry` class:**
```
def __init__(self, plugins_dir: Path = Path("plugins")): ...
def load(self) → None          # idempotent; safe to call multiple times
def get(name: str) → type[BaseScanner] | None
def all() → list[type[BaseScanner]]
def names() → list[str]
```

**Rules:**
- `load()` is synchronous (imports + inspection only, no async I/O).
- If `plugins_dir` does not exist → log warning, return, no crash.
- Duplicate `name` → last one loaded wins, warning logged.

**Commit:** `feat(core): PluginRegistry — discovery and loading`

---

### Step 6 — `core/atomic.py`

The old tool had a real bug: a crash mid-write could leave `audit_data_complete.json` truncated.
This module prevents that everywhere in V3.

**Interface:**
```python
async def write_json(path: Path, data: dict | list) → None:
    """
    Writes data as formatted JSON atomically.
    Process: serialise → write to path.with_suffix(".tmp") → os.replace(tmp, path).
    os.replace() is atomic on POSIX. The .tmp file is always cleaned up.
    """

async def read_json(path: Path) → dict | list | None:
    """
    Reads and parses JSON from path.
    Returns None if path does not exist.
    Raises json.JSONDecodeError if the file is present but corrupt.
    """
```

**Rules:**
- Uses `aiofiles` — no blocking `open()`.
- `json.dumps` with `indent=2` and `default=str` so `datetime`, `Path`, `Enum` serialize without crashing.
- `.tmp` cleanup happens in a `finally` block — survives exceptions.

**Commit:** `feat(core): atomic JSON read/write`

---

### Step 7 — `core/settings.py`

Loads, validates, and saves `settings.json` against the JSON Schema.

**Interface:**
```python
DEFAULT_SETTINGS: Settings   # module-level constant — safe defaults, no project_path

def load(path: Path = Path("settings.json")) → Settings:
    """
    If file missing → return DEFAULT_SETTINGS.
    If file present → validate against settings.schema.json → return Settings.
    Raises SettingsValidationError (subclass of ValueError) on schema mismatch.
    """

async def save(settings: Settings, path: Path = Path("settings.json")) → None:
    """Serialise Settings → dict and write atomically via core.atomic.write_json."""

class SettingsValidationError(ValueError): ...
```

**`settings.schema.json`** (project root, not inside `core/`):
- Required: `project_path`, `scanners`
- All other fields optional with defaults matching `DEFAULT_SETTINGS`
- `project_path` must be a string (validated as a path after load)

**Rules:**
- `load()` is synchronous — called before the event loop starts.
- `save()` is async — called from inside a running API route.
- Relative `project_path` is resolved and made absolute against the settings file's directory.
- Unknown keys in `settings.json` are silently ignored (forward compatibility).

**Commit:** `feat(core): settings load/validate/save`

---

### Step 8 — Tests

One file per module. Every test is self-contained and runnable with `pytest tests/test_<module>.py`.

| File | Coverage |
|------|---------|
| `test_models.py` | `Finding.id` is deterministic; same inputs always produce same id; `Finding` is immutable (frozen); `Severity` members exist |
| `test_events.py` | publish → subscriber called; subscriber exception doesn't block others; unsubscribe stops delivery; multiple subscribers all receive; publish with no subscribers is a no-op |
| `test_registry.py` | valid plugin discovered; plugin missing `name` skipped with warning; plugin with bad `name` slug skipped; `ImportError` in plugin file skipped; `get()` returns correct class; missing `plugins_dir` logs warning without crashing |
| `test_atomic.py` | write→read round-trip; result matches original data; `.tmp` file absent after success; reading missing file returns `None`; corrupt file raises `JSONDecodeError` |
| `test_settings.py` | missing file returns `DEFAULT_SETTINGS`; valid file loads correctly; invalid field raises `SettingsValidationError`; save→load round-trip preserves all fields |

**Rules:**
- `asyncio_mode = "auto"` in `pyproject.toml` — no `@pytest.mark.asyncio` needed.
- Filesystem tests use `tmp_path` fixture — no writes to the project directory.
- Zero network calls.

**Commit:** `test: Phase 1 test suite`

---

### Step 9 — Final commit and tag

After all tests pass:

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q        # must exit 0
mypy core/ plugins/ --strict
ruff check .
git add -A
git commit -m "feat: Phase 1 complete — core foundation"
git tag v0.1.0-phase1
```

---

## What Phase 1 Explicitly Does NOT Include

| Excluded | Reason |
|----------|--------|
| HTTP server | Phase 2 |
| Scanner implementations (Bandit, Vulture, etc.) | Phase 3 |
| Frontend | Phase 4 |
| AI calls | Phase 7 |
| `orchestrator.py` | Phase 2 |
| `core/security.py` (API key encryption) | Phase 2 — needed when the server starts |
| Anything from `nexus_audit/` copied verbatim | Reference only — always reimplement |

---

## Key Decisions (Do Not Revisit Without Good Reason)

| Decision | Rationale |
|----------|-----------|
| `Finding` is frozen | Findings are immutable facts; mutation after emit is always a bug |
| `Finding.id` is a content hash | Deduplication is free; two scanners can't produce different IDs for the same issue |
| `EventBus` uses callbacks, not queues | Simpler; backpressure not needed at this scale |
| One `bus` singleton exported from `core/events` | Avoids dependency injection boilerplate in every scanner and route |
| `load()` in settings is synchronous | Settings are needed before the event loop starts |
| `ClassVar` metadata on scanners | Registry reads metadata without constructing the scanner object |
| Max plugin dir depth = 2 | Enforces the flat nesting rule; prevents accidentally importing test helpers |

---

## Definition of Done — Phase 1

- [ ] All 6 modules written and fully type-annotated
- [ ] `mypy core/ plugins/ --strict` exits 0
- [ ] `pytest --tb=short -q` exits 0
- [ ] `ruff check .` exits 0
- [ ] `pip install -e .` works in a fresh venv
- [ ] `git log --oneline` shows one commit per step (Steps 1–9)
- [ ] `git tag v0.1.0-phase1` exists
- [ ] No file in `core/` or `plugins/` imports from `api/`, `frontend/`, or `orchestrator`:
  ```bash
  grep -r "from api\|from frontend\|import orchestrator" core/ plugins/
  # must return nothing
  ```

---

*Plan written: 2026-05-27 | Project: my_tools/nexus_audit_v3/*
