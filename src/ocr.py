from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from typing import List

import fitz  # PyMuPDF
import pandas as pd
import pytesseract
from PIL import Image

from .image_quality import ImageQualityReport, assess_image_quality, make_ocr_variants

WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(WINDOWS_TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = WINDOWS_TESSERACT_PATH
else:
    discovered = shutil.which("tesseract")
    if discovered:
        pytesseract.pytesseract.tesseract_cmd = discovered


@dataclass
class OCRPageResult:
    page_number: int
    text: str


@dataclass
class OCRResult:
    text: str
    pages: List[OCRPageResult]
    quality: ImageQualityReport | None
    engine: str = "Tesseract OCR multi-pass"


def _dedupe_lines(text_blocks: list[str]) -> str:
    seen = set()
    lines = []
    for block in text_blocks:
        for raw_line in block.splitlines():
            line = " ".join(raw_line.split()).strip()
            if len(line) < 2:
                continue
            key = line.lower()
            if key not in seen:
                seen.add(key)
                lines.append(line)
    return "\n".join(lines)


def _ocr_image_multi_pass(image: Image.Image, rescue: bool = True) -> tuple[str, ImageQualityReport]:
    quality = assess_image_quality(image)
    variants = make_ocr_variants(image) if rescue else [("original", image)]
    psm_modes = [6, 11] if rescue else [6]
    text_blocks: list[str] = []

    for variant_name, variant in variants:
        for psm in psm_modes:
            config = f"--oem 3 --psm {psm}"
            try:
                text = pytesseract.image_to_string(variant, config=config)
                if text and text.strip():
                    text_blocks.append(text)
            except Exception:
                continue

    return _dedupe_lines(text_blocks), quality


def ocr_word_data(image: Image.Image) -> pd.DataFrame:
    # Used for style/capitalization heuristics, not full font recognition.
    variants = make_ocr_variants(image)
    best_variant = variants[0][1]
    data = pytesseract.image_to_data(best_variant, output_type=pytesseract.Output.DATAFRAME, config="--oem 3 --psm 6")
    data = data.dropna(subset=["text"])
    data = data[data["text"].astype(str).str.strip() != ""]
    return data


def _pdf_to_images(file_bytes: bytes, dpi: int = 180) -> List[Image.Image]:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images: List[Image.Image] = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    return images


def run_ocr(file_bytes: bytes, filename: str, rescue: bool = True) -> OCRResult:
    suffix = filename.lower().split(".")[-1]
    images = _pdf_to_images(file_bytes) if suffix == "pdf" else [Image.open(io.BytesIO(file_bytes))]

    pages: List[OCRPageResult] = []
    first_quality: ImageQualityReport | None = None
    for i, image in enumerate(images, start=1):
        text, quality = _ocr_image_multi_pass(image, rescue=rescue)
        if first_quality is None:
            first_quality = quality
        pages.append(OCRPageResult(page_number=i, text=text))
    return OCRResult(text="\n\n".join(page.text for page in pages), pages=pages, quality=first_quality)
