"""Radon cyclomatic complexity scanner plugin."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from core.events import EventBus
from core.models import Category, Finding, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class RadonScanner(BaseScanner):
    """Radon cyclomatic complexity analyzer."""

    name = "radon"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY
    requires_ai = False
    timeout = 60

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]:
        """Scan with Radon."""
        # Check if radon is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "radon",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code != 0:
                await bus.publish_log("warning", "radon tool not available")
                return []
        except FileNotFoundError:
            await bus.publish_log("warning", "radon tool not installed")
            return []

        await bus.publish_progress("radon", 0, "")

        min_rank = config.get("min_rank", "C")
        cmd = [
            "radon",
            "cc",
            str(target),
            "--json",
            "--min",
            min_rank,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            await bus.publish_log("warning", f"radon timeout after {self.timeout}s")
            return []
        except Exception as e:
            await bus.publish_log("error", f"radon failed: {e}")
            return []

        if proc.returncode not in (0, 1):
            await bus.publish_log("warning", f"radon exited with code {proc.returncode}")
            return []

        await bus.publish_progress("radon", 50, "")

        # Parse JSON output
        findings: list[Finding] = []
        try:
            if stdout:
                data = json.loads(stdout.decode("utf-8"))
                for file_path, functions in data.items():
                    for func_info in functions:
                        finding = self._parse_function(func_info, file_path, target)
                        if finding:
                            findings.append(finding)
        except json.JSONDecodeError as e:
            await bus.publish_log("warning", f"radon JSON parse error: {e}")
            return []

        await bus.publish_progress("radon", 100, "")
        return findings

    def _parse_function(
        self,
        func_info: dict[str, Any],
        file_path: str,
        target: Path,
    ) -> Finding | None:
        """Convert Radon function complexity to Finding."""
        try:
            rank = func_info.get("complexity", "C")
            complexity = func_info.get("classic_complexity", 0)
            name = func_info.get("name", "unknown")
            lineno = func_info.get("lineno", 0)

            # Map rank to severity
            severity_map = {
                "C": Severity.LOW,
                "D": Severity.MEDIUM,
                "E": Severity.HIGH,
                "F": Severity.HIGH,
            }
            severity = severity_map.get(rank, Severity.LOW)

            # Adjust for __init__ methods
            if name == "__init__" and rank in ("D", "E", "F"):
                # Downgrade one level for constructors
                if rank == "D":
                    severity = Severity.LOW
                elif rank in ("E", "F"):
                    severity = Severity.MEDIUM

            # Make path relative
            try:
                file_rel = str(Path(file_path).relative_to(target))
            except ValueError:
                file_rel = file_path

            return Finding(
                scanner="radon",
                file=file_rel,
                line=lineno,
                column=0,
                severity=severity,
                category=Category.QUALITY,
                title=f"High complexity in {name} (rank {rank}, score {complexity})",
                description=f"Cyclomatic complexity {complexity} — consider refactoring",
                suggestion="Break this function into smaller units or reduce branching",
                cwe=None,
                cvss_score=None,
            )
        except Exception as e:
            logger.warning(f"Error parsing radon function: {e}")
            return None
