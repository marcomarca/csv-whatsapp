"""Domain models and data transfer objects."""

from dataclasses import dataclass, field


@dataclass
class DeviceInfo:
    """Information about an Android device connected via ADB."""

    serial: str
    state: str  # "device", "unauthorized", "offline", "unknown"
    model: str = ""
    manufacturer: str = ""
    brand: str = ""
    android_version: str = ""
    whatsapp_packages: list[str] = field(default_factory=list)

    @property
    def is_authorized(self) -> bool:
        return self.state == "device"


@dataclass
class RemoteBackupInfo:
    """Information about a WhatsApp backup file found on the remote Android device."""

    remote_path: str
    filename: str
    file_size: int
    modified_at: str
    format: str  # "crypt15", "crypt14", "crypt12", "unknown"
    is_main: bool = False


@dataclass
class BackupMetadata:
    """Metadata recorded for a local copy of a WhatsApp backup."""

    backup_id: str
    device_id: str
    source_path: str
    filename: str
    format: str
    file_size: int
    sha256: str
    source_modified_at: str
    imported_at: str
    decryption_status: str  # "pending", "success", "failed"
    parser_version: str = "WhaPa-2.0"
    message_count: int = 0


@dataclass
class WhatsAppAccount:
    """Represents a distinct WhatsApp account profile on the Android device."""

    account_id: str  # "principal", "dual_xiaomi", "samsung_dual", "business_principal", etc.
    display_name: str  # "WhatsApp (Principal)", "WhatsApp (Samsung Dual Messenger)"
    android_user_id: int  # 0, 95, 96, 150, 999, 10, etc.
    package_name: str  # "com.whatsapp", "com.whatsapp.w4b"
    remote_db_dir: str
    device_serial: str = ""
    manufacturer: str = ""
    latest_backup_file: str | None = None
    latest_backup_size_mb: float = 0.0
    latest_backup_date: str | None = None
    crypt_format: str = "unknown"  # "crypt15", "crypt14", "crypt12", "unknown"
    is_dual: bool = False


@dataclass
class Conversation:
    """Representation of a WhatsApp chat/conversation."""

    conversation_id: str
    conversation_name: str
    conversation_type: str  # "individual", "group", "broadcast", "system"
    original_jid: str
    account_id: str = "principal"
    device_serial: str = ""
    last_message_at: str | None = None
    message_count: int = 0


@dataclass
class Message:
    """Representation of a single WhatsApp message."""

    message_uid: str
    conversation_id: str
    sender_id: str
    sender_name: str | None
    direction: str  # "incoming", "outgoing", "system"
    timestamp_utc: str  # ISO-8601 UTC
    timestamp_local: str  # ISO-8601 Local
    message_type: str  # "text", "image", "audio", "video", "document", "location", "sticker", "call", "system", "unknown"
    account_id: str = "principal"
    device_serial: str = ""
    text: str | None = None
    media_path: str | None = None
    media_mime: str | None = None
    media_size: int | None = None
    media_status: str = "not_exported"  # "available", "missing", "not_exported"
    quoted_message_id: str | None = None
    forwarded: bool = False
    edited: bool = False
    starred: bool = False
    raw_type_code: int | None = None
    source_backup_id: str = ""


@dataclass
class ExportRun:
    """Execution log for an export run."""

    run_id: str
    started_at: str
    account_id: str = "principal"
    device_serial: str = ""
    finished_at: str | None = None
    status: str = "started"  # "started", "completed", "failed"
    backup_id: str | None = None
    total_conversations: int = 0
    total_messages: int = 0
    inserted_messages: int = 0
    updated_messages: int = 0
    warnings: str = ""
    error_code: str | None = None


@dataclass
class ExportManifest:
    """Manifest JSON output produced during CSV export."""

    run_id: str
    exported_at: str
    backup_file: str
    backup_sha256: str
    total_conversations: int
    total_messages: int
    files_generated: list[str]
    tool_versions: dict[str, str]
    account_id: str = "principal"
    device_serial: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "device_serial": self.device_serial,
            "account_id": self.account_id,
            "exported_at": self.exported_at,
            "backup_file": self.backup_file,
            "backup_sha256": self.backup_sha256,
            "total_conversations": self.total_conversations,
            "total_messages": self.total_messages,
            "files_generated": self.files_generated,
            "tool_versions": self.tool_versions,
            "warnings": self.warnings,
        }
