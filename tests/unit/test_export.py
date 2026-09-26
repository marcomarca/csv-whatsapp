"""Unit tests for ExportManager, UTF-8 BOM, formula escaping, and atomic writes."""

import csv
import json
from pathlib import Path
import pandas as pd
import pytest

from src.export_manager import ExportManager
from src.models import Conversation, ExportManifest, Message


def test_csv_export_and_bom_encoding(tmp_path: Path):
    """Test generating CSV files and verifying UTF-8 with BOM for Excel compatibility."""
    out_dir = tmp_path / "exports"

    convs = [
        Conversation(
            conversation_id="34600111222@s.whatsapp.net",
            conversation_name="Alice 🌸",
            conversation_type="individual",
            original_jid="34600111222@s.whatsapp.net",
            last_message_at="2026-09-25T12:00:00Z",
            message_count=2,
        )
    ]

    msgs = [
        Message(
            message_uid="MSG_001",
            conversation_id="34600111222@s.whatsapp.net",
            sender_id="34600111222@s.whatsapp.net",
            sender_name="Alice",
            direction="incoming",
            timestamp_utc="2026-09-25T12:00:00Z",
            timestamp_local="2026-09-25T14:00:00+02:00",
            message_type="text",
            text="¡Hola! ☕ Con acentos áéíóú y saltos\nde línea",
            source_backup_id="backup_hash",
        ),
        Message(
            message_uid="MSG_002",
            conversation_id="34600111222@s.whatsapp.net",
            sender_id="me",
            sender_name=None,
            direction="outgoing",
            timestamp_utc="2026-09-25T12:01:00Z",
            timestamp_local="2026-09-25T14:01:00+02:00",
            message_type="text",
            text="=SUM(1+1) y +cmd y @admin",
            source_backup_id="backup_hash",
        ),
    ]

    manifest = ExportManifest(
        run_id="run_123",
        exported_at="2026-09-25T12:05:00Z",
        backup_file="msgstore.db.crypt15",
        backup_sha256="abcdef123456",
        total_conversations=1,
        total_messages=2,
        files_generated=[],
        tool_versions={"wa-crypt-tools": "0.1.0"},
    )

    written = ExportManager.export_all(convs, msgs, manifest, output_dir=out_dir)
    assert len(written) == 4  # all_messages.csv, conversations.csv, 1 conversation CSV, manifest.json

    all_msgs_file = out_dir / "all_messages.csv"
    assert all_msgs_file.is_file()

    # Check BOM bytes
    with open(all_msgs_file, "rb") as f:
        header_bytes = f.read(3)
        assert header_bytes == b"\xef\xbb\xbf"  # UTF-8 BOM

    # Open with pandas to test dataframe compatibility
    df = pd.read_csv(all_msgs_file, encoding="utf-8-sig")
    assert len(df) == 2
    assert "¡Hola! ☕ Con acentos áéíóú y saltos\nde línea" in df["text"].values

    # Check formula escaping
    row2_text = df[df["message_uid"] == "MSG_002"]["text"].values[0]
    assert row2_text.startswith("'=")  # Preceded by single quote

    # Check manifest.json
    manifest_file = out_dir / "manifest.json"
    assert manifest_file.is_file()
    with open(manifest_file, "r", encoding="utf-8") as f:
        m_data = json.load(f)
        assert m_data["run_id"] == "run_123"
        assert m_data["total_messages"] == 2


def test_atomic_export_preserves_existing_on_error(tmp_path: Path, monkeypatch):
    """Test that a failure during export does not overwrite or corrupt existing CSVs."""
    out_dir = tmp_path / "exports"
    out_dir.mkdir(parents=True)
    all_msgs = out_dir / "all_messages.csv"
    all_msgs.write_text("PREVIOUS_VALID_CSV_CONTENT", encoding="utf-8")

    # Simulate error inside atomic write
    def fail_write(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(ExportManager, "_atomic_write_csv", fail_write)

    convs = [Conversation("c1", "Test", "individual", "c1")]
    msgs = [Message("m1", "c1", "s1", None, "in", "2026", "2026", "text", "test")]
    manifest = ExportManifest("r1", "2026", "b", "h", 1, 1, [], {})

    with pytest.raises(Exception):
        ExportManager.export_all(convs, msgs, manifest, output_dir=out_dir)

    # Previous file must remain untouched
    assert all_msgs.read_text(encoding="utf-8") == "PREVIOUS_VALID_CSV_CONTENT"
