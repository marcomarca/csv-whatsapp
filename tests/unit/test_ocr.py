"""Unit tests for OCRManager, ROI cropping, and 64-hex key extraction."""

from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from src.errors import InvalidKeyError
from src.ocr_manager import OCRManager


def test_clean_hex_ocr_text():
    """Test cleaning raw OCR text and resolving common character ambiguities."""
    raw = "  4a 1f 89 b2 : c3 d4 e5 f6 \n O1 23 45 67 89 ab cd ef \n fe dc ba 98 76 54 32 10 \n 11 22 33 44 55 66 77 88  "
    cleaned = OCRManager.clean_hex_ocr_text(raw)
    assert len(cleaned) == 64
    assert cleaned.startswith("4a1f89b2c3d4e5f601234567")


def test_crop_to_roi():
    """Test cropping image to normalized ROI bounding box."""
    img = Image.new("RGB", (1000, 2000), color=(255, 255, 255))
    roi = {"x_min": 0.1, "y_min": 0.2, "x_max": 0.9, "y_max": 0.6}

    cropped = OCRManager.crop_to_roi(img, roi)
    assert cropped.size == (800, 800)  # 0.8 * 1000, 0.4 * 2000


def test_roi_save_and_get(tmp_path: Path, monkeypatch):
    """Test ROI configuration persistence."""
    roi_file = tmp_path / "ocr_roi.json"
    monkeypatch.setattr("src.ocr_manager.OCRManager.ROI_CONFIG_FILE", roi_file)

    assert OCRManager.get_saved_roi() is None

    test_roi = {"x_min": 0.05, "y_min": 0.30, "x_max": 0.95, "y_max": 0.70}
    OCRManager.save_roi(test_roi)

    loaded = OCRManager.get_saved_roi()
    assert loaded == test_roi


def test_extract_key_from_synthetic_image():
    """Test OCR key extraction on a synthetic image containing 64 hex characters."""
    img = Image.new("RGB", (800, 250), color=(255, 255, 255))
    d = ImageDraw.Draw(img)

    lines = [
        "4a 1f 89 b2 c3 d4 e5 f6",
        "01 23 45 67 89 ab cd ef",
        "fe dc ba 98 76 54 32 10",
        "11 22 33 44 55 66 77 88",
    ]
    for i, line in enumerate(lines):
        d.text((40, 30 + i * 40), line, fill=(0, 0, 0))

    key, raw_text = OCRManager.extract_key_from_image(img)
    assert len(key) == 64
    assert key == "4a1f89b2c3d4e5f60123456789abcdeffedcba98765432101122334455667788"


def test_extract_key_invalid_text_raises_error():
    """Test that image without 64 hex digits raises InvalidKeyError."""
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 20), "Texto sin clave suficiente 1234", fill=(0, 0, 0))

    with pytest.raises(InvalidKeyError):
        OCRManager.extract_key_from_image(img)
