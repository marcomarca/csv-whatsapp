"""OCR and Screen Capture Manager for extracting 64-digit WhatsApp encryption keys from Android screens."""

import io
import json
import logging
import re
from pathlib import Path

from PIL import Image, ImageEnhance

from src.config import AppConfig
from src.device_manager import DeviceManager
from src.errors import InvalidKeyError, WhatsAppBackupError
from src.secret_manager import SecretManager

logger = logging.getLogger(__name__)

try:
    from rapidocr_onnxruntime import RapidOCR

    _ocr_engine = RapidOCR()
except Exception as e:
    logger.warning(f"Could not initialize RapidOCR: {e}")
    _ocr_engine = None


class OCRManager:
    """Manages Android screen capture, ROI bounding box persistence, and OCR key extraction."""

    ROI_CONFIG_FILE: Path = AppConfig.WORKING_DIR / "ocr_roi.json"

    def __init__(self, device_manager: DeviceManager | None = None):
        self.device_manager = device_manager or DeviceManager()

    def capture_screenshot(self, serial: str | None = None) -> Image.Image:
        """Capture the current phone screen via ADB and return a PIL Image."""
        dev = self.device_manager.get_active_device(serial)

        # Use 'exec-out screencap -p' for binary PNG stream
        cmd = [self.device_manager.adb_path, "-s", dev.serial, "exec-out", "screencap", "-p"]
        try:
            import subprocess

            res = subprocess.run(cmd, capture_output=True, check=False, timeout=30)
            if res.returncode != 0 or not res.stdout:
                # Fallback to shell screencap
                cmd_fallback = [
                    self.device_manager.adb_path,
                    "-s",
                    dev.serial,
                    "shell",
                    "screencap",
                    "-p",
                ]
                res = subprocess.run(cmd_fallback, capture_output=True, check=False, timeout=30)

            if not res.stdout or len(res.stdout) < 100:
                raise WhatsAppBackupError(
                    code="SCREEN_CAPTURE_FAILED",
                    message="No se pudo capturar la pantalla del teléfono mediante ADB.",
                    operation="capture_screenshot",
                    action_recommended="Comprueba que el teléfono esté desbloqueado y con la pantalla encendida.",
                    retryable=True,
                )

            # Fix Windows CRLF translation in stdout binary stream if present
            raw_png = (
                res.stdout.replace(b"\r\n", b"\n")
                if res.stdout.startswith(b"\x89PNG\r\r\n")
                else res.stdout
            )
            if not raw_png.startswith(b"\x89PNG"):
                # Search for PNG header inside buffer
                png_idx = raw_png.find(b"\x89PNG")
                if png_idx != -1:
                    raw_png = raw_png[png_idx:]

            img = Image.open(io.BytesIO(raw_png))
            img.load()
            return img

        except WhatsAppBackupError:
            raise
        except Exception as e:
            raise WhatsAppBackupError(
                code="SCREEN_CAPTURE_FAILED",
                message=f"Error al capturar la pantalla: {e}",
                operation="capture_screenshot",
                action_recommended="Desbloquea el teléfono y mantén la pantalla en WhatsApp.",
                retryable=True,
            )

    @classmethod
    def get_saved_roi(cls) -> dict[str, float] | None:
        """Get the saved normalized Region of Interest (0.0 to 1.0 coordinates)."""
        if cls.ROI_CONFIG_FILE.is_file():
            try:
                with open(cls.ROI_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if all(k in data for k in ("x_min", "y_min", "x_max", "y_max")):
                        return data
            except Exception as e:
                logger.warning(f"Could not read saved ROI: {e}")
        return None

    @classmethod
    def save_roi(cls, roi: dict[str, float]) -> None:
        """Save normalized Region of Interest coordinates (x_min, y_min, x_max, y_max) to config."""
        cls.ROI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.ROI_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(roi, f, indent=2)
        logger.info(f"Saved OCR ROI configuration: {roi}")

    @classmethod
    def crop_to_roi(cls, image: Image.Image, roi: dict[str, float] | None = None) -> Image.Image:
        """Crop PIL Image using normalized coordinates (0.0 to 1.0)."""
        effective_roi = roi or cls.get_saved_roi()
        if not effective_roi:
            return image

        w, h = image.size
        left = int(effective_roi["x_min"] * w)
        top = int(effective_roi["y_min"] * h)
        right = int(effective_roi["x_max"] * w)
        bottom = int(effective_roi["y_max"] * h)

        # Ensure valid boundaries
        left = max(0, min(left, w - 10))
        top = max(0, min(top, h - 10))
        right = max(left + 10, min(right, w))
        bottom = max(top + 10, min(bottom, h))

        return image.crop((left, top, right, bottom))

    @classmethod
    def clean_hex_ocr_text(cls, text: str) -> str:
        """Clean OCR recognized text and correct common OCR confusion in hex digits."""
        # Remove whitespace, newlines, colons, hyphens, dots
        cleaned = text.strip()

        # WhatsApp 64-digit key is displayed in 16 groups of 4 or 4 lines of 16.
        # Common OCR ambiguities:
        # 'O', 'o' -> '0'
        # 'l', 'I', '|' -> '1'
        # 'S', 's' -> '5'
        # 'B' (if surrounded by hex lowercase) -> 'b'
        # 'Z', 'z' -> '2' (in some cases)
        char_map = {
            "O": "0",
            "o": "0",
            "l": "1",
            "I": "1",
            "|": "1",
            "S": "5",
            "s": "5",
            "Z": "2",
            "z": "2",
        }

        # Replace non-hex with mapped chars
        res = []
        for ch in cleaned:
            if ch in "0123456789abcdefABCDEF":
                res.append(ch.lower())
            elif ch in char_map:
                res.append(char_map[ch])

        result_hex = "".join(res)
        return result_hex

    @classmethod
    def extract_key_from_image(
        cls,
        image: Image.Image,
        roi: dict[str, float] | None = None,
    ) -> tuple[str, str]:
        """Perform OCR on the image (cropped to ROI) and return (64_hex_key, raw_text)."""
        cropped = cls.crop_to_roi(image, roi)

        # Preprocessing: convert to grayscale and enhance contrast
        gray = cropped.convert("L")
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.8)

        if _ocr_engine is None:
            raise WhatsAppBackupError(
                code="OCR_ENGINE_UNAVAILABLE",
                message="El motor de OCR (RapidOCR) no está inicializado.",
                operation="extract_key_from_image",
                action_recommended="Instala rapidocr-onnxruntime con 'uv add rapidocr-onnxruntime'.",
            )

        # Run OCR
        ocr_result, _ = _ocr_engine(enhanced)
        if not ocr_result:
            # Try on original cropped color image
            ocr_result, _ = _ocr_engine(cropped)

        if not ocr_result:
            raise InvalidKeyError(
                reason="No se detectó ningún texto en el área seleccionada de la pantalla.",
                action_recommended="Asegúrate de que la pantalla del teléfono muestre la clave de 64 dígitos y delimita el área correctamente.",
            )

        # Collect detected text lines
        raw_lines = [item[1] for item in ocr_result if len(item) >= 2]
        full_raw_text = " ".join(raw_lines)
        logger.info(f"Raw OCR text detected: '{full_raw_text}'")

        cleaned_hex = cls.clean_hex_ocr_text(full_raw_text)

        if len(cleaned_hex) != 64 or not re.fullmatch(r"[0-9a-f]{64}", cleaned_hex):
            raise InvalidKeyError(
                reason=f"El texto extraído por OCR contiene {len(cleaned_hex)} caracteres hexadecimales (se requieren exactamente 64). Texto detectado: '{full_raw_text}'",
                action_recommended="Ajusta el área de captura (ROI) para encuadrar exactamente los 64 dígitos de la clave.",
            )

        # Validate format through SecretManager
        valid_key = SecretManager.validate_hex_key(cleaned_hex)
        return valid_key, full_raw_text
