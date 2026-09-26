"""Unit tests for SecretManager and key storage."""

import pytest
from src.errors import InvalidKeyError
from src.secret_manager import SecretManager


def test_sanitize_and_validate_hex_key():
    """Test hex key validation with various whitespace and format variations."""
    valid_raw = " 0123456789abcdef:0123456789ABCDEF-0123456789abcdef 0123456789abcdef \n"
    sanitized = SecretManager.validate_hex_key(valid_raw)
    assert len(sanitized) == 64
    assert sanitized == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_invalid_key_formats_raise_error():
    """Test that invalid keys raise structured InvalidKeyError."""
    # Empty
    with pytest.raises(InvalidKeyError) as e1:
        SecretManager.validate_hex_key("")
    assert e1.value.code == "INVALID_KEY"

    # Too short (63 chars)
    with pytest.raises(InvalidKeyError):
        SecretManager.validate_hex_key("0123456789abcdef" * 3 + "0123456789abcde")

    # Non-hex characters (e.g., 'z')
    with pytest.raises(InvalidKeyError):
        SecretManager.validate_hex_key("z" * 64)


def test_keyring_storage_operations(mock_keyring):
    """Test storing, retrieving, and deleting keys from keyring."""
    sec = SecretManager(service_name="test_service")
    key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    assert sec.has_key("test_device") is False
    assert sec.get_key("test_device") is None

    # Store
    sec.store_key(key, "test_device")
    assert sec.has_key("test_device") is True
    assert sec.get_key("test_device") == key

    # Masking for UI
    assert sec.mask_key(key) == "0123...cdef"

    # Delete
    deleted = sec.delete_key("test_device")
    assert deleted is True
    assert sec.has_key("test_device") is False
