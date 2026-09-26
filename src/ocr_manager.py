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
        if not roi:
            return image

        w, h = image.size
        left = int(roi["x_min"] * w)
        top = int(roi["y_min"] * h)
        right = int(roi["x_max"] * w)
        bottom = int(roi["y_max"] * h)

        # Ensure valid boundaries
        left = max(0, min(left, w - 10))
        top = max(0, min(top, h - 10))
        right = max(left + 10, min(right, w))
        bottom = max(top + 10, min(bottom, h))

        return image.crop((left, top, right, bottom))

    @classmethod
    def _cluster_and_sort_chunks(
        cls,
        chunks: list[tuple[float, float, str, list]],
        row_threshold: float = 35.0,
    ) -> list[tuple[float, float, str, list]]:
        """Cluster 2D tokens into horizontal lines and sort left-to-right within each line."""
        if not chunks:
            return []

        # Sort roughly by vertical position (Y)
        sorted_by_y = sorted(chunks, key=lambda c: c[0])
        rows: list[list[tuple[float, float, str, list]]] = []
        current_row: list[tuple[float, float, str, list]] = []

        for c in sorted_by_y:
            cy = c[0]
            if not current_row:
                current_row.append(c)
            else:
                avg_y = sum(item[0] for item in current_row) / len(current_row)
                if abs(cy - avg_y) <= row_threshold:
                    current_row.append(c)
                else:
                    current_row.sort(key=lambda item: item[1])
                    rows.append(current_row)
                    current_row = [c]

        if current_row:
            current_row.sort(key=lambda item: item[1])
            rows.append(current_row)

        ordered: list[tuple[float, float, str, list]] = []
        for r in rows:
            for item in r:
                ordered.append(item)
        return ordered

    @classmethod
    def clean_hex_ocr_text(cls, text: str) -> str:
        """Clean OCR recognized text and correct common OCR confusion in hex digits."""
        cleaned = text.strip()
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
            "B": "b",
        }

        res = []
        for ch in cleaned:
            if ch in "0123456789abcdefABCDEF":
                res.append(ch.lower())
            elif ch in char_map:
                res.append(char_map[ch])

        return "".join(res)

    @classmethod
    def extract_key_from_ocr_results(
        cls,
        ocr_result: list,
        image_size: tuple[int, int],
    ) -> tuple[str, dict[str, float] | None]:
        """Extract 64-hex key from RapidOCR results using token spatial clustering and ambiguity correction."""
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
            "B": "b",
        }

        raw_chunks: list[tuple[float, float, str, list]] = []
        all_boxes: list[list[float]] = []

        # 1. Inspect all OCR tokens
        for item in ocr_result:
            if len(item) < 2:
                continue
            box, text = item[0], item[1]
            cy = sum(p[1] for p in box) / 4.0
            cx = sum(p[0] for p in box) / 4.0

            words = re.split(r"[\s\-_]+", text.strip())
            for w in words:
                if not w:
                    continue
                # Map potential OCR substitutions
                cleaned = "".join(char_map.get(ch, ch) for ch in w)
                cleaned_hex = re.sub(r"[^0-9a-fA-F]", "", cleaned).lower()

                # WhatsApp displays keys in groups of 4 hex digits (or multiples of 4: 8, 16)
                if len(cleaned_hex) % 4 == 0 and 0 < len(cleaned_hex) <= 64:
                    # Ensure word was predominantly hex rather than Spanish word stripped of vowels/consonants
                    if len(cleaned_hex) == len(w):
                        for i in range(0, len(cleaned_hex), 4):
                            sub = cleaned_hex[i : i + 4]
                            raw_chunks.append((cy, cx, sub, box))
                            all_boxes.append(box)

        # 2. Cluster chunks into lines and sort left-to-right
        ordered = cls._cluster_and_sort_chunks(raw_chunks, row_threshold=40.0)

        # If exactly 16 4-hex chunks found, we have the complete 64-hex key
        if len(ordered) == 16:
            key_candidate = "".join(c[2] for c in ordered)
            if re.fullmatch(r"[0-9a-f]{64}", key_candidate):
                # Calculate bounding box (ROI) from the 16 key tokens
                w_img, h_img = image_size
                all_pts = [pt for item in ordered for pt in item[3]]
                min_x = max(0.0, (min(p[0] for p in all_pts) - 15) / w_img)
                max_x = min(1.0, (max(p[0] for p in all_pts) + 15) / w_img)
                min_y = max(0.0, (min(p[1] for p in all_pts) - 15) / h_img)
                max_y = min(1.0, (max(p[1] for p in all_pts) + 15) / h_img)
                detected_roi = {
                    "x_min": round(min_x, 3),
                    "y_min": round(min_y, 3),
                    "x_max": round(max_x, 3),
                    "y_max": round(max_y, 3),
                }
                return key_candidate, detected_roi

        # 3. Fallback: If contiguous block of 16 chunks in a larger set
        if len(ordered) > 16:
            for i in range(len(ordered) - 15):
                candidate = "".join(ordered[j][2] for j in range(i, i + 16))
                if len(candidate) == 64 and re.fullmatch(r"[0-9a-f]{64}", candidate):
                    return candidate, None

        # 4. Fallback: Direct text regex matching on cleaned text lines
        raw_lines = [item[1] for item in ocr_result if len(item) >= 2]
        full_raw_text = " ".join(raw_lines)
        cleaned_text = cls.clean_hex_ocr_text(full_raw_text)

        # Search for exact 64-hex substring
        match = re.search(r"[0-9a-f]{64}", cleaned_text)
        if match:
            return match.group(0), None

        return "", None

    @classmethod
    def extract_key_from_image(
        cls,
        image: Image.Image,
        roi: dict[str, float] | None = None,
        use_saved_roi: bool = True,
    ) -> tuple[str, str]:
        """Perform OCR on the image (optionally cropped to ROI) and return (64_hex_key, raw_text)."""
        if _ocr_engine is None:
            raise WhatsAppBackupError(
                code="OCR_ENGINE_UNAVAILABLE",
                message="El motor de OCR (RapidOCR) no está inicializado.",
                operation="extract_key_from_image",
                action_recommended="Instala rapidocr-onnxruntime con 'uv add rapidocr-onnxruntime'.",
            )

        effective_roi = roi or (cls.get_saved_roi() if use_saved_roi else None)

        variants: list[Image.Image] = []
        if effective_roi:
            cropped = cls.crop_to_roi(image, effective_roi)
            variants.append(cropped)
            try:
                gray = cropped.convert("L")
                variants.append(ImageEnhance.Contrast(gray).enhance(1.6))
            except Exception:
                pass

        # Always add original image (and enhanced original) as candidate passes
        variants.append(image)
        try:
            gray_full = image.convert("L")
            variants.append(ImageEnhance.Contrast(gray_full).enhance(1.6))
        except Exception:
            pass

        extracted_key = ""
        detected_roi = None
        full_raw_text = ""

        for candidate_img in variants:
            try:
                ocr_result, _ = _ocr_engine(candidate_img)
            except Exception as e:
                logger.debug(f"OCR variant pass error: {e}")
                continue

            if not ocr_result:
                continue

            raw_lines = [item[1] for item in ocr_result if len(item) >= 2]
            current_raw = " ".join(raw_lines)
            if not full_raw_text:
                full_raw_text = current_raw

            key, maybe_roi = cls.extract_key_from_ocr_results(ocr_result, candidate_img.size)
            if key and len(key) == 64:
                extracted_key = key
                detected_roi = maybe_roi
                full_raw_text = current_raw
                break

        if not full_raw_text:
            raise InvalidKeyError(
                reason="No se detectó ningún texto en el área seleccionada de la pantalla.",
                action_recommended="Asegúrate de que la pantalla del teléfono muestre la clave de 64 dígitos y delimita el área correctamente.",
            )

        # If key was found and ROI was auto-calculated, save it for future runs
        if extracted_key and detected_roi and not roi:
            cls.save_roi(detected_roi)

        if not extracted_key or len(extracted_key) != 64:
            raise InvalidKeyError(
                reason=f"No se pudo aislar la clave de 64 dígitos hexadecimales. Texto detectado: '{full_raw_text[:80]}...'",
                action_recommended="Ajusta el área de captura (ROI) en la interfaz gráfica para encuadrar los 16 bloques de la clave.",
            )

        # Validate format through SecretManager
        valid_key = SecretManager.validate_hex_key(extracted_key)
        return valid_key, full_raw_text
