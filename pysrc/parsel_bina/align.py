"""
pyKalfa / Parsel-Bina - iki katmani `both.png` uzerinden hizalama

Kullanici UC gorsel verir: `bina.png` (yalniz binalar), `parsel.png`
(yalniz parseller + etiketler) ve `both.png` (ikisi ust uste). Ilk ikisi
geometrinin KAYNAGIDIR, ucuncusu ise yalniz HIZALAMA referansidir.

## Neden ucuncu bir gorsel gerekli

`bina.png` ile `parsel.png` ayni haritanin iki katmani olsa da ayri ayri
disa aktarilir; kullanici arada haritayi kaydirirsa (ya da disa aktarim
gorunumu birebir ayni kadraja oturtmazsa) iki gorsel ayni piksel
boyutunda olmasina ragmen ayni yeri gostermez. Boyle bir durumda "iki
goruntu zaten hizali" varsayimiyla yapilan parsel-bina eslesmesi sessizce
yanlis sonuc verir: binalar komsu parsele kayar. Bu, ciktida hic hata
gibi gorunmez -- en tehlikeli hata turu.

`both.png` iki katmani TEK bir kadrajda tasidigi icin bu sorunun cevabini
kendi icinde barindirir: her katman kendi kaynagindan `both.png`'ye
ayri ayri hizalanir, aradaki fark da katmanlar arasi gercek kaymadir:

    bina -> parsel kaymasi = (bina -> both) - (parsel -> both)

`both.png`'nin kendi kadraji hic kullanilmaz; sadece ortak referans
gorevi gorur. Cikti karesi eskisi gibi `parsel.png`'dir (olcek cubugu,
kuzey oku, etiketler ve cerceve hep oradan gelir).

## Neden geometri `both.png`'den okunmuyor

`both.png` iki katmani birden tasidigi icin ilk bakista tek basina
yeterliymis gibi gorunur, ama katmanlar birbirinin uzerine cizilir:
parsel cizgileri ve siyah etiketler bina cizgisinin GOVDESINDE delikler
acar (olculdu: ayni bolgede `bina.png` cizgileri kesintisiz, `both.png`
karsiliklari kopuk). Kopuk bir cizgi de kapanmayan bir bina demektir.
Ayni sekilde binalarin altinda kalan parsel cizgileri `both.png`'de
gorunmez. Bu yuzden geometri her zaman kendi TEK katmanli kaynagindan
okunur.

## Yontem

Hizalama saf otelemedir (donme/olcek degisimi beklenmez -- ayni haritanin
ayni yakinlastirmada iki cikti): `cv2.phaseCorrelate` ile alt-piksel
oteleme bulunur, ardindan bulunan oteleme UYGULANIP katmanlarin birbirini
ne kadar kapsadigi olculerek dogrulanir (bkz. `_coverage`). Faz
korelasyonunun kendi "yanit" degeri tek basina guvenilir degildir;
oteleme uygulandiktan sonraki gercek ortusme, hizalamanin tutup
tutmadiginin dogrudan olcusudur.

Dogrulama basarisiz olursa (ör. kullanici `both.png` yerine baska bir
kadraj/yakinlastirma verdiyse) hizalama REDDEDILIR: kayma sifir kabul
edilip cagirana bir uyari dondurulur. Sessizce yanlis bir kaymayi
uygulamaktansa "hizalanamadi" demek dogrudur -- iki gorsel zaten cogu
zaman hizalidir, sifir kayma en az zararli varsayimdir.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from imaging import layer_masks

# Oteleme uygulandiktan sonra beklenen en dusuk kapsama (bkz. `_coverage`).
# Olculdu: dogru kaymada iki katmanda da >= 0.99; %5 yanlis yakinlastirilmis
# bir `both.png`de ise <= 0.47. Esik ikisinin arasinda secildi.
MIN_OVERLAP = 0.7

# Kapsama olculurken bu kadar piksellik konum farki "ayni cizgi" sayilir:
# ayni cizim iki gorselde birebir ayni kalinlikta cizilmez (olculdu: bina
# cizgisi `bina.png`'de ~10 px, `both.png`'de ~5 px) ve anti-alias kenarlari
# bir piksel oynayabilir.
ALIGN_TOLERANCE_PX = 2

# Faz korelasyonunun bundan kucuk otelemeleri gurultu sayilir ve "zaten
# hizali" kabul edilir (olculdu: hizali ornek gorsellerde 0.45 px).
MIN_SHIFT_PX = 0.5

# Bir katmanin hizalanabilmesi icin her iki goruntude de en az bu kadar
# piksel bulunmali; altindaysa olcum anlamsizdir (ör. bos/yanlis dosya).
MIN_LAYER_PIXELS = 500


def _hann_window(shape: tuple[int, int]) -> np.ndarray:
    """2B Hann penceresi.

    Faz korelasyonu goruntuyu dongusel varsayar; kenarlardaki ani kesilme
    frekans uzayinda cizgi bicimli guclu bir artefakt uretir ve tepe
    noktasini kaydirabilir. Pencere kenarlari yumusatarak bunu onler."""
    height, width = shape
    return np.outer(np.hanning(height), np.hanning(width))


def _coverage(
    source: np.ndarray, target: np.ndarray, occluder: np.ndarray, dx: float, dy: float
) -> float:
    """`source` (dx, dy) kadar otelendiginde `target` ile ne kadar ortusuyor?

    IoU (kesisim/birlesim) bu is icin yanlis olcuttu. `both.png`'de bir
    katman digerinin ALTINDA kalir: binalarin altindaki parsel cizgileri
    orada hic yoktur, yani dogru kaymada bile birlesim kesisimden cok
    buyuktur. Olculdu: dogru bulunan kaymada parsel IoU'su 0.22 cikti,
    esigin altinda kaldigi icin hizalama reddedildi ve binalar parsellere
    gore ~2 m kaymis cizildi.

    Bunun yerine kapsama iki yonlu, yalnizca DIGER katmanin (`occluder`)
    ortmedigi yerlerde ve `ALIGN_TOLERANCE_PX` payla olculur:

      - hedefin piksellerinin ne kadari otelenmis kaynakta var,
      - otelenmis kaynagin piksellerinin ne kadari hedefte var.

    Kucugu doner. Iki yon birlikte sart: tek yonlu kapsama, yogun bir
    katmanin seyrek bir katmani "kapsamasiyla" yanlis bir kaymayi da
    gecirebilirdi.

    Oteleme kaynagin bir kismini kadraj disina tasir; disari cikan bolge
    her iki maskede de yok sayilir, aksi halde ortusme yapay olarak
    dususurdu."""
    height, width = source.shape[:2]
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    shifted = cv2.warpAffine(source, matrix, (width, height)) > 0

    # Otelemeden sonra kaynak verisinin gercekten bulundugu bant
    valid = np.zeros((height, width), dtype=bool)
    x0, y0 = max(0, int(np.ceil(dx))), max(0, int(np.ceil(dy)))
    x1, y1 = width + min(0, int(np.floor(dx))), height + min(0, int(np.floor(dy)))
    if x0 >= x1 or y0 >= y1:
        return 0.0
    valid[y0:y1, x0:x1] = True

    size = 2 * ALIGN_TOLERANCE_PX + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    visible = valid & ~(cv2.dilate(occluder, kernel) > 0)
    target_px = (target > 0) & visible
    source_px = shifted & visible
    if target_px.sum() < MIN_LAYER_PIXELS or source_px.sum() < MIN_LAYER_PIXELS:
        return 0.0

    near_source = cv2.dilate(shifted.astype(np.uint8), kernel) > 0
    near_target = cv2.dilate((target > 0).astype(np.uint8), kernel) > 0
    explained = (target_px & near_source).sum() / float(target_px.sum())
    found = (source_px & near_target).sum() / float(source_px.sum())
    return float(min(explained, found))


def estimate_offset(
    source: np.ndarray, target: np.ndarray, occluder: np.ndarray
) -> tuple[float, float, float]:
    """`source` maskesini `target`e goturen otelemeyi ve ortusme kalitesini
    dondurur: `(dx, dy, kapsama)`.

    `occluder`, `target` goruntusundeki DIGER katmandir; orttugu yerler
    olcume girmez (bkz. `_coverage`).

    Ortusme, oteleme UYGULANDIKTAN sonra olculur (bkz. modul docstring'i).
    Sifir oteleme ile de karsilastirilir: kayma yoksa faz korelasyonunun
    urettigi gurultulu kucuk bir oteleme kabul edilmesin, "zaten hizali"
    sonucu tercih edilsin diye.
    """
    if (source > 0).sum() < MIN_LAYER_PIXELS or (target > 0).sum() < MIN_LAYER_PIXELS:
        return 0.0, 0.0, 0.0

    window = _hann_window(source.shape[:2])
    a = (source > 0).astype(np.float64) * window
    b = (target > 0).astype(np.float64) * window
    (dx, dy), _ = cv2.phaseCorrelate(a, b)

    identity = _coverage(source, target, occluder, 0.0, 0.0)
    if math.hypot(dx, dy) < MIN_SHIFT_PX:
        return 0.0, 0.0, identity
    measured = _coverage(source, target, occluder, dx, dy)
    if identity > measured:
        return 0.0, 0.0, identity
    return dx, dy, measured


def layer_offset(
    bina_path: Path, parsel_path: Path, both_path: Path
) -> dict:
    """Bina katmanini parsel katmaninin karesine goturen otelemeyi olcer.

    Doner: `offset_px` (bina konturlarina eklenecek (dx, dy)), her iki
    hizalamanin ortusme skoru ve -- hizalama dogrulanamadiysa -- insan
    tarafindan okunabilir bir `warning`.
    """
    bina_layers = layer_masks(bina_path)
    parsel_layers = layer_masks(parsel_path)
    both_layers = layer_masks(both_path)

    shapes = {bina_layers.shape, parsel_layers.shape, both_layers.shape}
    if len(shapes) != 1:
        raise ValueError(
            "Uc goruntu ayni piksel boyutunda olmali; bulunan boyutlar: {}. "
            "Ucu de ayni gorunumden disa aktarilmalidir.".format(sorted(shapes))
        )

    building_dx, building_dy, building_overlap = estimate_offset(
        bina_layers.building, both_layers.building, both_layers.parcel
    )
    parcel_dx, parcel_dy, parcel_overlap = estimate_offset(
        parsel_layers.parcel, both_layers.parcel, both_layers.building
    )

    warning = None
    if building_overlap < MIN_OVERLAP or parcel_overlap < MIN_OVERLAP:
        warning = (
            "both.png ile hizalama dogrulanamadi (ortusme: bina {:.2f}, parsel {:.2f}; "
            "beklenen >= {:.2f}). Katmanlar hizali varsayildi -- bina/parsel eslesmesi "
            "yanlis olabilir. Ucu de AYNI gorunumden disa aktarildigindan emin olun."
        ).format(building_overlap, parcel_overlap, MIN_OVERLAP)
        offset = (0.0, 0.0)
    else:
        offset = (building_dx - parcel_dx, building_dy - parcel_dy)

    return {
        "offset_px": [round(offset[0], 2), round(offset[1], 2)],
        "building_to_both_px": [round(building_dx, 2), round(building_dy, 2)],
        "parcel_to_both_px": [round(parcel_dx, 2), round(parcel_dy, 2)],
        "building_overlap": round(building_overlap, 3),
        "parcel_overlap": round(parcel_overlap, 3),
        "warning": warning,
        "note": (
            "bina.png konturlarina eklenerek parsel.png karesine goturen oteleme; "
            "her iki katman both.png'ye ayri ayri hizalanip fark alinarak olculdu."
        ),
    }


def shift_contours(contours: list[np.ndarray], offset: tuple[float, float]) -> list[np.ndarray]:
    """Kontur listesini (dx, dy) kadar oteler (float32 korunur)."""
    dx, dy = offset
    if dx == 0.0 and dy == 0.0:
        return contours
    delta = np.array([dx, dy], dtype=np.float32).reshape(1, 1, 2)
    return [(c.astype(np.float32) + delta) for c in contours]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Katman hizalama olcumu (tani/debug amacli)")
    parser.add_argument("--bina", type=Path, default=Path("assets/bina.png"))
    parser.add_argument("--parsel", type=Path, default=Path("assets/parsel.png"))
    parser.add_argument("--both", type=Path, default=Path("assets/both.png"))
    args = parser.parse_args()

    info = layer_offset(args.bina, args.parsel, args.both)
    print("bina  -> both : {} (ortusme {:.3f})".format(
        info["building_to_both_px"], info["building_overlap"]))
    print("parsel-> both : {} (ortusme {:.3f})".format(
        info["parcel_to_both_px"], info["parcel_overlap"]))
    print("bina  -> parsel kaymasi: {}".format(info["offset_px"]))
    if info["warning"]:
        print("UYARI: {}".format(info["warning"]))


if __name__ == "__main__":
    main()
