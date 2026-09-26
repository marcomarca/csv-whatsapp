"""Tkinter Desktop User Interface for WhatsApp Backup to CSV."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from src.config import AppConfig
from src.database import VaultDatabase
from src.device_manager import DeviceManager
from src.errors import WhatsAppBackupError
from src.pipeline import ExportPipeline
from src.secret_manager import SecretManager


class AppUI(tk.Tk):
    """Main Desktop GUI Window for WhatsApp Backup to CSV."""

    def __init__(self):
        super().__init__()
        self.title("WhatsApp Backup to CSV")
        self.geometry("780x640")
        self.minsize(700, 560)

        # Apply clean styling
        self._configure_styles()

        self.device_manager = DeviceManager()
        self.secret_manager = SecretManager()
        self.vault_db = VaultDatabase()
        self.pipeline = ExportPipeline(
            device_manager=self.device_manager,
            secret_manager=self.secret_manager,
            vault_db=self.vault_db,
        )

        self._build_ui()
        self.refresh_status()

    def _configure_styles(self):
        self.style = ttk.Style(self)
        # Try modern theme if available
        available_themes = self.style.theme_names()
        if "clam" in available_themes:
            self.style.theme_use("clam")

        self.style.configure("Title.TLabel", font=("Helvetica", 16, "bold"), foreground="#128C7E")
        self.style.configure("Subtitle.TLabel", font=("Helvetica", 10), foreground="#555555")
        self.style.configure(
            "Section.TLabelframe.Label", font=("Helvetica", 10, "bold"), foreground="#075E54"
        )
        self.style.configure("BadgeOK.TLabel", font=("Helvetica", 9, "bold"), foreground="#25D366")
        self.style.configure(
            "BadgeWarn.TLabel", font=("Helvetica", 9, "bold"), foreground="#E65100"
        )
        self.style.configure("BadgeErr.TLabel", font=("Helvetica", 9, "bold"), foreground="#D32F2F")
        self.style.configure("Primary.TButton", font=("Helvetica", 12, "bold"), padding=10)

    def _build_ui(self):
        # Top Header
        header_frame = ttk.Frame(self, padding="15 10 15 5")
        header_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(header_frame, text="WhatsApp Backup to CSV", style="Title.TLabel")
        title_lbl.pack(anchor=tk.W)

        sub_lbl = ttk.Label(
            header_frame,
            text="Exportación automática, descifrado verificado y consolidación de chats en CSV normalizados.",
            style="Subtitle.TLabel",
        )
        sub_lbl.pack(anchor=tk.W, pady=(2, 0))

        # Status Box
        status_frame = ttk.LabelFrame(
            self, text=" Estado del Teléfono y Sistema ", padding=12, style="Section.TLabelframe"
        )
        status_frame.pack(fill=tk.X, padx=15, pady=8)

        # Status Grid
        ttk.Label(status_frame, text="Dispositivo Android:", font=("Helvetica", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W, pady=3
        )
        self.lbl_device = ttk.Label(status_frame, text="Comprobando...", style="BadgeWarn.TLabel")
        self.lbl_device.grid(row=0, column=1, sticky=tk.W, padx=10, pady=3)

        ttk.Label(status_frame, text="Autorización ADB:", font=("Helvetica", 9, "bold")).grid(
            row=0, column=2, sticky=tk.W, pady=3, padx=(20, 0)
        )
        self.lbl_adb = ttk.Label(status_frame, text="Comprobando...", style="BadgeWarn.TLabel")
        self.lbl_adb.grid(row=0, column=3, sticky=tk.W, padx=10, pady=3)

        ttk.Label(
            status_frame, text="Clave de Cifrado (OS Keyring):", font=("Helvetica", 9, "bold")
        ).grid(row=1, column=0, sticky=tk.W, pady=3)
        self.lbl_key = ttk.Label(status_frame, text="Comprobando...", style="BadgeWarn.TLabel")
        self.lbl_key.grid(row=1, column=1, sticky=tk.W, padx=10, pady=3)

        ttk.Label(
            status_frame, text="Último Backup Detectado:", font=("Helvetica", 9, "bold")
        ).grid(row=1, column=2, sticky=tk.W, pady=3, padx=(20, 0))
        self.lbl_backup = ttk.Label(status_frame, text="Buscando...")
        self.lbl_backup.grid(row=1, column=3, sticky=tk.W, padx=10, pady=3)

        ttk.Label(status_frame, text="Almacén Local (Total):", font=("Helvetica", 9, "bold")).grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        self.lbl_vault = ttk.Label(status_frame, text="0 conversaciones | 0 mensajes")
        self.lbl_vault.grid(row=2, column=1, columnspan=3, sticky=tk.W, padx=10, pady=3)

        btn_refresh = ttk.Button(
            status_frame, text="↻ Actualizar Estado", command=self.refresh_status
        )
        btn_refresh.grid(row=3, column=0, columnspan=4, sticky=tk.E, pady=(6, 0))

        # Action Buttons Center
        action_frame = ttk.Frame(self, padding="15 8")
        action_frame.pack(fill=tk.X)

        self.btn_export = ttk.Button(
            action_frame,
            text="📥  EXPORTAR WHATSAPP A CSV",
            style="Primary.TButton",
            command=self.start_export_thread,
        )
        self.btn_export.pack(fill=tk.X, ipady=5)

        # Progress Section
        progress_frame = ttk.LabelFrame(
            self, text=" Progreso de la Operación ", padding=10, style="Section.TLabelframe"
        )
        progress_frame.pack(fill=tk.X, padx=15, pady=6)

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=4)

        self.lbl_step = ttk.Label(
            progress_frame, text="Listo para exportar.", font=("Helvetica", 9)
        )
        self.lbl_step.pack(anchor=tk.W, pady=2)

        # Secondary Actions
        sec_frame = ttk.Frame(self, padding="15 5")
        sec_frame.pack(fill=tk.X)

        ttk.Button(sec_frame, text="🔑 Configurar Clave", command=self.prompt_set_key).pack(
            side=tk.LEFT, padx=3
        )
        ttk.Button(
            sec_frame, text="📱 Guía de Conexión USB", command=self.show_connection_guide
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(sec_frame, text="📂 Abrir Carpeta CSV", command=self.open_exports_folder).pack(
            side=tk.LEFT, padx=3
        )
        ttk.Button(sec_frame, text="📋 Historial", command=self.show_history).pack(
            side=tk.LEFT, padx=3
        )
        ttk.Button(sec_frame, text="📄 Ver Logs", command=self.open_logs).pack(
            side=tk.RIGHT, padx=3
        )

        # Output Log Box
        log_frame = ttk.LabelFrame(
            self, text=" Registro de Ejecución ", padding=8, style="Section.TLabelframe"
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 12))

        self.txt_log = tk.Text(
            log_frame, wrap=tk.WORD, height=8, font=("Consolas", 8), bg="#F8F9FA"
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scroll = ttk.Scrollbar(log_frame, command=self.txt_log.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.config(yscrollcommand=scroll.set)

    def log_message(self, msg: str):
        self.txt_log.insert(tk.END, f"{msg}\n")
        self.txt_log.see(tk.END)

    def refresh_status(self):
        """Query ADB, Keyring, and Vault to refresh status badges."""
        try:
            devices = self.device_manager.get_devices()
            if not devices:
                self.lbl_device.config(text="No detectado", style="BadgeErr.TLabel")
                self.lbl_adb.config(text="Desconectado", style="BadgeErr.TLabel")
                self.lbl_backup.config(text="Desconocido")
            else:
                dev = devices[0]
                if dev.is_authorized:
                    self.lbl_device.config(
                        text=f"{dev.model or dev.serial} (Android {dev.android_version or '?'})",
                        style="BadgeOK.TLabel",
                    )
                    self.lbl_adb.config(text="Autorizado", style="BadgeOK.TLabel")
                    # Try finding backup
                    try:
                        backups = self.device_manager.list_backups(dev.serial)
                        main_b = backups[0]
                        self.lbl_backup.config(text=f"{main_b.filename} ({main_b.modified_at})")
                    except Exception:
                        self.lbl_backup.config(text="Sin copias encontradas")
                else:
                    self.lbl_device.config(text=f"{dev.serial}", style="BadgeWarn.TLabel")
                    self.lbl_adb.config(
                        text=f"No Autorizado ({dev.state})", style="BadgeWarn.TLabel"
                    )
                    self.lbl_backup.config(text="Esperando autorización")

        except Exception as e:
            self.lbl_device.config(text="Error ADB", style="BadgeErr.TLabel")
            self.lbl_adb.config(text=str(e)[:30], style="BadgeErr.TLabel")

        # Key status
        has_key = self.secret_manager.has_key("default")
        if has_key:
            key_val = self.secret_manager.get_key("default") or ""
            self.lbl_key.config(
                text=f"Configurada ({self.secret_manager.mask_key(key_val)})",
                style="BadgeOK.TLabel",
            )
        else:
            self.lbl_key.config(
                text="No configurada (Introduce la clave de 64 hex)", style="BadgeWarn.TLabel"
            )

        # Vault status
        convs = self.vault_db.get_all_conversations()
        msgs = self.vault_db.get_all_messages()
        self.lbl_vault.config(
            text=f"{len(convs)} conversaciones | {len(msgs)} mensajes almacenados"
        )

    def prompt_set_key(self):
        """Prompt user for 64-character hex key and store it securely."""
        key = simpledialog.askstring(
            "Configurar Clave de Cifrado",
            "Introduce la clave de cifrado de extremo a extremo de WhatsApp\n(64 caracteres hexadecimales generados por WhatsApp):",
            parent=self,
        )
        if key:
            try:
                self.secret_manager.store_key(key, "default")
                messagebox.showinfo(
                    "Clave Guardada",
                    "La clave se ha validado y guardado de forma segura en el almacén del sistema operativo.",
                    parent=self,
                )
                self.refresh_status()
            except WhatsAppBackupError as e:
                messagebox.showerror(
                    "Clave Inválida", f"{e.message}\n\n{e.action_recommended}", parent=self
                )

    def show_connection_guide(self):
        """Show interactive onboarding instructions for connecting Android phone."""
        guide_msg = (
            "PASOS PARA CONFIGURAR TU TELÉFONO ANDROID:\n\n"
            "1. Conecta el teléfono por USB con un cable de transferencia de datos.\n"
            "2. Desbloquea la pantalla de tu teléfono.\n"
            "3. En Android: Abre Ajustes > Información del teléfono y pulsa 7 veces 'Número de compilación'.\n"
            "4. Regresa a Ajustes > Opciones de desarrollador > Activa 'Depuración por USB'.\n"
            "5. En la pantalla del teléfono aparecerá: '¿Permitir depuración por USB desde este equipo?'. Acepta la solicitud.\n"
            "6. En WhatsApp: Ajustes > Chats > Copia de seguridad > Copia de seguridad cifrada de extremo a extremo > Guardar clave de 64 dígitos y pulsa 'Guardar' para crear el backup."
        )
        messagebox.showinfo("Guía de Conexión USB y WhatsApp", guide_msg, parent=self)

    def open_exports_folder(self):
        """Open the data/exports folder in Windows Explorer or OS file manager."""
        AppConfig.ensure_directories()
        path = str(AppConfig.EXPORTS_DIR.resolve())
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    def open_logs(self):
        """Open the application log file."""
        log_path = AppConfig.LOGS_DIR / "whatsapp_backup.log"
        if log_path.exists():
            if sys.platform == "win32":
                os.startfile(str(log_path))
            else:
                subprocess.run(["xdg-open", str(log_path)], check=False)
        else:
            messagebox.showinfo(
                "Registros", "Aún no se han generado registros de log.", parent=self
            )

    def show_history(self):
        """Show dialog with export history."""
        runs = self.vault_db.get_export_runs(limit=30)
        hist_win = tk.Toplevel(self)
        hist_win.title("Historial de Exportaciones")
        hist_win.geometry("640x350")

        cols = ("fecha", "estado", "chats", "mensajes", "nuevos", "id")
        tree = ttk.Treeview(hist_win, columns=cols, show="headings")
        tree.heading("fecha", text="Fecha")
        tree.heading("estado", text="Estado")
        tree.heading("chats", text="Chats")
        tree.heading("mensajes", text="Mensajes")
        tree.heading("nuevos", text="Nuevos")
        tree.heading("id", text="ID Ejecución")

        tree.column("fecha", width=140)
        tree.column("estado", width=80)
        tree.column("chats", width=60)
        tree.column("mensajes", width=70)
        tree.column("nuevos", width=60)
        tree.column("id", width=180)

        for r in runs:
            dt_str = r.started_at[:19].replace("T", " ") if r.started_at else "?"
            tree.insert(
                "",
                tk.END,
                values=(
                    dt_str,
                    r.status,
                    r.total_conversations,
                    r.total_messages,
                    r.inserted_messages,
                    r.run_id,
                ),
            )

        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def start_export_thread(self):
        """Run export pipeline in a background thread to maintain GUI responsiveness."""
        self.btn_export.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.lbl_step.config(text="Iniciando exportación...")
        self.log_message("--- Iniciando proceso de exportación ---")

        threading.Thread(target=self._run_export_worker, daemon=True).start()

    def _run_export_worker(self):
        def progress_cb(stage: str, message: str, percent: float):
            self.after(0, lambda: self._update_progress(message, percent))

        try:
            res = self.pipeline.run_export(progress_cb=progress_cb)
            self.after(0, lambda: self._on_export_success(res))
        except WhatsAppBackupError as e:
            self.after(0, lambda err=e: self._on_export_error(err))
        except Exception as e:
            self.after(0, lambda err=e: self._on_unexpected_error(err))
        finally:
            self.after(0, lambda: self.btn_export.config(state=tk.NORMAL))
            self.after(0, self.refresh_status)

    def _update_progress(self, msg: str, pct: float):
        self.progress_bar["value"] = pct
        self.lbl_step.config(text=f"[{pct:.0f}%] {msg}")
        self.log_message(f"[{pct:.0f}%] {msg}")

    def _on_export_success(self, res: dict):
        self.progress_bar["value"] = 100
        self.lbl_step.config(text="Exportación completada con éxito.")
        self.log_message("=== Exportación finalizada correctamente ===")
        msg = (
            f"Exportación realizada con éxito:\n\n"
            f"• Dispositivo: {res['device_model']}\n"
            f"• Conversaciones: {res['total_conversations']}\n"
            f"• Mensajes totales: {res['total_messages']}\n"
            f"• Mensajes nuevos: {res['inserted_messages']}\n\n"
            f"Archivos guardados en data/exports/ (all_messages.csv, conversations.csv y CSVs por chat)."
        )
        if messagebox.askyesno(
            "Exportación Exitosa",
            f"{msg}\n\n¿Deseas abrir la carpeta con los archivos CSV?",
            parent=self,
        ):
            self.open_exports_folder()

    def _on_export_error(self, e: WhatsAppBackupError):
        self.lbl_step.config(text=f"Error: {e.code}")
        self.log_message(f"[ERROR {e.code}] {e.message}")
        messagebox.showerror(
            f"Error en Exportación ({e.code})",
            f"{e.message}\n\nAcción recomendada:\n{e.action_recommended}",
            parent=self,
        )

    def _on_unexpected_error(self, e: Exception):
        self.lbl_step.config(text="Error inesperado.")
        self.log_message(f"[ERROR INESPERADO] {e}")
        messagebox.showerror("Error Inesperado", f"Ocurrió un error inesperado:\n{e}", parent=self)


def main():
    AppConfig.ensure_directories()
    app = AppUI()
    app.mainloop()


if __name__ == "__main__":
    main()
