import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class TruffleHogScanner(BaseScanner):
    name: ClassVar[str] = "trufflehog"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["*"]
    category: ClassVar[Category] = Category.SECURITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "trufflehog"
    ecosystem: ClassVar[str] = "binary"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        git_dir = target / ".git"
        if git_dir.exists():
            args = ["git", str(target), "--json"]
        else:
            args = ["filesystem", str(target), "--json"]
        args.append("--no-update")
        exclude = config.get("exclude_paths", [])
        for path in exclude:
            args.extend(["--exclude-paths", path])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        findings = []
        for line in output.splitlines():
            if not line.strip(): continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
                
            source = data.get("SourceMetadata", {}).get("Data", {})
            fs = source.get("Filesystem", {})
            filename = fs.get("filename", "") or source.get("Git", {}).get("commit", "")
            
            # The line number is usually within SourceMetadata/Data/Git
            line_no = int(data.get("SourceMetadata",{}).get("Data",{}).get("Git",{}).get("line", 0) or 0)
            
            findings.append(create_finding(
                scanner=self.name, 
                rule_id=data.get("DetectorName",""),
                file=filename, 
                line=line_no,
                column=0, 
                severity=Severity.HIGH, 
                category=self.category,
                title=f"Secret detected: {data.get('DetectorName','')}",
                description=f"Raw: {data.get('Raw','')[:100]}...",
                suggestion="Rotate this secret immediately",
            ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        if code != 0:
            await bus.publish_log("error", f"TruffleHog failed: {stderr[:200]}")
            return []
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
