"""Unit tests for MessageParser extraction, Unicode, and groups."""

from pathlib import Path
from src.message_parser import MessageParser


def test_parse_synthetic_database(synthetic_sqlite_db: Path):
    """Test parsing messages and conversations from decrypted SQLite database."""
    convs, msgs = MessageParser.parse_database(synthetic_sqlite_db, backup_id="test_backup")

    assert len(convs) >= 2
    assert len(msgs) >= 7

    # Find Alice chat
    alice_msgs = [m for m in msgs if "Alice" in m.conversation_id or "34600111222" in m.conversation_id]
    assert len(alice_msgs) >= 3

    # Check Unicode message
    unicode_msg = [m for m in alice_msgs if "áéíóú" in (m.text or "")][0]
    assert "☕✨" in unicode_msg.text
    assert "Línea 2" in unicode_msg.text
    assert unicode_msg.direction == "incoming"

    # Check formula injection message
    formula_msg = [m for m in alice_msgs if "=SUM" in (m.text or "")][0]
    assert formula_msg.direction == "outgoing"

    # Check media message
    media_msg = [m for m in alice_msgs if m.media_path][0]
    assert "IMG-20260925-WA0001.jpg" in media_msg.media_path

    # Check Group chat with multiple senders
    group_msgs = [m for m in msgs if "12345678-14508" in m.conversation_id]
    assert len(group_msgs) >= 4
    senders = {m.sender_id for m in group_msgs}
    assert len(senders) >= 3  # Distinct senders present
