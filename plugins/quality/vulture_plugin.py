from pathlib import Path
from typing import ClassVar, List, Any
from plugins.base import BaseScanner
from core.primitives.models import Category, Severity, create_finding, Finding

class VultureScanner(BaseScanner):
    name: ClassVar[str] = "vulture"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "vulture"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        # Vulture needs min-confidence. Default to 60.
        min_conf = config.get("min_confidence", 60)
        return [str(target), "--min-confidence", str(min_conf)]

    def _parse_output(self, output: str) -> List[Finding]:
        findings = []
        # Expected format: "file:line: message (confidence%)"
        for line in output.splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            
            file_path, line_no, message = parts
            
            findings.append(create_finding(
                scanner=self.name,
                rule_id="dead-code",
                file=file_path.strip(),
                line=int(line_no.strip()),
                column=1,
                severity=Severity.LOW,
                category=Category.QUALITY,
                title="Dead code detected",
                description=message.strip(),
                suggestion="Remove unused code"
            ))
        return findings

    async def scan(self, target: Path, config: dict, bus: Any) -> List[Finding]:
        if not await self._check_tool(bus):
            return []
            
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # Vulture returns 0 if nothing found, 1 if findings found
        if code > 1:
            await bus.publish_log("error", f"Vulture failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        findings = await self._filter_to_changed(findings, config.get("_file_filter"))
        await bus.publish_progress(self.name, 100, str(target))
        return findings
