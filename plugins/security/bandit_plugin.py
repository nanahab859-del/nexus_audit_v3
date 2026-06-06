from pathlib import Path
from typing import List
from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus, EventType
import subprocess
import json
import hashlib

class BanditScanner(BaseScanner):
    name = "bandit"
    version = "1.0.0"
    languages = ["python"]
    category = Category.SECURITY

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Run Bandit security scanner on Python files.
        Requires: pip install bandit
        """
        findings = []
        
        try:
            await bus.publish(EventType.PROGRESS, {"scanner": self.name, "percent": 10, "file": str(target)})
            
            # Run bandit with JSON output
            result = subprocess.run(
                ["bandit", "-r", str(target), "-f", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    issues = data.get("results", [])
                    
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
                        
                except json.JSONDecodeError:
                    pass
                    
            await bus.publish(EventType.PROGRESS, {"scanner": self.name, "percent": 100, "file": str(target)})
            
        except FileNotFoundError:
            await bus.publish(EventType.LOG, {
                "level": "warning",
                "message": "Bandit not found. Install with: pip install bandit"
            })
        except subprocess.TimeoutExpired:
            await bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Bandit scan timed out after {self.timeout}s"
            })
        except Exception as e:
            await bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Bandit scan error: {str(e)}"
            })
        
        return findings
