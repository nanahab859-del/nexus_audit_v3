"""Tests for core.security module."""

import pytest

from core.security import encrypt, decrypt, InvalidTokenError


def test_encrypt_decrypt_round_trip() -> None:
    """Test encrypt → decrypt returns original."""
    plaintext = "test-api-key-12345"
    ciphertext = encrypt(plaintext)
    result = decrypt(ciphertext)
    assert result == plaintext


def test_encrypt_empty_string() -> None:
    """Test encrypt empty string returns empty."""
    assert encrypt("") == ""


def test_decrypt_empty_string() -> None:
    """Test decrypt empty string returns empty."""
    assert decrypt("") == ""


def test_encrypt_is_non_deterministic() -> None:
    """Test two encrypts of same string produce different ciphertext."""
    plaintext = "api-key"
    c1 = encrypt(plaintext)
    c2 = encrypt(plaintext)
    assert c1 != c2  # Fernet is non-deterministic


def test_decrypt_corrupt_raises() -> None:
    """Test decrypt of corrupt data raises InvalidTokenError."""
    with pytest.raises(InvalidTokenError):
        decrypt("not-valid-base64-ciphertext!!!")
