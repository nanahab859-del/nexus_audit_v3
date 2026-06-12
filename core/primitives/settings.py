from pathlib import Path
import asyncio
import uuid
import dataclasses
from datetime import datetime
from typing import Optional, Dict
from core.primitives.models import Workspace, Project, GlobalSettings, ProjectSettings
from core.primitives.atomic import read_json, write_json
from core.primitives.security import encrypt, decrypt

class SettingsManager:
    def __init__(self):
        self._workspace_path = Path.home() / ".nexus_audit" / "workspace.json"
        self._projects_dir = Path.home() / ".nexus_audit" / "projects"
        self._lock = asyncio.Lock()

    # ── Workspace ──────────────────────────────────────────────
    async def load_workspace(self) -> Workspace:
        async with self._lock:
            data = await read_json(self._workspace_path)
            if not data:
                return Workspace()
            
            # Reconstruct Workspace from dict
            # Simple deserialization: create GlobalSettings, then projects
            gs_dict = data.get("global_settings", {})
            if gs_dict.get("api_key"):
                gs_dict["api_key"] = decrypt(gs_dict["api_key"])
            
            global_settings = GlobalSettings(**gs_dict)
            
            # Projects deserialization would be more complex, 
            # here we assume simple dict-to-dataclass for now based on the spec.
            # In a real system, you'd use a robust mapper.
            projects = {}
            for pid, pdata in data.get("projects", {}).items():
                # Assuming Project needs to be constructed carefully
                projects[pid] = Project(**pdata)
            
            return Workspace(projects=projects, global_settings=global_settings, active_project_id=data.get("active_project_id"))

    async def save_workspace(self, workspace: Workspace) -> None:
        async with self._lock:
            from core.primitives.models import to_dict
            ws_dict = to_dict(workspace)
            # Encrypt api_key
            if ws_dict["global_settings"].get("api_key"):
                ws_dict["global_settings"]["api_key"] = encrypt(ws_dict["global_settings"]["api_key"])
            
            await write_json(self._workspace_path, ws_dict, indent=4)
            # Restore plaintext (not strictly necessary but safe)
            if workspace.global_settings.api_key:
                workspace.global_settings.api_key = decrypt(ws_dict["global_settings"]["api_key"])

    # ── Project lifecycle ──────────────────────────────────────
    async def register_project(self, name: str, path: str) -> Project:
        resolved_path = Path(path).resolve()
        if not resolved_path.exists() or not resolved_path.is_dir():
            raise ValueError(f"Path does not exist or is not a directory: {path}")
        
        project_id = str(uuid.uuid4())
        project_dir = self._projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        
        settings = ProjectSettings(project_path=str(resolved_path), project_name=name)
        project = Project(id=project_id, name=name, path=str(resolved_path), settings=settings)
        
        # Save project
        await self.save_project(project)
        
        # Update workspace
        workspace = await self.load_workspace()
        workspace.projects[project_id] = project
        await self.save_workspace(workspace)
        
        return project

    async def load_project(self, project_id: str) -> Project:
        project_path = self._projects_dir / project_id / "project.json"
        data = await read_json(project_path)
        if not data:
            raise FileNotFoundError(f"Project not found: {project_id}")
        
        # Construct Project object from data
        settings_dict = data.get("settings", {})
        
        # Manually construct nested objects
        pipeline_config_data = settings_dict.get("pipeline_config", {})
        retention_policy_data = settings_dict.get("retention_policy", {})
        quality_gate_data = settings_dict.get("quality_gate", {})
        suppression_policy_data = settings_dict.get("suppression_policy", {})
        
        from core.primitives.models import RetentionPolicy, QualityGate, PipelineConfig, SuppressionPolicy, Severity
        
        # Ensure fail_on_severity is converted back to Enum if it's a string
        severity_val = settings_dict.get("fail_on_severity", "CRITICAL")
        if isinstance(severity_val, str):
            severity = Severity[severity_val]
        else:
            severity = Severity(severity_val)

        settings = ProjectSettings(
            project_path=settings_dict["project_path"],
            project_name=settings_dict.get("project_name", ""),
            scanners=settings_dict.get("scanners", {}),
            scanner_configs=settings_dict.get("scanner_configs", {}),
            ignore_paths=settings_dict.get("ignore_paths", []),
            fail_on_severity=severity,
            force_rescan=settings_dict.get("force_rescan", False),
            retention_policy=RetentionPolicy(**retention_policy_data),
            quality_gate=QualityGate(**quality_gate_data),
            pipeline_config=PipelineConfig(**pipeline_config_data),
            suppression_policy=SuppressionPolicy(**suppression_policy_data)
        )
        
        return Project(
            id=data["id"], 
            name=data["name"], 
            path=data["path"], 
            settings=settings,
            job_history=data.get("job_history", []),
            registered_at=datetime.fromisoformat(data.get("registered_at")), 
            last_audited_at=datetime.fromisoformat(data.get("last_audited_at")) if data.get("last_audited_at") else None
        )

    async def save_project(self, project: Project) -> None:
        project_dir = self._projects_dir / project.id
        project_dir.mkdir(parents=True, exist_ok=True)
        from core.primitives.models import to_dict
        await write_json(project_dir / "project.json", to_dict(project), indent=4)

    async def delete_project(self, project_id: str) -> None:
        workspace = await self.load_workspace()
        if project_id in workspace.projects:
            del workspace.projects[project_id]
            await self.save_workspace(workspace)
        
        project_dir = self._projects_dir / project_id
        if project_dir.exists():
            import shutil
            shutil.rmtree(project_dir)

    # ── Active project ─────────────────────────────────────────
    async def get_active_project(self) -> Optional[Project]:
        workspace = await self.load_workspace()
        if workspace.active_project_id:
            return await self.load_project(workspace.active_project_id)
        return None

    async def set_active_project(self, project_id: str) -> None:
        # Verify exists
        await self.load_project(project_id)
        
        workspace = await self.load_workspace()
        workspace.active_project_id = project_id
        await self.save_workspace(workspace)

    # ── ProjectSettings access ────────────────────────────────────────
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

    async def update_project_settings(self, project_id: str, settings: ProjectSettings) -> None:
        project = await self.load_project(project_id)
        project.settings = settings
        await self.save_project(project)

    # ── Partial updates (PATCH) ────────────────────────────────
    async def patch_project_settings(self, project_id: str, updates: dict) -> ProjectSettings:
        project = await self.load_project(project_id)
        settings_dict = dataclasses.asdict(project.settings)
        
        def deep_merge(target, source):
            for k, v in source.items():
                if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                    deep_merge(target[k], v)
                else:
                    target[k] = v
        
        deep_merge(settings_dict, updates)
        
        # Filter keys that are not in ProjectSettings fields
        allowed_keys = {f.name for f in dataclasses.fields(ProjectSettings)}
        filtered_dict = {k: v for k, v in settings_dict.items() if k in allowed_keys}
        
        new_settings = ProjectSettings(**filtered_dict)
        project.settings = new_settings
        await self.save_project(project)
        return new_settings

    # ── Export ─────────────────────────────────────────────────
    async def export_project_config(self, project_id: str) -> dict:
        project = await self.load_project(project_id)
        return dataclasses.asdict(project.settings)
