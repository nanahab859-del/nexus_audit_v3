# Nexus Audit V3 — Phase 2.2: API Layer Hardening
**Status:** Planning  
**Depends on:** Phase 2 complete (`v0.2.0` tag exists)  
**Goal:** Fix two load-bearing gaps in the Phase 2 implementation before Phase 3
adds real scanners. Without these fixes, SSE replay is broken and AI plugins
will receive an encrypted key instead of a plaintext one — both are silent failures
that would be painful to diagnose in Phase 3.

---

## What Phase 2.2 Fixes

| # | Gap | Symptom if unfixed | File(s) touched |
|---|-----|--------------------|----------------|
| 1 | `EventBus` has no sequential event IDs | SSE `id:` field is empty; `Last-Event-ID` replay silently delivers nothing | `core/events.py`, `tests/test_events.py` |
| 2 | `core/settings.py` does not decrypt `api_key` on load | Orchestrator and all future AI plugins receive the Fernet ciphertext string instead of the real key | `core/settings.py`, `tests/test_settings.py` |

These are the only two changes. No new files. No scope expansion.

---

## Folder Changes After Phase 2.2

```
nexus_audit_v3/
├── core/
│   ├── events.py      ← EDIT: sequential event IDs + proper history()
│   └── settings.py    ← EDIT: decrypt on load, encrypt on save
└── tests/
    ├── test_events.py  ← EDIT: verify IDs, history(since_id), replay
    └── test_settings.py← EDIT: verify round-trip with encryption
```

No new files. No other modules touched.

---

## Step-by-Step Implementation Order

---

### Step 1 — Add sequential event IDs to `EventBus`

**Problem in detail:**  
The SSE wire format requires an `id:` field on every event:
```
id: 42
event: progress
data: {"scanner": "stub", "percent": 50}

```
The client sends `Last-Event-ID: 42` on reconnect. The server calls
`bus.history(since_id=42)` to replay everything after that point.

Currently `Event` has no `id` field and `EventBus` has no history buffer,
so `routes_stream.py`'s replay loop has nothing to work with.

**Changes to `core/events.py`:**

Add to `EventBus.__init__`:
```python
self._event_counter: int = 0
self._history: deque[tuple[int, Event]] = deque(maxlen=500)
self._history_lock: asyncio.Lock = asyncio.Lock()
```

In `publish()`, after delivering to subscribers:
```python
async with self._history_lock:
    self._event_counter += 1
    event_id = self._event_counter
    self._history.append((event_id, event))
```

Replace (or add) the `history()` method:
```python
def history(self, since_id: int = 0) -> list[tuple[int, Event]]:
    """
    Return all buffered (id, event) tuples where id > since_id.
    The SSE route passes the client's Last-Event-ID integer as since_id.
    Returns [] if since_id >= current counter or buffer is empty.
    Synchronous — safe to call from inside an async route before the send loop.
    """
    return [(eid, ev) for eid, ev in self._history if eid > since_id]
```

**Rules:**
- `deque(maxlen=500)` replaces any earlier `list`-based buffer from Phase 1.2.
  500 is large enough to cover a full stub scan replay plus headroom.
- `_event_counter` starts at 0 and increments by 1 per published event —
  never resets within a process lifetime.
- `history()` is synchronous because it is called before the async send loop,
  not from inside an event handler.
- The lock only protects the append — subscriber delivery is unchanged.

**Update `api/routes_stream.py`** to use the new interface:
```python
# On connect: read Last-Event-ID header
last_id = int(request.headers.get("Last-Event-ID", "0"))

# Replay buffered events
for event_id, event in bus.history(since_id=last_id):
    await response.write(
        f"id: {event_id}\nevent: {event.type.value}\n"
        f"data: {json.dumps(event.payload)}\n\n".encode()
    )

# Live events: publish with sequential ID
# (queue callback receives the (id, event) tuple)
```

**Update `tests/test_events.py`:**
- Add test: after publishing N events, each `(id, event)` tuple has a unique,
  incrementing integer id starting from 1.
- Add test: `history(since_id=0)` returns all events.
- Add test: `history(since_id=3)` returns only events with id > 3.
- Add test: after 600 publishes, `history()` returns at most 500 events
  (deque maxlen enforced).
- Add test: `history()` on a fresh bus returns `[]`.

**Commit:** `fix(events): add sequential event IDs and deque history buffer`

---

### Step 2 — Encrypt on save, decrypt on load in `core/settings.py`

**Problem in detail:**  
Current flow:
```
POST /api/settings
  → routes_settings encrypts key → saves to disk ✓

GET /api/settings  (or server startup)
  → core.settings.load() reads raw file
  → Settings.api_key = "gAAAAA..." (Fernet ciphertext) ✗
  → orchestrator.start_job receives Settings with encrypted key ✗
  → AI plugin calls Gemini/Claude with garbage key → 401 ✗
```

Required flow:
```
POST /api/settings
  → routes_settings encrypts key → saves to disk ✓

core.settings.load()
  → reads raw file
  → decrypts api_key if present → Settings.api_key = "real-key" ✓
  → orchestrator, scanners, AI plugin all receive plaintext ✓

GET /api/settings (view layer)
  → loads Settings (plaintext key in memory)
  → redacts to "***" before sending to client ✓  (already done in routes_settings)
```

**Changes to `core/settings.py`:**

In `load()`, after constructing the `Settings` object, add:
```python
if settings.api_key and settings.api_key not in ("", "***"):
    try:
        from core.security import decrypt
        settings = dataclasses.replace(settings, api_key=decrypt(settings.api_key))
    except Exception:
        # Key is corrupt or was stored in plaintext (legacy/test).
        # Log a warning; do not crash. Leave as-is so tests without
        # real encryption still work.
        import warnings
        warnings.warn(
            "api_key in settings.json could not be decrypted — "
            "key may be stored in plaintext or is corrupt.",
            stacklevel=2,
        )
```

In `save()`, encrypt the key before serialising:
```python
if settings.api_key and settings.api_key not in ("", "***"):
    try:
        from core.security import encrypt
        settings = dataclasses.replace(settings, api_key=encrypt(settings.api_key))
    except Exception:
        pass  # If encryption fails, save plaintext rather than lose the key
```

**Rules:**
- Use `dataclasses.replace()` — `Settings` must not be mutated in-place.
- The `try/except` in `load()` is intentional: unit tests that write plain
  settings files without encrypted keys must not break.
- `"***"` must never be passed to `decrypt()` — it is a view-layer sentinel only.
- The circular import risk (`settings.py` ← `security.py`) is avoided by using
  a local import inside the function, not a module-level import.

**Update `tests/test_settings.py`:**
- Add test: save settings with a plaintext `api_key` → load → `api_key` field
  contains the original plaintext (round-trip through encrypt/decrypt).
- Add test: settings file with no `api_key` → load → `api_key` is `None`
  (no decryption attempted, no crash).
- Add test: settings file with `api_key = ""` → load → `api_key` is `""`
  (empty string treated as no key).
- Add test: settings file with a corrupt/non-Fernet `api_key` string → load →
  `api_key` is left as-is (warning emitted, no crash).
- Existing round-trip tests must still pass.

**Commit:** `fix(settings): decrypt api_key on load, encrypt on save`

---

### Step 3 — Final tag

After all tests pass:

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q        # must exit 0
mypy core/ plugins/ api/ orchestrator.py server.py --strict
ruff check .
git add -A
git commit -m "feat: Phase 2.2 complete — API layer hardening"
git tag v0.2.2
```

---

## What Phase 2.2 Does NOT Include

| Excluded | Reason |
|----------|--------|
| Any new endpoints | Phase 2 endpoints are complete |
| Scanner implementations | Phase 3 |
| Frontend | Phase 4 |
| Run history diffing | Phase 6 |
| Changing the SSE wire format | Already correct in Phase 2 |
| Modifying `core/security.py` | Works as implemented |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `deque(maxlen=500)` not `list` | Bounded memory; O(1) append; auto-evicts oldest events |
| Sequential integer IDs, not UUIDs | SSE `Last-Event-ID` is an integer by convention; simpler comparison in `history()` |
| Local import for `security` in `settings.py` | Avoids circular import at module level; acceptable since `load()` is called once at startup |
| `try/except` around decrypt in `load()` | Plaintext keys in test fixtures must not break the test suite |
| `dataclasses.replace()` not mutation | `Settings` may be `frozen=True` in the future; replace is always safe |

---

## Definition of Done — Phase 2.2

- [ ] `EventBus.publish` assigns a sequential integer ID to every event
- [ ] `bus.history(since_id=N)` returns only events with id > N
- [ ] `bus.history()` on a fresh bus returns `[]`
- [ ] After 600 publishes, `len(bus.history())` ≤ 500
- [ ] `routes_stream.py` sends `id: {N}` on every SSE event
- [ ] `routes_stream.py` replays `bus.history(since_id=last_event_id)` on connect
- [ ] `core.settings.load()` returns plaintext `api_key` when file has encrypted value
- [ ] `core.settings.save()` writes encrypted `api_key` to disk
- [ ] Settings with no `api_key` load without error
- [ ] Corrupt `api_key` in settings file emits warning, does not crash
- [ ] `mypy ... --strict` exits 0
- [ ] `pytest --tb=short -q` exits 0 (all Phase 1 + Phase 2 + Phase 2.2 tests)
- [ ] `ruff check .` exits 0
- [ ] `git tag v0.2.2` exists

---

*Plan written: 2026-05-28 | Follows: Phase 2 (`v0.2.0`) | Precedes: Phase 3 (Scanner Plugins)*
