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
MIN_STREET_LABEL_M = 15.0   # cerceve icinde bundan kisa kalan sokak adi yazilmaz
STREET_TANGENT_M = 2.0      # yazi acisi orta noktanin +- bu kadar cevresinden olculur


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


def parcel_segments(parcels, box, exclude=None):
    """Cerceve icindeki parsel sinirlari; komsu parsellerin ortak kenari tek kez.
    `exclude` (secilen parsel) verilirse onun sinirina dusen kisimlar cikarilir:
    o sinir `selected_parcel_segments` ile ayri stilde cizilir, iki kez degil."""
    if not parcels:
        return []
    lines = [rings_to_geom(p["rings"]).boundary for p in parcels]
    if exclude is None:
        return _segments(lines, box)
    sel = shapely.set_precision(rings_to_geom(exclude["rings"]).boundary, SNAP_M)
    merged = shapely.unary_union([shapely.set_precision(g, SNAP_M) for g in lines])
    return _segments([merged.difference(sel.buffer(SNAP_M))], box)


def selected_parcel_segments(parcel, box):
    """Secilen parselin cerceve icindeki siniri (komsularla ortak kenarlar dahil)."""
    return _segments([rings_to_geom(parcel["rings"]).boundary], box)


def road_segments(roads, box):
    """Cerceve icindeki yol/kaldirim kenarlari; ust uste binen parcalar tek kez."""
    lines = [LineString(path) for r in roads for path in r["paths"] if len(path) >= 2]
    return _segments(lines, box) if lines else []


def _segments(lines, box):
    """Cizgileri birlestirip (cakisanlar tek) cerceveye kirpar, ft segmentlere boler."""
    merged = shapely.unary_union([shapely.set_precision(g, SNAP_M) for g in lines])
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


def parcel_labels(parcels, box, selected_capakey=None):
    """Her parsel icin numara etiketi; cerceve icinde kalan alani kucukse atlanir.
    `selected` = secilen parselin etiketi mi (Revit'te ayri text note tipi)."""
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
                    "selected": bool(selected_capakey) and p.get("capakey") == selected_capakey,
                    "position_ft": to_local_ft(pt.x, pt.y, box), "rotation_deg": 0.0})
    return out


def north_record(box):
    """Veri kuzey yukari: ok 0 derece, cercevenin sag-ust kosesinden iceride."""
    return {"position_ft": to_local_ft(box[2] - NORTH_INSET_M, box[3] - NORTH_INSET_M, box),
            "rotation_deg": 0.0}


def readable_angle(deg):
    """Aciyi (-90, 90] araligina getirir: yazi yol yonunde ama ters okunmaz."""
    a = deg % 180.0
    if a > 90.0:
        a -= 180.0
    return round(a, 2) + 0.0


def street_labels(axes, box):
    """Her sokak adi bir kez: cerceve icindeki en uzun birlesik eksen parcasinin
    ortasina, yol yonunde dondurulmus. Konum metnin ORTASIDIR (Revit'te ortali)."""
    frame = shapely.box(*box)
    by_name = {}
    for a in axes:
        by_name.setdefault(a["name"], []).extend(
            LineString(p) for p in a["paths"] if len(p) >= 2)
    out = []
    for name in sorted(by_name, key=lambda n: n.lower()):
        merged = shapely.line_merge(shapely.unary_union(by_name[name]).intersection(frame))
        parts = [g for g in _lines(merged) if g.length > 0]
        if not parts:
            continue
        line = max(parts, key=lambda g: g.length)
        if line.length < MIN_STREET_LABEL_M:
            continue
        d = line.length / 2.0
        mid = line.interpolate(d)
        p1 = line.interpolate(max(0.0, d - STREET_TANGENT_M))
        p2 = line.interpolate(min(line.length, d + STREET_TANGENT_M))
        angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        out.append({"id": len(out), "text": name, "position_ft": to_local_ft(mid.x, mid.y, box),
                    "rotation_deg": readable_angle(angle)})
    return out
