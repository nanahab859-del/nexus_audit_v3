import pytest
from pathlib import Path
from core.security import encrypt, decrypt, is_encrypted

def test_encryption_decryption(tmp_path):
    # Change working directory or mock _SECRET_FILE somehow, 
    # but the functions just use Path(".nexus_secret").
    # It will use the cwd. We will just test it directly.
    original_text = "sk-ant-1234567890"
    
    # Encrypt
    encrypted = encrypt(original_text)
    assert encrypted != original_text
    assert is_encrypted(encrypted)
    
    # Decrypt
    decrypted = decrypt(encrypted)
    assert decrypted == original_text

def test_decryption_with_unencrypted_text():
    assert decrypt("plain_text") == "plain_text"
    assert not is_encrypted("plain_text")
