"""Unit tests for DecryptManager and SQLite validation."""

from pathlib import Path
import pytest

from src.decrypt_manager import DecryptManager
from src.errors import InvalidKeyError, InvalidSQLiteError
from tests.conftest import TEST_KEY_HEX, WRONG_KEY_HEX


def test_identify_format(tmp_path: Path, synthetic_sqlite_db: Path):
    """Test format detection from extension and magic header."""
    assert DecryptManager.identify_format(Path("msgstore.db.crypt15")) == "crypt15"
    assert DecryptManager.identify_format(Path("msgstore.db.crypt14")) == "crypt14"
    assert DecryptManager.identify_format(Path("msgstore.db.crypt12")) == "crypt12"
    assert DecryptManager.identify_format(synthetic_sqlite_db) == "sqlite"


def test_decrypt_synthetic_backup_success(
    synthetic_crypt15_backup: Path,
    tmp_path: Path,
):
    """Test successful decryption and SQLite verification of synthetic crypt15 backup."""
    output_db = tmp_path / "decrypted.db"
    decrypted = DecryptManager.decrypt(synthetic_crypt15_backup, TEST_KEY_HEX, output_db)

    assert decrypted.is_file()
    assert decrypted.stat().st_size > 0
    # Header check
    with open(decrypted, "rb") as f:
        assert f.read(16) == b"SQLite format 3\x00"


def test_decrypt_with_wrong_key_fails(
    synthetic_crypt15_backup: Path,
    tmp_path: Path,
):
    """Test that decryption with wrong key is rejected and does not produce valid database."""
    output_db = tmp_path / "decrypted_bad.db"

    with pytest.raises((InvalidKeyError, InvalidSQLiteError)):
        DecryptManager.decrypt(synthetic_crypt15_backup, WRONG_KEY_HEX, output_db)

    assert not output_db.exists()


def test_validate_sqlite_corrupted_file(tmp_path: Path):
    """Test that corrupted or invalid SQLite files are rejected."""
    corrupted_db = tmp_path / "corrupt.db"
    corrupted_db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)

    with pytest.raises(InvalidSQLiteError):
        DecryptManager.validate_sqlite(corrupted_db)
