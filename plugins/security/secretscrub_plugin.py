import math
import re
import fnmatch
from pathlib import Path
from typing import ClassVar, List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category, Severity, create_finding
from core.primitives.events import EventBus
from core.infra.file_discovery import discover

class SecretScrubScanner(BaseScanner):
    name: ClassVar[str] = "secretscrub"
    version: ClassVar[str] = "1.0.0"
    languages: ClassVar[List[str]] = ["*"]
    category: ClassVar[Category] = Category.SECURITY
    requires_tool: ClassVar[bool] = False
    tool_name: ClassVar[str] = ""
    timeout: ClassVar[int] = 60

    BUILTIN_PATTERNS = [
        (r'AKIA[0-9A-Z]{16}', 'AWS Access Key'),
        (r'AIza[0-9A-Za-z\-_]{35}', 'Google API Key'),
        (r'gh[pousr]_[A-Za-z0-9_]{36,}', 'GitHub Token'),
        (r'[A-Za-z0-9+/=]{40,}', 'High-entropy base64 string'),
        (r'-----BEGIN.*PRIVATE KEY-----', 'Private key header'),
        (r'password\s*=\s*["\'][^"\']{8,}["\']', 'Password assignment'),
        (r'api[_-]?key\s*=\s*["\'][^"\']{8,}["\']', 'API key assignment'),
    ]

    DANGEROUS_FILENAMES = [
        '.env', '.env.example', 'credentials.json', 'id_rsa', 'id_ed25519',
        '*.pem', '*.key', '*.pkcs12', '*.pfx', 'secret*', 'private*'
    ]

    DEFAULT_EXCLUSIONS = [
        '*.min.js', '*.min.css', 'package-lock.json', 'yarn.lock',
        'poetry.lock', 'dist/', 'build/'
    ]

    @staticmethod
    def _entropy_score(s: str) -> float:
        if not s: return 0.0
        freq = {}
        for c in s: freq[c] = freq.get(c, 0) + 1
        length = len(s)
        entropy = 0.0
        for count in freq.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        return []

    def _parse_output(self, output: Any) -> List[Finding]:
        return []

    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        await bus.publish_progress(self.name, 0, str(target))
        findings = []
        # Discover files
        discovered_files = await discover(target)
        
        # Merge exclusions
        exclusions = self.DEFAULT_EXCLUSIONS + config.get("exclude_paths", [])
        
        additional_patterns = config.get("additional_patterns", [])
        patterns = self.BUILTIN_PATTERNS + [(p, "Custom Secret") for p in additional_patterns]

        for disc_file in discovered_files:
            file_path = disc_file.absolute_path
            
            # Check exclusions — use relative path for directory patterns, filename for extensions
            rel = disc_file.relative_path
            if any(fnmatch.fnmatch(rel, excl) for excl in exclusions):
                continue
            if any(fnmatch.fnmatch(file_path.name, excl) for excl in exclusions):
                continue
                
            # Check dangerous filenames
            if any(fnmatch.fnmatch(file_path.name, pat) for pat in self.DANGEROUS_FILENAMES):
                findings.append(create_finding(
                    scanner=self.name,
                    rule_id="dangerous-filename",
                    file=disc_file.relative_path,
                    line=0, column=0,
                    severity=Severity.HIGH,
                    category=self.category,
                    title="Dangerous filename found",
                    description=f"File {file_path.name} is potentially dangerous",
                    suggestion="Remove or move this file"
                ))
            
            # Read and scan content
            try:
                # Skip large files (assuming 1MB)
                if file_path.stat().st_size > 1024 * 1024:
                    continue
                    
                lines = file_path.read_text(encoding='utf-8', errors='ignore').splitlines()
                for i, line in enumerate(lines):
                    for pattern, name in patterns:
                        for match in re.finditer(pattern, line):
                            # Special case: entropy check for high-entropy base64
                            if "base64" in name.lower():
                                if self._entropy_score(match.group(0)) <= 4.5:
                                    continue
                            
                            findings.append(create_finding(
                                scanner=self.name,
                                rule_id=name.lower().replace(" ", "-"),
                                file=disc_file.relative_path,
                                line=i + 1,
                                column=match.start(),
                                severity=Severity.HIGH,
                                category=self.category,
                                title=f"Potential secret found: {name}",
                               description="Secret detected. Sensitive data should not be stored in source code.",
                               suggestion="Remove secret and use environment variables or secret management tools."
                            ))
            except Exception as e:
                await bus.publish_log("error", f"SecretScrub failed to read {file_path}: {e}")

        findings = await self._filter_to_changed(findings, config.get("_file_filter"))
        await bus.publish_progress(self.name, 100, str(target))
        return findings
