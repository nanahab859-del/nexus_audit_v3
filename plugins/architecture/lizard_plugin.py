"""Lizard code structure metrics scanner plugin."""

import asyncio
import csv
import io
import logging
from pathlib import Path

from core.events import EventBus
from core.models import Category, Finding, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class LizardScanner(BaseScanner):
    """Lizard code structure analyzer."""

    name = "lizard"
    version = "1.0.0"
    languages = ["python", "javascript", "typescript", "java", "cpp", "c", "go"]
    category = Category.ARCHITECTURE
    requires_ai = False
    timeout = 120

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]:
        """Scan with Lizard."""
        # Check if lizard is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "lizard",
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            code = await proc.wait()
            if code != 0:
                await bus.publish_log("warning", "lizard tool not available")
                return []
        except FileNotFoundError:
            await bus.publish_log("warning", "lizard tool not installed")
            return []

        await bus.publish_progress("lizard", 0, "")

        # Build language list
        lang_args: list[str] = []
        for lang in self.languages:
            if lang != "typescript":  # typescript is handled as javascript in lizard
                lang_args.extend(["-l", lang])

        cmd = ["lizard", str(target), "--csv"] + lang_args

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            await bus.publish_log("warning", f"lizard timeout after {self.timeout}s")
            return []
        except Exception as e:
            await bus.publish_log("error", f"lizard failed: {e}")
            return []

        if proc.returncode not in (0, 1):
            await bus.publish_log("warning", f"lizard exited with code {proc.returncode}")
            return []

        await bus.publish_progress("lizard", 50, "")

        # Parse CSV output
        findings: list[Finding] = []
        thresholds = {
            "loc_high": config.get("loc_threshold_high", 100),
            "loc_medium": config.get("loc_threshold_medium", 50),
            "param_high": config.get("param_threshold_high", 7),
            "param_medium": config.get("param_threshold_medium", 5),
        }

        try:
            if stdout:
                reader = csv.DictReader(io.StringIO(stdout.decode("utf-8")))
                if reader:
                    for row in reader:
                        new_findings = self._parse_row(row, target, thresholds)
                        findings.extend(new_findings)
        except Exception as e:
            logger.warning(f"lizard CSV parse error: {e}")
            return []

        await bus.publish_progress("lizard", 100, "")
        return findings

    def _parse_row(
        self,
        row: dict[str, str],
        target: Path,
        thresholds: dict,
    ) -> list[Finding]:
        """
        Parse lizard CSV row and generate Findings for violations.
        One row can generate multiple Findings if multiple thresholds exceeded.
        """
        findings: list[Finding] = []

        try:
            file_path = row.get("file", "")
            func_name = row.get("function", "")
            loc = int(row.get("LOC", "0"))
            params = int(row.get("parameter count", "0"))
            tokens = int(row.get("token count", "0"))
            complexity = int(row.get("cyclomatic complexity", "0"))
            lineno = int(row.get("start line", "0"))

            # Skip if no function name (summary rows)
            if not func_name or func_name == "function":
                return []

            # Make path relative
            try:
                file_rel = str(Path(file_path).relative_to(target))
            except ValueError:
                file_rel = file_path

            # Check LOC thresholds
            if loc > thresholds["loc_high"]:
                findings.append(
                    Finding(
                        scanner="lizard",
                        file=file_rel,
                        line=lineno,
                        column=0,
                        severity=Severity.HIGH,
                        category=Category.ARCHITECTURE,
                        title=f"Function '{func_name}' exceeds LOC threshold ({loc} > {thresholds['loc_high']})",
                        description=f"LOC={loc}, params={params}, tokens={tokens}, complexity={complexity}",
                        suggestion="Consider splitting this function or reducing its responsibilities",
                        cwe=None,
                        cvss_score=None,
                    )
                )
            elif loc > thresholds["loc_medium"]:
                findings.append(
                    Finding(
                        scanner="lizard",
                        file=file_rel,
                        line=lineno,
                        column=0,
                        severity=Severity.MEDIUM,
                        category=Category.ARCHITECTURE,
                        title=f"Function '{func_name}' exceeds LOC threshold ({loc} > {thresholds['loc_medium']})",
                        description=f"LOC={loc}, params={params}, tokens={tokens}, complexity={complexity}",
                        suggestion="Consider splitting this function or reducing its responsibilities",
                        cwe=None,
                        cvss_score=None,
                    )
                )

            # Check parameter thresholds
            if params > thresholds["param_high"]:
                findings.append(
                    Finding(
                        scanner="lizard",
                        file=file_rel,
                        line=lineno,
                        column=0,
                        severity=Severity.HIGH,
                        category=Category.ARCHITECTURE,
                        title=f"Function '{func_name}' has too many parameters ({params} > {thresholds['param_high']})",
                        description=f"LOC={loc}, params={params}, tokens={tokens}, complexity={complexity}",
                        suggestion="Reduce the number of parameters by using data classes or configuration objects",
                        cwe=None,
                        cvss_score=None,
                    )
                )
            elif params > thresholds["param_medium"]:
                findings.append(
                    Finding(
                        scanner="lizard",
                        file=file_rel,
                        line=lineno,
                        column=0,
                        severity=Severity.MEDIUM,
                        category=Category.ARCHITECTURE,
                        title=f"Function '{func_name}' has too many parameters ({params} > {thresholds['param_medium']})",
                        description=f"LOC={loc}, params={params}, tokens={tokens}, complexity={complexity}",
                        suggestion="Reduce the number of parameters by using data classes or configuration objects",
                        cwe=None,
                        cvss_score=None,
                    )
                )

        except (ValueError, KeyError) as e:
            logger.warning(f"Error parsing lizard row: {e}")

        return findings
