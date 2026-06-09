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
    error: Optional[str] = None

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
    # Core (existing)
    project_path:     str  = ""
    api_key:          Optional[str] = None
    ai_enabled:       bool = False
    ai_provider:      str  = "claude"
    ai_model:         str  = "claude-opus-4-7"
    force_rescan:     bool = False
    scanners:         Dict[str, bool] = field(default_factory=dict)
    scanner_configs:  Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ui:               Dict[str, Any] = field(default_factory=dict)

    # Project Identity
    project_name:             str  = ""
    project_key:              str  = ""         # NEW — slug, auto-derived
    project_version:          str  = ""
    primary_stack:            List[str] = field(default_factory=list)  # CHANGED: was str
    project_description:      str  = ""         # NEW
    project_owner:            str  = ""         # NEW
    project_criticality_tier: str  = "Tier 3"  # NEW

    # Source
    source_type:              str  = "local"    # NEW — "local" | "remote"
    source_remote_url:        str  = ""         # NEW
    source_remote_branch:     str  = "main"     # NEW
    source_remote_auth_type:  str  = "none"     # NEW — "none" | "ssh" | "token"
    source_remote_token_env:  str  = ""         # NEW
    source_remote_clone_depth:int  = 0          # NEW — 0 = full clone

    # Audit Scope
    inclusions:               List[str] = field(default_factory=list)
    exclusions:               List[str] = field(default_factory=lambda: [
                                  "node_modules/**", ".venv/**", "tests/**",
                                  "migrations/**", "**/*.pyc", "dist/**", "build/**"
                              ])
    enabled_extensions:       List[str] = field(default_factory=lambda: [".py"])
    test_pattern:             str  = ""         # NEW
    max_file_size_kb:         int  = 500        # NEW

    # Context
    reachability_enabled:     bool = True       # NEW
    telemetry_source:         str  = "none"     # NEW — "none"|"datadog"|"opentelemetry"

    # Reporting
    output_format:            str  = "JSON"     # kept for backward compat
    output_formats:           List[str] = field(default_factory=lambda: ["json","html"])  # NEW
    vex_formats:              List[str] = field(default_factory=list)  # NEW
    include_suppressions:     bool = False      # NEW
    report_output_dir:        str  = ""
    report_filename_template: str  = ""         # NEW
    report_retention_days:    int  = 0          # NEW
    custom_metadata:          List[Dict[str,str]] = field(default_factory=list)

    # AI Agent
    ai_remediation_level:     str  = "suggest"  # NEW — "suggest"|"draft_pr"|"auto_merge"
    ai_verify_with_tests:     bool = False       # NEW
    ai_test_command:          str  = ""          # NEW

    # Integrations
    webhook_url:              str  = ""
    notify_on:                List[str] = field(default_factory=list)   # NEW
    ci_mode:                  bool = False       # NEW
    quality_gate:             Dict[str,Any] = field(default_factory=lambda: {  # NEW
                                  "max_critical": 0, "min_score": 0
                              })

    # Environment
    environment_vars:         List[Dict[str,str]] = field(default_factory=list)  # NEW
    secret_refs:              List[Dict[str,str]] = field(default_factory=list)  # NEW

    # Rules
    custom_rules_yaml:        str  = ""

    # AI Extended Settings
    ai_temperature:        float = 0.7
    ai_max_tokens:         int   = 4096
    ai_timeout:            int   = 120
    ai_retry_enabled:      bool  = True
    ai_max_retries:        int   = 3
    ai_custom_endpoint:    str   = ""
    ai_api_version:        str   = ""
    ai_org_id:             str   = ""
    ai_local_model:        str   = "llama3:latest"
    ai_key_pool:           List[str] = field(default_factory=list)
    ai_smart_routing:      bool  = False
    ai_fallback_model:     str   = ""
    ai_budget_cap:         float = 0.0
    ai_data_scrubber:      bool  = True
    ai_prompt_shield:      bool  = True
    ai_multimodal_enabled: bool  = False
    ai_context_limit:      int   = 128000
