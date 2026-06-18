import json
from pathlib import Path
import re
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class RuffScanner(BaseScanner):
    name: ClassVar[str] = "ruff"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "ruff"
    timeout: ClassVar[int] = 60

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        select = config.get("select", ["E", "F", "W", "I", "UP"])
        ignore = config.get("ignore", [])
        
        args = ["check", "--output-format", "json", str(target)]
        if select:
            args.extend(["--select", ",".join(select)])
        if ignore:
            args.extend(["--ignore", ",".join(ignore)])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        if not output:
            return []
            
        try:
            data = json.loads(output) if isinstance(output, str) else output
        except json.JSONDecodeError:
            return []
            
        findings = []
        # Mapping Ruff rule prefixes to severity
        # E: Errors, F: Pyflakes, W: Warnings, I: isort, UP: pyupgrade
        severity_map = {
            "E": Severity.HIGH,
            "F": Severity.MEDIUM,
            "W": Severity.MEDIUM,
            "I": Severity.LOW,
            "UP": Severity.LOW
        }
        
        for issue in data:
            rule_id = issue.get("code", "")
            # Extract prefix (e.g., 'E' from 'E123')
            prefix = re.sub(r'[^A-Za-z]', '', rule_id)
            
            findings.append(create_finding(
                scanner=self.name,
                rule_id=rule_id,
                file=issue.get("filename", ""),
                line=issue.get("location", {}).get("row", 0),
                column=issue.get("location", {}).get("column", 0),
                severity=severity_map.get(prefix, Severity.LOW),
                category=self.category,
                title=issue.get("message", "Ruff Issue"),
                description=issue.get("message", ""),
                suggestion=issue.get("fix", {}).get("message", "No automatic fix")
            ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        import re # Import here for parse_output helper
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # Ruff returns 1 if issues are found, 0 if clean
        if code > 1:
            await bus.publish_log("error", f"Ruff failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
