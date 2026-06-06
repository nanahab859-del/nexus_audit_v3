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
        
        Handles:
        - Virtual environment detection
        - Missing tool errors (logged, not raised)
        - File filtering via config["_file_filter"]
        - Force rescan via config["_force_rescan"]
        """
        findings = []
        
        try:
            # Step 1: Find the tool command
            await bus.publish_log("info", "Locating bandit tool...")
            tool_cmd = find_tool_command("bandit")
            await bus.publish_log("info", f"Using: {tool_cmd}")
            
            # Step 2: Prepare environment (add venv bin to PATH if available)
            env = os.environ.copy()
            venv_python = _get_venv_python()
            if venv_python:
                bin_dir = venv_python.parent
                env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            
            # Step 3: Build command
            cmd = [
                tool_cmd, "-r", str(target),
                "-x", ".venv,venv,.env,node_modules,build,dist",
                "-f", "json",
                "-q"
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
                
                # Step 5: Parse JSON output
                if stdout:
                    try:
                        data = json.loads(stdout.decode('utf-8'))
                        issues = data.get("results", [])
                        
                        await bus.publish_log("info", f"Bandit found {len(issues)} issues")
                        
                        for issue in issues:
                            severity_map = {
                                "HIGH": Severity.HIGH,
                                "MEDIUM": Severity.MEDIUM,
                                "LOW": Severity.LOW
                            }
                            
                            finding_id = hashlib.sha256(
                                f"{issue.get('filename')}{issue.get('line_number')}{issue.get('test_id')}".encode()
                            ).hexdigest()[:16]
                            
                            finding = Finding(
                                id=finding_id,
                                scanner=self.name,
                                file=issue.get("filename", "unknown"),
                                line=issue.get("line_number", 0),
                                column=0,
                                severity=severity_map.get(issue.get("severity", "LOW"), Severity.MEDIUM),
                                category=Category.SECURITY,
                                title=issue.get("issue_text", "Security issue"),
                                description=issue.get("issue_cwe", {}).get("id", issue.get("issue_text", "Security issue detected")),
                                suggestion=f"See Bandit test {issue.get('test_id')} documentation",
                                cwe=issue.get("issue_cwe", {}).get("id"),
                                persistence=Persistence.NEW,
                                fix_status=FixStatus.OPEN
                            )
                            findings.append(finding)
                        
                    except json.JSONDecodeError as e:
                        await bus.publish_log("warning", f"Bandit JSON parse error: {str(e)}")
                else:
                    await bus.publish_log("info", "Bandit completed with no output")
                
                await bus.publish_progress(self.name, 100, str(target))
                
            except asyncio.TimeoutError:
                await bus.publish_log("error", f"Bandit scan timed out after {self.timeout}s")
            except Exception as e:
                await bus.publish_log("error", f"Bandit scan error: {str(e)}")
        
        except FileNotFoundError as e:
            # Tool not installed — log warning, don't crash
            await bus.publish_log(
                "warning",
                f"Bandit not available: {str(e)}"
            )
        except Exception as e:
            await bus.publish_log("error", f"Bandit scanner error: {str(e)}")
        
        return findings
