"""Automatic detection, validation, and installation of Android SDK Platform Tools (ADB)."""

import io
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from src.config import AppConfig

logger = logging.getLogger(__name__)

# Official Google Android SDK Platform Tools URLs
GOOGLE_PLATFORM_TOOLS_URLS = {
    "Windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "Linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
    "Darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
}


def is_valid_adb(executable_path: str | Path) -> bool:
    """Test if the given path is a working ADB binary."""
    p = Path(executable_path)
    if not p.is_file():
        return False
    try:
        res = subprocess.run(
            [str(p), "version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return res.returncode == 0 and "Android Debug Bridge" in (res.stdout or "")
    except Exception:
        return False


def find_existing_adb() -> str | None:
    """Search for an existing valid ADB executable across known locations."""
    # 1. Environment variable
    env_adb = os.environ.get("ADB_PATH")
    if env_adb and is_valid_adb(env_adb):
        return env_adb

    # 2. Bundled in vendor/platform-tools
    exe_name = "adb.exe" if platform.system() == "Windows" else "adb"
    bundled_adb = AppConfig.VENDOR_DIR / "platform-tools" / exe_name
    if is_valid_adb(bundled_adb):
        return str(bundled_adb)

    # 3. System PATH
    path_adb = shutil.which("adb")
    if path_adb and is_valid_adb(path_adb):
        return path_adb

    # 4. Standard OS-specific SDK locations
    candidates: list[Path] = []
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(
                Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
            )
        candidates.extend(
            [
                Path("C:/platform-tools/adb.exe"),
                Path("C:/tools/platform-tools/adb.exe"),
                Path("C:/scrcpy/adb.exe"),
                Path("C:/Program Files/platform-tools/adb.exe"),
                Path("C:/Program Files (x86)/platform-tools/adb.exe"),
            ]
        )
    elif platform.system() == "Darwin":
        home = Path.home()
        candidates.extend(
            [
                home / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
                Path("/opt/homebrew/bin/adb"),
                Path("/usr/local/bin/adb"),
            ]
        )
    else:  # Linux
        home = Path.home()
        candidates.extend(
            [
                home / "Android" / "Sdk" / "platform-tools" / "adb",
                Path("/usr/bin/adb"),
                Path("/usr/local/bin/adb"),
            ]
        )

    for cand in candidates:
        if is_valid_adb(cand):
            return str(cand)

    return None


def download_and_install_platform_tools(target_dir: Path | None = None) -> str:
    """Download official Google Android Platform-Tools zip and extract to vendor directory."""
    target_dir = target_dir or (AppConfig.VENDOR_DIR / "platform-tools")
    vendor_root = target_dir.parent
    vendor_root.mkdir(parents=True, exist_ok=True)

    system_name = platform.system()
    url = GOOGLE_PLATFORM_TOOLS_URLS.get(system_name)
    if not url:
        raise RuntimeError(f"Sistema operativo no soportado para descarga automática de ADB: {system_name}")

    exe_name = "adb.exe" if system_name == "Windows" else "adb"
    expected_exe = target_dir / exe_name

    logger.info(f"Descargando Android SDK Platform-Tools oficial desde {url}...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "WhatsApp-Backup-CSV/1.0 (Android-Tools-Downloader)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            zip_bytes = response.read()

        logger.info(f"Descarga completada ({len(zip_bytes) // 1024} KB). Extrayendo archivos...")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            z.extractall(vendor_root)

        if system_name != "Windows" and expected_exe.is_file():
            current_stat = expected_exe.stat().st_mode
            expected_exe.chmod(current_stat | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        if not is_valid_adb(expected_exe):
            raise RuntimeError(f"El binario extraído en '{expected_exe}' no superó la prueba de validación.")

        logger.info(f"Android SDK Platform-Tools instalado exitosamente en: {expected_exe}")
        return str(expected_exe)

    except Exception as e:
        logger.error(f"Error durante la descarga o instalación automática de ADB: {e}")
        raise


def ensure_adb(auto_download: bool = True) -> str:
    """Ensure ADB is available, finding existing install or downloading automatically."""
    found = find_existing_adb()
    if found:
        return found

    if auto_download:
        logger.warning("ADB no encontrado en el sistema. Iniciando descarga e instalación automática...")
        return download_and_install_platform_tools()

    exe_name = "adb.exe" if platform.system() == "Windows" else "adb"
    return exe_name


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    adb = ensure_adb(auto_download=True)
    print(f"ADB listo para usar: {adb}")
