import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.models import Finding, Severity, Category
from core.events import EventBus
from core.dna_builder import ProjectDNA

@dataclass
class RuleDefinition:
    id: str
    severity: Severity
    type: Literal["boundary", "cycle", "ghost", "metric", "pattern", "regex", "dependency"]
    name: str = ""
    description: str = ""
    category: Category = Category.ARCHITECTURE
    config: dict[str, Any] = field(default_factory=dict)
    suggestion: str = ""
    languages: list[str] = field(default_factory=list)

class RulesEngine:
    def __init__(self, rules_file: Path) -> None:
        self.rules_file = rules_file
        self._rules_cache: list[RuleDefinition] | None = None
        self._raw_config: dict[str, Any] | None = None

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

    def load(self) -> list[RuleDefinition]:
        if self._rules_cache is not None:
            return self._rules_cache
            
        if not self.rules_file.exists():
            return []
            
        try:
            with open(self.rules_file, "r", encoding="utf-8") as f:
                self._raw_config = yaml.safe_load(f) or {}
        except Exception:
            return []
            
        rules_data = self._raw_config.get("rules", [])
        rules = []
        for r in rules_data:
            if "id" not in r or "type" not in r:
                continue
            
            rule = RuleDefinition(
                id=r["id"],
                severity=self._parse_severity(r.get("severity", "MEDIUM")),
                type=r["type"],
                name=r.get("name", r["id"]),
                description=r.get("description", ""),
                category=self._parse_category(r.get("category", "ARCHITECTURE")),
                config=r.get("config", {}),
                suggestion=r.get("suggestion", ""),
                languages=r.get("languages", [])
            )
            rules.append(rule)
            
        self._rules_cache = rules
        return rules

    def validate(self) -> list[str]:
        """Return list of validation errors in the rules file. [] = valid."""
        errors = []
        if not self.rules_file.exists():
            errors.append(f"Rules file not found: {self.rules_file}")
            return errors
            
        try:
            with open(self.rules_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            errors.append(f"YAML syntax error: {e}")
            return errors
            
        if not isinstance(data, dict):
            errors.append("Root element must be a dictionary.")
            return errors
            
        rules = data.get("rules", [])
        if not isinstance(rules, list):
            errors.append("'rules' must be a list.")
        else:
            for i, r in enumerate(rules):
                if not isinstance(r, dict):
                    errors.append(f"Rule at index {i} must be a dictionary.")
                    continue
                if "id" not in r:
                    errors.append(f"Rule at index {i} is missing 'id'.")
                if "type" not in r:
                    errors.append(f"Rule '{r.get('id', i)}' is missing 'type'.")
                    
        return errors

    async def evaluate(
        self,
        dna: ProjectDNA,
        scanner_findings: list[Finding],
        bus: EventBus,
    ) -> list[Finding]:
        """
        Evaluate all loaded rules against the DNA and scanner output.
        Returns Finding objects for each rule violation.
        """
        rules = self.load()
        violations: list[Finding] = []
        
        # Build inverted import graph for 'ghost' file detection
        imported_by: dict[str, set[str]] = {p: set() for p in dna.physical_files}
        for mod in dna.modules.values():
            for imp in mod.imports:
                # Naive matching of imported module back to physical file
                # In a real impl, this needs accurate resolution. 
                # For now, mark anything that matches a module path
                imp_path = imp.replace(".", "/") + ".py"
                imp_init = imp.replace(".", "/") + "/__init__.py"
                if imp_path in imported_by:
                    imported_by[imp_path].add(mod.relative_path)
                if imp_init in imported_by:
                    imported_by[imp_init].add(mod.relative_path)
                    
        for rule in rules:
            if rule.type == "ghost":
                for file_path, importers in imported_by.items():
                    if not importers and file_path in dna.physical_files:
                        # Ensure it's not a bootstrap or entrypoint file
                        if "manage.py" in file_path or "wsgi" in file_path or "asgi" in file_path or "settings" in file_path:
                            continue
                        if file_path.endswith("__init__.py"):
                            continue
                            
                        violations.append(Finding(
                            scanner="rules_engine",
                            file=file_path,
                            line=1,
                            column=1,
                            severity=rule.severity,
                            category=rule.category,
                            title=rule.name,
                            description=rule.description or "File exists on disk but is never imported",
                            suggestion=rule.suggestion
                        ))
            
            elif rule.type == "metric":
                metric_name = rule.config.get("metric")
                threshold = rule.config.get("threshold", 0)
                if not metric_name:
                    continue
                metric_name_l = metric_name.lower()
                match_count = 0
                for f in scanner_findings:
                    text = (f.title or "") + " " + (f.description or "")
                    if metric_name_l in text.lower():
                        match_count += 1
                if match_count > threshold:
                    violations.append(Finding(
                        scanner="rules_engine",
                        file=next(iter(dna.physical_files), ""),
                        line=1,
                        column=1,
                        severity=rule.severity,
                        category=rule.category,
                        title=rule.name,
                        description=rule.description or f"Metric '{metric_name}' count {match_count} exceeds threshold {threshold}",
                        suggestion=rule.suggestion
                    ))

            elif rule.type == "pattern":
                from core.dna_builder import LANGUAGES
                import tree_sitter
                pattern = rule.config.get("pattern")
                if not pattern:
                    continue
                for file_path, mod in dna.modules.items():
                    if rule.languages and mod.language not in rule.languages:
                        continue
                    ts_lang = LANGUAGES.get(mod.language)
                    if not ts_lang:
                        continue
                    try:
                        query = ts_lang.query(pattern)
                        abs_path = dna.project_root / mod.relative_path
                        source_bytes = abs_path.read_bytes()
                        parser = tree_sitter.Parser(ts_lang)
                        tree = parser.parse(source_bytes)
                        captures = query.captures(tree.root_node)  # type: ignore
                        for node, _ in captures:
                            line_num = node.start_point.row + 1
                            violations.append(Finding(
                                scanner="rules_engine",
                                file=mod.relative_path,
                                line=line_num,
                                column=node.start_point.column,
                                severity=rule.severity,
                                category=rule.category,
                                title=rule.name,
                                description=rule.description or f"AST Pattern match",
                                suggestion=rule.suggestion
                            ))
                    except Exception as e:
                        pass

                    
            elif rule.type == "regex":
                expression = rule.config.get("expression")
                if not expression:
                    continue
                try:
                    pattern = re.compile(expression)
                    for file_path in dna.physical_files:
                        # Check language constraint if any
                        matched_mod = None
                        for mod in dna.modules.values():
                            if mod.relative_path == file_path:
                                matched_mod = mod
                                break
                        if rule.languages and matched_mod and matched_mod.language not in rule.languages:
                            continue
                            
                        abs_path = dna.project_root / file_path
                        try:
                            content = abs_path.read_text(encoding="utf-8")
                            for line_num, line in enumerate(content.splitlines(), 1):
                                if pattern.search(line):
                                    violations.append(Finding(
                                        scanner="rules_engine",
                                        file=file_path,
                                        line=line_num,
                                        column=1,
                                        severity=rule.severity,
                                        category=rule.category,
                                        title=rule.name,
                                        description=rule.description or f"Regex match: {expression}",
                                        suggestion=rule.suggestion
                                    ))
                        except Exception:
                            pass
                except re.error:
                    await bus.publish_log("error", f"Invalid regex in rule {rule.id}")

            elif rule.type == "cycle":
                # Find cycles using DFS on DNA import graph
                graph = {}
                for mod in dna.modules.values():
                    graph[mod.module_path] = mod.imports

                cycles: list[list[str]] = []
                global_visited: set[str] = set()

                for start_node in list(graph.keys()):
                    if start_node in global_visited:
                        continue
                    # iterative DFS using explicit stack: (node, iterator, path)
                    stack: list[tuple[str, Any, list[str]]] = [(start_node, iter(graph.get(start_node, [])), [start_node])]
                    while stack:
                        node, neighbors_iter, path = stack[-1]
                        global_visited.add(node)
                        try:
                            neighbor = next(neighbors_iter)
                            if neighbor not in dna.modules:
                                continue
                            if neighbor in path:
                                cycle_start = path.index(neighbor)
                                cycles.append(path[cycle_start:] + [neighbor])
                                continue
                            if neighbor in global_visited:
                                continue
                            stack.append((neighbor, iter(graph.get(neighbor, [])), path + [neighbor]))
                        except StopIteration:
                            stack.pop()

                # report cycles
                reported_cycles = set()
                for cycle in cycles:
                    # Create a deterministic hash for the cycle set
                    cycle_set = frozenset(cycle)
                    if cycle_set in reported_cycles:
                        continue
                    reported_cycles.add(cycle_set)
                    
                    cycle_str = " -> ".join(cycle)
                    # Create finding on the first file in the cycle
                    mod = dna.modules[cycle[0]]
                    violations.append(Finding(
                        scanner="rules_engine",
                        file=mod.relative_path,
                        line=1,
                        column=1,
                        severity=rule.severity,
                        category=rule.category,
                        title=rule.name,
                        description=rule.description or f"Circular dependency: {cycle_str}",
                        suggestion=rule.suggestion
                    ))
                    
            elif rule.type == "boundary":
                pass
                
        # Evaluate boundary rules
        from core.boundary_engine import BoundaryEngine
        boundary_engine = BoundaryEngine(self._raw_config)
        boundary_findings = boundary_engine.evaluate(dna, rules)
        violations.extend(boundary_findings)
                
        return violations
