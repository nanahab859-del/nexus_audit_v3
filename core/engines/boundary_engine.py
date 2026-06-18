from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from core.primitives.models import ModuleEntry, ProjectDNA, Finding, Category, Severity, create_finding
from core.primitives.events import EventBus
import fnmatch
import logging

logger = logging.getLogger(__name__)

class Classification(Enum):
    INTERNAL = "internal"
    FRAMEWORK = "framework"
    BOOTSTRAP = "bootstrap"
    ALLOWED = "allowed"
    HUB_APP = "hub_app"
    TEST_CROSS_APP = "test_cross_app"
    VIOLATION = "violation"

class BoundaryEngine:
    def __init__(self, communication_config: dict):
        self.config = communication_config
        self.default_action = self.config.get("default_action", "allow")
        self.allowed_patterns = self.config.get("allowed_patterns", [])
        self.bootstrap_files = self.config.get("bootstrap_files", [])

    def classify_import(
        self,
        source_module: ModuleEntry,
        imported_module_path: str,
        dna: ProjectDNA,
        hub_apps: set[str]
    ) -> Classification:
        
        # 1. Internal
        target_mod = dna.modules.get(imported_module_path)
        if target_mod and target_mod.app == source_module.app:
            return Classification.INTERNAL
            
        # 2. Hub App
        if target_mod and target_mod.app in hub_apps:
            return Classification.HUB_APP
            
        # 3. Framework/External
        if not target_mod:
            return Classification.FRAMEWORK
            
        # 4. Bootstrap
        # Supports both bare stems ("modA") and full relative paths ("app1/modA.py")
        rel = source_module.relative_path.replace("\\", "/")
        stem = source_module.file_path.stem
        if any(rel == b or rel.endswith("/" + b) or stem == b for b in self.bootstrap_files):
            return Classification.BOOTSTRAP
            
        # 5. Allowed pattern
        for pattern in self.allowed_patterns:
            if fnmatch.fnmatch(imported_module_path, pattern.get("import_pattern", "")):
                return Classification.ALLOWED
                
        # 6. Test cross-app
        if source_module.is_test:
            return Classification.TEST_CROSS_APP
            
        # 7. Default action
        if self.default_action == "deny":
            return Classification.VIOLATION
        
        return Classification.ALLOWED

    def evaluate(
        self,
        dna: ProjectDNA,
        hub_apps: set[str],
        bus: EventBus
    ) -> list[Finding]:
        violations = []
        
        for source_module in dna.modules.values():
            for import_path, line_number in source_module.imports.items():
                target_mod = dna.modules.get(import_path)
                target_app = target_mod.app if target_mod else "external"
                
                # Internal imports are ignored
                if target_mod and target_mod.app == source_module.app:
                    continue
                    
                classification = self.classify_import(source_module, import_path, dna, hub_apps)
                
                if classification == Classification.VIOLATION:
                    severity_str = self.config.get("violation_severity", "MEDIUM")
                    try:
                        severity = Severity[severity_str.upper()]
                    except KeyError:
                        severity = Severity.MEDIUM
                    
                    violations.append(create_finding(
                        scanner="boundary_engine",
                        rule_id="boundary-violation",
                        file=source_module.relative_path,
                        line=line_number,
                        column=1,
                        severity=severity,
                        category=Category.ARCHITECTURE,
                        title=f"Cross-app violation: {source_module.app} → {target_app}",
                        description=f"Import of '{import_path}' crosses app boundary",
                        suggestion="Use an allowed communication pattern or restructure"
                    ))
                    
        return violations
