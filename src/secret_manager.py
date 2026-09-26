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

    def _normalize_account_id(self, account_id: str | None) -> str:
        """Normalize account ID, mapping None or 'default' to 'principal'."""
        if not account_id or account_id == "default":
            return "principal"
        return account_id.strip().lower()

    def store_key(
        self,
        key_hex: str,
        account_id: str = "principal",
        serial: str | None = None,
    ) -> None:
        """Store the validated hex key in the OS secure vault (optionally bound to device serial)."""
        valid_hex = self.validate_hex_key(key_hex)
        target_account = self._normalize_account_id(account_id)
        try:
            if serial:
                device_key_id = f"{serial.strip().lower()}_{target_account}"
                keyring.set_password(self.service_name, device_key_id, valid_hex)
            keyring.set_password(self.service_name, target_account, valid_hex)
            logger.info(f"Encryption key stored securely for account '{target_account}'.")
        except Exception as e:
            logger.error(f"Failed to access OS keyring: {e}")
            raise InvalidKeyError(
                reason=f"No se pudo guardar la clave en el almacén seguro del sistema: {e}",
                action_recommended="Permite el acceso al almacén de credenciales del sistema o introduce la clave por parámetro.",
            )

    def get_key(
        self,
        account_id: str = "principal",
        serial: str | None = None,
    ) -> str | None:
        """Retrieve the encryption key from the OS secure vault with serial and account fallback."""
        target_account = self._normalize_account_id(account_id)
        try:
            # 1. Device-serial specific key
            if serial:
                device_key_id = f"{serial.strip().lower()}_{target_account}"
                dev_key = keyring.get_password(self.service_name, device_key_id)
                if dev_key:
                    return self.sanitize_key(dev_key)

            # 2. Account-specific key
            key = keyring.get_password(self.service_name, target_account)
            if key:
                return self.sanitize_key(key)

            # 3. Backwards compatibility check for legacy 'default'
            if target_account == "principal":
                legacy_key = keyring.get_password(self.service_name, "default")
                if legacy_key:
                    return self.sanitize_key(legacy_key)
            return None
        except Exception as e:
            logger.warning(f"Could not read from OS keyring: {e}")
            return None

    def has_key(
        self,
        account_id: str = "principal",
        serial: str | None = None,
    ) -> bool:
        """Check if an encryption key exists in the OS secure vault."""
        k = self.get_key(account_id, serial=serial)
        return bool(k and len(k) == 64)

    def delete_key(
        self,
        account_id: str = "principal",
        serial: str | None = None,
    ) -> bool:
        """Delete the stored encryption key from the OS secure vault."""
        target_account = self._normalize_account_id(account_id)
        deleted = False
        try:
            if serial:
                device_key_id = f"{serial.strip().lower()}_{target_account}"
                try:
                    keyring.delete_password(self.service_name, device_key_id)
                    deleted = True
                except Exception:
                    pass
            keyring.delete_password(self.service_name, target_account)
            deleted = True
            logger.info(f"Encryption key deleted for account '{target_account}'.")
            return deleted
        except Exception as e:
            logger.warning(f"Could not delete password from keyring: {e}")
            return deleted

    def list_stored_accounts(self) -> list[str]:
        """List known account IDs that have stored keys in keyring."""
        candidates = [
            "principal",
            "dual_xiaomi",
            "samsung_dual",
            "samsung_secure",
            "dual_honor",
            "dual_realme",
            "dual_oppo",
            "dual_vivo",
            "business_principal",
            "business_dual",
            "default",
        ]
        stored = []
        for acc in candidates:
            if self.has_key(acc) and acc not in stored:
                stored.append(acc)
        return stored

    @staticmethod
    def mask_key(raw_key: str) -> str:
        """Return a masked representation of the key for safe logging and UI display."""
        if not raw_key or len(raw_key) < 8:
            return "********"
        return f"{raw_key[:4]}...{raw_key[-4:]}"
