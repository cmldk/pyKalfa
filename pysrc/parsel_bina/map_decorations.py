"""
pyKalfa / Parsel-Bina - harita sagolcumleri: kuzey oku, olcek cubugu, kunye

Kadastro kesitinin uzerinde parsel/bina geometrisine AIT OLMAYAN birkac
sagolcum bulunur: kuzey oku, olcek cubugu, "20 m" ve kunye yazisi. Hepsi
lacivert tonundadir; parsel cizgileri kirmizimsi, bina cizgileri kirmizi,
parsel numaralari ise notr gri/siyahtir. Yani renk, bu ogeleri geometriden
ayirmak icin yeterli ve basit bir olcuttur.

Parsel katmani (renk bazli kirmizimsi maske) ve OCR (notr renk maskesi)
bu ogeleri zaten disarida birakiyordu; bina katmani ise grayscale esikleme
kullandigi icin kuzey okunu ve olcek cubugunu "bina" sanıyordu. Bu modul o
ayiklamayi tek yerde toplar.

Kuzey oku ayrica ISE YARAR bir bilgidir: konumu ve yonu olculup Revit'e
bir aciklama sembolu (annotation symbol) olarak birebir ayni yonde
yerlestirilebilir.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from detect_lines import _load_on_white_background

# B kanali G/R'nin en az bu kadar uzerindeyse "lacivert sagolcum" sayilir.
BLUISH_CHANNEL_MARGIN = 20

# Sagolcumlerin anti-alias kenarlari lacivert esigini gecemeyecek kadar
# aciktir ama grayscale maskede hala "cizgi" sayilir; maskeden silerken bu
# kadar piksel genisletilir ki geride ok bicimli bir halka kalmasin.
DECORATION_DILATION_PX = 2

# Sagolcum haritanin ustunu ORTER: olcek cubugunun altindan gecen bina
# cizgisi kaynak goruntude zaten yoktur, silme sonrasi o cizgide bir
# kopukluk kalir ve bina kapanmaz. Silinen bandin ICINDE bu yaricapla
# morfolojik kapama yapilarak kopukluk kopruleni r (bandin disina
# dokunulmaz). Bandin kalinligindan (cubuk ~10 px + genisletme) buyuk
# olmalidir.
DECORATION_BRIDGE_PX = 8

# Kuzey oku adayi icin en kucuk bilesen alani (px). Altindakiler "20 m"/"N"
# gibi metin parcalari ya da gurultudur.
MIN_ARROW_AREA = 150

# Olcek cubugu: dolu (fill ~1) ve uzun/ince bir dikdortgen. Kuzey oku
# adaylarindan bu olcutle elenir.
BAR_MIN_FILL_RATIO = 0.9
BAR_MIN_ASPECT = 3.0


def decoration_mask(image: np.ndarray) -> np.ndarray:
    """Lacivert sagolcum (kuzey oku, olcek cubugu, kunye) piksellerinin
    ikili maskesi."""
    b = image[:, :, 0].astype(np.int16)
    g = image[:, :, 1].astype(np.int16)
    r = image[:, :, 2].astype(np.int16)
    return ((b - np.maximum(g, r)) > BLUISH_CHANNEL_MARGIN).astype(np.uint8) * 255


def strip_decorations(image: np.ndarray, line_mask: np.ndarray) -> np.ndarray:
    """Cizgi maskesinden harita sagolcumlerini siler.

    Lacivert cekirdek maskesi `DECORATION_DILATION_PX` kadar genisletilerek
    cikarilir: cekirdegi oldugu gibi cikarmak, sagolcumun anti-alias
    kenarindan geriye ayni bicimde ince bir halka birakir ve o halka bir
    sonraki adimda "bina" olarak konturlanir.

    Sagolcum haritanin ustunu ORTTUGU icin altindan gecen bina cizgisi de
    silinmis olur; bu yuzden silinen bandin icinde morfolojik kapama ile
    kopukluk kopruleni r. Kapama SADECE bandin icine yazilir -- haritanin
    geri kalaninda cizgileri kalinlastirip komsu binalari birbirine
    yapistirmamasi icin.
    """
    decorations = decoration_mask(image)
    if DECORATION_DILATION_PX > 0:
        size = 2 * DECORATION_DILATION_PX + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        decorations = cv2.dilate(decorations, kernel)

    cleaned = line_mask.copy()
    band = decorations > 0
    cleaned[band] = 0

    if DECORATION_BRIDGE_PX > 0:
        size = 2 * DECORATION_BRIDGE_PX + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        bridged = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
        cleaned[band] = bridged[band]
    return cleaned


def detect_north_arrow(image_path: Path) -> dict | None:
    """Kuzey okunun piksel merkezini ve gosterdigi yonu bulur.

    Aday: lacivert bilesenlerin en buyugu; olcek cubugu (dolu, uzun/ince
    dikdortgen) elenir. Yon, bilesenin ana ekseni (PCA) uzerinde merkeze
    EN UZAK ucun yonudur -- ucgen/ok bicimlerinde tepe noktasi merkeze
    tabandan daha uzaktir (ucgende 2/3h'ye karsi 1/3h), bu yuzden bu olcut
    "kutle agirligi" gibi olculere gore bicime daha az duyarlidir.

    `rotation_deg`: yukari bakan bir sembolun ayni yone donmesi icin
    gereken aci (CCW pozitif, Revit'in Z ekseni etrafinda donusuyle ayni).
    Ok bulunamazsa None doner.
    """
    image = _load_on_white_background(image_path)
    mask = decoration_mask(image)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    best = None
    best_area = 0
    for label_id in range(1, num_labels):
        _, _, w, h, area = stats[label_id]
        if area < MIN_ARROW_AREA:
            continue
        fill_ratio = area / float(w * h)
        aspect = max(w, h) / float(max(min(w, h), 1))
        if fill_ratio > BAR_MIN_FILL_RATIO and aspect >= BAR_MIN_ASPECT:
            continue  # olcek cubugu
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

    parser = argparse.ArgumentParser(description="Kuzey oku tespiti (tani/debug amacli)")
    parser.add_argument("--image", type=Path, default=Path("assets/parsel.png"))
    args = parser.parse_args()

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
