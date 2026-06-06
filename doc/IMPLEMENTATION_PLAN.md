# Nexus Audit V3 Implementation Plan

This plan describes the missing work in the current repository and the concrete implementation steps taken to complete the feature set defined by `doc/TECHNICAL_SPEC.md`.

## Goals

1. Ensure backend lifecycle events are fully implemented for audit run and cancellation.
2. Provide a working settings API that returns persisted application settings.
3. Make the front-end views for named routes visible and navigable.
4. Add verification coverage for the new lifecycle behavior.
5. Document the work and confirm completion.

## Steps

### Backend fixes

1. Update `orchestrator.py`:
   - Publish `status: running` immediately when a new job starts.
   - Add `cancel_run()` support to cancel the current task.
   - Handle `asyncio.CancelledError` in `_run_job()` and publish `status: cancelled`.

2. Update `api/routes_run.py`:
   - Wire `/api/cancel` to call `Orchestrator.cancel_run()`.
   - Return the cancelled job id and HTTP 202 on success.
   - Return 409 if no job is running.

3. Update `api/routes_settings.py`:
   - Return serialized settings from `SettingsManager` on `GET /api/settings`.
   - Accept settings updates on `POST /api/settings` and persist them.

### Frontend fixes

1. Update `frontend/js/main.js`:
   - Import and initialize placeholder view content for every named route.
   - Preserve the existing dashboard view.

2. Add `frontend/js/views/placeholder.js`:
   - Render a minimal explanatory panel for each unmatched route.
   - Make tabs and settings navigation immediately visible.

### Tests and verification

1. Add orchestrator coverage in `tests/test_orchestrator.py`:
   - Verify that starting a run publishes a `running` status event.
   - Verify that canceling a run publishes a `cancelled` status event and updates state.

2. Run existing Python tests.
3. Run JavaScript syntax validation on frontend modules.

## Notes

- `aiohttp` is not currently available in the environment, so full runtime backend startup cannot be verified here via local server execution.
- The changes are designed to make the existing application layers consistent with the spec and to fix the core broken button/state interaction.
