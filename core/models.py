import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, Enum
from pathlib import Path
from typing import Literal

UTC = timezone.utc


class Severity(IntEnum):
    """Severity levels ordered from lowest to highest."""
    INFO = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5


class Category(Enum):
    """Finding categories."""
    SECURITY = "security"
    QUALITY = "quality"
    PERFORMANCE = "performance"
    DEPENDENCY = "dependency"
    ARCHITECTURE = "architecture"


@dataclass(frozen=True)
class Finding:
    """Immutable finding from a scanner."""
    scanner: str
    file: str
    line: int
    column: int
    severity: Severity
    category: Category
    title: str
    description: str
    suggestion: str | None = None
    cwe: str | None = None
    cvss_score: float | None = None
    id: str = field(init=False)

    def __post_init__(self) -> None:
        # Compute deterministic id from content
        content = f"{self.scanner}:{self.file}:{self.line}:{self.title}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
        object.__setattr__(self, "id", hash_val)


@dataclass
class ScanResult:
    """Result from one scanner run."""
    scanner: str
    started_at: datetime
    finished_at: datetime | None = None
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None


@dataclass
class Job:
    """Audit job tracking state."""
    project_path: Path
    started_at: datetime
    id: str = field(init=False)
    finished_at: datetime | None = None
    state: Literal["running", "completed", "cancelled", "failed"] = "running"
    scan_results: list[ScanResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(uuid.uuid4()))


@dataclass
class Settings:
    """Application settings."""
    project_path: Path
    api_key: str | None = None
    ai_enabled: bool = False
    ai_provider: str = "claude"
    ai_model: str = "claude-opus-4-7"
    force_rescan: bool = False
    scanners: dict[str, bool] = field(default_factory=dict)
    scanner_configs: dict[str, dict] = field(default_factory=dict)
    ui: dict = field(default_factory=dict)
