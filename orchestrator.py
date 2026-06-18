import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Any, Dict

# Imports based on dependencies and 3-Layer Rule
from core.primitives.models import (
    Job, Finding, ScanResult, ScanStatus, JobState, 
    ProjectSettings, create_finding, to_dict
)
from core.primitives.events import EventBus, EventType
from core.primitives.atomic import write_json
from core.primitives.settings import SettingsManager
from core.infra.source_sync import sync, SyncConfig
from core.infra.fast_check import get_changed_files
from core.infra.git_context import get_git_context
from core.infra.audit_logger import AuditLogger
from core.infra.registry import PluginRegistry
from core.engines.dna_builder import build_dna
from core.engines.rules_engine import RulesEngine
from core.engines.scoring_engine import calculate_scores
from core.engines.coupling import build_coupling_matrix
from core.engines.timeline import load_score_history, compute_violation_persistence
from core.engines.fix_queue import FixQueue

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, settings_manager: SettingsManager):
        self._settings_manager = settings_manager
        self._bus = EventBus()
        self._current_job: Optional[Job] = None
        self._current_task: Optional[asyncio.Task] = None
        self._audit_logger: Optional[AuditLogger] = None

    @property
    def bus(self) -> EventBus:
        return self._bus

    async def start_job(self, project_id: str, fast_mode: bool = False) -> Job:
        if self._current_job and self._current_job.state == JobState.RUNNING:
            raise RuntimeError("A job is already running")
            
        project = self._settings_manager.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
            
        job = Job(
            id=str(uuid.uuid4()),
            project_id=project_id,
            project_path=project.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.RUNNING
        )
        
        self._current_job = job
        self._current_task = asyncio.create_task(self._run_job(job, project_id, fast_mode))
        return job

    async def cancel_job(self) -> None:
        if not self._current_task or self._current_task.done():
            return
            
        self._current_task.cancel()
        if self._current_job:
            self._current_job.state = JobState.CANCELLED
            self._current_job.finished_at = datetime.now(timezone.utc)
            await self._bus.publish_status("cancelled", self._current_job.id)
            
        if self._audit_logger:
            await self._audit_logger.stop()

    def current_job(self) -> Optional[Job]:
        return self._current_job

    def status(self) -> dict:
        job = self._current_job
        return {"state": job.state.value if job else "idle", "job_id": job.id if job else None}

    async def _run_job(self, job: Job, project_id: str, fast_mode: bool) -> None:
        try:
            project = self._settings_manager.get_project(project_id)
            if not project:
                raise ValueError(f"Project {project_id} not found in settings cache.")
            settings = project.settings
            working_path = Path(project.path)
            
            # PHASE 0: Source Sync + Start AuditLogger
            self._audit_logger = AuditLogger(
                job.id, self._bus, 
                Path.home() / ".nexus_audit" / "projects" / project_id / "jobs" / job.id
            )
            await self._audit_logger.start()
            await self._bus.publish_status("running", job.id)
            
            # Sync sync if enabled
            if settings.pipeline_config.cache_scan_results: # Assuming caching implies sync
                sync_config = SyncConfig(enabled=True, source_type="local", local_path=str(working_path), working_dir=str(working_path))
                working_path = await sync(sync_config, self._bus)

            # PHASE 1: Build DNA
            dna = await build_dna(working_path, self._bus)
            await self._bus.publish_log("info", f"DNA built: {len(dna.modules)} modules")

            # PHASE 1.5: Fast Check
            file_filter = None
            if fast_mode:
                file_filter = await get_changed_files(working_path)
                await self._bus.publish_log("info", f"Fast mode: {'N files' if file_filter else 'full scan'}")

            # PHASE 2: Load Rules
            rules_path = working_path / "audit_rules.yaml"
            if not rules_path.exists():
                rules_path = Path("default_rules.yaml")
            rules_engine = await RulesEngine.create(rules_path)

            # PHASE 3: Run Scanners
            registry = PluginRegistry()
            registry.load()
            scanner_tasks = []
            
            for name, enabled in settings.scanners.items():
                if not enabled: continue
                cls = registry.get(name)
                if cls is None: continue
                
                config = settings.scanner_configs.get(name, {})
                if file_filter: config["_file_filter"] = file_filter
                config["_force_rescan"] = settings.force_rescan
                
                scanner = registry.instantiate(name, config, self._bus)
                scanner_tasks.append((name, asyncio.create_task(scanner.scan(working_path, config, self._bus))))
            
            results = await asyncio.gather(*[t for _, t in scanner_tasks], return_exceptions=True)
            scanner_findings = []
            for (name, _), result in zip(scanner_tasks, results):
                if isinstance(result, Exception):
                    await self._bus.publish_log("error", f"Scanner '{name}' crashed: {result}")
                    job.scan_results.append(ScanResult(scanner=name, status=ScanStatus.FAILED, error=str(result)))
                else:
                    job.scan_results.append(ScanResult(scanner=name, status=ScanStatus.COMPLETED, findings=result))
                    scanner_findings.extend(result)

            # PHASE 4: Evaluate Rules
            rule_findings = await rules_engine.evaluate(dna, scanner_findings, self._bus)
            all_findings = scanner_findings + rule_findings

            # PHASE 5: Score Apps
            hub_apps = {app['name'] for app in rules_engine.app_definitions if app.get('hub')}
            app_scores, fleet_average = calculate_scores(dna, all_findings, hub_apps, rules_engine.scoring_config, self._bus)

            # PHASE 6: Coupling Matrix
            boundary_findings = [f for f in all_findings if f.category.value == "architecture"]
            coupling = build_coupling_matrix(dna, boundary_findings)

            # PHASE 7: Timeline
            history_dir = Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"
            all_findings = await compute_violation_persistence(history_dir, all_findings)
            trends = await load_score_history(history_dir)

            # PHASE 8: Fix Queue
            queue_path = working_path / ".nexus_fix_queue.json"
            fix_queue = FixQueue(queue_path)
            sync_result = await fix_queue.sync(all_findings)

            # PHASE 9: Git Context
            git_ctx = await get_git_context(working_path)

            # PHASE 10: AI Recommendations (STUB)
            recommendations = []

            # PHASE 11: Write Result
            output_dir = Path.home() / ".nexus_audit" / "projects" / project_id / "jobs" / job.id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            result_data = self._build_result(job, all_findings, app_scores, fleet_average, coupling, trends, sync_result, git_ctx, recommendations, rules_engine, dna)
            await write_json(output_dir / "audit_data_complete.json", result_data, indent=2)
            await write_json(output_dir / "audit_summary.json", self._build_summary(result_data), indent=2)
            
            # PHASE 12: Report Generation (STUB — NOT YET IMPLEMENTED)
            # Reports are NOT automatically generated on audit completion in the current version.
            # Users must explicitly call 'report:generate' to create reports.
            # This phase is reserved for future implementation of auto-generation.
            # See: docs/LAYER4_REPORTS_REFACTOR.md for the report engine design.
            await self._bus.publish_log("info", "Audit complete. Reports not auto-generated. Use 'report:generate' to create reports.")
            
            # PHASE 13: Complete
            job.state = JobState.COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            await self._bus.publish_status("completed", job.id)

        except Exception as e:
            job.state = JobState.FAILED
            job.error = str(e)
            job.finished_at = datetime.now(timezone.utc)
            await self._bus.publish_log("error", f"Audit failed: {e}")
            await self._bus.publish_status("failed", job.id)
        finally:
            if self._audit_logger:
                await self._audit_logger.stop()

    def _build_result(self, job, all_findings, app_scores, fleet_average, coupling, trends, sync_result, git_ctx, recommendations, rules_engine, dna) -> dict:
        from core.primitives.models import to_dict
        
        apps_dict = {}
        for app_name, app_score in app_scores.items():
            fc = app_score.finding_counts
            apps_dict[app_name] = {
                "score": app_score.score,
                "is_hub": app_score.is_hub,
                "finding_counts": fc,
                "finding_count": sum(fc.values()),
                "violation_count": fc.get("violation", 0),
                "security_high": fc.get("security_high", 0),
                "security_medium": fc.get("security_medium", 0),
                "security_low": fc.get("security_low", 0),
                "dead_code_count": fc.get("dead_code", 0),
                "ghost_file_count": fc.get("ghost_file", 0),
                "avg_complexity": fc.get("complexity", 0.0),
                "penalty_breakdown": app_score.penalty_breakdown
            }

        total_violations = sum(app.get("violation_count", 0) for app in apps_dict.values())
        
        return {
            "metadata": {
                "job_id": job.id,
                "project_path": job.project_path,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else datetime.now(timezone.utc).isoformat(),
                "total_findings": len(all_findings),
                "total_violations": total_violations,
                "git_context": git_ctx
            },
            "findings": [
                {**to_dict(f), "fingerprint": FixQueue.fingerprint(f)}
                for f in all_findings
            ],
            "apps": apps_dict,
            "fleet_average": fleet_average,
            "coupling_matrix": coupling,
            "dna": to_dict(dna),
            "config_health": [],
            "dependency_scan": [],
            "recommendations": recommendations if recommendations else [],
            "change_summary": {
                "first_run": False,
                "new_violations": 0,
                "resolved_violations": 0,
                "score_deltas": {}
            },
            "rules_summary": [],
            "fix_queue": to_dict(sync_result),
            "timeline": trends,
            "git_context": git_ctx
        }

    def _build_summary(self, result_data: dict) -> dict:
        """
        Lightweight summary written alongside audit_data_complete.json.
        Must include:
          - timestamp  for load_score_history chart labels
          - findings   for compute_violation_persistence fingerprint lookup
        """
        findings_with_fp = [
            {
                "fingerprint": f.get("fingerprint"),
                "rule_id":     f.get("rule_id"),
            }
            for f in result_data.get("findings", [])
            if f.get("fingerprint")
        ]

        return {
            "job_id":         result_data["metadata"]["job_id"],
            "timestamp":      (
                result_data["metadata"].get("finished_at")
                or datetime.now(timezone.utc).isoformat()
            ),
            "fleet_average":  result_data["fleet_average"],
            "app_scores":     {k: v["score"] for k, v in result_data["apps"].items()},
            "findings_count": len(result_data["findings"]),
            "findings":       findings_with_fp,
        }
