from cryptography.fernet import Fernet, InvalidToken
import pytest
import logging
import os
import stat
from unittest.mock import patch, MagicMock
from core.primitives.security import encrypt, decrypt, derive_key, is_encrypted

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
    with pytest.raises(InvalidToken):
        decrypt(tampered)

def test_key_cache_creation():
    with patch("core.primitives.security._FERNET", None):
        key1 = derive_key()
        key2 = derive_key()
        assert key1 == key2

def test_derive_key_fallback():
    # Covers: if hostname == "localhost" or not node:
    with patch("socket.gethostname", return_value="localhost"):
        with patch("platform.node", return_value=""):
            with patch("core.primitives.security._FERNET", None):
                key = derive_key()
                assert len(key) > 0

def test_is_encrypted():
    assert is_encrypted("gAAAAA") is True
    assert is_encrypted("not-encrypted") is False
    assert is_encrypted("") is False
    assert is_encrypted(None) is False

def test_derive_key_returns_same_key_twice():
    from core.primitives.security import derive_key
    with patch("core.primitives.security._FERNET", None):
        key1 = derive_key()
        key2 = derive_key()
        assert key1 == key2

def test_derive_key_creates_cache_file(tmp_path, monkeypatch):
    from core.primitives.security import derive_key
    cache_path = tmp_path / ".key_cache"
    monkeypatch.setattr("core.primitives.security._CACHE_PATH", cache_path)
    with patch("core.primitives.security._FERNET", None):
        with patch("socket.gethostname", return_value="localhost"):
            with patch("platform.node", return_value=""):
                derive_key()
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
