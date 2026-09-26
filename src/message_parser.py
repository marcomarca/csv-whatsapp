"""MessageParser parses decrypted WhatsApp SQLite databases into domain Conversation and Message models."""

import datetime
import logging
import sqlite3
import sys
from pathlib import Path

from src.config import AppConfig
from src.errors import ParserFailedError
from src.models import Conversation, Message

# Add vendor whapa libs to sys.path
if str(AppConfig.WHAPA_LIBS_DIR) not in sys.path:
    sys.path.insert(0, str(AppConfig.WHAPA_LIBS_DIR))

try:
    import whacodes as codes
    import whareader
except ImportError:
    whareader = None
    codes = None

logger = logging.getLogger(__name__)


class MessageParser:
    """Extracts chats and messages from decrypted SQLite databases using WhaPa."""

    @classmethod
    def _ts_to_iso(cls, ts_epoch: int | None) -> tuple[str, str]:
        """Convert Unix epoch timestamp (seconds) into ISO-8601 UTC and Local datetime strings."""
        if not ts_epoch or ts_epoch <= 0:
            return "", ""
        try:
            dt_utc = datetime.datetime.fromtimestamp(ts_epoch, tz=datetime.UTC)
            # Local timezone
            dt_local = dt_utc.astimezone()
            return dt_utc.isoformat(), dt_local.isoformat()
        except (ValueError, OverflowError, OSError):
            return str(ts_epoch), str(ts_epoch)

    @classmethod
    def parse_database(
        cls,
        db_path: Path,
        backup_id: str = "",
        wa_db_path: Path | None = None,
    ) -> tuple[list[Conversation], list[Message]]:
        """Parse all conversations and messages from a decrypted SQLite database."""
        if not db_path.is_file():
            raise ParserFailedError(
                reason=f"No se encontró el archivo de base de datos descifrada en '{db_path}'."
            )

        logger.info(f"Parsing WhatsApp messages from {db_path}...")

        # 1. Use WhaPa parser if available
        if whareader is not None:
            try:
                wa_db_str = str(wa_db_path) if wa_db_path and wa_db_path.is_file() else None
                extraction = whareader.read(str(db_path), wa_db=wa_db_str)
                return cls._normalize_whapa_extraction(extraction, backup_id)
            except Exception as e:
                logger.warning(
                    f"WhaPa reader encountered an error: {e}. Falling back to native SQL parser."
                )

        # 2. Fallback direct SQL parser
        return cls._parse_direct_sqlite(db_path, backup_id)

    @classmethod
    def _normalize_whapa_extraction(
        cls,
        extraction,
        backup_id: str,
    ) -> tuple[list[Conversation], list[Message]]:
        """Transform WhaPa extraction objects into domain models."""
        conversations: list[Conversation] = []
        messages: list[Message] = []

        chats = extraction.chats()
        for chat in chats:
            chat_type = (
                "group" if chat.is_group else ("broadcast" if chat.is_broadcast else "individual")
            )
            conv_name = chat.name or chat.label or chat.chat_id
            last_ts_iso, _ = cls._ts_to_iso(chat.last_ts)

            conv = Conversation(
                conversation_id=str(chat.chat_id),
                conversation_name=conv_name,
                conversation_type=chat_type,
                original_jid=str(chat.chat_id),
                last_message_at=last_ts_iso,
                message_count=len(chat.messages),
            )
            conversations.append(conv)

        for m in extraction.messages:
            utc_iso, local_iso = cls._ts_to_iso(m.timestamp)

            # Determine message direction
            if m.from_me:
                direction = "outgoing"
            elif m.sender == "system" or (codes and m.kind == codes.Kind.SYSTEM):
                direction = "system"
            else:
                direction = "incoming"

            # Determine kind name
            kind_name = m.kind.value if hasattr(m.kind, "value") else str(m.type_desc).lower()

            # Unique message UID
            uid = m.key_id or f"{m.chat_id}_{m.row_id}_{m.timestamp}"

            # Quoted message id if any
            quoted_id = None
            if m.quote and hasattr(m.quote, "key_id"):
                quoted_id = m.quote.key_id

            msg = Message(
                message_uid=str(uid),
                conversation_id=str(m.chat_id),
                sender_id=str(m.sender or ("me" if m.from_me else m.chat_id)),
                sender_name=m.sender_name
                or (m.buscar_contacto.display_name if hasattr(m, "buscar_contacto") else None),
                direction=direction,
                timestamp_utc=utc_iso,
                timestamp_local=local_iso,
                message_type=kind_name,
                text=m.text or m.media_caption or m.system_action,
                media_path=m.media_path,
                media_mime=m.media_mime,
                media_size=m.media_size,
                media_status="missing" if m.media_path else "not_exported",
                quoted_message_id=quoted_id,
                forwarded=bool(m.is_forwarded),
                edited=bool(m.edited),
                starred=bool(m.starred),
                raw_type_code=m.raw_type,
                source_backup_id=backup_id,
            )
            messages.append(msg)

        logger.info(
            f"Successfully parsed {len(conversations)} conversations and {len(messages)} messages."
        )
        return conversations, messages

    @classmethod
    def _parse_direct_sqlite(
        cls,
        db_path: Path,
        backup_id: str,
    ) -> tuple[list[Conversation], list[Message]]:
        """Fallback direct SQLite query when WhaPa encounters an unrecognized schema."""
        conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        conversations: list[Conversation] = []
        messages: list[Message] = []

        try:
            # Check modern Android schema: table 'message' vs legacy 'messages'
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('message', 'messages', 'chat', 'jid');"
            )
            tables = {row["name"] for row in cursor.fetchall()}

            if "message" in tables:
                # Modern Android WhatsApp schema
                # Build JID mapping if jid table exists
                jid_map = {}
                if "jid" in tables:
                    try:
                        cursor.execute("SELECT _id, raw_string FROM jid;")
                        for row in cursor.fetchall():
                            jid_map[row["_id"]] = row["raw_string"]
                    except sqlite3.Error:
                        pass

                # Build chat mapping
                chat_map = {}
                if "chat" in tables:
                    try:
                        cursor.execute("SELECT _id, jid_row_id, subject FROM chat;")
                        for row in cursor.fetchall():
                            jid_str = jid_map.get(row["jid_row_id"], str(row["jid_row_id"]))
                            chat_map[row["_id"]] = {
                                "jid": jid_str,
                                "subject": row["subject"] or jid_str,
                            }
                    except sqlite3.Error:
                        pass

                # Query messages
                cursor.execute("""
                    SELECT 
                        _id, chat_row_id, from_me, key_id, sender_jid_row_id, 
                        timestamp, received_timestamp, message_type, text_data,
                        starred
                    FROM message
                    ORDER BY timestamp ASC;
                """)

                conv_buckets: dict[str, list[Message]] = {}

                for row in cursor.fetchall():
                    chat_info = chat_map.get(
                        row["chat_row_id"],
                        {
                            "jid": f"chat_{row['chat_row_id']}",
                            "subject": f"chat_{row['chat_row_id']}",
                        },
                    )
                    conv_id = chat_info["jid"]
                    sender = (
                        "me" if row["from_me"] else jid_map.get(row["sender_jid_row_id"], conv_id)
                    )
                    ts_sec = (
                        int(row["timestamp"] / 1000)
                        if row["timestamp"] and row["timestamp"] > 1e11
                        else (row["timestamp"] or 0)
                    )
                    utc_iso, local_iso = cls._ts_to_iso(ts_sec)

                    uid = row["key_id"] or f"{conv_id}_{row['_id']}_{ts_sec}"

                    msg = Message(
                        message_uid=str(uid),
                        conversation_id=conv_id,
                        sender_id=sender,
                        sender_name=None,
                        direction="outgoing" if row["from_me"] else "incoming",
                        timestamp_utc=utc_iso,
                        timestamp_local=local_iso,
                        message_type="text"
                        if row["message_type"] == 0
                        else f"type_{row['message_type']}",
                        text=row["text_data"],
                        starred=bool(row["starred"]),
                        raw_type_code=row["message_type"],
                        source_backup_id=backup_id,
                    )
                    messages.append(msg)
                    conv_buckets.setdefault(conv_id, []).append(msg)

                for cid, cmsgs in conv_buckets.items():
                    chat_name = (
                        chat_map.get(cid, {}).get("subject", cid) if isinstance(cid, int) else cid
                    )
                    conv_type = "group" if "g.us" in cid else "individual"
                    last_ts = cmsgs[-1].timestamp_utc if cmsgs else None
                    conversations.append(
                        Conversation(
                            conversation_id=cid,
                            conversation_name=chat_name,
                            conversation_type=conv_type,
                            original_jid=cid,
                            last_message_at=last_ts,
                            message_count=len(cmsgs),
                        )
                    )

            return conversations, messages

        except Exception as e:
            raise ParserFailedError(reason=f"Error en consulta SQL directa a SQLite: {e}")
        finally:
            conn.close()
