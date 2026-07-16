import io
import os
import re
import shutil
from collections import Counter

import pytesseract
from PIL import Image, ImageOps

_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
if not shutil.which("tesseract"):
    for _cand in _TESSERACT_CANDIDATES:
        if os.path.exists(_cand):
            pytesseract.pytesseract.tesseract_cmd = _cand
            break

_SCALES = [9, 11]
_THRESHOLDS = [120, 140, 160]
_PSM = ["7"]
_WHITELIST = "0123456789+=?"


def _binarize(gray: Image.Image, scale: int, threshold: int) -> Image.Image:
    big = ImageOps.autocontrast(gray).resize(
        (gray.width * scale, gray.height * scale), Image.LANCZOS
    )
    return big.point(lambda v: 0 if v < threshold else 255)


def _pair_from_text(text: str) -> tuple[int, int] | None:
    # "= ?" sonrasini at, kalanini "+" ile bolerek iki operandi ayir.
    eq = text.find("=")
    segment = text[:eq] if eq > 0 else text
    parts = [p for p in re.split(r"[+]", segment) if re.search(r"\d", p)]
    if len(parts) >= 2:
        return (
            int(re.search(r"\d+", parts[0]).group()),
            int(re.search(r"\d+", parts[1]).group()),
        )
    numbers = re.findall(r"\d+", segment)
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
    return None


def solve_sum_captcha(png_bytes: bytes) -> str | None:
    """Captcha bir 'A + B = ?' toplama sorusu. Cesitli olcek/esik/psm
    kombinasyonlariyla okuyup aday (A, B) ciftlerini toplar ve en cok oy alani
    secer. Hicbir kombinasyon iki sayi okuyamazsa None doner (cagiran taraf
    yeni captcha ile tekrar denemeli)."""
    gray = Image.open(io.BytesIO(png_bytes)).convert("L")

    candidates: list[tuple[int, int]] = []
    for scale in _SCALES:
        for threshold in _THRESHOLDS:
            binary = _binarize(gray, scale, threshold)
            for psm in _PSM:
                text = pytesseract.image_to_string(
                    binary, config=f"--psm {psm} -c tessedit_char_whitelist={_WHITELIST}"
                )
                pair = _pair_from_text(text)
                if pair is not None:
                    candidates.append(pair)

    if not candidates:
        return None

    (a, b), _ = Counter(candidates).most_common(1)[0]
    return str(a + b)
