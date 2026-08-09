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
ayrilir: olcek cubugu uzun, ince ve UCTAN UCA kesintisizdir; ok degildir.
Bu yuzden ikisinin tespiti tek modulde durur -- ayri modullerde
olduklarinda ayni renk esikleri iki kez, birbirinden bagimsiz sekilde
tanimlanmis oluyordu.

## Cubuk olcutu neden "dolu dikdortgen" degil

Cizim motorunun surumune gore olcek cubugu iki bicimde gelir: yeni
ciktilarda ici dolu bir dikdortgen (doluluk ~1.0), eski ciktilarda ise
iki ucunda dikey tirnak olan ince bir cizgi -- yani bir "I" kirisi
(doluluk ~0.25). Doluluk orani bu ikisini ayni esikte tutamaz; dahasi
metin parcalarinin dolulugu (~0.3-0.5) I kirisininkinden YUKSEK oldugu
icin bu olcut ayirt edici bile degildir.

Iki bicimin de ortak ozelligi, kunye harflerinin hicbirinde bulunmayan
sudur: cubugun govdesi bastan sona TEK bir kesintisiz yatay diziden
gecer. Olcut bu yuzden en uzun yatay dizinin genislige oranidir
(bkz. BAR_MIN_SPAN_RATIO).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from imaging import decoration_mask

# Olcek cubugu olcutu: uzun, ince ve uctan uca kesintisiz.
BAR_MIN_ASPECT = 3.0
BAR_MIN_WIDTH = 25
# En uzun kesintisiz yatay dizi, bilesen genisliginin en az bu kadari
# olmali. Olculen degerler: dolu cubuk 1.00, I kirisi 0.99; en yakin
# yanlis aday (kuzey oku) 0.90, kunye harfleri <= 0.6.
BAR_MIN_SPAN_RATIO = 0.95

# Kuzey oku adayi icin en kucuk bilesen alani (px). Altindakiler "10 m"/"N"
# gibi metin parcalari ya da gurultudur.
MIN_ARROW_AREA = 150


def _longest_row_run(pixels: np.ndarray) -> int:
    """Bilesenin en uzun kesintisiz yatay piksel dizisinin uzunlugu."""
    best = 0
    for row in pixels:
        gaps = np.flatnonzero(~row)
        edges = np.concatenate(([-1], gaps, [row.size]))
        best = max(best, int(np.diff(edges).max()) - 1)
    return best


@dataclass(frozen=True)
class _Component:
    """Sagolcum maskesinin tek bir baglantili bileseni."""

    x: int
    y: int
    width: int
    height: int
    area: int
    pixels: np.ndarray  # bbox boyutunda bool maske

    @property
    def is_scale_bar(self) -> bool:
        if self.width < BAR_MIN_WIDTH or self.height == 0:
            return False
        if (self.width / float(self.height)) < BAR_MIN_ASPECT:
            return False
        return _longest_row_run(self.pixels) >= BAR_MIN_SPAN_RATIO * self.width


def _components(image_path: Path) -> list[_Component]:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        decoration_mask(image_path), connectivity=8
    )
    components = []
    for label_id in range(1, num_labels):
        x, y, w, h, area = (int(v) for v in stats[label_id])
        components.append(_Component(x, y, w, h, area, labels[y:y + h, x:x + w] == label_id))
    return components


def detect_scale_bar_px(image_path: Path) -> int:
    """Lacivert olcek cubugunun piksel genisligini bulur.

    Metin parcalari ve kuzey oku sekil olcutuyle elenir; birden fazla aday
    kalirsa en genisi alinir (cubuk, kunye harflerinden her zaman uzundur).
    """
    widths = [c.width for c in _components(image_path) if c.is_scale_bar]
    if not widths:
        raise RuntimeError(
            "Olcek cubugu tespit edilemedi: goruntude lacivert, uzun ve uctan uca "
            "kesintisiz bir cubuk bulunamadi. Kaynak gorsel olcek cubugunu iceriyor mu?"
        )
    return max(widths)


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
    candidates = [c for c in _components(image_path) if c.area >= MIN_ARROW_AREA and not c.is_scale_bar]
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c.area)

    ys, xs = np.nonzero(best.pixels)
    xs, ys = xs + best.x, ys + best.y
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
        "pixel_area": best.area,
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
