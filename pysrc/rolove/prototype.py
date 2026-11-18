"""
pyKalfa / Rolove Prototip - rolove sozlugunu "toparlanmis" prototipe cevirir.

Rolove Aktar'in hazirlik ciktisi (`prepare_rolove_input.prepare`, koordinatlar
feet) ustunde calisir ve sozlugu YERINDE degistirir:

  1. Baskin yon (ana katin dis duvarlari, uzunluk agirlikli tepe).
  2. Diklestirme: yonu baskin yone ya da dikine ANGLE_MAX_DEG icinde olan
     duvar orta noktasi etrafinda o yone dondurulur.
  3. Katlar arasi dis duvar hizasi: farkli katlarda paralel, STACK_TOL_M
     yakin ve planda ortusen dis duvarlar tek hatta toplanir (ana kat
     duvari varsa onun hatti).
  4. Kat icinde koseler yeniden kesistirilir (`refine.join_corners`).
  5. Aciklik merkezleri yeni host hattina izdusurulur, duvar icinde kenetlenir.
  6. Etiket: taranmis hattan MOVE_TOL_CM'den fazla uzaklasan duvar en az
     `duzeltildi`, sapma (cm) = uclardaki en buyuk yanal uzaklik.
  7. `top_floor` (kotca bir ustteki kat), `p-` onekli id'ler,
     `Kat N (Prototip)` adlari.

Dosemeler (`floor_loops`) dis duvar kalinligi bilindikten sonra hesaplanir.
"""

from __future__ import annotations

import math

import config
import geom2d

ANGLE_MAX_DEG = 5.0
STACK_TOL_M = 0.15
MOVE_TOL_CM = 1.0
PEAK_WINDOW_DEG = 1.0
PARALLEL_STACK_DEG = 1.0
ID_PREFIX = "p-"
STATUS_ORDER = ("olculdu", "duzeltildi", "varsayildi")


def params() -> dict:
    return {"angle_max_deg": ANGLE_MAX_DEG, "stack_tol_m": STACK_TOL_M,
            "move_tol_cm": MOVE_TOL_CM, "corner_snap_m": config.CORNER_SNAP_M}


# --------------------------------------------------------------------------
# Kucuk yardimcilar (duvar = JSON sozlugu, feet)
# --------------------------------------------------------------------------

def _line(w):
    return (tuple(w["start_ft"]), tuple(w["end_ft"]))


def _set_line(w, a, b):
    w["start_ft"] = [float(a[0]), float(a[1])]
    w["end_ft"] = [float(b[0]), float(b[1])]


def _angle(w):
    (x1, y1), (x2, y2) = _line(w)
    return math.atan2(y2 - y1, x2 - x1)


def _length(w):
    return geom2d.seg_length(_line(w))


def _mod90_diff(a, b):
    """a - b, 90 derece moduna gore [-45, 45) derece araliginda (radyan)."""
    q = math.pi / 2.0
    return (a - b + q / 2.0) % q - q / 2.0


def _mark(moved, w, what):
    if moved is not None:
        moved.setdefault(w["id"], set()).add(what)


# --------------------------------------------------------------------------
# 1-3. Yon, diklestirme, kat hizasi
# --------------------------------------------------------------------------

def dominant_angle(walls, floor) -> float:
    """Radyan, [0, pi/2). Adaylar duvar yonleri (mod 90); her adayin destegi
    PEAK_WINDOW_DEG icindeki duvarlarin toplam uzunlugu; en guclu adayin
    penceresindeki yonlerin uzunluk agirlikli ortalamasi. Tek bir carpik
    duvar butun binayi dondurmesin diye ortalama degil tepe."""
    pools = ([w for w in walls if w["floor"] == floor and w["side"] == "exterior"],
             [w for w in walls if w["side"] == "exterior"], list(walls))
    pool = next((p for p in pools if p), [])
    pool = [w for w in pool if _length(w) > 1e-9]
    if not pool:
        return 0.0
    win = math.radians(PEAK_WINDOW_DEG)
    best = None
    for cand in pool:
        c = _angle(cand)
        members = [w for w in pool if abs(_mod90_diff(_angle(w), c)) <= win]
        support = sum(_length(w) for w in members)
        if best is None or support > best[0] + 1e-9:
            best = (support, c, members)
    _, c, members = best
    total = sum(_length(w) for w in members)
    mean = c + sum(_mod90_diff(_angle(w), c) * _length(w) for w in members) / total
    return mean % (math.pi / 2.0)


def orthogonalize(walls, theta, max_deg=ANGLE_MAX_DEG, moved=None) -> int:
    limit = math.radians(max_deg)
    n = 0
    for w in walls:
        if _length(w) <= 1e-9:
            continue
        d = _mod90_diff(_angle(w), theta)
        if abs(d) < 1e-8 or abs(d) > limit:
            continue
        (x1, y1), (x2, y2) = _line(w)
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        c, s = math.cos(-d), math.sin(-d)

        def rot(px, py):
            dx, dy = px - mx, py - my
            return (mx + dx * c - dy * s, my + dx * s + dy * c)

        _set_line(w, rot(x1, y1), rot(x2, y2))
        _mark(moved, w, "diklestirildi")
        n += 1
    return n


def _parallel(a, b):
    d = (_angle(a) - _angle(b)) % math.pi
    d = min(d, math.pi - d)
    return d <= math.radians(PARALLEL_STACK_DEG)


def _overlap(a, b):
    la = _line(a)
    length = geom2d.seg_length(la)
    t1, _ = geom2d.project(la, _line(b)[0])
    t2, _ = geom2d.project(la, _line(b)[1])
    lo, hi = min(t1, t2), max(t1, t2)
    return min(hi, length) - max(lo, 0.0) > 1e-6


def stack_exterior(walls, main_floor, tol_m=STACK_TOL_M, moved=None) -> int:
    tol = tol_m * config.FT
    ext = [w for w in walls if w["side"] == "exterior" and _length(w) > 1e-9]
    parent = list(range(len(ext)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(ext)):
        for j in range(i + 1, len(ext)):
            a, b = ext[i], ext[j]
            if a["floor"] == b["floor"] or not _parallel(a, b):
                continue
            mid_b = tuple((p + q) / 2.0 for p, q in zip(b["start_ft"], b["end_ft"]))
            _, dist = geom2d.project(_line(a), mid_b)
            if abs(dist) <= tol and (_overlap(a, b) or _overlap(b, a)):
                parent[find(i)] = find(j)

    clusters = {}
    for i in range(len(ext)):
        clusters.setdefault(find(i), []).append(ext[i])
    n = 0
    for members in clusters.values():
        if len({w["floor"] for w in members}) < 2:
            continue
        ref = max(members, key=_length)
        nx, ny = geom2d.seg_normal(_line(ref))

        def offset(w):
            mx = (w["start_ft"][0] + w["end_ft"][0]) / 2.0
            my = (w["start_ft"][1] + w["end_ft"][1]) / 2.0
            return mx * nx + my * ny

        main = [w for w in members if w["floor"] == main_floor]
        base = main or members
        target = sum(offset(w) * _length(w) for w in base) / sum(_length(w) for w in base)
        for w in members:
            delta = target - offset(w)
            if abs(delta) < 1e-9 or abs(delta) > tol:
                continue
            (x1, y1), (x2, y2) = _line(w)
            _set_line(w, (x1 + nx * delta, y1 + ny * delta), (x2 + nx * delta, y2 + ny * delta))
            _mark(moved, w, "kat hizasina tasindi")
            n += 1
    return n


# --------------------------------------------------------------------------
# 4-7
# --------------------------------------------------------------------------

class _Seg(object):
    """`refine.join_corners` icin `.line` tasiyan ince sarmalayici."""

    def __init__(self, w):
        self.w = w
        self.line = _line(w)


def _join_floor(walls):
    import refine
    segs = [_Seg(w) for w in walls if _length(w) > 1e-9]
    refine.join_corners(segs, config.CORNER_SNAP_M * config.FT)
    for s in segs:
        _set_line(s.w, s.line[0], s.line[1])


def top_floors(levels) -> dict:
    order = sorted(levels, key=lambda lv: (lv["elevation_m"], lv["floor"]))
    return {lv["floor"]: (order[i + 1]["floor"] if i + 1 < len(order) else None)
            for i, lv in enumerate(order)}


def _worse(a, b):
    ia = STATUS_ORDER.index(a) if a in STATUS_ORDER else 0
    ib = STATUS_ORDER.index(b) if b in STATUS_ORDER else 0
    return STATUS_ORDER[max(ia, ib)]


def _lateral_cm(scan, w):
    line = _line(w)
    if geom2d.seg_length(line) <= 1e-9:
        return 0.0
    return max(abs(geom2d.project(line, p)[1]) for p in scan) / config.FT * 100.0


def _point_at(line, t):
    (x1, y1), _ = line
    ux, uy = geom2d.seg_dir(line)
    return (x1 + ux * t, y1 + uy * t)


def tidy(doc: dict) -> dict:
    walls = doc.get("walls") or []
    by_id = {w["id"]: w for w in walls}
    main_floor = (doc.get("z_datum") or {}).get("floor")
    if main_floor is None and walls:
        main_floor = walls[0]["floor"]

    for w in walls:
        w["scan_start_ft"] = list(w["start_ft"])
        w["scan_end_ft"] = list(w["end_ft"])
    centers = {}
    for o in doc.get("openings") or []:
        host = by_id.get(o["host_id"])
        if host is not None and _length(host) > 1e-9:
            centers[o["id"]] = _point_at(_line(host), o["offset_ft"])

    moved = {}
    theta = dominant_angle(walls, main_floor) if walls else 0.0
    n_orth = orthogonalize(walls, theta, moved=moved)
    n_stack = stack_exterior(walls, main_floor, moved=moved)
    for f in sorted({w["floor"] for w in walls}):
        _join_floor([w for w in walls if w["floor"] == f])

    skipped = []
    limit = math.radians(ANGLE_MAX_DEG)
    for w in walls:
        scan = (tuple(w["scan_start_ft"]), tuple(w["scan_end_ft"]))
        d = abs(_mod90_diff(math.atan2(scan[1][1] - scan[0][1], scan[1][0] - scan[0][0]), theta))
        if d > limit:
            skipped.append(w["id"])
        dev = _lateral_cm(scan, w)
        if dev >= MOVE_TOL_CM:
            w["status"] = _worse(w.get("status"), "duzeltildi")
            w["deviation_cm"] = round(max(float(w.get("deviation_cm") or 0.0), dev), 1)
            for what in sorted(moved.get(w["id"], ())):
                w.setdefault("warnings", []).append("prototip: {}".format(what))

    for o in doc.get("openings") or []:
        host = by_id.get(o["host_id"])
        if host is None or _length(host) <= 1e-9:
            continue
        line = _line(host)
        length = geom2d.seg_length(line)
        t = geom2d.project(line, centers[o["id"]])[0] if o["id"] in centers else o["offset_ft"]
        half = float(o.get("width_ft") or 0.0) / 2.0
        t = length / 2.0 if length < 2 * half else min(max(t, half), length - half)
        o["offset_ft"] = t

    tops = top_floors(doc.get("levels") or [])
    for w in walls:
        w["top_floor"] = tops.get(w["floor"])
        if w["top_floor"] is not None:
            w.setdefault("warnings", []).append(
                "yukseklik: taranan {:.2f} m -> Level'a bagli (Kat {})".format(
                    float(w.get("height_m") or 0.0), w["top_floor"]))

    for key in ("levels", "walls", "openings", "rooms"):
        for x in doc.get(key) or []:
            x["id"] = ID_PREFIX + x["id"]
    for o in doc.get("openings") or []:
        o["host_id"] = ID_PREFIX + o["host_id"]
    for lv in doc.get("levels") or []:
        lv["name"] = "Kat {} (Prototip)".format(lv["floor"])

    info = {"theta_deg": round(math.degrees(theta), 3), "orthogonalized": n_orth,
            "stacked": n_stack, "skipped": [ID_PREFIX + s for s in skipped],
            "params": params()}
    doc["prototype"] = info
    doc.setdefault("params", {})["prototype"] = params()
    return doc


# --------------------------------------------------------------------------
# Dosemeler
# --------------------------------------------------------------------------

LINE_EXTEND_M = 0.05        # polygonize icin dis duvar hatlari uclardan uzatilir
ROOM_CLOSE_M = 0.15         # oda araliklari (ic duvar) bu kadar kapatilir
MIN_SLAB_M2 = 0.5
SQFT_TO_M2 = 0.3048 * 0.3048
_MITRE = 2                  # shapely JOIN_STYLE.mitre


def _extended(w, d):
    (x1, y1), (x2, y2) = _line(w)
    ux, uy = geom2d.seg_dir(_line(w))
    return ((x1 - ux * d, y1 - uy * d), (x2 + ux * d, y2 + uy * d))


def footprint(doc, floor, exterior_thickness_m):
    """Katin ayak izi (shapely, feet): dis duvar ic yuz hatlarindan kapanan
    poligonlar + bunlarin disinda kalan odalar (ic duvar araliklari
    kapatilmis), dis duvar kalinligi kadar disa genisletilmis."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union

    ext = [w for w in doc.get("walls") or []
           if w["floor"] == floor and w["side"] == "exterior" and _length(w) > 1e-9]
    lines = [LineString(_extended(w, LINE_EXTEND_M * config.FT)) for w in ext]
    primary = unary_union(list(polygonize(unary_union(lines)))) if lines else Polygon()

    rooms = []
    for r in doc.get("rooms") or []:
        if r["floor"] != floor or len(r.get("polygon_ft") or []) < 3:
            continue
        poly = Polygon(r["polygon_ft"]).buffer(0)
        if poly.is_empty:
            continue
        if primary.is_empty or not primary.contains(poly.representative_point()):
            rooms.append(poly)
    parts = [primary]
    if rooms:
        c = ROOM_CLOSE_M * config.FT
        parts.append(unary_union([p.buffer(c, join_style=_MITRE) for p in rooms])
                     .buffer(-c, join_style=_MITRE))
    geom = unary_union([p for p in parts if not p.is_empty]) if any(
        not p.is_empty for p in parts) else Polygon()
    if geom.is_empty or exterior_thickness_m <= 0:
        return geom
    return geom.buffer(exterior_thickness_m * config.FT, join_style=_MITRE)


def _ring(coords):
    pts = [[float(x), float(y)] for x, y in coords]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def floor_loops(doc, exterior_thickness_m, warnings=None) -> list:
    """Level basina doseme: kendi izi U kotca hemen altindaki katin izi.
    Her parca {"id", "floor", "loops_ft" (dis halka + delikler), "area_m2"}."""
    import shapely
    from shapely.ops import unary_union

    levels = sorted(doc.get("levels") or [], key=lambda lv: (lv["elevation_m"], lv["floor"]))
    prints = {lv["floor"]: footprint(doc, lv["floor"], exterior_thickness_m) for lv in levels}
    out = []
    for i, lv in enumerate(levels):
        f = lv["floor"]
        geoms = [prints[f]] + ([prints[levels[i - 1]["floor"]]] if i > 0 else [])
        geoms = [g for g in geoms if not g.is_empty]
        if not geoms:
            if warnings is not None:
                warnings.append("Kat {}: doseme cikarilamadi (dis duvar ve oda yok)".format(f))
            continue
        geom = shapely.set_precision(unary_union(geoms), 0.001 * config.FT)
        polys = list(getattr(geom, "geoms", [geom]))
        polys = [p for p in polys if p.geom_type == "Polygon"
                 and p.area * SQFT_TO_M2 >= MIN_SLAB_M2]
        polys.sort(key=lambda p: -p.area)
        for k, p in enumerate(polys):
            out.append({"id": "{}floor-{}-{}".format(ID_PREFIX, f, k), "floor": f,
                        "loops_ft": [_ring(p.exterior.coords)] +
                                    [_ring(h.coords) for h in p.interiors],
                        "area_m2": round(p.area * SQFT_TO_M2, 3)})
    return out
