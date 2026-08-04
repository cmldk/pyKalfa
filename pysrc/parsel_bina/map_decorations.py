"""
pyKalfa / Parsel-Bina - harita sagolcumleri: kuzey oku ve olcek cubugu

Kadastro kesitinin uzerinde geometriye AIT OLMAYAN birkac sagolcum
bulunur: kuzey oku, olcek cubugu, "10 m" ve kunye yazisi. Hepsi lacivert
tonundadir (bkz. imaging.py), yani renk bu ogeleri geometriden ayirmak
icin yeterli ve basit bir olcuttur -- geometri maskeleri onlari zaten hic
icermez.

Ikisi de ISE YARAR bilgidir, bu yuzden ayiklanmakla kalmaz olculur de:

  - kuzey oku -> konumu ve yonu; Revit'te projenin KENDI kuzey oku
    sembolu ayni yone cevrilerek yerlestirilir.
  - olcek cubugu -> piksel uzunlugu; olcek kalibrasyonunun temeli
    (bkz. scale.py).

Ikisi de ayni lacivert bilesen kumesinden gelir ve birbirinden SEKILLE
ayrilir: olcek cubugu dolu (fill ~1), uzun ve ince bir dikdortgendir; ok
degildir. Bu yuzden ikisinin tespiti tek modulde durur -- ayri modullerde
olduklarinda ayni renk esikleri iki kez, birbirinden bagimsiz sekilde
tanimlanmis oluyordu.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from imaging import decoration_mask

# Olcek cubugu olcutu: dolu, uzun/ince, yeterince genis bir dikdortgen.
BAR_MIN_FILL_RATIO = 0.8
BAR_MIN_ASPECT = 3.0
BAR_MIN_WIDTH = 25
BAR_MIN_AREA = 150

# Kuzey oku adayi icin en kucuk bilesen alani (px). Altindakiler "10 m"/"N"
# gibi metin parcalari ya da gurultudur.
MIN_ARROW_AREA = 150


def _components(image_path: Path):
    mask = decoration_mask(image_path)
    return cv2.connectedComponentsWithStats(mask, connectivity=8)


def _is_scale_bar(width: int, height: int, area: int) -> bool:
    if area < BAR_MIN_AREA or width < BAR_MIN_WIDTH or height == 0:
        return False
    return (area / float(width * height)) >= BAR_MIN_FILL_RATIO and (width / float(height)) >= BAR_MIN_ASPECT


def detect_scale_bar_px(image_path: Path) -> int:
    """Dolu lacivert olcek cubugunun piksel genisligini bulur.

    Metin parcalari ve kuzey oku sekil olcutuyle elenir; birden fazla aday
    kalirsa en genisi alinir (cubuk, kunye harflerinden her zaman uzundur).
    """
    num_labels, _, stats, _ = _components(image_path)
    widths = [
        stats[i, cv2.CC_STAT_WIDTH]
        for i in range(1, num_labels)
        if _is_scale_bar(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_AREA])
    ]
    if not widths:
        raise RuntimeError(
            "Olcek cubugu tespit edilemedi: goruntude lacivert, dolu ve uzun bir "
            "cubuk bulunamadi. Kaynak gorsel olcek cubugunu iceriyor mu?"
        )
    return int(max(widths))


def detect_north_arrow(image_path: Path) -> dict | None:
    """Kuzey okunun piksel merkezini ve gosterdigi yonu bulur.

    Aday: olcek cubugu elendikten sonra kalan en buyuk lacivert bilesen.
    Yon, bilesenin ana ekseni (PCA) uzerinde merkeze EN UZAK ucun
    yonudur -- ucgen/ok bicimlerinde tepe noktasi merkeze tabandan daha
    uzaktir (ucgende 2/3h'ye karsi 1/3h), bu yuzden bu olcut "kutle
    agirligi" gibi olculere gore bicime daha az duyarlidir.

    `rotation_deg`: yukari bakan bir sembolun ayni yone donmesi icin
    gereken aci (CCW pozitif, Revit'in Z ekseni etrafinda donusuyle ayni).
    Ok bulunamazsa None doner.
    """
    num_labels, labels, stats, _ = _components(image_path)

    best, best_area = None, 0
    for label_id in range(1, num_labels):
        _, _, w, h, area = stats[label_id]
        if area < MIN_ARROW_AREA or _is_scale_bar(w, h, area):
            continue
        if area > best_area:
            best, best_area = label_id, area
    if best is None:
        return None

    ys, xs = np.where(labels == best)
    cx, cy = float(xs.mean()), float(ys.mean())
    centered = np.stack([xs - cx, ys - cy]).astype(np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov(centered))
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]

    projection = centered[0] * axis[0] + centered[1] * axis[1]
    tip = axis if projection.max() >= -projection.min() else -axis

    # Piksel Y-ekseni asagi artar; dunya (Revit) ekseninde yukari cevrilir.
    vx, vy = float(tip[0]), -float(tip[1])
    rotation_deg = math.degrees(math.atan2(-vx, vy))
    return {
        "center_px": (cx, cy),
        "rotation_deg": round(rotation_deg, 2),
        "pixel_area": int(best_area),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Kuzey oku / olcek cubugu tespiti (tani/debug amacli)")
    parser.add_argument("--image", type=Path, default=Path("assets/parsel.png"))
    args = parser.parse_args()

    try:
        print("Olcek cubugu: {} px".format(detect_scale_bar_px(args.image)))
    except RuntimeError as ex:
        print("Olcek cubugu: {}".format(ex))

    arrow = detect_north_arrow(args.image)
    if arrow is None:
        print("Kuzey oku bulunamadi.")
        return
    print(
        "Kuzey oku: merkez=({:.0f}, {:.0f}) px, donus={:+.1f} derece, alan={} px".format(
            arrow["center_px"][0], arrow["center_px"][1], arrow["rotation_deg"], arrow["pixel_area"]
        )
    )


if __name__ == "__main__":
    main()
