# Nexus Audit V3 Implementation Review

This review checks the current repository against the documented implementation plan in `doc/TECHNICAL_SPEC.md`.

## Summary

- Backend base architecture is mostly present.
- Frontend wiring is present for the main shell, but multiple intended view modules are missing.
- The most important runtime bug is that the orchestrator does not publish a `running` status event at job start, and cancel is not implemented.
- The backend startup environment in this workspace currently fails because `aiohttp` is not installed.

---

## Step-by-step verification

### 1. `core/models.py`
Status: ✅ Implemented

- `Finding`, `ScanResult`, `Job`, and `Settings` dataclasses are defined.
- `finding_to_dict()` exists and returns clean primitive values for enum fields.

Notes:
- Implementation matches the plan for canonical serialization.

### 2. `core/events.py`
Status: ✅ Implemented

- `EventBus` maintains `_event_counter` and `_history`.
- `publish()` increments the counter and stores events in history.
- `subscribe_all()` exists and receives `(event_id, event)`.

Notes:
- This matches the plan’s SSE history model.
- The bus supports type-specific and all-subscriber callbacks.

### 3. `core/atomic.py`
Status: ✅ Implemented

- `write_json()` writes via temporary file then renames.
- `read_json()` returns `None` if file is missing.

Notes:
- Implementation follows the safe atomic pattern.

### 4. `core/settings.py`
Status: ✅ Implemented with a caution

- `SettingsManager.load()` and `save()` exist.
- Default settings are created when `settings.json` is missing.

Caution:
- Default project path is `Path.cwd()`, which depends on the working directory when the server starts.
- If the server is launched from the wrong folder, settings may point to an unintended path.

### 5. `orchestrator.py`
Status: ⚠️ Partially correct

- `Orchestrator` exists and owns a single current job.
- `start_run()` creates a `Job` and launches `_run_job()` as an asyncio task.
- `run()` publishes fake progress and log events.
- Error handling is present for job failures.

Defects:
- No `EventType.STATUS` publish when the job starts. The job is set to `running`, but the front end will not see the transition until completion or failure.
- The stub implementation uses fake progress rather than real scanner dispatch, which is acceptable for a stub, but incomplete relative to full planner expectations.

### 6. `api/server.py`
Status: ✅ Implemented

- API routes are registered before static assets.
- `/api/status`, `/api/data`, `/api/run`, `/api/cancel`, `/api/settings`, `/api/stream` are all wired.
- Static assets are served under `/static/css`, `/static/js`, `/static/assets`.
- SPA fallback is registered last.

Notes:
- Route order follows the spec.

### 7. `plugins/` and scanner integration
Status: ⚠️ Not integrated

- The repository has `plugins/__init__.py`, `plugins/base.py`, and `plugins/quality/vulture_plugin.py`.
- The orchestrator currently does not use plugins or scanner dispatch.
- There is no evidence the plugin layer is actually invoked by `Orchestrator.run()`.

Notes:
- Step 7 of the plan is not implemented in the current orchestrator stub.

### 8. `core/dna_builder.py`, `core/rules_engine.py`, `core/scoring_engine.py`
Status: Not fully audited in this review

- These files exist in the repository under `core/`.
- This review did not validate their internal content or integration because the plan step was primarily about backend layering order rather than exact logic.

---

## Frontend architecture review

### File structure
Status: ⚠️ Partially implemented

- Expected frontend layout exists: `frontend/index.html`, `frontend/css/`, `frontend/js/`, `frontend/js/views/`.
- Only one view module exists: `frontend/js/views/dashboard.js`.
- The plan implies multiple view modules should exist; these are not present.

### `store.js`
Status: ✅ Implemented

- Proxy-based reactive state is implemented.
- `set()`, `get()`, `subscribe()` are present.
- Convenience setters and derived list filtering are implemented.

### `stream.js`
Status: ✅ Implemented

- `openStream()` is the only EventSource call.
- SSE event handlers update the store correctly.
- Error logging is present.

### `main.js`
Status: ✅ Implemented

- Only wires router, theme, run/cancel buttons, settings button, and store subscriptions.
- Loads initial data from `/api/status`, `/api/data`, and `/api/settings`.
- Starts SSE stream.

Notes:
- A startup failure in module load would prevent all buttons from working, but the code itself wires the buttons correctly.

### `router.js`
Status: ✅ Implemented

- Hash-based navigation works through `navigate()`.
- View divs are shown/hidden by id.
- Tab button active state updates correctly.

### Views
Status: ⚠️ Incomplete

- `dashboard.js` exists and renders dashboard content from the store.
- No other view modules exist for `issues`, `violations`, `security`, `dependencies`, `recommendations`, `graph`, `trends`, `coupling`, `manifest`, `config-health`, or `settings`.
- Clicking tabs likely toggles button active state but does not render content for those views.

## Specific logical errors found

1. **No status event on job start**
   - `Orchestrator.start_run()` does not publish `EventType.STATUS` with `state: running`.
   - The UI relies on SSE status updates to switch buttons and badge state.

2. **Cancel is a stub**
   - `api/routes_run.cancel_run()` returns success without cancelling the running job.
   - This violates the plan’s lifecycle control contract.

3. **Potential settings path issue**
   - `SettingsManager.load()` uses `Path.cwd()` for the default project path.
   - This is fragile if the server is launched from a directory other than the repo root.

4. **Frontend views are incomplete**
   - Only `dashboard` view is implemented.
   - The UI shell includes many route targets, but no code renders them.
   - This can make many buttons feel nonfunctional.

5. **Plugin layer exists but is unused**
   - The orchestrator stub does not exercise the real plugin contract.
   - If `plugins/quality/vulture_plugin.py` exists, it is not wired into the audit run path.

## Recommended priority fixes

1. Publish `running` status immediately when `Orchestrator.start_run()` is called.
2. Implement cancellation in `api/routes_run.cancel_run()` and the orchestrator.
3. Add a minimal `settings`/`issues`/`violations` view or a placeholder renderer for every named view so tab buttons are visibly functional.
4. Consider using an absolute repo-root-based default path in `core/settings.py` instead of `Path.cwd()`.
5. Wire plugin execution into `Orchestrator.run()` before relying on actual scanner behavior.

---

## Conclusion

The implementation is structurally close to the plan, but there are key incomplete areas:

- runtime state transition events for job start are missing,
- cancel behavior is not implemented,
- frontend views beyond dashboard are incomplete,
- plugin/scanner integration is not present.

These defects explain why the app feels nonfunctional even when buttons appear wired.
