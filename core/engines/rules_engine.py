import yaml
import logging
import asyncio
import re
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.primitives.models import Finding, ProjectDNA, RuleDefinition, create_finding, Severity, Category
from core.primitives.events import EventBus
from core.infra.language_detection import EXTENSION_MAP
from core.engines.boundary_engine import BoundaryEngine

logger = logging.getLogger(__name__)

class RulesEngine:
    def __init__(self, rules_path: Optional[Path] = None):
        self.rules_path = rules_path
        self._rules: List[RuleDefinition] = []
        self._scoring_config: Dict[str, Any] = {}
        self._communication_config: Dict[str, Any] = {}
        self._app_definitions: List[Dict] = []
        if rules_path is not None:
            self._load_rules()

    @classmethod
    async def create(cls, rules_path: Path) -> "RulesEngine":
        """Async factory — loads rules via asyncio.to_thread to avoid blocking the event loop."""
        engine = cls.__new__(cls)
        engine.rules_path = rules_path
        engine._rules = []
        engine._scoring_config = {}
        engine._communication_config = {}
        engine._app_definitions = []
        await asyncio.to_thread(engine._load_rules)
        return engine

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
        if not getattr(self, 'rules_path', None) or not self.rules_path.exists():
            logger.warning(f"Rules file not found: {getattr(self, 'rules_path', None)}")
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
            
            raw_apps = data.get("app_definitions", [])
            if isinstance(raw_apps, dict):
                self._app_definitions = []
                for name, cfg in raw_apps.items():
                    app_cfg = dict(cfg) if cfg else {}
                    app_cfg["name"] = name
                    if "is_hub" in app_cfg and "hub" not in app_cfg:
                        app_cfg["hub"] = app_cfg["is_hub"]
                    self._app_definitions.append(app_cfg)
            else:
                self._app_definitions = raw_apps
                for app_cfg in self._app_definitions:
                    if isinstance(app_cfg, dict) and "is_hub" in app_cfg and "hub" not in app_cfg:
                        app_cfg["hub"] = app_cfg["is_hub"]
            
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
        
        imported_by: Dict[str, set] = {p: set() for p in dna.physical_files}
        for mod in dna.modules.values():
            for imp_module_path in mod.imports:
                target = dna.modules.get(imp_module_path)
                if target:
                    imported_by[target.relative_path].add(mod.relative_path)
        
        for rule in self._rules:
            try:
                if rule.type == "ghost":
                    violations.extend(self._evaluate_ghost(rule, dna, imported_by))
                elif rule.type == "metric":
                    violations.extend(self._evaluate_metric(rule, scanner_findings))
                elif rule.type == "pattern":
                    violations.extend(self._evaluate_pattern(rule, dna))
                elif rule.type == "regex":
                    violations.extend(await self._evaluate_regex(rule, dna))
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
        cfg            = rule.config
        filter_cat     = cfg.get("category")
        min_sev_str    = cfg.get("min_severity", "LOW")
        threshold      = int(cfg.get("threshold", 1))

        try:
            min_sev = Severity[min_sev_str.upper()]
        except KeyError:
            min_sev = Severity.LOW

        matched = [
            f for f in scanner_findings
            if (not filter_cat or f.category.value == filter_cat)
            and f.severity.value >= min_sev.value
        ]

        if len(matched) >= threshold:
            return [create_finding(
                scanner="rules_engine",
                rule_id=rule.id,
                file="(project)",
                line=0,
                column=0,
                severity=rule.severity,
                category=rule.category,
                title=rule.name,
                description=(
                    f"{rule.description} "
                    f"({len(matched)} findings exceed threshold of {threshold})"
                ),
                suggestion=rule.suggestion,
            )]
        return []

    def _evaluate_pattern(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
        """
        Tree-sitter-based structural pattern matching — not yet implemented.
        Use type='regex' for text-based matching in the meantime.
        """
        logger.warning(
            "Rule '%s' uses type='pattern' which is not yet implemented. "
            "Switch to type='regex' for text-based matching. Skipping.",
            rule.id,
        )
        return []

    async def _evaluate_regex(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
        pattern_str = rule.config.get("pattern")
        if not pattern_str:
            logger.warning("Rule %s: missing 'pattern' in config", rule.id)
            return []

        try:
            compiled = re.compile(pattern_str)
        except re.error as e:
            logger.warning("Rule %s: invalid regex '%s': %s", rule.id, pattern_str, e)
            return []

        findings = []
        for mod in dna.modules.values():
            if rule.languages and "*" not in rule.languages and mod.language not in rule.languages:
                continue
            if mod.is_test and not rule.config.get("include_tests", False):
                continue

            try:
                source = await asyncio.to_thread(
                    mod.file_path.read_text, encoding="utf-8", errors="replace"
                )
            except OSError:
                continue

            for lineno, line in enumerate(source.splitlines(), start=1):
                if compiled.search(line):
                    findings.append(create_finding(
                        scanner="rules_engine",
                        rule_id=rule.id,
                        file=mod.relative_path,
                        line=lineno,
                        column=1,
                        severity=rule.severity,
                        category=rule.category,
                        title=rule.name,
                        description=rule.description or f"Pattern matched: {pattern_str}",
                        suggestion=rule.suggestion,
                    ))
                    if rule.config.get("first_match_only", True):
                        break   # one finding per file by default

        return findings

    def _evaluate_cycle(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
        graph: Dict[str, set] = {mp: set() for mp in dna.modules}
        for mp, mod in dna.modules.items():
            for imp in mod.imports:
                if imp in dna.modules:
                    graph[mp].add(imp)

        index_counter = [0]
        index: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        tarjan_stack: list[str] = []
        work_stack: list[tuple[str, Any]] = []
        sccs: list[list[str]] = []

        for start in dna.modules:
            if start in index:
                continue

            index[start] = lowlink[start] = index_counter[0]
            index_counter[0] += 1
            tarjan_stack.append(start)
            on_stack[start] = True
            work_stack.append((start, iter(graph.get(start, []))))

            while work_stack:
                node, it = work_stack[-1]
                pushed = False

                for successor in it:
                    if successor not in index:
                        index[successor] = lowlink[successor] = index_counter[0]
                        index_counter[0] += 1
                        tarjan_stack.append(successor)
                        on_stack[successor] = True
                        work_stack.append((successor, iter(graph.get(successor, []))))
                        pushed = True
                        break
                    elif on_stack.get(successor):
                        lowlink[node] = min(lowlink[node], index[successor])

                if pushed:
                    continue

                work_stack.pop()
                if work_stack:
                    parent = work_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

                if lowlink[node] == index[node]:
                    scc: list[str] = []
                    while True:
                        w = tarjan_stack.pop()
                        on_stack[w] = False
                        scc.append(w)
                        if w == node:
                            break
                    if len(scc) > 1:
                        sccs.append(scc)

        findings: list[Finding] = []
        for scc in sccs:
            scc_sorted = sorted(scc)

            apps_in_scc = {dna.modules[m].app for m in scc if m in dna.modules}
            is_intra_app_models = (
                len(apps_in_scc) == 1
                and all("models" in m for m in scc)
            )

            chain = " → ".join(scc_sorted + [scc_sorted[0]])
            first_mod = dna.modules.get(scc_sorted[0])
            severity = Severity.INFO if is_intra_app_models else rule.severity
            description = (
                f"Import cycle detected: {chain}"
                + (" (intra-app models pattern — informational)" if is_intra_app_models else "")
            )

            findings.append(create_finding(
                scanner="rules_engine",
                rule_id=rule.id,
                file=first_mod.relative_path if first_mod else scc_sorted[0],
                line=1, column=1,
                severity=severity,
                category=rule.category,
                title=rule.name,
                description=description,
                suggestion=rule.suggestion or "Break the cycle by extracting shared logic into a new module.",
            ))

        return findings

    def _evaluate_boundary(
        self,
        rule: RuleDefinition,
        dna: ProjectDNA,
        scanner_findings: List[Finding],
        bus: EventBus
    ) -> List[Finding]:
        comm_config = self._communication_config or {}
        hub_apps    = {app["name"] for app in self._app_definitions if app.get("hub")}
        engine      = BoundaryEngine(comm_config)
        return engine.evaluate(dna, hub_apps, bus)

    def _evaluate_dependency(self, rule: RuleDefinition, scanner_findings: List[Finding]) -> List[Finding]:
        scanner_filter = rule.config.get("scanner")
        min_sev_str    = rule.config.get("min_severity", "LOW")
        try:
            min_sev = Severity[min_sev_str.upper()]
        except KeyError:
            min_sev = Severity.LOW

        results = []
        for f in scanner_findings:
            if f.category != Category.DEPENDENCY:
                continue
            if f.severity.value < min_sev.value:
                continue
            if scanner_filter and f.scanner != scanner_filter:
                continue
            results.append(create_finding(
                scanner="rules_engine",
                rule_id=rule.id,
                file=f.file,
                line=f.line, column=f.column,
                severity=rule.severity,
                category=rule.category,
                title=f"{rule.name}: {f.title}",
                description=f.description,
                suggestion=rule.suggestion or f.suggestion,
            ))
        return results
