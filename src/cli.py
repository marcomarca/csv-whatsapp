import argparse
import datetime
import logging
import sys
from pathlib import Path

from src.config import AppConfig
from src.database import VaultDatabase
from src.decrypt_manager import DecryptManager
from src.device_manager import DeviceManager
from src.errors import WhatsAppBackupError
from src.export_manager import ExportManager
from src.message_parser import MessageParser
from src.models import ExportManifest
from src.pipeline import ExportPipeline
from src.secret_manager import SecretManager


def setup_logging(verbose: bool = False) -> None:
    AppConfig.ensure_directories()
    log_file = AppConfig.LOGS_DIR / "whatsapp_backup.log"
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def cmd_export(args: argparse.Namespace) -> int:
    """Execute the full export pipeline."""
    pipeline = ExportPipeline()
    out_dir = Path(args.output_dir) if args.output_dir else None

    print("\n--- WhatsApp Backup to CSV: Iniciando Exportación ---")

    def progress_callback(stage: str, message: str, percent: float):
        print(f"[{percent:3.0f}%] {message}")

    try:
        res = pipeline.run_export(
            key=args.key,
            serial=args.serial,
            force=args.force,
            include_media=args.include_media,
            output_dir=out_dir,
            progress_cb=progress_callback,
        )

        print("\n========================================================")
        print("  EXPORTACIÓN COMPLETADA CON ÉXITO")
        print("========================================================")
        print(f"  Dispositivo:          {res['device_model']}")
        print(f"  Backup procesado:     {res['backup_filename']}")
        print(f"  Conversaciones:       {res['total_conversations']}")
        print(f"  Mensajes totales:     {res['total_messages']}")
        print(f"  Mensajes nuevos:      {res['inserted_messages']}")
        print(f"  Mensajes actualizados:{res['updated_messages']}")
        print(f"  Carpeta de salida:    {res['exports_dir']}")
        print("========================================================\n")
        return 0

    except WhatsAppBackupError as e:
        print(f"\n[ERROR: {e.code}] {e.message}", file=sys.stderr)
        print(f"Acción recomendada: {e.action_recommended}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[ERROR INESPERADO] {e}", file=sys.stderr)
        return 2


def cmd_status(args: argparse.Namespace) -> int:
    """Show current system, device, key, and vault status."""
    print("\n--- Estado del Sistema y Dispositivo ---")
    dev_mgr = DeviceManager()
    sec_mgr = SecretManager()
    vault = VaultDatabase()

    # 1. ADB & Devices
    try:
        devices = dev_mgr.get_devices()
        print(f"ADB Executable: {dev_mgr.adb_path}")
        print(f"Dispositivos detectados: {len(devices)}")
        for d in devices:
            auth_str = "AUTORIZADO" if d.is_authorized else f"NO AUTORIZADO ({d.state})"
            model_str = f" - Modelo: {d.model} (Android {d.android_version})" if d.model else ""
            pkgs_str = (
                f" - WhatsApp: {', '.join(d.whatsapp_packages)}" if d.whatsapp_packages else ""
            )
            print(f"  * Serial: {d.serial} [{auth_str}]{model_str}{pkgs_str}")
    except Exception as e:
        print(f"  * Error consultando ADB: {e}")

    # 2. Keyring Key
    has_key = sec_mgr.has_key("default")
    key_preview = (
        sec_mgr.mask_key(sec_mgr.get_key("default") or "") if has_key else "NO CONFIGURADA"
    )
    print(
        f"\nClave en almacén seguro OS: {'CONFIGURADA (' + key_preview + ')' if has_key else 'NO CONFIGURADA'}"
    )

    # 3. Vault & Latest backup
    latest = vault.get_latest_backup()
    if latest:
        print("\nÚltimo backup procesado:")
        print(f"  Archivo:    {latest.filename}")
        print(f"  Fecha:      {latest.source_modified_at}")
        print(f"  Importado:  {latest.imported_at}")
        print(f"  Mensajes:   {latest.message_count}")
    else:
        print("\nNo hay backups previos registrados en el almacén interno.")

    convs = vault.get_all_conversations()
    msgs = vault.get_all_messages()
    print(f"\nAlmacén consolidado: {len(convs)} conversaciones, {len(msgs)} mensajes.")
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    """List connected devices and discover their remote WhatsApp backups."""
    dev_mgr = DeviceManager()
    devices = dev_mgr.get_devices()

    if not devices:
        print("No se encontraron dispositivos conectados por USB con depuración ADB activa.")
        return 1

    print(f"Dispositivos conectados ({len(devices)}):")
    for d in devices:
        print(f"\nDispositivo: {d.serial} ({d.state})")
        if d.is_authorized:
            print(f"  Modelo:           {d.model}")
            print(f"  Versión Android:  {d.android_version}")
            print(f"  Paquetes WA:      {', '.join(d.whatsapp_packages)}")
            try:
                backups = dev_mgr.list_backups(d.serial)
                print(f"  Backups encontrados ({len(backups)}):")
                for b in backups:
                    main_flag = " [PRINCIPAL]" if b.is_main else ""
                    print(
                        f"    - {b.filename} ({b.file_size / (1024 * 1024):.2f} MB, {b.modified_at}, {b.format}){main_flag}"
                    )
            except Exception as e:
                print(f"    (No se pudieron listar backups: {e})")
        else:
            print("  Estado: NO AUTORIZADO. Desbloquea la pantalla y acepta la depuración USB.")
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    """Manage encryption keys stored in the OS secure vault."""
    sec_mgr = SecretManager()

    if args.action == "set":
        if not args.value:
            print(
                "Error: Debes proporcionar la clave de 64 caracteres hexadecimales.",
                file=sys.stderr,
            )
            return 1
        try:
            sec_mgr.store_key(args.value, account_id=args.account or "default")
            print(
                f"Clave guardada con éxito en el almacén seguro para la cuenta '{args.account or 'default'}'."
            )
            return 0
        except WhatsAppBackupError as e:
            print(f"Error: {e.message}", file=sys.stderr)
            return 1

    elif args.action == "get":
        stored = sec_mgr.get_key(account_id=args.account or "default")
        if stored:
            print(f"Clave almacenada ({args.account or 'default'}): {sec_mgr.mask_key(stored)}")
        else:
            print(f"No hay ninguna clave guardada para la cuenta '{args.account or 'default'}'.")
        return 0

    elif args.action == "clear":
        deleted = sec_mgr.delete_key(account_id=args.account or "default")
        if deleted:
            print(
                f"Clave eliminada del almacén seguro para la cuenta '{args.account or 'default'}'."
            )
        else:
            print(f"No se pudo eliminar o no existía la clave para '{args.account or 'default'}'.")
        return 0

    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Display past export runs."""
    vault = VaultDatabase()
    runs = vault.get_export_runs(limit=args.limit)

    if not runs:
        print("No hay historial de ejecuciones registrado.")
        return 0

    print(f"\nHistorial de exportaciones (últimas {len(runs)}):")
    print(
        f"{'Fecha':<20} | {'Estado':<10} | {'Chats':<6} | {'Mensajes':<8} | {'Nuevos':<6} | {'ID Ejecución'}"
    )
    print("-" * 80)
    for r in runs:
        dt_str = r.started_at[:19].replace("T", " ") if r.started_at else "?"
        print(
            f"{dt_str:<20} | {r.status:<10} | {r.total_conversations:<6} | {r.total_messages:<8} | {r.inserted_messages:<6} | {r.run_id}"
        )
    return 0


def cmd_parse_local(args: argparse.Namespace) -> int:
    """Decrypt and export an already downloaded local backup file."""
    input_file = Path(args.input_file)
    if not input_file.is_file():
        print(f"Error: No existe el archivo '{input_file}'", file=sys.stderr)
        return 1

    sec_mgr = SecretManager()
    key = args.key or sec_mgr.get_key("default")
    if not key:
        print("Error: Se requiere una clave (--key o guardada previamente).", file=sys.stderr)
        return 1

    decrypted_path = AppConfig.WORKING_DIR / f"local_decrypted_{input_file.stem}.db"
    out_dir = Path(args.output_dir) if args.output_dir else AppConfig.EXPORTS_DIR

    print(f"Descifrando {input_file}...")
    DecryptManager.decrypt(input_file, key, decrypted_path)
    print("Descifrado correcto. Extrayendo conversaciones...")
    convs, msgs = MessageParser.parse_database(decrypted_path, backup_id=input_file.name)

    manifest = ExportManifest(
        run_id="local_parse",
        exported_at=datetime.datetime.now(datetime.UTC).isoformat(),
        backup_file=input_file.name,
        backup_sha256="local",
        total_conversations=len(convs),
        total_messages=len(msgs),
        files_generated=[],
        tool_versions={"wa-crypt-tools": "0.1.0", "whapa": "2.00"},
    )
    ExportManager.export_all(convs, msgs, manifest, output_dir=out_dir)
    print(f"\nExportación local finalizada: {len(convs)} chats, {len(msgs)} mensajes en {out_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whatsapp-csv",
        description="WhatsApp Backup to CSV: Extracción automatizada y descifrado de WhatsApp vía ADB.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Habilitar registros de depuración"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # export
    p_export = subparsers.add_parser(
        "export", help="Ejecuta la exportación completa desde el teléfono Android"
    )
    p_export.add_argument("-k", "--key", help="Clave hexadecimal de 64 caracteres de WhatsApp")
    p_export.add_argument(
        "-s", "--serial", help="Número de serie del dispositivo Android específico"
    )
    p_export.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Forzar exportación incluso si el backup no ha cambiado",
    )
    p_export.add_argument(
        "-m",
        "--include-media",
        action="store_true",
        help="Descargar también los archivos multimedia",
    )
    p_export.add_argument(
        "-o", "--output-dir", help="Directorio de destino para los archivos CSV exportados"
    )

    # status
    subparsers.add_parser(
        "status", help="Muestra el estado de ADB, teléfono conectado, clave y almacén local"
    )

    # devices
    subparsers.add_parser(
        "devices", help="Lista dispositivos conectados y busca copias de seguridad de WhatsApp"
    )

    # key
    p_key = subparsers.add_parser(
        "key", help="Gestiona la clave de cifrado en el almacén seguro del sistema"
    )
    p_key.add_argument(
        "action", choices=["set", "get", "clear"], help="Acción a realizar sobre la clave"
    )
    p_key.add_argument(
        "value", nargs="?", help="Valor de la clave de 64 caracteres hex (solo para 'set')"
    )
    p_key.add_argument(
        "--account",
        help="Identificador de cuenta/dispositivo para la clave (por defecto 'default')",
    )

    # history
    p_hist = subparsers.add_parser(
        "history", help="Muestra el historial de exportaciones realizadas"
    )
    p_hist.add_argument(
        "-n", "--limit", type=int, default=20, help="Número máximo de ejecuciones a mostrar"
    )

    # parse-local
    p_local = subparsers.add_parser(
        "parse-local", help="Descifra y exporta un archivo de backup local existente"
    )
    p_local.add_argument("input_file", help="Ruta al archivo .crypt15, .crypt14 o .db")
    p_local.add_argument("-k", "--key", help="Clave de cifrado de 64 caracteres hexadecimales")
    p_local.add_argument("-o", "--output-dir", help="Directorio de salida para los CSVs")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    if not args.command:
        # Default action: status or help
        cmd_status(args)
        print("\nPara ejecutar la exportación completa: python -m src.cli export")
        print("Para ver todas las opciones: python -m src.cli --help\n")
        sys.exit(0)

    dispatch = {
        "export": cmd_export,
        "status": cmd_status,
        "devices": cmd_devices,
        "key": cmd_key,
        "history": cmd_history,
        "parse-local": cmd_parse_local,
    }

    handler = dispatch.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
