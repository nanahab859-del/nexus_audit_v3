import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus
from core.infra.python_exe import get_venv_python

class LicenseAuditScanner(BaseScanner):
    name: ClassVar[str] = "license_audit"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.DEPENDENCY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "pip-licenses"
    timeout: ClassVar[int] = 60

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        venv_python = get_venv_python()
        
        args = ["--format", "json", "--from", "mixed"]
        if venv_python:
            args.extend(["--python", str(venv_python)])
        return args

    def _parse_output(self, output: Any, config: dict = None) -> List[Finding]:
        config = config or {}
        allowed = config.get("allowed_licenses", ["MIT", "Apache 2.0", "BSD-3-Clause"])
        flagged = config.get("flagged_licenses", ["GPL", "AGPL"])
        
        if not output:
            return []
            
        try:
            data = json.loads(output) if isinstance(output, str) else output
        except json.JSONDecodeError:
            return []
            
        findings = []
        for pkg in data:
            license_name = pkg.get("License", "UNKNOWN")
            pkg_name = pkg.get("Name", "unknown")
            
            severity = Severity.LOW
            if license_name in flagged:
                severity = Severity.HIGH
            elif license_name not in allowed:
                severity = Severity.MEDIUM
                
            if severity != Severity.LOW or license_name == "UNKNOWN":
                findings.append(create_finding(
                    scanner=self.name,
                    rule_id="license-violation",
                    file="",
                    line=0,
                    column=0,
                    severity=severity,
                    category=self.category,
                    title=f"Package {pkg_name} has license issue: {license_name}",
                    description=f"License '{license_name}' is not in allowed list.",
                    suggestion=f"Verify if {license_name} is acceptable for this project."
                ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        if code != 0:
            await bus.publish_log("error", f"LicenseAudit failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout, config)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
