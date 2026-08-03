"""
pyKalfa / Parsel-Bina - Faz 3: temiz kontur/cizgi cikarimi

Revit hedefi iki katman icin farkli geometri turu gerektirir:

  - Bina -> her bina BIRIMI ayri bir `FilledRegion` olacak: kapali kontur
    gerekir. Bitisik binalarda (sira ev bloklari) dis hat almak butun
    blogu tek FilledRegion yapip ic bolme duvarlarini kaybettirir; bunun
    yerine kirmizi cizgi agi bir graf olarak izlenir ve
    `shapely.ops.polygonize` ile agin cevreledigi her hucre (= her
    bagimsiz bina birimi) ayri ayri cikarilir (bkz. `extract_buildings`,
    `_polygonize_cells`). Bu yaklasim raster tabanli (arka plan bilesenini
    genisletme) denemelerin aksine komsu birimler arasinda piksel payi
    birakmaz: ortak duvar iki tarafta da AYNI polyline'dan gelir.
  - Parsel -> parsel sinirlari `DetailLine` (duz cizgi) olarak cizilecek;
    kapali bir alan/dolgu degil. Bu yuzden "hangi parsel nerede kapali"
    sorusuna degil, "agin cizgileri piksel piksel nerede" sorusuna cevap
    ariyoruz. `cv2.RETR_CCOMP` + yalniz "hole" (cocuk) konturlari almak
    (onceki deneme) goruntu kenarina degen/acik parselleri tamamen
    kaybettiriyordu (RETR_CCOMP'ta kenara degen bosluklar "hole" degil
    ust-seviye/parent=-1 sayiliyor, biz de onlari atiyorduk). Cizgi
    amaci icin bu kayip kabul edilemez; bunun yerine `cv2.RETR_LIST`
    kullanilir (agin butun cizgileri - kenardakiler dahil - polyline
    olarak donsun) ve yalniz agin kendi dis hattini temsil eden tek dev
    artefakt kontur (goruntu alaninin >%50'si) elenir.

Parsel katmaninda iki ek sorun daha vardi:

  1. Parsel numara etiketleri (ör. "1024W") parsel cizgisi sanilip
     konturlere dahil oluyordu -- genel grayscale esikleme metni de
     cizgiyle ayni "ink" sayiyordu. Cozum: parsel cizgileri gorselde
     kahverengi/kirmizimsi (R kanali G/B'den belirgin yuksek), etiketler
     ise notr gri/siyah (R~G~B) -- renk kanallarina bakarak sadece
     kirmizimsi pikseller alinir, boylece metin/kuzey oku/olcek cubugu
     (hepsi notr/lacivert tonlarda) otomatik disarida kalir.
  2. Komsu iki parselin ortak siniri, her iki parselin de kendi konturunde
     ayri ayri (cizginin iki farkli tarafindan) izlendigi icin DetailLine
     olarak iki kez (birbirine yakin, hafif kaymis) ciziliyordu. Cozum:
     kontur cikarmadan once maske `skimage.morphology.skeletonize` ile
     1 piksel genisliginde bir iskelete indirgenir; boylece cizgi
     kalinligindan kaynaklanan kayma buyuk olcude azalir.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from skimage.morphology import skeletonize

from detect_lines import MIN_CONTOUR_AREA, _load_on_white_background
from map_decorations import strip_decorations

MIN_CONTOUR_ARC_LENGTH = 60
MAX_PARCEL_AREA_RATIO = 0.5  # bu orandan buyuk konturlar parsel degil, agin dis hatti/artefakt
REDDISH_CHANNEL_MARGIN = 20   # R kanali G/B'nin en az bu kadar uzerindeyse "parsel cizgisi" sayilir
BUILDING_RED_MARGIN = 60      # R kanali G/B'nin en az bu kadar uzerindeyse "bina cizgisi" sayilir
                               # (parselden daha yuksek: bina cizgisi doymus kirmizi, R-G/B farki
                               # genelde 200+; kahverengi/lacivert sagolcumlerde bu fark negatif)
BUILDING_ALPHA_MIN = 16       # PNG'nin kendi alfa kanalindaki bu esigin altindaki piksel
                               # anti-alias/gurultu sayilir, cizgiye dahil edilmez
MORPH_KERNEL_SIZE = 3


def _filter_contours(contours: list[np.ndarray]) -> list[np.ndarray]:
    return [c for c in contours if cv2.contourArea(c) >= MIN_CONTOUR_AREA or cv2.arcLength(c, False) >= MIN_CONTOUR_ARC_LENGTH]


def build_parcel_line_mask(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Sadece kirmizimsi/kahverengi parsel cizgisi piksellerinden olusan,
    1 piksele inceltilmis (skeletonize) ikili maske dondurur.

    Genel `build_line_mask` (grayscale esikleme) yerine renk kanallarina
    bakar; bu sayede notr renkteki parsel numara etiketleri, kuzey oku ve
    olcek cubugu bastan disarida kalir (ayrica bkz. modul docstring'i).
    """
    image = _load_on_white_background(image_path)
    b = image[:, :, 0].astype(np.int16)
    g = image[:, :, 1].astype(np.int16)
    r = image[:, :, 2].astype(np.int16)
    reddish = ((r - np.maximum(b, g)) > REDDISH_CHANNEL_MARGIN).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    closed = cv2.morphologyEx(reddish, cv2.MORPH_CLOSE, kernel)
    skeleton = (skeletonize(closed > 0).astype(np.uint8)) * 255
    return image, skeleton


def _perimeter_coords(height: int, width: int) -> list[tuple[int, int]]:
    """Goruntu cercevesinin piksellerini saat yonunde, dongusel bir dizi
    olarak dondurur (sol-ust kosede baslar). Kapanmamis sekilleri cerceve
    boyunca kapatirken "iki degme noktasi arasindaki yol" bu dizi uzerinde
    aranir."""
    top = [(x, 0) for x in range(width)]
    right = [(width - 1, y) for y in range(1, height)]
    bottom = [(x, height - 1) for x in range(width - 2, -1, -1)]
    left = [(0, y) for y in range(height - 2, 0, -1)]
    return top + right + bottom + left


def close_shapes_at_frame(mask: np.ndarray) -> np.ndarray:
    """Goruntu kenarinda kesilmis bina konturlarini goruntunun cercevesiyle
    kapatir.

    Kadastro kesiti bir binanin ortasindan gectiginde o binanin cizgisi
    goruntu icinde kapanmaz; geriye "U" bicimli acik bir seritt kalir.
    `RETR_EXTERNAL` boyle bir serittin cevresini izledigi icin bina alani
    yerine cizgi kalinligi kadar ince, anlamsiz bir bolge uretir (ornek
    goruntude 46 konturun 11'i boyleydi, doluluk oranlari 0.05-0.45).

    Cozum: her bilesenin cerceveye DEGDIGI noktalar arasindaki cerceve
    parcasi maskeye eklenir; boylece sekil goruntu siniri boyunca kapanir
    ve dis hatti gercek bina alanini verir. Bilesenin cerceve uzerindeki
    ardisik degme noktalari arasinda kalan bosluklardan EN GENISI atlanir:
    o bosluk seklin disinda kalan (goruntunun geri kalanini dolasan)
    taraftir, doldurulursa sekil degil butun cerceve dolar.

    Araya baska bir bilesenin degme noktasi giren bosluklar da atlanir --
    aksi halde cerceve boyunca komsu iki bina tek bir bolgeye yapisirdi.
    """
    height, width = mask.shape
    perimeter = _perimeter_coords(height, width)
    xs = np.array([p[0] for p in perimeter])
    ys = np.array([p[1] for p in perimeter])

    num_labels, labels = cv2.connectedComponents((mask > 0).astype(np.uint8), connectivity=8)
    perimeter_labels = labels[ys, xs]  # her cerceve pikselinin bileseni (0 = bos)

    closed = mask.copy()
    total = len(perimeter)
    for label_id in range(1, num_labels):
        touches = np.flatnonzero(perimeter_labels == label_id)
        if touches.size < 2:
            continue  # cerceveye hic degmiyor ya da tek noktada siyiriyor

        # Ardisik degme noktalari arasindaki dongusel bosluklar: (a, b) -> a+1..b-1
        gaps = list(zip(touches, np.append(touches[1:], touches[0] + total)))
        widest = max(range(len(gaps)), key=lambda i: gaps[i][1] - gaps[i][0])

        for i, (start, end) in enumerate(gaps):
            if i == widest or end - start <= 1:
                continue
            span = [(start + k) % total for k in range(1, end - start)]
            if any(perimeter_labels[s] not in (0, label_id) for s in span):
                continue
            for s in span:
                x, y = perimeter[s]
                closed[y, x] = 255
    return closed


def build_building_line_mask(image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Sadece kirmizi bina cizgisi piksellerinden olusan ikili maske dondurur.

    `build_line_mask` (genel grayscale esikleme) yerine dogrudan renk
    kanallarina bakar: R kanali B/G'den belirgin yuksekse "bina cizgisi"
    sayilir. Bu, harita sagolcumlerini (kuzey oku, olcek cubugu -- lacivert)
    ve metin etiketlerini (notr gri/siyah) bastan disarida birakir; ayrica
    (bkz. `strip_decorations`) ikinci bir guvenlik agi olarak uygulanir.

    Kaynak PNG'lerde anti-alias RGB kanalina degil ALFA kanalina yazilir
    (cizgi kenarindaki piksel hep doymus kirmizi (255,0,0) renginde kalir,
    sadece opakligi duser). Bu yuzden goruntu once beyaz zemine
    duzlestirilmeden, HAM alfa kanali uzerinden okunur -- aksi halde
    kenardaki soluk pikseller beyaza yakin bir tona karisip kaybolurdu.
    """
    raw = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Goruntu okunamadi: {image_path}")

    if raw.ndim == 3 and raw.shape[2] == 4:
        bgr = raw[:, :, :3].astype(np.int16)
        opaque = raw[:, :, 3] > BUILDING_ALPHA_MIN
    else:
        bgr = (raw if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)).astype(np.int16)
        opaque = np.ones(bgr.shape[:2], dtype=bool)

    b, g, r = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]
    reddish = (r - np.maximum(b, g)) > BUILDING_RED_MARGIN
    mask = (reddish & opaque).astype(np.uint8) * 255

    image = _load_on_white_background(image_path)
    mask = strip_decorations(image, mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return image, closed


def _polygonize_cells(polylines_px: list[list[tuple[int, int]]]) -> list[np.ndarray]:
    """Iskelet-grafigi polyline'larindan, ag icinde kapali kalan HER hucreyi
    (yani her bagimsiz bina birimini) ayri bir kapali kontur olarak dondurur.

    `shapely.ops.polygonize` bir cizgi agini duzlemsel bir graf olarak ele
    alip, agin cevreledigi her sinirli bolgeyi kendi poligonu olarak
    uretir -- sinirsiz dis bolgeyi (sokak/bos alan) hic dondurmez, bu yuzden
    onu ayiklamak icin ayri bir kritere gerek kalmaz. Bitisik iki bina birimi
    ortak duvari AYNI polyline'dan (biri ileri, biri geri yonde) miras aldigi
    icin aralarinda onceki raster
    tabanli denemelerde (arka plan bilesenlerini genisletme) ortaya cikan
    piksel payi/margin sifirdir: iki komsu poligonun ortak kenari piksel
    piksel ayni cizgidir.
    """
    lines = [LineString(p) for p in polylines_px if len(p) >= 2]
    if not lines:
        return []
    noded = unary_union(lines)
    cells = []
    for polygon in polygonize(noded):
        if polygon.is_empty or polygon.area < MIN_CONTOUR_AREA:
            continue
        coords = np.array(polygon.exterior.coords[:-1], dtype=np.int32)
        cells.append(coords.reshape(-1, 1, 2))
    return cells


def extract_buildings(image_path: Path) -> tuple[np.ndarray, list[np.ndarray]]:
    """Her bina BIRIMI icin kapali bir kontur dondurur -> FilledRegion'a hazir.

    Bitisik yapilarda (sira ev bloklari) dis hat alinirsa butun blok tek bir
    FilledRegion olur ve ic bolme (parti) duvarlari kaybolur. Bunun yerine
    kirmizi cizgi agi -- parsel katmanindaki ile ayni yontemle (bkz.
    `_skeleton_to_polylines`) -- bir graf olarak izlenir ve `_polygonize_cells`
    ile agin cevreledigi her hucre (= her bagimsiz bina birimi) ayri ayri
    cikarilir. Boylece bitisik binalar arasindaki ic cizgiler de -- kendi
    aralarindaki ortak duvarlar dahil -- birebir korunur.

    Iskelet, kalin cizginin (~3 px) DIS kenari degil TAM ORTASI oldugu icin
    binalar cizildigi boyutta kalir ve koseler anti-alias'la pahlanmaz."""
    image, mask = build_building_line_mask(image_path)
    mask = close_shapes_at_frame(mask)
    skeleton = (skeletonize(mask > 0).astype(np.uint8)) * 255
    polylines = _skeleton_to_polylines(skeleton > 0)
    return image, _polygonize_cells(polylines)


def extract_parcels(image_path: Path) -> tuple[np.ndarray, list[np.ndarray]]:
    """Parsel agindaki tum cizgi/polyline'lari (kapali bolge konturu olarak)
    dondurur -- SADECE parsel-bina eslesmesi (point-in-polygon) ve alan
    hesabi icin kullanilir. Gercek DetailLine cizimi icin `extract_parcel_lines()`
    kullanilir (bkz. asagi, neden ayri oldugu aciklaniyor).

    Kapaniklik aranmaz (goruntu kenarina degen acik parseller de dahildir);
    sadece agin kendi dis hattini temsil eden dev artefakt kontur elenir.
    """
    image, mask = build_parcel_line_mask(image_path)
    image_area = float(image.shape[0] * image.shape[1])
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) <= image_area * MAX_PARCEL_AREA_RATIO]
    return image, _filter_contours(contours)


# --- Iskelet -> cizgi grafigi ------------------------------------------------
#
# extract_parcels() her parselin KENDI kapali bolgesini ayri ayri izler; iki
# komsu parsel ortak bir siniri paylastiginda bu sinir HER IKI parselin
# konturunde de (cizginin iki farkli tarafindan) ayri ayri yer alir. Sonradan
# "birbirine yakin segmentleri birlestir" seklinde bir düzeltme kirilgan:
# komsu parseller ayni siniri farkli noktalardan sadelestirebiliyor, boylece
# segmentler tam ortusmuyor.
#
# Yapisal dogru cozum: her fiziksel cizgiyi -- kac parsel paylasirsa
# paylassin -- SADECE BIR KEZ izlemek. Bunun icin 1 piksele inceltilmis
# iskeleti bir GRAF olarak ele aliyoruz: dugum noktalari (ucnoktalar ve
# kesisimler) arasindaki yollari takip edip her yolu tek bir polyline olarak
# donduruyoruz.

_NEIGHBOR_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _neighbor_counts(skeleton: np.ndarray) -> np.ndarray:
    """Her piksel icin 8-komsulugundaki iskelet piksel sayisini dondurur."""
    padded = np.pad(skeleton, 1, mode="constant")
    counts = np.zeros_like(skeleton, dtype=np.uint8)
    for dy, dx in _NEIGHBOR_OFFSETS:
        counts += padded[1 + dy : 1 + dy + skeleton.shape[0], 1 + dx : 1 + dx + skeleton.shape[1]]
    return counts * (skeleton > 0)


def _skeleton_to_polylines(skeleton_bool: np.ndarray) -> list[list[tuple[int, int]]]:
    """1 piksellik iskeleti, her fiziksel cizgiyi tam bir kez iceren bir
    (x, y) nokta listeleri (polyline) kumesine cevirir.

    Dugum (node) = uc nokta (1 komsu) veya kesisim (3+ komsu). Iki dugum
    arasindaki her yol (araya giren, tam 2 komsulu "sıradan" pikseller
    zinciri) tek bir polyline olarak izlenir. Agin geri kalanina hic
    degmeyen izole kapali donguler (nadiren olusabilir) ayrica islenir.
    """
    skeleton = skeleton_bool.astype(np.uint8)
    counts = _neighbor_counts(skeleton)
    is_node = (skeleton > 0) & ((counts == 1) | (counts >= 3))

    node_ys, node_xs = np.where(is_node)
    node_coords = set(zip(node_xs.tolist(), node_ys.tolist()))

    height, width = skeleton.shape

    def neighbors_of(x: int, y: int) -> list[tuple[int, int]]:
        result = []
        for dy, dx in _NEIGHBOR_OFFSETS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and skeleton[ny, nx]:
                result.append((nx, ny))
        return result

    visited_path_pixel = np.zeros_like(skeleton, dtype=bool)
    polylines: list[list[tuple[int, int]]] = []

    def trace(start: tuple[int, int], first_step: tuple[int, int]) -> list[tuple[int, int]]:
        path = [start, first_step]
        prev, cur = start, first_step
        max_steps = height * width  # sonsuz donguye karsi guvenlik
        for _ in range(max_steps):
            if cur in node_coords:
                break
            visited_path_pixel[cur[1], cur[0]] = True
            nxts = [n for n in neighbors_of(*cur) if n != prev]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
            path.append(cur)
        return path

    for x, y in node_coords:
        for nx, ny in neighbors_of(x, y):
            if (nx, ny) in node_coords:
                if (x, y) < (nx, ny):  # ayni tek-piksellik kenari iki kez ekleme
                    polylines.append([(x, y), (nx, ny)])
                continue
            if visited_path_pixel[ny, nx]:
                continue
            polylines.append(trace((x, y), (nx, ny)))

    # Dugumsuz, izole kapali donguler (ag ile hic temas etmeyen kapali bir
    # parsel siniri gibi -- her pikselin tam 2 komsusu var, hic dugum yok).
    remaining = (skeleton > 0) & ~visited_path_pixel & ~is_node
    handled = np.zeros_like(skeleton, dtype=bool)
    rem_ys, rem_xs = np.where(remaining)
    for x, y in zip(rem_xs.tolist(), rem_ys.tolist()):
        if handled[y, x]:
            continue
        nbrs = neighbors_of(x, y)
        if not nbrs:
            continue
        start = (x, y)
        path = [start]
        prev, cur = start, nbrs[0]
        max_steps = height * width
        for _ in range(max_steps):
            path.append(cur)
            handled[cur[1], cur[0]] = True
            if cur == start:
                break
            nxts = [n for n in neighbors_of(*cur) if n != prev]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
        handled[y, x] = True
        polylines.append(path)

    return polylines


def extract_parcel_lines(image_path: Path) -> tuple[np.ndarray, list[list[tuple[int, int]]]]:
    """Parsel agini, her fiziksel cizgiyi tam bir kez iceren piksel bazli
    polyline listesi olarak dondurur -> DetailLine cizimi icin kullanilir.

    `extract_parcels()`'in aksine bolge/kontur degil, dogrudan iskelet
    grafigini izler; bu yuzden komsu iki parselin ortak siniri iki kez
    (hafif kaymis) degil, tam olarak bir kez donar.
    """
    image, skeleton = build_parcel_line_mask(image_path)
    polylines = _skeleton_to_polylines(skeleton > 0)
    polylines = [p for p in polylines if len(p) >= 2]
    return image, polylines


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Katman bazli temiz kontur sayilari (tani/debug amacli)")
    parser.add_argument("--parsel", type=Path, default=Path("assets/parsel.png"))
    parser.add_argument("--bina", type=Path, default=Path("assets/bina.png"))
    args = parser.parse_args()

    _, parcels = extract_parcels(args.parsel)
    _, buildings = extract_buildings(args.bina)
    print(f"parsel: {len(parcels)} temiz kontur")
    print(f"bina:   {len(buildings)} temiz kontur")


if __name__ == "__main__":
    main()
