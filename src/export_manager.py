"""ExportManager generates normalized CSV files and manifest JSON with atomic safety."""

import csv
import json
import logging
import os
import re
from pathlib import Path

from src.config import AppConfig
from src.errors import ExportFailedError
from src.models import Conversation, ExportManifest, Message

logger = logging.getLogger(__name__)


class ExportManager:
    """Handles CSV generation and manifest export with Excel UTF-8 BOM compatibility and atomic writes."""

    MESSAGE_HEADERS: tuple[str, ...] = (
        "message_uid",
        "conversation_id",
        "sender_id",
        "sender_name",
        "direction",
        "timestamp_utc",
        "timestamp_local",
        "message_type",
        "text",
        "media_path",
        "media_mime",
        "media_size",
        "media_status",
        "quoted_message_id",
        "forwarded",
        "edited",
        "starred",
        "raw_type_code",
        "source_backup_id",
    )

    CONVERSATION_HEADERS: tuple[str, ...] = (
        "conversation_id",
        "conversation_name",
        "conversation_type",
        "original_jid",
        "last_message_at",
        "message_count",
    )

    @staticmethod
    def sanitize_filename(name: str, fallback_id: str) -> str:
        """Create a safe filesystem filename avoiding forbidden characters across Windows/macOS/Linux."""
        if not name:
            clean = fallback_id
        else:
            # Replace forbidden chars with underscore: \ / : * ? " < > |
            clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
            # Collapse multiple spaces or underscores
            clean = re.sub(r"[\s_]+", "_", clean).strip("_.")
        if not clean:
            clean = "unnamed"
        # Sanitize fallback id as well
        clean_id = re.sub(r'[\\/*?:"<>|@]', "_", fallback_id).strip("_.")
        # Limit total filename length to 80 chars
        return f"{clean[:50]}_{clean_id[:25]}.csv"

    @staticmethod
    def escape_csv_cell(value: str | None) -> str:
        """Escape potential CSV formula injection characters (=, +, -, @, \t, \r) for spreadsheet safety."""
        if value is None:
            return ""
        str_val = str(value)
        if not str_val:
            return ""
        # If string starts with formula triggers, prepend a single quote
        if str_val[0] in ("=", "+", "-", "@", "\t", "\r"):
            return f"'{str_val}"
        return str_val

    @classmethod
    def _message_to_row(cls, msg: Message) -> dict[str, str]:
        """Convert domain Message to CSV string dictionary."""
        return {
            "message_uid": cls.escape_csv_cell(msg.message_uid),
            "conversation_id": cls.escape_csv_cell(msg.conversation_id),
            "sender_id": cls.escape_csv_cell(msg.sender_id),
            "sender_name": cls.escape_csv_cell(msg.sender_name),
            "direction": msg.direction,
            "timestamp_utc": msg.timestamp_utc or "",
            "timestamp_local": msg.timestamp_local or "",
            "message_type": msg.message_type,
            "text": cls.escape_csv_cell(msg.text),
            "media_path": cls.escape_csv_cell(msg.media_path),
            "media_mime": cls.escape_csv_cell(msg.media_mime),
            "media_size": str(msg.media_size) if msg.media_size is not None else "",
            "media_status": msg.media_status,
            "quoted_message_id": cls.escape_csv_cell(msg.quoted_message_id),
            "forwarded": "1" if msg.forwarded else "0",
            "edited": "1" if msg.edited else "0",
            "starred": "1" if msg.starred else "0",
            "raw_type_code": str(msg.raw_type_code) if msg.raw_type_code is not None else "",
            "source_backup_id": cls.escape_csv_cell(msg.source_backup_id),
        }

    @classmethod
    def _conversation_to_row(cls, conv: Conversation) -> dict[str, str]:
        """Convert domain Conversation to CSV string dictionary."""
        return {
            "conversation_id": cls.escape_csv_cell(conv.conversation_id),
            "conversation_name": cls.escape_csv_cell(conv.conversation_name),
            "conversation_type": conv.conversation_type,
            "original_jid": cls.escape_csv_cell(conv.original_jid),
            "last_message_at": conv.last_message_at or "",
            "message_count": str(conv.message_count),
        }

    @classmethod
    def _atomic_write_csv(
        cls,
        target_path: Path,
        headers: list[str],
        rows: list[dict[str, str]],
    ) -> None:
        """Write CSV using UTF-8 with BOM to a temporary file and atomically rename."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_name(f"{target_path.name}.tmp_{os.getpid()}")

        try:
            # Use 'utf-8-sig' for Excel BOM compatibility
            with open(temp_path, mode="w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=headers,
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\r\n",
                )
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)

            # Atomic replace
            if target_path.exists():
                target_path.unlink()
            temp_path.replace(target_path)

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise ExportFailedError(
                reason=f"Fallo al escribir el archivo CSV en '{target_path}': {e}"
            )

    @classmethod
    def export_all(
        cls,
        conversations: list[Conversation],
        messages: list[Message],
        manifest: ExportManifest,
        output_dir: Path | None = None,
    ) -> list[Path]:
        """Export all_messages.csv, conversations.csv, individual conversation CSVs, and manifest.json."""
        out_dir = output_dir or AppConfig.EXPORTS_DIR
        conv_dir = out_dir / "conversations"
        out_dir.mkdir(parents=True, exist_ok=True)
        conv_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[Path] = []

        # 1. all_messages.csv
        all_messages_path = out_dir / "all_messages.csv"
        msg_rows = [cls._message_to_row(m) for m in messages]
        cls._atomic_write_csv(all_messages_path, cls.MESSAGE_HEADERS, msg_rows)
        files_written.append(all_messages_path)

        # 2. conversations.csv
        conversations_path = out_dir / "conversations.csv"
        conv_rows = [cls._conversation_to_row(c) for c in conversations]
        cls._atomic_write_csv(conversations_path, cls.CONVERSATION_HEADERS, conv_rows)
        files_written.append(conversations_path)

        # 3. Individual conversation CSVs
        # Group messages by conversation_id
        conv_messages_map: dict[str, list[Message]] = {}
        for m in messages:
            conv_messages_map.setdefault(m.conversation_id, []).append(m)

        for conv in conversations:
            c_msgs = conv_messages_map.get(conv.conversation_id, [])
            filename = cls.sanitize_filename(conv.conversation_name, conv.conversation_id)
            conv_file_path = conv_dir / filename
            c_rows = [cls._message_to_row(m) for m in c_msgs]
            cls._atomic_write_csv(conv_file_path, cls.MESSAGE_HEADERS, c_rows)
            files_written.append(conv_file_path)

        # 4. manifest.json
        manifest_path = out_dir / "manifest.json"
        temp_manifest = out_dir / f"manifest.json.tmp_{os.getpid()}"
        manifest.files_generated = [p.name for p in files_written]
        manifest.total_conversations = len(conversations)
        manifest.total_messages = len(messages)

        try:
            with open(temp_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
            if manifest_path.exists():
                manifest_path.unlink()
            temp_manifest.replace(manifest_path)
            files_written.append(manifest_path)
        except Exception as e:
            if temp_manifest.exists():
                temp_manifest.unlink(missing_ok=True)
            raise ExportFailedError(reason=f"Fallo al escribir el archivo manifest.json: {e}")

        logger.info(
            f"Export completed: {len(files_written)} files written to {out_dir} (all_messages.csv, conversations.csv, individual CSVs, manifest.json)."
        )
        return files_written
