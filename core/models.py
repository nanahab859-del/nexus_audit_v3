from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime

class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

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

@dataclass
class Finding:
    id: str
    scanner: str
    file: str
    line: int
    column: int
    severity: Severity
    category: Category
    title: str
    description: str
    suggestion: Optional[str] = None
    cwe: Optional[str] = None
    cvss_score: Optional[float] = None
    persistence: Persistence = Persistence.NEW
    fix_status: FixStatus = FixStatus.OPEN

def finding_to_dict(f: Finding) -> dict:
    return {
        "id":          f.id,
        "scanner":     f.scanner,
        "file":        f.file,
        "line":        f.line,
        "column":      f.column,
        "severity":    f.severity.name,
        "category":    f.category.value,
        "title":       f.title,
        "description": f.description,
        "suggestion":  f.suggestion,
        "cwe":         f.cwe,
        "cvss_score":  f.cvss_score,
        "persistence": f.persistence.value,
        "fix_status":  f.fix_status.value,
    }

@dataclass
class ScanResult:
    scanner: str
    started_at: datetime
    finished_at: datetime
    findings: List[Finding]

@dataclass
class Job:
    id: str
    project_path: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    state: str = "running"
    scan_results: List[ScanResult] = field(default_factory=list)
    git_context: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Settings:
    project_path: str
    api_key: Optional[str] = None
    ai_enabled: bool = False
    ai_provider: str = "claude"
    ai_model: str = "claude-opus-4-7"
    force_rescan: bool = False
    scanners: Dict[str, bool] = field(default_factory=dict)
    scanner_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ui: Dict[str, Any] = field(default_factory=dict)
