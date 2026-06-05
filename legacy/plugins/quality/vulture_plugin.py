"""Vulture dead code scanner plugin."""

from typing import Any
import asyncio
import logging
import re
from pathlib import Path

from core.events import EventBus
from core.models import Category, Finding, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class VultureScanner(BaseScanner):
    """Vulture dead code detector."""

    name = "vulture"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY
    requires_ai = False
    timeout = 60

    async def scan(
        self,
        target: Path,
        config: dict[str, Any],
        bus: EventBus,
    ) -> list[Finding]:
        """Scan with Vulture."""
        # Check if vulture is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "vulture",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code != 0:
                await bus.publish_log("warning", "vulture tool not available")
                return []
        except FileNotFoundError:
            await bus.publish_log("warning", "vulture tool not installed")
            return []

        await bus.publish_progress("vulture", 0, "")

        min_confidence = config.get("min_confidence", 60)
        cmd = ["vulture", str(target), "--min-confidence", str(min_confidence)]

        # Add whitelist file if provided
        whitelist_path = config.get("whitelist_path")
        if whitelist_path:
            whitelist = Path(whitelist_path)
            if whitelist.exists():
                cmd.append(str(whitelist))
            else:
                await bus.publish_log(
                    "warning",
                    f"Vulture whitelist_path '{whitelist_path}' does not exist — ignored"
                )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            await bus.publish_log("warning", f"vulture timeout after {self.timeout}s")
            return []
        except Exception as e:
            await bus.publish_log("error", f"vulture failed: {e}")
            return []

        if proc.returncode not in (0, 1):
            await bus.publish_log("warning", f"vulture exited with code {proc.returncode}")
            return []

        await bus.publish_progress("vulture", 50, "")

        # Parse line-by-line output
        findings: list[Finding] = []
        if stdout:
            for line in stdout.decode("utf-8").splitlines():
                finding = self._parse_line(line, target)
                if finding:
                    findings.append(finding)

        await bus.publish_progress("vulture", 100, "")
        return findings

    def _parse_line(self, line: str, target: Path) -> Finding | None:
        """
        Parse vulture output line.
        Format: {file}:{line}: {message} ({confidence}% confidence)
        """
        try:
            # Match pattern: file:line: message (N% confidence)
            match = re.match(
                r"^(.+?):(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)$",
                line.strip(),
            )
            if not match:
                return None

            file_path, line_no, message, confidence = match.groups()

            # Make path relative
            try:
                file_rel = str(Path(file_path).relative_to(target))
            except ValueError:
                file_rel = file_path

            return Finding(
                scanner="vulture",
                file=file_rel,
                line=int(line_no),
                column=0,
                severity=Severity.LOW,
                category=Category.QUALITY,
                title=message,
                description=f"{confidence}% confidence this code is unused",
                suggestion="Remove this code or add a # noqa comment if intentional",
                cwe=None,
                cvss_score=None,
            )
        except Exception as e:
            logger.warning(f"Error parsing vulture line: {e}")
            return None
