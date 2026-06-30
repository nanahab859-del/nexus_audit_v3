# Nexus Audit V3 — Phase 1.2: Foundation Hardening
**Status:** Planning  
**Depends on:** Phase 1 complete (`v0.1.0-phase1` tag exists)  
**Goal:** Small, targeted additions that cost almost nothing now but prevent real headaches in Phases 2–4.  
Phase 1.2 does not add new modules. It only hardens what Phase 1 built.

---

## What Phase 1.2 Delivers

| Item | File touched | Why now |
|------|-------------|---------|
| `settings.schema.json` moved to Step 1 scope | `settings.schema.json` | Tests can't run reliably without it present from the start |
| `core/__main__.py` placeholder | `core/__main__.py` | Prevents `ImportError` when the entry point is invoked before Phase 2 |
| Sub-package `__init__.py` rule documented | `core/registry.py` docstring | Prevents silent plugin-not-found bugs in Phase 3 |
| Async callback enforcement in `EventBus` | `core/events.py` | Already intended in the plan — just wasn't coded explicitly |
| Event history ring buffer | `core/events.py` | Saves Phase 2 from building its own replay mechanism for SSE |
| `os.replace` cross-platform note | `core/atomic.py` | One-line comment clarification, no logic change |
| `Finding.id` hash inputs aligned | `core/models.py` + tests | `rule_id` was mentioned in the plan but doesn't exist as a field — align the hash with actual fields |

---

## Folder Changes After Phase 1.2

No new files except `core/__main__.py`. Everything else is edits to existing files.

```
nexus_audit_v3/
├── core/
│   ├── __main__.py      ← NEW (stub only)
│   ├── models.py        ← EDIT: clarify Finding.id hash inputs
│   ├── events.py        ← EDIT: async enforcement + ring buffer
│   ├── atomic.py        ← EDIT: one-line comment only
│   └── registry.py      ← EDIT: docstring addition only
├── settings.schema.json ← EDIT: confirm it exists and is complete
└── tests/
    ├── test_models.py   ← EDIT: align determinism test with actual hash inputs
    └── test_events.py   ← EDIT: add ring buffer + async enforcement tests
```

---

## Step-by-Step Implementation Order

---

### Step 1 — Confirm and complete `settings.schema.json`

The file already exists from Phase 1. This step verifies it is complete and correct so tests never hit a "file not found" path.

**Required schema contents:**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Nexus Audit V3 Settings",
  "type": "object",
  "required": ["project_path", "scanners"],
  "properties": {
    "project_path": { "type": "string", "minLength": 1 },
    "api_key":      { "type": ["string", "null"] },
    "ai_enabled":   { "type": "boolean", "default": false },
    "ai_provider":  { "type": "string",  "default": "claude" },
    "ai_model":     { "type": "string",  "default": "claude-opus-4-7" },
    "force_rescan": { "type": "boolean", "default": false },
    "scanners":     { "type": "object",  "additionalProperties": { "type": "boolean" } },
    "scanner_configs": {
      "type": "object",
      "additionalProperties": { "type": "object" }
    },
    "ui": { "type": "object" }
  },
  "additionalProperties": false
}
```

**Rules:**
- `additionalProperties: false` — unknown keys in `settings.json` raise a schema error.
  Wait — this conflicts with the Phase 1 rule "unknown keys silently ignored."
  Resolution: set `additionalProperties: true` in the schema; the "ignore unknown keys"
  behaviour is enforced in `core/settings.py` by stripping unknown fields before
  validation, not by the schema itself.
- If the file already matches the above, no change is needed. Just confirm and move on.

**Commit:** `fix(settings): confirm schema complete and accessible from Step 1`

---

### Step 2 — Add `core/__main__.py` placeholder

Prevents `ImportError` / broken install when someone runs `nexus-audit` before Phase 2 exists.

**Full file contents:**

```python
"""
Nexus Audit V3 — entry point stub.
The server is implemented in Phase 2. Running this now is safe but does nothing.
"""


def main() -> None:
    print("Nexus Audit V3 — Phase 2 (API server) not yet implemented.")
    print("Run `nexus-audit` again after Phase 2 is complete.")


if __name__ == "__main__":
    main()
```

**Rules:**
- No imports from `core.events`, `core.settings`, or any other module — this stub
  must work even in a broken environment.
- `pyproject.toml` entry point already points here (`core.__main__:main`) — no change
  needed there.

**Commit:** `feat(core): __main__ stub — prevents broken entry point before Phase 2`

---

### Step 3 — Fix `Finding.id` hash inputs

The Phase 1 plan described `Finding.id` as `sha256(scanner+file+line+rule_id)[:16]`
but `Finding` has no `rule_id` field. The actual hash must be derived from fields
that exist on the dataclass.

**Correct hash input** (use exactly these fields, in this order):

```
sha256( f"{scanner}:{file}:{line}:{title}" )[:16]
```

`title` replaces the nonexistent `rule_id`. It's the closest stable identifier for
what the finding is. Two scanners reporting the same file+line+title will produce
the same ID — which is the desired deduplication behaviour.

**Check the existing implementation in `core/models.py`:**
- If it already uses `title` (or equivalent), no code change is needed.
- If it uses `rule_id` or something else, update `__post_init__` to match the above.

**Update `tests/test_models.py`:**
- The determinism test must use exactly `scanner + file + line + title` as the
  varying inputs.
- Add a test: two different scanners reporting the same `file + line + title`
  produce the **same** `Finding.id` — this is the deduplication guarantee.
- Add a test: same scanner, different `title` → different `Finding.id`.

**Commit:** `fix(models): align Finding.id hash inputs with actual dataclass fields`

---

### Step 4 — Enforce async callbacks in `EventBus`

The plan said this was intended. Phase 1 may or may not have coded it.
This step makes it explicit and tested.

**In `core/events.py`, `subscribe()` must contain:**

```python
if not asyncio.iscoroutinefunction(callback):
    raise TypeError(
        f"EventBus.subscribe requires an async callback, "
        f"got {type(callback).__name__}: {callback!r}"
    )
```

**Rules:**
- The check runs before the callback is stored — a sync function never enters the registry.
- The `TypeError` message names the offending callback so the developer knows exactly
  what to fix.

**Update `tests/test_events.py`:**
- Add test: `subscribe` with a sync lambda raises `TypeError`.
- Add test: `subscribe` with an `async def` succeeds.
- Existing tests must still pass.

**Commit:** `fix(events): enforce async callbacks in EventBus.subscribe`

---

### Step 5 — Add event history ring buffer to `EventBus`

Phase 2's SSE endpoint needs to replay recent events to a newly connected client
(using the `Last-Event-ID` header). Adding this to `EventBus` now is 15 lines of code
and avoids Phase 2 building a separate mechanism.

**Changes to `core/events.py`:**

Add two new items to `EventBus.__init__`:
```python
self._history: list[Event] = []
self._history_max: int = 100
```

In `publish()`, after delivering to subscribers, append to history:
```python
self._history.append(event)
if len(self._history) > self._history_max:
    self._history = self._history[-self._history_max:]
```

Add new method:
```python
def history(self, since_index: int = 0) -> list[Event]:
    """
    Return events from the ring buffer starting at since_index.
    Phase 2 SSE route passes the client's Last-Event-ID as since_index.
    Returns an empty list if since_index >= current buffer length.
    """
    return self._history[since_index:]
```

**Rules:**
- The buffer is in-memory only — it is lost on process restart. This is intentional;
  SSE replay only covers the current session.
- `_history_max = 100` is a module-level constant, not hardcoded. Phase 2 can
  change it via settings if needed.
- `history()` is synchronous — it is called from the SSE route before the async
  send loop, not from inside a running event handler.

**Update `tests/test_events.py`:**
- Add test: after publishing 5 events, `bus.history()` returns all 5.
- Add test: after publishing 110 events, `bus.history()` returns only the last 100.
- Add test: `bus.history(since_index=3)` returns events from index 3 onward.

**Commit:** `feat(events): add ring buffer + history() for SSE replay`

---

### Step 6 — Document sub-package `__init__.py` requirement in registry

No code change. One docstring addition to `core/registry.py`.

**Add to the `PluginRegistry` class docstring:**

```
Plugin sub-directories (e.g., plugins/security/, plugins/quality/) must each
contain an __init__.py file so that importlib.import_module() can resolve them
as Python packages. A sub-directory without __init__.py will be silently skipped
during discovery — no error, no crash, but the plugins inside will not be found.
Phase 3 scanner scaffolding handles this automatically.
```

**Rules:**
- This is documentation only. No logic change.
- The note about "silently skipped" is important — it tells future developers
  exactly what happens so they don't spend time debugging missing plugins.

**Commit:** `docs(registry): document sub-package __init__.py requirement`

---

### Step 7 — Add `os.replace` cross-platform note to `atomic.py`

One-line comment. No logic change.

**In `core/atomic.py`, the comment above `os.replace()` should read:**

```python
# os.replace() is atomic on POSIX and effectively atomic on Windows
# when source and destination are on the same filesystem (always true here).
```

**Commit:** `docs(atomic): clarify os.replace cross-platform behaviour`

---

### Step 8 — Final tag

After all tests pass:

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q        # must exit 0
mypy core/ plugins/ --strict
ruff check .
git add -A
git commit -m "feat: Phase 1.2 complete — foundation hardening"
git tag v0.1.2
```

---

## What Phase 1.2 Does NOT Include

| Excluded | Reason |
|----------|--------|
| Event history persistence to disk | Phase 2 — the orchestrator owns job state on disk |
| `core/security.py` (API key encryption) | Phase 2 — needed when the server starts |
| Any scanner implementation | Phase 3 |
| Any frontend file | Phase 4 |
| Changing any public API already established in Phase 1 | Breaking change — Phase 1 is tagged and stable |

---

## Definition of Done — Phase 1.2

- [ ] `settings.schema.json` present, valid JSON, passes `jsonschema` self-validation
- [ ] `nexus-audit` entry point runs without `ImportError` (prints Phase 2 stub message)
- [ ] `Finding.id` hash uses `scanner + file + line + title` — confirmed in code and tests
- [ ] `EventBus.subscribe` raises `TypeError` on sync callback — confirmed in tests
- [ ] `bus.history()` returns last N events — confirmed in tests
- [ ] `core/registry.py` docstring documents the `__init__.py` requirement
- [ ] `core/atomic.py` has the cross-platform comment
- [ ] `mypy core/ plugins/ --strict` exits 0
- [ ] `pytest --tb=short -q` exits 0
- [ ] `ruff check .` exits 0
- [ ] `git tag v0.1.2` exists

---

*Plan written: 2026-05-27 | Follows: Phase 1 (`v0.1.0-phase1`) | Precedes: Phase 2*
