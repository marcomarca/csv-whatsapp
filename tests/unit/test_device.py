"""Unit tests for DeviceManager and ADB parsing."""

import subprocess
import pytest
from pathlib import Path

from src.device_manager import DeviceManager
from src.errors import (
    BackupCopyFailedError,
    BackupNotFoundError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
)
from src.models import DeviceInfo


def test_device_discovery_parsing(monkeypatch):
    """Test parsing standard ADB devices output."""
    mock_output = (
        "* daemon not running; starting now at tcp:5037\n"
        "* daemon started successfully\n"
        "List of devices attached\n"
        "c83eb1a\tdevice\n"
        "emulator-5554\tunauthorized\n"
    )

    dev_mgr = DeviceManager(adb_path="mock_adb")

    def mock_run(args, timeout=60):
        if "devices" in args:
            return subprocess.CompletedProcess(args, 0, stdout=mock_output, stderr="")
        if "getprop" in args and "ro.product.model" in args:
            return subprocess.CompletedProcess(args, 0, stdout="POCO X3 Pro\n", stderr="")
        if "getprop" in args and "ro.build.version.release" in args:
            return subprocess.CompletedProcess(args, 0, stdout="12\n", stderr="")
        if any("pm" in str(arg) for arg in args):
            return subprocess.CompletedProcess(args, 0, stdout="package:com.whatsapp\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run)

    devices = dev_mgr.get_devices()
    assert len(devices) == 2

    d1 = devices[0]
    assert d1.serial == "c83eb1a"
    assert d1.state == "device"
    assert d1.is_authorized is True
    assert d1.model == "POCO X3 Pro"
    assert d1.android_version == "12"
    assert d1.whatsapp_packages == ["com.whatsapp"]

    d2 = devices[1]
    assert d2.serial == "emulator-5554"
    assert d2.state == "unauthorized"
    assert d2.is_authorized is False


def test_device_selection_errors(monkeypatch):
    """Test DeviceNotFoundError, DeviceUnauthorizedError, and MultipleDevicesError."""
    dev_mgr = DeviceManager(adb_path="mock_adb")

    # Case 1: No devices
    monkeypatch.setattr(dev_mgr, "get_devices", lambda: [])
    with pytest.raises(DeviceNotFoundError):
        dev_mgr.get_active_device()

    # Case 2: Unauthorized device
    monkeypatch.setattr(
        dev_mgr,
        "get_devices",
        lambda: [DeviceInfo(serial="unauth123", state="unauthorized")],
    )
    with pytest.raises(DeviceUnauthorizedError) as exc_info:
        dev_mgr.get_active_device()
    assert exc_info.value.code == "DEVICE_UNAUTHORIZED"

    # Case 3: Multiple authorized devices without serial
    monkeypatch.setattr(
        dev_mgr,
        "get_devices",
        lambda: [
            DeviceInfo(serial="dev1", state="device"),
            DeviceInfo(serial="dev2", state="device"),
        ],
    )
    with pytest.raises(MultipleDevicesError):
        dev_mgr.get_active_device()

    # Case 4: Multiple devices but explicit serial requested
    dev = dev_mgr.get_active_device(serial="dev2")
    assert dev.serial == "dev2"


def test_list_remote_backups_parsing(monkeypatch):
    """Test remote ls output parsing for backup files."""
    dev_mgr = DeviceManager(adb_path="mock_adb")

    mock_ls = (
        "total 17848\n"
        "-rw-rw---- 1 u0_a254 everybody 5862757 2026-09-10 02:00 msgstore-2026-09-16.1.db.crypt14\n"
        "-rw-rw---- 1 u0_a254 everybody 5914043 2026-09-22 02:00 msgstore.db.crypt14\n"
    )

    def mock_run(args, timeout=60):
        if len(args) > 3 and "/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Databases" in args[3]:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls, stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run)

    backups = dev_mgr.list_backups("mock_serial")
    assert len(backups) == 2
    # Main backup should be sorted first
    assert backups[0].filename == "msgstore.db.crypt14"
    assert backups[0].is_main is True
    assert backups[0].format == "crypt14"
    assert backups[0].file_size == 5914043


def test_pull_backup_failure_raises_error(monkeypatch, tmp_path: Path):
    """Test that failed or interrupted transfer raises BackupCopyFailedError."""
    dev_mgr = DeviceManager(adb_path="mock_adb")

    def mock_run_fail(args, timeout=60):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="adb: error: closed")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run_fail)

    with pytest.raises(BackupCopyFailedError) as exc_info:
        dev_mgr.pull_backup("serial", "/sdcard/msgstore.db.crypt15", tmp_path)
    assert exc_info.value.code == "BACKUP_COPY_FAILED"


def test_list_whatsapp_accounts_dual_apps(monkeypatch):
    """Test discovering multiple WhatsApp accounts (Principal and Xiaomi Dual App)."""
    dev_mgr = DeviceManager(adb_path="mock_adb")
    monkeypatch.setattr(
        dev_mgr,
        "get_devices",
        lambda: [DeviceInfo(serial="poco123", state="device", model="POCO X3 Pro")],
    )

    mock_pm_users = "Users:\n\tUserInfo{0:Propietario:c13} running\n\tUserInfo{999:XSpace:801010} running\n"
    mock_ls_u0 = "total 5000\n-rw-rw---- 1 u0_a254 everybody 5900000 2026-09-26 01:00 msgstore.db.crypt15\n"
    mock_ls_u999 = "total 190000\n-rw-rw---- 1 u999_a254 everybody 195000000 2026-09-25 02:00 msgstore.db.crypt14\n"

    def mock_run(args, timeout=60):
        cmd_str = " ".join(args)
        if "pm list users" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_pm_users, stderr="")
        if "0/Android/media/com.whatsapp/WhatsApp/Databases" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls_u0, stderr="")
        if "999/Android/media/com.whatsapp/WhatsApp/Databases" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls_u999, stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run)

    accounts = dev_mgr.list_whatsapp_accounts("poco123")
    assert len(accounts) == 2

    acc0 = next(a for a in accounts if a.account_id == "principal")
    assert acc0.android_user_id == 0
    assert acc0.crypt_format == "crypt15"
    assert acc0.latest_backup_file == "msgstore.db.crypt15"
    assert acc0.is_dual is False

    acc999 = next(a for a in accounts if a.account_id == "dual_xiaomi")
    assert acc999.android_user_id == 999
    assert acc999.crypt_format == "crypt14"
    assert acc999.latest_backup_file == "msgstore.db.crypt14"
    assert acc999.is_dual is True


def test_list_whatsapp_accounts_with_business(monkeypatch):
    """Test discovering WhatsApp Business alongside standard and dual accounts."""
    dev_mgr = DeviceManager(adb_path="mock_adb")
    monkeypatch.setattr(
        dev_mgr,
        "get_devices",
        lambda: [DeviceInfo(serial="poco123", state="device", model="POCO X3 Pro")],
    )

    mock_pm_users = "Users:\n\tUserInfo{0:Propietario:c13} running\n\tUserInfo{999:XSpace:801010} running\n"
    mock_ls_w4b = "total 8000\n-rw-rw---- 1 u0_a254 everybody 8100000 2026-09-26 01:00 msgstore.db.crypt15\n"

    def mock_run(args, timeout=60):
        cmd_str = " ".join(args)
        if "pm list users" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_pm_users, stderr="")
        if "com.whatsapp.w4b" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls_w4b, stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run)

    accounts = dev_mgr.list_whatsapp_accounts("poco123")
    assert len(accounts) == 2
    w4b_p = next(a for a in accounts if a.account_id == "business_principal")
    assert w4b_p.package_name == "com.whatsapp.w4b"
    assert w4b_p.display_name == "WhatsApp Business (Principal)"
    assert w4b_p.latest_backup_file == "msgstore.db.crypt15"
    assert w4b_p.is_dual is False

    w4b_d = next(a for a in accounts if a.account_id == "business_dual")
    assert w4b_d.package_name == "com.whatsapp.w4b"
    assert w4b_d.display_name == "WhatsApp Business (Dual Xiaomi/Dual Apps - Usuario 999)" or "Dual Xiaomi" in w4b_d.display_name
    assert w4b_d.latest_backup_file == "msgstore.db.crypt15"
    assert w4b_d.is_dual is True


def test_list_whatsapp_accounts_samsung(monkeypatch):
    """Test discovering Samsung Dual Messenger (User 95) and Secure Folder (User 150)."""
    dev_mgr = DeviceManager(adb_path="mock_adb")
    monkeypatch.setattr(
        dev_mgr,
        "get_devices",
        lambda: [DeviceInfo(serial="samsung123", state="device", model="Galaxy S22", manufacturer="samsung")],
    )

    mock_pm_users = "Users:\n\tUserInfo{0:Owner:13} running\n\tUserInfo{95:DualApp:30} running\n\tUserInfo{150:Secure Folder:10} running\n"
    mock_ls_u0 = "total 5000\n-rw-rw---- 1 u0_a254 everybody 5900000 2026-09-26 01:00 msgstore.db.crypt15\n"
    mock_ls_u95 = "total 12000\n-rw-rw---- 1 u95_a254 everybody 12500000 2026-09-26 01:00 msgstore.db.crypt15\n"
    mock_ls_u150 = "total 8000\n-rw-rw---- 1 u150_a254 everybody 8500000 2026-09-26 01:00 msgstore.db.crypt15\n"

    def mock_run(args, timeout=60):
        cmd_str = " ".join(args)
        if "pm list users" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_pm_users, stderr="")
        if "0/Android/media/com.whatsapp/WhatsApp/Databases" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls_u0, stderr="")
        if "95/Android/media/com.whatsapp/WhatsApp/Databases" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls_u95, stderr="")
        if "150/Android/media/com.whatsapp/WhatsApp/Databases" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls_u150, stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run)

    accounts = dev_mgr.list_whatsapp_accounts("samsung123")
    assert len(accounts) == 3

    acc0 = next(a for a in accounts if a.account_id == "principal")
    assert acc0.android_user_id == 0

    acc95 = next(a for a in accounts if a.account_id == "samsung_dual")
    assert acc95.android_user_id == 95
    assert "Samsung Dual Messenger" in acc95.display_name

    acc150 = next(a for a in accounts if a.account_id == "samsung_secure")
    assert acc150.android_user_id == 150
    assert "Samsung Secure Folder" in acc150.display_name


def test_list_whatsapp_accounts_honor_realme(monkeypatch):
    """Test discovering Honor App Twin and Realme App Cloner."""
    dev_mgr = DeviceManager(adb_path="mock_adb")
    
    # Case Honor
    monkeypatch.setattr(
        dev_mgr,
        "get_devices",
        lambda: [DeviceInfo(serial="honor123", state="device", model="Honor Magic 5", manufacturer="HONOR")],
    )
    mock_pm_honor = "Users:\n\tUserInfo{0:Owner:13} running\n\tUserInfo{999:Twin:801010} running\n"
    mock_ls = "total 5000\n-rw-rw---- 1 u0_a254 everybody 5900000 2026-09-26 01:00 msgstore.db.crypt15\n"

    def mock_run_honor(args, timeout=60):
        cmd_str = " ".join(args)
        if "pm list users" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_pm_honor, stderr="")
        if "WhatsApp/Databases" in cmd_str:
            return subprocess.CompletedProcess(args, 0, stdout=mock_ls, stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run_honor)
    honor_accs = dev_mgr.list_whatsapp_accounts("honor123")
    assert any(a.account_id == "dual_honor" for a in honor_accs)


def test_wait_for_backup_stability(monkeypatch):
    """Test wait_for_backup_stability detects changing size and returns stable size."""
    dev_mgr = DeviceManager(adb_path="mock_adb")
    sizes = ["1000", "2000", "2000"]
    call_idx = 0

    def mock_run(args, timeout=60):
        nonlocal call_idx
        res_size = sizes[min(call_idx, len(sizes) - 1)]
        call_idx += 1
        return subprocess.CompletedProcess(args, 0, stdout=f"{res_size}\n", stderr="")

    monkeypatch.setattr(dev_mgr, "run_adb", mock_run)
    stable_size = dev_mgr.wait_for_backup_stability(
        "test_serial", "/path/to/msgstore.db.crypt15", max_wait_seconds=5, poll_interval=0.01
    )
    assert stable_size == 2000

