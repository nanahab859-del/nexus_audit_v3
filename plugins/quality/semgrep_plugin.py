"""Semgrep multi-language security scanner plugin."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from core.events import EventBus
from core.models import Category, Finding, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class SemgrepScanner(BaseScanner):
    """Semgrep multi-language static analysis scanner."""

    name = "semgrep"
    version = "1.0.0"
    languages = ["*"]
    category = Category.SECURITY
    requires_ai = False
    timeout = 180

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]:
        """Scan with Semgrep."""
        # Check if semgrep is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "semgrep",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code != 0:
                await bus.publish_log("warning", "semgrep tool not available")
                return []
        except FileNotFoundError:
            await bus.publish_log("warning", "semgrep tool not installed")
            return []

        await bus.publish_progress("semgrep", 0, "")

        # Build ruleset
        rules_path = config.get("rules_path", None)
        extra_rules = config.get("extra_rules", [])

        # Build the --config argument list
        configs = []
        if rules_path:
            configs.append(rules_path)
        else:
            configs.extend(["p/python", "p/security-audit"])

        for rule in extra_rules:
            configs.append(rule)

        # Build CLI args: semgrep --config X --config Y --config Z
        config_args = []
        for c in configs:
            config_args.extend(["--config", c])

        cmd = [
            "semgrep",
            *config_args,
            str(target),
            "--json",
            "--quiet",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            await bus.publish_log("warning", f"semgrep timeout after {self.timeout}s")
            return []
        except Exception as e:
            await bus.publish_log("error", f"semgrep failed: {e}")
            return []

        if proc.returncode not in (0, 1):
            await bus.publish_log("warning", f"semgrep exited with code {proc.returncode}")
            return []

        # Semgrep JSON output is atomic — no per-file progress available.
        # Coarse 0%/100% lifecycle events are emitted instead.
        # Parse JSON output
        findings: list[Finding] = []
        try:
            if stdout:
                data = json.loads(stdout.decode("utf-8"))
                for result in data.get("results", []):
                    finding = self._parse_result(result, target)
                    if finding:
                        findings.append(finding)
        except json.JSONDecodeError as e:
            logger.warning(f"semgrep JSON parse error: {e}")
            return []

        await bus.publish_progress("semgrep", 100, "")
        return findings

    def _parse_result(self, result: dict[str, Any], target: Path) -> Finding | None:
        """Convert Semgrep JSON result to Finding."""
        try:
            # Map severity
            extra = result.get("extra", {})
            severity_str = extra.get("severity", "INFO")
            severity_map = {
                "ERROR": Severity.HIGH,
                "WARNING": Severity.MEDIUM,
                "INFO": Severity.LOW,
            }
            severity = severity_map.get(severity_str, Severity.LOW)

            # Get file path and make relative
            file_path = result.get("path", "")
            if file_path:
                try:
                    file_rel = str(Path(file_path).relative_to(target))
                except ValueError:
                    file_rel = file_path
            else:
                return None

            # Get check ID (rule name)
            check_id = result.get("check_id", "semgrep")
            message = extra.get("message", "Issue found")
            suggestion = extra.get("fix", None)

            # Get CWE if available
            cwe = None
            metadata = extra.get("metadata", {})
            cwe_list = metadata.get("cwe", [])
            if cwe_list:
                cwe = cwe_list[0]

            return Finding(
                scanner="semgrep",
                file=file_rel,
                line=result.get("start", {}).get("line", 0),
                column=result.get("start", {}).get("col", 0),
                severity=severity,
                category=Category.SECURITY,
                title=check_id,
                description=message,
                suggestion=suggestion or "Review and fix this issue",
                cwe=cwe,
                cvss_score=None,
            )
        except Exception as e:
            logger.warning(f"Error parsing semgrep result: {e}")
            return None
