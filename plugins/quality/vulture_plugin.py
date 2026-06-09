import asyncio
import os
import sys
from pathlib import Path
from typing import List
import re
import hashlib

from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus, EventType
from core.python_exe import find_tool_command, _get_venv_python

class VultureScanner(BaseScanner):
    name = "vulture"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY
    timeout = 60

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Run Vulture dead code detector on Python files.

        Reads from config:
          - config["strictness"]       → "Low"|"Medium"|"High"
                                         maps to --min-confidence 40 / 60 / 80
          - config["exclude_paths"]    → list[str] or comma-str of globs to exclude
          - config["skip_checks"]      → list[str] of check IDs to skip in output
          - config["_force_rescan"]    → bool (unused by vulture itself)
        """
        findings = []

        try:
            await bus.publish_log("info", "Locating vulture tool...")
            tool_cmd = find_tool_command("vulture")
            await bus.publish_log("info", f"Using: {tool_cmd}")

            # Prepare environment
            env = os.environ.copy()
            venv_python = _get_venv_python()
            if venv_python:
                bin_dir = venv_python.parent
                env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

            # ── Config-driven exclusions ─────────────────────────────────
            base_excludes = [".venv", "venv", ".env", "node_modules", "__pycache__",
                             "build", "dist", "*.egg-info"]
            extra_excludes = config.get("exclude_paths", [])
            if isinstance(extra_excludes, str):
                extra_excludes = [p.strip() for p in extra_excludes.split(",") if p.strip()]
            all_excludes = base_excludes + list(extra_excludes)
            exclude_str = ",".join(all_excludes)

            # ── Strictness → --min-confidence ───────────────────────────
            strictness = str(config.get("strictness", "Medium")).capitalize()
            min_confidence = {
                "Low":    "40",
                "Medium": "60",
                "High":   "80",
            }.get(strictness, "60")

            # ── Skip check IDs (post-filter on finding descriptions) ─────
            skip_checks = config.get("skip_checks", [])
            if isinstance(skip_checks, str):
                skip_checks = [s.strip() for s in skip_checks.split(",") if s.strip()]
            skip_set = set(skip_checks)

            # Build command
            cmd = [
                tool_cmd, str(target),
                "--exclude", exclude_str,
                "--min-confidence", min_confidence,
            ]

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
                    pattern = r"^(.+?):(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)"
                    for line in stdout.decode("utf-8").strip().split("\n"):
                        if not line.strip():
                            continue
                        match = re.match(pattern, line)
                        if not match:
                            continue
                        filename, lineno, message, confidence = match.groups()

                        # Skip user-requested check IDs
                        if any(skip in message for skip in skip_set):
                            continue

                        finding_id = hashlib.sha256(
                            f"{filename}{lineno}{message}".encode()
                        ).hexdigest()[:16]

                        findings.append(Finding(
                            id=finding_id,
                            scanner=self.name,
                            file=filename,
                            line=int(lineno),
                            column=0,
                            severity=Severity.LOW,
                            category=Category.QUALITY,
                            title="Dead code detected",
                            description=message,
                            suggestion="Remove unused code or implement functionality",
                            persistence=Persistence.NEW,
                            fix_status=FixStatus.OPEN,
                        ))

                await bus.publish_progress(self.name, 100, str(target))
                await bus.publish_log("info", f"Vulture found {len(findings)} issues")

            except asyncio.TimeoutError:
                await bus.publish_log("error", f"Vulture scan timed out after {self.timeout}s")
            except Exception as e:
                await bus.publish_log("error", f"Vulture scan error: {e}")

        except FileNotFoundError as e:
            await bus.publish_log("warning", f"Vulture not available: {e}")
        except Exception as e:
            await bus.publish_log("error", f"Vulture scanner error: {e}")

        return findings
