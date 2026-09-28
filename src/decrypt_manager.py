"""DecryptManager handles decryption of WhatsApp backups (crypt12, crypt14, crypt15) and SQLite integrity checks."""

import logging
import sqlite3
import sys
from pathlib import Path

from src.config import AppConfig
from src.errors import (
    DecryptionFailedError,
    InvalidKeyError,
    InvalidSQLiteError,
    WhatsAppBackupError,
)

# Add vendor whapa libs to sys.path
if str(AppConfig.WHAPA_LIBS_DIR) not in sys.path:
    sys.path.insert(0, str(AppConfig.WHAPA_LIBS_DIR))

try:
    import whacipher
except ImportError:
    whacipher = None

logger = logging.getLogger(__name__)


class DecryptManager:
    """Decrypts WhatsApp backup databases and verifies SQLite structure and integrity."""

    SQLITE_HEADER = b"SQLite format 3\x00"

    @classmethod
    def identify_format(cls, backup_path: Path) -> str:
        """Determine backup encryption format from file extension or content."""
        ext = backup_path.suffix.lower()
        if ext == ".crypt15":
            return "crypt15"
        elif ext == ".crypt14":
            return "crypt14"
        elif ext == ".crypt12":
            return "crypt12"

        # Check if already an unencrypted SQLite file
        if backup_path.is_file() and backup_path.stat().st_size >= 16:
            try:
                with open(backup_path, "rb") as f:
                    header = f.read(16)
                    if header == cls.SQLITE_HEADER:
                        return "sqlite"
            except OSError:
                pass

        # Check filename pattern
        name = backup_path.name.lower()
        if "crypt15" in name:
            return "crypt15"
        if "crypt14" in name:
            return "crypt14"
        if "crypt12" in name:
            return "crypt12"

        return "unknown"

    @classmethod
    def validate_sqlite(cls, db_path: Path) -> bool:
        """Validate SQLite header, integrity check, and schema structure."""
        if not db_path.is_file() or db_path.stat().st_size < 100:
            raise InvalidSQLiteError(
                reason="El archivo de base de datos descifrado está vacío o es demasiado pequeño."
            )

        # 1. Header magic check
        with open(db_path, "rb") as f:
            header = f.read(16)
            if header != cls.SQLITE_HEADER:
                raise InvalidSQLiteError(
                    reason="La cabecera del archivo descifrado no coincide con 'SQLite format 3'. La clave de descifrado es incorrecta o los datos están corruptos."
                )

        # 2. SQLite integrity check
        try:
            conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Run quick_check
            cursor.execute("PRAGMA quick_check;")
            res = cursor.fetchone()
            if not res or res[0].lower() != "ok":
                conn.close()
                raise InvalidSQLiteError(
                    reason=f"Fallo en PRAGMA quick_check: {res[0] if res else 'sin respuesta'}."
                )

            # Check for recognized WhatsApp tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()

            expected_tables = {"message", "messages", "chat", "jid", "chat_view", "messages_quotes"}
            matching = expected_tables.intersection(set(tables))
            if not matching and len(tables) > 0:
                logger.warning(
                    f"Warning: SQLite tables found ({tables}) do not match typical WhatsApp schema."
                )
            elif not tables:
                raise InvalidSQLiteError(reason="La base de datos SQLite no contiene tablas.")

            logger.info(f"SQLite validation successful for {db_path} ({len(tables)} tables found).")
            return True

        except sqlite3.DatabaseError as e:
            raise InvalidSQLiteError(
                reason=f"Error al abrir la base de datos SQLite descifrada: {e}"
            )

    @classmethod
    def decrypt(
        cls,
        encrypted_path: Path,
        key: str | Path,
        output_path: Path,
    ) -> Path:
        """Decrypt backup file using provided hex key or key file and validate output."""
        if not encrypted_path.is_file():
            raise DecryptionFailedError(
                reason=f"No se encontró el archivo de backup en '{encrypted_path}'."
            )

        fmt = cls.identify_format(encrypted_path)
        logger.info(f"Decrypting {encrypted_path} (format: {fmt}) -> {output_path}...")

        # If already unencrypted SQLite, copy directly
        if fmt == "sqlite":
            import shutil

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(encrypted_path, output_path)
            cls.validate_sqlite(output_path)
            return output_path

        # Handle key
        key_source = str(key) if isinstance(key, Path) else key.strip()

        # Try using whacipher or wa_crypt_tools
        temp_out = output_path.with_suffix(".tmp_decrypted")
        temp_out.parent.mkdir(parents=True, exist_ok=True)

        try:
            if whacipher is not None:
                success = whacipher.decrypt(str(encrypted_path), key_source, str(temp_out))
                if not success or not temp_out.is_file() or temp_out.stat().st_size == 0:
                    raise DecryptionFailedError(
                        reason="El proceso de descifrado no generó datos válidos."
                    )
            else:
                import zlib
                from wa_crypt_tools.wadecrypt import DatabaseFactory, KeyFactory

                with open(encrypted_path, "rb") as enc_f:
                    db = DatabaseFactory.from_file(enc_f)
                    key_obj = KeyFactory.new(key_source)
                    output_decrypted = db.decrypt(key_obj, enc_f.read())
                    try:
                        z_obj = zlib.decompressobj()
                        output_data = z_obj.decompress(output_decrypted)
                    except zlib.error:
                        output_data = output_decrypted

                    with open(temp_out, "wb") as out_f:
                        out_f.write(output_data)

            # Validate SQLite
            cls.validate_sqlite(temp_out)

            # Move atomically
            if output_path.exists():
                output_path.unlink()
            temp_out.replace(output_path)
            logger.info(f"Decryption and validation successful: {output_path}")
            return output_path

        except (ValueError, KeyError, Exception) as e:
            if temp_out.exists():
                temp_out.unlink(missing_ok=True)
            if isinstance(e, WhatsAppBackupError):
                raise
            raise InvalidKeyError(
                reason=f"Error criptográfico durante el descifrado: {e}. Comprueba que la clave pertenezca a esta copia.",
            )

    @classmethod
    def encrypt_synthetic_backup(
        cls,
        sqlite_path: Path,
        key_hex: str,
        output_path: Path,
    ) -> Path:
        """Create a synthetic encrypted crypt15 backup for testing."""
        if whacipher is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            whacipher.encrypt(str(sqlite_path), key_hex, str(output_path))
            return output_path

        import zlib
        from wa_crypt_tools.wadecrypt import KeyFactory
        from wa_crypt_tools.waencrypt import Database15, Props

        key_obj = KeyFactory.from_hex(key_hex)
        with open(sqlite_path, "rb") as in_f:
            data = in_f.read()
        db = Database15(key=key_obj)
        compressed = zlib.compress(data, 1)
        encrypted = db.encrypt(key_obj, Props(), compressed)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as out_f:
            out_f.write(encrypted)
        return output_path
