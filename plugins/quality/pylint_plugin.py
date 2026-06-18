import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class PylintScanner(BaseScanner):
    name: ClassVar[str] = "pylint"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "pylint"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        disable = config.get("disable", ["C0114", "C0115", "C0116", "R0903"])
        enable = config.get("enable", [])
        
        args = ["--output-format=json", str(target)]
        if disable:
            args.extend(["--disable", ",".join(disable)])
        if enable:
            args.extend(["--enable", ",".join(enable)])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        # Pylint JSON output can be empty if no issues, or a list of issues
        if not output:
            return []
            
        try:
            data = json.loads(output) if isinstance(output, str) else output
        except json.JSONDecodeError:
            return []
            
        findings = []
        severity_map = {
            "fatal": Severity.CRITICAL,
            "error": Severity.HIGH,
            "warning": Severity.MEDIUM,
            "refactor": Severity.LOW,
            "convention": Severity.LOW
        }
        
        for issue in data:
            findings.append(create_finding(
                scanner=self.name,
                rule_id=issue.get("message-id", "unknown"),
                file=issue.get("path", ""),
                line=issue.get("line", 0),
                column=issue.get("column", 0),
                severity=severity_map.get(issue.get("type", "convention"), Severity.LOW),
                category=self.category,
                title=issue.get("symbol", "Pylint Issue"),
                description=issue.get("message", ""),
                suggestion=f"See Pylint docs for {issue.get('message-id')}"
            ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # Pylint exit codes: bitmask (1=fatal, 2=error, 4=warning, 8=refactor, 16=convention, 32=usage)
        # We parse the output regardless of exit code if it's not a usage error
        if code & 32:
            await bus.publish_log("error", f"Pylint usage error: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
