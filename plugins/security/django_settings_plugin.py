import re
import asyncio
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus

class DjangoSettingsScanner(BaseScanner):
    name: ClassVar[str] = "django_settings"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["python"]
    category: ClassVar[Category] = Category.SECURITY
    requires_tool: ClassVar[bool] = False
    tool_name: ClassVar[str] = ""
    timeout: ClassVar[int] = 30

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        return []

    def _parse_output(self, output: Any) -> List[Finding]:
        return []

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        await bus.publish_progress(self.name, 0, str(target))
        findings = []
        
        settings_file = None
        # Common locations for Django settings
        candidates = [
            "settings.py",
            "settings/__init__.py",
            "config/settings.py",
            "project/settings.py"
        ]
        
        for candidate in candidates:
            p = target / candidate
            if p.exists():
                settings_file = p
                break
        
        # Also check if it's a Django project by looking for manage.py
        if not settings_file and (target / "manage.py").exists():
            # Try to find any file named settings.py in subdirectories
            for p in target.glob("**/settings.py"):
                if "venv" not in str(p) and "node_modules" not in str(p):
                    settings_file = p
                    break
                    
        if not settings_file:
            await bus.publish_log("info", "No Django settings file found")
            await bus.publish_progress(self.name, 100, str(target))
            return []
            
        try:
            content = await asyncio.to_thread(settings_file.read_text, encoding='utf-8', errors='ignore')
        except Exception as e:
            await bus.publish_log("error", f"Failed to read settings file {settings_file}: {e}")
            return []
            
        checks = {
            "SECRET_KEY": r'SECRET_KEY\s*=\s*["\'](?!\$\{)([^"\']+)["\']',
            "DEBUG": r'DEBUG\s*=\s*True',
            "ALLOWED_HOSTS": r'ALLOWED_HOSTS\s*=\s*\[\s*["\']\*["\']',
            "SECURE_SSL_REDIRECT": r'SECURE_SSL_REDIRECT\s*=\s*False',
            "SESSION_COOKIE_SECURE": r'SESSION_COOKIE_SECURE\s*=\s*False',
            "CSRF_COOKIE_SECURE": r'CSRF_COOKIE_SECURE\s*=\s*False',
            "SECURE_HSTS_SECONDS": r'SECURE_HSTS_SECONDS\s*=\s*0',
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": r'SECURE_HSTS_INCLUDE_SUBDOMAINS\s*=\s*False',
            "SECURE_CONTENT_TYPE_NOSNIFF": r'SECURE_CONTENT_TYPE_NOSNIFF\s*=\s*False',
        }
        
        lines = content.splitlines()
        
        for check_name, pattern in checks.items():
            compiled = re.compile(pattern)
            for i, line_text in enumerate(lines, start=1):
                match = compiled.search(line_text)
                if not match:
                    continue
                
                issue_detected = False
                if check_name == "SECRET_KEY":
                    # If SECRET_KEY is a placeholder or too short (simplified check)
                    val = match.group(1)
                    if len(val) < 20 or "placeholder" in val.lower() or "changeme" in val.lower():
                        issue_detected = True
                elif check_name in ("DEBUG", "ALLOWED_HOSTS"):
                    # These patterns match INSECURE settings
                    issue_detected = True
                else:
                    # For the rest, patterns match INSECURE settings (False or 0)
                    issue_detected = True
                
                if issue_detected:
                    severity = Severity.HIGH if check_name in ("SECRET_KEY", "DEBUG", "ALLOWED_HOSTS") else Severity.MEDIUM
                    findings.append(create_finding(
                        scanner=self.name,
                        rule_id=f"django-{check_name.lower().replace('_', '-')}",
                        file=str(settings_file.relative_to(target)) if settings_file.is_relative_to(target) else str(settings_file),
                        line=i,
                        column=match.start(),
                        severity=severity,
                        category=self.category,
                        title=f"Django security misconfiguration: {check_name}",
                        description=f"{check_name} is not properly configured for production in {settings_file.name}",
                        suggestion=f"Set {check_name} to a secure value in production settings",
                        cwe="CWE-16",
                    ))
                    break   # one finding per check_name
                
        findings = await self._filter_to_changed(findings, config.get("_file_filter"))
        await bus.publish_progress(self.name, 100, str(target))
        return findings
