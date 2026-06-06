from pathlib import Path
from typing import List
from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus, EventType
import subprocess
import json
import hashlib

class VultureScanner(BaseScanner):
    name = "vulture"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Run Vulture dead code detector on Python files.
        Requires: pip install vulture
        """
        findings = []
        
        try:
            await bus.publish(EventType.PROGRESS, {"scanner": self.name, "percent": 10, "file": str(target)})
            
            # Run vulture with JSON output
            result = subprocess.run(
                ["vulture", str(target), "--format=json"],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.stdout:
                issues = json.loads(result.stdout)
                
                for issue in issues:
                    finding_id = hashlib.sha256(
                        f"{issue.get('filename')}{issue.get('line')}{issue.get('message')}".encode()
                    ).hexdigest()[:16]
                    
                    finding = Finding(
                        id=finding_id,
                        scanner=self.name,
                        file=issue.get("filename", "unknown"),
                        line=issue.get("line", 0),
                        column=0,
                        severity=Severity.LOW,
                        category=Category.QUALITY,
                        title=f"Dead code: {issue.get('type', 'unused')}",
                        description=issue.get("message", "Dead code detected"),
                        suggestion="Remove unused code or implement functionality",
                        persistence=Persistence.NEW,
                        fix_status=FixStatus.OPEN
                    )
                    findings.append(finding)
                    
            await bus.publish(EventType.PROGRESS, {"scanner": self.name, "percent": 100, "file": str(target)})
            
        except FileNotFoundError:
            await bus.publish(EventType.LOG, {
                "level": "warning",
                "message": "Vulture not found. Install with: pip install vulture"
            })
        except json.JSONDecodeError:
            # vulture sometimes returns non-JSON output
            pass
        except subprocess.TimeoutExpired:
            await bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Vulture scan timed out after {self.timeout}s"
            })
        except Exception as e:
            await bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Vulture scan error: {str(e)}"
            })
        
        return findings

