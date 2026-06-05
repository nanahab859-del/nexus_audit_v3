import fnmatch
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.dna_builder import ProjectDNA, ModuleEntry
from core.models import Finding, Severity, Category
from core.rules_engine import RuleDefinition

class Classification(Enum):
    INTERNAL = "internal"          # same app
    FRAMEWORK = "framework"        # stdlib or framework package
    BOOTSTRAP = "bootstrap"        # exempt bootstrap file
    ALLOWED = "allowed"            # matches an allowed_pattern
    TEST_CROSS_APP = "test_cross_app"  # test file cross-app import
    VIOLATION = "violation"        # everything else

@dataclass
class AppConfig:
    name: str
    paths: list[str]
    role: str
    hub: bool

@dataclass
class CommunicationConfig:
    allowed_patterns: list[dict[str, str]]
    bootstrap_files: list[str]

class BoundaryEngine:
    def __init__(self, raw_config: dict[str, Any] | None):
        self.raw_config = raw_config or {}
        
        apps_data = self.raw_config.get("apps", [])
        self.apps: dict[str, AppConfig] = {}
        for app_data in apps_data:
            name = app_data.get("name")
            if name:
                self.apps[name] = AppConfig(
                    name=name,
                    paths=app_data.get("paths", [f"{name}/"]),
                    role=app_data.get("role", ""),
                    hub=app_data.get("hub", False)
                )
                
        comm_data = self.raw_config.get("communication", {})
        self.communication = CommunicationConfig(
            allowed_patterns=comm_data.get("allowed_patterns", [
                {"name": "Django signals", "import_pattern": "*.signals"},
                {"name": "Celery tasks", "import_pattern": "*.tasks"}
            ]),
            bootstrap_files=comm_data.get("bootstrap_files", [
                "asgi", "wsgi", "settings", "celery", "manage", "routing", "apps", "admin"
            ])
        )

    def classify_import(self, source_mod: ModuleEntry, target_module_path: str, dna: ProjectDNA) -> Classification:
        """Classify a single import statement."""
        source_app = source_mod.app
        
        # Check if target is a known app in DNA
        target_app = None
        for app in dna.apps:
            if target_module_path == app or target_module_path.startswith(f"{app}."):
                target_app = app
                break
                
        if not target_app:
            return Classification.FRAMEWORK
            
        if source_app == target_app:
            return Classification.INTERNAL
            
        if source_mod.is_test:
            return Classification.TEST_CROSS_APP
            
        # It's a cross-app import. Check bootstrap
        for bootstrap in self.communication.bootstrap_files:
            if source_mod.relative_path.endswith(f"{bootstrap}.py") or f"/{bootstrap}/" in source_mod.relative_path:
                return Classification.BOOTSTRAP
                
        # Check allowed patterns
        for pattern in self.communication.allowed_patterns:
            pat = pattern.get("import_pattern", "")
            if fnmatch.fnmatch(target_module_path, pat) or fnmatch.fnmatch(f"{target_module_path}.*", pat):
                return Classification.ALLOWED
                
        return Classification.VIOLATION

    def evaluate(self, dna: ProjectDNA, rules: list[RuleDefinition]) -> list[Finding]:
        """Evaluate all boundary rules."""
        boundary_rules = [r for r in rules if r.type == "boundary"]
        if not boundary_rules:
            # Add a default boundary rule if none configured
            boundary_rules = [RuleDefinition(
                id="no-cross-app-import",
                name="Direct cross-app import",
                severity=Severity.HIGH,
                type="boundary",
                category=Category.ARCHITECTURE,
                suggestion="Use allowed communication patterns instead."
            )]
            
        findings = []
        for rule in boundary_rules:
            scope = rule.config.get("scope", "cross_app")
            
            for mod in dna.modules.values():
                for imp in mod.imports:
                    classification = self.classify_import(mod, imp, dna)
                    
                    if classification == Classification.VIOLATION:
                        target_app = imp.split(".")[0] if imp else "unknown"
                        desc = rule.description.format(source_app=mod.app, target_app=target_app) if rule.description else f"App '{mod.app}' directly imports from '{target_app}'"
                        
                        findings.append(Finding(
                            scanner="boundary_engine",
                            file=mod.relative_path,
                            line=1,  # Approximate, since dna_builder didn't store line per import
                            column=1,
                            severity=rule.severity,
                            category=rule.category,
                            title=rule.name,
                            description=desc,
                            suggestion=rule.suggestion
                        ))
                        
        return findings
