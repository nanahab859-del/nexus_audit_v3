"""
Django settings security scanner.

Audits Django settings modules for critical security misconfigurations
including SECRET_KEY, DEBUG, ALLOWED_HOSTS, and secure cookie/redirect settings.
"""

from typing import Any
import ast
import logging
from pathlib import Path

from core.events import EventBus
from core.models import Finding, Category, Severity
from plugins.base import BaseScanner

logger = logging.getLogger(__name__)


class DjangoSettingsPlugin(BaseScanner):
    """Scanner for Django project settings security."""

    name = "django_settings"
    version = "0.1.0"
    languages = ["python"]
    category = Category.SECURITY
    requires_ai = False
    timeout = 30

    async def scan(self, target: Path, config: dict[str, Any], bus: EventBus) -> list[Finding]:
        """
        Scan Django settings for security misconfigurations.

        Args:
            target: Project root directory
            config: Scanner configuration (unused for now)
            bus: EventBus for publishing events

        Returns:
            List of Finding objects for each security issue detected
        """
        await bus.publish_progress(self.name, 0, "Searching for Django settings...")

        findings: list[Finding] = []

        # Try to locate settings module
        settings_path = self._find_settings_file(target)
        if not settings_path:
            await bus.publish_log("info", f"{self.name}: No Django settings module found")
            return []

        await bus.publish_log("info", f"{self.name}: Analyzing {settings_path.relative_to(target)}")

        # Parse settings file
        try:
            settings_dict = self._parse_settings(settings_path)
        except Exception as e:
            await bus.publish_log("warning", f"{self.name}: Could not parse settings: {e}")
            return []

        # Check each security rule
        findings.extend(self._check_secret_key(settings_path, settings_dict))
        findings.extend(self._check_debug_mode(settings_path, settings_dict))
        findings.extend(self._check_allowed_hosts(settings_path, settings_dict))
        findings.extend(self._check_secure_ssl_redirect(settings_path, settings_dict))
        findings.extend(self._check_session_cookie_secure(settings_path, settings_dict))
        findings.extend(self._check_csrf_cookie_secure(settings_path, settings_dict))
        findings.extend(self._check_secure_hsts(settings_path, settings_dict))
        findings.extend(self._check_content_type_nosniff(settings_path, settings_dict))

        await bus.publish_progress(self.name, 100, "")
        return findings

    def _find_settings_file(self, project_root: Path) -> Path | None:
        """
        Locate Django settings module.

        Search strategy:
        1. Look for manage.py (Django marker)
        2. Scan for settings.py in common locations (project/, app/, etc.)
        3. Return first found settings.py

        Args:
            project_root: Root directory

        Returns:
            Path to settings.py or None if not found
        """
        # Check for manage.py
        if not (project_root / "manage.py").exists():
            return None

        # Look for settings.py in common locations
        candidates = [
            project_root / "settings.py",  # Root level
            project_root / "config" / "settings.py",  # Common Django project template
            project_root / "project" / "settings.py",  # Another common pattern
        ]

        # Scan subdirectories for settings.py
        for py_file in project_root.rglob("settings.py"):
            if not any(part.startswith(".") for part in py_file.relative_to(project_root).parts):
                candidates.insert(0, py_file)

        for path in candidates:
            if path.exists():
                return path

        return None

    def _parse_settings(self, settings_path: Path) -> dict[str, Any]:
        """
        Parse Django settings file using ast.literal_eval for assignments.

        Safe parsing: only extracts simple assignments at module level,
        doesn't execute arbitrary code.

        Args:
            settings_path: Path to settings.py

        Returns:
            Dict of {SETTING_NAME: value} for all simple assignments found
        """
        settings_dict = {}

        try:
            source = settings_path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Assign):
                    # Simple assignment: VAR = value
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_name = target.id
                            try:
                                # Try to evaluate the value safely
                                value = ast.literal_eval(node.value)
                                settings_dict[var_name] = value
                            except (ValueError, TypeError):
                                # Complex expression; skip
                                pass
        except Exception as e:
            logger.warning(f"Error parsing settings: {e}")

        return settings_dict

    def _check_secret_key(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if SECRET_KEY is properly set (not placeholder)."""
        findings: list[Finding] = []
        secret_key = settings_dict.get("SECRET_KEY", "")

        if not secret_key:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.CRITICAL,
                    category=self.category,
                    title="Django SECRET_KEY not set",
                    description="SECRET_KEY is missing or empty. This breaks session security and CSRF protection.",
                    suggestion='Set SECRET_KEY to a random 50-character string (use django.core.management.utils.get_random_secret_key())',
                    cwe="CWE-798",  # Use of Hard-coded Credentials
                )
            )
        elif isinstance(secret_key, str) and (secret_key.startswith("...") or len(secret_key) < 32):
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.HIGH,
                    category=self.category,
                    title="Django SECRET_KEY is weak or placeholder",
                    description="SECRET_KEY appears to be a placeholder or too short. It must be random and at least 50 characters.",
                    suggestion="Generate a new SECRET_KEY using Django's get_random_secret_key() utility",
                    cwe="CWE-330",  # Use of Insufficiently Random Values
                )
            )

        return findings

    def _check_debug_mode(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if DEBUG is False in production-like settings."""
        findings: list[Finding] = []
        debug = settings_dict.get("DEBUG", False)

        if debug is True:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.HIGH,
                    category=self.category,
                    title="Django DEBUG mode is enabled",
                    description="DEBUG=True exposes sensitive information (settings, SQL queries, stack traces) in error pages.",
                    suggestion="Set DEBUG=False in production settings. Use environment-specific settings modules.",
                    cwe="CWE-215",  # Information Exposure Through Debug Information
                )
            )

        return findings

    def _check_allowed_hosts(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if ALLOWED_HOSTS is properly configured."""
        findings: list[Finding] = []
        allowed_hosts = settings_dict.get("ALLOWED_HOSTS", [])

        if not allowed_hosts:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.MEDIUM,
                    category=self.category,
                    title="Django ALLOWED_HOSTS is empty",
                    description="ALLOWED_HOSTS is empty or not set. This allows Host header injection attacks.",
                    suggestion='Set ALLOWED_HOSTS to specific domain names, e.g., ["example.com", "www.example.com"]',
                    cwe="CWE-601",  # URL Redirection to Untrusted Site
                )
            )
        elif allowed_hosts == ["*"]:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.MEDIUM,
                    category=self.category,
                    title="Django ALLOWED_HOSTS is set to wildcard",
                    description='ALLOWED_HOSTS=["*"] allows any Host header, enabling cache poisoning and header injection attacks.',
                    suggestion='Specify explicit domain names instead of ["*"]',
                    cwe="CWE-601",  # URL Redirection to Untrusted Site
                )
            )

        return findings

    def _check_secure_ssl_redirect(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if SECURE_SSL_REDIRECT is enabled."""
        findings: list[Finding] = []
        ssl_redirect = settings_dict.get("SECURE_SSL_REDIRECT", False)

        if ssl_redirect is not True:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.MEDIUM,
                    category=self.category,
                    title="Django SECURE_SSL_REDIRECT is disabled",
                    description="HTTP requests will not be redirected to HTTPS, exposing data to man-in-the-middle attacks.",
                    suggestion="Set SECURE_SSL_REDIRECT=True to force HTTPS",
                    cwe="CWE-295",  # Improper Certificate Validation
                )
            )

        return findings

    def _check_session_cookie_secure(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if SESSION_COOKIE_SECURE is enabled."""
        findings: list[Finding] = []
        secure = settings_dict.get("SESSION_COOKIE_SECURE", False)

        if secure is not True:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.MEDIUM,
                    category=self.category,
                    title="Django SESSION_COOKIE_SECURE is disabled",
                    description="Session cookies will be transmitted over HTTP, exposing them to interception.",
                    suggestion="Set SESSION_COOKIE_SECURE=True to transmit session cookies only over HTTPS",
                    cwe="CWE-614",  # Sensitive Cookie in HTTPS Session Without 'Secure' Attribute
                )
            )

        return findings

    def _check_csrf_cookie_secure(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if CSRF_COOKIE_SECURE is enabled."""
        findings: list[Finding] = []
        secure = settings_dict.get("CSRF_COOKIE_SECURE", False)

        if secure is not True:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.MEDIUM,
                    category=self.category,
                    title="Django CSRF_COOKIE_SECURE is disabled",
                    description="CSRF tokens will be transmitted over HTTP, exposing them to interception.",
                    suggestion="Set CSRF_COOKIE_SECURE=True to transmit CSRF cookies only over HTTPS",
                    cwe="CWE-614",  # Sensitive Cookie in HTTPS Session Without 'Secure' Attribute
                )
            )

        return findings

    def _check_secure_hsts(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if SECURE_HSTS_SECONDS is configured."""
        findings: list[Finding] = []
        hsts_seconds = settings_dict.get("SECURE_HSTS_SECONDS", 0)

        if not isinstance(hsts_seconds, int) or hsts_seconds <= 0:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.LOW,
                    category=self.category,
                    title="Django SECURE_HSTS_SECONDS not configured",
                    description="HTTP Strict Transport Security (HSTS) is not enabled. This allows downgrade attacks.",
                    suggestion="Set SECURE_HSTS_SECONDS to at least 31536000 (1 year)",
                    cwe="CWE-295",  # Improper Certificate Validation
                )
            )

        return findings

    def _check_content_type_nosniff(self, settings_path: Path, settings_dict: dict[str, Any]) -> list[Finding]:
        """Check if SECURE_CONTENT_TYPE_NOSNIFF is enabled."""
        findings: list[Finding] = []
        nosniff = settings_dict.get("SECURE_CONTENT_TYPE_NOSNIFF", False)

        if nosniff is not True:
            findings.append(
                Finding(
                    scanner=self.name,
                    file=str(settings_path.name),
                    line=0,
                    column=0,
                    severity=Severity.LOW,
                    category=self.category,
                    title="Django SECURE_CONTENT_TYPE_NOSNIFF is disabled",
                    description="X-Content-Type-Options header is not set. Browsers may sniff MIME types, enabling XSS attacks.",
                    suggestion="Set SECURE_CONTENT_TYPE_NOSNIFF=True to add X-Content-Type-Options: nosniff header",
                    cwe="CWE-434",  # Unrestricted Upload of File with Dangerous Type
                )
            )

        return findings
