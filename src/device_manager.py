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
from src.models import DeviceInfo, RemoteBackupInfo, WhatsAppAccount

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
        """Fetch model, manufacturer, brand, Android OS version, and WhatsApp packages for an authorized device."""
        # 1. Model
        model_res = self.run_adb(["-s", dev.serial, "shell", "getprop", "ro.product.model"])
        if model_res.returncode == 0:
            dev.model = model_res.stdout.strip()

        # 2. Manufacturer & Brand
        mfg_res = self.run_adb(["-s", dev.serial, "shell", "getprop", "ro.product.manufacturer"])
        if mfg_res.returncode == 0:
            dev.manufacturer = mfg_res.stdout.strip()

        brand_res = self.run_adb(["-s", dev.serial, "shell", "getprop", "ro.product.brand"])
        if brand_res.returncode == 0:
            dev.brand = brand_res.stdout.strip()

        # 3. Android Version
        ver_res = self.run_adb(["-s", dev.serial, "shell", "getprop", "ro.build.version.release"])
        if ver_res.returncode == 0:
            dev.android_version = ver_res.stdout.strip()

        # 4. WhatsApp packages across known OEM user profiles
        installed = set()
        for user_id in (0, 95, 96, 150, 999, 10):
            pkg_res = self.run_adb(
                ["-s", dev.serial, "shell", f"pm list packages --user {user_id}"]
            )
            if pkg_res.returncode == 0:
                for pkg in AppConfig.REMOTE_WHATSAPP_PACKAGES:
                    if f"package:{pkg}" in pkg_res.stdout:
                        installed.add(pkg)
        dev.whatsapp_packages = sorted(list(installed))

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

    def list_whatsapp_accounts(self, serial: str | None = None) -> list[WhatsAppAccount]:
        """Discover all WhatsApp accounts across OEMs (Samsung, Xiaomi, Honor, Realme, Oppo, Vivo, generic multi-user)."""
        dev = self.get_active_device(serial)
        accounts: list[WhatsAppAccount] = []
        user_labels: dict[int, str] = {0: "Principal"}

        # 1. Discover Android user IDs via pm list users
        user_ids = [0]
        users_res = self.run_adb(["-s", dev.serial, "shell", "pm", "list", "users"])
        if users_res.returncode == 0:
            for match in re.finditer(r"UserInfo\{(\d+):([^:]*):", users_res.stdout):
                uid = int(match.group(1))
                label = match.group(2).strip()
                user_labels[uid] = label
                if uid not in user_ids:
                    user_ids.append(uid)

        # 2. Filesystem probe for OEM storage directories
        # Probe Samsung Dual Messenger (95, 96), Knox Secure Folder (150, 151), Xiaomi/Honor/Realme (999), Work (10, 11)
        common_uids = (95, 96, 150, 151, 999, 10, 11, 12)
        for check_uid in common_uids:
            if check_uid not in user_ids:
                check_res = self.run_adb(
                    ["-s", dev.serial, "shell", f"ls -d /storage/emulated/{check_uid}/ 2>/dev/null"]
                )
                if check_res.returncode == 0 and str(check_uid) in check_res.stdout:
                    user_ids.append(check_uid)

        mfg = (dev.manufacturer or dev.brand or "").lower()

        # 3. Check candidate directories for each user profile and package
        seen_dirs = set()
        for uid in sorted(user_ids):
            user_label = user_labels.get(uid, "")
            user_label_lower = user_label.lower()

            for pkg in AppConfig.REMOTE_WHATSAPP_PACKAGES:
                is_business = pkg == "com.whatsapp.w4b"
                subfolder = "WhatsApp Business" if is_business else "WhatsApp"

                candidate_dirs = [
                    f"/storage/emulated/{uid}/Android/media/{pkg}/{subfolder}/Databases/",
                    f"/storage/emulated/{uid}/{subfolder}/Databases/",
                ]
                if uid == 0:
                    candidate_dirs.append(f"/sdcard/Android/media/{pkg}/{subfolder}/Databases/")
                    candidate_dirs.append(f"/sdcard/{subfolder}/Databases/")

                for cdir in candidate_dirs:
                    if cdir in seen_dirs:
                        continue

                    res = self.run_adb(["-s", dev.serial, "shell", f"ls -la '{cdir}' 2>/dev/null"])
                    if res.returncode == 0 and res.stdout.strip():
                        backups = self._parse_ls_output(res.stdout, cdir)
                        if backups:
                            seen_dirs.add(cdir)
                            latest = backups[0]
                            is_dual = uid != 0

                            # Determine semantic account ID and display name
                            if uid == 0:
                                if is_business:
                                    account_id = "business_principal"
                                    display_name = "WhatsApp Business (Principal)"
                                else:
                                    account_id = "principal"
                                    display_name = "WhatsApp (Principal - Usuario 0)"
                            elif "samsung" in mfg or uid in (95, 96) or "dualapp" in user_label_lower:
                                if uid in (95, 96) or "dualapp" in user_label_lower:
                                    account_id = "business_samsung_dual" if is_business else "samsung_dual"
                                    display_name = f"WhatsApp {'Business ' if is_business else ''}(Samsung Dual Messenger - Usuario {uid})"
                                elif uid >= 150 or "secure" in user_label_lower or "knox" in user_label_lower:
                                    account_id = "business_samsung_secure" if is_business else "samsung_secure"
                                    display_name = f"WhatsApp {'Business ' if is_business else ''}(Samsung Secure Folder - Usuario {uid})"
                                else:
                                    account_id = f"{'business_' if is_business else ''}samsung_user_{uid}"
                                    display_name = f"WhatsApp {'Business ' if is_business else ''}(Samsung Perfil {uid})"
                            elif "honor" in mfg or "huawei" in mfg or "twin" in user_label_lower:
                                account_id = "business_dual_honor" if is_business else "dual_honor"
                                display_name = f"WhatsApp {'Business ' if is_business else ''}(Honor App Twin - Usuario {uid})"
                            elif "realme" in mfg or "oppo" in mfg or "oneplus" in mfg or "clone" in user_label_lower:
                                brand_name = "Realme" if "realme" in mfg else ("OnePlus" if "oneplus" in mfg else "Oppo")
                                account_id = f"{'business_' if is_business else ''}dual_{brand_name.lower()}"
                                display_name = f"WhatsApp {'Business ' if is_business else ''}({brand_name} App Cloner - Usuario {uid})"
                            elif "vivo" in mfg or "iqoo" in mfg:
                                account_id = "business_dual_vivo" if is_business else "dual_vivo"
                                display_name = f"WhatsApp {'Business ' if is_business else ''}(Vivo App Clone - Usuario {uid})"
                            elif uid == 999:
                                # Xiaomi / General Dual App fallback (maintains exact compatibility with dual_xiaomi)
                                account_id = "business_dual" if is_business else "dual_xiaomi"
                                display_name = f"WhatsApp {'Business ' if is_business else ''}(Dual Xiaomi/Dual Apps - Usuario {uid})"
                            else:
                                account_id = f"{'business_' if is_business else ''}user_{uid}"
                                display_name = f"WhatsApp {'Business ' if is_business else ''}(Usuario {uid})"

                            acc = WhatsAppAccount(
                                account_id=account_id,
                                display_name=display_name,
                                android_user_id=uid,
                                package_name=pkg,
                                remote_db_dir=cdir,
                                device_serial=dev.serial,
                                manufacturer=dev.manufacturer or dev.brand or "Android",
                                latest_backup_file=latest.filename,
                                latest_backup_size_mb=round(latest.file_size / (1024 * 1024), 2),
                                latest_backup_date=latest.modified_at,
                                crypt_format=latest.format,
                                is_dual=is_dual,
                            )
                            if not any(a.account_id == acc.account_id for a in accounts):
                                accounts.append(acc)
                            break

        return accounts

    def get_account(
        self,
        serial: str | None = None,
        account_id: str = "principal",
    ) -> WhatsAppAccount:
        """Get a specific WhatsApp account profile by account_id, or raise BackupNotFoundError."""
        accounts = self.list_whatsapp_accounts(serial)
        for acc in accounts:
            if acc.account_id == account_id:
                return acc

        # Fallback match on prefix or first account if default requested
        if account_id == "principal" and accounts:
            return accounts[0]

        raise BackupNotFoundError(
            searched_paths=[a.remote_db_dir for a in accounts]
            or list(AppConfig.REMOTE_BACKUP_DIRS)
        )

    def _parse_ls_output(self, ls_stdout: str, base_dir: str) -> list[RemoteBackupInfo]:
        """Parse ls -la output to extract RemoteBackupInfo records."""
        found: list[RemoteBackupInfo] = []
        for line in ls_stdout.splitlines():
            line = line.strip()
            if not line or line.startswith(("total", "d")):
                continue

            match = re.search(r"(msgstore[^\s]*\.db\.crypt(\d+))", line)
            if not match:
                continue

            filename = match.group(1)
            crypt_num = match.group(2)
            remote_path = f"{base_dir.rstrip('/')}/{filename}"

            parts = line.split()
            file_size = 0
            mod_date = ""

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

        found.sort(key=lambda b: (1 if b.is_main else 0, b.modified_at, b.filename), reverse=True)
        return found

    def list_backups(
        self, serial: str, account_id: str | None = None
    ) -> list[RemoteBackupInfo]:
        """Discover all WhatsApp backup files on the device (optionally filtered by account)."""
        if account_id:
            try:
                acc = self.get_account(serial, account_id)
                res = self.run_adb(
                    ["-s", serial, "shell", f"ls -la '{acc.remote_db_dir}' 2>/dev/null"]
                )
                if res.returncode == 0 and res.stdout.strip():
                    backups = self._parse_ls_output(res.stdout, acc.remote_db_dir)
                    if backups:
                        return backups
            except Exception as e:
                logger.warning(f"Error listing backups for account {account_id}: {e}")

        found: list[RemoteBackupInfo] = []
        for base_dir in AppConfig.REMOTE_BACKUP_DIRS:
            res = self.run_adb(["-s", serial, "shell", f"ls -la '{base_dir}' 2>/dev/null"])
            if res.returncode != 0 or not res.stdout.strip():
                continue

            parsed = self._parse_ls_output(res.stdout, base_dir)
            found.extend(parsed)

        if not found:
            raise BackupNotFoundError(searched_paths=list(AppConfig.REMOTE_BACKUP_DIRS))

        # Deduplicate and sort
        seen = set()
        deduped = []
        for b in found:
            if b.remote_path not in seen:
                seen.add(b.remote_path)
                deduped.append(b)

        deduped.sort(key=lambda b: (1 if b.is_main else 0, b.modified_at, b.filename), reverse=True)
        return deduped

    def find_latest_backup(
        self, serial: str, account_id: str | None = None
    ) -> RemoteBackupInfo:
        """Find the latest primary backup for an account or default."""
        backups = self.list_backups(serial, account_id=account_id)
        return backups[0]

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
