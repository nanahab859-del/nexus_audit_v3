import csv
import io
from pathlib import Path
from typing import ClassVar, List, Any, Optional

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class LizardScanner(BaseScanner):
    name: ClassVar[str] = "lizard"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python", "javascript", "typescript", "java", "c", "cpp", "go"]
    category: ClassVar[Category] = Category.ARCHITECTURE
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = "lizard"
    timeout: ClassVar[int] = 120

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        langs = config.get("languages", self.languages)
        args = [str(target), "--csv"]
        for lang in langs:
            args.extend(["-l", lang])
        return args

    def _parse_output(self, output: Any, config: Optional[dict] = None) -> List[Finding]:
        config = config or {}
        loc_high = config.get("loc_threshold_high", 100)
        loc_med = config.get("loc_threshold_medium", 50)
        param_high = config.get("param_threshold_high", 7)
        param_med = config.get("param_threshold_medium", 5)
        
        findings = []
        if not output or not isinstance(output, str):
            return []
            
        # Lizard CSV format: NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end
        f = io.StringIO(output)
        # Using the researched field names
        reader = csv.DictReader(f, fieldnames=["nloc", "complexity", "token_count", "parameters", "length", "location", "file", "function", "long_name", "start", "end"])
        
        for row in reader:
            try:
                # Skip header if it exists
                if row["nloc"] == "NLOC":
                    continue
                    
                loc = int(row.get("nloc", 0))
                params = int(row.get("parameters", 0))
                
                sev = None
                if loc > loc_high or params > param_high:
                    sev = Severity.HIGH
                elif loc > loc_med or params > param_med:
                    sev = Severity.MEDIUM
                elif loc > 30:
                    sev = Severity.LOW
                
                if sev:
                    findings.append(create_finding(
                        scanner=self.name,
                        rule_id="lizard-threshold",
                        file=row.get("file", ""),
                        line=int(row.get("start", 0)),
                        column=0,
                        severity=sev,
                        category=self.category,
                        title=f"Function '{row.get('function','')}' exceeds metric thresholds",
                        description=f"LOC={loc}, params={params}",
                        suggestion="Consider splitting this function or reducing parameters",
                    ))
            except (ValueError, TypeError):
                continue
                
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        if not await self._check_tool(bus):
            return []
            
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        code, stdout, stderr = await self._run_tool(args, bus)
        
        if code != 0:
            await bus.publish_log("error", f"Lizard failed: {stderr[:200]}")
            return []
            
        findings = self._parse_output(stdout, config)
        await bus.publish_progress(self.name, 100, str(target))
        return findings
