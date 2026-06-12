import yaml
import logging
import asyncio
import re
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.primitives.models import Finding, ProjectDNA, RuleDefinition, create_finding, Severity, Category
from core.primitives.events import EventBus
from core.infra.language_detection import LANGUAGE_EXTENSIONS

logger = logging.getLogger(__name__)

class RulesEngine:
    def __init__(self, rules_path: Path):
        self.rules_path = rules_path
        self._rules: List[RuleDefinition] = []
        self._scoring_config: Dict[str, Any] = {}
        self._communication_config: Dict[str, Any] = {}
        self._app_definitions: List[Dict] = []
        self._load_rules()

    def _parse_severity(self, sev_str: str) -> Severity:
        try:
            return Severity[sev_str.upper()]
        except KeyError:
            return Severity.MEDIUM

    def _parse_category(self, cat_str: str) -> Category:
        try:
            return Category(cat_str.lower())
        except ValueError:
            return Category.ARCHITECTURE

    def _load_rules(self) -> None:
        if not self.rules_path.exists():
            logger.warning(f"Rules file not found: {self.rules_path}")
            return
            
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
            rules_list = data.get("rules", [])
            for r in rules_list:
                try:
                    self._rules.append(RuleDefinition(
                        id=r["id"],
                        name=r.get("name", r["id"]),
                        type=r["type"],
                        severity=self._parse_severity(r.get("severity", "MEDIUM")),
                        category=self._parse_category(r.get("category", "ARCHITECTURE")),
                        languages=r.get("languages", []),
                        description=r.get("description", ""),
                        suggestion=r.get("suggestion", ""),
                        config=r.get("config", {})
                    ))
                except KeyError as e:
                    logger.warning(f"Invalid rule format in {self.rules_path}: missing {e}")
                    
            self._scoring_config = data.get("scoring_config", {})
            self._communication_config = data.get("communication_config", {})
            self._app_definitions = data.get("app_definitions", [])
            
        except Exception as e:
            logger.warning(f"Failed to load rules: {e}")
            self._rules = []

    @property
    def rules(self) -> List[RuleDefinition]:
        return self._rules

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def scoring_config(self) -> Dict:
        return self._scoring_config

    @property
    def communication_config(self) -> Dict:
        return self._communication_config

    @property
    def app_definitions(self) -> List[Dict]:
        return self._app_definitions

    async def evaluate(
        self,
        dna: ProjectDNA,
        scanner_findings: List[Finding],
        bus: EventBus
    ) -> List[Finding]:
        violations: List[Finding] = []
        
        # Build imported_by graph
        imported_by: Dict[str, set[str]] = {p: set() for p in dna.physical_files}
        for mod in dna.modules.values():
            for imp in mod.imports:
                # Naive reverse mapping
                for physical in dna.physical_files:
                    if physical.startswith(imp.replace(".", os.sep)):
                        imported_by[physical].add(mod.relative_path)
        
        for rule in self._rules:
            try:
                if rule.type == "ghost":
                    violations.extend(self._evaluate_ghost(rule, dna, imported_by))
                elif rule.type == "metric":
                    violations.extend(self._evaluate_metric(rule, scanner_findings))
                elif rule.type == "pattern":
                    violations.extend(self._evaluate_pattern(rule, dna))
                elif rule.type == "regex":
                    violations.extend(self._evaluate_regex(rule, dna))
                elif rule.type == "cycle":
                    violations.extend(self._evaluate_cycle(rule, dna))
                elif rule.type == "boundary":
                    violations.extend(self._evaluate_boundary(rule, dna, scanner_findings, bus))
                elif rule.type == "dependency":
                    violations.extend(self._evaluate_dependency(rule, scanner_findings))
            except Exception as e:
                logger.warning(f"Rule {rule.id} failed: {e}")
                
        return violations

    def _evaluate_ghost(self, rule: RuleDefinition, dna: ProjectDNA, imported_by: dict) -> List[Finding]:
        findings = []
        bootstrap = self._communication_config.get("bootstrap_files", [])
        
        for file_path, importers in imported_by.items():
            if not importers:
                # Check exclusions
                if any(b in file_path for b in bootstrap): continue
                if file_path.endswith("__init__.py"): continue
                if file_path not in dna.physical_files: continue
                
                # Check languages
                mod = next((m for m in dna.modules.values() if m.relative_path == file_path), None)
                if not mod or (rule.languages and rule.languages != ["*"] and mod.language not in rule.languages):
                    continue
                    
                findings.append(create_finding(
                    scanner="rules_engine", rule_id=rule.id, file=file_path, line=1, column=1,
                    severity=rule.severity, category=rule.category, title=rule.name,
                    description=rule.description or "File exists on disk but is never imported",
                    suggestion=rule.suggestion
                ))
        return findings

    def _evaluate_metric(self, rule: RuleDefinition, scanner_findings: List[Finding]) -> List[Finding]:
        # Filter scanner_findings by category/severity
        # Create ONE summary finding if threshold exceeded
        return [] # Placeholder, implement based on specific rule config

    def _evaluate_pattern(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
        # Implement pattern matching using tree-sitter
        return []

    def _evaluate_regex(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
        # Implement regex matching line-by-line
        return []

    def _evaluate_cycle(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
        # Implement DFS cycle detection as described in spec
        return []

    def _evaluate_boundary(self, rule: RuleDefinition, dna: ProjectDNA, scanner_findings: List[Finding], bus: EventBus) -> List[Finding]:
        from core.boundary_engine import BoundaryEngine
        # ... logic to delegate
        return []

    def _evaluate_dependency(self, rule: RuleDefinition, scanner_findings: List[Finding]) -> List[Finding]:
        # Filter scanner_findings by category=DEPENDENCY
        return []
