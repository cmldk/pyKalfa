"""
pyKalfa / Parsel-Bina - temiz kontur/cizgi cikarimi

Her katman kendi TEK katmanli kaynagindan okunur (`both.png` yalnizca
hizalama referansidir, bkz. align.py) ve Revit'te farkli bir nesneye
donustugu icin farkli bir geometri turu gerekir:

  - Bina -> `FilledRegion`: kapali kontur gerekir. Kirmizi cizgi agi bir
    GRAF olarak izlenir (`_skeleton_to_polylines`) ve `shapely.ops.polygonize`
    ile agin cevreledigi HER hucre (= her bagimsiz bina birimi) ayri bir
    FilledRegion olur. Bitisik bir blogu tek parca cikarmak (birlestirilmis
    kontur) denendi ve birakildi: birlesmis dis hat onlarca koseli, cokca
    icbukey bir cokgen oluyor ve sadelestirme/izgaraya oturtma sonrasi
    kendi kendini kesebiliyordu -- Revit boyle bir `CurveLoop`u reddedince
    o blok icin hic dolgu olusmuyordu. Hucre bazinda uretilen poligonlar
    kucuk ve basit oldugu icin bu sorun ortaya cikmaz.

  - Parsel -> iki ayri cikti:
      * `extract_parcel_lines` -> `DetailLine` cizimi icin polyline'lar.
        Bolge degil CIZGI istendigi icin ag dogrudan izlenir; boylece
        komsu iki parselin ortak siniri (kontur izlemede oldugu gibi
        cizginin iki farkli tarafindan iki kez degil) tam bir kez doner.
      * `extract_parcel_cells` -> parsel-bina eslesmesi icin kapali
        hucreler. Burada -- binanin aksine -- hucreler BIRLESTIRILMEZ:
        her parsel kendi poligonudur, zaten eslesme icin gereken de budur.

## Ortak omurga: iskelet -> graf -> polygonize

Iki katman da ayni omurgayi kullanir. Kalin cizgi (~3-10 px) once
`skeletonize` ile 1 piksele indirgenir; iskelet cizginin DIS kenari degil
TAM ORTASI oldugu icin geometri cizildigi boyutta kalir ve komsu iki
bolge arasinda piksel payi olusmaz -- ortak duvar iki tarafta da AYNI
polyline'dan gelir. Ham iskelet grafigi `polygonize`a verilmeden once
`polyline_cleanup` katmanindan gecer (kavsak tekillestirme, kor cikinti
temizligi, zincir birlestirme, sadelestirme). Kavsak tekillestirmesi
islevseldir: kil payi ayri kalan iki dugum, o kavsakta kapanmasi gereken
hucrenin hic bulunamamasina yol acabiliyordu.

Ayarlar `BUILDING_CLEANUP`/`PARCEL_CLEANUP` sabitlerindedir ve `cleanup`
argumaniyla degistirilebilir; neyin neden yapildigi icin bkz.
polyline_cleanup.py. Tek fark aci normalizasyonudur:

  - Bina duvarlari gercekte duz ve cogunlukla dik acilidir; 0/45/90'a
    yakin bir kenar raster gurultusu yuzunden birkac derece kaymissa
    duzeltilir.
  - Parsel sinirlari dogal olarak egiktir; oraya aci dayatmak sinirlari
    bozar, bu yuzden `axis_tolerance_deg=0` (kapali) birakilir.

## Neden geometriyi degistiren HER adim `polygonize`dan ONCE

Bina katmaninda sadelestirme ve izgaraya oturtma (`square_network`)
hucrelere bolunmeden once, AG uzerinde yapilir. Bunlar bir zamanlar
`polygonize`dan sonra her hucreye ayri ayri uygulaniyordu; iki komsu
birimin paylastigi duvar boylece IKI KEZ ve bagimsizca isleniyor,
sonuclar birebir ayni cikmayinca aralarinda ince bir bosluk aciliyordu
(olculdu: duvar paylasan 107 ciftin 6'si ayriliyor, en genis bosluk
30 cm). Revit'te "bitisik binalar yapisik gelmiyor" sikayeti buydu.

Kural sudur: her fiziksel cizgi TAM BIR KEZ islenir, hucreler o tek
geometriyi miras alir. Ayni sebeple kucuk yuzeyler atilmaz, komsusuna
katilir (`_absorb_slivers`) -- silmek dosemede delik acardi.

Koordinatlar temizleme katmanindan sonra alt-piksel (ondalikli) doner ve
oyle korunur: konturlar `float32`dir. `cv2.contourArea`, `pointPolygonTest`
ve `approxPolyDP` float32 ile calisir; yalniz `drawContours` (onizleme)
tam sayi ister ve orada yuvarlanir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid
from skimage.morphology import skeletonize

from imaging import layer_masks
from polyline_cleanup import CleanupConfig, Polyline, clean_polylines
from regularize import (
    dominant_angle,
    edge_line,
    rebuild_open,
    snap_edges,
    snap_polyline_to_axes,
    solve_node,
)

MIN_BUILDING_AREA_PX = 40     # bu alanin altindaki hucreler gurultu sayilir
MIN_PARCEL_AREA_PX = 150      # parsel hucreleri binadan buyuktur; kavsaklarda
                               # olusan kil payi ucgenleri bu esikle elenir
MORPH_KERNEL_SIZE = 3         # cizgideki kucuk kopukluklari kapatma cekirdegi

# Sagolcumun (kuzey oku / olcek cubugu / kunye) altinda kalan cizgi
# kopukluklarini kopruleme (bkz. `bridge_under_decorations`).
DECORATION_DILATION_PX = 2    # sagolcumun anti-alias kenarini da bandin icine al
DECORATION_BRIDGE_PX = 8      # bandin icinde bu yaricapla kapama yapilir; harflerin
                               # cizgide actigi bosluktan buyuk olmali

FRAME_EDGE_TOLERANCE_PX = 3.0  # bir kose pafta kenarina bu kadar yakinsa "kenarda"
                                # sayilir (kapanis cizgisi iskeletlestikten sonra
                                # kenardan birkac piksel iceride kalabiliyor)

MAX_FRAME_GAP_RATIO = 0.4     # `close_shapes_at_frame`: kapatilabilecek en genis
                               # cerceve boslugu, goruntunun KISA kenarina oran
                               # olarak. Sabit bir piksel sayisi yanlisti: bir
                               # binanin cerceveye bakan cephesi, kesitin
                               # yakinlastirma duzeyine gore 200 pikseli asabiliyor
                               # (olculdu). Oran, esigi kadrajla birlikte olcekler.

BUILDING_CLEANUP = CleanupConfig(axis_tolerance_deg=4.0)
PARCEL_CLEANUP = CleanupConfig()


# --- Ortak yardimcilar -------------------------------------------------------


def _closed_mask(mask: np.ndarray) -> np.ndarray:
    """Cizgideki kucuk kopukluklari morfolojik kapama ile giderir."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def bridge_under_decorations(line_mask: np.ndarray, decorations: np.ndarray) -> np.ndarray:
    """Sagolcumlerin ORTTUGU cizgi parcalarini koprular.

    Kuzey oku, olcek cubugu ve kunye yazisi ("AGDP (2024), IGN") haritanin
    UZERINE cizilir. Renk maskesi bunlari geometriye almaz -- ama altta
    kalan kirmizi/kahverengi piksel kaynak goruntude zaten yoktur, yani o
    cizgide gercek bir KOPUKLUK vardir. Kapanmayan bir bina konturu ise
    ic bolgesini disariya baglar: hucre ya hic bulunamaz ya da dis alanla
    birlesip anlamsiz bir sekle doner (olculdu: bir kesitte kunye yazisi
    bir binanin dis duvarini uc yerden kesiyor ve bina, pafta kenarina
    kadar uzayan sivri bir seride donusuyordu).

    Kapama YALNIZ sagolcumun kapladigi bandin icine yazilir. Butun maskeye
    uygulanirsa cizgiler kalinlasir ve dar sokakla ayrilmis komsu binalar
    birbirine yapisir; bant disina hic dokunulmaz.
    """
    if not decorations.any():
        return line_mask
    size = 2 * DECORATION_DILATION_PX + 1
    band = cv2.dilate(decorations, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))) > 0

    size = 2 * DECORATION_BRIDGE_PX + 1
    bridged = cv2.morphologyEx(
        line_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    )
    result = line_mask.copy()
    result[band] = bridged[band]
    return result


def _valid_polygons(geometry) -> list[Polygon]:
    """Poligonu Revit'e gonderilebilecek gecerli poligon(lar)a cevirir.

    `polygonize` ciktisi kendi kendine degen (self-touching) bir halkadan
    gelebilir: iskeletin iki kolu tek bir pikselde birlestiginde ortaya
    "kum saati" bicimli, OGC acisindan gecersiz bir poligon cikar. Revit
    boyle bir `CurveLoop`u `FilledRegion`a cevirirken hata verir.

    `make_valid` bu tur bir halkayi -- alan kaybetmeden -- birden fazla
    gecerli poligona ayirir; her biri ayri bir bolge olur. `make_valid`
    bir sey dondurmezse (ya da hala gecersizse) klasik `buffer(0)`
    denenir; ikisi de basarisiz olursa poligon atilir.

    """
    if geometry.is_empty:
        return []
    if not geometry.is_valid:
        geometry = make_valid(geometry)
        if geometry.is_empty or not geometry.is_valid:
            geometry = geometry.buffer(0)
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.is_valid and not geometry.is_empty else []
    if isinstance(geometry, MultiPolygon):
        return [g for g in geometry.geoms if g.is_valid and not g.is_empty]
    # GeometryCollection: make_valid poligonun yaninda cizgi/nokta artiklari
    # da dondurebilir; sadece poligonlari al.
    parts = getattr(geometry, "geoms", None)
    if parts is None:
        return []
    result: list[Polygon] = []
    for part in parts:
        result.extend(_valid_polygons(part))
    return result


def _to_contour(polygon: Polygon) -> np.ndarray | None:
    """Poligonun dis halkasini OpenCV kontur bicimine (N,1,2) cevirir.

    Ic halkalar (avlu/delik) dusurulur: kontur arayuzu tek halka tasir ve
    Revit tarafinda her bolge tek bir `CurveLoop` olarak olusturulur."""
    coords = np.asarray(polygon.exterior.coords[:-1], dtype=np.float32)
    if len(coords) < 3:
        return None
    return coords.reshape(-1, 1, 2)


def _network_polygons(polylines_px: list[Polyline]) -> list[Polygon]:
    """Cizgi agini duzlemsel bir graf olarak ele alip cevreledigi her
    hucreyi poligon olarak dondurur.

    `shapely.ops.polygonize` sinirsiz dis bolgeyi (sokak/bos alan) hic
    dondurmez, bu yuzden onu ayiklamak icin ayri bir kritere gerek kalmaz.
    """
    lines = [LineString(p) for p in polylines_px if len(p) >= 2]
    if not lines:
        return []
    cells: list[Polygon] = []
    for cell in polygonize(unary_union(lines)):
        cells.extend(_valid_polygons(cell))
    return cells


def _polygonize_cells(polylines_px: list[Polyline], min_area: float) -> list[np.ndarray]:
    """Agin cevreledigi her hucreyi AYRI bir kapali kontur olarak dondurur.

    Iki katman da bunu kullanir: bir hucre bina katmaninda bir bina
    birimi, parsel katmaninda bir parseldir. Bitisik hucreler
    BIRLESTIRILMEZ -- ortak duvar iki komsu poligonun PIKSEL PIKSEL ayni
    kenari oldugu icin aralarinda bosluk/pay da kalmaz.

    IC HALKASI (deligi) olan hucreler atilir. Boyle bir yuzey, icinde
    kendisine hic degmeyen BASKA bir kapali sekil barindiriyor demektir;
    bu da onun bir bina/parsel degil, cevresini saran DIS bosluk (bahce,
    sokak) oldugunun yapisal kanitidir. Pratikte bunlar `close_shapes_at_frame`
    bir cerceve bosluguna kapatma uygulayip aradaki acik alani da
    cevreledigi zaman olusur; delik testi olmadan boyle bir alan, icindeki
    binayi da yutan dev bir dolgu olarak ciktiya girerdi (olculdu: bu
    goruntude iki tane). Gercek kesik binalarin deligi yoktur.
    """
    faces = [cell for cell in _network_polygons(polylines_px) if not cell.interiors]
    cells = []
    for cell in _absorb_slivers(faces, min_area):
        contour = _to_contour(cell)
        if contour is not None:
            cells.append(contour)
    return cells


def _absorb_slivers(faces: list[Polygon], min_area: float) -> list[Polygon]:
    """Alan esiginin altindaki yuzeyleri ATMAK yerine komsusuna katar.

    `polygonize` ciktisi bosluksuz bir doseme uretir: her yuzey komsusuyla
    tam olarak ayni kenari paylasir. Kucuk bir yuzeyi silmek bu dosemede
    bir DELIK acar -- ve o delik, Revit'te iki bina biriminin arasindaki
    gozle gorunur bir bosluk olarak ortaya cikar (olculdu: kavsaklarda
    olusan 0.01 m2'lik bir kiymigin actigi bosluk 7 cm idi).

    Bu yuzden kiymik, sinirini EN UZUN paylastigi komsuya katilir; doseme
    butun kalir, alan kaybolmaz. Hicbir komsusu olmayan kiymik gercekten
    izole gurultudur ve atilir.
    """
    keep = [f for f in faces if f.area >= min_area]
    slivers = sorted((f for f in faces if f.area < min_area), key=lambda f: f.area)

    for sliver in slivers:
        best_index, best_shared = None, 0.0
        for index, neighbour in enumerate(keep):
            if not sliver.intersects(neighbour):
                continue
            shared = sliver.intersection(neighbour).length
            if shared > best_shared:
                best_index, best_shared = index, shared
        if best_index is None:
            continue
        merged = _valid_polygons(unary_union([keep[best_index], sliver]))
        if merged:
            keep[best_index] = max(merged, key=lambda p: p.area)
    return keep


# --- Iskelet -> cizgi grafigi ------------------------------------------------
#
# Bolge/kontur izleme her fiziksel cizgiyi IKI kez (iki tarafindan) gorur.
# Yapisal dogru cozum, her cizgiyi -- kac bolge paylasirsa paylassin --
# SADECE BIR KEZ izlemektir: 1 piksele inceltilmis iskeleti bir GRAF olarak
# ele alip dugum noktalari (ucnoktalar ve kesisimler) arasindaki yollari
# takip ediyor ve her yolu tek bir polyline olarak donduruyoruz.

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


def _trace_network(mask: np.ndarray, cleanup: CleanupConfig) -> list[Polyline]:
    """Maske -> temizlenmis polyline agi (iki katmanin ortak omurgasi)."""
    skeleton = skeletonize(mask > 0)
    return clean_polylines(_skeleton_to_polylines(skeleton), cleanup)


@dataclass(frozen=True)
class SquaringConfig:
    """`square_network` esikleri; hepsi PIKSEL biriminde.

    Gercek-dunya karsiliklari cagiran tarafta belirlenir (olcegi bilen
    tek yer orasidir, bkz. prepare_revit_input)."""

    max_shift: float
    chamfer_max_length: float = 0.0
    angle_tolerance_deg: float = 20.0
    min_point_spacing: float = 0.0   # bu araliktan yakin ardisik noktalar birlestirilir
    frame_shape: tuple[int, int] | None = None   # (yukseklik, genislik); verilirse pafta
                                                  # kenarindaki kapanis segmentleri kilitlenir


def _components(polylines: list[Polyline]) -> list[list[int]]:
    """Uc noktalarini paylasan polyline'lari bloklar halinde gruplar.

    Bitisik bir yapi blogu (dis hat + ic bolme duvarlari) tek bir
    bilesendir; izole bir bina da kendi basina bir bilesendir. Gruplama
    NOKTA ESITLIGI uzerinden yapilir -- `polyline_cleanup`in son adimi
    (`snap_tolerance_px`) paylasilan uclari birebir ayni koordinata
    oturttugu icin bu guvenlidir."""
    parent = list(range(len(polylines)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[tuple[float, float], int] = {}
    for index, polyline in enumerate(polylines):
        for endpoint in (polyline[0], polyline[-1]):
            key = (float(endpoint[0]), float(endpoint[1]))
            if key in owner:
                a, b = find(index), find(owner[key])
                if a != b:
                    parent[a] = b
            else:
                owner[key] = index

    groups: dict[int, list[int]] = {}
    for index in range(len(polylines)):
        groups.setdefault(find(index), []).append(index)
    return list(groups.values())


def square_network(polylines: list[Polyline], config: SquaringConfig) -> list[Polyline]:
    """Cizgi agini, TOPOLOJIYI BOZMADAN kendi izgarasina oturtur.

    Neden hucre basina degil de ag uzerinde:

    Sadelestirme ve izgaraya oturtma daha once `polygonize`dan SONRA, her
    hucreye ayri ayri uygulaniyordu. Iki komsu hucrenin paylastigi duvar
    boylece IKI KEZ ve birbirinden bagimsiz isleniyor, sonuclar birebir
    ayni cikmayinca da aralarinda ince bir bosluk aciliyordu -- Revit'te
    "bitisik binalar yapisik gelmiyor" seklinde gorunen sey buydu
    (olculdu: 107 komsu ciftin 6'si ayriliyor, en genis bosluk 30 cm).

    Ag uzerinde islenince her fiziksel cizgi TAM BIR KEZ oturtulur ve
    hucreler o tek geometriyi miras alir; ayrilma yapisal olarak imkansiz
    hale gelir. Dugumler (polyline uclari) sabit tutulur, sadece ic
    noktalar oynar -- yani ag hic kopmaz.

    Izgara acisi BLOK BAZINDA hesaplanir: bitisik bir yapi blogunun butun
    duvarlari ayni dogrultuya oturur, ayri bloklar ise (kadastroda sik
    oldugu gibi) kendi acilarini korur.

    Dugumler de oynatilir ama HER DUGUM ICIN BIR KEZ: konumu, o dugumde
    bulusan butun segmentlerin ortak cozumu olarak hesaplanir ve paylasan
    polyline'lar ayni sayiyi kullanir (bkz. `regularize.solve_node`).
    Dugumleri sabit tutmak da topolojiyi korurdu, ama bina koselerinin
    buyuk cogunlugu tam bir dugumun dibindedir -- sabit tutuldugunda o
    koseler pahli kaliyordu (olculdu: kalan pahlarin %84'u).
    """
    result: list[Polyline] = []
    for group in _components(polylines):
        members = [polylines[i] for i in group]
        locks = [_frame_edge_flags(p, config.frame_shape) for p in members]
        dominant = dominant_angle(members, locks)
        if dominant is None:
            result.extend(members)
            continue

        # Kapali donguler (izole binalar) dugum paylasmaz; halka olarak
        # tek adimda islenir.
        rings = [(p, locks[i]) for i, p in enumerate(members) if _is_ring(p)]
        chains = [p for p in members if not _is_ring(p)]
        chain_locks = [
            locks[i] for i, p in enumerate(members) if not _is_ring(p)
        ]
        for polyline, lock in rings:
            result.append(
                snap_polyline_to_axes(
                    polyline,
                    dominant=dominant,
                    max_shift=config.max_shift,
                    angle_tolerance_deg=config.angle_tolerance_deg,
                    chamfer_max_length=config.chamfer_max_length,
                    locked=lock,
                )
            )

        snapped = [
            snap_edges(p, dominant, config.angle_tolerance_deg, config.chamfer_max_length,
                       locked=lock)
            for p, lock in zip(chains, chain_locks)
        ]

        # Her dugumde bulusan uc segmentlerin dogrularini topla, dugumu
        # bir kez coz, sonra polyline'lari o dugumlerle yeniden kur.
        incident: dict[tuple[float, float], list] = {}
        for polyline, (edges, angles) in zip(chains, snapped):
            if not edges:
                continue
            for point, edge, angle in (
                (polyline[0], edges[0], angles[0]),
                (polyline[-1], edges[-1], angles[-1]),
            ):
                incident.setdefault(_node_key(point), []).append(edge_line(edge, angle))

        node_limit = config.max_shift + config.chamfer_max_length
        moved = {
            key: solve_node(lines, key, node_limit) for key, lines in incident.items()
        }

        for polyline, (edges, angles) in zip(chains, snapped):
            if not edges:
                result.append(polyline)
                continue
            start = moved.get(_node_key(polyline[0]), tuple(polyline[0]))
            end = moved.get(_node_key(polyline[-1]), tuple(polyline[-1]))
            result.append(rebuild_open(edges, angles, start, end, config.max_shift))

    if config.min_point_spacing > 0:
        result = [_drop_dense_points(p, config.min_point_spacing) for p in result]
    return result


def _drop_dense_points(polyline: Polyline, min_spacing: float) -> Polyline:
    """Birbirine cok yakin ardisik noktalari teke indirir; UCLAR korunur.

    Revit sifira yakin uzunlukta bir `Line`/`CurveLoop` segmentini kaldirmaz
    (otomasyonda kararsizlasip cokebiliyor), bu yuzden boyle noktalar
    ayiklanmak zorunda. Kritik olan bunun NEREDE yapildigi: ayni ayiklama
    hucre basina yapildiginda, paylasilan bir duvardaki kisa segment bir
    hucrede atilip komsusunda kaldigi icin ikisi birbirinden ayriliyordu
    (olculdu: 2 cift, 18 cm). Ag uzerinde bir kez yapilinca iki komsu da
    ayni sonucu miras alir."""
    if len(polyline) < 3:
        return polyline
    result = [polyline[0]]
    for point in polyline[1:-1]:
        if math.hypot(point[0] - result[-1][0], point[1] - result[-1][1]) >= min_spacing:
            result.append(point)
    last = polyline[-1]
    if (
        len(result) > 1
        and math.hypot(last[0] - result[-1][0], last[1] - result[-1][1]) < min_spacing
    ):
        result.pop()
    result.append(last)
    return result


def _frame_edge_flags(
    polyline: Polyline, shape: tuple[int, int] | None
) -> list[bool]:
    """Polyline'in hangi segmentleri pafta KENARI uzerinde?

    `close_shapes_at_frame`in ekledigi kapanis cizgisi bir duvar degildir;
    pafta sinirinda kalmalidir. Izgaraya oturtma onu binanin kendi
    izgarasina cevirdiginde kesilmis binalarin taban kenari egiliyor ve
    Revit'te bina yamuk gorunuyordu -- kaynaktaki cizgiyle hic ilgisi
    olmayan bir egim. Bu yuzden boyle segmentler kilitlenir: kendi
    dogrultularinda kalirlar ve baskin aci hesabina da girmezler."""
    if shape is None or len(polyline) < 2:
        return [False] * max(len(polyline) - 1, 0)
    height, width = shape
    tolerance = FRAME_EDGE_TOLERANCE_PX

    def edges_of(point) -> set[str]:
        x, y = float(point[0]), float(point[1])
        found = set()
        if x <= tolerance:
            found.add("left")
        if x >= width - 1 - tolerance:
            found.add("right")
        if y <= tolerance:
            found.add("top")
        if y >= height - 1 - tolerance:
            found.add("bottom")
        return found

    flags = []
    for i in range(len(polyline) - 1):
        # Iki uc da AYNI kenara oturuyorsa segment o kenar boyunca uzanir.
        flags.append(bool(edges_of(polyline[i]) & edges_of(polyline[i + 1])))
    return flags


def _is_ring(polyline: Polyline) -> bool:
    return len(polyline) > 2 and _node_key(polyline[0]) == _node_key(polyline[-1])


def _node_key(point) -> tuple[float, float]:
    """Dugum kimligi. Yuvarlama sart: paylasilan uclar `polyline_cleanup`
    sonrasi ayni sayiya oturur ama kayan nokta gosteriminde son bitleri
    farkli olabilir; ayni dugumun iki ayri kimlige dusmesi agi koparirdi."""
    return (round(float(point[0]), 3), round(float(point[1]), 3))


# --- Bina --------------------------------------------------------------------


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
    goruntu icinde kapanmaz; geriye "U" bicimli acik bir serit kalir ve o
    bina hic bulunamaz.

    Cozum: her bilesenin cerceveye DEGDIGI noktalar arasindaki cerceve
    parcasi maskeye eklenir; boylece sekil goruntu siniri boyunca kapanir
    ve dis hatti gercek bina alanini verir. Bilesenin cerceve uzerindeki
    ardisik degme noktalari arasinda kalan bosluklardan EN GENISI atlanir:
    o bosluk seklin disinda kalan (goruntunun geri kalanini dolasan)
    taraftir, doldurulursa sekil degil butun cerceve dolar.

    Araya baska bir bilesenin degme noktasi giren bosluklar da atlanir --
    aksi halde cerceve boyunca komsu iki bina tek bir bolgeye yapisirdi.

    `MAX_FRAME_GAP_RATIO`'nun izin verdiginden uzun bosluklar da atlanir.
    Bitisik binalar (sira ev bloklari) ic duvarlarla birbirine bagli
    oldugu icin TEK bir baglanti bileseni olusturur; bu blok cerceveye
    ONLARCA farkli noktada degebilir (her binanin kendi cephesi ayri bir
    degme noktasidir). "En genis bosluk disinda kalani kapat" kurali boyle
    bir durumda, iki binanin arasindaki gercek sokak/bosluk araligini da
    kapatabilir.

    Bu esik tek basina yeterli DEGILDIR ve olmasi da beklenmez: kapatilan
    bosluktan dogan yuzey `_polygonize_cells`te ayrica delik testinden
    gecer. Ikisi birlikte calisir -- esik acikca sacma genislikteki
    bosluklari bastan eler, delik testi ise kapatilanlar arasindan
    "icinde baska bina olan" (yani aslinda dis bosluk olan) yuzeyleri
    ayiklar.
    """
    height, width = mask.shape
    max_gap = int(MAX_FRAME_GAP_RATIO * min(height, width))
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
            if i == widest or end - start <= 1 or end - start > max_gap:
                continue
            span = [(start + k) % total for k in range(1, end - start)]
            if any(perimeter_labels[s] not in (0, label_id) for s in span):
                continue
            for s in span:
                x, y = perimeter[s]
                closed[y, x] = 255
    return closed


def extract_buildings(
    image_path: Path,
    cleanup: CleanupConfig | None = None,
    squaring: SquaringConfig | None = None,
    frame_overshoot_px: float = 0.0,
) -> list[np.ndarray]:
    """Her bina BIRIMI icin kapali bir kontur -> FilledRegion'a hazir.

    Bitisik yapilarda (sira ev bloklari) her birim ayri bir hucredir ve
    ayri bir FilledRegion olur; ic bolme (parti) duvarlari korunur.

    `squaring` verilirse sadelestirilmis ag, hucrelere bolunmeden ONCE
    kendi izgarasina oturtulur (bkz. `square_network`). Bu sira sarttir:
    hucre basina oturtma, komsu birimlerin paylastigi duvari iki kez
    isleyip aralarinda bosluk aciyordu.

    `frame_overshoot_px` verilirse pafta kenarinin kestigi binalar cizginin
    tam UZERINDE degil, o kadar DISINDA kapatilir. Kapanis cizgisi pafta
    cercevesiyle cakisinca Revit'te iki cizgi ust uste biniyor ve dolgu
    cerceveye tam degmiyormus gibi gorunuyordu; disarida kapatinca dolgu
    cerceveyi asar ve cizim kirpilarak (crop) cerceveye oturtulabilir.
    Bu, geometri cikarildiktan SONRA yalnizca kenardaki koseleri oynatarak
    yapilir (bkz. `_overshoot_frame_edges`); kenar disindaki noktalar
    negatif ya da genislikten buyuk cikar -- bilincli.

    Girdi `bina.png` olmalidir (yalniz bina katmani). `both.png`'de bina
    cizgilerinin govdesi parsel cizgileri ve etiketlerle delindigi icin
    oradan okumak kapanmayan birimler uretir (bkz. align.py).
    """
    masks = layer_masks(image_path)
    mask = _closed_mask(bridge_under_decorations(masks.building, masks.decoration))
    mask = close_shapes_at_frame(mask)
    polylines = _trace_network(mask, cleanup or BUILDING_CLEANUP)
    if squaring is not None:
        polylines = square_network(polylines, squaring)
    cells = _polygonize_cells(polylines, MIN_BUILDING_AREA_PX)
    return _overshoot_frame_edges(cells, mask.shape, frame_overshoot_px)


def _overshoot_frame_edges(
    cells: list[np.ndarray], shape: tuple[int, int], overshoot: float
) -> list[np.ndarray]:
    """Pafta kenarinda kapanan koseleri o kadar DISARI iter.

    Kesilmis bir bina, cerceve cizgisinin tam UZERINDE kapaniyordu; Revit'te
    dolgunun kenari pafta cizgisiyle cakisinca dolgu cerceveye degmiyormus
    gibi gorunuyor. Birkac desimetre disari tasirmak bu izi kaldirir ve
    cizim kirpilarak (crop) cerceveye tam oturtulabilir.

    Tasirma maskeye DEGIL, bitmis konturlara uygulanir. Once maskeyi
    genisletmek (kenar piksellerini disari kopyalayarak) denendi ve
    birakildi: kopyalama murekkegi kenara DIK uzattigi icin kenari egik
    kesen duvarlarda topolojiyi degistiriyordu -- olculdu, bir kesitte
    sahte bir kiymik hucre dogurdu ve komsu binayi 134 m2'den 318 m2'ye
    sisirdi. Yalnizca kenardaki koseleri oynatmak ise cerceve icindeki
    geometriyi bit bit ayni birakir; degisen tek sey kapanis kenaridir.
    """
    if overshoot <= 0:
        return cells
    height, width = shape
    result = []
    for contour in cells:
        points = contour.reshape(-1, 2).copy()
        on_left = points[:, 0] <= FRAME_EDGE_TOLERANCE_PX
        on_right = points[:, 0] >= width - 1 - FRAME_EDGE_TOLERANCE_PX
        on_top = points[:, 1] <= FRAME_EDGE_TOLERANCE_PX
        on_bottom = points[:, 1] >= height - 1 - FRAME_EDGE_TOLERANCE_PX
        points[on_left, 0] -= overshoot
        points[on_right, 0] += overshoot
        points[on_top, 1] -= overshoot
        points[on_bottom, 1] += overshoot
        result.append(points.reshape(-1, 1, 2))
    return result


# --- Parsel ------------------------------------------------------------------


def extract_parcel_lines(
    image_path: Path, cleanup: CleanupConfig | None = None
) -> list[Polyline]:
    """Parsel agini, her fiziksel cizgiyi tam bir kez iceren polyline
    listesi olarak dondurur -> DetailLine cizimi icin.

    Goruntu cercevesi bilerek EKLENMEZ: cerceve Revit'te kendi line
    style'iyla ayrica cizilir (bkz. prepare_revit_input._image_frame_lines).
    """
    masks = layer_masks(image_path)
    mask = _closed_mask(bridge_under_decorations(masks.parcel, masks.decoration))
    return _trace_network(mask, cleanup or PARCEL_CLEANUP)


def extract_parcel_cells(
    image_path: Path, cleanup: CleanupConfig | None = None
) -> list[np.ndarray]:
    """Her parsel icin kapali bir hucre konturu -> bina eslesmesi icin.

    Cizim icin degil, yalnizca "bu bina hangi parselin icinde" ve "bu
    etiket hangi parsele ait" sorularina cevap vermek icin uretilir.

    Cizgi agina goruntunun dis cercevesi EKLENIR: kadastro kesitinin
    kenarina degen parseller goruntu icinde kapanmaz ve cerceve olmadan
    hic hucre uretmezler -- oysa bir binanin en cok o kenar parsellerde
    kalmasi olagandir. Cerceve maske duzeyinde (1 px'lik dikdortgen olarak)
    eklenir; boylece kenara ulasan parsel cizgileri ona piksel duzeyinde
    baglanir ve iskelet grafigi butun olarak izlenir.
    """
    masks = layer_masks(image_path)
    mask = _closed_mask(bridge_under_decorations(masks.parcel, masks.decoration))
    height, width = mask.shape
    cv2.rectangle(mask, (0, 0), (width - 1, height - 1), 255, 1)
    polylines = _trace_network(mask, cleanup or PARCEL_CLEANUP)
    return _polygonize_cells(polylines, MIN_PARCEL_AREA_PX)


def enclosed_coverage(image_path: Path, cells: list[np.ndarray]) -> dict:
    """Kaynakta KAPALI kalan alanin ne kadari cikarildi? (tani olcutu)

    Bina cizgileri kapali konturlardir, yani bir binanin ici arka planin
    disariya BAGLANMAYAN bir bilesenidir -- bunu tespit etmek icin
    geometriye hic gerek yok, basit bir baglanti analizi yeter. Cikarilan
    hucreler bu alani kapatmiyorsa boru hattinda bir yerde kayip var
    demektir.

    Bu olcut, gozle fark edilmesi zor gerilemeleri sayiya dokuyor: ornegin
    izgaraya oturtma pafta kenarindaki kapanis cizgisini dondurdugunde bir
    binanin %41'i sessizce kayboluyordu (kalan parca "ucgen bir yapiyla
    ayrilmis" gibi gorunuyordu). Kapsama orani o hatayi tek bakista
    gosterir.
    """
    masks = layer_masks(image_path)
    mask = _closed_mask(bridge_under_decorations(masks.building, masks.decoration))
    height, width = mask.shape

    background = (mask == 0).astype(np.uint8)
    count, labels = cv2.connectedComponents(background, connectivity=4)

    # Pafta KENARINA degen hicbir bolge "kapali" sayilmaz. Kenara degen bir
    # bosluk (ör. iki binanin arasindaki sokak) goruntu icinde kapanmaz;
    # onu bina saymak yanlis olur. Yalnizca dort bir yani murekkeple
    # cevrili bolgeler olcute girer -- bunlar tanim geregi bina icidir.
    border = np.zeros(labels.shape, dtype=bool)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    open_labels = set(np.unique(labels[border & (background > 0)]).tolist())

    enclosed = (background > 0) & ~np.isin(labels, list(open_labels))

    covered = np.zeros((height, width), dtype=np.uint8)
    if cells:
        cv2.drawContours(covered, [np.round(c).astype(np.int32) for c in cells], -1, 255, cv2.FILLED)

    total = int(enclosed.sum())
    inside = int((enclosed & (covered > 0)).sum())
    return {
        "enclosed_px": total,
        "covered_px": inside,
        "ratio": (inside / total) if total else 1.0,
        "regions": count - 1,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Katman bazli geometri sayilari (tani/debug amacli)")
    parser.add_argument("--bina", type=Path, default=Path("assets/bina.png"))
    parser.add_argument("--parsel", type=Path, default=Path("assets/parsel.png"))
    args = parser.parse_args()

    buildings = extract_buildings(args.bina)
    cells = extract_parcel_cells(args.parsel)
    lines = extract_parcel_lines(args.parsel)
    print(f"bina:   {len(buildings)} birim konturu")
    print(f"parsel: {len(cells)} hucre, {len(lines)} cizgi polyline'i")

    coverage = enclosed_coverage(args.bina, buildings)
    print(
        "kapali alan kapsamasi: %.1f%% (%d/%d px)"
        % (100 * coverage["ratio"], coverage["covered_px"], coverage["enclosed_px"])
    )


if __name__ == "__main__":
    main()
