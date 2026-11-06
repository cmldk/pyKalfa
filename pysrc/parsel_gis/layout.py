"""Parsel-Bina GIS: saf geometri (ag yok).

Girdi: servislerden gelen Esri halkalari (EPSG:31370, metre). Cikti: mevcut
Parsel/Bina Aktar butonunun `revit_input.json` bicimindeki parcalar.

Orijin = cercevenin sol-alt kosesi, X saga, Y yukari artar, birim feet --
mevcut butonla ayni kural (orada orijin parsel.png'nin sol-alt kosesi).
"""

from __future__ import annotations

import math

import shapely
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.validation import make_valid

from services import parcel_numero

FEET_PER_METER = 1 / 0.3048
MIN_LABEL_AREA_M2 = 20.0
NORTH_INSET_M = 5.0
SNAP_M = 0.01
MAX_MARGIN_M = 200.0
# Revit tarafi (parsel_draw.MIN_SEGMENT_LENGTH_FT = 0.05 ft = 0.01524 m) bundan
# kisa kenari atlar ve bina loop'u kopar; bu yuzden esik onun ustunde tutulur.
MIN_SEGMENT_M = 0.02
MIN_REGION_AREA_M2 = 0.5


def _ring_area(r):
    return 0.5 * sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1))


def rings_to_geom(rings):
    """Esri halkalari -> Polygon / MultiPolygon. Yon bilgisine guvenmez:
    buyukten kucuge siralanir, daha once kabul edilmis bir dis halkanin
    icine dusen halka o poligonun deligi olur."""
    shells = []  # [(Polygon(dis), [delik halkalari])]
    for r in sorted(rings, key=lambda r: -abs(_ring_area(r))):
        if len(r) < 4:
            continue
        ring_poly = Polygon(r)
        if not ring_poly.is_valid:
            ring_poly = ring_poly.buffer(0)
        for shell, holes in shells:
            if shell.contains(ring_poly.representative_point()) and not any(
                    Polygon(h).contains(ring_poly.representative_point()) for h in holes):
                holes.append(r)
                break
        else:
            shells.append((Polygon(r), []))
    polys = [Polygon(shell.exterior.coords, holes) for shell, holes in shells]
    geom = shapely.union_all(polys) if len(polys) > 1 else (polys[0] if polys else Polygon())
    return geom if geom.is_valid else make_valid(geom)


def frame_box(rings, margin_m):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return (min(xs) - margin_m, min(ys) - margin_m, max(xs) + margin_m, max(ys) + margin_m)


def to_local_ft(x, y, box):
    return [round((x - box[0]) * FEET_PER_METER, 3), round((y - box[1]) * FEET_PER_METER, 3)]


def frame_lines(box):
    w = round((box[2] - box[0]) * FEET_PER_METER, 3)
    h = round((box[3] - box[1]) * FEET_PER_METER, 3)
    corners = [[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]]
    return [[corners[i], corners[(i + 1) % 4]] for i in range(4)]


def _lines(geom):
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString) or hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from _lines(g)


def parcel_segments(parcels, box):
    """Cerceve icindeki parsel sinirlari; komsu parsellerin ortak kenari tek kez."""
    if not parcels:
        return []
    lines = [shapely.set_precision(rings_to_geom(p["rings"]).boundary, SNAP_M) for p in parcels]
    merged = shapely.unary_union(lines)
    inside = merged.intersection(shapely.box(*box))
    segments = []
    for line in _lines(inside):
        coords = list(line.coords)
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            if math.hypot(x2 - x1, y2 - y1) < MIN_SEGMENT_M:
                continue
            segments.append([to_local_ft(x1, y1, box), to_local_ft(x2, y2, box)])
    return segments


def _polygons(geom):
    if isinstance(geom, Polygon):
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from _polygons(g)


def building_regions(buildings, box):
    """Her bina (veya cercevenin bolduğu her parcasi) bir FilledRegion kaydi.
    Yalniz dis halka kullanilir (mevcut buton tek CurveLoop ciziyor)."""
    frame = shapely.box(*box)
    out = []
    for b in buildings:
        clipped = rings_to_geom(b["rings"]).intersection(frame)
        for part in _polygons(clipped):
            if part.area < MIN_REGION_AREA_M2:
                continue
            pts = []
            for x, y in list(part.exterior.coords)[:-1]:
                if pts and math.hypot(x - pts[-1][0], y - pts[-1][1]) < MIN_SEGMENT_M:
                    continue
                pts.append((x, y))
            if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < MIN_SEGMENT_M:
                pts.pop()
            if len(pts) < 3:
                continue
            out.append({"id": len(out), "source_id": b.get("id"),
                        "vertices_ft": [to_local_ft(x, y, box) for x, y in pts],
                        "area_m2": round(part.area, 2)})
    return out


def parcel_labels(parcels, box):
    """Her parsel icin numara etiketi; cerceve icinde kalan alani kucukse atlanir."""
    frame = shapely.box(*box)
    out = []
    for p in parcels:
        text = parcel_numero(p.get("attributes") or {})
        if not text or text == "0":
            continue
        clipped = rings_to_geom(p["rings"]).intersection(frame)
        if clipped.is_empty or clipped.area < MIN_LABEL_AREA_M2:
            continue
        pt = clipped.representative_point()
        out.append({"id": len(out), "text": text, "capakey": p.get("capakey"),
                    "position_ft": to_local_ft(pt.x, pt.y, box), "rotation_deg": 0.0})
    return out


def north_record(box):
    """Veri kuzey yukari: ok 0 derece, cercevenin sag-ust kosesinden iceride."""
    return {"position_ft": to_local_ft(box[2] - NORTH_INSET_M, box[3] - NORTH_INSET_M, box),
            "rotation_deg": 0.0}
