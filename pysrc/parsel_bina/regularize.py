"""
pyKalfa / Parsel-Bina - bina poligonlarini kendi izgarasina oturtma

Raster bir cizimden cikarilan kontur, gercekte dumduz olan bir duvari
"merdiven" basamaklariyla temsil eder. `cv2.approxPolyDP` basamaklari
temizler ama iki bedel oder:

  1. Kenarin acisini bir-iki derece kaydirir, dik koseler yamulur.
  2. Bir kosedeki basamak yigilmasini TEK bir kisa capraz kenarla
     degistirir -- yani keskin kose, pahli (kesik) bir koseye doner.

Bu modul ikisini de duzeltir:

  - **Izgaraya oturtma**: poligonun BASKIN yonu bulunur, her kenar o yone
    gore 90 derecelik izgaranin en yakin dogrultusuna oturtulur ve koseler
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
  - Yeni kose eskisinden `max_shift` pikselden fazla uzaga duserse eski
    kose korunur. Cok kisa kenarlarda iki dogru neredeyse paralel
    kesisip koseyi metrelerce oteye atabilir; bu koruma onu engeller.
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


def _edges(polygon: list[tuple[float, float]]) -> list[_Edge]:
    """Kapali poligonun kenarlari (sifir uzunluklu olanlar atilir)."""
    count = len(polygon)
    result = []
    for i in range(count):
        edge = _Edge(polygon[i], polygon[(i + 1) % count])
        if edge.length >= 1e-9:
            result.append(edge)
    return result


def _dominant_angle(edges: list[_Edge]) -> float:
    """Kenarlarin uzunlukla agirlikli baskin dogrultusu (0-90 derece).

    Aci 4 ile carpilarak tam daireye tasinir: boylece 0 ile 90 derece
    (ayni izgaranin iki ekseni) ayni yone denk gelir ve dairesel ortalama
    90 derecelik sarmadan etkilenmez."""
    vx = sum(e.length * math.cos(4 * e.angle) for e in edges)
    vy = sum(e.length * math.sin(4 * e.angle) for e in edges)
    return math.atan2(vy, vx) / 4.0


def _angle_between(first: float, second: float) -> float:
    """Iki dogrultu arasindaki aci, derece (0-180)."""
    return math.degrees(abs((second - first + math.pi) % (2 * math.pi) - math.pi))


def _snap(angle: float, dominant: float, tolerance: float) -> tuple[float, bool]:
    """Kenar acisini izgaranin en yakin eksenine oturtur.

    `(aci, izgaraya_oturdu_mu)` doner; tolerans disindaysa aci degismez."""
    steps = round((angle - dominant) / _RIGHT_ANGLE)
    snapped = dominant + steps * _RIGHT_ANGLE
    difference = (angle - snapped + math.pi) % (2 * math.pi) - math.pi
    if abs(difference) <= tolerance:
        return snapped, True
    return angle, False


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
        limit = max_shift + (previous.length + current.length) / 2.0
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


def dominant_angle(polylines: list[list[tuple[float, float]]]) -> float | None:
    """Bir polyline kumesinin ortak baskin izgara yonu.

    Bir bina BLOGUNUN butun cizgileri (dis hat + ic bolme duvarlari) tek
    bir izgaraya oturur; blok bazinda tek bir aci hesaplamak, her hucreyi
    kendi basina oturtmaya gore hem daha kararlidir (daha cok kenardan
    ortalama alinir) hem de komsu hucrelerin AYNI aciya oturmasini
    garanti eder."""
    edges: list[_Edge] = []
    for polyline in polylines:
        edges.extend(_edges_open([(float(x), float(y)) for x, y in polyline]))
    if not edges:
        return None
    return _dominant_angle(edges)


def _edges_open(polyline: list[tuple[float, float]]) -> list[_Edge]:
    """Acik bir polyline'in segmentleri (kapali poligondan farkli olarak
    son noktadan ilkine donen kenar YOKTUR)."""
    result = []
    for i in range(len(polyline) - 1):
        edge = _Edge(polyline[i], polyline[i + 1])
        if edge.length >= 1e-9:
            result.append(edge)
    return result


def snap_edges(
    polyline: list[tuple[float, float]],
    dominant: float,
    angle_tolerance_deg: float = ANGLE_TOLERANCE_DEG,
    chamfer_max_length: float = 0.0,
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
    edges = _edges_open([(float(x), float(y)) for x, y in polyline])
    if not edges:
        return [], []

    tolerance = math.radians(angle_tolerance_deg)
    snapped = [_snap(e.angle, dominant, tolerance) for e in edges]
    angles = [a for a, _ in snapped]
    aligned = [ok for _, ok in snapped]

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
        limit = max_shift + (previous.length + current.length) / 2.0
        if point is None or _distance(point, fallback) > limit:
            result.append(fallback)
        else:
            result.append(point)
    result.append(end)
    return result


def snap_polyline_to_axes(
    points: list[tuple[float, float]],
    dominant: float,
    max_shift: float,
    angle_tolerance_deg: float = ANGLE_TOLERANCE_DEG,
    chamfer_max_length: float = 0.0,
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
        ring = snap_to_dominant_axes(
            polyline[:-1], max_shift, angle_tolerance_deg, chamfer_max_length,
            dominant=dominant,
        )
        return list(ring) + [ring[0]]

    edges = _edges_open(polyline)
    if len(edges) < 2:
        return polyline

    tolerance = math.radians(angle_tolerance_deg)
    snapped = [_snap(e.angle, dominant, tolerance) for e in edges]
    angles = [a for a, _ in snapped]
    aligned = [ok for _, ok in snapped]

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
        limit = max_shift + (previous.length + current.length) / 2.0
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
    dominant: float | None = None,
) -> list[tuple[float, float]]:
    """Kapali poligonu baskin izgarasina oturtur (bkz. modul docstring).

    `points` kapali poligonun koseleridir (son nokta ilkine esit degil).
    `max_shift`: bir kosenin en fazla ne kadar oteye tasinabilecegi (px).
    `chamfer_max_length`: bu uzunlugun altindaki raster artigi capraz
    kenarlar atilir (px); 0 verilirse pah temizligi yapilmaz.
    `dominant`: izgara yonu; verilmezse poligonun kendi kenarlarindan
    hesaplanir.
    """
    polygon = [(float(x), float(y)) for x, y in points]
    if len(polygon) < 4:
        return polygon

    edges = _edges(polygon)
    if len(edges) < 4:
        return polygon

    if dominant is None:
        dominant = _dominant_angle(edges)
    tolerance = math.radians(angle_tolerance_deg)
    snapped = [_snap(e.angle, dominant, tolerance) for e in edges]
    angles = [a for a, _ in snapped]
    aligned = [ok for _, ok in snapped]

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
