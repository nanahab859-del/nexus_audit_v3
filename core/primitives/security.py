import os
import sys
import socket
import platform
import hashlib
import base64
import logging
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

# Module-level state
_FERNET: Optional[Fernet] = None
_CACHE_PATH = Path.home() / ".nexus_audit" / ".key_cache"

def derive_key() -> bytes:
    """
    Return a 32-byte URL-safe base64 Fernet key.
    Uses machine-stable identifiers, with fallback to a cached random key.
    """
    global _FERNET
    
    # 1-3. Attempt stable derivation
    hostname = socket.gethostname()
    node = platform.node()
    executable = sys.executable
    
    stable_string = f"{hostname}:{node}:{executable}"
    
    # Check if identifiers look unstable
    if hostname == "localhost" or not node:
        # Fallback to cached key
        if _CACHE_PATH.exists():
            key = _CACHE_PATH.read_bytes().strip()
        else:
            key = base64.urlsafe_b64encode(os.urandom(32))
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_PATH.write_bytes(key)
            os.chmod(_CACHE_PATH, 0o600)
    else:
        # Primary derivation
        digest = hashlib.sha256(stable_string.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    
    # Initialize Fernet instance
    _FERNET = Fernet(key)
    return key

def _ensure_fernet():
    if _FERNET is None:
        derive_key()

def encrypt(plaintext: Optional[str]) -> str:
    """Encrypt with Fernet. Returns token string."""
    if not plaintext:
        return ""
    _ensure_fernet()
    # _FERNET is guaranteed to be set after _ensure_fernet()
    return _FERNET.encrypt(plaintext.encode()).decode() # type: ignore

def decrypt(ciphertext: Optional[str]) -> str:
    """Decrypt Fernet token. Returns original string."""
    if not ciphertext:
        return ""
        
    # Legacy cleartext check
    if not ciphertext.startswith("gAAAAA"):
        logging.warning("Decrypting legacy unencrypted key.")
        return ciphertext
        
    _ensure_fernet()
    # _FERNET is guaranteed to be set after _ensure_fernet()
    return _FERNET.decrypt(ciphertext.encode()).decode() # type: ignore

def is_encrypted(value: str) -> bool:
    """Return True if the value looks like an encrypted/obfuscated key."""
    return bool(value and value.startswith("gAAAAA"))
