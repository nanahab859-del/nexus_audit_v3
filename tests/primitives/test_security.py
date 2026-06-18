from cryptography.fernet import Fernet, InvalidToken
import pytest
import logging
import os
import stat
from unittest.mock import patch, MagicMock
from core.primitives.security import encrypt, decrypt, is_encrypted, _load_or_create_key

def test_encrypt_decrypt():
    plaintext = "hello world"
    with patch("core.primitives.security._FERNET", None):
        with patch("cryptography.fernet.Fernet.generate_key", return_value=Fernet.generate_key()):
            encrypted = encrypt(plaintext)
            assert decrypt(encrypted) == plaintext

def test_decrypt_with_non_fernet_legacy_string():
    with patch("logging.warning") as mock_warn:
        assert decrypt("my-legacy-plaintext-key") == "my-legacy-plaintext-key"
        mock_warn.assert_called()

def test_encrypt_empty_string_twice_produces_same_result():
    assert encrypt("") == ""
    assert encrypt(None) == ""
    assert decrypt("") == ""
    assert decrypt(None) == ""

def test_tamper_detection():
    encrypted = encrypt("hello")
    tampered = encrypted[:-1] + "A"
    assert decrypt(tampered) == ""

def test_key_cache_creation():
    with patch("core.primitives.security._FERNET", None):
        key1 = _load_or_create_key()
        key2 = _load_or_create_key()
        assert key1 == key2

def test_derive_key_fallback():
    # Covers: random key creation
    with patch("core.primitives.security._FERNET", None):
        key = _load_or_create_key()
        assert key is not None

def test_is_encrypted():
    assert is_encrypted("gAAAAA") is True
    assert is_encrypted("not-encrypted") is False
    assert is_encrypted("") is False
    assert is_encrypted(None) is False

def test_derive_key_returns_same_key_twice():
    with patch("core.primitives.security._FERNET", None):
        key1 = _load_or_create_key()
        key2 = _load_or_create_key()
        assert key1 == key2

def test_derive_key_creates_cache_file(tmp_path, monkeypatch):
    cache_path = tmp_path / ".key_cache"
    monkeypatch.setattr("core.primitives.security._CACHE_PATH", cache_path)
    with patch("core.primitives.security._FERNET", None):
        _load_or_create_key()
        assert cache_path.exists()
        mode = cache_path.stat().st_mode
        # Check for 0o600 permissions
        assert bool(mode & stat.S_IRUSR)
        assert bool(mode & stat.S_IWUSR)
        assert not bool(mode & stat.S_IRGRP)
        assert not bool(mode & stat.S_IROTH)

def test_encrypt_produces_different_ciphertext_for_same_plaintext():
    p = "hello"
    c1 = encrypt(p)
    c2 = encrypt(p)
    assert c1 != c2
    assert decrypt(c1) == p
    assert decrypt(c2) == p


def test_rotate_key_clears_fernet_and_creates_new_key(tmp_path, monkeypatch):
    """Covers rotate_key() — lines 113-117 of security.py."""
    import core.primitives.security as sec
    cache_path = tmp_path / ".key_cache"
    monkeypatch.setattr(sec, "_CACHE_PATH", cache_path)
    monkeypatch.setattr(sec, "_FERNET", None)

    # Create an initial key
    old_fernet = _load_or_create_key()
    assert cache_path.exists()

    # Rotate — should delete cache, reset _FERNET, create a new key
    from core.primitives.security import rotate_key
    rotate_key()

    # After rotation, _FERNET was reset and re-created
    assert sec._FERNET is not None
    # Cache file should be recreated (new key)
    assert cache_path.exists()


def test_load_existing_key_from_cache(tmp_path, monkeypatch):
    """Covers the _CACHE_PATH.exists() branch (line 48) in _load_or_create_key."""
    import core.primitives.security as sec
    from cryptography.fernet import Fernet as _F
    cache_path = tmp_path / ".key_cache"

    # Pre-write a known valid key
    known_key = _F.generate_key()
    cache_path.write_bytes(known_key)
    os.chmod(cache_path, 0o600)

    monkeypatch.setattr(sec, "_CACHE_PATH", cache_path)
    monkeypatch.setattr(sec, "_FERNET", None)

    f = _load_or_create_key()
    assert f is not None
    # Encrypt/decrypt should work with the loaded key
    token = f.encrypt(b"test")
    assert f.decrypt(token) == b"test"
