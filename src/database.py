"""VaultDatabase manages internal SQLite storage for consolidation, deduplication, and export history."""

import logging
import sqlite3
from pathlib import Path

from src.config import AppConfig
from src.models import BackupMetadata, Conversation, ExportRun, Message

logger = logging.getLogger(__name__)


class VaultDatabase:
    """Internal SQLite database ensuring incremental consolidation and deduplication."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or AppConfig.VAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Initialize database schema with tables, columns, and indexes."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS backups (
                    backup_id TEXT PRIMARY KEY,
                    device_id TEXT,
                    source_path TEXT,
                    filename TEXT,
                    format TEXT,
                    file_size INTEGER,
                    sha256 TEXT UNIQUE,
                    source_modified_at TEXT,
                    imported_at TEXT,
                    decryption_status TEXT,
                    parser_version TEXT,
                    message_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    conversation_name TEXT,
                    conversation_type TEXT,
                    original_jid TEXT,
                    account_id TEXT DEFAULT 'principal',
                    device_serial TEXT DEFAULT '',
                    last_message_at TEXT,
                    message_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_uid TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    sender_id TEXT,
                    sender_name TEXT,
                    direction TEXT,
                    timestamp_utc TEXT,
                    timestamp_local TEXT,
                    message_type TEXT,
                    account_id TEXT DEFAULT 'principal',
                    device_serial TEXT DEFAULT '',
                    text TEXT,
                    media_path TEXT,
                    media_mime TEXT,
                    media_size INTEGER,
                    media_status TEXT DEFAULT 'not_exported',
                    quoted_message_id TEXT,
                    forwarded INTEGER DEFAULT 0,
                    edited INTEGER DEFAULT 0,
                    starred INTEGER DEFAULT 0,
                    raw_type_code INTEGER,
                    source_backup_id TEXT
                );

                CREATE TABLE IF NOT EXISTS export_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT,
                    account_id TEXT DEFAULT 'principal',
                    device_serial TEXT DEFAULT '',
                    finished_at TEXT,
                    status TEXT,
                    backup_id TEXT,
                    total_conversations INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    inserted_messages INTEGER DEFAULT 0,
                    updated_messages INTEGER DEFAULT 0,
                    warnings TEXT,
                    error_code TEXT
                );
            """)

            # Schema migration: check if account_id & device_serial columns exist before creating indexes
            for table_name in ("conversations", "messages", "export_runs"):
                cur = conn.execute(f"PRAGMA table_info({table_name});")
                cols = [r["name"] for r in cur.fetchall()]
                if "account_id" not in cols:
                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN account_id TEXT DEFAULT 'principal';"
                    )
                if "device_serial" not in cols:
                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN device_serial TEXT DEFAULT '';"
                    )

            # Create indexes after migrations ensure all columns exist
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_acc ON messages(account_id);
                CREATE INDEX IF NOT EXISTS idx_messages_dev_acc ON messages(device_serial, account_id);
                CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp_utc);
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
                CREATE INDEX IF NOT EXISTS idx_conv_acc ON conversations(account_id);
                CREATE INDEX IF NOT EXISTS idx_conv_dev_acc ON conversations(device_serial, account_id);
                CREATE INDEX IF NOT EXISTS idx_backups_sha ON backups(sha256);
            """)

            conn.commit()

    def save_backup_metadata(self, backup: BackupMetadata) -> None:
        """Insert or replace backup metadata."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO backups (
                    backup_id, device_id, source_path, filename, format,
                    file_size, sha256, source_modified_at, imported_at,
                    decryption_status, parser_version, message_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
                (
                    backup.backup_id,
                    backup.device_id,
                    backup.source_path,
                    backup.filename,
                    backup.format,
                    backup.file_size,
                    backup.sha256,
                    backup.source_modified_at,
                    backup.imported_at,
                    backup.decryption_status,
                    backup.parser_version,
                    backup.message_count,
                ),
            )
            conn.commit()

    def get_backup_by_sha256(self, sha256: str) -> BackupMetadata | None:
        """Find a previously imported backup by its SHA-256 hash."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM backups WHERE sha256 = ?;", (sha256,))
            row = cur.fetchone()
            if row:
                return BackupMetadata(
                    backup_id=row["backup_id"],
                    device_id=row["device_id"],
                    source_path=row["source_path"],
                    filename=row["filename"],
                    format=row["format"],
                    file_size=row["file_size"],
                    sha256=row["sha256"],
                    source_modified_at=row["source_modified_at"],
                    imported_at=row["imported_at"],
                    decryption_status=row["decryption_status"],
                    parser_version=row["parser_version"],
                    message_count=row["message_count"],
                )
            return None

    def get_latest_backup(self) -> BackupMetadata | None:
        """Get the most recently imported backup record."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM backups ORDER BY imported_at DESC LIMIT 1;")
            row = cur.fetchone()
            if row:
                return BackupMetadata(
                    backup_id=row["backup_id"],
                    device_id=row["device_id"],
                    source_path=row["source_path"],
                    filename=row["filename"],
                    format=row["format"],
                    file_size=row["file_size"],
                    sha256=row["sha256"],
                    source_modified_at=row["source_modified_at"],
                    imported_at=row["imported_at"],
                    decryption_status=row["decryption_status"],
                    parser_version=row["parser_version"],
                    message_count=row["message_count"],
                )
            return None

    def upsert_conversations(
        self,
        conversations: list[Conversation],
        account_id: str = "principal",
        device_serial: str = "",
    ) -> None:
        """Upsert conversations list associated with an account and device."""
        with self._get_connection() as conn:
            for conv in conversations:
                conn.execute(
                    """
                    INSERT INTO conversations (
                        conversation_id, conversation_name, conversation_type,
                        original_jid, account_id, device_serial, last_message_at, message_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(conversation_id) DO UPDATE SET
                        conversation_name = excluded.conversation_name,
                        conversation_type = excluded.conversation_type,
                        account_id = excluded.account_id,
                        device_serial = excluded.device_serial,
                        last_message_at = CASE 
                            WHEN excluded.last_message_at > conversations.last_message_at OR conversations.last_message_at IS NULL 
                            THEN excluded.last_message_at 
                            ELSE conversations.last_message_at 
                        END,
                        message_count = max(conversations.message_count, excluded.message_count);
                """,
                    (
                        conv.conversation_id,
                        conv.conversation_name,
                        conv.conversation_type,
                        conv.original_jid,
                        account_id,
                        device_serial,
                        conv.last_message_at,
                        conv.message_count,
                    ),
                )
            conn.commit()

    def consolidate_messages(
        self,
        messages: list[Message],
        backup_id: str,
        account_id: str = "principal",
        device_serial: str = "",
    ) -> tuple[int, int, int]:
        """Consolidate parsed messages into the database for a specific account and device."""
        total = len(messages)
        inserted = 0
        updated = 0

        with self._get_connection() as conn:
            for msg in messages:
                cur = conn.execute(
                    "SELECT edited, text, media_path FROM messages WHERE message_uid = ?;",
                    (msg.message_uid,),
                )
                existing = cur.fetchone()

                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO messages (
                            message_uid, conversation_id, sender_id, sender_name,
                            direction, timestamp_utc, timestamp_local, message_type,
                            account_id, device_serial, text, media_path, media_mime, media_size, media_status,
                            quoted_message_id, forwarded, edited, starred,
                            raw_type_code, source_backup_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                        (
                            msg.message_uid,
                            msg.conversation_id,
                            msg.sender_id,
                            msg.sender_name,
                            msg.direction,
                            msg.timestamp_utc,
                            msg.timestamp_local,
                            msg.message_type,
                            account_id,
                            device_serial,
                            msg.text,
                            msg.media_path,
                            msg.media_mime,
                            msg.media_size,
                            msg.media_status,
                            msg.quoted_message_id,
                            int(msg.forwarded),
                            int(msg.edited),
                            int(msg.starred),
                            msg.raw_type_code,
                            backup_id,
                        ),
                    )
                    inserted += 1
                else:
                    if (
                        msg.edited
                        or msg.text != existing["text"]
                        or (msg.media_path and not existing["media_path"])
                    ):
                        conn.execute(
                            """
                            UPDATE messages SET
                                sender_name = coalesce(?, sender_name),
                                account_id = ?,
                                device_serial = ?,
                                text = ?,
                                media_path = coalesce(?, media_path),
                                media_mime = coalesce(?, media_mime),
                                media_size = coalesce(?, media_size),
                                edited = ?,
                                starred = ?,
                                source_backup_id = ?
                            WHERE message_uid = ?;
                        """,
                            (
                                msg.sender_name,
                                account_id,
                                device_serial,
                                msg.text,
                                msg.media_path,
                                msg.media_mime,
                                msg.media_size,
                                int(msg.edited),
                                int(msg.starred),
                                backup_id,
                                msg.message_uid,
                            ),
                        )
                        updated += 1

            # Update conversation stats for this account and device
            if device_serial:
                conn.execute("""
                    UPDATE conversations SET
                        message_count = (SELECT count(*) FROM messages WHERE messages.conversation_id = conversations.conversation_id),
                        last_message_at = (SELECT max(timestamp_utc) FROM messages WHERE messages.conversation_id = conversations.conversation_id)
                    WHERE account_id = ? AND device_serial = ?;
                """, (account_id, device_serial))
            else:
                conn.execute("""
                    UPDATE conversations SET
                        message_count = (SELECT count(*) FROM messages WHERE messages.conversation_id = conversations.conversation_id),
                        last_message_at = (SELECT max(timestamp_utc) FROM messages WHERE messages.conversation_id = conversations.conversation_id)
                    WHERE account_id = ?;
                """, (account_id,))
            conn.commit()

        logger.info(
            f"Consolidated {total} messages from backup {backup_id} (device: '{device_serial}', account: '{account_id}'): {inserted} inserted, {updated} updated."
        )
        return total, inserted, updated

    def get_stats(
        self, account_id: str | None = None, device_serial: str | None = None
    ) -> tuple[int, int]:
        """Return fast count of conversations and messages without deserializing full objects."""
        with self._get_connection() as conn:
            # 1. Conversations count
            conv_query = "SELECT COUNT(*) FROM conversations"
            conv_params: list[str] = []
            conv_conds: list[str] = []
            if account_id:
                conv_conds.append("account_id = ?")
                conv_params.append(account_id)
            if device_serial:
                conv_conds.append("device_serial = ?")
                conv_params.append(device_serial)
            if conv_conds:
                conv_query += " WHERE " + " AND ".join(conv_conds)
            conv_cur = conn.execute(conv_query, tuple(conv_params))
            conv_row = conv_cur.fetchone()
            conv_count = conv_row[0] if conv_row else 0

            # 2. Messages count
            msg_query = "SELECT COUNT(*) FROM messages"
            msg_params: list[str] = []
            msg_conds: list[str] = []
            if account_id:
                msg_conds.append("account_id = ?")
                msg_params.append(account_id)
            if device_serial:
                msg_conds.append("device_serial = ?")
                msg_params.append(device_serial)
            if msg_conds:
                msg_query += " WHERE " + " AND ".join(msg_conds)
            msg_cur = conn.execute(msg_query, tuple(msg_params))
            msg_row = msg_cur.fetchone()
            msg_count = msg_row[0] if msg_row else 0

            return conv_count, msg_count

    def get_all_conversations(
        self, account_id: str | None = None, device_serial: str | None = None
    ) -> list[Conversation]:
        """Fetch stored conversations (optionally filtered by account_id and device_serial) ordered by last message date."""
        with self._get_connection() as conn:
            query = "SELECT * FROM conversations"
            params: list[str] = []
            conditions: list[str] = []

            if account_id:
                conditions.append("account_id = ?")
                params.append(account_id)
            if device_serial:
                conditions.append("device_serial = ?")
                params.append(device_serial)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY last_message_at DESC NULLS LAST;"

            cur = conn.execute(query, tuple(params))
            return [
                Conversation(
                    conversation_id=row["conversation_id"],
                    conversation_name=row["conversation_name"],
                    conversation_type=row["conversation_type"],
                    original_jid=row["original_jid"],
                    account_id=row["account_id"] if "account_id" in row.keys() else "principal",
                    device_serial=row["device_serial"] if "device_serial" in row.keys() else "",
                    last_message_at=row["last_message_at"],
                    message_count=row["message_count"],
                )
                for row in cur.fetchall()
            ]

    def get_all_messages(
        self, account_id: str | None = None, device_serial: str | None = None
    ) -> list[Message]:
        """Fetch all stored messages (optionally filtered by account_id and device_serial) ordered chronologically."""
        with self._get_connection() as conn:
            query = "SELECT * FROM messages"
            params: list[str] = []
            conditions: list[str] = []

            if account_id:
                conditions.append("account_id = ?")
                params.append(account_id)
            if device_serial:
                conditions.append("device_serial = ?")
                params.append(device_serial)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp_utc ASC;"

            cur = conn.execute(query, tuple(params))
            return [self._row_to_message(row) for row in cur.fetchall()]

    def get_messages_for_conversation(
        self,
        conv_id: str,
        account_id: str | None = None,
        device_serial: str | None = None,
    ) -> list[Message]:
        """Fetch all messages for a given conversation ID ordered chronologically."""
        with self._get_connection() as conn:
            query = "SELECT * FROM messages WHERE conversation_id = ?"
            params: list[str] = [conv_id]

            if account_id:
                query += " AND account_id = ?"
                params.append(account_id)
            if device_serial:
                query += " AND device_serial = ?"
                params.append(device_serial)

            query += " ORDER BY timestamp_utc ASC;"
            cur = conn.execute(query, tuple(params))
            return [self._row_to_message(row) for row in cur.fetchall()]

    def record_export_run(
        self,
        run: ExportRun,
        account_id: str = "principal",
        device_serial: str = "",
    ) -> None:
        """Record an export run in history."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO export_runs (
                    run_id, started_at, account_id, device_serial, finished_at, status, backup_id,
                    total_conversations, total_messages, inserted_messages,
                    updated_messages, warnings, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
                (
                    run.run_id,
                    run.started_at,
                    account_id,
                    device_serial,
                    run.finished_at,
                    run.status,
                    run.backup_id,
                    run.total_conversations,
                    run.total_messages,
                    run.inserted_messages,
                    run.updated_messages,
                    run.warnings,
                    run.error_code,
                ),
            )
            conn.commit()

    def get_export_runs(
        self,
        limit: int = 50,
        account_id: str | None = None,
        device_serial: str | None = None,
    ) -> list[ExportRun]:
        """Fetch past export execution runs (optionally filtered by account_id and device_serial)."""
        with self._get_connection() as conn:
            query = "SELECT * FROM export_runs"
            params: list[object] = []
            conditions: list[str] = []

            if account_id:
                conditions.append("account_id = ?")
                params.append(account_id)
            if device_serial:
                conditions.append("device_serial = ?")
                params.append(device_serial)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY started_at DESC LIMIT ?;"
            params.append(limit)

            cur = conn.execute(query, tuple(params))
            return [
                ExportRun(
                    run_id=row["run_id"],
                    started_at=row["started_at"],
                    account_id=row["account_id"] if "account_id" in row.keys() else "principal",
                    device_serial=row["device_serial"] if "device_serial" in row.keys() else "",
                    finished_at=row["finished_at"],
                    status=row["status"],
                    backup_id=row["backup_id"],
                    total_conversations=row["total_conversations"],
                    total_messages=row["total_messages"],
                    inserted_messages=row["inserted_messages"],
                    updated_messages=row["updated_messages"],
                    warnings=row["warnings"] or "",
                    error_code=row["error_code"],
                )
                for row in cur.fetchall()
            ]

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        return Message(
            message_uid=row["message_uid"],
            conversation_id=row["conversation_id"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            direction=row["direction"],
            timestamp_utc=row["timestamp_utc"],
            timestamp_local=row["timestamp_local"],
            message_type=row["message_type"],
            account_id=row["account_id"] if "account_id" in row.keys() else "principal",
            device_serial=row["device_serial"] if "device_serial" in row.keys() else "",
            text=row["text"],
            media_path=row["media_path"],
            media_mime=row["media_mime"],
            media_size=row["media_size"],
            media_status=row["media_status"],
            quoted_message_id=row["quoted_message_id"],
            forwarded=bool(row["forwarded"]),
            edited=bool(row["edited"]),
            starred=bool(row["starred"]),
            raw_type_code=row["raw_type_code"],
            source_backup_id=row["source_backup_id"],
        )

