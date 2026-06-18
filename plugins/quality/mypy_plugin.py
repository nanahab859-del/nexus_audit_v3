import re
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class MypyScanner(BaseScanner):
    name: ClassVar[str] = "mypy"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "mypy"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        args = [str(target), "--no-error-summary", "--show-error-codes"]
        if config.get("strict", False):
            args.append("--strict")
        exclude = config.get("exclude_paths", [])
        if exclude:
            args.extend(["--exclude", "|".join(exclude)])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        if not output or not isinstance(output, str):
            return []
            
        findings = []
        # file:line:column: severity: message [error-code]
        # Example: src/models.py:12: error: Incompatible types... [assignment]
        pattern = re.compile(r"^(?P<file>.+?):(?P<line>\d+)(?P<column>:\d+)?: (?P<severity>\w+): (?P<message>.+?) \[(?P<code>.+)\]$")
        
        for line in output.splitlines():
            match = pattern.match(line)
            if match:
                sev_str = match.group("severity")
                code = match.group("code")
                
                # Default MEDIUM. Map no-untyped-def, no-untyped-call to HIGH.
                severity = Severity.MEDIUM
                if code in ("no-untyped-def", "no-untyped-call"):
                    severity = Severity.HIGH
                    
                findings.append(create_finding(
                    scanner=self.name,
                    rule_id=code,
                    file=match.group("file"),
                    line=int(match.group("line")),
                    column=0, # Simplified column
                    severity=severity,
                    category=self.category,
                    title=f"Mypy Error: {code}",
                    description=match.group("message"),
                    suggestion="Add type hints or fix type mismatch"
                ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # Mypy returns 1 if issues are found, 0 if clean
        if code > 1:
            await bus.publish_log("error", f"Mypy failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        findings = await self._filter_to_changed(findings, config.get("_file_filter"))
        await bus.publish_progress(self.name, 100, str(target))
        return findings
