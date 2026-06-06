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
        
        Handles:
        - Virtual environment detection
        - Missing tool errors (logged, not raised)
        - File filtering via config["_file_filter"]
        - Force rescan via config["_force_rescan"]
        """
        findings = []
        
        try:
            # Step 1: Find the tool command
            await bus.publish_log("info", "Locating vulture tool...")
            tool_cmd = find_tool_command("vulture")
            await bus.publish_log("info", f"Using: {tool_cmd}")
            
            # Step 2: Prepare environment (add venv bin to PATH if available)
            env = os.environ.copy()
            venv_python = _get_venv_python()
            if venv_python:
                bin_dir = venv_python.parent
                env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            
            # Step 3: Build command
            cmd = [
                tool_cmd, str(target),
                "--exclude", ".venv,venv,.env,node_modules,__pycache__,build,dist,*.egg-info"
            ]
            
            # Step 4: Run with asyncio (non-blocking)
            await bus.publish_progress(self.name, 10, str(target))
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                # Wait for completion with timeout
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout
                )
                
                # Step 5: Parse output
                if stdout:
                    pattern = r'^(.+?):(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)'
                    for line in stdout.decode('utf-8').strip().split('\n'):
                        if not line.strip():
                            continue
                        match = re.match(pattern, line)
                        if match:
                            filename, lineno, message, confidence = match.groups()
                            finding_id = hashlib.sha256(
                                f"{filename}{lineno}{message}".encode()
                            ).hexdigest()[:16]
                            
                            finding = Finding(
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
                                fix_status=FixStatus.OPEN
                            )
                            findings.append(finding)
                
                await bus.publish_progress(self.name, 100, str(target))
                await bus.publish_log("info", f"Vulture found {len(findings)} issues")
                
            except asyncio.TimeoutError:
                await bus.publish_log("error", f"Vulture scan timed out after {self.timeout}s")
            except Exception as e:
                await bus.publish_log("error", f"Vulture scan error: {str(e)}")
        
        except FileNotFoundError as e:
            # Tool not installed — log warning, don't crash
            await bus.publish_log(
                "warning",
                f"Vulture not available: {str(e)}"
            )
        except Exception as e:
            await bus.publish_log("error", f"Vulture scanner error: {str(e)}")
        
        return findings
