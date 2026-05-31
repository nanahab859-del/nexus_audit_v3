"""pip-audit dependency vulnerability scanner plugin."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from core.events import EventBus
from core.models import Category, Finding, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class SafetyScanner(BaseScanner):
    """pip-audit dependency vulnerability detector."""

    name = "safety"
    version = "1.0.0"
    languages = ["python"]
    category = Category.DEPENDENCY
    requires_ai = False
    timeout = 120

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]:
        """Scan with pip-audit."""
        # Check if pip-audit is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "pip-audit",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code != 0:
                await bus.publish_log("warning", "pip-audit tool not available")
                return []
        except FileNotFoundError:
            await bus.publish_log("warning", "pip-audit tool not installed")
            return []

        await bus.publish_progress("safety", 0, "")

        # Look for requirements file
        req_file = self._find_requirements_file(target)
        if not req_file:
            await bus.publish_log("info", "No requirements file found (requirements.txt, pyproject.toml, setup.py)")
            return []

        cmd = ["pip-audit", "--format", "json"]
        if req_file.name == "requirements.txt":
            cmd.extend(["--requirement", str(req_file)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            await bus.publish_log("warning", f"pip-audit timeout after {self.timeout}s")
            return []
        except Exception as e:
            await bus.publish_log("error", f"pip-audit failed: {e}")
            return []

        if proc.returncode not in (0, 1):
            await bus.publish_log("warning", f"pip-audit exited with code {proc.returncode}")
            return []

        await bus.publish_progress("safety", 50, "")

        # Parse JSON output
        findings: list[Finding] = []
        try:
            if stdout:
                data = json.loads(stdout.decode("utf-8"))
                for vuln in data.get("vulnerabilities", []):
                    finding = self._parse_vulnerability(vuln)
                    if finding:
                        findings.append(finding)
        except json.JSONDecodeError as e:
            await bus.publish_log("warning", f"pip-audit JSON parse error: {e}")
            return []

        await bus.publish_progress("safety", 100, "")
        return findings

    def _find_requirements_file(self, target: Path) -> Path | None:
        """Find a requirements file in target directory."""
        candidates = [
            target / "requirements.txt",
            target / "pyproject.toml",
            target / "setup.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _parse_vulnerability(self, vuln: dict[str, Any]) -> Finding | None:
        """Convert pip-audit JSON vulnerability to Finding."""
        try:
            package = vuln.get("name", "unknown")
            installed = vuln.get("installed_version", "unknown")
            fix_versions = vuln.get("fix_versions", [])
            description = vuln.get("description", "")
            cve_id = None
            cvss_score = None

            # Extract CVE and CVSS if available
            aliases = vuln.get("aliases", [])
            for alias in aliases:
                if alias.startswith("CVE-"):
                    cve_id = alias
                    break

            # Determine severity based on fix availability
            if fix_versions:
                severity = Severity.HIGH
                fix_msg = f"Upgrade to {fix_versions[0]}"
            else:
                severity = Severity.MEDIUM
                fix_msg = "No fix available — consider replacing this dependency"

            return Finding(
                scanner="safety",
                file="",  # Dependencies not tied to specific file
                line=0,
                column=0,
                severity=severity,
                category=Category.DEPENDENCY,
                title=f"{package} {installed} has known vulnerability",
                description=description,
                suggestion=fix_msg,
                cwe=None,
                cvss_score=cvss_score,
            )
        except Exception as e:
            logger.warning(f"Error parsing pip-audit vulnerability: {e}")
            return None
