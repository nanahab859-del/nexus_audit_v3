# plugins/generic_script_scanner.py
"""
GenericScriptScanner — wraps any external executable as a Nexus scanner.

Each custom scanner entry in settings.ui.custom_scanners is loaded by the
PluginRegistry and represented by an instance of this class.

Expected tool output format (one finding per line):
    SEVERITY:file/path.py:LINE:Message text here

Where SEVERITY is one of: CRITICAL, HIGH, MEDIUM, LOW, INFO (case-insensitive).
A custom regex can be provided via config["output_pattern"].
"""

from __future__ import annotations
import asyncio
import os
import re
import hashlib
from pathlib import Path
from typing import List, Optional

from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus


_DEFAULT_PATTERN = (
    r"^(?P<severity>CRITICAL|HIGH|MEDIUM|LOW|INFO):(?P<file>[^:]+):(?P<line>\d+):(?P<message>.+)$"
)

_SEVERITY_MAP = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH":     Severity.HIGH,
    "MEDIUM":   Severity.MEDIUM,
    "LOW":      Severity.LOW,
    "INFO":     Severity.INFO,
}


class GenericScriptScanner(BaseScanner):
    name     = "generic_script"   # overridden per instance
    version  = "1.0.0"
    languages: list[str] = ["*"]
    category = Category.QUALITY
    timeout  = 300
    is_internal = True

    def __init__(
        self,
        name: str,
        executable: str,
        output_pattern: Optional[str] = None,
    ):
        # Override class-level name so the registry key matches
        self.name           = name
        self.executable     = executable
        self.output_pattern = re.compile(
            output_pattern or _DEFAULT_PATTERN, re.IGNORECASE
        )

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        findings: List[Finding] = []

        await bus.publish_log("info", f"[{self.name}] Starting custom scanner…")
        await bus.publish_progress(self.name, 10, str(target))

        try:
            env = os.environ.copy()
            cmd = [self.executable, str(target)]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                await bus.publish_log(
                    "error", f"[{self.name}] Timed out after {self.timeout}s"
                )
                return findings

            output = (stdout or b"").decode(errors="replace")
            if stderr:
                await bus.publish_log(
                    "debug",
                    f"[{self.name}] stderr: {stderr.decode(errors='replace')[:200]}",
                )

            for raw_line in output.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                m = self.output_pattern.match(line)
                if not m:
                    continue

                groups = m.groupdict()
                severity_str = groups.get("severity", "MEDIUM").upper()
                severity = _SEVERITY_MAP.get(severity_str, Severity.MEDIUM)
                file_path = groups.get("file", "unknown")
                line_no = int(groups.get("line", 0))
                message = groups.get("message", line)

                fid = hashlib.sha256(
                    f"{self.name}{file_path}{line_no}{message}".encode()
                ).hexdigest()[:16]

                findings.append(
                    Finding(
                        id=fid,
                        scanner=self.name,
                        file=file_path,
                        line=line_no,
                        column=0,
                        severity=severity,
                        category=self.category,
                        title=f"[{self.name}] {message[:80]}",
                        description=message,
                        suggestion=f"Review finding from custom scanner '{self.name}'.",
                        persistence=Persistence.NEW,
                        fix_status=FixStatus.OPEN,
                    )
                )

        except FileNotFoundError:
            await bus.publish_log(
                "warning",
                f"[{self.name}] Executable not found: {self.executable}",
            )
        except Exception as exc:
            await bus.publish_log("error", f"[{self.name}] Error: {exc}")

        await bus.publish_progress(self.name, 100, str(target))
        await bus.publish_log("info", f"[{self.name}] Found {len(findings)} issues")
        return findings
