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
        force: bool = False,
        include_media: bool = False,
        output_dir: Path | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> dict:
        """Run complete automated pipeline from Android USB to CSV."""
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
            status="started",
        )
        self.vault_db.record_export_run(run_record)

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

            # 2. Remote Backup Discovery
            notify(
                "DISCOVERING", "Buscando copias de seguridad de WhatsApp en el teléfono...", 20.0
            )
            backups = self.device_manager.list_backups(dev_info.serial)
            target_backup = backups[0]
            notify(
                "DISCOVERING",
                f"Backup localizado: {target_backup.filename} ({target_backup.file_size / (1024 * 1024):.2f} MB, {target_backup.modified_at})",
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
                # Proceed with export of consolidated data
                warnings_list.append(
                    f"El backup transferido es idéntico al procesado previamente el {prev_backup.imported_at}."
                )

            # 5. Encryption Key Resolution
            notify("KEY_RESOLUTION", "Obteniendo clave de cifrado...", 55.0)
            effective_key = (
                key
                or self.secret_manager.get_key(dev_info.serial)
                or self.secret_manager.get_key("default")
            )

            if not effective_key:
                raise InvalidKeyError(
                    reason="No se proporcionó ni se encontró una clave de cifrado guardada.",
                    action_recommended="Introduce la clave de cifrado de 64 dígitos hexadecimales.",
                )

            # 6. Decrypt and Validate SQLite
            notify(
                "DECRYPTING",
                "Descifrando copia de seguridad y validando integridad SQLite...",
                65.0,
            )
            decrypted_db_path = AppConfig.WORKING_DIR / f"{sha256_hash[:12]}_msgstore.db"
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
            notify("CONSOLIDATING", "Consolidando y deduplicando datos en la base local...", 90.0)
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
            self.vault_db.upsert_conversations(conversations)
            _tot, inserted, updated = self.vault_db.consolidate_messages(messages, sha256_hash)

            # 9. Pull Media if requested
            if include_media:
                notify("MEDIA", "Descargando archivos multimedia...", 92.0)
                media_count = self.device_manager.pull_media(dev_info.serial, AppConfig.MEDIA_DIR)
                notify("MEDIA", f"Descarga multimedia completada ({media_count} carpetas).", 94.0)

            # 10. Generate CSV files and Manifest
            notify(
                "EXPORTING_CSV",
                "Generando all_messages.csv, conversations.csv y CSVs por chat...",
                95.0,
            )
            all_vault_convs = self.vault_db.get_all_conversations()
            all_vault_msgs = self.vault_db.get_all_messages()

            manifest = ExportManifest(
                run_id=run_id,
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
                output_dir=output_dir or AppConfig.EXPORTS_DIR,
            )

            # Complete Run
            finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            run_record.finished_at = finished_at
            run_record.status = "completed"
            run_record.backup_id = sha256_hash
            run_record.total_conversations = len(all_vault_convs)
            run_record.total_messages = len(all_vault_msgs)
            run_record.inserted_messages = inserted
            run_record.updated_messages = updated
            run_record.warnings = "; ".join(warnings_list)
            self.vault_db.record_export_run(run_record)

            notify(
                "COMPLETED",
                f"Exportación completada: {len(all_vault_convs)} chats, {len(all_vault_msgs)} mensajes ({inserted} nuevos, {updated} actualizados).",
                100.0,
            )

            return {
                "status": "success",
                "run_id": run_id,
                "backup_filename": target_backup.filename,
                "backup_sha256": sha256_hash,
                "device_model": dev_info.model or dev_info.serial,
                "total_conversations": len(all_vault_convs),
                "total_messages": len(all_vault_msgs),
                "inserted_messages": inserted,
                "updated_messages": updated,
                "files_written": [str(f) for f in files_written],
                "exports_dir": str(output_dir or AppConfig.EXPORTS_DIR),
                "warnings": warnings_list,
            }

        except WhatsAppBackupError as e:
            logger.error(f"Pipeline error: {e}")
            run_record.finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            run_record.status = "failed"
            run_record.error_code = e.code
            run_record.warnings = str(e)
            self.vault_db.record_export_run(run_record)
            raise
        except Exception as e:
            logger.exception("Unexpected error in export pipeline")
            run_record.finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            run_record.status = "failed"
            run_record.error_code = "UNEXPECTED_ERROR"
            run_record.warnings = str(e)
            self.vault_db.record_export_run(run_record)
            raise
