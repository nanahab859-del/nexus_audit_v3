from __future__ import annotations

import dataclasses
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.primitives.models import (
    GlobalSettings, PipelineConfig, Project, ProjectSettings,
    QualityGate, RetentionPolicy, Severity, SuppressionPolicy, Workspace,
    to_dict,
)
from core.primitives.atomic import read_json, write_json
from core.primitives.security import encrypt, decrypt

import asyncio

class DuplicateNameError(ValueError):
    """Raised when attempting to register a project name that already exists."""
    pass

class SettingsManager:

    def __init__(self) -> None:
        self._workspace_path  = Path.home() / ".nexus_audit" / "workspace.json"
        self._projects_dir    = Path.home() / ".nexus_audit" / "projects"
        self._lock            = asyncio.Lock()
        self._project_cache: Dict[str, Project] = {}

    # ── Workspace ──────────────────────────────────────────────────────────────

    async def load_workspace(self) -> Workspace:
        async with self._lock:
            try:
                data = await read_json(self._workspace_path)
            except (OSError, PermissionError) as e:
                logging.warning(f"Cannot read workspace: {e}")
                return Workspace()

            if not data:
                return Workspace()

            gs_dict = data.get("global_settings", {})
            if gs_dict.get("api_key"):
                gs_dict["api_key"] = decrypt(gs_dict["api_key"])

            global_settings = GlobalSettings(**gs_dict)

            projects: Dict[str, Project] = {}
            for pid, pdata in data.get("projects", {}).items():
                try:
                    projects[pid] = self._deserialise_project(pdata)
                except Exception as e:
                    logging.warning(f"Skipping malformed project '{pid}': {e}")

            return Workspace(
                projects=projects,
                global_settings=global_settings,
                active_project_id=data.get("active_project_id"),
            )

    async def save_workspace(self, workspace: Workspace) -> None:
        async with self._lock:
            ws_dict = to_dict(workspace)

            # Encrypt api_key in the serialised dict ONLY — never mutate workspace
            if ws_dict["global_settings"].get("api_key"):
                ws_dict["global_settings"]["api_key"] = encrypt(
                    ws_dict["global_settings"]["api_key"]
                )

            try:
                await write_json(self._workspace_path, ws_dict, indent=4)
            except (OSError, PermissionError) as e:
                logging.error(f"Cannot save workspace: {e}")

    async def _get_project_by_path(self, path: str) -> Optional[Project]:
        workspace = await self.load_workspace()
        resolved = str(Path(path).resolve())
        for proj in workspace.projects.values():
            if proj.path == resolved:
                return proj
        return None

    # ── Project lifecycle ──────────────────────────────────────────────────────

    async def register_project(self, name: str, path: str) -> Project:
        resolved_path = Path(path).resolve()
        if not resolved_path.exists() or not resolved_path.is_dir():
            raise ValueError(f"Path does not exist or is not a directory: {path}")

        existing_proj = await self._get_project_by_path(str(resolved_path))
        if existing_proj:
            return existing_proj

        workspace = await self.load_workspace()
        for proj in workspace.projects.values():
            if proj.name == name:
                raise DuplicateNameError(f"A project with the name '{name}' already exists.")

        project_id  = str(uuid.uuid4())
        project_dir = self._projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        settings = ProjectSettings(project_path=str(resolved_path), project_name=name)
        project  = Project(
            id=project_id, name=name, path=str(resolved_path), settings=settings
        )

        await self.save_project(project)

        workspace = await self.load_workspace()
        workspace.projects[project_id] = project
        await self.save_workspace(workspace)

        return project

    async def load_project(self, project_id: str) -> Project:
        project_path = self._projects_dir / project_id / "project.json"
        data = await read_json(project_path)
        if not data:
            raise FileNotFoundError(f"Project not found: {project_id}")
        project = self._deserialise_project(data)
        self._project_cache[project.id] = project
        return project

    async def save_project(self, project: Project) -> None:
        project_dir = self._projects_dir / project.id
        project_dir.mkdir(parents=True, exist_ok=True)
        try:
            await write_json(project_dir / "project.json", to_dict(project), indent=4)
        except (OSError, PermissionError) as e:
            logging.error(f"Cannot save project {project.id}: {e}")

    async def delete_project(self, project_id: str) -> None:
        workspace = await self.load_workspace()
        if project_id in workspace.projects:
            del workspace.projects[project_id]
            await self.save_workspace(workspace)

        # Evict from cache so get_project() raises KeyError as expected
        self._project_cache.pop(project_id, None)

        project_dir = self._projects_dir / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)

    def get_project(self, project_id: str) -> Project:
        """
        Synchronous cache accessor. Raises KeyError if the project has not
        been loaded yet. Callers must await load_project() first.
        """
        if project_id not in self._project_cache:
            raise KeyError(
                f"Project '{project_id}' not in cache. "
                "Call `await load_project(project_id)` first."
            )
        return self._project_cache[project_id]

    def current_job(self) -> None:
        # Placeholder — will be connected to Orchestrator when job tracking lands
        return None

    # ── Active project ─────────────────────────────────────────────────────────

    async def get_active_project(self) -> Optional[Project]:
        workspace = await self.load_workspace()
        if workspace.active_project_id:
            return await self.load_project(workspace.active_project_id)
        return None

    async def set_active_project(self, project_id: str) -> None:
        await self.load_project(project_id)   # validate exists
        workspace = await self.load_workspace()
        workspace.active_project_id = project_id
        await self.save_workspace(workspace)

    # ── Settings access ────────────────────────────────────────────────────────

    async def get_global_settings(self) -> GlobalSettings:
        workspace = await self.load_workspace()
        return workspace.global_settings

    async def update_global_settings(self, settings: GlobalSettings) -> None:
        workspace = await self.load_workspace()
        workspace.global_settings = settings
        await self.save_workspace(workspace)

    async def get_project_settings(self, project_id: str) -> ProjectSettings:
        project = await self.load_project(project_id)
        return project.settings

    async def update_project_settings(
        self, project_id: str, settings: ProjectSettings
    ) -> None:
        project = await self.load_project(project_id)
        project.settings = settings
        await self.save_project(project)

    # ── Partial update (PATCH) ─────────────────────────────────────────────────

    async def patch_project_settings(
        self, project_id: str, updates: dict
    ) -> ProjectSettings:
        """
        Deep-merge `updates` into the current project settings and persist.

        Correctly reconstructs nested policy dataclasses after the merge so
        that accessing e.g. project.settings.retention_policy.max_jobs never
        raises AttributeError.
        """
        project       = await self.load_project(project_id)
        settings_dict = dataclasses.asdict(project.settings)

        def _deep_merge(target: dict, source: dict) -> None:
            for k, v in source.items():
                if isinstance(v, dict) and isinstance(target.get(k), dict):
                    _deep_merge(target[k], v)
                else:
                    target[k] = v

        _deep_merge(settings_dict, updates)

        # Reconstruct Severity from whatever form asdict() produced
        sev_raw = settings_dict.get("fail_on_severity", "CRITICAL")
        if isinstance(sev_raw, str):
            severity = Severity[sev_raw]
        elif isinstance(sev_raw, int):
            severity = Severity(sev_raw)
        else:
            severity = Severity.CRITICAL

        # Rebuild nested policy objects — asdict() converts them to plain dicts
        new_settings = ProjectSettings(
            project_path=settings_dict["project_path"],
            project_name=settings_dict.get("project_name", ""),
            scanners=settings_dict.get("scanners", {}),
            scanner_configs=settings_dict.get("scanner_configs", {}),
            ignore_paths=settings_dict.get("ignore_paths", []),
            fail_on_severity=severity,
            force_rescan=settings_dict.get("force_rescan", False),
            retention_policy=RetentionPolicy(
                **settings_dict.get("retention_policy", {})
            ),
            quality_gate=QualityGate(
                **settings_dict.get("quality_gate", {})
            ),
            pipeline_config=PipelineConfig(
                **settings_dict.get("pipeline_config", {})
            ),
            suppression_policy=SuppressionPolicy(
                **settings_dict.get("suppression_policy", {})
            ),
        )

        project.settings = new_settings
        await self.save_project(project)
        return new_settings

    # ── Export ─────────────────────────────────────────────────────────────────

    async def export_project_config(self, project_id: str) -> dict:
        project = await self.load_project(project_id)
        return dataclasses.asdict(project.settings)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _deserialise_project(self, data: dict) -> Project:
        """
        Reconstruct a Project from a raw dict (loaded from JSON).

        This is the single authoritative deserialisation path. Both
        load_workspace and load_project must use this method so that
        project objects are always properly typed regardless of the
        loading source.
        """
        settings_dict = data.get("settings", {})

        sev_raw = settings_dict.get("fail_on_severity", "CRITICAL")
        if isinstance(sev_raw, str):
            severity = Severity[sev_raw]
        elif isinstance(sev_raw, int):
            severity = Severity(sev_raw)
        else:
            severity = Severity.CRITICAL

        settings = ProjectSettings(
            project_path=settings_dict["project_path"],
            project_name=settings_dict.get("project_name", ""),
            scanners=settings_dict.get("scanners", {}),
            scanner_configs=settings_dict.get("scanner_configs", {}),
            ignore_paths=settings_dict.get("ignore_paths", []),
            fail_on_severity=severity,
            force_rescan=settings_dict.get("force_rescan", False),
            retention_policy=RetentionPolicy(
                **settings_dict.get("retention_policy", {})
            ),
            quality_gate=QualityGate(
                **settings_dict.get("quality_gate", {})
            ),
            pipeline_config=PipelineConfig(
                **settings_dict.get("pipeline_config", {})
            ),
            suppression_policy=SuppressionPolicy(
                **settings_dict.get("suppression_policy", {})
            ),
        )

        registered_raw  = data.get("registered_at")
        last_audit_raw  = data.get("last_audited_at")

        return Project(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            settings=settings,
            job_history=data.get("job_history", []),
            registered_at=(
                datetime.fromisoformat(registered_raw)
                if registered_raw
                else datetime.now(timezone.utc)
            ),
            last_audited_at=(
                datetime.fromisoformat(last_audit_raw)
                if last_audit_raw
                else None
            ),
        )
