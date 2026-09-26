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
from src.ocr_manager import OCRManager
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


def cmd_accounts(args: argparse.Namespace) -> int:
    """List all detected WhatsApp accounts across Android user profiles."""
    dev_mgr = DeviceManager()
    sec_mgr = SecretManager()
    try:
        dev = dev_mgr.get_active_device(args.serial)
        accounts = dev_mgr.list_whatsapp_accounts(dev.serial)
        if not accounts:
            print("No se detectaron cuentas de WhatsApp en el dispositivo.")
            return 1

        print(f"\nCuentas de WhatsApp detectadas en {dev.model or dev.serial} ({len(accounts)}):")
        print(
            f"{'ID Cuenta':<18} | {'Perfil / Nombre':<38} | {'Usuario':<7} | {'Formato':<8} | {'Último Backup':<30} | {'Clave'}"
        )
        print("-" * 120)
        for a in accounts:
            has_k = "CONFIGURADA" if sec_mgr.has_key(a.account_id) else "NO CONFIGURADA"
            backup_info = (
                f"{a.latest_backup_file} ({a.latest_backup_size_mb:.1f} MB)"
                if a.latest_backup_file
                else "(ninguno)"
            )
            print(
                f"{a.account_id:<18} | {a.display_name:<38} | {a.android_user_id:<7} | {a.crypt_format:<8} | {backup_info:<30} | {has_k}"
            )
        print(
            "\nPara procesar una cuenta específica: python -m src.cli export -a <ID Cuenta>"
        )
        print(
            "Para capturar la clave de una cuenta: python -m src.cli capture-key -a <ID Cuenta>\n"
        )
        return 0
    except WhatsAppBackupError as e:
        print(f"\n[ERROR: {e.code}] {e.message}", file=sys.stderr)
        return 1


def cmd_export(args: argparse.Namespace) -> int:
    """Execute the full export pipeline."""
    pipeline = ExportPipeline()
    out_dir = Path(args.output_dir) if args.output_dir else None
    account = args.account or "principal"

    print(f"\n--- WhatsApp Backup to CSV: Exportando cuenta '{account}' ---")

    def progress_callback(stage: str, message: str, percent: float):
        print(f"[{percent:3.0f}%] {message}")

    try:
        res = pipeline.run_export(
            key=args.key,
            serial=args.serial,
            account_id=account,
            force=args.force,
            include_media=args.include_media,
            output_dir=out_dir,
            progress_cb=progress_callback,
        )

        print("\n========================================================")
        print("  EXPORTACIÓN COMPLETADA CON ÉXITO")
        print("========================================================")
        print(f"  Cuenta:               {res['account_display_name']} [{res['account_id']}]")
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
    """Show current system, device, accounts, keys, and vault status."""
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

            if d.is_authorized:
                accounts = dev_mgr.list_whatsapp_accounts(d.serial)
                print(f"    Cuentas detectadas ({len(accounts)}):")
                for a in accounts:
                    k_str = (
                        "CLAVE GUARDADA"
                        if sec_mgr.has_key(a.account_id)
                        else "SIN CLAVE"
                    )
                    print(
                        f"      - {a.account_id}: {a.display_name} ({a.latest_backup_file or 'sin backup'}, {a.crypt_format}) [{k_str}]"
                    )
    except Exception as e:
        print(f"  * Error consultando ADB: {e}")

    # 2. Keyring Accounts
    stored_accs = sec_mgr.list_stored_accounts()
    print(f"\nCuentas con clave en almacén seguro: {', '.join(stored_accs) if stored_accs else 'Ninguna'}")

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
                accounts = dev_mgr.list_whatsapp_accounts(d.serial)
                print(f"  Cuentas detectadas ({len(accounts)}):")
                for a in accounts:
                    print(
                        f"    - [{a.account_id}] {a.display_name}: {a.latest_backup_file} ({a.latest_backup_size_mb} MB, {a.latest_backup_date})"
                    )
            except Exception as e:
                print(f"    (No se pudieron listar cuentas: {e})")
        else:
            print("  Estado: NO AUTORIZADO. Desbloquea la pantalla y acepta la depuración USB.")
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    """Manage encryption keys stored in the OS secure vault."""
    sec_mgr = SecretManager()
    target_account = getattr(args, "account", "principal") or "principal"
    serial = getattr(args, "serial", None)

    if args.action == "set":
        if not args.value:
            print(
                "Error: Debes proporcionar la clave de 64 caracteres hexadecimales.",
                file=sys.stderr,
            )
            return 1
        try:
            sec_mgr.store_key(args.value, account_id=target_account, serial=serial)
            print(
                f"Clave guardada con éxito en el almacén seguro para la cuenta '{target_account}'"
                + (f" (dispositivo: {serial})" if serial else "")
                + "."
            )
            return 0
        except WhatsAppBackupError as e:
            print(f"Error: {e.message}", file=sys.stderr)
            return 1

    elif args.action == "get":
        stored = sec_mgr.get_key(account_id=target_account, serial=serial)
        if stored:
            print(
                f"Clave almacenada ({target_account}"
                + (f", serial {serial}" if serial else "")
                + f"): {sec_mgr.mask_key(stored)}"
            )
        else:
            print(f"No hay ninguna clave guardada para la cuenta '{target_account}'.")
        return 0

    elif args.action == "clear":
        deleted = sec_mgr.delete_key(account_id=target_account, serial=serial)
        if deleted:
            print(
                f"Clave eliminada del almacén seguro para la cuenta '{target_account}'."
            )
        else:
            print(f"No se pudo eliminar o no existía la clave para '{target_account}'.")
        return 0

    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Display past export runs."""
    vault = VaultDatabase()
    account_filter = getattr(args, "account", None)
    serial_filter = getattr(args, "serial", None)
    runs = vault.get_export_runs(
        limit=args.limit, account_id=account_filter, device_serial=serial_filter
    )

    if not runs:
        print("No hay historial de ejecuciones registrado.")
        return 0

    print(f"\nHistorial de exportaciones (últimas {len(runs)}):")
    print(
        f"{'Fecha':<20} | {'Dispositivo':<15} | {'Cuenta':<15} | {'Estado':<10} | {'Chats':<6} | {'Mensajes':<8} | {'Nuevos':<6} | {'ID Ejecución'}"
    )
    print("-" * 115)
    for r in runs:
        dt_str = r.started_at[:19].replace("T", " ") if r.started_at else "?"
        dev_str = r.device_serial or "default"
        print(
            f"{dt_str:<20} | {dev_str:<15} | {r.account_id:<15} | {r.status:<10} | {r.total_conversations:<6} | {r.total_messages:<8} | {r.inserted_messages:<6} | {r.run_id}"
        )
    return 0


def cmd_parse_local(args: argparse.Namespace) -> int:
    """Decrypt and export an already downloaded local backup file."""
    input_file = Path(args.input_file)
    if not input_file.is_file():
        print(f"Error: No existe el archivo '{input_file}'", file=sys.stderr)
        return 1

    sec_mgr = SecretManager()
    account = args.account or "principal"
    key = args.key or sec_mgr.get_key(account) or sec_mgr.get_key("default")
    if not key:
        print(f"Error: Se requiere una clave (--key o guardada para la cuenta '{account}').", file=sys.stderr)
        return 1

    decrypted_path = AppConfig.WORKING_DIR / f"local_decrypted_{input_file.stem}.db"
    out_dir = Path(args.output_dir) if args.output_dir else ExportManager.get_account_export_dir(account)

    print(f"Descifrando {input_file}...")
    DecryptManager.decrypt(input_file, key, decrypted_path)
    print("Descifrado correcto. Extrayendo conversaciones...")
    convs, msgs = MessageParser.parse_database(decrypted_path, backup_id=input_file.name)

    manifest = ExportManifest(
        run_id="local_parse",
        account_id=account,
        exported_at=datetime.datetime.now(datetime.UTC).isoformat(),
        backup_file=input_file.name,
        backup_sha256="local",
        total_conversations=len(convs),
        total_messages=len(msgs),
        files_generated=[],
        tool_versions={"wa-crypt-tools": "0.1.0", "whapa": "2.00"},
    )
    ExportManager.export_all(convs, msgs, manifest, output_dir=out_dir, account_id=account)
    print(f"\nExportación local finalizada: {len(convs)} chats, {len(msgs)} mensajes en {out_dir}")
    return 0


def cmd_capture_key(args: argparse.Namespace) -> int:
    """Capture phone screen via ADB and extract 64-hex key via OCR for an account."""
    ocr_mgr = OCRManager()
    sec_mgr = SecretManager()
    account = args.account or "principal"

    print(f"\n--- Captura OCR de Clave de WhatsApp (64 dígitos) - Cuenta: '{account}' ---")
    print("[1/3] Capturando pantalla del dispositivo Android conectado por ADB...")

    try:
        img = ocr_mgr.capture_screenshot(serial=args.serial)
        print(f"      Pantalla capturada con éxito ({img.width}x{img.height} px).")

        roi = None
        if args.roi:
            parts = [float(x.strip()) for x in args.roi.split(",")]
            if len(parts) == 4:
                roi = {
                    "x_min": parts[0],
                    "y_min": parts[1],
                    "x_max": parts[2],
                    "y_max": parts[3],
                }
                if args.save_roi:
                    ocr_mgr.save_roi(roi)
        else:
            saved = ocr_mgr.get_saved_roi()
            if saved:
                roi = saved
                print(
                    f"      Usando área ROI guardada: ({saved['x_min']}, {saved['y_min']}) a ({saved['x_max']}, {saved['y_max']})"
                )

        print("[2/3] Procesando imagen y ejecutando OCR...")
        key_hex, _raw_text = ocr_mgr.extract_key_from_image(img, roi)

        formatted = " ".join([key_hex[i : i + 4] for i in range(0, 64, 4)])
        print("[3/3] ¡Clave detectada y verificada con éxito!")
        print("\n========================================================")
        print(f"  CLAVE DETECTADA ({account.upper()} - 64 HEX):")
        print(f"  {formatted}")
        print("========================================================")

        if not args.no_save:
            sec_mgr.store_key(key_hex, account, serial=args.serial)
            print(
                f"\n[OK] Clave guardada de forma segura en el almacén OS para la cuenta '{account}'."
            )

        return 0

    except WhatsAppBackupError as e:
        print(f"\n[ERROR: {e.code}] {e.message}", file=sys.stderr)
        print(f"Acción recomendada: {e.action_recommended}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[ERROR INESPERADO] {e}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whatsapp-csv",
        description="WhatsApp Backup to CSV: Extracción automatizada y descifrado de WhatsApp vía ADB con soporte multi-cuenta y multi-dispositivo.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Habilitar registros de depuración"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # accounts
    p_accs = subparsers.add_parser(
        "accounts", help="Lista todas las cuentas de WhatsApp detectadas en el teléfono (Samsung, Xiaomi, Honor, Realme, Oppo, etc.)"
    )
    p_accs.add_argument("-s", "--serial", help="Número de serie del dispositivo Android específico")

    # export
    p_export = subparsers.add_parser(
        "export", help="Ejecuta la exportación completa desde el teléfono Android"
    )
    p_export.add_argument(
        "-a",
        "--account",
        default="principal",
        help="Identificador de cuenta (ej. 'principal', 'dual_xiaomi', 'samsung_dual'). Por defecto: 'principal'",
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
        "status", help="Muestra el estado de ADB, teléfono conectado, cuentas, claves y almacén local"
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
        "-a",
        "--account",
        default="principal",
        help="Identificador de cuenta para la clave (por defecto 'principal')",
    )
    p_key.add_argument(
        "-s",
        "--serial",
        help="Número de serie del dispositivo para vincular la clave a un teléfono concreto",
    )

    # history
    p_hist = subparsers.add_parser("history", help="Consulta el historial de exportaciones previas")
    p_hist.add_argument(
        "-l", "--limit", type=int, default=20, help="Número máximo de registros a mostrar"
    )
    p_hist.add_argument(
        "-a", "--account", help="Filtrar historial por identificador de cuenta"
    )
    p_hist.add_argument(
        "-s", "--serial", help="Filtrar historial por número de serie del dispositivo"
    )

    # capture-key (OCR)
    p_ocr = subparsers.add_parser(
        "capture-key",
        help="Captura la pantalla del teléfono por ADB y extrae la clave de 64 hex con OCR",
    )
    p_ocr.add_argument(
        "-a",
        "--account",
        default="principal",
        help="Identificador de cuenta para la que se capturará la clave (ej. 'principal', 'dual_xiaomi')",
    )
    p_ocr.add_argument("-s", "--serial", help="Número de serie del dispositivo Android específico")
    p_ocr.add_argument(
        "--roi",
        help="Coordenadas normalizadas del área x_min,y_min,x_max,y_max (ej. 0.08,0.35,0.92,0.65)",
    )
    p_ocr.add_argument(
        "--save-roi",
        action="store_true",
        help="Guardar el área ROI especificada como predeterminada",
    )
    p_ocr.add_argument(
        "--no-save",
        action="store_true",
        help="No guardar automáticamente la clave en el almacén seguro (solo imprimir)",
    )

    # history
    p_hist = subparsers.add_parser(
        "history", help="Muestra el historial de exportaciones realizadas"
    )
    p_hist.add_argument(
        "-a", "--account", help="Filtrar historial por cuenta específica"
    )
    p_hist.add_argument(
        "-n", "--limit", type=int, default=20, help="Número máximo de ejecuciones a mostrar"
    )

    # parse-local
    p_local = subparsers.add_parser(
        "parse-local", help="Descifra y exporta un archivo de backup local existente"
    )
    p_local.add_argument("input_file", help="Ruta al archivo .crypt15, .crypt14 o .db")
    p_local.add_argument(
        "-a", "--account", default="principal", help="Identificador de cuenta para organizar la exportación"
    )
    p_local.add_argument("-k", "--key", help="Clave de cifrado de 64 caracteres hexadecimales")
    p_local.add_argument("-o", "--output-dir", help="Directorio de salida para los CSVs")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    if not args.command:
        cmd_status(args)
        print("\nPara listar cuentas detectadas: python -m src.cli accounts")
        print("Para ejecutar exportación: python -m src.cli export -a principal | dual_xiaomi")
        print("Para capturar clave con OCR: python -m src.cli capture-key -a dual_xiaomi")
        print("Para ver todas las opciones: python -m src.cli --help\n")
        sys.exit(0)

    dispatch = {
        "accounts": cmd_accounts,
        "export": cmd_export,
        "status": cmd_status,
        "devices": cmd_devices,
        "key": cmd_key,
        "capture-key": cmd_capture_key,
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

