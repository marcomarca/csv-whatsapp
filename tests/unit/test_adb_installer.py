"""Unit tests for ADB automatic detection and installer module."""

import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.adb_installer import (
    ensure_adb,
    find_existing_adb,
    is_valid_adb,
)


def test_is_valid_adb_non_existent(tmp_path: Path):
    """Test is_valid_adb returns False for non-existent files."""
    assert not is_valid_adb(tmp_path / "non_existent_adb")


def test_is_valid_adb_mock_success(tmp_path: Path):
    """Test is_valid_adb returns True when version output contains Android Debug Bridge."""
    fake_adb = tmp_path / "fake_adb.exe"
    fake_adb.write_text("dummy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Android Debug Bridge version 1.0.41"
        )
        assert is_valid_adb(fake_adb)


def test_is_valid_adb_mock_failure(tmp_path: Path):
    """Test is_valid_adb returns False when binary fails or output is unexpected."""
    fake_adb = tmp_path / "fake_adb.exe"
    fake_adb.write_text("dummy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="Error")
        assert not is_valid_adb(fake_adb)


def test_find_existing_adb_env_var(tmp_path: Path, monkeypatch):
    """Test find_existing_adb respects valid ADB_PATH environment variable."""
    fake_adb = tmp_path / "custom_adb.exe"
    fake_adb.write_text("dummy")

    monkeypatch.setenv("ADB_PATH", str(fake_adb))
    with patch("src.adb_installer.is_valid_adb", return_value=True):
        assert find_existing_adb() == str(fake_adb)


def test_ensure_adb_already_present():
    """Test ensure_adb returns existing path without downloading."""
    with patch("src.adb_installer.find_existing_adb", return_value="/mock/bin/adb"):
        with patch("src.adb_installer.download_and_install_platform_tools") as mock_download:
            res = ensure_adb(auto_download=True)
            assert res == "/mock/bin/adb"
            mock_download.assert_not_called()
