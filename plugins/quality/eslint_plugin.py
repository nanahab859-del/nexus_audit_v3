import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class ESLintScanner(BaseScanner):
    name: ClassVar[str] = "eslint"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["javascript", "typescript"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "eslint"
    ecosystem: ClassVar[str] = "node"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        # Check for local installation handled by ToolResolver now
        # Check for config file
        has_config = any(target.glob(".eslintrc*")) or any(target.glob("eslint.config.*"))
        if not has_config:
            raise FileNotFoundError("No ESLint configuration file found")
            
        args = [str(target), "--format", "json", "--ext", ".js,.ts,.jsx,.tsx"]
        ignore = config.get("exclude_paths", [])
        for path in ignore:
            args.extend(["--ignore-pattern", path])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        try:
            data = json.loads(output) if isinstance(output, str) else output
        except json.JSONDecodeError:
            return []
            
        findings = []
        for file_obj in data if isinstance(data, list) else []:
            file_path = file_obj.get("filePath", "")
            for msg in file_obj.get("messages", []):
                sev = msg.get("severity", 1)
                severity = Severity.HIGH if sev == 2 else Severity.MEDIUM if sev == 1 else Severity.LOW
                
                findings.append(create_finding(
                    scanner=self.name, rule_id=msg.get("ruleId",""),
                    file=file_path, line=int(msg.get("line",0)), column=int(msg.get("column",0)),
                    severity=severity,
                    category=self.category,
                    title=msg.get("message","")[:100],
                    description=msg.get("message",""),
                    suggestion="Fix the ESLint violation",
                ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus): return []
        await bus.publish_progress(self.name, 0, str(target))
        try:
            args = await self._build_args(target, config)
        except FileNotFoundError as e:
            await bus.publish_log("warning", str(e))
            return []
            
        code, stdout, stderr = await self._run_tool(args, bus)
        # ESLint exit code 0=clean, 1=errors, 2=fatal
        if code > 1:
            await bus.publish_log("error", f"ESLint failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
