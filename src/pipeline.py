"""Pipeline orchestrates the entire WhatsApp backup extraction, decryption, consolidation, and CSV export flow."""

import datetime
import logging
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from src.config import AppConfig
from src.database import VaultDatabase
from src.decrypt_manager import DecryptManager
from src.device_manager import DeviceManager
from src.errors import (
    InvalidKeyError,
    WhatsAppBackupError,
)
from src.export_manager import ExportManager
from src.message_parser import MessageParser
from src.models import (
    BackupMetadata,
    ExportManifest,
    ExportRun,
)
from src.secret_manager import SecretManager

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, float], None]


class ExportPipeline:
    """Orchestrator for the entire WhatsApp to CSV export pipeline."""

    def __init__(
        self,
        device_manager: DeviceManager | None = None,
        secret_manager: SecretManager | None = None,
        vault_db: VaultDatabase | None = None,
    ):
        self.device_manager = device_manager or DeviceManager()
        self.secret_manager = secret_manager or SecretManager()
        self.vault_db = vault_db or VaultDatabase()

    def run_export(
        self,
        key: str | None = None,
        serial: str | None = None,
        account_id: str = "principal",
        force: bool = False,
        include_media: bool = False,
        output_dir: Path | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> dict:
        """Run complete automated pipeline from Android USB to CSV for a specific account."""
        AppConfig.ensure_directories()
        run_id = f"run_{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        started_at = datetime.datetime.now(datetime.UTC).isoformat()
        warnings_list: list[str] = []

        def notify(stage: str, msg: str, pct: float):
            logger.info(f"[{pct:.0f}%] Stage: {stage} - {msg}")
            if progress_cb:
                progress_cb(stage, msg, pct)

        run_record = ExportRun(
            run_id=run_id,
            started_at=started_at,
            account_id=account_id,
            status="started",
        )
        self.vault_db.record_export_run(run_record, account_id=account_id)

        try:
            # 1. Device Connection
            notify(
                "CONNECTING", "Comprobando conexión y autorización del dispositivo Android...", 10.0
            )
            dev_info = self.device_manager.get_active_device(serial)
            notify(
                "CONNECTING",
                f"Dispositivo detectado: {dev_info.model or dev_info.serial} (Android {dev_info.android_version or '?'})",
                15.0,
            )

            # 2. Remote Backup Discovery for target account
            notify(
                "DISCOVERING",
                f"Localizando cuenta '{account_id}' y copias de seguridad en el teléfono...",
                20.0,
            )
            target_account = self.device_manager.get_account(dev_info.serial, account_id=account_id)
            backups = self.device_manager.list_backups(dev_info.serial, account_id=target_account.account_id)
            target_backup = backups[0]
            notify(
                "DISCOVERING",
                f"Cuenta: {target_account.display_name} | Backup: {target_backup.filename} ({target_backup.file_size / (1024 * 1024):.2f} MB, {target_backup.modified_at})",
                30.0,
            )

            # 3. Pull Backup via ADB
            notify("PULLING", f"Descargando {target_backup.filename} desde el dispositivo...", 40.0)
            local_backup_path, sha256_hash = self.device_manager.pull_backup(
                dev_info.serial,
                target_backup.remote_path,
                AppConfig.BACKUPS_DIR,
            )
            notify("PULLING", f"Descarga finalizada. SHA256: {sha256_hash[:12]}...", 50.0)

            # 4. Check Freshness against vault
            prev_backup = self.vault_db.get_backup_by_sha256(sha256_hash)
            if prev_backup and not force:
                logger.info(
                    f"Backup with hash {sha256_hash} was already processed on {prev_backup.imported_at}."
                )
                warnings_list.append(
                    f"El backup transferido es idéntico al procesado previamente el {prev_backup.imported_at}."
                )

            # 5. Encryption Key Resolution for target account and device
            notify("KEY_RESOLUTION", f"Obteniendo clave de cifrado para cuenta '{account_id}'...", 55.0)
            effective_key = (
                key
                or self.secret_manager.get_key(account_id, serial=dev_info.serial)
                or self.secret_manager.get_key(dev_info.serial)
                or self.secret_manager.get_key("default")
            )

            if not effective_key:
                raise InvalidKeyError(
                    reason=f"No se encontró una clave de cifrado guardada para la cuenta '{account_id}' en el dispositivo '{dev_info.serial}'.",
                    action_recommended=f"Captura o introduce la clave de 64 dígitos con 'uv run python -m src.cli capture-key -a {account_id}'.",
                )

            # 6. Decrypt and Validate SQLite
            notify(
                "DECRYPTING",
                f"Descifrando copia de seguridad ({target_backup.format}) y validando SQLite...",
                65.0,
            )
            decrypted_db_path = AppConfig.WORKING_DIR / f"{sha256_hash[:12]}_{account_id}_msgstore.db"
            DecryptManager.decrypt(local_backup_path, effective_key, decrypted_db_path)
            notify(
                "DECRYPTING",
                "Base de datos descifrada e integridad SQLite verificada con éxito.",
                75.0,
            )

            # 7. Parse Messages with WhaPa
            notify("PARSING", "Extrayendo conversaciones, mensajes y metadatos con WhaPa...", 80.0)
            conversations, messages = MessageParser.parse_database(
                decrypted_db_path,
                backup_id=sha256_hash,
            )
            notify(
                "PARSING", f"Extraídos {len(conversations)} chats y {len(messages)} mensajes.", 85.0
            )

            # 8. Consolidate into Vault Database
            notify("CONSOLIDATING", f"Consolidando datos para cuenta '{account_id}' en la base local...", 90.0)
            backup_meta = BackupMetadata(
                backup_id=sha256_hash,
                device_id=dev_info.serial,
                source_path=target_backup.remote_path,
                filename=target_backup.filename,
                format=target_backup.format,
                file_size=local_backup_path.stat().st_size,
                sha256=sha256_hash,
                source_modified_at=target_backup.modified_at,
                imported_at=datetime.datetime.now(datetime.UTC).isoformat(),
                decryption_status="success",
                message_count=len(messages),
            )
            self.vault_db.save_backup_metadata(backup_meta)
            self.vault_db.upsert_conversations(
                conversations, account_id=account_id, device_serial=dev_info.serial
            )
            _tot, inserted, updated = self.vault_db.consolidate_messages(
                messages, sha256_hash, account_id=account_id, device_serial=dev_info.serial
            )

            # 9. Pull Media if requested
            if include_media:
                notify("MEDIA", "Descargando archivos multimedia...", 92.0)
                media_count = self.device_manager.pull_media(dev_info.serial, AppConfig.MEDIA_DIR)
                notify("MEDIA", f"Descarga multimedia completada ({media_count} carpetas).", 94.0)

            # 10. Generate CSV files and Manifest in isolated account/device folder
            target_out_dir = output_dir or ExportManager.get_account_export_dir(
                account_id, device_serial=dev_info.serial
            )
            notify(
                "EXPORTING_CSV",
                f"Generando CSVs en {target_out_dir}...",
                95.0,
            )
            all_vault_convs = self.vault_db.get_all_conversations(
                account_id=account_id, device_serial=dev_info.serial
            )
            all_vault_msgs = self.vault_db.get_all_messages(
                account_id=account_id, device_serial=dev_info.serial
            )

            manifest = ExportManifest(
                run_id=run_id,
                account_id=account_id,
                device_serial=dev_info.serial,
                exported_at=datetime.datetime.now(datetime.UTC).isoformat(),
                backup_file=target_backup.filename,
                backup_sha256=sha256_hash,
                total_conversations=len(all_vault_convs),
                total_messages=len(all_vault_msgs),
                files_generated=[],
                tool_versions={
                    "wa-crypt-tools": "0.1.0",
                    "whapa": "2.00",
                    "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                },
                warnings=warnings_list,
            )

            files_written = ExportManager.export_all(
                all_vault_convs,
                all_vault_msgs,
                manifest,
                output_dir=target_out_dir,
                account_id=account_id,
                device_serial=dev_info.serial,
            )

            # Complete Run
            finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            run_record.finished_at = finished_at
            run_record.status = "completed"
            run_record.backup_id = sha256_hash
            run_record.device_serial = dev_info.serial
            run_record.total_conversations = len(all_vault_convs)
            run_record.total_messages = len(all_vault_msgs)
            run_record.inserted_messages = inserted
            run_record.updated_messages = updated
            run_record.warnings = "; ".join(warnings_list)
            self.vault_db.record_export_run(
                run_record, account_id=account_id, device_serial=dev_info.serial
            )

            notify(
                "COMPLETED",
                f"Exportación de '{account_id}' ({dev_info.model or dev_info.serial}) completada: {len(all_vault_convs)} chats, {len(all_vault_msgs)} mensajes ({inserted} nuevos, {updated} actualizados).",
                100.0,
            )

            return {
                "status": "success",
                "run_id": run_id,
                "account_id": account_id,
                "account_display_name": target_account.display_name,
                "backup_filename": target_backup.filename,
                "backup_sha256": sha256_hash,
                "device_serial": dev_info.serial,
                "device_model": dev_info.model or dev_info.serial,
                "total_conversations": len(all_vault_convs),
                "total_messages": len(all_vault_msgs),
                "inserted_messages": inserted,
                "updated_messages": updated,
                "files_written": [str(f) for f in files_written],
                "exports_dir": str(target_out_dir),
                "warnings": warnings_list,
            }

        except WhatsAppBackupError as e:
            logger.error(f"Pipeline error for account {account_id}: {e}")
            run_record.finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            run_record.status = "failed"
            run_record.error_code = e.code
            run_record.warnings = str(e)
            self.vault_db.record_export_run(run_record, account_id=account_id)
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in export pipeline for account {account_id}")
            run_record.finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            run_record.status = "failed"
            run_record.error_code = "UNEXPECTED_ERROR"
            run_record.warnings = str(e)
            self.vault_db.record_export_run(run_record, account_id=account_id)
            raise
