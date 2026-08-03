"""
pyKalfa / Parsel-Bina - iskelet polyline'lari icin temizleme katmani

`geometry._skeleton_to_polylines` piksel piksel izlenmis ham bir cizgi
grafigi dondurur. Bu graf dogru (her fiziksel cizgi tam bir kez) ama
"kirli"dir:

  - Skeletonize, kalin cizgilerin kose/kesisim bolgelerinde birbirine
    1-2 piksel uzaklikta BIRDEN FAZLA dugum uretir; ayni kavsak bu yuzden
    graf uzerinde iki ayri node gibi gorunur.
  - Ayni bolgelerde cizgi disina dogru birkac piksellik kor uclu
    cikintilar (spur) olusur; bunlar Revit'te tek basina anlamsiz kisa
    DetailLine'lara doner.
  - Iki dugum arasindaki her yol ayri bir polyline oldugu icin, aslinda
    tek ve duz olan bir parsel siniri sirf uzerinden baska bir dugum
    gectigi icin parcalanir -> gereksiz cok sayida DetailLine.
  - Raster "merdiven" basamaklari yuzunden gercekte dumduz olan kenarlar
    onlarca kucuk zigzag noktasindan olusur.

Bu modul bu sorunlari bagimsiz, sirayla uygulanan katmanlar halinde
cozer (bkz. `clean_polylines`). Butun esik degerleri `CleanupConfig`
uzerinden gelir ve **her esik 0 (veya negatif) verilerek kapatilabilir**;
boylece bir katmanin davranisini olcmek/geri almak icin kodu degistirmeye
gerek kalmaz.

Bilincli sinirlar:

  - Aci normalizasyonu (`normalize_angles`) yalnizca polyline'in IC
    noktalarini oynatir; ilk/son nokta grafin baska polyline'lariyla
    paylasilan dugumdur ve sabit kalir. Aksi halde bir cizgiyi dikeye
    oturtmak komsu cizgiyle olan baglantiyi koparirdi.
  - Bu yuzden aci normalizasyonu varsayilan olarak KAPALIDIR ve sadece
    bina katmaninda acilir (parsel sinirlari dogal olarak egik ve dik
    acili olmayan cokgenlerdir -- bkz. regularize.py).
  - Buradaki sadelestirme piksel uzayinda ve kucuk toleransli, "gurultu
    temizligi" duzeyindedir; gercek-dunya toleransiyla (30 cm) yapilan
    esas sadelestirme prepare_revit_input.py'de kalir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

Point = tuple[float, float]
Polyline = list[Point]

MAX_PRUNE_PASSES = 4  # bir spur silinince komsusu spur olabilir; birkac gecis yeter
_EPSILON = 1e-9


@dataclass(frozen=True)
class CleanupConfig:
    """Temizleme katmanlarinin esikleri. Her esik icin 0 = o katman kapali.

    junction_radius_px:
        Bu yaricap icindeki polyline UCLARI tek bir dugume (kumeciklerin
        agirlik merkezine) indirgenir. Skeletonize'in kavsaklarda urettigi
        1-2 piksellik ikiz dugumleri birlestirir.
    min_spur_length_px:
        Serbest (baska hicbir polyline'in degmedigi) bir ucu olan ve bu
        uzunluktan kisa polyline'lar silinir.
    join_chains:
        Tam iki polyline'in birlestigi dugumler gercek bir kavsak degil,
        yalnizca izleme sirasinda olusmus bir kesme noktasidir; bu
        dugumlerdeki polyline'lar tek bir uzun polyline'a baglanir.
    collinear_tolerance_deg:
        Ardisik iki segment arasindaki donus acisi bu degerin altindaysa
        aradaki nokta atilir (ayni dogrultudaki segmentler birlesir).
    simplify_tolerance_px:
        `cv2.approxPolyDP` toleransi (piksel) -- merdiven zigzaglarini
        temizler. Polyline uclari (paylasilan dugumler) korunur.
    axis_tolerance_deg / axis_step_deg:
        Bir segmentin acisi `axis_step_deg`in katlarina (varsayilan 45 ->
        0/45/90/135 derece) bu tolerans icinde yakinsa segment tam o
        aciya oturtulur. Sadece ic noktalar oynatilir (bkz. modul
        docstring'i). Varsayilan 0 = kapali.
    snap_tolerance_px:
        Son adim: bu mesafeden yakin butun noktalar tek bir koordinatta
        birlestirilir; boylece komsu cizgilerin paylastigi noktalar
        birebir ayni sayilara oturur.
    """

    junction_radius_px: float = 2.0
    min_spur_length_px: float = 10.0
    join_chains: bool = True
    collinear_tolerance_deg: float = 5.0
    simplify_tolerance_px: float = 1.0
    axis_tolerance_deg: float = 0.0
    axis_step_deg: float = 45.0
    snap_tolerance_px: float = 1.0


# --- Yardimcilar -------------------------------------------------------------


def _as_float(polylines: list[list[tuple[float, float]]]) -> list[Polyline]:
    """Girdiyi (piksel tuple'lari ya da numpy sayilari olabilir) float
    noktalara cevirir; nokta esitligi sonraki adimlarda dugum kimligi
    olarak kullanildigi icin tip birligi sart."""
    return [[(float(x), float(y)) for x, y in polyline] for polyline in polylines]


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(polyline: Polyline) -> float:
    return sum(_distance(polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))


def _dedupe_consecutive(polyline: Polyline) -> Polyline:
    """Ust uste dusmus ardisik noktalari teke indirir (kapanis noktasi korunur)."""
    result = [polyline[0]]
    for point in polyline[1:]:
        if _distance(point, result[-1]) > _EPSILON:
            result.append(point)
    return result


def _cluster_map(points: list[Point], radius: float) -> dict[Point, Point]:
    """Birbirine `radius`tan yakin noktalari ortak bir temsilciye (kumenin
    agirlik merkezi) esleyen sozluk dondurur.

    Kume aramasi `radius` boyutlu bir izgara uzerinden yapilir: bir nokta
    yalnizca kendi ve komsu 8 hucredeki mevcut kume CIPASINA bakilarak
    eslenir. Cipa (kumenin ilk noktasi) sabit kalir, agirlik merkezi en
    sonda hesaplanir; boylece kumeler izgara uzerinde kaymaz ve bir kume
    hicbir zaman 2*radius'tan genis olmaz (yan yana dizili noktalarin
    zincirleme tek kumeye cokmesi engellenir).
    """
    if radius <= 0:
        return {}

    anchors: list[Point] = []
    members: list[list[Point]] = []
    buckets: dict[tuple[int, int], list[int]] = {}
    assigned: dict[Point, int] = {}

    for point in points:
        if point in assigned:
            continue  # ayni koordinat -> zaten ayni temsilci
        gx, gy = int(math.floor(point[0] / radius)), int(math.floor(point[1] / radius))
        found = -1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for index in buckets.get((gx + dx, gy + dy), ()):
                    if _distance(point, anchors[index]) <= radius:
                        found = index
                        break
                if found >= 0:
                    break
            if found >= 0:
                break
        if found < 0:
            found = len(anchors)
            anchors.append(point)
            members.append([])
            buckets.setdefault((gx, gy), []).append(found)
        members[found].append(point)
        assigned[point] = found

    centroids = [
        (sum(p[0] for p in group) / len(group), sum(p[1] for p in group) / len(group))
        for group in members
    ]
    return {point: centroids[index] for point, index in assigned.items()}


def _is_closed(polyline: Polyline) -> bool:
    return len(polyline) > 2 and _distance(polyline[0], polyline[-1]) <= _EPSILON


# --- Katmanlar ---------------------------------------------------------------


def merge_junction_nodes(polylines: list[Polyline], config: CleanupConfig) -> list[Polyline]:
    """Birbirine cok yakin polyline uclarini tek bir dugume indirger.

    Skeletonize kalin bir cizginin kavsaginda genelde tek bir dugum degil,
    1-2 piksel arayla birkac dugum birakir. Bunlar `polygonize` icin ayri
    node'lardir: aralarinda kil payi bir bosluk kalir ve o kavsakta kapanmasi
    gereken hucre (bina birimi) kapanmayabilir. Uclari ortak agirlik
    merkezine tasimak bu bosluklari kapatir ve grafin dugum sayisini dusurur.
    """
    lines = _as_float(polylines)
    if config.junction_radius_px <= 0:
        return lines

    endpoints = [p[0] for p in lines if p] + [p[-1] for p in lines if p]
    mapping = _cluster_map(endpoints, config.junction_radius_px)

    result: list[Polyline] = []
    for polyline in lines:
        if len(polyline) < 2:
            continue
        points = list(polyline)
        points[0] = mapping.get(points[0], points[0])
        points[-1] = mapping.get(points[-1], points[-1])
        points = _dedupe_consecutive(points)
        if len(points) >= 2:
            result.append(points)
    return result


def prune_spurs(polylines: list[Polyline], config: CleanupConfig) -> list[Polyline]:
    """Agin disina dogru uzanan kisa kor cikintilari (spur) siler.

    Serbest uc = o koordinatta baska hicbir polyline ucu bulunmayan uc.
    Boyle bir ucu olan ve `min_spur_length_px`ten kisa polyline gercek bir
    cizgi degil, skeletonize artigidir. Kapali dongular (iki ucu ayni
    noktada) ve iki ucu da bagli polyline'lar -- ne kadar kisa olurlarsa
    olsunlar -- korunur: onlar agin tasiyici parcalaridir.

    Bir cikinti silininca onun tuttugu komsu parca da serbest kalabilir,
    bu yuzden islem birkac gecis boyunca tekrarlanir.
    """
    lines = _as_float(polylines)
    if config.min_spur_length_px <= 0:
        return lines

    for _ in range(MAX_PRUNE_PASSES):
        degree: dict[Point, int] = {}
        for polyline in lines:
            degree[polyline[0]] = degree.get(polyline[0], 0) + 1
            degree[polyline[-1]] = degree.get(polyline[-1], 0) + 1

        kept: list[Polyline] = []
        removed = False
        for polyline in lines:
            free_end = not _is_closed(polyline) and (
                degree[polyline[0]] == 1 or degree[polyline[-1]] == 1
            )
            if free_end and polyline_length(polyline) < config.min_spur_length_px:
                removed = True
                continue
            kept.append(polyline)
        lines = kept
        if not removed:
            break
    return lines


def _join_chains(polylines: list[Polyline]) -> list[Polyline]:
    """Tam iki polyline'in bulustugu dugumlerde zincirleri birlestirir.

    Boyle bir dugum gercek bir kavsak degildir: iskelet izleyicisi orada
    (ornegin bir piksel gecici olarak 3 komsulu gorundugu ya da araya bir
    spur girdigi icin) cizgiyi bosuna ikiye bolmustur. Birlestirme
    geometriyi degistirmez -- sadece ayni fiziksel cizgi tek bir polyline
    olur, dolayisiyla sonraki sadelestirme butun cizgiyi bir arada gorur ve
    Revit'te daha az, daha uzun DetailLine olusur.
    """
    ends: dict[Point, list[int]] = {}
    for index, polyline in enumerate(polylines):
        if _is_closed(polyline):
            continue
        ends.setdefault(polyline[0], []).append(index)
        ends.setdefault(polyline[-1], []).append(index)

    used = [False] * len(polylines)
    result: list[Polyline] = []
    for index, polyline in enumerate(polylines):
        if used[index]:
            continue
        used[index] = True
        chain = list(polyline)
        if _is_closed(polyline):
            result.append(chain)
            continue

        # Once bir yone, sonra (listeyi ters cevirip) diger yone uzat;
        # ikinci ters cevirme zinciri ilk yonune geri dondurur.
        for _ in range(2):
            while True:
                node = chain[-1]
                at_node = ends.get(node, ())
                candidates = [i for i in at_node if not used[i]]
                if len(at_node) != 2 or not candidates:
                    break
                other = list(polylines[candidates[0]])
                if _distance(other[-1], node) <= _EPSILON:
                    other.reverse()
                if _distance(other[0], node) > _EPSILON:
                    break
                used[candidates[0]] = True
                chain.extend(other[1:])
                if _is_closed(chain):
                    break
            chain.reverse()
        result.append(chain)
    return result


def drop_collinear_vertices(polyline: Polyline, tolerance_deg: float) -> Polyline:
    """Ardisik segmentlerin donus acisi tolerans altindaysa aradaki noktayi atar."""
    if tolerance_deg <= 0 or len(polyline) < 3:
        return list(polyline)
    result = [polyline[0]]
    for i in range(1, len(polyline) - 1):
        previous, current, following = result[-1], polyline[i], polyline[i + 1]
        turn = math.atan2(following[1] - current[1], following[0] - current[0]) - math.atan2(
            current[1] - previous[1], current[0] - previous[0]
        )
        turn_deg = abs(math.degrees((turn + math.pi) % (2 * math.pi) - math.pi))
        if turn_deg > tolerance_deg:
            result.append(current)
    result.append(polyline[-1])
    return result


def merge_collinear_segments(polylines: list[Polyline], config: CleanupConfig) -> list[Polyline]:
    """Ayni dogrultudaki parcalari tek bir cizgide toplar.

    Iki asamalidir: once graf duzeyinde zincirler birlestirilir
    (`_join_chains`), sonra her polyline icinde ayni dogrultuda devam eden
    ardisik segmentlerin arasindaki noktalar atilir.
    """
    lines = _as_float(polylines)
    if config.join_chains:
        lines = _join_chains(lines)
    merged = [drop_collinear_vertices(p, config.collinear_tolerance_deg) for p in lines]
    return [p for p in merged if len(p) >= 2]


def simplify_polylines(polylines: list[Polyline], config: CleanupConfig) -> list[Polyline]:
    """`cv2.approxPolyDP` ile merdiven zigzaglarini temizler.

    Douglas-Peucker acik bir polyline'in ILK ve SON noktasini her zaman
    korur; yani paylasilan dugumler yerinde kalir, ag kopmaz. Kapali
    dongulerde (paylasilan dugumu olmayan izole halkalar) kapanis noktasi
    ayrica geri eklenir.
    """
    lines = _as_float(polylines)
    if config.simplify_tolerance_px <= 0:
        return lines

    result: list[Polyline] = []
    for polyline in lines:
        closed = _is_closed(polyline)
        source = polyline[:-1] if closed else polyline
        if len(source) < 2:
            continue
        contour = np.array(source, dtype=np.float32).reshape(-1, 1, 2)
        simplified = cv2.approxPolyDP(contour, config.simplify_tolerance_px, closed).reshape(-1, 2)
        points = [(float(x), float(y)) for x, y in simplified]
        if closed and points:
            points.append(points[0])
        if len(points) >= 2:
            result.append(points)
    return result


def normalize_angles(polylines: list[Polyline], config: CleanupConfig) -> list[Polyline]:
    """Acisi 0/45/90 (genel olarak `axis_step_deg`in katlari) dogrultusuna
    yakin segmentleri tam o aciya oturtur.

    Yalnizca IC noktalar oynatilir: polyline'in ilk ve son noktasi grafin
    baska cizgileriyle paylasilan dugumdur, oynatilirsa ag kopar. Bu yuzden
    iki noktali (dugumden dugume) bir polyline hic degismez -- duzeltme
    ancak arasinda ic nokta kalan cizgilerde etkilidir.

    Segment uzunlugu, yeni yon vektorune izdusum alinarak korunur; boylece
    duzeltme cizgiyi uzatip kisaltmaz, sadece dondurur.
    """
    lines = _as_float(polylines)
    if config.axis_tolerance_deg <= 0 or config.axis_step_deg <= 0:
        return lines

    result: list[Polyline] = []
    for polyline in lines:
        points = list(polyline)
        last = len(points) - 1
        for i in range(last):
            head, tail = points[i], points[i + 1]
            dx, dy = tail[0] - head[0], tail[1] - head[1]
            if math.hypot(dx, dy) < _EPSILON:
                continue
            angle = math.degrees(math.atan2(dy, dx))
            target = round(angle / config.axis_step_deg) * config.axis_step_deg
            if abs((angle - target + 180.0) % 360.0 - 180.0) > config.axis_tolerance_deg:
                continue
            ux, uy = math.cos(math.radians(target)), math.sin(math.radians(target))
            extent = dx * ux + dy * uy
            if i + 1 != last:
                points[i + 1] = (head[0] + ux * extent, head[1] + uy * extent)
            elif i != 0:
                points[i] = (tail[0] - ux * extent, tail[1] - uy * extent)
        points = _dedupe_consecutive(points)
        if len(points) >= 2:
            result.append(points)
    return result


def snap_vertices(polylines: list[Polyline], config: CleanupConfig) -> list[Polyline]:
    """Birbirine cok yakin butun noktalari tek bir koordinata oturtur.

    Son adimdir: onceki katmanlar (ozellikle aci normalizasyonu) noktalari
    kil payi kaydirmis olabilir. Ayni koordinata oturan noktalar
    `shapely.ops.polygonize` icin de birebir ayni node olur; komsu iki bina
    biriminin ortak duvari boylece iki degil tek bir kenar kalir.

    Sadelestirmeden SONRA calistirilmalidir: ham iskelet polyline'larinda
    ardisik pikseller zaten 1 px arayladir, o asamada uygulanirsa cizgiyi
    kendi uzerine cokertir.
    """
    lines = _as_float(polylines)
    if config.snap_tolerance_px <= 0:
        return lines

    mapping = _cluster_map([point for line in lines for point in line], config.snap_tolerance_px)
    result: list[Polyline] = []
    for polyline in lines:
        points = _dedupe_consecutive([mapping.get(p, p) for p in polyline])
        if len(points) >= 2:
            result.append(points)
    return result


def clean_polylines(
    polylines: list[list[tuple[float, float]]], config: CleanupConfig | None = None
) -> list[Polyline]:
    """Butun temizleme katmanlarini sirayla uygular.

    Sira onemlidir:
      1. `merge_junction_nodes` - dugumler once tekillestirilir, cunku
         sonraki adimlarin hepsi "hangi uc hangi uca degiyor" bilgisine
         (nokta esitligine) dayanir.
      2. `prune_spurs`         - dugum dereceleri ancak tekillestirmeden
         sonra dogrudur.
      3. `merge_collinear_segments` - spur'lar silindikten sonra pek cok
         kavsak sirali bir devam noktasina doner ve zincirler birlesir.
      4. `simplify_polylines`  - artik uzun, butunlesik cizgiler uzerinde
         calisir.
      5. `normalize_angles`    - sadelestirilmis (az sayida, uzun) segmentler
         uzerinde anlamli.
      6. `snap_vertices`       - onceki adimlarin biraktigi kil payi
         kaymalari kapatilir.
    """
    config = config or CleanupConfig()
    lines = [p for p in _as_float(polylines) if len(p) >= 2]
    lines = merge_junction_nodes(lines, config)
    lines = prune_spurs(lines, config)
    lines = merge_collinear_segments(lines, config)
    lines = simplify_polylines(lines, config)
    lines = normalize_angles(lines, config)
    lines = snap_vertices(lines, config)
    return [p for p in lines if len(p) >= 2]
