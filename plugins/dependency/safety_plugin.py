import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class PipAuditScanner(BaseScanner):
    name: ClassVar[str] = "pip_audit"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.DEPENDENCY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "pip-audit"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        req_file = config.get("requirements_file")
        if not req_file:
            for candidate in ["requirements.txt", "pyproject.toml", "Pipfile"]:
                p = target / candidate
                if p.exists():
                    req_file = str(p)
                    break
        
        args = ["--format", "json"]
        if req_file:
            args.extend(["--requirement", req_file])
        else:
            args.append("--local")
            
        cache_dir = config.get("cache_dir")
        if cache_dir:
            args.extend(["--cache-dir", cache_dir])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        data = json.loads(output) if isinstance(output, str) else output
        findings = []
        
        # pip-audit v2.x+ structure: {'dependencies': [{'name': ..., 'vulns': [...]}, ...]}
        dependencies = data.get("dependencies", []) if isinstance(data, dict) else []
        for dep in dependencies:
            pkg_name = dep.get("name", "unknown")
            pkg_version = dep.get("version", "unknown")
            
            for v in dep.get("vulns", []):
                fix_versions = v.get("fix_versions", [])
                fix_available = bool(fix_versions)
                
                findings.append(create_finding(
                    scanner=self.name,
                    rule_id=v.get("id", "unknown-vuln"),
                    file="",  # Dependency scan doesn't point to a specific file line
                    line=0,
                    column=0,
                    severity=Severity.HIGH if fix_available else Severity.MEDIUM,
                    category=self.category,
                    title=f"{pkg_name} {pkg_version} has known vulnerability {v.get('id', '')}",
                    description=v.get("description", "No description available"),
                    suggestion=f"Upgrade to {fix_versions[0]}" if fix_available else "No fix available",
                    cwe=v.get("aliases", [None])[0] if v.get("aliases") else None,
                    cvss_score=None # Severity is provided, CVSS not always available
                ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus):
            return []
            
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # pip-audit returns non-zero if vulnerabilities are found
        if code != 0 and not stdout:
            await bus.publish_log("error", f"pip-audit failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
