"""DeviceManager handles ADB discovery, authorization checks, and remote file transfers."""

import hashlib
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from src.config import AppConfig
from src.errors import (
    BackupCopyFailedError,
    BackupNotFoundError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
)
from src.models import DeviceInfo, RemoteBackupInfo

logger = logging.getLogger(__name__)


class DeviceManager:
    """Interface to communicate with Android devices via ADB."""

    def __init__(self, adb_path: str | None = None):
        self.adb_path = adb_path or AppConfig.get_adb_path()

    def run_adb(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        """Execute an ADB command safely with arguments array."""
        cmd = [self.adb_path] + args
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return res
        except FileNotFoundError:
            raise DeviceNotFoundError(
                operation="run_adb",
                message=f"No se encontró el ejecutable de ADB en '{self.adb_path}'.",
                action_recommended="Verifica que Android SDK Platform Tools esté instalado o añade adb al PATH.",
            )
        except subprocess.TimeoutExpired:
            raise BackupCopyFailedError(
                source="adb_command",
                target="local",
                reason=f"La operación ADB excedió el tiempo límite ({timeout}s).",
                operation="run_adb",
            )

    def get_devices(self) -> list[DeviceInfo]:
        """List all attached devices and their ADB states."""
        res = self.run_adb(["devices"])
        if res.returncode != 0:
            logger.error(f"adb devices error: {res.stderr}")
            return []

        devices: list[DeviceInfo] = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith(("*", "List of devices")):
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial, state = parts[0], parts[1]
                dev = DeviceInfo(serial=serial, state=state)
                if state == "device":
                    self._populate_device_details(dev)
                devices.append(dev)

        return devices

    def _populate_device_details(self, dev: DeviceInfo) -> None:
        """Fetch model, Android OS version, and WhatsApp packages for an authorized device."""
        # 1. Model
        model_res = self.run_adb(["-s", dev.serial, "shell", "getprop", "ro.product.model"])
        if model_res.returncode == 0:
            dev.model = model_res.stdout.strip()

        # 2. Android Version
        ver_res = self.run_adb(["-s", dev.serial, "shell", "getprop", "ro.build.version.release"])
        if ver_res.returncode == 0:
            dev.android_version = ver_res.stdout.strip()

        # 3. WhatsApp packages
        pkg_res = self.run_adb(["-s", dev.serial, "shell", "pm", "list", "packages"])
        if pkg_res.returncode == 0:
            installed = []
            for pkg in AppConfig.REMOTE_WHATSAPP_PACKAGES:
                if f"package:{pkg}" in pkg_res.stdout:
                    installed.append(pkg)
            dev.whatsapp_packages = installed

    def get_active_device(self, serial: str | None = None) -> DeviceInfo:
        """Get the target authorized device or raise an appropriate structured error."""
        devices = self.get_devices()

        if not devices:
            raise DeviceNotFoundError()

        if serial:
            matching = [d for d in devices if d.serial == serial]
            if not matching:
                raise DeviceNotFoundError(
                    message=f"No se encontró el dispositivo con número de serie '{serial}'."
                )
            dev = matching[0]
        else:
            if len(devices) > 1:
                authorized = [d for d in devices if d.is_authorized]
                if len(authorized) == 1:
                    dev = authorized[0]
                else:
                    raise MultipleDevicesError(devices=[d.serial for d in devices])
            else:
                dev = devices[0]

        if not dev.is_authorized:
            raise DeviceUnauthorizedError(serial=dev.serial)

        return dev

    def list_backups(self, serial: str) -> list[RemoteBackupInfo]:
        """Discover all WhatsApp backup files on the device."""
        found: list[RemoteBackupInfo] = []

        for base_dir in AppConfig.REMOTE_BACKUP_DIRS:
            # Use 'ls -la' or 'ls -l' to inspect directory
            res = self.run_adb(["-s", serial, "shell", f"ls -la '{base_dir}' 2>/dev/null"])
            if res.returncode != 0 or not res.stdout.strip():
                continue

            for line in res.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith(("total", "d")):
                    continue

                # Match files like msgstore.db.crypt15, msgstore-2026-09-22.1.db.crypt14, msgstore.db.crypt14
                match = re.search(r"(msgstore[^\s]*\.db\.crypt(\d+))", line)
                if not match:
                    continue

                filename = match.group(1)
                crypt_num = match.group(2)
                remote_path = f"{base_dir.rstrip('/')}/{filename}"

                # Extract file size and date if available
                parts = line.split()
                file_size = 0
                mod_date = ""

                # Example ls line: -rw-rw---- 1 u0_a254 everybody 5914043 2026-09-22 02:00 msgstore.db.crypt14
                try:
                    for i, p in enumerate(parts):
                        if p == filename:
                            if i >= 3:
                                file_size = int(parts[i - 3])
                                mod_date = f"{parts[i - 2]} {parts[i - 1]}"
                            break
                except (ValueError, IndexError):
                    pass

                is_main = filename in (
                    f"msgstore.db.crypt{crypt_num}",
                    "msgstore.db.crypt15",
                    "msgstore.db.crypt14",
                    "msgstore.db.crypt12",
                )

                found.append(
                    RemoteBackupInfo(
                        remote_path=remote_path,
                        filename=filename,
                        file_size=file_size,
                        modified_at=mod_date,
                        format=f"crypt{crypt_num}",
                        is_main=is_main,
                    )
                )

        if not found:
            raise BackupNotFoundError(searched_paths=list(AppConfig.REMOTE_BACKUP_DIRS))

        # Sort: main backups first (msgstore.db.crypt*), then descending modification date
        found.sort(key=lambda b: (1 if b.is_main else 0, b.modified_at, b.filename), reverse=True)
        return found

    def pull_backup(
        self,
        serial: str,
        remote_path: str,
        destination_dir: Path,
    ) -> tuple[Path, str]:
        """Pull a backup file from the device safely to destination_dir and verify SHA-256."""
        destination_dir.mkdir(parents=True, exist_ok=True)
        filename = os.path.basename(remote_path)
        temp_dest = destination_dir / f"{filename}.tmp_{os.getpid()}"

        logger.info(f"Transferring {remote_path} from device {serial} to {temp_dest}...")
        res = self.run_adb(["-s", serial, "pull", remote_path, str(temp_dest)], timeout=180)

        if res.returncode != 0 or not temp_dest.exists() or temp_dest.stat().st_size == 0:
            if temp_dest.exists():
                temp_dest.unlink(missing_ok=True)
            raise BackupCopyFailedError(
                source=remote_path,
                target=str(temp_dest),
                reason=res.stderr or "El archivo transferido está vacío o no se creó.",
            )

        # Calculate SHA-256 hash
        hasher = hashlib.sha256()
        with open(temp_dest, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        sha256_hash = hasher.hexdigest()

        # Atomic move to unique backup name incorporating hash prefix
        final_dest = destination_dir / f"{sha256_hash[:12]}_{filename}"
        if final_dest.exists():
            final_dest.unlink()
        shutil.move(str(temp_dest), str(final_dest))

        logger.info(f"Backup transfer completed: {final_dest} (SHA256: {sha256_hash})")
        return final_dest, sha256_hash

    def pull_media(
        self,
        serial: str,
        local_media_dir: Path,
    ) -> int:
        """Pull media folder from Android device if present."""
        local_media_dir.mkdir(parents=True, exist_ok=True)
        pulled_count = 0

        for remote_media in AppConfig.REMOTE_MEDIA_DIRS:
            res = self.run_adb(["-s", serial, "shell", f"ls '{remote_media}' 2>/dev/null"])
            if res.returncode == 0 and res.stdout.strip():
                logger.info(f"Pulling media from {remote_media} to {local_media_dir}...")
                pull_res = self.run_adb(
                    ["-s", serial, "pull", remote_media.rstrip("/"), str(local_media_dir)],
                    timeout=600,
                )
                if pull_res.returncode == 0:
                    pulled_count += 1
                break

        return pulled_count
