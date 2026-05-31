"""Bandit security scanner plugin."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from core.events import EventBus
from core.models import Category, Finding, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class BanditScanner(BaseScanner):
    """Bandit security scanner for Python."""

    name = "bandit"
    version = "1.0.0"
    languages = ["python"]
    category = Category.SECURITY
    requires_ai = False
    timeout = 120

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]:
        """Scan Python project with Bandit."""
        # Check if bandit is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "bandit",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code != 0:
                await bus.publish_log("warning", "bandit tool not found or unavailable")
                return []
        except FileNotFoundError:
            await bus.publish_log("warning", "bandit tool not installed")
            return []

        await bus.publish_progress("bandit", 0, "")

        # Build exclude list
        exclude_dirs = config.get("exclude_dirs", ["tests", "migrations", "venv", ".venv"])
        exclude_str = ",".join(exclude_dirs) if exclude_dirs else ""

        # Run bandit
        cmd = ["bandit", "-r", str(target), "-f", "json", "-q"]
        if exclude_str:
            cmd.extend(["--exclude", exclude_str])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            await bus.publish_log("warning", f"bandit timeout after {self.timeout}s")
            return []
        except Exception as e:
            await bus.publish_log("error", f"bandit failed: {e}")
            return []

        if proc.returncode not in (0, 1):  # Bandit returns 1 if issues found
            await bus.publish_log("warning", f"bandit exited with code {proc.returncode}")
            return []

        await bus.publish_progress("bandit", 50, "")

        # Parse JSON output
        findings: list[Finding] = []
        try:
            if stdout:
                data = json.loads(stdout.decode("utf-8"))
                for issue in data.get("results", []):
                    finding = self._parse_issue(issue, target)
                    if finding:
                        findings.append(finding)
        except json.JSONDecodeError as e:
            await bus.publish_log("warning", f"bandit JSON parse error: {e}")
            return []

        # Apply severity filter from config
        severity_filter = config.get("severity_filter", "low").lower()
        filter_map = {
            "low": {Severity.LOW, Severity.MEDIUM, Severity.HIGH},
            "medium": {Severity.MEDIUM, Severity.HIGH},
            "high": {Severity.HIGH},
        }
        allowed = filter_map.get(severity_filter, filter_map["low"])
        if severity_filter not in filter_map:
            await bus.publish_log("warning", f"Unknown severity_filter '{severity_filter}', defaulting to 'low'")
        findings = [f for f in findings if f.severity in allowed]

        await bus.publish_progress("bandit", 100, "")
        return findings

    def _parse_issue(self, issue: dict[str, Any], target: Path) -> Finding | None:
        """Convert Bandit JSON issue to Finding."""
        try:
            # Map severity
            severity_map = {
                "HIGH": Severity.HIGH,
                "MEDIUM": Severity.MEDIUM,
                "LOW": Severity.LOW,
            }
            severity = severity_map.get(issue.get("severity", "LOW"), Severity.LOW)

            # Get file path and make relative
            file_path_str = issue.get("filename", "")
            if file_path_str:
                try:
                    file_rel = str(Path(file_path_str).relative_to(target))
                except ValueError:
                    file_rel = file_path_str
            else:
                return None

            # Downgrade test file findings one level
            if "/test" in file_rel or "_test.py" in file_rel:
                if severity == Severity.HIGH:
                    severity = Severity.MEDIUM
                elif severity == Severity.MEDIUM:
                    severity = Severity.LOW

            title = issue.get("issue_text", "Security issue")
            confidence = issue.get("issue_confidence", "UNKNOWN")
            suggestion = issue.get("more_info", "")
            cwe = None
            if "issue_cwe" in issue and isinstance(issue["issue_cwe"], dict):
                cwe = issue["issue_cwe"].get("id")

            return Finding(
                scanner="bandit",
                file=file_rel,
                line=issue.get("line_number", 0),
                column=0,
                severity=severity,
                category=Category.SECURITY,
                title=title,
                description=f"Confidence: {confidence}. {title}",
                suggestion=suggestion or "Review and fix this security issue.",
                cwe=cwe,
                cvss_score=None,
            )
        except Exception as e:
            logger.warning(f"Error parsing bandit issue: {e}")
            return None
