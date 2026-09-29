"""Unit tests for VaultDatabase deduplication and incremental consolidation."""

from pathlib import Path
from src.database import VaultDatabase
from src.models import BackupMetadata, Conversation, Message


def test_vault_database_deduplication(tmp_path: Path):
    """Test that importing the same messages multiple times does not produce duplicates."""
    db_file = tmp_path / "test_vault.db"
    vault = VaultDatabase(db_file)

    convs = [
        Conversation(
            conversation_id="chat_1",
            conversation_name="Alice",
            conversation_type="individual",
            original_jid="chat_1",
            last_message_at="2026-09-25T12:00:00Z",
            message_count=2,
        )
    ]

    msgs = [
        Message(
            message_uid="UID_001",
            conversation_id="chat_1",
            sender_id="sender_1",
            sender_name="Alice",
            direction="incoming",
            timestamp_utc="2026-09-25T12:00:00Z",
            timestamp_local="2026-09-25T14:00:00+02:00",
            message_type="text",
            text="Hello 1",
            source_backup_id="backup_1",
        ),
        Message(
            message_uid="UID_002",
            conversation_id="chat_1",
            sender_id="me",
            sender_name=None,
            direction="outgoing",
            timestamp_utc="2026-09-25T12:01:00Z",
            timestamp_local="2026-09-25T14:01:00+02:00",
            message_type="text",
            text="Hello 2",
            source_backup_id="backup_1",
        ),
    ]

    vault.upsert_conversations(convs)
    total, inserted, updated = vault.consolidate_messages(msgs, "backup_1")
    assert total == 2
    assert inserted == 2
    assert updated == 0
    assert len(vault.get_all_messages()) == 2

    # Second import with identical messages
    total2, inserted2, updated2 = vault.consolidate_messages(msgs, "backup_1")
    assert total2 == 2
    assert inserted2 == 0
    assert updated2 == 0
    assert len(vault.get_all_messages()) == 2


def test_vault_incremental_update(tmp_path: Path):
    """Test importing new messages incrementally alongside existing messages."""
    db_file = tmp_path / "test_vault.db"
    vault = VaultDatabase(db_file)

    # Initial batch
    m1 = Message(
        message_uid="UID_001",
        conversation_id="chat_1",
        sender_id="sender_1",
        sender_name="Alice",
        direction="incoming",
        timestamp_utc="2026-09-25T12:00:00Z",
        timestamp_local="2026-09-25T14:00:00+02:00",
        message_type="text",
        text="Original text",
        source_backup_id="backup_1",
    )
    vault.consolidate_messages([m1], "backup_1")

    # Incremental batch: m1 edited, m2 is new
    m1_edited = Message(
        message_uid="UID_001",
        conversation_id="chat_1",
        sender_id="sender_1",
        sender_name="Alice",
        direction="incoming",
        timestamp_utc="2026-09-25T12:00:00Z",
        timestamp_local="2026-09-25T14:00:00+02:00",
        message_type="text",
        text="Edited text",
        edited=True,
        source_backup_id="backup_2",
    )
    m2_new = Message(
        message_uid="UID_002",
        conversation_id="chat_1",
        sender_id="me",
        sender_name=None,
        direction="outgoing",
        timestamp_utc="2026-09-25T12:05:00Z",
        timestamp_local="2026-09-25T14:05:00+02:00",
        message_type="text",
        text="New message in backup 2",
        source_backup_id="backup_2",
    )

    total, inserted, updated = vault.consolidate_messages([m1_edited, m2_new], "backup_2")
    assert total == 2
    assert inserted == 1
    assert updated == 1

    all_msgs = vault.get_all_messages()
    assert len(all_msgs) == 2
    m1_stored = [m for m in all_msgs if m.message_uid == "UID_001"][0]
    assert m1_stored.text == "Edited text"
    assert m1_stored.edited is True


def test_vault_multi_account_isolation(tmp_path: Path):
    """Test that messages and conversations belonging to different accounts are isolated."""
    db_file = tmp_path / "test_vault_multi.db"
    vault = VaultDatabase(db_file)

    # Principal account message
    m_principal = Message(
        message_uid="UID_P01",
        conversation_id="conv_work",
        sender_id="boss",
        sender_name="Boss",
        direction="incoming",
        timestamp_utc="2026-09-25T10:00:00Z",
        timestamp_local="2026-09-25T10:00:00Z",
        message_type="text",
        text="Work message",
        source_backup_id="bk_p",
    )
    vault.consolidate_messages([m_principal], "bk_p", account_id="principal")

    # Dual Xiaomi account message with same conversation_id name
    m_dual = Message(
        message_uid="UID_D01",
        conversation_id="conv_personal",
        sender_id="friend",
        sender_name="Friend",
        direction="incoming",
        timestamp_utc="2026-09-25T11:00:00Z",
        timestamp_local="2026-09-25T11:00:00Z",
        message_type="text",
        text="Personal dual message",
        source_backup_id="bk_d",
    )
    vault.consolidate_messages([m_dual], "bk_d", account_id="dual_xiaomi")

    # Verify filtered queries
    principal_msgs = vault.get_all_messages(account_id="principal")
    assert len(principal_msgs) == 1
    assert principal_msgs[0].text == "Work message"

    dual_msgs = vault.get_all_messages(account_id="dual_xiaomi")
    assert len(dual_msgs) == 1
    assert dual_msgs[0].text == "Personal dual message"


def test_vault_multi_device_isolation(tmp_path: Path):
    """Test that messages and conversations belonging to different hardware devices are isolated."""
    db_file = tmp_path / "test_vault_multi_dev.db"
    vault = VaultDatabase(db_file)

    # Message from POCO Phone
    m_poco = Message(
        message_uid="UID_POCO_01",
        conversation_id="chat_1",
        sender_id="sender_poco",
        sender_name="Poco Contact",
        direction="incoming",
        timestamp_utc="2026-09-25T10:00:00Z",
        timestamp_local="2026-09-25T10:00:00Z",
        message_type="text",
        text="Poco device message",
        source_backup_id="bk_poco",
    )
    vault.consolidate_messages([m_poco], "bk_poco", account_id="principal", device_serial="poco_c83eb1a")

    # Message from Samsung Phone
    m_samsung = Message(
        message_uid="UID_SAMSUNG_01",
        conversation_id="chat_1",
        sender_id="sender_samsung",
        sender_name="Samsung Contact",
        direction="incoming",
        timestamp_utc="2026-09-25T11:00:00Z",
        timestamp_local="2026-09-25T11:00:00Z",
        message_type="text",
        text="Samsung device message",
        source_backup_id="bk_samsung",
    )
    vault.consolidate_messages([m_samsung], "bk_samsung", account_id="principal", device_serial="samsung_r58m")

    # Filtered by device serial
    poco_msgs = vault.get_all_messages(account_id="principal", device_serial="poco_c83eb1a")
    assert len(poco_msgs) == 1
    assert poco_msgs[0].text == "Poco device message"

    samsung_msgs = vault.get_all_messages(account_id="principal", device_serial="samsung_r58m")
    assert len(samsung_msgs) == 1
    assert samsung_msgs[0].text == "Samsung device message"


def test_vault_legacy_schema_migration(tmp_path: Path):
    """Test that an existing database without account_id or device_serial is migrated smoothly."""
    import sqlite3

    db_file = tmp_path / "legacy_vault.db"
    # Create legacy tables without account_id and device_serial columns
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE backups (
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

        CREATE TABLE conversations (
            conversation_id TEXT PRIMARY KEY,
            conversation_name TEXT,
            conversation_type TEXT,
            original_jid TEXT,
            last_message_at TEXT,
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE messages (
            message_uid TEXT PRIMARY KEY,
            conversation_id TEXT,
            sender_id TEXT,
            sender_name TEXT,
            direction TEXT,
            timestamp_utc TEXT,
            timestamp_local TEXT,
            message_type TEXT,
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

        CREATE TABLE export_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
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
    conn.close()

    # Now instantiate VaultDatabase, which runs init_db() and schema migrations
    vault = VaultDatabase(db_file)

    # Verify that columns were added and queries with filters work
    convs = vault.get_all_conversations(account_id="principal")
    assert convs == []
    msgs = vault.get_all_messages(account_id="principal", device_serial="")
    assert msgs == []



