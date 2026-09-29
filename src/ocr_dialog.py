"""Interactive Tkinter Dialog for capturing screen, delimiting ROI, and performing OCR on WhatsApp 64-digit key."""

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from src.config import AppConfig
from src.errors import WhatsAppBackupError
from src.ocr_manager import OCRManager
from src.secret_manager import SecretManager

logger = logging.getLogger(__name__)


class CaptureKeyDialog(tk.Toplevel):
    """Interactive screen cropping and OCR extraction dialog."""

    def __init__(
        self,
        parent: tk.Tk,
        ocr_manager: OCRManager | None = None,
        account_id: str = "principal",
        device_serial: str = "",
        on_key_saved: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self.account_id = account_id
        self.device_serial = device_serial
        title_suffix = f" [{device_serial}]" if device_serial else ""
        self.title(f"Captura OCR de Clave (64 dígitos) - Cuenta: {self.account_id}{title_suffix}")
        self.geometry("860x720")
        self.minsize(740, 600)
        self.transient(parent)
        self.grab_set()

        # Set dialog icon from branding
        png_icon = AppConfig.get_app_icon_png(64)
        if png_icon:
            try:
                self._dialog_icon_photo = ImageTk.PhotoImage(Image.open(png_icon))
                self.iconphoto(False, self._dialog_icon_photo)
            except Exception:
                pass

        self.ocr_manager = ocr_manager or OCRManager()
        self.secret_manager = SecretManager()
        self.on_key_saved = on_key_saved

        self.original_image: Image.Image | None = None
        self.display_image: Image.Image | None = None
        self.tk_image: ImageTk.PhotoImage | None = None

        self.scale_factor = 1.0
        self.img_offset_x = 0
        self.img_offset_y = 0

        # ROI selection state (in canvas coords)
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        # Normalized ROI (0.0 to 1.0)
        self.current_roi = self.ocr_manager.get_saved_roi() or {
            "x_min": 0.107,
            "y_min": 0.318,
            "x_max": 0.897,
            "y_max": 0.466,
        }

        self._build_ui()
        self.after(100, self.refresh_screenshot)

    def _build_ui(self):
        # Top toolbar
        top_frame = ttk.Frame(self, padding="10 8")
        top_frame.pack(fill=tk.X)

        instructions = (
            f"Cuenta seleccionada: [{self.account_id.upper()}]\n"
            "1. En tu teléfono, abre WhatsApp > Copia de seguridad cifrada y muestra la clave de 64 dígitos.\n"
            "2. Pulsa '📷 Capturar Pantalla' y delimita con el ratón el área de la clave (o usa la detectada).\n"
            "3. Pulsa '🔍 EXTRAER CLAVE (OCR)' para verificarla y guardarla en el almacén seguro."
        )
        ttk.Label(top_frame, text=instructions, font=("Helvetica", 9), justify=tk.LEFT).pack(
            side=tk.LEFT, padx=5
        )

        btn_box = ttk.Frame(top_frame)
        btn_box.pack(side=tk.RIGHT, padx=5)

        ttk.Button(btn_box, text="📷 Capturar Pantalla", command=self.refresh_screenshot).pack(
            fill=tk.X, pady=2
        )

        # Center Canvas for Interactive Cropping
        canvas_frame = ttk.Frame(self, padding="10 5")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#202020", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind canvas mouse events for rectangle selection
        self.canvas.bind("<ButtonPress-1>", self._on_button_press)
        self.canvas.bind("<B1-Motion>", self._on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_release)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Bottom Controls and Results
        bot_frame = ttk.LabelFrame(self, text=" Extracción y Guardado ", padding="10 8")
        bot_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        roi_opts = ttk.Frame(bot_frame)
        roi_opts.pack(fill=tk.X, pady=2)

        self.var_save_roi = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            roi_opts,
            text="Guardar este área delimitada (ROI) como referencia para futuros dispositivos",
            variable=self.var_save_roi,
        ).pack(side=tk.LEFT)

        self.lbl_roi_info = ttk.Label(
            roi_opts, text="", font=("Helvetica", 8), foreground="#666666"
        )
        self.lbl_roi_info.pack(side=tk.RIGHT)

        # Action and Result display
        res_row = ttk.Frame(bot_frame)
        res_row.pack(fill=tk.X, pady=(6, 2))

        self.btn_ocr = ttk.Button(res_row, text="🔍  EXTRAER CLAVE (OCR)", command=self.perform_ocr)
        self.btn_ocr.pack(side=tk.LEFT, padx=(0, 10), ipady=3)

        self.ent_extracted_key = ttk.Entry(res_row, font=("Consolas", 11, "bold"), state="readonly")
        self.ent_extracted_key.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.btn_save = ttk.Button(
            res_row,
            text="💾 Guardar Clave",
            state=tk.DISABLED,
            command=self.save_extracted_key,
        )
        self.btn_save.pack(side=tk.RIGHT, padx=5)

    def refresh_screenshot(self):
        """Capture screenshot from connected phone via ADB asynchronously."""
        self.lbl_roi_info.config(text="Capturando pantalla desde el teléfono vía ADB...")
        threading.Thread(target=self._async_capture_worker, daemon=True).start()

    def _async_capture_worker(self):
        try:
            img = self.ocr_manager.capture_screenshot()
            self.after(0, lambda: self._on_screenshot_captured(img))
        except WhatsAppBackupError as e:
            self.after(0, lambda err=e: self._on_capture_error(err))
        except Exception as e:
            self.after(
                0,
                lambda err=e: messagebox.showerror(
                    "Error Inesperado", f"No se pudo capturar la pantalla: {err}", parent=self
                ),
            )

    def _on_screenshot_captured(self, img):
        self.original_image = img
        self._redraw_image_and_roi()
        self.lbl_roi_info.config(text="Pantalla capturada. Delimita el área de la clave con el ratón.")

    def _on_capture_error(self, e: WhatsAppBackupError):
        self.lbl_roi_info.config(text="Error al capturar pantalla.")
        messagebox.showerror(
            "Error de Captura",
            f"{e.message}\n\nAcción recomendada:\n{e.action_recommended}",
            parent=self,
        )

    def _on_canvas_resize(self, event):
        if self.original_image:
            self._redraw_image_and_roi()

    def _redraw_image_and_roi(self):
        if not self.original_image:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        orig_w, orig_h = self.original_image.size

        # Fit image to canvas maintaining aspect ratio
        scale = min(cw / orig_w, ch / orig_h, 1.0)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        self.scale_factor = scale
        self.img_offset_x = (cw - new_w) // 2
        self.img_offset_y = (ch - new_h) // 2

        resized = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(
            self.img_offset_x, self.img_offset_y, anchor=tk.NW, image=self.tk_image
        )

        # Draw current ROI rectangle
        self._draw_roi_rect()

    def _draw_roi_rect(self):
        if not self.current_roi or not self.original_image:
            return

        orig_w, orig_h = self.original_image.size
        left = self.img_offset_x + int(self.current_roi["x_min"] * orig_w * self.scale_factor)
        top = self.img_offset_y + int(self.current_roi["y_min"] * orig_h * self.scale_factor)
        right = self.img_offset_x + int(self.current_roi["x_max"] * orig_w * self.scale_factor)
        bottom = self.img_offset_y + int(self.current_roi["y_max"] * orig_h * self.scale_factor)

        if self.rect_id:
            self.canvas.delete(self.rect_id)

        self.rect_id = self.canvas.create_rectangle(
            left, top, right, bottom, outline="#00FF66", width=2, dash=(4, 2)
        )
        self.lbl_roi_info.config(
            text=f"Área seleccionada: {self.current_roi['x_min'] * 100:.0f}%-{self.current_roi['x_max'] * 100:.0f}% X, {self.current_roi['y_min'] * 100:.0f}%-{self.current_roi['y_max'] * 100:.0f}% Y"
        )

    def _on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline="#00FF66", width=2
        )

    def _on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)

    def _on_button_release(self, event):
        if not self.original_image:
            return

        end_x = event.x
        end_y = event.y

        # Order coordinates
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        # Check minimal selection
        if (x2 - x1) < 20 or (y2 - y1) < 20:
            self._redraw_image_and_roi()
            return

        # Convert canvas coords to normalized image coords (0.0 to 1.0)
        orig_w, orig_h = self.original_image.size
        scaled_w = orig_w * self.scale_factor
        scaled_h = orig_h * self.scale_factor

        norm_x1 = max(0.0, min(1.0, (x1 - self.img_offset_x) / scaled_w))
        norm_y1 = max(0.0, min(1.0, (y1 - self.img_offset_y) / scaled_h))
        norm_x2 = max(0.0, min(1.0, (x2 - self.img_offset_x) / scaled_w))
        norm_y2 = max(0.0, min(1.0, (y2 - self.img_offset_y) / scaled_h))

        self.current_roi = {
            "x_min": round(norm_x1, 3),
            "y_min": round(norm_y1, 3),
            "x_max": round(norm_x2, 3),
            "y_max": round(norm_y2, 3),
        }
        self._draw_roi_rect()

    def perform_ocr(self):
        """Run OCR on the delimited ROI asynchronously."""
        if not self.original_image:
            messagebox.showwarning(
                "Sin Imagen",
                "Captura primero la pantalla del teléfono con el botón '📷 Capturar Pantalla'.",
                parent=self,
            )
            return

        # Save ROI if requested
        if self.var_save_roi.get() and self.current_roi:
            self.ocr_manager.save_roi(self.current_roi)

        self.btn_ocr.config(state=tk.DISABLED)
        self.lbl_roi_info.config(text="Ejecutando reconocimiento OCR sobre el área delimitada...")
        threading.Thread(target=self._async_ocr_worker, daemon=True).start()

    def _async_ocr_worker(self):
        try:
            key_hex, _raw_text = self.ocr_manager.extract_key_from_image(
                self.original_image, self.current_roi
            )
            self.after(0, lambda: self._on_ocr_success(key_hex))
        except WhatsAppBackupError as e:
            self.after(0, lambda err=e: self._on_ocr_error(err))
        except Exception as e:
            self.after(
                0,
                lambda err=e: messagebox.showerror(
                    "Error Inesperado", f"Fallo al ejecutar OCR: {err}", parent=self
                ),
            )
        finally:
            self.after(0, lambda: self.btn_ocr.config(state=tk.NORMAL))

    def _on_ocr_success(self, key_hex: str):
        formatted_key = " ".join([key_hex[i : i + 4] for i in range(0, 64, 4)])
        self.ent_extracted_key.config(state="normal")
        self.ent_extracted_key.delete(0, tk.END)
        self.ent_extracted_key.insert(0, formatted_key)
        self.ent_extracted_key.config(state="readonly")
        self.btn_save.config(state=tk.NORMAL)
        self.detected_key_clean = key_hex
        self.lbl_roi_info.config(text="¡Clave extraída y validada correctamente!")
        messagebox.showinfo(
            "Clave Detectada con Éxito",
            f"Se han extraído correctamente los 64 dígitos hexadecimales de la clave.\n\n"
            f"Clave:\n{formatted_key}\n\n"
            f"Pulsa '💾 Guardar Clave' para almacenarla de forma segura.",
            parent=self,
        )

    def _on_ocr_error(self, e: WhatsAppBackupError):
        self.lbl_roi_info.config(text="Error de lectura OCR.")
        messagebox.showerror("Error de OCR", f"{e.message}\n\n{e.action_recommended}", parent=self)

    def save_extracted_key(self):
        """Save the extracted valid key into the OS keyring."""
        if not hasattr(self, "detected_key_clean") or not self.detected_key_clean:
            return

        try:
            self.secret_manager.store_key(
                self.detected_key_clean, self.account_id, serial=self.device_serial
            )
            messagebox.showinfo(
                "Clave Guardada",
                f"La clave se ha validado y almacenado de forma segura en el almacén de credenciales para la cuenta '{self.account_id}'.",
                parent=self,
            )
            if self.on_key_saved:
                self.on_key_saved(self.detected_key_clean)
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                "Error al Guardar", f"No se pudo guardar la clave: {e}", parent=self
            )
