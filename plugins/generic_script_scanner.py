import asyncio
import re
from pathlib import Path
from typing import ClassVar, List, Any, Tuple

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class GenericScriptScanner(BaseScanner):
    name: ClassVar[str] = "generic_script"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["*"]
    category: ClassVar[Category] = Category.QUALITY
    requires_tool: ClassVar[bool] = True
    tool_name: ClassVar[str] = ""
    ecosystem: ClassVar[str] = "binary"
    timeout: ClassVar[int] = 300
    is_internal: ClassVar[bool] = True

    def __init__(self, config: dict, bus):
        super().__init__(config, bus)
        self._executable: str = ""

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        args = config.get("args", [])
        args.append(str(target))
        return args

    def _parse_output(self, output: Any, config: dict = None) -> List[Finding]:
        config = config or {}
        fmt = config.get("output_format", "line")
        findings = []
        
        if not output or not isinstance(output, str):
            return []
            
        if fmt == "line":
            for line in output.splitlines():
                if not line.strip(): continue
                # SEVERITY:file:line:message
                parts = line.split(":", 3)
                if len(parts) >= 4:
                    sev_str, file, line_no, msg = parts[0], parts[1], parts[2], parts[3]
                    sev_map = {"CRITICAL":Severity.CRITICAL,"HIGH":Severity.HIGH,"MEDIUM":Severity.MEDIUM,"LOW":Severity.LOW,"INFO":Severity.INFO}
                    findings.append(create_finding(
                        scanner=self.name, rule_id="custom-script",
                        file=file, line=int(line_no), column=0,
                        severity=sev_map.get(sev_str.upper(), Severity.MEDIUM),
                        category=self.category, title=msg[:100], description=msg,
                    ))
        elif fmt == "regex":
            pattern = config.get("parse_pattern")
            if pattern:
                for match in re.finditer(pattern, output, re.MULTILINE):
                    groups = match.groupdict()
                    sev = groups.get("severity","MEDIUM").upper()
                    sev_map = {"CRITICAL":Severity.CRITICAL,"HIGH":Severity.HIGH,"MEDIUM":Severity.MEDIUM,"LOW":Severity.LOW,"INFO":Severity.INFO}
                    findings.append(create_finding(
                        scanner=self.name, rule_id="custom-script",
                        file=groups.get("file",""), line=int(groups.get("line",0)), column=0,
                        severity=sev_map.get(sev, Severity.MEDIUM),
                        category=self.category,
                        title=groups.get("message","")[:100],
                        description=groups.get("message",""),
                    ))
        return findings

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        executable = config.get("executable")
        if not executable:
            await bus.publish_log("error", "GenericScriptScanner: No executable configured")
            return []
        
        # Store executable in instance variable (not ClassVar shadow)
        self._executable = executable
        
        await bus.publish_progress(self.name, 0, str(target))
        args = await self._build_args(target, config)
        
        # Run the dynamic executable
        code, stdout, stderr = await self._run_dynamic_tool(executable, args, bus)
        
        if code != 0:
            await bus.publish_log("error", f"Custom script failed: {stderr[:200]}")
        
        findings = self._parse_output(stdout, config)
        await bus.publish_progress(self.name, 100, str(target))
        return findings

    async def _run_dynamic_tool(
        self, executable: str, args: List[str], bus: EventBus
    ) -> Tuple[int, str, str]:
        """Run a dynamically-specified executable."""
        try:
            resolved = await self.resolver.resolve(executable, self.ecosystem)
            full_cmd = resolved + args
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            return proc.returncode, stdout.decode(errors="ignore"), stderr.decode(errors="ignore")
        except asyncio.TimeoutError:
            try:
                proc.terminate()
                await proc.wait()
            except:
                pass
            return 1, "", "Timeout exceeded"
        except Exception as e:
            return 1, "", str(e)
