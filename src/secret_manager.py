"""SecretManager handles secure storage and validation of WhatsApp encryption keys."""

import logging
import re
from pathlib import Path

import keyring

from src.config import AppConfig
from src.errors import InvalidKeyError

logger = logging.getLogger(__name__)


class SecretManager:
    """Manages encryption key validation and secure storage in OS keyring."""

    def __init__(self, service_name: str | None = None):
        self.service_name = service_name or AppConfig.KEYRING_SERVICE_NAME

    @staticmethod
    def sanitize_key(raw_key: str) -> str:
        """Strip whitespace, separators, and normalize hex characters to lowercase."""
        if not raw_key:
            return ""
        # Remove spaces, colons, hyphens, newlines
        clean = re.sub(r"[\s\:\-]+", "", raw_key).strip().lower()
        return clean

    @classmethod
    def validate_hex_key(cls, raw_key: str) -> str:
        """Validate that a key is a 64-character hexadecimal string (32 bytes = 256 bits)."""
        clean = cls.sanitize_key(raw_key)
        if not clean:
            raise InvalidKeyError(
                reason="La clave no puede estar vacía.",
                action_recommended="Introduce la clave de cifrado de 64 caracteres hexadecimales.",
            )

        if len(clean) != 64 or not re.fullmatch(r"[0-9a-f]{64}", clean):
            raise InvalidKeyError(
                reason=f"La clave debe tener exactamente 64 caracteres hexadecimales (recibidos: {len(clean)}).",
                action_recommended="Revisa que la clave de 64 caracteres de WhatsApp contenga únicamente caracteres 0-9 y a-f.",
            )

        return clean

    @classmethod
    def validate_key_file(cls, key_file_path: Path) -> bytes:
        """Validate and read a binary WhatsApp key file (typically 158 bytes for crypt14/15 or 32-byte raw key)."""
        if not key_file_path.is_file():
            raise InvalidKeyError(
                reason=f"No se encuentra el archivo de clave en '{key_file_path}'.",
                action_recommended="Verifica la ruta al archivo de clave .key.",
            )

        data = key_file_path.read_bytes()
        if len(data) not in (32, 158):
            # Check if it's text hex in the file
            try:
                text_content = data.decode("utf-8").strip()
                if len(text_content) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", text_content):
                    return bytes.fromhex(text_content)
            except UnicodeDecodeError:
                pass
            raise InvalidKeyError(
                reason=f"El tamaño del archivo de clave ({len(data)} bytes) no es compatible (esperado: 32 bytes de clave bruta o 158 bytes de cabecera WhatsApp).",
                action_recommended="Proporciona la clave de 64 dígitos hexadecimales o un archivo .key válido.",
            )

        return data

    def store_key(self, key_hex: str, account_id: str = "default") -> None:
        """Store the validated hex key in the OS secure vault."""
        valid_hex = self.validate_hex_key(key_hex)
        try:
            keyring.set_password(self.service_name, account_id, valid_hex)
            logger.info(f"Encryption key stored securely for account '{account_id}'.")
        except Exception as e:
            logger.error(f"Failed to access OS keyring: {e}")
            raise InvalidKeyError(
                reason=f"No se pudo guardar la clave en el almacén seguro del sistema: {e}",
                action_recommended="Permite el acceso al almacén de credenciales del sistema o introduce la clave por parámetro.",
            )

    def get_key(self, account_id: str = "default") -> str | None:
        """Retrieve the encryption key from the OS secure vault."""
        try:
            key = keyring.get_password(self.service_name, account_id)
            if key:
                return self.sanitize_key(key)
            return None
        except Exception as e:
            logger.warning(f"Could not read from OS keyring: {e}")
            return None

    def has_key(self, account_id: str = "default") -> bool:
        """Check if an encryption key exists in the OS secure vault."""
        k = self.get_key(account_id)
        return bool(k and len(k) == 64)

    def delete_key(self, account_id: str = "default") -> bool:
        """Delete the stored encryption key from the OS secure vault."""
        try:
            keyring.delete_password(self.service_name, account_id)
            logger.info(f"Encryption key deleted for account '{account_id}'.")
            return True
        except Exception as e:
            logger.warning(f"Could not delete password from keyring: {e}")
            return False

    @staticmethod
    def mask_key(raw_key: str) -> str:
        """Return a masked representation of the key for safe logging and UI display."""
        if not raw_key or len(raw_key) < 8:
            return "********"
        return f"{raw_key[:4]}...{raw_key[-4:]}"
