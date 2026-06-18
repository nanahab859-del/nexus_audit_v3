import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class RadonScanner(BaseScanner):
    name: ClassVar[str] = "radon"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "radon"
    timeout: ClassVar[int] = 60

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        min_rank = config.get("min_rank", "C")
        return ["cc", str(target), "--json", "--min", min_rank]

    def _parse_output(self, output: Any) -> List[Finding]:
        data = json.loads(output) if isinstance(output, str) else output
        findings = []
        rank_map = {
            "C": Severity.LOW,
            "D": Severity.MEDIUM,
            "E": Severity.HIGH,
            "F": Severity.HIGH
        }
        
        if not isinstance(data, dict):
            return []
            
        for file_path, blocks in data.items():
            for block in blocks:
                rank = block.get("rank", "C")
                if rank in rank_map:
                    findings.append(create_finding(
                        scanner=self.name,
                        rule_id=f"radon-{rank}",
                        file=file_path,
                        line=block.get("lineno", 0),
                        column=block.get("col_offset", 0),
                        severity=rank_map[rank],
                        category=self.category,
                        title=f"High complexity in {block.get('name', 'unknown')}",
                        description=f"Cyclomatic complexity: {block.get('complexity', 0)} (rank {rank})",
                        suggestion="Refactor into smaller functions",
                    ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus):
            return []
            
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        if code != 0:
            await bus.publish_log("error", f"Radon failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
