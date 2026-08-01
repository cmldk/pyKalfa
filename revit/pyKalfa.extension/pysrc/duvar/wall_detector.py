"""
pyKalfa / Duvar - hangi cizim nesnesi duvar, ekseni nerede?

Bu modul, ilk surumdeki "her cizgi bir duvardir" varsayimini birakip
gercek kat plani ciktilarinin nasil cizildigine gore calisir.

## Neden degisti (gercek Polycam ciktisindan ogrenilenler)

`assets/simple.dxf` incelendiginde su cikti:

  - Bir duvar **iki ayri cizgi degil**, tek bir **kapali dis hat
    (outline) polyline'idir**: 6 noktali bir halka; iki uzun kenar
    duvarin iki yuzu, kisa kenarlar ise komsu duvarlarla birlesen
    (genelde gonyeli/mitered) uclardir.
  - Duvar kalinligi cizimde gercekten vardir (bu dosyada tam 0.100 m) --
    yani tahmin etmeye gerek yok, olculebilir.
  - Kapi, pencere ve gecisler (`Poly-Doors`, `Poly-Windows`,
    `Poly-Openings`) ayni formatta, ayni kalinlikta cizilir; onlari
    duvardan ayiran tek sey KATMANDIR.

"Her cizgi bir duvar" kurali bu yapida her fiziksel duvar icin iki ince
duvar (iki yuz) + kisa uc parcalari uretiyordu. Dogru okuma: **halkadan
merkez ekseni cikarmak.**

## Yontem

Bir halkanin en uzun iki kenari alinir. Bunlar
  - birbirine paralel,
  - zit yonlu (halka boyunca gidildigi icin),
  - aralarindaki dik mesafe (kalinlik) makul bir duvar araliginda,
  - ve uzunluk/kalinlik orani yeterince buyuk
ise bu bir duvar dis hattidir. Merkez eksen, karsilikli uc noktalarin
orta noktalarindan gecer; kalinlik da aradaki dik mesafedir.

Dis hat olmayan nesneler (tek cizgiler, mobilya konturlari, oda
poligonlari) duvar sayilmaz; bunlar "eslesmeyen" olarak ayri dondurulur
ve kullanici isterse (tek cizgiyle cizilmis planlar icin) geri donus
modunda eksen olarak kullanilabilir.

Faz 2'ye kalanlar: kapi/pencere bosluklarini duvardan cikarmak (Revit'te
kapi/pencere ailesi zaten duvari kestigi icin dusuk oncelikli), egri
(bulge) duvarlar, oda sinirlari.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Bir dis hattin duvar sayilmasi icin kalinlik bu aralikta olmali (metre).
# Alt sinir ince bolme/cam duvarlari, ust sinir kalin perde/istinat
# duvarlarini kapsar; oda poligonlari (metrelerce "kalinlik") bu testte
# elenir.
MIN_THICKNESS_M = 0.03
MAX_THICKNESS_M = 0.80

# Iki uzun kenarin paralel sayilmasi icin sinus toleransi (~1.1 derece).
PARALLEL_SIN_TOL = 0.02

# Uzunluk/kalinlik orani bunun altindaysa "duvar" degil, kare/kutu benzeri
# bir nesnedir (ör. bir kolon veya mobilya parcasi).
MIN_ASPECT_RATIO = 1.2

# Iki uzun kenarin uzunlugu birbirine yakin olmali; gonyeli uclarda
# aralarinda kalinlik kadar fark olabilir, bu yuzden oran toleransli.
MIN_EDGE_LENGTH_RATIO = 0.5

# Ayni duvarin tekrar tekrar cizilmis kopyalarini elemek icin konum
# toleransi (metre). Polycam ciktisinda her duvar iki kez yer aliyor.
DUPLICATE_TOL_M = 0.005


@dataclass
class WallCandidate:
    """Revit'te bir duvara donusecek eksen cizgisi (feet cinsinden)."""

    x1: float
    y1: float
    x2: float
    y2: float
    layer: str
    length_ft: float
    #: Cizimden OLCULEN duvar kalinligi (feet); tek cizgiden gelen
    #: adaylarda None (kalinlik kullanicinin sectigi WallType'tan gelir).
    thickness_ft: float = None
    #: "outline" (dis hattan olculdu) veya "line" (tek cizgi, geri donus)
    source: str = "outline"

    def to_dict(self) -> dict:
        return {
            "start": [self.x1, self.y1],
            "end": [self.x2, self.y2],
            "layer": self.layer,
            "length_ft": self.length_ft,
            "thickness_ft": self.thickness_ft,
            "source": self.source,
        }


def _edges(points):
    return [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def _edge_vector(edge):
    return (edge[1][0] - edge[0][0], edge[1][1] - edge[0][1])


def _edge_length(edge):
    dx, dy = _edge_vector(edge)
    return math.hypot(dx, dy)


def outline_to_centerline(points, feet_per_meter):
    """Kapali bir halkadan (merkez_eksen, kalinlik) cikarir.

    Duvar dis hattina benzemiyorsa None dondurur. Uzunluklar cagiranin
    birimindedir (feet); kalinlik esikleri metreden cevrilir."""
    if len(points) < 4:
        return None

    edges = _edges(points)
    if len(edges) < 4:
        return None

    order = sorted(range(len(edges)), key=lambda i: -_edge_length(edges[i]))
    i, j = order[0], order[1]

    # En uzun iki kenar komsu olmamali: bir duvarin iki yuzu halkanin
    # karsilikli kenarlaridir. (Komsu cikiyorsa bu bir "L" veya baska bir
    # sekildir, duvar dis hatti degil.)
    if abs(i - j) == 1 or abs(i - j) == len(edges) - 1:
        return None

    a, b = edges[i], edges[j]
    len_a, len_b = _edge_length(a), _edge_length(b)
    if len_a <= 0 or len_b <= 0:
        return None
    if min(len_a, len_b) / max(len_a, len_b) < MIN_EDGE_LENGTH_RATIO:
        return None

    ax, ay = _edge_vector(a)
    bx, by = _edge_vector(b)
    # Birim vektorler uzerinden paralellik (capraz carpim = sin) ve
    # yon (skaler carpim = cos) kontrolu.
    sin_angle = abs(ax * by - ay * bx) / (len_a * len_b)
    cos_angle = (ax * bx + ay * by) / (len_a * len_b)
    if sin_angle > PARALLEL_SIN_TOL:
        return None
    if cos_angle > 0:
        # Ayni yonluler: halka boyunca gidildiginde duvarin iki yuzu
        # zit yonlu olmali. Ayni yonluyse bu karsilikli iki yuz degildir.
        return None

    # Kalinlik: b'nin baslangicinin, a dogrusuna dik uzakligi.
    nx, ny = -ay / len_a, ax / len_a
    thickness = abs((b[0][0] - a[0][0]) * nx + (b[0][1] - a[0][1]) * ny)
    min_t = MIN_THICKNESS_M * feet_per_meter
    max_t = MAX_THICKNESS_M * feet_per_meter
    if not (min_t <= thickness <= max_t):
        return None

    # Merkez eksen: karsilikli uclarin orta noktalari. (b zit yonlu
    # oldugu icin a.start <-> b.end ve a.end <-> b.start eslesir.)
    c1 = ((a[0][0] + b[1][0]) / 2.0, (a[0][1] + b[1][1]) / 2.0)
    c2 = ((a[1][0] + b[0][0]) / 2.0, (a[1][1] + b[0][1]) / 2.0)
    length = math.dist(c1, c2)
    if length <= 0 or length / thickness < MIN_ASPECT_RATIO:
        return None

    return c1, c2, thickness


def _dedupe(candidates, tol):
    """Ayni yerdeki tekrar eden duvarlari eler (yon farki onemsiz).

    Polycam ciktisinda her duvar iki kez cizilmis olarak geliyor; bu
    ayiklanmazsa Revit'te ust uste iki duvar olusur."""
    seen = set()
    unique = []
    for c in candidates:
        key_a = (round(c.x1 / tol), round(c.y1 / tol), round(c.x2 / tol), round(c.y2 / tol))
        key_b = (key_a[2], key_a[3], key_a[0], key_a[1])
        if key_a in seen or key_b in seen:
            continue
        seen.add(key_a)
        unique.append(c)
    return unique


def detect_walls(polys, feet_per_meter):
    """`Poly` listesinden duvar adaylarini cikarir.

    (duvarlar, eslesmeyen_nesneler) dondurur. Girdi feet cinsinden
    olmalidir (bkz. `geometry.to_feet_polys`)."""
    walls = []
    leftovers = []

    for poly in polys:
        result = None
        if poly.is_ring():
            result = outline_to_centerline(poly.ring(), feet_per_meter)
        if result is None:
            leftovers.append(poly)
            continue
        (x1, y1), (x2, y2), thickness = result
        walls.append(
            WallCandidate(
                x1, y1, x2, y2, poly.layer,
                math.hypot(x2 - x1, y2 - y1),
                thickness_ft=thickness,
                source="outline",
            )
        )

    return _dedupe(walls, DUPLICATE_TOL_M * feet_per_meter), leftovers


def walls_from_segments(segments):
    """Geri donus modu: her segment bir duvar ekseni (kalinlik olculmez).

    Duvarlari tek cizgiyle cizilmis (dis hatsiz) planlar icin. Kullanici
    acikca istemedikce kullanilmaz -- aksi halde mobilya/olculendirme
    cizgileri de duvara doner."""
    return [
        WallCandidate(
            s.x1, s.y1, s.x2, s.y2, s.layer, s.length(),
            thickness_ft=None, source="line",
        )
        for s in segments
    ]


def summarize_by_layer(candidates) -> dict:
    """Katman -> {"count", "length_ft", "thickness_ft" (medyan), "source"} ozeti.

    Arayuz, katman secim listesinde her katmanin yaninda kac duvar, ne
    kadar uzunluk ve olculen kalinlik oldugunu gosterebilsin diye."""
    summary = {}
    for candidate in candidates:
        entry = summary.setdefault(
            candidate.layer,
            {"count": 0, "length_ft": 0.0, "thicknesses": [], "sources": set()},
        )
        entry["count"] += 1
        entry["length_ft"] += candidate.length_ft
        entry["sources"].add(candidate.source)
        if candidate.thickness_ft:
            entry["thicknesses"].append(candidate.thickness_ft)

    out = {}
    for layer, entry in summary.items():
        thicknesses = sorted(entry["thicknesses"])
        median = thicknesses[len(thicknesses) // 2] if thicknesses else None
        out[layer] = {
            "count": entry["count"],
            "length_ft": entry["length_ft"],
            "thickness_ft": median,
            "sources": sorted(entry["sources"]),
        }
    return out
