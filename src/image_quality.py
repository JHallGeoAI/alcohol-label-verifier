from __future__ import annotations

from dataclasses import dataclass, asdict
import cv2
import numpy as np
from PIL import Image


@dataclass
class ImageQualityReport:
    sharpness: float
    contrast: float
    glare_percent: float
    width: int
    height: int
    warnings: list[str]

    def to_dict(self):
        return asdict(self)


def pil_to_rgb_array(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("RGB"))


def assess_image_quality(image: Image.Image) -> ImageQualityReport:
    arr = pil_to_rgb_array(image)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    glare_percent = float((gray > 245).sum() / gray.size * 100.0)
    warnings: list[str] = []
    if sharpness < 80:
        warnings.append("Image may be blurry; OCR confidence may be reduced.")
    if contrast < 35:
        warnings.append("Image appears low contrast or poorly lit.")
    if glare_percent > 8:
        warnings.append("Bright glare/overexposure detected; required text may be obscured.")
    if min(image.size) < 800:
        warnings.append("Image resolution is low; upload a larger image if OCR is weak.")
    return ImageQualityReport(sharpness, contrast, glare_percent, image.width, image.height, warnings)


def resize_for_ocr(arr: np.ndarray, target_max: int = 1800) -> np.ndarray:
    h, w = arr.shape[:2]
    max_dim = max(h, w)
    if max_dim < target_max:
        scale = target_max / max_dim
        return cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if max_dim > 2600:
        scale = 2600 / max_dim
        return cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return arr


def deskew_gray(gray: np.ndarray) -> np.ndarray:
    # Deskew based on foreground pixel coordinates; conservative to avoid damaging labels.
    try:
        inv = cv2.bitwise_not(gray)
        thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if coords.size == 0:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 1 or abs(angle) > 12:
            return gray
        h, w = gray.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return gray


def reduce_glare(rgb: np.ndarray) -> np.ndarray:
    # Light-touch glare reduction for OCR variants. This cannot recover fully washed-out text.
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    mask = (v > 240) & (s < 45)
    if mask.mean() < 0.01:
        return rgb
    v2 = v.copy()
    v2[mask] = 210
    merged = cv2.merge([h, s, v2])
    return cv2.cvtColor(merged, cv2.COLOR_HSV2RGB)


def make_ocr_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    rgb = resize_for_ocr(pil_to_rgb_array(image))
    variants: list[tuple[str, Image.Image]] = [("original", Image.fromarray(rgb))]

    glare = reduce_glare(rgb)
    if not np.array_equal(glare, rgb):
        variants.append(("glare_reduced", Image.fromarray(glare)))

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.bilateralFilter(gray, 5, 35, 35)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    variants.append(("contrast_grayscale", Image.fromarray(clahe)))

    deskewed = deskew_gray(clahe)
    variants.append(("deskewed_grayscale", Image.fromarray(deskewed)))

    thresh = cv2.adaptiveThreshold(deskewed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 11)
    variants.append(("adaptive_threshold", Image.fromarray(thresh)))

    # Inverted threshold sometimes helps light text on dark banners.
    variants.append(("adaptive_threshold_inverted", Image.fromarray(cv2.bitwise_not(thresh))))
    return variants
