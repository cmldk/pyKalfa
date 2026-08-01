"""
pyKalfa / Parsel-Bina - Faz 2: parsel-bina iliskilendirme

parsel.png ve bina.png ayni piksel boyutuna sahip oldugu icin (ayni kadastro
kesitinin iki katmani), ekstra bir hizalama/donusum islemine gerek yok: her
iki goruntudeki piksel koordinatlari zaten ortak bir referans sistemindedir.
Bu script:

  1. Her iki katman icin geometry.py'nin katman-bazli temiz kontur
     cikarimini kullanir (Faz 3: parsel icin "hole", bina icin "external"
     modu -- cift kontur/artefakt sorunu olmadan).
  2. Her binanin agirlik merkezini (centroid) hesaplayip hangi parsel
     konturunun icinde kaldigini (point-in-polygon) bulur.
  3. Sonucu tek bir birlesim (union) gorseli olarak ve JSON eslesme
     dosyasi olarak output/ klasorune yazar.

Kullanim:
    env/Scripts/python.exe pysrc/parsel_bina/associate.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from geometry import extract_buildings, extract_parcels

# ---------------------------------------------------------------------------
# Ayarlanabilir parametreler
# ---------------------------------------------------------------------------

PARCEL_COLOR = (0, 140, 255)     # BGR - turuncu
BUILDING_COLOR = (255, 120, 0)   # BGR - mavi
MATCHED_FILL = (0, 200, 0)       # BGR - yesil (eslesen bina ic dolgusu)
UNMATCHED_FILL = (0, 0, 220)     # BGR - kirmizi (eslesmeyen bina ic dolgusu)
FILL_ALPHA = 0.35
LINE_THICKNESS = 2


def _centroid(contour: np.ndarray) -> tuple[float, float]:
    m = cv2.moments(contour)
    if m["m00"] != 0:
        return m["m10"] / m["m00"], m["m01"] / m["m00"]
    x, y, w, h = cv2.boundingRect(contour)
    return x + w / 2.0, y + h / 2.0


def associate(parsel_path: Path, bina_path: Path, output_dir: Path) -> None:
    parcel_image, parcels = extract_parcels(parsel_path)
    building_image, buildings = extract_buildings(bina_path)

    if parcel_image.shape[:2] != building_image.shape[:2]:
        raise ValueError(
            f"Goruntu boyutlari eslesmiyor: parsel={parcel_image.shape[:2]} "
            f"bina={building_image.shape[:2]}. Ortak piksel referansi varsayimi bozulur."
        )
    height, width = parcel_image.shape[:2]

    # En kucuk kapsayan parsel = en spesifik eslesme
    parcels = sorted(parcels, key=cv2.contourArea)

    parcel_to_buildings: dict[int, list[int]] = {i: [] for i in range(len(parcels))}
    building_matches: list[dict] = []

    for b_idx, b_contour in enumerate(buildings):
        cx, cy = _centroid(b_contour)
        matched_parcel = None
        for p_idx, p_contour in enumerate(parcels):
            if cv2.pointPolygonTest(p_contour, (cx, cy), False) >= 0:
                matched_parcel = p_idx
                break
        if matched_parcel is not None:
            parcel_to_buildings[matched_parcel].append(b_idx)
        building_matches.append(
            {
                "building_id": b_idx,
                "centroid_px": [round(cx, 1), round(cy, 1)],
                "area_px": round(cv2.contourArea(b_contour), 1),
                "parcel_id": matched_parcel,
            }
        )

    # --- Birlesim (union) gorseli -------------------------------------------------
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.drawContours(canvas, parcels, -1, PARCEL_COLOR, LINE_THICKNESS)

    overlay = canvas.copy()
    for b_idx, b_contour in enumerate(buildings):
        fill = MATCHED_FILL if building_matches[b_idx]["parcel_id"] is not None else UNMATCHED_FILL
        cv2.drawContours(overlay, [b_contour], -1, fill, cv2.FILLED)
    canvas = cv2.addWeighted(overlay, FILL_ALPHA, canvas, 1 - FILL_ALPHA, 0)
    cv2.drawContours(canvas, buildings, -1, BUILDING_COLOR, LINE_THICKNESS)

    output_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_dir / "parsel_bina_birlesim.png"), canvas)

    matched_count = sum(1 for b in building_matches if b["parcel_id"] is not None)
    result = {
        "image_size": {"width": width, "height": height},
        "parcel_count": len(parcels),
        "building_count": len(buildings),
        "matched_building_count": matched_count,
        "unmatched_building_count": len(buildings) - matched_count,
        "parcels": [
            {
                "parcel_id": p_idx,
                "area_px": round(cv2.contourArea(p_contour), 1),
                "building_ids": b_ids,
            }
            for p_idx, (p_contour, b_ids) in enumerate(zip(parcels, parcel_to_buildings.values()))
        ],
        "buildings": building_matches,
    }
    with open(output_dir / "parsel_bina_eslesme.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        f"Parsel: {len(parcels)}, Bina: {len(buildings)}, "
        f"eslesen: {matched_count}, eslesmeyen: {len(buildings) - matched_count} "
        f"-> {output_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parsel-bina iliskilendirme (Faz 2)")
    parser.add_argument("--parsel", type=Path, default=Path("assets/parsel.png"))
    parser.add_argument("--bina", type=Path, default=Path("assets/bina.png"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    associate(args.parsel, args.bina, args.output_dir)


if __name__ == "__main__":
    main()
