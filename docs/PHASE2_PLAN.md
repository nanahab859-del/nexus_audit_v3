# Nexus Audit V3 — Phase 2: API Server
**Status:** Planning  
**Depends on:** Phase 1.2 complete (`v0.1.2` tag exists)  
**Goal:** A fully working HTTP server that exposes every REST endpoint and the SSE
stream. No scanners yet — the server runs, accepts requests, manages job state,
and streams events. Phase 3 plugs real scanners in.

---

## What Phase 2 Delivers

| Module | What it is |
|--------|-----------|
| `api/server.py` | aiohttp app factory — wires routes, CORS, error middleware |
| `api/routes_data.py` | `GET /api/status`, `GET /api/data`, `GET /api/history`, `GET /api/history/{id}` |
| `api/routes_settings.py` | `GET /api/settings`, `POST /api/settings` |
| `api/routes_run.py` | `POST /api/run`, `POST /api/cancel` |
| `api/routes_stream.py` | `GET /api/stream` — SSE, replays ring buffer on connect |
| `api/middleware.py` | CORS (localhost only), JSON error handler, 127.0.0.1 binding guard |
| `core/security.py` | API key encrypt/decrypt at rest using `cryptography.fernet` |
| `orchestrator.py` | Job lifecycle — start, cancel, track state, write results atomically |
| `server.py` | Entry point — replaces the Phase 1 stub in `core/__main__.py` |

Plus a full test suite covering every endpoint and the SSE stream.

---

## Folder Layout After Phase 2

```
nexus_audit_v3/
├── api/
│   ├── __init__.py
│   ├── server.py           ← NEW
│   ├── routes_data.py      ← NEW
│   ├── routes_settings.py  ← NEW
│   ├── routes_run.py       ← NEW
│   ├── routes_stream.py    ← NEW
│   └── middleware.py       ← NEW
├── core/
│   ├── __init__.py
│   ├── __main__.py         ← EDIT: point to new server entry point
│   ├── atomic.py
│   ├── events.py
│   ├── models.py
│   ├── registry.py
│   ├── security.py         ← NEW
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
│   ├── test_settings.py
│   ├── test_security.py    ← NEW
│   ├── test_api_data.py    ← NEW
│   ├── test_api_settings.py← NEW
│   ├── test_api_run.py     ← NEW
│   └── test_api_stream.py  ← NEW
├── orchestrator.py         ← NEW
├── server.py               ← NEW (entry point)
├── audit_history/          ← created at runtime, gitignored
├── docs/
│   ├── PHASE1_PLAN.md
│   ├── PHASE1_2_PLAN.md
│   └── PHASE2_PLAN.md
├── settings.schema.json
├── pyproject.toml
└── .gitignore
```

---

## Step-by-Step Implementation Order

---

### Step 1 — `core/security.py`

API key encryption at rest. Done first because `routes_settings.py` depends on it.

**Interface:**

```python
def derive_key() -> bytes:
    """
    Derives a Fernet key from a machine-stable identifier.
    Uses: sha256( hostname + platform + python_version ) → base64-urlsafe 32 bytes.
    Falls back to a random key written to .key_cache in the project dir if the
    machine identifier is unstable (e.g. Docker with random hostname).
    Never raises — always returns a valid key.
    """

def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64 ciphertext string."""

def decrypt(ciphertext: str) -> str:
    """
    Decrypt a ciphertext string. Returns original plaintext.
    Raises: InvalidToken if ciphertext is corrupt or key has changed.
    """

class InvalidToken(Exception): ...
```

**Rules:**
- The key is derived, not stored — no `.key` file on disk unless the fallback is needed.
- `encrypt("")` and `encrypt(None)` → return `""` (no-op for empty/null keys).
- `decrypt("")` → return `""` (no-op).
- The `.key_cache` fallback file is gitignored.

**Commit:** `feat(core): security — Fernet API key encryption`

---

### Step 2 — `orchestrator.py`

The job lifecycle manager. Lives at project root (not inside `core/`) because it
imports from both `core/` and `plugins/` — it is the coordinator between them.

**State the orchestrator owns:**
```python
_current_job: Job | None        # only one job runs at a time
_current_task: asyncio.Task | None  # the running asyncio task (for cancellation)
```

**Interface:**

```python
class Orchestrator:

    async def start_job(self, project_path: Path, settings: Settings) -> Job:
        """
        Start a new audit job.
        Raises ConflictError if a job is already running (→ HTTP 409).
        Creates a Job, sets state="running", publishes STATUS event, launches task.
        Returns the Job immediately (task runs in background).
        """

    async def cancel_job(self) -> None:
        """
        Cancel the running job.
        Cancels the asyncio task, sets state="cancelled", publishes STATUS event.
        No-op if no job is running.
        """

    def current_job(self) -> Job | None:
        """Return the current job (running or last completed)."""

    def status(self) -> dict:
        """Return {"state": str, "job_id": str | None} for GET /api/status."""

    async def _run_job(self, job: Job, settings: Settings) -> None:
        """
        Internal coroutine run as a task.
        Phase 2: no real scanners — emits synthetic progress events to prove
        the pipeline works end-to-end (see Stub Behaviour below).
        Phase 3: replaced with real scanner dispatch.
        Sets state="completed" or "failed" when done.
        Writes results atomically via core.atomic.write_json.
        """

class ConflictError(Exception): ...
```

**Stub Behaviour for Phase 2** (so SSE and the dashboard can be tested before Phase 3):

`_run_job` simulates a scan over 3 stages with `asyncio.sleep` delays:
```
Stage 1 (1s): publish_log "Starting audit..." then publish_progress("stub", 0, "")
Stage 2 (2s): publish_progress("stub", 50, "app.py") + publish_finding (one fake Finding)
Stage 3 (1s): publish_progress("stub", 100, "") then publish_status("completed", job.id)
```

This lets the entire SSE stream be exercised in tests without real scanners.

**Output files written on completion:**
- `audit_data_complete.json` — the full `Job` serialised via `core.atomic.write_json`
- `audit_history/{timestamp}.json` — copy of the same data

**Commit:** `feat: orchestrator — job lifecycle with stub scan`

---

### Step 3 — `api/middleware.py`

Two pieces of middleware registered on the aiohttp app.

**CORS middleware:**
```python
async def cors_middleware(app, handler):
    """
    Allows requests only from http://localhost:{port} and http://127.0.0.1:{port}.
    All other Origins receive 403.
    Adds Access-Control-Allow-Origin header to responses.
    Handles OPTIONS preflight.
    """
```

**JSON error middleware:**
```python
async def error_middleware(app, handler):
    """
    Catches all unhandled exceptions and returns JSON:
    {"error": "error_type", "message": "...", "detail": "..."}
    HTTP 500 for unexpected errors.
    HTTP 400, 404, 409 for known error classes (SettingsValidationError,
    FileNotFoundError, ConflictError).
    Never leaks tracebacks to the client.
    """
```

**Rules:**
- Both are pure middleware functions, no class needed.
- The server binds to `127.0.0.1` only — the CORS middleware is a second layer of
  defence, not the primary one.

**Commit:** `feat(api): middleware — CORS and JSON error handling`

---

### Step 4 — `api/server.py`

The aiohttp app factory. Wires everything together.

**Interface:**

```python
def create_app(
    orchestrator: Orchestrator,
    settings_path: Path = Path("settings.json"),
    port: int = 8421,
) -> web.Application:
    """
    Create and return the configured aiohttp Application.
    Registers all routes and middleware.
    Does NOT start the server — caller does that.
    """
```

**Route registration:**
```
GET  /api/status           → routes_data.get_status
GET  /api/data             → routes_data.get_data
GET  /api/history          → routes_data.get_history
GET  /api/history/{id}     → routes_data.get_history_item
GET  /api/settings         → routes_settings.get_settings
POST /api/settings         → routes_settings.post_settings
POST /api/run              → routes_run.post_run
POST /api/cancel           → routes_run.post_cancel
GET  /api/stream           → routes_stream.get_stream
GET  /                     → serve frontend/index.html (placeholder in Phase 2)
GET  /{tail:.*}            → serve static files from frontend/ (placeholder)
```

**Rules:**
- The app factory accepts `orchestrator` as a parameter — never constructs it
  internally. This makes testing easy (pass a mock or real instance).
- Port 8421 matches the old tool's port — consistency for users already familiar with it.
- The static file serving routes return a simple "Frontend coming in Phase 4"
  plain-text response for now. They must not 404.

**Commit:** `feat(api): server factory — app wiring and route registration`

---

### Step 5 — `api/routes_data.py`

Read-only data endpoints.

**`GET /api/status`**
```json
{"state": "idle", "job_id": null}
{"state": "running", "job_id": "abc-123"}
{"state": "completed", "job_id": "abc-123"}
```
Source: `orchestrator.status()`. Always HTTP 200.

**`GET /api/data`**
Returns the contents of `audit_data_complete.json` if it exists.
Returns `{"findings": [], "job": null}` if no audit has run yet.
HTTP 200 always.

**`GET /api/history`**
Lists all files in `audit_history/`, sorted newest-first.
Returns array of `{"id": "timestamp", "timestamp": "...", "finding_count": N}`.
Returns `[]` if directory is empty or does not exist. HTTP 200 always.

**`GET /api/history/{id}`**
Reads `audit_history/{id}.json`.
HTTP 200 with full content, or HTTP 404 with JSON error if not found.

**Rules:**
- All reads via `core.atomic.read_json` — never raw `open()`.
- `finding_count` in the history list is derived from the stored JSON without
  loading the full object — read `data["scan_results"]` and sum findings.

**Commit:** `feat(api): routes_data — status, data, history endpoints`

---

### Step 6 — `api/routes_settings.py`

Settings read and write.

**`GET /api/settings`**
Loads current settings via `core.settings.load()`.
Redacts `api_key`: if set, returns `"***"` instead of the real value.
HTTP 200.

**`POST /api/settings`**
Accepts full settings JSON body.
If `api_key` is `"***"` in the body → preserve the existing encrypted key (don't overwrite).
If `api_key` is a real value → encrypt via `core.security.encrypt()` before saving.
Validates against schema via `core.settings.load()` logic.
Returns `{"ok": true}` on success, HTTP 400 + JSON error on validation failure.

**Rules:**
- The `"***"` sentinel means "unchanged" — never store literal `"***"` as the key.
- Settings are saved atomically via `core.atomic.write_json`.
- After a successful POST, the orchestrator's settings reference is updated so the
  next `POST /api/run` uses the new settings.

**Commit:** `feat(api): routes_settings — GET/POST settings with key redaction`

---

### Step 7 — `api/routes_run.py`

Job control.

**`POST /api/run`**
Calls `orchestrator.start_job(project_path, settings)`.
Returns `{"job_id": "abc-123"}` HTTP 202 on success.
Returns HTTP 409 + JSON error if a job is already running (`ConflictError`).
Returns HTTP 400 if `project_path` in settings does not exist.

**`POST /api/cancel`**
Calls `orchestrator.cancel_job()`.
Returns `{"ok": true}` HTTP 200 always (no-op if nothing running).

**Rules:**
- `POST /api/run` is non-blocking — it starts the background task and returns
  immediately. The client watches progress via SSE.
- HTTP 202 (Accepted) not 200, because the job is started but not complete.

**Commit:** `feat(api): routes_run — POST /api/run and /api/cancel`

---

### Step 8 — `api/routes_stream.py`

The SSE endpoint — the most critical piece of Phase 2.

**`GET /api/stream`**

Connection lifecycle:
```
1. Client connects
2. Server reads Last-Event-ID header (integer index into ring buffer, default 0)
3. Server replays bus.history(since_index) — sends all buffered events to catch up
4. Server subscribes to ALL EventTypes on the bus
5. Server enters a loop: wait for new events → send as SSE
6. On client disconnect: unsubscribe from bus, close response
```

**SSE wire format:**
```
id: {sequential_integer}
event: {event.type.value}
data: {json.dumps(event.payload)}

```
(blank line terminates each event — standard SSE protocol)

**Event-to-SSE mapping:**
```
EventType.STATUS   → event: status
EventType.PROGRESS → event: progress
EventType.LOG      → event: log
EventType.FINDING  → event: finding
```

**Heartbeat:** send a comment line (`: heartbeat`) every 15 seconds to prevent
proxy timeouts. Uses `asyncio.wait_for` with a timeout on the event queue.

**Rules:**
- Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
  `X-Accel-Buffering: no` (prevents nginx buffering).
- The SSE route uses an `asyncio.Queue` per connection — the bus callback puts
  events into the queue, the send loop drains it. This decouples event publishing
  speed from client send speed.
- Multiple simultaneous SSE clients are supported (each gets its own queue).
- On `asyncio.CancelledError` (client disconnect): unsubscribe cleanly, do not log
  as an error.

**Commit:** `feat(api): routes_stream — SSE endpoint with replay and heartbeat`

---

### Step 9 — `server.py` (entry point) + update `core/__main__.py`

**`server.py`** at project root:

```python
"""
Nexus Audit V3 — server entry point.
Usage: python server.py [--port 8421] [--settings path/to/settings.json]
"""
import argparse
import asyncio
from pathlib import Path

from aiohttp import web
from api.server import create_app
from orchestrator import Orchestrator
from core.settings import load as load_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8421)
    parser.add_argument("--settings", type=Path, default=Path("settings.json"))
    args = parser.parse_args()

    settings = load_settings(args.settings)
    orc = Orchestrator()
    app = create_app(orc, settings_path=args.settings, port=args.port)

    web.run_app(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
```

**Update `core/__main__.py`** to delegate to `server.main()`:
```python
from server import main
main()
```

**Update `pyproject.toml`** entry point:
```
nexus-audit = "server:main"
```

**Commit:** `feat: server entry point — wires app and starts on 127.0.0.1:8421`

---

### Step 10 — Tests

One file per new module. All use `aiohttp.test_utils.TestClient` for API tests.

**`test_security.py`**
- `encrypt` → `decrypt` round-trip returns original string
- `encrypt("")` returns `""`
- `decrypt("")` returns `""`
- Corrupt ciphertext raises `InvalidToken`
- Two calls to `encrypt(same_string)` produce different ciphertext (Fernet is non-deterministic)

**`test_api_data.py`**
- `GET /api/status` returns `{"state": "idle", "job_id": null}` before any job
- `GET /api/data` returns `{"findings": [], "job": null}` before any job
- `GET /api/history` returns `[]` before any job
- `GET /api/history/nonexistent` returns HTTP 404

**`test_api_settings.py`**
- `GET /api/settings` returns defaults when no settings file
- `POST /api/settings` with valid body returns `{"ok": true}`
- `POST /api/settings` with invalid body returns HTTP 400
- `POST /api/settings` with `api_key: "***"` does not overwrite existing key
- `GET /api/settings` after saving a real key returns `"***"` not the key

**`test_api_run.py`**
- `POST /api/run` with valid project_path returns HTTP 202 + `job_id`
- `POST /api/run` again while running returns HTTP 409
- `POST /api/cancel` returns `{"ok": true}` whether or not a job is running
- After cancel, `GET /api/status` returns `state: "cancelled"`

**`test_api_stream.py`**
- Client connects, receives replayed history events
- Client receives new events published after connect
- Heartbeat comment is sent within the timeout window
- Client disconnect causes clean unsubscribe (no leaked tasks)

**Rules:**
- All API tests use `tmp_path` for `audit_history/` and settings files.
- SSE tests use `asyncio.timeout` to avoid hanging if events never arrive.
- No real scanner invocations — the stub orchestrator behaviour is enough.

**Commit:** `test: Phase 2 test suite — API server, security, SSE`

---

### Step 11 — Final commit and tag

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q        # must exit 0
mypy core/ plugins/ api/ orchestrator.py server.py --strict
ruff check .
git add -A
git commit -m "feat: Phase 2 complete — API server"
git tag v0.2.0
```

---

## What Phase 2 Does NOT Include

| Excluded | Reason |
|----------|--------|
| Real scanner execution | Phase 3 |
| Frontend HTML/CSS/JS | Phase 4 |
| AI calls | Phase 7 |
| Run history diffing | Phase 6 |
| WebSocket | Not needed — SSE is sufficient and simpler |
| External network binding | Security requirement — 127.0.0.1 only, always |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| aiohttp over FastAPI | Lighter dependency, native SSE support, no magic |
| One job at a time | Simplicity; audit tools don't need parallelism at the job level |
| HTTP 202 for `/api/run` | Correct semantics — job accepted but not finished |
| `"***"` sentinel for API key | Standard pattern; avoids re-encrypting unchanged keys |
| Per-connection asyncio.Queue for SSE | Decouples publish speed from send speed; supports multiple clients |
| Port 8421 | Matches V2 — users don't need to update bookmarks |
| Stub scan in orchestrator | Proves the full pipeline (run → SSE → status) works before Phase 3 adds real scanners |

---

## Definition of Done — Phase 2

- [ ] `python server.py` starts without error and listens on `127.0.0.1:8421`
- [ ] `curl http://localhost:8421/api/status` returns `{"state":"idle","job_id":null}`
- [ ] `curl -X POST http://localhost:8421/api/run` starts the stub scan and returns `job_id`
- [ ] `curl http://localhost:8421/api/stream` receives SSE events including progress and status
- [ ] `curl -X POST http://localhost:8421/api/run` while running returns HTTP 409
- [ ] `curl -X POST http://localhost:8421/api/cancel` cancels cleanly
- [ ] `GET /api/settings` redacts `api_key` as `"***"`
- [ ] `mypy ... --strict` exits 0
- [ ] `pytest --tb=short -q` exits 0 (all Phase 1 + Phase 2 tests)
- [ ] `ruff check .` exits 0
- [ ] `git tag v0.2.0` exists
- [ ] No file imports from `frontend/` (it doesn't exist yet)
- [ ] Binding check: server refuses to start if port is already in use (clear error message)

---

*Plan written: 2026-05-28 | Follows: Phase 1.2 (`v0.1.2`) | Precedes: Phase 3 (Scanner Plugins)*
