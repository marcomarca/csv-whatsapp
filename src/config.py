import os
import shutil
import sys
from pathlib import Path


class AppConfig:
    """Configuration paths and settings."""

    # Base workspace paths supporting normal run and PyInstaller bundle
    if getattr(sys, "frozen", False):
        BUNDLE_DIR: Path = Path(sys._MEIPASS)
        APP_DIR: Path = Path(sys.executable).resolve().parent
    else:
        BUNDLE_DIR: Path = Path(__file__).resolve().parent.parent
        APP_DIR: Path = Path(__file__).resolve().parent.parent

    ROOT_DIR: Path = APP_DIR
    SRC_DIR: Path = BUNDLE_DIR / "src"

    # Vendor directory (bundled in frozen app or local)
    _bundled_vendor = BUNDLE_DIR / "vendor"
    _local_vendor = APP_DIR / "vendor"
    VENDOR_DIR: Path = _bundled_vendor if _bundled_vendor.exists() else _local_vendor
    WHAPA_LIBS_DIR: Path = VENDOR_DIR / "whapa" / "libs"

    DATA_DIR: Path = APP_DIR / "data"
    BACKUPS_DIR: Path = DATA_DIR / "backups"
    WORKING_DIR: Path = DATA_DIR / "working"
    EXPORTS_DIR: Path = DATA_DIR / "exports"
    CONVERSATIONS_CSV_DIR: Path = EXPORTS_DIR / "conversations"
    LOGS_DIR: Path = DATA_DIR / "logs"
    MEDIA_DIR: Path = DATA_DIR / "media"
    VAULT_DB_PATH: Path = WORKING_DIR / "whatsapp_vault.db"

    # Security / Keyring
    KEYRING_SERVICE_NAME: str = "whatsapp_backup_csv"

    # Remote paths on Android device
    REMOTE_WHATSAPP_PACKAGES: tuple[str, ...] = (
        "com.whatsapp",
        "com.whatsapp.w4b",
    )

    REMOTE_BACKUP_DIRS: tuple[str, ...] = (
        "/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Databases/",
        "/storage/emulated/0/WhatsApp/Databases/",
        "/storage/emulated/999/Android/media/com.whatsapp/WhatsApp/Databases/",
        "/storage/emulated/999/WhatsApp/Databases/",
        "/storage/emulated/0/Android/media/com.whatsapp.w4b/WhatsApp Business/Databases/",
        "/storage/emulated/999/Android/media/com.whatsapp.w4b/WhatsApp Business/Databases/",
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Databases/",
        "/sdcard/WhatsApp/Databases/",
    )

    REMOTE_MEDIA_DIRS: tuple[str, ...] = (
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/",
        "/sdcard/WhatsApp/Media/",
        "/storage/emulated/999/Android/media/com.whatsapp/WhatsApp/Media/",
        "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media/",
    )

    # ADB executable detection
    @classmethod
    def get_adb_path(cls, auto_download: bool = True) -> str:
        """Find or automatically install the adb executable path on the system."""
        try:
            from src.adb_installer import ensure_adb

            return ensure_adb(auto_download=auto_download)
        except Exception:
            # Fallback to local search
            vendor_adb = cls.VENDOR_DIR / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if vendor_adb.is_file():
                return str(vendor_adb)
            path_adb = shutil.which("adb")
            if path_adb:
                return path_adb
            return "adb"

    @classmethod
    def ensure_directories(cls) -> None:
        """Create all required data and cache directories if they don't exist."""
        for d in (
            cls.DATA_DIR,
            cls.BACKUPS_DIR,
            cls.WORKING_DIR,
            cls.EXPORTS_DIR,
            cls.CONVERSATIONS_CSV_DIR,
            cls.LOGS_DIR,
            cls.MEDIA_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)
