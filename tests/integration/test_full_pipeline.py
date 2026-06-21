"""
Full pipeline integration test for Nexus Audit V3.

Runs a real end-to-end audit against the project itself
(nexus_audit_v3 as the scan target).  Every test shares the
audit output produced by the first run; sequential and
cancellation tests use fresh Orchestrator instances.

Log streaming: all EventBus LOG events are forwarded to both
Python's root logger (captured by pytest's live-logging
facility) *and* to the project-root integration log file at
  <project>/integration_pipeline.log
so the sequence can be reviewed offline.

Usage:
    pytest tests/integration/test_full_pipeline.py -v \\
           --log-cli-level=INFO --tb=short
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from core.primitives.events import EventBus, EventType
from core.primitives.models import JobState
from core.primitives.settings import SettingsManager
from orchestrator import Orchestrator

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_PATH = Path("/home/yusupha/my_tools/nexus_audit_v3")
LOG_FILE = PROJECT_PATH / "integration_pipeline.log"

# Scanners confirmed installed in the venv (bandit, vulture, ruff, mypy, pylint, lizard)
ENABLED_SCANNERS = {
    "bandit": True,
    "vulture": True,
    "ruff": True,
    "mypy": True,
    "pylint": True,
    "lizard": True,
    # All others disabled to keep run time reasonable
    "semgrep": False,
    "safety": False,
    "trufflehog": False,
    "djlint": False,
    "eslint": False,
    "radon": False,
    "license_audit": False,
}

REQUIRED_SCHEMA_KEYS = {
    "metadata", "findings", "apps", "fleet_average",
    "coupling_matrix", "dna", "config_health",
    "dependency_scan", "recommendations", "change_summary",
    "rules_summary", "fix_queue", "timeline", "git_context",
}

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
VALID_CATEGORIES = {"SECURITY", "QUALITY", "PERFORMANCE", "DEPENDENCY", "ARCHITECTURE"}

# ──────────────────────────────────────────────────────────────────────────────
# Logging bootstrap — project-root log file + pytest live capture
# ──────────────────────────────────────────────────────────────────────────────

def _configure_file_logging() -> logging.Logger:
    """
    Returns a dedicated integration logger that writes to
    integration_pipeline.log at the project root.  The file is
    opened in *append* mode so multiple test runs accumulate.
    """
    integration_logger = logging.getLogger("nexus.integration")
    integration_logger.setLevel(logging.DEBUG)

    if not any(isinstance(h, logging.FileHandler) for h in integration_logger.handlers):
        fh = logging.FileHandler(str(LOG_FILE), mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        integration_logger.addHandler(fh)

    return integration_logger


log = _configure_file_logging()


def _log(msg: str, level: str = "info") -> None:
    """Write to both the file logger and Python's root logger (pytest captures both)."""
    getattr(log, level)(msg)
    getattr(logging.getLogger(), level)(msg)


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _attach_event_streaming(bus: EventBus) -> None:
    """Subscribe to ALL bus events and stream them to the log file."""

    async def _on_event(event_id: int, event) -> None:
        payload_str = json.dumps(event.payload, default=str)
        _log(
            f"[BUS#{event_id:05d}] {event.type.value.upper():8s} | {payload_str}",
            level="debug",
        )

    await bus.subscribe_all(_on_event)


async def _run_audit_and_wait(
    orch: Orchestrator,
    project_id: str,
    timeout_seconds: float = 600.0,
) -> tuple:
    """
    Start a job and block until a STATUS(completed|failed|cancelled) event
    arrives.  Returns (job, result_data_path, duration_seconds).
    """
    done_event = asyncio.Event()
    final_state: dict = {}

    async def on_status(event) -> None:
        state = event.payload.get("state", "")
        _log(f"[STATUS] {state}")
        if state in ("completed", "failed", "cancelled"):
            final_state["state"] = state
            done_event.set()

    await orch.bus.subscribe(EventType.STATUS, on_status)

    t0 = time.monotonic()
    job = await orch.start_job(project_id)
    _log(f"[JOB STARTED] job_id={job.id}  project_id={project_id}")

    try:
        await asyncio.wait_for(done_event.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        _log("[TIMEOUT] audit did not complete within the allowed window", level="error")
        raise RuntimeError(
            f"Audit timed out after {timeout_seconds}s  job_id={job.id}"
        )

    duration = time.monotonic() - t0
    _log(
        f"[JOB DONE] job_id={job.id}  state={job.state.value}  "
        f"duration={duration:.1f}s"
    )

    output_dir = (
        Path.home()
        / ".nexus_audit"
        / "projects"
        / project_id
        / "jobs"
        / job.id
    )
    return job, output_dir, duration


async def _build_orchestrator(sm: SettingsManager, project_id: str) -> Orchestrator:
    """Create a fresh Orchestrator with event streaming attached."""
    orch = Orchestrator(sm)
    await _attach_event_streaming(orch.bus)
    return orch


# ──────────────────────────────────────────────────────────────────────────────
# Session-scoped fixture — register the project ONCE and run the first audit
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Override pytest-asyncio's default loop to be session-scoped."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def session_sm():
    """One SettingsManager instance shared across the whole session."""
    return SettingsManager()


@pytest.fixture(scope="session")
def registered_project_id(session_sm, event_loop):
    """
    Register nexus_audit_v3 as a project and return its project_id.
    Uses the session event_loop so no nested loops.
    """
    _log("=" * 72)
    _log(f"INTEGRATION RUN  started_at={datetime.now(timezone.utc).isoformat()}")
    _log(f"  target : {PROJECT_PATH}")
    _log(f"  log    : {LOG_FILE}")
    _log("=" * 72)

    project = event_loop.run_until_complete(
        session_sm.register_project("nexus_audit_v3_integration", str(PROJECT_PATH))
    )
    _log(f"[REGISTER] project_id={project.id}")

    # Patch scanner config
    project.settings.scanners = ENABLED_SCANNERS
    project.settings.force_rescan = True
    project.settings.pipeline_config.cache_scan_results = False  # skip source sync in integration test
    session_sm._project_cache[project.id] = project

    # Persist updated settings
    event_loop.run_until_complete(session_sm.save_project(project))
    return project.id


@pytest.fixture(scope="session")
def first_audit(session_sm, registered_project_id, event_loop):
    """
    Run the first full audit and return (job, output_dir, duration, result_data).
    """
    orch = event_loop.run_until_complete(
        _build_orchestrator(session_sm, registered_project_id)
    )
    job, output_dir, duration = event_loop.run_until_complete(
        _run_audit_and_wait(orch, registered_project_id)
    )

    _log(f"[FIRST AUDIT COMPLETE]  duration={duration:.1f}s  findings={job}")

    result_data: Optional[dict] = None
    data_file = output_dir / "audit_data_complete.json"
    if data_file.exists():
        result_data = json.loads(data_file.read_text(encoding="utf-8"))

    return job, output_dir, duration, result_data


# ──────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ──────────────────────────────────────────────────────────────────────────────


class TestFullPipeline:

    # ── 1. Pipeline completes ─────────────────────────────────────────────────

    def test_pipeline_completes(self, first_audit):
        job, output_dir, duration, result_data = first_audit

        _log(f"[TC1] test_pipeline_completes  state={job.state}  duration={duration:.1f}s")

        assert job.state == JobState.COMPLETED, (
            f"Expected COMPLETED, got {job.state}.  "
            f"Error: {getattr(job, 'error', None)}"
        )

        data_file = output_dir / "audit_data_complete.json"
        summary_file = output_dir / "audit_summary.json"

        assert data_file.exists(), f"audit_data_complete.json missing at {output_dir}"
        assert summary_file.exists(), f"audit_summary.json missing at {output_dir}"

        _log(f"[TC1] PASS  files_exist=True  duration={duration:.1f}s")

    # ── 2. Output schema valid ────────────────────────────────────────────────

    def test_output_schema_valid(self, first_audit):
        _, output_dir, _, result_data = first_audit

        assert result_data is not None, "result_data is None — audit likely failed"

        missing = REQUIRED_SCHEMA_KEYS - set(result_data.keys())
        assert not missing, f"Schema missing keys: {missing}"

        _log(f"[TC2] PASS  schema_keys_present={sorted(REQUIRED_SCHEMA_KEYS)}")

    # ── 3. Findings present and well-formed ───────────────────────────────────

    def test_findings_present_and_well_formed(self, first_audit):
        _, _, _, result_data = first_audit

        findings = result_data.get("findings", [])
        _log(f"[TC3] findings_count={len(findings)}")

        assert len(findings) > 0, (
            "No findings produced — at least one enabled scanner "
            "(bandit/vulture/ruff) should find something in the project itself"
        )

        for i, f in enumerate(findings):
            assert isinstance(f.get("id"), str) and f["id"], (
                f"Finding[{i}] 'id' is empty or missing"
            )
            assert isinstance(f.get("fingerprint"), str) and f["fingerprint"] is not None, (
                f"Finding[{i}] 'fingerprint' is missing.  id={f.get('id')}"
            )
            assert f.get("severity") in VALID_SEVERITIES, (
                f"Finding[{i}] invalid severity={f.get('severity')}  id={f.get('id')}"
            )
            assert f.get("category") in VALID_CATEGORIES, (
                f"Finding[{i}] invalid category={f.get('category')}  id={f.get('id')}"
            )

        _log(f"[TC3] PASS  all {len(findings)} findings are well-formed")

    # ── 4. Health scores calculated ───────────────────────────────────────────

    def test_health_scores_calculated(self, first_audit):
        _, _, _, result_data = first_audit

        apps = result_data.get("apps", {})
        fleet_average = result_data.get("fleet_average", -1)

        _log(f"[TC4] apps_count={len(apps)}  fleet_average={fleet_average}")

        assert len(apps) >= 1, "No apps scored — expected at least one app entry"

        for app_name, app_data in apps.items():
            score = app_data.get("score", -1)
            assert 0 <= score <= 100, (
                f"App '{app_name}' score={score} is out of [0, 100]"
            )

        assert 0 <= fleet_average <= 100, (
            f"fleet_average={fleet_average} is out of [0, 100]"
        )

        _log(f"[TC4] PASS  apps={list(apps.keys())}  fleet_average={fleet_average}")

    # ── 5. Coupling matrix built ──────────────────────────────────────────────

    def test_coupling_matrix_built(self, first_audit):
        _, _, _, result_data = first_audit

        coupling = result_data.get("coupling_matrix", {})
        apps = result_data.get("apps", {})

        _log(f"[TC5] coupling_apps={coupling.get('apps')}  matrix_shape=?")

        assert "apps" in coupling, "coupling_matrix missing 'apps' key"
        assert "matrix" in coupling, "coupling_matrix missing 'matrix' key"

        coupling_apps = coupling["apps"]
        assert len(coupling_apps) >= 1, "coupling_matrix.apps is empty"

        matrix = coupling["matrix"]
        assert isinstance(matrix, list), "coupling_matrix.matrix is not a list"
        for row in matrix:
            assert isinstance(row, list), "Each row in coupling_matrix.matrix must be a list"
            assert len(row) == len(coupling_apps), (
                f"Matrix row width {len(row)} != apps count {len(coupling_apps)}"
            )

        _log(
            f"[TC5] PASS  apps={coupling_apps}  "
            f"matrix_dim={len(coupling_apps)}x{len(coupling_apps)}"
        )

    # ── 6. Timeline data present ──────────────────────────────────────────────

    def test_timeline_data_present(self, first_audit):
        _, _, _, result_data = first_audit

        timeline = result_data.get("timeline", {})
        _log(f"[TC6] timeline_keys={list(timeline.keys())}")

        assert "labels" in timeline, "timeline missing 'labels' key"
        assert "fleet_avg" in timeline, "timeline missing 'fleet_avg' key"

        _log(f"[TC6] PASS")

    # ── 7. Fix queue synced ───────────────────────────────────────────────────

    def test_fix_queue_synced(self, first_audit):
        _, _, _, result_data = first_audit

        fix_queue = result_data.get("fix_queue", {})
        _log(f"[TC7] fix_queue_keys={list(fix_queue.keys())}")

        assert "reappeared" in fix_queue, "fix_queue missing 'reappeared' key"
        assert "new_count" in fix_queue, "fix_queue missing 'new_count' key"

        _log(f"[TC7] PASS  new_count={fix_queue.get('new_count')}")

    # ── 8. Git context extracted ──────────────────────────────────────────────

    def test_git_context_extracted(self, first_audit):
        _, _, _, result_data = first_audit

        git_context = result_data.get("git_context", {})
        _log(f"[TC8] git_context={git_context}")

        assert "branch" in git_context, "git_context missing 'branch' key"

        # nexus_audit_v3 IS a git repo — branch and commit must be non-None
        assert git_context.get("branch") is not None, (
            "git_context.branch is None — project should be inside a git repo"
        )

        _log(f"[TC8] PASS  branch={git_context.get('branch')}")

    # ── 9. Two sequential audits ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_two_sequential_audits(self, session_sm, registered_project_id):
        _log("[TC9] Starting second sequential audit...")

        orch2 = await _build_orchestrator(session_sm, registered_project_id)
        job2, output_dir2, duration2 = await _run_audit_and_wait(
            orch2, registered_project_id
        )

        assert job2.state == JobState.COMPLETED, (
            f"Second audit ended in state={job2.state}"
        )

        data_file2 = output_dir2 / "audit_data_complete.json"
        assert data_file2.exists(), (
            f"audit_data_complete.json not found for second audit at {output_dir2}"
        )

        result2 = json.loads(data_file2.read_text(encoding="utf-8"))
        missing2 = REQUIRED_SCHEMA_KEYS - set(result2.keys())
        assert not missing2, (
            f"Second audit output is missing schema keys: {missing2}"
        )

        _log(
            f"[TC9] PASS  job2_id={job2.id}  "
            f"duration={duration2:.1f}s"
        )

    # ── 10. Cancellation works ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cancellation_works(self, session_sm, registered_project_id):
        _log("[TC10] Testing cancellation...")

        orch3 = await _build_orchestrator(session_sm, registered_project_id)

        done_event = asyncio.Event()
        final_state: dict = {}

        async def on_status(event) -> None:
            state = event.payload.get("state", "")
            _log(f"[TC10][STATUS] {state}")
            if state in ("completed", "failed", "cancelled"):
                final_state["state"] = state
                done_event.set()

        await orch3.bus.subscribe(EventType.STATUS, on_status)

        job3 = await orch3.start_job(registered_project_id)
        _log(f"[TC10] job started  job_id={job3.id}  — cancelling immediately")

        # yield one event-loop tick so the coroutine starts, then cancel
        await asyncio.sleep(0.05)
        await orch3.cancel_job()

        # Wait a moment for the cancellation event to propagate
        try:
            await asyncio.wait_for(done_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass  # The task may have been cancelled before publishing STATUS

        assert job3.state == JobState.CANCELLED, (
            f"Expected CANCELLED after cancel_job(), got {job3.state}"
        )

        # audit_data_complete.json must NOT exist for the cancelled job
        output_dir3 = (
            Path.home()
            / ".nexus_audit"
            / "projects"
            / registered_project_id
            / "jobs"
            / job3.id
        )
        data_file3 = output_dir3 / "audit_data_complete.json"
        assert not data_file3.exists(), (
            "audit_data_complete.json was written for a cancelled job — "
            "incomplete output should not be persisted"
        )

        _log(f"[TC10] PASS  job3_id={job3.id}  state={job3.state.value}")
