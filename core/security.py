# core/security.py
"""
Lightweight symmetric encryption for the API key stored in settings.json.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The encryption key is derived from a machine-specific secret and stored in
.nexus_secret (gitignored). If the package is unavailable we fall back to
base64-obfuscation with a clear warning — the sentinel prefix "enc:" vs
"b64:" lets decrypt() handle both transparently.
"""

from __future__ import annotations
import base64
import os
from pathlib import Path

_SECRET_FILE = Path(".nexus_secret")
_ENC_PREFIX = "fernet:"
_B64_PREFIX = "b64:"

# ── Key bootstrap ─────────────────────────────────────────────────────────────

def _load_or_create_key() -> bytes:
    """Return a 32-byte Fernet key, creating it on first run."""
    if _SECRET_FILE.exists():
        raw = _SECRET_FILE.read_bytes().strip()
        return raw
    key = base64.urlsafe_b64encode(os.urandom(32))
    _SECRET_FILE.write_bytes(key)
    # Restrict file permissions on POSIX
    try:
        _SECRET_FILE.chmod(0o600)
    except Exception:
        pass
    return key

# ── Public API ─────────────────────────────────────────────────────────────────

def encrypt(plaintext: str) -> str:
    """Encrypt a string.  Returns a prefixed, encoded ciphertext string."""
    if not plaintext:
        return plaintext
    try:
        from cryptography.fernet import Fernet
        key = _load_or_create_key()
        f = Fernet(key)
        token = f.encrypt(plaintext.encode()).decode()
        return f"{_ENC_PREFIX}{token}"
    except ImportError:
        # Fallback: base64 obfuscation (not secure, but better than plaintext)
        import warnings
        warnings.warn(
            "cryptography package not installed — API key stored as base64. "
            "Install with: pip install cryptography",
            stacklevel=2,
        )
        encoded = base64.b64encode(plaintext.encode()).decode()
        return f"{_B64_PREFIX}{encoded}"


def decrypt(ciphertext: str) -> str:
    """Decrypt a string produced by encrypt().  Handles both prefixes."""
    if not ciphertext:
        return ciphertext
    if ciphertext.startswith(_ENC_PREFIX):
        try:
            from cryptography.fernet import Fernet
            key = _load_or_create_key()
            f = Fernet(key)
            token = ciphertext[len(_ENC_PREFIX):]
            return f.decrypt(token.encode()).decode()
        except Exception:
            return ""
    if ciphertext.startswith(_B64_PREFIX):
        try:
            encoded = ciphertext[len(_B64_PREFIX):]
            return base64.b64decode(encoded.encode()).decode()
        except Exception:
            return ""
    # Unrecognised format — return as-is (legacy plaintext)
    return ciphertext


def is_encrypted(value: str) -> bool:
    """Return True if the value looks like an encrypted/obfuscated key."""
    return bool(value and (
        value.startswith(_ENC_PREFIX) or value.startswith(_B64_PREFIX)
    ))
