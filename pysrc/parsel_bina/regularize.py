"""
pyKalfa / Parsel-Bina - bina poligonlarini kendi izgarasina oturtma

Raster bir cizimden cikarilan kontur, gercekte dumduz olan bir duvari
"merdiven" basamaklariyla temsil eder. `cv2.approxPolyDP` basamaklari
temizler ama iki bedel oder:

  1. Kenarin acisini bir-iki derece kaydirir, dik koseler yamulur.
  2. Bir kosedeki basamak yigilmasini TEK bir kisa capraz kenarla
     degistirir -- yani keskin kose, pahli (kesik) bir koseye doner.

Bu modul ikisini de duzeltir:

  - **Izgaraya oturtma**: blogun izgara AILELERI (baskin yonleri) bulunur,
    her kenar en yakin ailenin 90 derecelik izgarasina oturtulur ve koseler
    ardisik kenar DOGRULARININ kesisimi olarak yeniden hesaplanir.
  - **Pah temizligi**: raster artigi olan kisa capraz kenarlar atilir,
    komsulari kesistirilerek kose sivri hale getirilir.

## Pah ile gercek mimari ogeyi ayirmak

Her kisa capraz kenar artik degildir; binalarda gercek pahli koseler ve
kucuk cikinti/basamaklar vardir. Uc olcut birlikte kullanilir:

  - kenar KISA (`chamfer_max_length`),
  - oturtmadan sonra hala IZGARA DISINDA (gercek bir duvar olsaydi
    izgaraya girerdi),
  - iki KOMSUSU birbirine DIK (`CHAMFER_NEIGHBOUR_*_DEG`).

Ucuncusu kucuk cikinti/basamaklari eler: kesilmis bir kosede komsu
duvarlar dik acidadir, gercek bir basamakta ise paraleldir. Olculdu: bu
goruntudeki kisa+izgara disi kenarlarin %81'inde komsular dik (medyan tam
90 derece), %11'inde paralel -- yani olcut ikisini temiz ayirir.

GERCEK bir mimari pah (pan coupe) icin ise sekil olcutu ise yaramaz;
onun da komsulari diktir. Onu koruyan tek sey UZUNLUK esigidir, bu yuzden
esik cagirandan gelir ve sadelestirme toleransina baglanmalidir: bu
artiklari URETEN adim `approxPolyDP`'dir, dolayisiyla boylari o toleransin
katlari mertebesindedir (olculdu: medyan 0.9 m, populasyon 1.5 m'de
tukeniyor). Mimari bir pan coupe tipik olarak 2 m'den uzundur ve arada
kalan bandi cagiran secer.

## Bilincli sinirlar

  - Izgaraya oturtma yalniz `ANGLE_TOLERANCE_DEG` icindeki kenarlara
    uygulanir. Gercekten egik bir duvar (kadastroda sik) zorla dikeye
    cevrilmez.
  - Aci toleransinin yaninda bir KAYMA siniri da vardir: kenar ortasi
    etrafinda dondugu icin uzun bir kenarda kucuk bir aci farki bile
    uclari cok oynatir; uclari `max_shift`ten fazla oynatacak oturtma
    yapilmaz (bkz. `_snap`).
  - Yeni kose eskisinden `CORNER_SHIFT_FACTOR * max_shift` (arada pah
    atildiysa arti pahin boyu) kadardan fazla uzaga duserse eski kose
    korunur. Cok kisa kenarlarda iki dogru neredeyse paralel kesisip
    koseyi metrelerce oteye atabilir; bu koruma onu engeller. Sinir
    eskiden komsu kenarlarin yari uzunluklarini da iceriyordu; uzun
    duvarlarin koseleri bu yuzden metreye yakin kayabiliyordu.
  - Sonucta poligon kendi uzerine katlanirsa once pah temizligi olmadan
    tekrar denenir, o da katlanirsa girdi oldugu gibi geri doner
    (asagi bkz.).

## Neden sonda bir gecerlilik kontrolu var

Kose bazindaki `max_shift` korumasi YEREL'dir: her koseyi tek basina
makul bir mesafede tutar ama koselerin BIRBIRINE gore sirasini garanti
etmez. Kisa bir kenarin iki ucu birbirinin otesine gectiginde poligon
kendi kendini keser. Boyle bir halkayi Revit `FilledRegion`a cevirirken
reddeder -- ve bu, ciktida "eksik dolgu" olarak gorunur, hata olarak
degil.

Geri cekilme KADEMELIDIR. Once butun duzeltme, sonra pahsiz duzeltme,
en son ham girdi denenir: tek adimda hepsinden vazgecmek, sirf bir kosesi
sorunlu diye binayi tamamen yamuk birakiyordu (olculdu: 85 binanin 4'u).
"""

from __future__ import annotations

import math

from shapely.geometry import Polygon

ANGLE_TOLERANCE_DEG = 20.0   # bu kadar sapmis kenar izgaraya cekilir, fazlasi egik kabul edilir
PARALLEL_EPSILON = 0.05      # iki dogru bu kadar paralelse kesisim aranmaz (sin(aci))

# Kesilmis kose imzasi: pahin iki komsusu arasindaki aci bu araliktaysa
# (yani birbirine dikse) o kisa capraz kenar raster artigi sayilir.
CHAMFER_NEIGHBOUR_MIN_DEG = 60.0
CHAMFER_NEIGHBOUR_MAX_DEG = 120.0

_RIGHT_ANGLE = math.pi / 2

# Izgara aileleri (bkz. `_grid_families`).
GRID_SEARCH_STEP_DEG = 0.5     # tepe aramasinin aci adimi
GRID_KERNEL_DEG = 1.5          # aci yogunlugunun yumusatma genisligi
GRID_FAMILY_WINDOW_DEG = 4.0   # bir ailenin tepe cevresinde topladigi aralik
GRID_FAMILY_MIN_SHARE = 0.25   # ilk aile disindakilerin tasimasi gereken en az uzunluk payi
GRID_MAX_FAMILIES = 4

# Kose/dugum, eski yerinden en fazla `max_shift`in bu kati kadar oynar (arada
# pah atildiysa arti pahin boyu). Uclari en fazla `max_shift` oynayan iki dik
# dogrunun kesisimi sqrt(2) kati kayar; 1.5 bunu kucuk bir payla karsilar.
CORNER_SHIFT_FACTOR = 1.5


class _Edge:
    """Poligonun bir kenari: yonu, uzunlugu ve iki ucu."""

    __slots__ = ("angle", "length", "start", "end")

    def __init__(self, start, end):
        self.start = start
        self.end = end
        dx, dy = end[0] - start[0], end[1] - start[1]
        self.angle = math.atan2(dy, dx)
        self.length = math.hypot(dx, dy)

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.start[0] + self.end[0]) / 2.0, (self.start[1] + self.end[1]) / 2.0)


def _edges_indexed(polygon: list[tuple[float, float]]) -> list[tuple[int, _Edge]]:
    """Kapali poligonun kenarlari, KAYNAK INDEKSIYLE birlikte.

    Indeks sart: `locked` gibi kenar basina verilen bayraklar cagiranin
    nokta dizisine gore numaralanir; sifir uzunluklu kenarlar atilinca
    dizi kayar ve bayraklar yanlis kenara denk gelirdi."""
    count = len(polygon)
    result = []
    for i in range(count):
        edge = _Edge(polygon[i], polygon[(i + 1) % count])
        if edge.length >= 1e-9:
            result.append((i, edge))
    return result


def _edges(polygon: list[tuple[float, float]]) -> list[_Edge]:
    """Kapali poligonun kenarlari (sifir uzunluklu olanlar atilir)."""
    return [edge for _, edge in _edges_indexed(polygon)]


def _dominant_angle(edges: list[_Edge]) -> float:
    """Kenarlarin uzunlukla agirlikli baskin dogrultusu (0-90 derece).

    Aci 4 ile carpilarak tam daireye tasinir: boylece 0 ile 90 derece
    (ayni izgaranin iki ekseni) ayni yone denk gelir ve dairesel ortalama
    90 derecelik sarmadan etkilenmez."""
    vx = sum(e.length * math.cos(4 * e.angle) for e in edges)
    vy = sum(e.length * math.sin(4 * e.angle) for e in edges)
    return math.atan2(vy, vx) / 4.0


def _quarter_difference(angle: float, reference: float) -> float:
    """Iki dogrultu arasindaki fark, 90 derecelik izgara simetrisiyle
    [-45, 45) derece araligina indirgenmis (radyan)."""
    return (angle - reference + _RIGHT_ANGLE / 2) % _RIGHT_ANGLE - _RIGHT_ANGLE / 2


def _grid_families(edges: list[_Edge]) -> list[float]:
    """Kenarlarin tasidigi izgara AILELERI, en guclu once.

    Tek bir uzunluk agirlikli ortalama, blokta birden fazla dogrultu varsa
    HICBIRINE oturmayan bir aci verir. Kadastroda bitisik bir blok cogu
    zaman farkli acilarda yapilmis binalardan olusur (olculdu: bir blokta
    duvar uzunlugunun %23'u ortalamadan 5-10 derece sapiyordu) ve o
    ortalamaya zorla oturtulan duvarlar donup yerinden kayiyordu.

    Bu yuzden aci yogunlugunun TEPELERI aranir: en guclu tepe ilk aile
    olur, cevresindeki kenarlar ayrilir ve kalanlarda yeni tepe aranir.
    Ilk aile disindakiler blok uzunlugunun en az `GRID_FAMILY_MIN_SHARE`
    kadarini tasimalidir; tek tuk gurultu kenarlari aile dogurmasin diye.
    Her ailenin acisi, tepe cevresindeki kenarlarin `_dominant_angle`
    ortalamasidir."""
    total = sum(e.length for e in edges)
    if total <= 0:
        return []
    kernel = math.radians(GRID_KERNEL_DEG)
    window = math.radians(GRID_FAMILY_WINDOW_DEG)
    candidates = [
        math.radians(step * GRID_SEARCH_STEP_DEG)
        for step in range(int(round(90 / GRID_SEARCH_STEP_DEG)))
    ]

    families: list[float] = []
    remaining = list(edges)

    def density(candidate: float) -> float:
        return sum(
            e.length * math.exp(-0.5 * (_quarter_difference(e.angle, candidate) / kernel) ** 2)
            for e in remaining
        )

    while remaining and len(families) < GRID_MAX_FAMILIES:
        peak = max(candidates, key=density)
        members = [e for e in remaining if abs(_quarter_difference(e.angle, peak)) <= window]
        weight = sum(e.length for e in members)
        if not members or (families and weight < GRID_FAMILY_MIN_SHARE * total):
            break
        families.append(_dominant_angle(members))
        remaining = [e for e in remaining if abs(_quarter_difference(e.angle, peak)) > window]
    return families


def _angle_between(first: float, second: float) -> float:
    """Iki dogrultu arasindaki aci, derece (0-180)."""
    return math.degrees(abs((second - first + math.pi) % (2 * math.pi) - math.pi))


def _snap(
    edge: _Edge, grid: float | list[float], tolerance: float, max_offset: float | None = None
) -> tuple[float, bool]:
    """Kenari izgaranin en yakin eksenine oturtur.

    `grid` tek bir aci ya da bir aci listesidir (bir blokta birden fazla
    izgara ailesi olabilir, bkz. `_grid_families`); kenar en yakin aileye
    oturur. `(aci, izgaraya_oturdu_mu)` doner; oturmazsa aci degismez.

    Aci toleransi TEK BASINA yeterli degildir: kenar ortasi etrafinda
    doner, uclari `uzunluk/2 * sin(sapma)` kadar yer degistirir -- 10
    m'lik bir duvarda 5 derecelik sapma uclari 44 cm oynatir. Kisa bir
    raster kenari icin buyuk bir aci farki gurultudur, uzun bir duvar
    icin ise gercek bir dogrultu farkidir. `max_offset` verilirse uclari
    bundan fazla oynatacak oturtma reddedilir."""
    families = grid if isinstance(grid, (list, tuple)) else (grid,)
    best_angle, best_difference = edge.angle, None
    for family in families:
        steps = round((edge.angle - family) / _RIGHT_ANGLE)
        snapped = family + steps * _RIGHT_ANGLE
        difference = (edge.angle - snapped + math.pi) % (2 * math.pi) - math.pi
        if best_difference is None or abs(difference) < abs(best_difference):
            best_angle, best_difference = snapped, difference
    if best_difference is None or abs(best_difference) > tolerance:
        return edge.angle, False
    if max_offset is not None and 0.5 * edge.length * abs(math.sin(best_difference)) > max_offset:
        return edge.angle, False
    return best_angle, True


def _drop_chamfers(
    edges: list[_Edge], aligned: list[bool], max_length: float
) -> list[int]:
    """Raster artigi pahlarin indekslerini bulur (bkz. modul docstring'i)."""
    count = len(edges)
    dropped = []
    for i, edge in enumerate(edges):
        if aligned[i] or edge.length > max_length:
            continue
        between = _angle_between(edges[i - 1].angle, edges[(i + 1) % count].angle)
        if CHAMFER_NEIGHBOUR_MIN_DEG <= between <= CHAMFER_NEIGHBOUR_MAX_DEG:
            dropped.append(i)
    return dropped


def _line(point: tuple[float, float], angle: float) -> tuple[float, float, float]:
    """Dogruyu (normal_x, normal_y, offset) olarak verir: n . x = offset."""
    nx, ny = -math.sin(angle), math.cos(angle)
    return nx, ny, nx * point[0] + ny * point[1]


def _intersect(a: tuple[float, float, float], b: tuple[float, float, float]):
    determinant = a[0] * b[1] - a[1] * b[0]
    if abs(determinant) < PARALLEL_EPSILON:
        return None
    x = (a[2] * b[1] - a[1] * b[2]) / determinant
    y = (a[0] * b[2] - a[2] * b[0]) / determinant
    return x, y


def _rebuild_corners(
    edges: list[_Edge], angles: list[float], max_shift: float
) -> list[tuple[float, float]]:
    """Koseleri ardisik kenar dogrularinin kesisimi olarak yeniden kurar.

    Kose i, (i-1). ve i. kenarin kesisimidir. Kesisim yoksa (neredeyse
    paralel) ya da cok uzaga dustuyse iki kenarin arasindaki gercek
    nokta -- pah atilmamissa eski kose, atilmissa pahin ortasi --
    kullanilir."""
    lines = [_line(edge.midpoint, angle) for edge, angle in zip(edges, angles)]
    corners = []
    for i, line in enumerate(lines):
        point = _intersect(lines[i - 1], line)
        previous, current = edges[i - 1], edges[i]
        fallback = (
            (previous.end[0] + current.start[0]) / 2.0,
            (previous.end[1] + current.start[1]) / 2.0,
        )
        limit = CORNER_SHIFT_FACTOR * max_shift + _distance(previous.end, current.start)
        if point is None or math.hypot(point[0] - fallback[0], point[1] - fallback[1]) > limit:
            corners.append(fallback)
        else:
            corners.append(point)
    return corners


def _is_simple(points: list[tuple[float, float]]) -> bool:
    """Poligon kendi kendini kesmiyor mu (OGC anlaminda gecerli mi)?"""
    if len(points) < 3:
        return False
    return Polygon(points).is_valid


def grid_angles(
    polylines: list[list[tuple[float, float]]],
    locked: list[list[bool]] | None = None,
) -> list[float] | None:
    """Bir polyline kumesinin ortak izgara aileleri (bkz. `_grid_families`).

    Aileler BLOK bazinda (dis hat + ic bolme duvarlari birlikte) bulunur:
    her hucreyi kendi basina ele almaya gore hem daha kararlidir (daha cok
    kenardan olculur) hem de ayni dogrultudaki komsu hucrelerin AYNI aciya
    oturmasini garanti eder.

    `locked` verilirse o segmentler hesaba KATILMAZ: pafta kenarindaki
    kapanis cizgileri binanin izgarasina ait degildir ve dahil edilirse
    aileleri kendilerine dogru cekerler."""
    edges: list[_Edge] = []
    for index, polyline in enumerate(polylines):
        own = _edges_open([(float(x), float(y)) for x, y in polyline])
        if locked is not None:
            flags = locked[index]
            own = [e for i, e in enumerate(own) if not (i < len(flags) and flags[i])]
        edges.extend(own)
    if not edges:
        return None
    return _grid_families(edges) or None


def _edges_open_indexed(polyline: list[tuple[float, float]]) -> list[tuple[int, _Edge]]:
    """Acik polyline'in segmentleri, kaynak indeksiyle (bkz. `_edges_indexed`)."""
    result = []
    for i in range(len(polyline) - 1):
        edge = _Edge(polyline[i], polyline[i + 1])
        if edge.length >= 1e-9:
            result.append((i, edge))
    return result


def _edges_open(polyline: list[tuple[float, float]]) -> list[_Edge]:
    """Acik bir polyline'in segmentleri (kapali poligondan farkli olarak
    son noktadan ilkine donen kenar YOKTUR)."""
    return [edge for _, edge in _edges_open_indexed(polyline)]


def _apply_locks(
    edges: list[_Edge], indices: list[int], angles: list[float],
    aligned: list[bool], locked: list[bool] | None,
) -> None:
    """KILITLI segmentleri kendi dogrultusunda birakir (yerinde degistirir).

    Kilitli kenar bir duvar degildir -- ornegin pafta kenarindaki kapanis
    cizgisi. Izgaraya oturtulursa kaynakta hic olmayan bir egim kazanir ve
    kesilmis binanin taban kenari doner. `aligned=True` isaretlenmesi ayni
    zamanda onu pah temizliginin disinda tutar."""
    if locked is None:
        return
    for position, source_index in enumerate(indices):
        if source_index < len(locked) and locked[source_index]:
            angles[position] = edges[position].angle
            aligned[position] = True


def snap_edges(
    polyline: list[tuple[float, float]],
    dominant: float | list[float],
    angle_tolerance_deg: float = ANGLE_TOLERANCE_DEG,
    chamfer_max_length: float = 0.0,
    locked: list[bool] | None = None,
    max_shift: float | None = None,
) -> tuple[list[_Edge], list[float]]:
    """Acik bir polyline'in segmentlerini izgaraya oturtur ve pahlari atar.

    Nokta URETMEZ, yalnizca "hangi segmentler kaldi ve dogrultulari ne"
    bilgisini dondurur. Noktalarin yeniden kurulmasi `rebuild_open`in
    isidir; ikisi bilerek ayrilmistir, cunku arada bir adim daha vardir:
    polyline'in UCLARINDAKI dugumler baska polyline'larla paylasilir ve
    tek tek degil, o dugumde bulusan BUTUN segmentlere birlikte bakilarak
    hesaplanmalidir (bkz. `solve_node`).

    Uc segmentler de pah olabilir ve atilabilir -- ki bina koselerinin
    buyuk cogunlugu tam da bir dugumun dibindedir (olculdu: kalan
    pahlarin %84'u). Atilan uc segment, o dugumun konumunu artik
    belirlemez; dugum bir iceriki gercek duvarin dogrultusuna oturur.
    """
    indexed = _edges_open_indexed([(float(x), float(y)) for x, y in polyline])
    if not indexed:
        return [], []
    indices = [i for i, _ in indexed]
    edges = [e for _, e in indexed]

    tolerance = math.radians(angle_tolerance_deg)
    snapped = [_snap(e, dominant, tolerance, max_shift) for e in edges]
    angles = [a for a, _ in snapped]
    aligned = [ok for _, ok in snapped]
    _apply_locks(edges, indices, angles, aligned, locked)

    if chamfer_max_length > 0 and len(edges) >= 3:
        dropped = set(_drop_chamfers_open(edges, aligned, chamfer_max_length))
        # Uc segmentler: komsusu tek tarafta oldugu icin ayri bakilir.
        for i in (0, len(edges) - 1):
            neighbour = 1 if i == 0 else len(edges) - 2
            if aligned[i] or edges[i].length > chamfer_max_length or neighbour in dropped:
                continue
            if CHAMFER_NEIGHBOUR_MIN_DEG <= _angle_between(
                edges[i].angle, edges[neighbour].angle
            ) <= CHAMFER_NEIGHBOUR_MAX_DEG:
                dropped.add(i)
        if dropped and len(edges) - len(dropped) >= 1:
            keep = [i for i in range(len(edges)) if i not in dropped]
            edges = [edges[i] for i in keep]
            angles = [angles[i] for i in keep]

    return edges, angles


def edge_line(edge: _Edge, angle: float) -> tuple[float, float, float]:
    """Segmentin ortasindan gecen, oturtulmus dogrultudaki dogru."""
    return _line(edge.midpoint, angle)


def solve_node(
    lines: list[tuple[float, float, float]],
    original: tuple[float, float],
    max_shift: float,
) -> tuple[float, float]:
    """Bir dugumun yeni konumu: orada bulusan dogrulara en yakin nokta.

    Dugum birden fazla polyline tarafindan PAYLASILIR; her biri kendi
    ucunu ayri hesaplasa ag koparadi. Bu yuzden konum bir kez, o dugumde
    bulusan butun segment dogrularinin en kucuk kareler cozumu olarak
    bulunur ve butun paylasanlar ayni sayiyi kullanir -- topoloji boylece
    korunur.

    Iki dik duvarin bulustugu bir dugumde cozum tam kose noktasidir
    (kose sivrilesir). Bir T kavsaginda (dumduz devam eden dis hat +
    dik bir bolme duvari) cozum yine dogru yerdedir. Butun dogrular
    paralelse (dejenere) ya da sonuc cok uzaga duserse dugum yerinde
    birakilir.
    """
    if len(lines) < 2:
        return original

    a11 = sum(n[0] * n[0] for n in lines)
    a12 = sum(n[0] * n[1] for n in lines)
    a22 = sum(n[1] * n[1] for n in lines)
    b1 = sum(n[2] * n[0] for n in lines)
    b2 = sum(n[2] * n[1] for n in lines)

    determinant = a11 * a22 - a12 * a12
    if abs(determinant) < PARALLEL_EPSILON:
        return original
    x = (b1 * a22 - a12 * b2) / determinant
    y = (a11 * b2 - b1 * a12) / determinant
    if _distance((x, y), original) > max_shift:
        return original
    return x, y


def rebuild_open(
    edges: list[_Edge],
    angles: list[float],
    start: tuple[float, float],
    end: tuple[float, float],
    max_shift: float,
) -> list[tuple[float, float]]:
    """Uclari VERILEN acik polyline'i yeniden kurar.

    Ic noktalar ardisik segment dogrularinin kesisimidir (kose sivrilesir);
    uclar cagirandan gelir, cunku onlar paylasilan dugumlerdir."""
    if not edges:
        return [start, end]
    lines = [edge_line(edge, angle) for edge, angle in zip(edges, angles)]
    result = [start]
    for i in range(1, len(edges)):
        point = _intersect(lines[i - 1], lines[i])
        previous, current = edges[i - 1], edges[i]
        fallback = (
            (previous.end[0] + current.start[0]) / 2.0,
            (previous.end[1] + current.start[1]) / 2.0,
        )
        limit = CORNER_SHIFT_FACTOR * max_shift + _distance(previous.end, current.start)
        if point is None or _distance(point, fallback) > limit:
            result.append(fallback)
        else:
            result.append(point)
    result.append(end)
    return result


def snap_polyline_to_axes(
    points: list[tuple[float, float]],
    dominant: float | list[float],
    max_shift: float,
    angle_tolerance_deg: float = ANGLE_TOLERANCE_DEG,
    chamfer_max_length: float = 0.0,
    locked: list[bool] | None = None,
) -> list[tuple[float, float]]:
    """Acik bir polyline'i verilen izgaraya oturtur; UCLARI SABIT tutar.

    Uclar grafin dugumleridir ve komsu polyline'larla paylasilir; onlari
    oynatmak agi koparir. Ic noktalar ise ardisik segment DOGRULARININ
    kesisimi olarak yeniden kurulur, yani kose sivrilesir.

    Bu, `snap_to_dominant_axes`in ag (planar graf) uzerinde calisan
    karsiligidir: her fiziksel cizgi bir kez oturtuldugu icin o cizgiyi
    paylasan komsu hucreler ayni geometriyi miras alir ve aralarinda
    bosluk acilmaz (bkz. geometry.square_network).
    """
    polyline = [(float(x), float(y)) for x, y in points]
    if len(polyline) < 3:
        return polyline

    # Kapali dongu (izole bina): baslangic noktasi da bir kosedir, halka
    # olarak islenirse o da sivrilesir.
    if _distance(polyline[0], polyline[-1]) < 1e-9:
        # Halkanin i. kenari, girdi dizisinin i. segmentiyle ayni (son
        # nokta ilkine esit oldugu icin sarma kenari da denk gelir), yani
        # `locked` oldugu gibi gecirilebilir.
        ring = snap_to_dominant_axes(
            polyline[:-1], max_shift, angle_tolerance_deg, chamfer_max_length,
            dominant=dominant, locked=locked,
        )
        return list(ring) + [ring[0]]

    indexed = _edges_open_indexed(polyline)
    if len(indexed) < 2:
        return polyline
    indices = [i for i, _ in indexed]
    edges = [e for _, e in indexed]

    tolerance = math.radians(angle_tolerance_deg)
    snapped = [_snap(e, dominant, tolerance, max_shift) for e in edges]
    angles = [a for a, _ in snapped]
    aligned = [ok for _, ok in snapped]
    _apply_locks(edges, indices, angles, aligned, locked)

    if chamfer_max_length > 0:
        # Uc segmentlere dokunulmaz: onlari atmak dugumu oynatirdi.
        dropped = {
            i for i in _drop_chamfers_open(edges, aligned, chamfer_max_length)
            if 0 < i < len(edges) - 1
        }
        if dropped and len(edges) - len(dropped) >= 2:
            keep = [i for i in range(len(edges)) if i not in dropped]
            edges = [edges[i] for i in keep]
            angles = [angles[i] for i in keep]

    lines = [_line(edge.midpoint, angle) for edge, angle in zip(edges, angles)]
    result = [polyline[0]]
    for i in range(1, len(edges)):
        point = _intersect(lines[i - 1], lines[i])
        previous, current = edges[i - 1], edges[i]
        fallback = (
            (previous.end[0] + current.start[0]) / 2.0,
            (previous.end[1] + current.start[1]) / 2.0,
        )
        limit = CORNER_SHIFT_FACTOR * max_shift + _distance(previous.end, current.start)
        if point is None or _distance(point, fallback) > limit:
            result.append(fallback)
        else:
            result.append(point)
    result.append(polyline[-1])
    return result


def _drop_chamfers_open(
    edges: list[_Edge], aligned: list[bool], max_length: float
) -> list[int]:
    """`_drop_chamfers`in acik polyline karsiligi (dongusel komsu yok)."""
    dropped = []
    for i in range(1, len(edges) - 1):
        if aligned[i] or edges[i].length > max_length:
            continue
        between = _angle_between(edges[i - 1].angle, edges[i + 1].angle)
        if CHAMFER_NEIGHBOUR_MIN_DEG <= between <= CHAMFER_NEIGHBOUR_MAX_DEG:
            dropped.append(i)
    return dropped


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def snap_to_dominant_axes(
    points: list[tuple[float, float]],
    max_shift: float,
    angle_tolerance_deg: float = ANGLE_TOLERANCE_DEG,
    chamfer_max_length: float = 0.0,
    dominant: float | list[float] | None = None,
    locked: list[bool] | None = None,
) -> list[tuple[float, float]]:
    """Kapali poligonu baskin izgarasina oturtur (bkz. modul docstring).

    `points` kapali poligonun koseleridir (son nokta ilkine esit degil).
    `max_shift`: bir kosenin en fazla ne kadar oteye tasinabilecegi (px).
    `chamfer_max_length`: bu uzunlugun altindaki raster artigi capraz
    kenarlar atilir (px); 0 verilirse pah temizligi yapilmaz.
    `dominant`: izgara yonu ya da aileleri; verilmezse poligonun kendi
    kenarlarindan hesaplanir.
    """
    polygon = [(float(x), float(y)) for x, y in points]
    if len(polygon) < 4:
        return polygon

    indexed = _edges_indexed(polygon)
    if len(indexed) < 4:
        return polygon
    indices = [i for i, _ in indexed]
    edges = [e for _, e in indexed]

    if dominant is None:
        dominant = _grid_families(edges)
    tolerance = math.radians(angle_tolerance_deg)
    snapped = [_snap(e, dominant, tolerance, max_shift) for e in edges]
    angles = [a for a, _ in snapped]
    aligned = [ok for _, ok in snapped]
    _apply_locks(edges, indices, angles, aligned, locked)

    # Once pahlar temizlenmis haliyle, sonra pahlar korunarak dene; ikisi de
    # kendi uzerine katlanirsa girdiyi oldugu gibi birak (bkz. docstring).
    attempts = []
    if chamfer_max_length > 0:
        dropped = set(_drop_chamfers(edges, aligned, chamfer_max_length))
        if dropped and len(edges) - len(dropped) >= 4:
            keep = [i for i in range(len(edges)) if i not in dropped]
            attempts.append(([edges[i] for i in keep], [angles[i] for i in keep]))
    attempts.append((edges, angles))

    for attempt_edges, attempt_angles in attempts:
        corners = _rebuild_corners(attempt_edges, attempt_angles, max_shift)
        if _is_simple(corners):
            return corners
    return polygon
