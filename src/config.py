"""Application configuration and environment settings."""

import os
import shutil
from pathlib import Path


class AppConfig:
    """Configuration paths and settings."""

    # Base workspace paths
    ROOT_DIR: Path = Path(__file__).resolve().parent.parent
    SRC_DIR: Path = ROOT_DIR / "src"
    VENDOR_DIR: Path = ROOT_DIR / "vendor"
    WHAPA_LIBS_DIR: Path = VENDOR_DIR / "whapa" / "libs"

    DATA_DIR: Path = ROOT_DIR / "data"
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
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Databases/",
        "/sdcard/WhatsApp/Databases/",
        "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Databases/",
    )

    REMOTE_MEDIA_DIRS: tuple[str, ...] = (
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/",
        "/sdcard/WhatsApp/Media/",
        "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media/",
    )

    # ADB executable detection
    @classmethod
    def get_adb_path(cls) -> str:
        """Find the adb executable path on the system."""
        # 1. Explicit env var
        env_adb = os.environ.get("ADB_PATH")
        if env_adb and os.path.isfile(env_adb):
            return env_adb

        # 2. Check PATH
        path_adb = shutil.which("adb")
        if path_adb:
            return path_adb

        # 3. Check standard Windows Android SDK location
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            standard_win_adb = (
                Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
            )
            if standard_win_adb.is_file():
                return str(standard_win_adb)

        # 4. Fallback default
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
