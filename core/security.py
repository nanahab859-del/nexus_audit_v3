"""API key encryption using Fernet (symmetric encryption)."""

import base64
import hashlib
import platform
from pathlib import Path
from socket import gethostname

from cryptography.fernet import Fernet, InvalidToken


class InvalidTokenError(Exception):
    """Raised when decryption fails."""
    pass


def derive_key() -> bytes:
    """
    Derive a Fernet key from machine-stable identifier.
    Falls back to random key in .key_cache if hostname is unstable.
    """
    key_cache = Path(".key_cache")

    try:
        # Try to derive from machine identifier
        identifier = f"{gethostname()}:{platform.system()}:{platform.python_version()}"
        hash_bytes = hashlib.sha256(identifier.encode()).digest()
        key = base64.urlsafe_b64encode(hash_bytes)
        return key
    except Exception:
        # Fallback: use cached random key
        if key_cache.exists():
            return key_cache.read_bytes()

        # Generate and cache a new random key
        key = Fernet.generate_key()
        key_cache.write_bytes(key)
        return key


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64 ciphertext string."""
    if not plaintext:
        return ""

    key = derive_key()
    f = Fernet(key)
    ciphertext = f.encrypt(plaintext.encode())
    return ciphertext.decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt ciphertext. Raises InvalidTokenError if corrupt."""
    if not ciphertext:
        return ""

    key = derive_key()
    f = Fernet(key)
    try:
        plaintext = f.decrypt(ciphertext.encode())
        return plaintext.decode()
    except InvalidToken as e:
        raise InvalidTokenError(f"Decryption failed: {e}") from e
