import json
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class SemgrepScanner(BaseScanner):
    name: ClassVar[str] = "semgrep"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["*"]
    category: ClassVar[Category] = Category.SECURITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "semgrep"
    timeout: ClassVar[int] = 180

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        rules_path = config.get("rules_path", "p/python,p/security-audit,p/secrets")
        extra = config.get("extra_rules", [])
        all_rules = [rules_path] + extra
        args = ["--config", ",".join(all_rules), str(target), "--json", "--quiet"]
        exclude = config.get("exclude_paths", [])
        for path in exclude:
            args.extend(["--exclude", path])
        return args

    def _parse_output(self, output: Any) -> List[Finding]:
        data = json.loads(output) if isinstance(output, str) else output
        findings = []
        severity_map = {
            "ERROR": Severity.HIGH,
            "WARNING": Severity.MEDIUM,
            "INFO": Severity.LOW
        }
        
        results = data.get("results", []) if isinstance(data, dict) else []
        for result in results:
            extra = result.get("extra", {})
            findings.append(create_finding(
                scanner=self.name,
                rule_id=result.get("check_id", ""),
                file=result.get("path", ""),
                line=result.get("start", {}).get("line", 0),
                column=result.get("start", {}).get("col", 0),
                severity=severity_map.get(extra.get("severity", ""), Severity.LOW),
                category=self.category,
                title=result.get("check_id", ""),
                description=extra.get("message", ""),
                suggestion=extra.get("fix", ""),
            ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus):
            return []
            
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # Semgrep returns 0 if no findings, or 1 if findings found (depending on flags).
        # We check stderr for actual failures.
        if code not in (0, 1) and stderr:
            await bus.publish_log("error", f"Semgrep failed (exit {code}): {stderr[:200]}")
            # Some versions of semgrep return 1 even for valid scans with findings.
            # If we have stdout, we might still want to parse it.
            if not stdout:
                return []
                
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
