"""
pyKalfa / Parsel-Bina - Faz 3: olcek kalibrasyonu

Kullanici haritanin basim olcegini (ör. 1:1000 icin --scale 1000) verir;
goruntudeki dolu lacivert olcek cubugunun piksel uzunlugu renk+sekil
bazli otomatik tespit edilir (OCR yok). IGN kadastro kurali geregi olcek
cubugunun gercek dunya karsiligi olcek paydasina orantilidir
(1:1000 -> 20 m, 1:500 -> 10 m, yani gercek_m = olcek / 50).

Kullanim:
    env/Scripts/python.exe pysrc/parsel_bina/scale.py --scale 1000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from detect_lines import _load_on_white_background

METERS_PER_FOOT_RATIO = 3.28084  # 1 m = 3.28084 ft

# Olcek cubugu tespiti icin renk/sekil esikleri (dolu lacivert dikdortgen)
BAR_COLOR_B_RANGE = (60, 160)
BAR_COLOR_R_MAX = 80
BAR_COLOR_G_MAX = 90
BAR_MIN_AREA = 150
BAR_MIN_WIDTH = 25
BAR_MIN_FILL_RATIO = 0.8
BAR_MIN_ASPECT = 3.0


def scale_to_meters(scale_denominator: float) -> float:
    """IGN kurali: 1:1000 -> 20 m, 1:500 -> 10 m (gercek_m = olcek / 50)."""
    return scale_denominator / 50.0


def detect_scale_bar_px(image: np.ndarray) -> int:
    """Dolu lacivert olcek cubugunun piksel genisligini bulur.

    Metin etiketlerinin anti-aliased kenarlari da benzer renkte
    olabildigi icin sadece genis, dolu (fill_ratio yuksek), yatay
    (aspect>=3) bicimli bilesen kabul edilir.
    """
    b, g, r = image[:, :, 0].astype(int), image[:, :, 1].astype(int), image[:, :, 2].astype(int)
    navy_mask = (
        (b > BAR_COLOR_B_RANGE[0]) & (b < BAR_COLOR_B_RANGE[1]) & (r < BAR_COLOR_R_MAX) & (g < BAR_COLOR_G_MAX)
    ).astype(np.uint8) * 255

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(navy_mask, connectivity=8)
    candidates = []
    for i in range(1, num_labels):
        x, y, w, h, area = stats[i]
        if area < BAR_MIN_AREA or w < BAR_MIN_WIDTH or h == 0:
            continue
        fill_ratio = area / (w * h)
        aspect = w / h
        if fill_ratio >= BAR_MIN_FILL_RATIO and aspect >= BAR_MIN_ASPECT:
            candidates.append(w)

    if not candidates:
        raise RuntimeError("Olcek cubugu tespit edilemedi (renk/sekil esiklerini kontrol edin).")
    return int(max(candidates))


def compute_scale_info(image_path: Path, scale_denominator: float) -> dict:
    image = _load_on_white_background(image_path)
    bar_px = detect_scale_bar_px(image)
    real_meters = scale_to_meters(scale_denominator)
    meters_per_px = real_meters / bar_px
    return {
        "source_image": image_path.as_posix(),
        "scale": scale_denominator,
        "scale_label": f"1:{int(scale_denominator)}",
        "scale_bar_real_meters": real_meters,
        "scale_bar_pixel_length": bar_px,
        "meters_per_pixel": meters_per_px,
        "feet_per_pixel": meters_per_px * METERS_PER_FOOT_RATIO,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Olcek kalibrasyonu (Faz 3)")
    parser.add_argument("--scale", type=float, required=True, help="Harita olcegi paydasi, ör. 1000 (1:1000 icin)")
    parser.add_argument("--image", type=Path, default=None, help="Tek bir goruntu (varsayilan: assets/parsel.png ve assets/bina.png)")
    parser.add_argument("--assets-dir", type=Path, default=Path("assets"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    images = [args.image] if args.image else sorted(args.assets_dir.glob("*.png"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for image_path in images:
        info = compute_scale_info(image_path, args.scale)
        out_path = args.output_dir / f"{image_path.stem}_scale.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        print(
            f"[{image_path.stem}] olcek={info['scale_label']} "
            f"cubuk={info['scale_bar_pixel_length']}px = {info['scale_bar_real_meters']}m "
            f"-> {info['meters_per_pixel']:.5f} m/px -> {out_path}"
        )


if __name__ == "__main__":
    main()
