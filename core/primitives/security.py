"""
security.py — API key encryption for Nexus Audit.

Strategy:
  A random 256-bit key is generated once and stored in a file with 0o600
  permissions at ~/.nexus_audit/.key_cache. All subsequent calls use this
  cached key.

  The key is per-user, per-machine, and not derivable from observable system
  state. It protects stored API keys against casual file-system inspection.

  It does NOT protect against an attacker with read access to the key file.
  For stronger protection, integrate with the OS keyring (keyring library).
  That is a future improvement — see TODO below.

TODO: Replace file-cached key with OS keyring:
  import keyring
  key = keyring.get_password("nexus-audit", "encryption-key")
  if not key:
      key = base64.urlsafe_b64encode(os.urandom(32)).decode()
      keyring.set_password("nexus-audit", "encryption-key", key)
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_CACHE_PATH: Path = Path.home() / ".nexus_audit" / ".key_cache"
_FERNET: Optional[Fernet] = None


def _load_or_create_key() -> Fernet:
    """
    Load the encryption key from cache, or create and store a new one.
    The cache file is created with 0o600 permissions (owner read/write only).
    """
    global _FERNET

    if _FERNET is not None:
        return _FERNET

    if _CACHE_PATH.exists():
        key = _CACHE_PATH.read_bytes().strip()
    else:
        key = base64.urlsafe_b64encode(os.urandom(32))
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_bytes(key)
        os.chmod(_CACHE_PATH, 0o600)

    _FERNET = Fernet(key)
    return _FERNET


def encrypt(plaintext: Optional[str]) -> str:
    """
    Encrypt a string with Fernet symmetric encryption.
    Returns an empty string if plaintext is falsy.
    """
    if not plaintext:
        return ""
    f = _load_or_create_key()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: Optional[str]) -> str:
    """
    Decrypt a Fernet token string.
    Returns empty string if ciphertext is falsy.
    Handles legacy cleartext values with a warning.
    """
    if not ciphertext:
        return ""

    # Legacy cleartext detection:
    # Fernet tokens are base64url-encoded and always start with "gAAAAA"
    # (the base64 encoding of the 0x80 version byte). Any value that does
    # not start with this prefix was stored without encryption.
    if not ciphertext.startswith("gAAAAA"):
        logging.warning(
            "Found a legacy unencrypted value. "
            "Re-save your API key to encrypt it: config:set global.api_key <key>"
        )
        return ciphertext

    try:
        f = _load_or_create_key()
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logging.error(
            "Failed to decrypt stored value — key may have changed. "
            "You will need to re-enter your API key."
        )
        return ""


def is_encrypted(value: Optional[str]) -> bool:
    """Return True if the value appears to be a Fernet-encrypted token."""
    return bool(value and value.startswith("gAAAAA"))


def rotate_key() -> None:
    """
    Generate a new random key and delete the old cache file.
    After calling this, all previously encrypted values become unreadable.
    Use only when deliberately rotating credentials.
    """
    global _FERNET
    _FERNET = None
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    _load_or_create_key()
    logging.info("Encryption key rotated. Re-encrypt all stored secrets.")
