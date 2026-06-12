from dataclasses import dataclass, field, is_dataclass, asdict
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pathlib import Path
import uuid

# --- 1. Enums ---
class ConfigurationError(Exception):
    """Raised when the merged audit configuration is invalid."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))

class Severity(Enum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class Category(Enum):
    SECURITY = "security"
    QUALITY = "quality"
    PERFORMANCE = "performance"
    DEPENDENCY = "dependency"
    ARCHITECTURE = "architecture"

class Persistence(Enum):
    NEW = "new"
    PERSISTENT = "persistent"
    INTERMITTENT = "intermittent"
    RESOLVED = "resolved"

class FixStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SNOOZED = "snoozed"

class ScanStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class JobState(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

# --- Serialization Helper ---
def to_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_dict(v) for v in obj]
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif is_dataclass(obj):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    return obj

@dataclass
class ModuleEntry:
    module_path: str
    file_path: Path
    relative_path: str
    app: str
    imports: Dict[str, int]
    defined_names: List[str]
    is_test: bool
    lines_of_code: int
    language: str
    parse_status: str
    has_wildcard_imports: bool

@dataclass
class ProjectDNA:
    modules: Dict[str, ModuleEntry]
    apps: List[str]
    physical_files: List[str]
    built_at: datetime
    project_root: Path

@dataclass(frozen=True)
class Finding:
    id: str
    rule_id: str
    scanner: str
    file: str
    line: int
    column: int
    severity: Severity
    category: Category
    title: str
    description: str
    snippet: Optional[str] = None
    fingerprint: Optional[str] = None
    suggestion: Optional[str] = None
    cwe: Optional[str] = None
    cvss_score: Optional[float] = None
    persistence: Persistence = Persistence.NEW
    fix_status: FixStatus = FixStatus.OPEN

def create_finding(
    scanner: str,
    rule_id: str,
    file: str,
    line: int,
    column: int,
    severity: Severity,
    category: Category,
    title: str,
    description: str,
    **kwargs
) -> Finding:
    return Finding(
        id=str(uuid.uuid4()),
        scanner=scanner,
        rule_id=rule_id,
        file=file,
        line=line,
        column=column,
        severity=severity,
        category=category,
        title=title,
        description=description,
        **kwargs
    )

def finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "rule_id": f.rule_id,
        "scanner": f.scanner,
        "file": f.file,
        "line": f.line,
        "column": f.column,
        "severity": f.severity.name,
        "category": f.category.value,
        "title": f.title,
        "description": f.description,
        "snippet": f.snippet,
        "fingerprint": f.fingerprint,
        "suggestion": f.suggestion,
        "cwe": f.cwe,
        "cvss_score": f.cvss_score,
        "persistence": f.persistence.value,
        "fix_status": f.fix_status.value,
    }

@dataclass
class ScanResult:
    scanner: str
    scanner_version: str
    status: ScanStatus = ScanStatus.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None

@dataclass
class Job:
    id: str
    project_id: str
    project_path: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    state: JobState = JobState.RUNNING
    scan_results: List[ScanResult] = field(default_factory=list)
    output_paths: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    is_locked: bool = False

# --- 3. Policy Objects ---

@dataclass
class RetentionPolicy:
    max_jobs: int = 20
    keep_reports: bool = True
    keep_trends: bool = True
    keep_milestone_jobs: bool = True

@dataclass
class QualityGate:
    max_critical: int = 0
    max_high: int = 5
    min_fleet_score: float = 0.0
    min_cvss_threshold: float = 7.0
    break_build_on_failure: bool = True

@dataclass
class PipelineConfig:
    scanner_timeout: int = 300
    max_concurrent_scanners: int = 4
    path_match_mode: str = "glob"
    cache_scan_results: bool = True
    follow_symlinks: bool = False

@dataclass
class SuppressionPolicy:
    rules: Dict[str, List[str]] = field(default_factory=dict)

@dataclass
class ScoringConfig:
    violation_default: float = 5.0
    violation_hub: float = 3.0
    security_high: float = 12.0
    security_medium: float = 6.0
    security_low: float = 3.0
    complexity_above: float = 10.0
    complexity_factor: float = 2.0
    dead_code_per: float = 3.0
    ghost_file_per: float = 2.0
    exclude_tests: bool = True

@dataclass
class AppScore:
    app: str
    score: int
    is_hub: bool
    lines_of_code: int
    finding_counts: Dict[str, int]
    penalty_breakdown: Dict[str, float]

@dataclass
class RuleDefinition:
    id: str
    name: str
    type: str
    severity: str
    category: str
    languages: List[str]
    description: str
    suggestion: str
    config: Dict[str, Any] = field(default_factory=dict)

# --- 4. Settings ---

@dataclass
class GlobalSettings:
    api_key: Optional[str] = None
    ai_enabled: bool = False
    ai_provider: str = "claude"
    ai_model: str = "claude-opus-4-7"
    ui_theme: str = "dark"
    active_project_id: Optional[str] = None

@dataclass
class ProjectSettings:
    project_path: str
    project_name: str = ""
    scanners: Dict[str, bool] = field(default_factory=dict)
    scanner_configs: Dict[str, Dict] = field(default_factory=dict)
    ignore_paths: List[str] = field(default_factory=lambda: [
        "venv/", "node_modules/", ".git/", "__pycache__/"
    ])
    fail_on_severity: Severity = Severity.CRITICAL
    force_rescan: bool = False
    retention_policy: RetentionPolicy = field(default_factory=RetentionPolicy)
    quality_gate: QualityGate = field(default_factory=QualityGate)
    pipeline_config: PipelineConfig = field(default_factory=PipelineConfig)
    suppression_policy: SuppressionPolicy = field(default_factory=SuppressionPolicy)

    def __post_init__(self):
        if not self.project_path:
            raise ValueError("project_path is required")

# --- 5. Workspace & Project System ---

@dataclass
class Project:
    id: str
    name: str
    path: str
    settings: ProjectSettings
    job_history: List[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=datetime.now)
    last_audited_at: Optional[datetime] = None

@dataclass
class Workspace:
    projects: Dict[str, Project] = field(default_factory=dict)
    global_settings: GlobalSettings = field(default_factory=GlobalSettings)
    active_project_id: Optional[str] = None
