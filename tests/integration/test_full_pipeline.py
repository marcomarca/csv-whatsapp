"""Integration tests for the complete WhatsApp Backup to CSV pipeline."""

import shutil
import subprocess
from pathlib import Path
import pytest

from src.database import VaultDatabase
from src.device_manager import DeviceManager
from src.models import DeviceInfo
from src.pipeline import ExportPipeline
from src.secret_manager import SecretManager
from tests.conftest import TEST_KEY_HEX


def test_full_pipeline_integration(
    tmp_path: Path,
    synthetic_crypt15_backup: Path,
    mock_keyring,
    monkeypatch,
):
    """Test full automated pipeline execution with synthetic encrypted WhatsApp backup."""
    vault_db_path = tmp_path / "integration_vault.db"
    exports_dir = tmp_path / "exports"
    backups_dir = tmp_path / "backups"
    working_dir = tmp_path / "working"

    monkeypatch.setattr("src.config.AppConfig.BACKUPS_DIR", backups_dir)
    monkeypatch.setattr("src.config.AppConfig.WORKING_DIR", working_dir)
    monkeypatch.setattr("src.config.AppConfig.EXPORTS_DIR", exports_dir)
    monkeypatch.setattr("src.config.AppConfig.VAULT_DB_PATH", vault_db_path)

    dev_mgr = DeviceManager(adb_path="mock_adb")
    sec_mgr = SecretManager()
    vault = VaultDatabase(vault_db_path)

    # Save encryption key in mock keyring
    sec_mgr.store_key(TEST_KEY_HEX, account_id="mock_serial")
    sec_mgr.store_key(TEST_KEY_HEX, account_id="default")

    # Mock DeviceManager adb calls
    def mock_run_adb(args, timeout=60):
        if "devices" in args:
            return subprocess.CompletedProcess(args, 0, stdout="mock_serial\tdevice\n", stderr="")
        if "getprop" in args and "ro.product.model" in args:
            return subprocess.CompletedProcess(args, 0, stdout="Mock Android Phone\n", stderr="")
        if "getprop" in args and "ro.build.version.release" in args:
            return subprocess.CompletedProcess(args, 0, stdout="14\n", stderr="")
        if "pm" in args:
            return subprocess.CompletedProcess(args, 0, stdout="package:com.whatsapp\n", stderr="")
        if "ls" in args[3]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=f"-rw-rw---- 1 u0_a254 everybody 50000 2026-09-25 12:00 {synthetic_crypt15_backup.name}\n",
                stderr="",
            )
        if "pull" in args:
            # Copy synthetic backup to destination
            dest = args[-1]
            shutil.copy2(synthetic_crypt15_backup, dest)
            return subprocess.CompletedProcess(args, 0, stdout="pulled", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run_adb)

    pipeline = ExportPipeline(
        device_manager=dev_mgr,
        secret_manager=sec_mgr,
        vault_db=vault,
    )

    # First Export Run
    res1 = pipeline.run_export(output_dir=exports_dir)
    assert res1["status"] == "success"
    assert res1["total_conversations"] >= 2
    assert res1["total_messages"] >= 7
    assert res1["inserted_messages"] >= 7
    assert (exports_dir / "all_messages.csv").is_file()
    assert (exports_dir / "conversations.csv").is_file()
    assert (exports_dir / "manifest.json").is_file()

    # Second Export Run (Identical backup - deduplication check)
    res2 = pipeline.run_export(output_dir=exports_dir)
    assert res2["status"] == "success"
    assert res2["inserted_messages"] == 0  # 0 new messages inserted
    assert res2["total_messages"] == res1["total_messages"]
