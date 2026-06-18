import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class DjLintScanner(BaseScanner):
    name: ClassVar[str] = "djlint"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["html"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "djlint"
    ecosystem: ClassVar[str] = "python"
    timeout: ClassVar[int] = 60

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        args = [str(target), "--lint", "--format=json", "--profile=django", "--extension", "html"]
        ignore = config.get("exclude_paths", [])
        for path in ignore:
            args.extend(["--ignore", path])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        try:
            data = json.loads(output) if isinstance(output, str) else output
        except json.JSONDecodeError:
            return []
            
        findings = []
        for item in data if isinstance(data, list) else []:
            findings.append(create_finding(
                scanner=self.name, rule_id=item.get("rule",""),
                file=item.get("file",""), line=int(item.get("line",0)), column=0,
                severity=Severity.MEDIUM, category=self.category,
                title=item.get("message","")[:100],
                description=item.get("message",""),
                suggestion="Fix the template issue",
            ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        # Exit codes: 0 = no issues, 1 = linting issues found, 2+ = fatal error
        if code > 1:
            await bus.publish_log("error", f"djLint failed (exit {code}): {stderr[:200]}")
            return []
        findings = self._parse_output(stdout)
        findings = await self._filter_to_changed(findings, config.get("_file_filter"))
        await bus.publish_progress(self.name, 100, str(target))
        return findings
