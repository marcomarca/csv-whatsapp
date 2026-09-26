"""Structured domain and infrastructure error classes."""

from dataclasses import dataclass


@dataclass
class WhatsAppBackupError(Exception):
    """Base exception for all WhatsApp Backup to CSV operations."""

    code: str
    message: str
    operation: str
    action_recommended: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} (Operación: {self.operation}) -> Acción: {self.action_recommended}"


class DeviceNotFoundError(WhatsAppBackupError):
    def __init__(
        self,
        operation: str = "detect_device",
        message: str = "No se ha detectado ningún dispositivo Android conectado mediante USB.",
        action_recommended: str = "Conecta el teléfono por USB con transferencia de datos habilitada y pantalla desbloqueada.",
        retryable: bool = True,
    ):
        super().__init__(
            code="DEVICE_NOT_FOUND",
            message=message,
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class DeviceUnauthorizedError(WhatsAppBackupError):
    def __init__(
        self,
        serial: str = "",
        operation: str = "check_device_auth",
        message: str = "El dispositivo Android está conectado pero no está autorizado para depuración USB.",
        action_recommended: str = "Desbloquea el teléfono y acepta el diálogo '¿Permitir depuración por USB?' en la pantalla.",
        retryable: bool = True,
    ):
        full_msg = f"{message} (Dispositivo: {serial})" if serial else message
        super().__init__(
            code="DEVICE_UNAUTHORIZED",
            message=full_msg,
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class MultipleDevicesError(WhatsAppBackupError):
    def __init__(
        self,
        devices: list[str],
        operation: str = "select_device",
        message: str = "Se han detectado múltiples dispositivos conectados.",
        action_recommended: str = "Especifica el número de serie con el parámetro --serial o desconecta los demás dispositivos.",
        retryable: bool = False,
    ):
        devs = ", ".join(devices)
        super().__init__(
            code="MULTIPLE_DEVICES",
            message=f"{message} Encontrados: {devs}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class BackupNotFoundError(WhatsAppBackupError):
    def __init__(
        self,
        searched_paths: list[str] | None = None,
        operation: str = "find_backup",
        message: str = "No se encontró ningún archivo de copia de seguridad (msgstore.db.crypt*) en el teléfono.",
        action_recommended: str = "Abre WhatsApp > Ajustes > Chats > Copia de seguridad y pulsa 'Guardar' para crear una copia local.",
        retryable: bool = True,
    ):
        paths_str = f" Rutas revisadas: {', '.join(searched_paths)}" if searched_paths else ""
        super().__init__(
            code="BACKUP_NOT_FOUND",
            message=f"{message}{paths_str}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class BackupOutdatedError(WhatsAppBackupError):
    def __init__(
        self,
        backup_date: str,
        operation: str = "check_backup_freshness",
        message: str = "La copia de seguridad encontrada es antigua y no se ha generado una nueva.",
        action_recommended: str = "Genera una copia actualizada en WhatsApp antes de exportar, o utiliza la opción --force para continuar.",
        retryable: bool = True,
    ):
        super().__init__(
            code="BACKUP_OUTDATED",
            message=f"{message} (Fecha del backup: {backup_date})",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class BackupCopyFailedError(WhatsAppBackupError):
    def __init__(
        self,
        source: str,
        target: str,
        reason: str = "",
        operation: str = "adb_pull",
        message: str = "Falló la transferencia del archivo de copia de seguridad desde el teléfono.",
        action_recommended: str = "Comprueba el cable USB, que el dispositivo tenga suficiente batería y espacio en disco.",
        retryable: bool = True,
    ):
        detail = f" Detalle: {reason}" if reason else ""
        super().__init__(
            code="BACKUP_COPY_FAILED",
            message=f"{message} ({source} -> {target}).{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class InvalidKeyError(WhatsAppBackupError):
    def __init__(
        self,
        reason: str = "",
        operation: str = "validate_key",
        message: str = "La clave de cifrado proporcionada no es válida o tiene un formato incorrecto.",
        action_recommended: str = "Introduce la clave de 64 caracteres hexadecimales de la copia de seguridad cifrada de extremo a extremo de WhatsApp.",
        retryable: bool = True,
    ):
        detail = f" Detalle: {reason}" if reason else ""
        super().__init__(
            code="INVALID_KEY",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class DecryptionFailedError(WhatsAppBackupError):
    def __init__(
        self,
        reason: str = "",
        operation: str = "decrypt_backup",
        message: str = "Error al descifrar el backup. La clave probablemente no coincide o el archivo está incompleto.",
        action_recommended: str = "Verifica que la clave hexadecimal de 64 dígitos corresponda exactamente a la cuenta y backup de este teléfono.",
        retryable: bool = True,
    ):
        detail = f" Detalle: {reason}" if reason else ""
        super().__init__(
            code="DECRYPTION_FAILED",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class InvalidSQLiteError(WhatsAppBackupError):
    def __init__(
        self,
        reason: str = "",
        operation: str = "validate_sqlite",
        message: str = "El archivo descifrado no es una base de datos SQLite íntegra o está dañado.",
        action_recommended: str = "Reintenta la exportación generando una nueva copia de seguridad en WhatsApp.",
        retryable: bool = True,
    ):
        detail = f" Detalle: {reason}" if reason else ""
        super().__init__(
            code="INVALID_SQLITE",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class UnsupportedSchemaError(WhatsAppBackupError):
    def __init__(
        self,
        schema_version: str = "",
        operation: str = "parse_schema",
        message: str = "El esquema de la base de datos de WhatsApp no es compatible con los parsers disponibles.",
        action_recommended: str = "Actualiza el parser WhaPa o consulta la documentación de compatibilidad.",
        retryable: bool = False,
    ):
        detail = f" Versión/Tablas detectadas: {schema_version}" if schema_version else ""
        super().__init__(
            code="UNSUPPORTED_SCHEMA",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class ParserFailedError(WhatsAppBackupError):
    def __init__(
        self,
        reason: str = "",
        operation: str = "parse_messages",
        message: str = "Error durante el análisis y extracción de mensajes desde la base de datos.",
        action_recommended: str = "Revisa los registros técnicos en data/logs/ para identificar los registros anómalos.",
        retryable: bool = False,
    ):
        detail = f" Detalle: {reason}" if reason else ""
        super().__init__(
            code="PARSER_FAILED",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class ExportFailedError(WhatsAppBackupError):
    def __init__(
        self,
        reason: str = "",
        operation: str = "write_csv",
        message: str = "Error al generar los archivos CSV finales o el manifiesto.",
        action_recommended: str = "Comprueba los permisos de escritura en la carpeta data/exports/ y que no haya archivos abiertos en Excel.",
        retryable: bool = True,
    ):
        detail = f" Detalle: {reason}" if reason else ""
        super().__init__(
            code="EXPORT_FAILED",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )


class InsufficientDiskSpaceError(WhatsAppBackupError):
    def __init__(
        self,
        required_mb: float = 0,
        available_mb: float = 0,
        operation: str = "check_disk_space",
        message: str = "Espacio insuficiente en el disco local para completar la transferencia y descifrado.",
        action_recommended: str = "Libera espacio en la unidad de disco donde está ubicado el proyecto.",
        retryable: bool = True,
    ):
        detail = (
            f" (Requerido: {required_mb:.1f} MB, Disponible: {available_mb:.1f} MB)"
            if required_mb
            else ""
        )
        super().__init__(
            code="INSUFFICIENT_DISK_SPACE",
            message=f"{message}{detail}",
            operation=operation,
            action_recommended=action_recommended,
            retryable=retryable,
        )
