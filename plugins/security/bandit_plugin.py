import json
from pathlib import Path
from typing import ClassVar, List, Any
from plugins.base import BaseScanner
from core.primitives.models import Category, Severity, create_finding, Finding

class BanditScanner(BaseScanner):
    name: ClassVar[str] = "bandit"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.SECURITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "bandit"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        args = ["-r", str(target), "-f", "json", "-q"]
        strictness = config.get("strictness", "medium")
        if strictness == "high":
            args.insert(1, "-lll")
        elif strictness == "low":
            args.insert(1, "-l")
        
        exclude = config.get("exclude_paths", [])
        if exclude:
            args.extend(["-x", ",".join(exclude)])
            
        skip = config.get("skip_checks", [])
        if skip:
            args.extend(["--skip"] + skip)
            
        return args

    def _parse_output(self, output: str) -> List[Finding]:
        findings = []
        try:
            data = json.loads(output)
            for res in data.get("results", []):
                # Map Bandit severity to our Enum
                sev_str = res.get("issue_severity", "MEDIUM")
                severity = Severity.MEDIUM
                if sev_str == "HIGH":
                    severity = Severity.HIGH
                elif sev_str == "LOW":
                    severity = Severity.LOW
                
                findings.append(create_finding(
                    scanner=self.name,
                    rule_id=res.get("test_id", "unknown"),
                    file=res.get("filename", ""),
                    line=int(res.get("line_number", 0)),
                    column=int(res.get("col_offset", 0)),
                    severity=severity,
                    category=Category.SECURITY,
                    title=res.get("test_name", "Bandit Finding"),
                    description=res.get("issue_text", ""),
                    suggestion=res.get("more_info", ""),
                    cwe=res.get("issue_cwe", {}).get("id") if isinstance(res.get("issue_cwe"), dict) else None
                ))
        except (json.JSONDecodeError, ValueError):
            pass
        return findings

    async def scan(self, target: Path, config: dict, bus: Any) -> List[Finding]:
        if not await self._check_tool(bus):
            return []
            
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        # Bandit returns 1 if findings found, 0 otherwise
        if code != 0 and code != 1:
            await bus.publish_log("error", f"Bandit failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
