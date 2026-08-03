"""
pyKalfa / Parsel-Bina - bina poligonlarini kendi izgarasina oturtma

Raster bir cizimden cikarilan kontur, gercekte dumduz olan bir duvari
"merdiven" basamaklariyla temsil eder. `cv2.approxPolyDP` basamaklari
temizler ama kenarin acisini bir-iki derece kaydirir ve dik koseleri
pahlar; sonucta Revit'e giden dortgenler yamuk gorunur.

Bu modul son bir duzeltme yapar: binanin BASKIN yonu bulunur, her kenar
o yone gore 90 derecelik izgaranin en yakin dogrultusuna oturtulur ve
koseler ardisik kenar dogrularinin KESISIMI olarak yeniden hesaplanir.
Boylece duvarlar birbirine tam paralel/dik olur ve koseler keskin kalir.

Bilincli sinirlar:

  - Izgaraya oturtma yalniz `ANGLE_TOLERANCE_DEG` icindeki kenarlara
    uygulanir. Gercekten egik bir duvar (kadastroda sik) zorla dikeye
    cevrilmez.
  - Yeni kose eskisinden `max_shift` pikselden fazla uzaga duserse eski
    kose korunur. Cok kisa kenarlarda iki dogru neredeyse paralel
    kesisip koseyi metrelerce oteye atabilir; bu koruma onu engeller.
"""

from __future__ import annotations

import math

ANGLE_TOLERANCE_DEG = 20.0   # bu kadar sapmis kenar izgaraya cekilir, fazlasi egik kabul edilir
PARALLEL_EPSILON = 0.05      # iki dogru bu kadar paralelse kesisim aranmaz (sin(aci))

_RIGHT_ANGLE = math.pi / 2


def _dominant_angle(edges: list[tuple[float, float]]) -> float:
    """Kenarlarin uzunlukla agirlikli baskin dogrultusu (0-90 derece).

    Aci 4 ile carpilarak tam daireye tasinir: boylece 0 ile 90 derece
    (ayni izgaranin iki ekseni) ayni yone denk gelir ve dairesel ortalama
    90 derecelik sarmadan etkilenmez."""
    vx = sum(length * math.cos(4 * angle) for angle, length in edges)
    vy = sum(length * math.sin(4 * angle) for angle, length in edges)
    return math.atan2(vy, vx) / 4.0


def _snap(angle: float, dominant: float, tolerance: float) -> float:
    """Kenar acisini izgaranin en yakin eksenine oturtur (tolerans icindeyse)."""
    steps = round((angle - dominant) / _RIGHT_ANGLE)
    snapped = dominant + steps * _RIGHT_ANGLE
    difference = (angle - snapped + math.pi) % (2 * math.pi) - math.pi
    return snapped if abs(difference) <= tolerance else angle


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


def snap_to_dominant_axes(
    points: list[tuple[float, float]],
    max_shift: float,
    angle_tolerance_deg: float = ANGLE_TOLERANCE_DEG,
) -> list[tuple[float, float]]:
    """Kapali poligonu kendi baskin izgarasina oturtur (bkz. modul docstring).

    `points` kapali poligonun koseleridir (son nokta ilkine esit degil).
    `max_shift`: bir kosenin en fazla ne kadar oteye tasinabilecegi (px).
    """
    polygon = [(float(x), float(y)) for x, y in points]
    if len(polygon) < 4:
        return polygon

    count = len(polygon)
    edges = []
    for i in range(count):
        head, tail = polygon[i], polygon[(i + 1) % count]
        dx, dy = tail[0] - head[0], tail[1] - head[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        edges.append((math.atan2(dy, dx), length, ((head[0] + tail[0]) / 2.0, (head[1] + tail[1]) / 2.0)))
    if len(edges) < 4:
        return polygon

    dominant = _dominant_angle([(angle, length) for angle, length, _ in edges])
    tolerance = math.radians(angle_tolerance_deg)
    lines = [_line(midpoint, _snap(angle, dominant, tolerance)) for angle, _, midpoint in edges]

    # Kose i, (i-1). ve i. kenarin kesisimidir; kenar sayisi sifir uzunluklu
    # kenarlar atildigi icin poligonun kose sayisindan az olabilir, bu yuzden
    # koseler kenar dizisi uzerinden yeniden kurulur.
    corners = []
    for i, line in enumerate(lines):
        previous = lines[i - 1]
        point = _intersect(previous, line)
        # Kesisim yoksa (neredeyse paralel) ya da cok uzaga dustuyse iki kenarin
        # ortak ucunu (yani eski koseyi) kullan.
        fallback = (
            (edges[i - 1][2][0] + edges[i][2][0]) / 2.0,
            (edges[i - 1][2][1] + edges[i][2][1]) / 2.0,
        )
        if point is None or math.hypot(point[0] - fallback[0], point[1] - fallback[1]) > max_shift + _half_span(edges, i):
            corners.append(fallback)
        else:
            corners.append(point)
    return corners


def _half_span(edges, index: int) -> float:
    """Kose kaymasi olcusunun referansi: kesisen iki kenarin yari uzunlugu.

    Kesisim noktasi dogal olarak kenarlarin ORTASINDAN degil UCUNDAN gecer;
    "ne kadar uzaga dustu" olcusu bu yuzden kenar uzunlugunu de icermelidir,
    yoksa uzun kenarlarda dogru kesisimler de reddedilirdi."""
    return (edges[index - 1][1] + edges[index][1]) / 2.0
