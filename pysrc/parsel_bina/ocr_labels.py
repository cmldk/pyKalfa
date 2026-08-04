"""
pyKalfa / Parsel-Bina - parsel numara etiketlerini (ör. "591G") OCR ile okuma.

Parsel cizgileri kirmizi, etiketler notr gri/siyah renkte oldugu icin
(bkz. imaging.py: katman renkleri), etiketleri ayni mantikla izole edip
EasyOCR'a veriyoruz. Boylece parsel agi/bina cizgileri/olcek cubugu/kuzey
oku (hicbiri notr degil) OCR'a hic girmiyor.

Notlar:
- EasyOCR (PyTorch tabanli) agir bir bagimliliktir (~1-1.5 GB, ilk
  kullanimda ayrica model indirir, internet gerektirir).
- Kucuk harita etiketleri (ör. 12-16 px yukseklik) OCR icin zorlayici;
  3x buyutme + sadece rakam/buyuk harf izin verilmesi (allowlist) test
  edilen dogrulugu ~%35'ten ~%80'e cikardi. Kalan hatalar genelde
  birbirine benzeyen karakterler (G/6, A/4, B/8, S/5 gibi). `confidence`
  degeri bu yuzden JSON'a dahil edilir.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2

from imaging import text_image

UPSCALE_FACTOR = 3                 # OCR dogrulugu icin kucuk etiketleri buyutme orani
OCR_ALLOWLIST = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MIN_CONFIDENCE = 0.15              # bu esigin altindaki okumalar (cok dusuk = gurultu) atilir


def extract_parcel_labels(image_path: Path) -> list[dict]:
    """Parsel numara etiketlerini OCR ile okuyup liste olarak dondurur.

    Her etiket: okunan metin, OCR guven skoru (0-1), piksel-uzayindaki
    merkez nokta ve piksel-uzayindaki (Y-asagi eksenine gore) dönüş
    acisi (radyan). Gercek birime cevirme/Y-flip prepare_revit_input.py'de
    yapilir (diger katmanlarla ayni transform kullanilsin diye).
    """
    import easyocr  # agir import; sadece bu fonksiyon cagrildiginda yuklenir

    upscaled = cv2.resize(
        text_image(image_path), None, fx=UPSCALE_FACTOR, fy=UPSCALE_FACTOR,
        interpolation=cv2.INTER_CUBIC,
    )

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    raw_results = reader.readtext(upscaled, detail=1, allowlist=OCR_ALLOWLIST)

    labels = []
    for bbox, text, confidence in raw_results:
        if confidence < MIN_CONFIDENCE or not text:
            continue
        pts = [(px / UPSCALE_FACTOR, py / UPSCALE_FACTOR) for px, py in bbox]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        (x0, y0), (x1, y1) = pts[0], pts[1]
        angle_rad_px = math.atan2(y1 - y0, x1 - x0)
        labels.append(
            {
                "text": text,
                "confidence": round(float(confidence), 3),
                "center_px": (cx, cy),
                "angle_rad_px": angle_rad_px,
            }
        )
    return labels
