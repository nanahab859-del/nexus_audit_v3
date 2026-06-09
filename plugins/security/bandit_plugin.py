import asyncio
import os
import sys
from pathlib import Path
from typing import List
import json
import hashlib

from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus, EventType
from core.python_exe import find_tool_command, _get_venv_python

class BanditScanner(BaseScanner):
    name = "bandit"
    version = "1.0.0"
    languages = ["python"]
    category = Category.SECURITY
    timeout = 60

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Run Bandit security scanner on Python files.

        Reads from config:
          - config["strictness"]       → "Low"|"Medium"|"High"  (→ -l / -ll / -lll)
          - config["exclude_paths"]    → list[str] or comma-str of paths to exclude
          - config["skip_checks"]      → list[str] of Bandit test IDs to skip (e.g. B101)
          - config["_force_rescan"]    → bool (currently unused by bandit itself)
        """
        findings = []

        try:
            await bus.publish_log("info", "Locating bandit tool...")
            tool_cmd = find_tool_command("bandit")
            await bus.publish_log("info", f"Using: {tool_cmd}")

            # Prepare environment
            env = os.environ.copy()
            venv_python = _get_venv_python()
            if venv_python:
                bin_dir = venv_python.parent
                env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

            # ── Config-driven exclusions ─────────────────────────────────
            base_excludes = [".venv", "venv", ".env", "node_modules", "build", "dist"]
            extra_excludes = config.get("exclude_paths", [])
            if isinstance(extra_excludes, str):
                extra_excludes = [p.strip() for p in extra_excludes.split(",") if p.strip()]
            all_excludes = base_excludes + list(extra_excludes)
            exclude_str = ",".join(all_excludes)

            # ── Strictness → confidence level flags ──────────────────────
            strictness = str(config.get("strictness", "Medium")).capitalize()
            level_flags: list[str] = {
                "Low":    ["-l"],
                "Medium": ["-ll"],
                "High":   ["-lll"],
            }.get(strictness, ["-ll"])

            # ── Skip checks ──────────────────────────────────────────────
            skip_checks = config.get("skip_checks", [])
            if isinstance(skip_checks, str):
                skip_checks = [s.strip() for s in skip_checks.split(",") if s.strip()]
            skip_flags: list[str] = []
            if skip_checks:
                skip_flags = ["--skip", ",".join(skip_checks)]

            # Build command
            cmd = (
                [tool_cmd, "-r", str(target)]
                + level_flags
                + ["-x", exclude_str]
                + skip_flags
                + ["-f", "json", "-q"]
            )

            await bus.publish_progress(self.name, 10, str(target))

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )

                if stdout:
                    try:
                        data = json.loads(stdout.decode("utf-8"))
                        issues = data.get("results", [])
                        await bus.publish_log("info", f"Bandit found {len(issues)} issues")

                        for issue in issues:
                            severity_map = {
                                "HIGH":   Severity.HIGH,
                                "MEDIUM": Severity.MEDIUM,
                                "LOW":    Severity.LOW,
                            }
                            finding_id = hashlib.sha256(
                                f"{issue.get('filename')}{issue.get('line_number')}{issue.get('test_id')}".encode()
                            ).hexdigest()[:16]

                            findings.append(Finding(
                                id=finding_id,
                                scanner=self.name,
                                file=issue.get("filename", "unknown"),
                                line=issue.get("line_number", 0),
                                column=0,
                                severity=severity_map.get(
                                    issue.get("severity", "LOW"), Severity.MEDIUM
                                ),
                                category=Category.SECURITY,
                                title=issue.get("issue_text", "Security issue"),
                                description=issue.get("issue_cwe", {}).get(
                                    "id", issue.get("issue_text", "Security issue detected")
                                ),
                                suggestion=f"See Bandit test {issue.get('test_id')} documentation",
                                cwe=issue.get("issue_cwe", {}).get("id"),
                                persistence=Persistence.NEW,
                                fix_status=FixStatus.OPEN,
                            ))

                    except json.JSONDecodeError as e:
                        await bus.publish_log("warning", f"Bandit JSON parse error: {e}")
                else:
                    await bus.publish_log("info", "Bandit completed with no output")

                await bus.publish_progress(self.name, 100, str(target))

            except asyncio.TimeoutError:
                await bus.publish_log("error", f"Bandit scan timed out after {self.timeout}s")
            except Exception as e:
                await bus.publish_log("error", f"Bandit scan error: {e}")

        except FileNotFoundError as e:
            await bus.publish_log("warning", f"Bandit not available: {e}")
        except Exception as e:
            await bus.publish_log("error", f"Bandit scanner error: {e}")

        return findings
