"""Unit tests for CLI subcommands."""

import argparse
from pathlib import Path

from src.cli import cmd_history, cmd_key, cmd_status
from src.database import VaultDatabase
from src.models import ExportRun
from src.secret_manager import SecretManager
from tests.conftest import TEST_KEY_HEX


def test_cli_status(capsys, mock_keyring, tmp_path: Path, monkeypatch):
    """Test 'status' CLI subcommand."""
    monkeypatch.setattr("src.config.AppConfig.VAULT_DB_PATH", tmp_path / "vault.db")
    args = argparse.Namespace(command="status")
    ret = cmd_status(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Estado del Sistema y Dispositivo" in captured.out


def test_cli_key_management(capsys, mock_keyring):
    """Test 'key' CLI subcommand (set, get, clear)."""
    # 1. set
    args_set = argparse.Namespace(command="key", action="set", value=TEST_KEY_HEX, account="default")
    assert cmd_key(args_set) == 0

    # 2. get
    args_get = argparse.Namespace(command="key", action="get", value=None, account="default")
    assert cmd_key(args_get) == 0
    captured = capsys.readouterr()
    assert "0123...cdef" in captured.out

    # 3. clear
    args_clear = argparse.Namespace(command="key", action="clear", value=None, account="default")
    assert cmd_key(args_clear) == 0


def test_cli_history(capsys, tmp_path: Path, monkeypatch):
    """Test 'history' CLI subcommand."""
    vault_path = tmp_path / "vault.db"
    monkeypatch.setattr("src.config.AppConfig.VAULT_DB_PATH", vault_path)
    vault = VaultDatabase(vault_path)

    vault.record_export_run(
        ExportRun(
            run_id="run_hist_1",
            started_at="2026-09-25T12:00:00Z",
            finished_at="2026-09-25T12:01:00Z",
            status="completed",
            total_conversations=5,
            total_messages=120,
            inserted_messages=120,
        )
    )

    args = argparse.Namespace(command="history", limit=10, account=None)
    assert cmd_history(args) == 0
    captured = capsys.readouterr()
    assert "run_hist_1" in captured.out
    assert "120" in captured.out


def test_cli_accounts(capsys, monkeypatch):
    """Test 'accounts' CLI subcommand."""
    from src.cli import cmd_accounts
    from src.models import DeviceInfo, WhatsAppAccount

    dev = DeviceInfo(serial="poco123", state="device", model="POCO X3 Pro")
    monkeypatch.setattr("src.device_manager.DeviceManager.get_active_device", lambda self, s=None: dev)

    mock_accounts = [
        WhatsAppAccount(
            account_id="principal",
            display_name="WhatsApp (Principal - Usuario 0)",
            android_user_id=0,
            package_name="com.whatsapp",
            remote_db_dir="/storage/emulated/0/WhatsApp/Databases/",
            latest_backup_file="msgstore.db.crypt15",
            latest_backup_size_mb=5.7,
            latest_backup_date="2026-09-26 01:00",
            crypt_format="crypt15",
        ),
        WhatsAppAccount(
            account_id="dual_xiaomi",
            display_name="WhatsApp (Dual Xiaomi - Usuario 999)",
            android_user_id=999,
            package_name="com.whatsapp",
            remote_db_dir="/storage/emulated/999/WhatsApp/Databases/",
            latest_backup_file="msgstore.db.crypt14",
            latest_backup_size_mb=187.8,
            latest_backup_date="2026-09-25 02:00",
            crypt_format="crypt14",
            is_dual=True,
        ),
    ]
    monkeypatch.setattr("src.device_manager.DeviceManager.list_whatsapp_accounts", lambda self, s=None: mock_accounts)

    args = argparse.Namespace(command="accounts", serial=None)
    assert cmd_accounts(args) == 0
    captured = capsys.readouterr()
    assert "principal" in captured.out
    assert "dual_xiaomi" in captured.out
    assert "POCO X3 Pro" in captured.out

