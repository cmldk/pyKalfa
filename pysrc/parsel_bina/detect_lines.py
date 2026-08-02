"""
pyKalfa / Parsel-Bina - parsel ve bina sinir cizgisi tespiti

assets/ altindaki kadastro goruntulerinden (parsel.png, bina.png) cizgi/kontur
tespiti yaparak output/ klasorune ara ve sonuc gorsellerini yazar.

Kullanim:
    env/Scripts/python.exe pysrc/parsel_bina/detect_lines.py
    env/Scripts/python.exe pysrc/parsel_bina/detect_lines.py --image assets/parsel.png --output-dir output
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Ayarlanabilir parametreler
# ---------------------------------------------------------------------------

WHITE_THRESHOLD = 240          # bu degerin ustundeki gri tonlar "arka plan/beyaz" sayilir
MIN_COMPONENT_SIZE = 18        # px cinsinden; bbox'in her iki kenari da bunun altindaysa
                                # bilesen metin/etiket karakteri sayilip elenir
MORPH_KERNEL_SIZE = 3          # cizgilerdeki kucuk kopukluklari kapatmak icin
MIN_CONTOUR_AREA = 40          # bu alanin altindaki konturlar gurultu sayilir
APPROX_EPSILON_RATIO = 0.01    # kontur sadelestirme (cv2.approxPolyDP) toleransi

CONTOUR_COLOR = (0, 200, 0)     # BGR - tespit edilen kontur cizim rengi
CONTOUR_THICKNESS = 2


@dataclass
class DetectionResult:
    mask: np.ndarray
    edges: np.ndarray
    overlay: np.ndarray
    contours: list[np.ndarray]


def _strip_text_labels(binary_mask: np.ndarray, min_component_size: int) -> np.ndarray:
    """Etiket/rakam gibi kucuk kompakt bilesenleri maskeden temizler.

    Parsel/bina cizgileri genelde en az bir eksende uzun sureklidir; harf ve
    rakamlarin bounding box'i ise her iki eksende de kucuktur. Bu ayrim
    gurultu/metin ile geometri (cizgi) arasinda basit ama etkili bir filtre
    saglar.
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    cleaned = np.zeros_like(binary_mask)
    for label_id in range(1, num_labels):  # 0 = arka plan
        w = stats[label_id, cv2.CC_STAT_WIDTH]
        h = stats[label_id, cv2.CC_STAT_HEIGHT]
        if w < min_component_size and h < min_component_size:
            continue  # kucuk/kompakt -> muhtemelen metin karakteri, at
        cleaned[labels == label_id] = 255
    return cleaned


def _load_on_white_background(image_path: Path) -> np.ndarray:
    """PNG'yi alfa kanaliyla birlikte okuyup beyaz zemin uzerine duzlestirir.

    Kaynak gorsellerde seffaf pikseller RGB=(0,0,0) olarak saklaniyor; alfayi
    yok sayip dogrudan BGR okumak zemini siyaha cevirir. Bu yuzden alfa
    varsa once beyaz arka plan uzerine composite ediyoruz.
    """
    raw = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Goruntu okunamadi: {image_path}")
    if raw.ndim == 2 or raw.shape[2] == 3:
        return raw if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)

    bgr, alpha = raw[:, :, :3], raw[:, :, 3:4].astype(np.float32) / 255.0
    white_bg = np.full_like(bgr, 255)
    composited = (bgr.astype(np.float32) * alpha + white_bg.astype(np.float32) * (1 - alpha))
    return composited.astype(np.uint8)


def build_line_mask(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Goruntuyu okuyup yalniz cizgi/geometri piksellerinden olusan ikili
    (binary) maskeyi dondurur (metin etiketleri elenmis, kopukluklar kapatilmis).

    Bu fonksiyon `detect_boundaries` (genel/Faz 1 kullanim) ile
    `src/geometry.py` (Faz 3 - katman bazli temiz kontur cikarimi) arasinda
    paylasilir; esikleme/temizleme mantigini tek yerde tutar.
    """
    image = _load_on_white_background(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Beyaz/acik arka plan disindaki her sey (cizgi + metin) -> beyaz piksel
    _, binary = cv2.threshold(gray, WHITE_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # Metin etiketlerini ele, sadece cizgi/geometri kalsin
    line_mask = _strip_text_labels(binary, MIN_COMPONENT_SIZE)

    # Cizgilerdeki kucuk kopukluklari kapat (morfolojik kapama)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    closed_mask = cv2.morphologyEx(line_mask, cv2.MORPH_CLOSE, kernel)
    return image, closed_mask


def detect_boundaries(image_path: Path) -> tuple[np.ndarray, DetectionResult]:
    image, closed_mask = build_line_mask(image_path)

    edges = cv2.Canny(closed_mask, 50, 150)

    contours, _ = cv2.findContours(closed_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= MIN_CONTOUR_AREA or cv2.arcLength(c, False) >= 60]

    overlay = image.copy()
    cv2.drawContours(overlay, contours, -1, CONTOUR_COLOR, CONTOUR_THICKNESS)

    result = DetectionResult(mask=closed_mask, edges=edges, overlay=overlay, contours=contours)
    return image, result


def _contours_to_polygons(contours: list[np.ndarray]) -> list[list[list[int]]]:
    polygons = []
    for c in contours:
        epsilon = APPROX_EPSILON_RATIO * cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, epsilon, True)
        polygons.append(approx.reshape(-1, 2).tolist())
    return polygons


def process_image(image_path: Path, output_dir: Path) -> None:
    stem = image_path.stem
    image, result = detect_boundaries(image_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_dir / f"{stem}_mask.png"), result.mask)
    cv2.imwrite(str(output_dir / f"{stem}_edges.png"), result.edges)
    cv2.imwrite(str(output_dir / f"{stem}_contours.png"), result.overlay)

    polygons = _contours_to_polygons(result.contours)
    summary = {
        "source_image": str(image_path.as_posix()),
        "image_size": {"width": image.shape[1], "height": image.shape[0]},
        "detected_contour_count": len(result.contours),
        "polygons_px": polygons,
    }
    with open(output_dir / f"{stem}_polygons.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[{stem}] {len(result.contours)} kontur tespit edildi -> {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parsel/bina cizgi tespiti (cv2)")
    parser.add_argument("--image", type=Path, default=None, help="Tek bir goruntu isle (varsayilan: assets altindaki tum png'ler)")
    parser.add_argument("--assets-dir", type=Path, default=Path("assets"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    if args.image is not None:
        process_image(args.image, args.output_dir)
        return

    images = sorted(args.assets_dir.glob("*.png"))
    if not images:
        raise SystemExit(f"'{args.assets_dir}' icinde png bulunamadi")

    for image_path in images:
        process_image(image_path, args.output_dir)


if __name__ == "__main__":
    main()
