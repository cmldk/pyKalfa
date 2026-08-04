"""
pyKalfa / Parsel-Bina - olcek kalibrasyonu

Kullanici haritanin basim olcegini (ör. 1:1000 icin --scale 1000) verir;
goruntudeki olcek cubugunun piksel uzunlugu renk+sekil bazli otomatik
tespit edilir (OCR yok, bkz. map_decorations.detect_scale_bar_px). IGN
kadastro kurali geregi olcek cubugunun gercek dunya karsiligi olcek
paydasina orantilidir (1:1000 -> 20 m, 1:500 -> 10 m, yani
gercek_m = olcek / 50).

Olcek TEK bir goruntuden bir kez hesaplanip butun katmanlara uygulanir:
uc gorsel de ayni gorunumun ciktisi oldugu icin m/px orani ortaktir, ama
her katman icin ayri ayri cubuk olcmek anti-alias kaynakli 1 piksellik
farklarla katmanlar arasinda tutarsiz bir olcege yol acardi.

Kullanim:
    env/Scripts/python.exe pysrc/parsel_bina/scale.py --scale 500
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from map_decorations import detect_scale_bar_px

METERS_PER_FOOT_RATIO = 3.28084  # 1 m = 3.28084 ft


def scale_to_meters(scale_denominator: float) -> float:
    """IGN kurali: 1:1000 -> 20 m, 1:500 -> 10 m (gercek_m = olcek / 50)."""
    return scale_denominator / 50.0


def compute_scale_info(image_path: Path, scale_denominator: float) -> dict:
    bar_px = detect_scale_bar_px(image_path)
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
    parser = argparse.ArgumentParser(description="Olcek kalibrasyonu")
    parser.add_argument("--scale", type=float, required=True, help="Harita olcegi paydasi, ör. 500 (1:500 icin)")
    parser.add_argument("--image", type=Path, default=Path("assets/parsel.png"))
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Verilirse sonuc ayrica <stem>_scale.json olarak yazilir")
    args = parser.parse_args()

    info = compute_scale_info(args.image, args.scale)
    print(
        f"[{args.image.stem}] olcek={info['scale_label']} "
        f"cubuk={info['scale_bar_pixel_length']}px = {info['scale_bar_real_meters']}m "
        f"-> {info['meters_per_pixel']:.5f} m/px"
    )
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = args.output_dir / f"{args.image.stem}_scale.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        print(f"-> {out_path}")


if __name__ == "__main__":
    main()
