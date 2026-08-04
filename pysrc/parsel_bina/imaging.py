"""
pyKalfa / Parsel-Bina - katman renkleri: hangi piksel neye ait?

Is akisi UC gorsel alir; ucu de ayni kadastro kesitinin ayni cizim
motorundan gelen ciktilaridir ve her katman KENDI sabit rengiyle cizilir:

    bina cizgisi   -> parlak kirmizi   BGR (0, 0, ~230)
    parsel cizgisi -> koyu kirmizi     BGR (0, 0, ~115)
    parsel etiketi -> notr siyah/gri   (R ~ G ~ B)
    kuzey oku, olcek cubugu, kunye -> lacivert BGR (~131, ~85, ~39)

Bu modul "hangi renk hangi katman" bilgisini TEK yerde tutar; geometry,
scale, ocr_labels ve align hep buradan maske ister. Daha once bu ayrim
her modulde ayri esiklerle tekrarlaniyordu (bina icin grayscale esikleme +
sagolcum ayiklama, parsel icin baska bir "kirmizimsi" marji), ki bu hem
tekrar hem de tutarsizlik kaynagiydi: iki kirmizi ayni "kirmizimsi"
esigini gectigi icin `both.png` gibi IKI katmani birden iceren bir
goruntude birbirinden ayrilamiyorlardi.

## Neden HAM piksel, beyaz zemine duzlestirilmis goruntu degil

Kaynak PNG'lerde anti-alias RGB kanalina degil ALFA kanalina yazilir:
cizginin kenarindaki piksel de tam doymus renktedir (0,0,115), sadece
opakligi duser. Goruntu once beyaz zemine duzlestirilirse yari saydam bir
KOYU kirmizi piksel beyaza dogru acilir --

    alfa 0.3 -> R = 255*0.7 + 115*0.3 = 213, G = B = 255*0.7 = 178

-- yani parlak kirmizi esigini gecip "bina" sanilir. Bu yuzden katman
maskeleri her zaman HAM BGR uzerinden, alfa kanaliyla kapili olarak
uretilir. Duzlestirilmis goruntu yalnizca onizleme ve OCR icindir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Bu esigin altindaki alfa anti-alias/gurultu sayilir, katmana dahil edilmez.
ALPHA_MIN = 16

# R kanali B/G'nin en az bu kadar uzerindeyse piksel "kirmizi ailesinden"dir
# (bina ya da parsel). Lacivert sagolcumlerde bu fark negatiftir, notr
# metinde sifirdir; ikisi de bu esikle bastan disarida kalir.
RED_DOMINANCE_MIN = 40

# Kirmizi ailesi ikiye ayrilir: bina ~230, parsel ~115. Esik ortada secilir,
# iki tarafa da ~55 tonluk pay birakir -- ayni cizim motorunun ciktilarinda
# bu tonlar sabit oldugu icin fazlasiyla yeterli. (Iki cizgi kesistiginde
# aradaki anti-alias pikselleri esigin bir tarafina duser; bir piksellik bu
# belirsizlik iskeletlestirme ile zaten ortadan kalkar.)
BUILDING_RED_MIN = 170

# B kanali G/R'nin en az bu kadar uzerindeyse "lacivert sagolcum".
BLUE_DOMINANCE_MIN = 20

# Notr (metin) piksel olcutu: kanallar birbirine bu kadar yakin ve piksel
# beyaz degil.
TEXT_NEUTRAL_TOLERANCE = 10
TEXT_MAX_BRIGHTNESS = 200


@dataclass
class LayerMasks:
    """Bir goruntunun katman maskeleri (hepsi 0/255 uint8, ayni boyutta)."""

    building: np.ndarray
    parcel: np.ndarray
    decoration: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return self.building.shape[:2]


def read_raw(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """PNG'yi HAM haliyle okur: `(bgr_int16, opak_bool)`.

    Alfa kanali yoksa butun pikseller opak sayilir (duz BGR/gri girdiler
    de kabul edilsin diye)."""
    raw = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Goruntu okunamadi: {image_path}")

    if raw.ndim == 2:
        raw = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    if raw.shape[2] == 4:
        return raw[:, :, :3].astype(np.int16), raw[:, :, 3] > ALPHA_MIN
    return raw.astype(np.int16), np.ones(raw.shape[:2], dtype=bool)


def load_on_white(image_path: Path) -> np.ndarray:
    """PNG'yi beyaz zemin uzerine duzlestirip BGR olarak dondurur.

    Kaynak gorsellerde seffaf pikseller RGB=(0,0,0) olarak saklanir; alfayi
    yok sayip dogrudan BGR okumak zemini siyaha cevirir.

    SADECE onizleme ve OCR icin kullanilir -- katman ayrimi icin degil
    (bkz. modul docstring'i)."""
    raw = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Goruntu okunamadi: {image_path}")
    if raw.ndim == 2:
        return cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    if raw.shape[2] == 3:
        return raw

    bgr, alpha = raw[:, :, :3], raw[:, :, 3:4].astype(np.float32) / 255.0
    white = np.full_like(bgr, 255, dtype=np.float32)
    return (bgr.astype(np.float32) * alpha + white * (1 - alpha)).astype(np.uint8)


def layer_masks(image_path: Path) -> LayerMasks:
    """Goruntunun bina/parsel/sagolcum maskelerini birlikte uretir.

    Ucu de ayni ham okumadan turedigi icin bir goruntu icin bir kez
    cagirmak yeterlidir; `both.png` gibi iki katmani birden iceren bir
    goruntude de dogru calisir -- ayrim renk tonundadir, katmanin hangi
    dosyada oldugunda degil."""
    bgr, opaque = read_raw(image_path)
    b, g, r = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]

    red_family = opaque & ((r - np.maximum(b, g)) > RED_DOMINANCE_MIN)
    bluish = opaque & ((b - np.maximum(g, r)) > BLUE_DOMINANCE_MIN)

    to_mask = lambda m: m.astype(np.uint8) * 255
    return LayerMasks(
        building=to_mask(red_family & (r >= BUILDING_RED_MIN)),
        parcel=to_mask(red_family & (r < BUILDING_RED_MIN)),
        decoration=to_mask(bluish),
    )


def building_mask(image_path: Path) -> np.ndarray:
    return layer_masks(image_path).building


def parcel_mask(image_path: Path) -> np.ndarray:
    return layer_masks(image_path).parcel


def decoration_mask(image_path: Path) -> np.ndarray:
    return layer_masks(image_path).decoration


def text_image(image_path: Path) -> np.ndarray:
    """Yalniz notr (siyah/gri) metin piksellerini beyaz zemine bindirir.

    OCR girdisi budur: parsel agi, bina cizgileri, kuzey oku ve olcek
    cubugu (hicbiri notr degil) bastan disarida kalir. Burada -- katman
    maskelerinin aksine -- duzlestirilmis goruntu kullanilir; metin zaten
    opak ve notrdur, OCR'a da gri tonlamali bir goruntu vermek gerekir.
    """
    image = load_on_white(image_path)
    b = image[:, :, 0].astype(np.int16)
    g = image[:, :, 1].astype(np.int16)
    r = image[:, :, 2].astype(np.int16)
    neutral = (
        (np.abs(r - g) < TEXT_NEUTRAL_TOLERANCE)
        & (np.abs(g - b) < TEXT_NEUTRAL_TOLERANCE)
        & (r < TEXT_MAX_BRIGHTNESS)
    )
    return np.where(neutral[:, :, None], image, np.full_like(image, 255))


def main() -> None:
    """Tani: her goruntude hangi katmandan kac piksel var."""
    import argparse

    parser = argparse.ArgumentParser(description="Katman maskesi piksel sayimi (tani/debug amacli)")
    parser.add_argument("images", nargs="*", type=Path,
                        default=[Path("assets/bina.png"), Path("assets/parsel.png"), Path("assets/both.png")])
    args = parser.parse_args()

    for image_path in args.images:
        masks = layer_masks(image_path)
        print("{:<24} bina={:>7} parsel={:>7} sagolcum={:>6}".format(
            image_path.name,
            int((masks.building > 0).sum()),
            int((masks.parcel > 0).sum()),
            int((masks.decoration > 0).sum()),
        ))


if __name__ == "__main__":
    main()
