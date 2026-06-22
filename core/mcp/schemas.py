from pathlib import Path
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field

SANDBOX_ROOT = (Path.home() / ".nexus_audit").resolve()

def _assert_safe_path(raw_path: str) -> Path:
    """Resolve and validate that a path is within the sandbox root.
    
    Raises ValueError if the resolved path escapes the sandbox.
    This blocks path traversal attacks like '../../.ssh/id_rsa'.
    """
    try:
        resolved = Path(raw_path).resolve()
    except (ValueError, OSError) as e:
        raise ValueError(f"Invalid path: {e}") from e

    if not str(resolved).startswith(str(SANDBOX_ROOT)):
        raise ValueError(
            f"Path '{resolved}' is outside the sandbox root '{SANDBOX_ROOT}'. "
            "The Nexus MCP server can only read from ~/.nexus_audit/."
        )
    return resolved

async def resolve_project_id(identifier: str) -> str:
    """
    Resolve a user-provided project identifier (path, name, or ID) 
    to the internal project UUID.
    """
    from core.primitives.settings import SettingsManager
    workspace = await SettingsManager().load_workspace()
    
    # 1. Check if it's already a valid UUID
    if identifier in workspace.projects:
        return identifier
        
    # 2. Check if it matches a project path or name
    for pid, proj in workspace.projects.items():
        if proj.path == identifier or proj.name == identifier:
            return pid
            
    raise ValueError(f"Project not found or unregistered: {identifier}")

class ProjectInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID to query")

class RunAuditInput(BaseModel):
    project_path: str = Field(
        description="Project path, name, or ID to audit",
        min_length=1,
        max_length=4096
    )
    fast_mode: bool = Field(
        default=False,
        description="If true, runs summary scan only (no coupling matrix). Faster."
    )

class FindingDetailInput(BaseModel):
    finding_hash: str = Field(
        description="SHA-256 fingerprint of the finding",
        pattern=r"^[a-f0-9]{8,64}$"
    )

class ListFindingsInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    run_id: Optional[str] = Field(default=None, description="Specific run; defaults to latest")
    severity: Optional[Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]] = None
    category: Optional[Literal["security", "quality", "complexity", "dependencies"]] = None
    status: Literal["open", "suppressed", "resolved"] = "open"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class FixQueueInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    severity_floor: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "HIGH"
    limit: int = Field(default=10, ge=1, le=50)

class TrendInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    last_n_runs: int = Field(default=10, ge=2, le=50)
    branch: Optional[str] = Field(default=None, description="Filter to a specific git branch")

class DiffInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    run_id_a: str = Field(description="The older run (baseline)")
    run_id_b: str = Field(description="The newer run (after fix)")

class FileContextInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    file_path: str = Field(description="Path relative to project root, e.g. src/auth/login.py")
    limit: int = Field(default=20, ge=1, le=50)

class ScannerToggleInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    scanner_names: List[str] = Field(description="List of scanner names to toggle (e.g. ['bandit', 'ruff'])")
    reasoning: str = Field(min_length=15, description="MANDATORY: Architectural or security justification for toggling these scanners.")

class ScannerConfigInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    scanner_name: str = Field(description="The exact string name of the scanner")
    strictness: str = Field(description="Strictness level to set")
    reasoning: str = Field(min_length=15, description="MANDATORY: Architectural or security justification for changing this config.")

class ProjectConfigInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    config_patch: Dict[str, Any] = Field(description="Dictionary of config settings to patch")
    reasoning: str = Field(min_length=15, description="MANDATORY: Architectural or security justification for changing project config.")

class ReportGenerationInput(BaseModel):
    project_path: str = Field(description="Project path, name, or ID")
    output_path: Optional[str] = Field(default=None, description="The filename or relative path for the generated markdown report. Must be inside the project sandbox.")
    format: Literal["md", "json"] = Field(default="md", description="Format of the report")
