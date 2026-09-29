"""Centralized logging configuration and exception hooks for WhatsApp Backup to CSV."""

import logging
import sys
import threading
import traceback
from pathlib import Path

from src.config import AppConfig

_LOGGING_INITIALIZED = False


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Initialize root file and console logging handlers."""
    global _LOGGING_INITIALIZED
    AppConfig.ensure_directories()
    log_file = AppConfig.LOGS_DIR / "whatsapp_backup.log"
    level = logging.DEBUG if verbose else logging.INFO

    root_logger = logging.getLogger()
    
    # If already initialized, just adjust level
    if _LOGGING_INITIALIZED:
        root_logger.setLevel(level)
        return logging.getLogger("src")

    root_logger.setLevel(level)

    # Format: Timestamp [LEVEL] [ThreadName] logger.name: Message
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File Handler
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"[WARN] No se pudo inicializar FileHandler en {log_file}: {e}", file=sys.stderr)

    # Console Stream Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    root_logger.addHandler(stream_handler)

    # Install global exception hooks
    _install_exception_hooks()
    _LOGGING_INITIALIZED = True

    logger = logging.getLogger("src")
    logger.info("=" * 60)
    logger.info(
        f"Iniciando sesión - Frozen={getattr(sys, 'frozen', False)}, "
        f"Platform={sys.platform}, Python={sys.version.split()[0]}"
    )
    logger.info(f"Ruta de registros: {log_file.resolve()}")
    logger.info(f"Directorio de datos: {AppConfig.DATA_DIR.resolve()}")
    logger.info("=" * 60)

    return logger


def _install_exception_hooks() -> None:
    """Catch unhandled exceptions from main and background threads and record them in logs."""
    logger = logging.getLogger("unhandled_exception")

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.critical(f"Excepción no capturada en hilo principal:\n{error_msg}")

        # If tkinter is loaded and running in GUI mode, attempt to show messagebox
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "Error Fatal en la Aplicación",
                f"Ocurrió un error inesperado:\n\n{exc_value}\n\nRevisa el archivo de registro en:\n{AppConfig.LOGS_DIR / 'whatsapp_backup.log'}"
            )
        except Exception:
            pass

        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def handle_thread_exception(args: threading.ExceptHookArgs):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return

        error_msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_trace))
        logger.critical(
            f"Excepción no capturada en hilo secundario [{args.thread.name}]:\n{error_msg}"
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
