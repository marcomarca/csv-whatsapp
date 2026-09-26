"""Pytest test configuration and fixtures with synthetic WhatsApp data."""

import sqlite3
import pytest
from pathlib import Path

from src.decrypt_manager import DecryptManager

# Known test 256-bit encryption key (64 hex characters)
TEST_KEY_HEX = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
WRONG_KEY_HEX = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


@pytest.fixture
def mock_keyring(monkeypatch):
    """In-memory keyring mock."""
    store = {}

    def set_password(service, username, password):
        store[(service, username)] = password

    def get_password(service, username):
        return store.get((service, username))

    def delete_password(service, username):
        if (service, username) in store:
            del store[(service, username)]
        else:
            raise KeyError("Password not found")

    monkeypatch.setattr("keyring.set_password", set_password)
    monkeypatch.setattr("keyring.get_password", get_password)
    monkeypatch.setattr("keyring.delete_password", delete_password)
    return store


@pytest.fixture
def synthetic_sqlite_db(tmp_path: Path) -> Path:
    """Create a fully-formed synthetic WhatsApp SQLite database with groups, Unicode, and media."""
    db_path = tmp_path / "synthetic_msgstore.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create WhatsApp schema (modern Android schema)
    cursor.executescript("""
        CREATE TABLE jid (
            _id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            server TEXT NOT NULL,
            agent INTEGER,
            device INTEGER,
            type INTEGER,
            raw_string TEXT NOT NULL
        );

        CREATE TABLE chat (
            _id INTEGER PRIMARY KEY AUTOINCREMENT,
            jid_row_id INTEGER NOT NULL,
            subject TEXT,
            created_timestamp INTEGER,
            archived INTEGER DEFAULT 0
        );

        CREATE TABLE message (
            _id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_row_id INTEGER NOT NULL,
            from_me INTEGER NOT NULL,
            key_id TEXT NOT NULL UNIQUE,
            sender_jid_row_id INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            received_timestamp INTEGER,
            message_type INTEGER DEFAULT 0,
            text_data TEXT,
            starred INTEGER DEFAULT 0
        );

        CREATE TABLE message_media (
            message_row_id INTEGER PRIMARY KEY,
            chat_row_id INTEGER,
            file_path TEXT,
            file_size INTEGER,
            mime_type TEXT,
            media_caption TEXT
        );
    """)

    # Populate JIDs
    # 1: User 1 (+34600111222)
    # 2: User 2 (+34600333444)
    # 3: Group JID (12345678-14508@g.us)
    # 4: Group Sender 3 (+34600555666)
    cursor.execute("INSERT INTO jid (user, server, raw_string) VALUES ('34600111222', 's.whatsapp.net', '34600111222@s.whatsapp.net');")
    cursor.execute("INSERT INTO jid (user, server, raw_string) VALUES ('34600333444', 's.whatsapp.net', '34600333444@s.whatsapp.net');")
    cursor.execute("INSERT INTO jid (user, server, raw_string) VALUES ('12345678-14508', 'g.us', '12345678-14508@g.us');")
    cursor.execute("INSERT INTO jid (user, server, raw_string) VALUES ('34600555666', 's.whatsapp.net', '34600555666@s.whatsapp.net');")

    # Populate Chats
    cursor.execute("INSERT INTO chat (jid_row_id, subject) VALUES (1, 'Alice 🌸');")
    cursor.execute("INSERT INTO chat (jid_row_id, subject) VALUES (3, 'Proyecto WhatsApp 🚀');")

    # Populate Messages
    # Chat 1: Alice (Individual Chat)
    # 1. Incoming Unicode message with accents & emojis
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (1, 0, 'MSG_001', 1, 1727300000000, '¡Hola! ¿Cómo estás hoy? ☕✨\nLínea 2 con acentos: áéíóú ñ Ñ', 0);
    """)

    # 2. Outgoing message with formula injection test string
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (1, 1, 'MSG_002', 1, 1727300060000, '=SUM(1+1) Fórmula peligrosa y -123 guión', 0);
    """)

    # 3. Multimedia message (Image)
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (1, 0, 'MSG_003', 1, 1727300120000, 'Foto de las vacaciones', 1);
    """)
    cursor.execute("""
        INSERT INTO message_media (message_row_id, chat_row_id, file_path, file_size, mime_type, media_caption)
        VALUES (3, 1, '/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/IMG-20260925-WA0001.jpg', 204850, 'image/jpeg', 'Foto de las vacaciones');
    """)

    # Chat 2: Group (Multiple senders)
    # 4. Message from Sender 1
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (2, 0, 'MSG_GRP_001', 1, 1727300200000, 'Mensaje grupal de Alice', 0);
    """)
    # 5. Message from Sender 2
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (2, 0, 'MSG_GRP_002', 2, 1727300260000, 'Mensaje grupal de Bob', 0);
    """)
    # 6. Message from Sender 3
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (2, 0, 'MSG_GRP_003', 4, 1727300320000, 'Mensaje grupal de Charlie', 0);
    """)
    # 7. Outgoing group message from me
    cursor.execute("""
        INSERT INTO message (chat_row_id, from_me, key_id, sender_jid_row_id, timestamp, text_data, message_type)
        VALUES (2, 1, 'MSG_GRP_004', 1, 1727300380000, 'Mi respuesta en el grupo 👍', 0);
    """)

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def synthetic_crypt15_backup(tmp_path: Path, synthetic_sqlite_db: Path) -> Path:
    """Create a real encrypted crypt15 WhatsApp backup using TEST_KEY_HEX."""
    crypt_path = tmp_path / "msgstore.db.crypt15"
    DecryptManager.encrypt_synthetic_backup(synthetic_sqlite_db, TEST_KEY_HEX, crypt_path)
    return crypt_path
