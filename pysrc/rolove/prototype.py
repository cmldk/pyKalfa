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


REJOIN_MAX_M = 0.5          # kaydedilmis birlesim bu kadardan uzaga tasinmaz
FOLLOW_TOL_M = 0.01         # ucuncu uc yalniz taramada GERCEKTEN ayni noktadaysa


def _end(w, k):
    return tuple(w["start_ft"] if k == 0 else w["end_ft"])


def _set_end(w, k, p):
    w["start_ft" if k == 0 else "end_ft"] = [float(p[0]), float(p[1])]


def record_joints(walls, snap_ft):
    """Toparlamadan ONCE (tarama geometrisi) kat icindeki birlesimler:
    ("corner", i, k, j, m) uc-uca (`snap_ft` icinde, en yakindan baslayarak,
    her uc bir kez); ("follow", i, k, j, m) ayni koseye gelen ucuncu (ve
    sonraki) uc -> o kosenin noktasina tasinir; ("t", i, k, j) bos ucun
    baska duvarin govdesine degmesi. Indeksler `walls` listesine."""
    pairs = []
    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            for k in (0, 1):
                for m in (0, 1):
                    d = math.dist(_end(walls[i], k), _end(walls[j], m))
                    if d <= snap_ft:
                        pairs.append((d, i, k, j, m))
    pairs.sort()
    used, joints = set(), []
    for _, i, k, j, m in pairs:
        if (i, k) in used or (j, m) in used:
            continue
        used.update({(i, k), (j, m)})
        joints.append(("corner", i, k, j, m))
    corner_ends = sorted(used)
    for i in range(len(walls)):
        for k in (0, 1):
            if (i, k) in used:
                continue
            near = [(math.dist(_end(walls[i], k), _end(walls[j], m)), j, m)
                    for j, m in corner_ends if j != i]
            near = [x for x in near if x[0] <= FOLLOW_TOL_M * config.FT]
            if near:
                _, j, m = min(near)
                used.add((i, k))
                joints.append(("follow", i, k, j, m))
    for i, w in enumerate(walls):
        for k in (0, 1):
            if (i, k) in used:
                continue
            best = None
            for j, other in enumerate(walls):
                if j == i or _length(other) <= 1e-9:
                    continue
                t, d = geom2d.project(_line(other), _end(w, k))
                if abs(d) <= snap_ft and 0.0 < t < _length(other):
                    if best is None or abs(d) < best[0]:
                        best = (abs(d), j)
            if best is not None:
                used.add((i, k))
                joints.append(("t", i, k, best[1]))
    return joints


def restore_joints(walls, joints, max_ft):
    """Toparlamadan SONRA: kaydedilen birlesimleri sonsuz dogrularin
    kesisimiyle yeniden kurar (paralel ya da `max_ft`'den uzak kesisimde
    kose = iki ucun ortasi; T = dokunulmaz). Kurulan uc sayisi."""
    import refine
    n = 0
    for joint in joints:
        if joint[0] == "corner":
            _, i, k, j, m = joint
            a, b = _end(walls[i], k), _end(walls[j], m)
            p = refine._intersect(_line(walls[i]), _line(walls[j]))
            if p is None or math.dist(p, a) > max_ft or math.dist(p, b) > max_ft:
                p = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            _set_end(walls[i], k, p)
            _set_end(walls[j], m, p)
            n += 2
        elif joint[0] == "follow":
            _, i, k, j, m = joint
            _set_end(walls[i], k, _end(walls[j], m))
            n += 1
        else:
            _, i, k, j = joint
            p = refine._intersect(_line(walls[i]), _line(walls[j]))
            if p is not None and math.dist(p, _end(walls[i], k)) <= max_ft:
                _set_end(walls[i], k, p)
                n += 1
    return n


def _join_floor(walls):
    """Taramada acik kalmis uclar icin mesafe tabanli kose birlestirme."""
    import refine
    segs = [_Seg(w) for w in walls if _length(w) > 1e-9]
    refine.join_corners(segs, config.CORNER_SNAP_M * config.FT)
    for s in segs:
        _set_line(s.w, s.line[0], s.line[1])


MERGE_LATERAL_M = 0.02      # ayni hat sayilma (yanal)
MERGE_GAP_M = 0.05          # uclar arasi bu kadar bosluk/ust uste binme birlestirilir
MERGE_PARALLEL_DEG = 1.0


def _mergeable(a, b):
    if (a["floor"], a["side"], a["location"], a.get("thickness_group_cm")) != \
            (b["floor"], b["side"], b["location"], b.get("thickness_group_cm")):
        return None
    la = _line(a)
    length = geom2d.seg_length(la)
    if length <= 1e-9 or _length(b) <= 1e-9:
        return None
    ua, ub = geom2d.seg_dir(la), geom2d.seg_dir(_line(b))
    if abs(ua[0] * ub[1] - ua[1] * ub[0]) > math.sin(math.radians(MERGE_PARALLEL_DEG)):
        return None
    t1, d1 = geom2d.project(la, _line(b)[0])
    t2, d2 = geom2d.project(la, _line(b)[1])
    if max(abs(d1), abs(d2)) > MERGE_LATERAL_M * config.FT:
        return None
    lo, hi = min(t1, t2), max(t1, t2)
    gap = max(lo - length, 0.0 - hi)
    if gap > MERGE_GAP_M * config.FT:
        return None
    return (min(0.0, lo), max(length, hi))


def merge_collinear(doc) -> int:
    """Ayni katta ayni tur/kalinlikta, ayni hat uzerinde (yanal < 2 cm) uc
    uca degen ya da ust uste binen duvar parcalari tek duvar olur (ornek
    tarama Kat 3: 0.54 m + 2.32 m, 7 mm ust uste -> Revit "walls overlap").
    Uzun parca kalir; kisa parcadaki kapi/pencereler ona gecer; durum kotu
    olani alir. Birlestirilen parca sayisi."""
    walls = doc.get("walls") or []
    ops = doc.get("openings") or []
    n = 0
    changed = True
    while changed:
        changed = False
        for i in range(len(walls)):
            for j in range(len(walls)):
                if i == j:
                    continue
                keep, drop = walls[i], walls[j]
                if _length(keep) < _length(drop):
                    continue
                ext = _mergeable(keep, drop)
                if ext is None:
                    continue
                line = _line(keep)
                ux, uy = geom2d.seg_dir(line)
                (x0, y0), _ = line
                centers = {}
                for o in ops:
                    host = keep if o["host_id"] == keep["id"] else drop if o["host_id"] == drop["id"] else None
                    if host is not None:
                        centers[o["id"]] = _point_at(_line(host), o["offset_ft"])
                t_min, t_max = ext
                _set_line(keep, (x0 + ux * t_min, y0 + uy * t_min), (x0 + ux * t_max, y0 + uy * t_max))
                new_line = _line(keep)
                for o in ops:
                    if o["id"] in centers:
                        o["host_id"] = keep["id"]
                        o["offset_ft"] = geom2d.project(new_line, centers[o["id"]])[0]
                keep["status"] = _worse(keep.get("status"), drop.get("status"))
                keep["deviation_cm"] = max(float(keep.get("deviation_cm") or 0.0),
                                           float(drop.get("deviation_cm") or 0.0))
                keep.setdefault("warnings", []).append(
                    "prototip: ayni hattaki {} ile birlestirildi".format(drop["id"]))
                del walls[j]
                n += 1
                changed = True
                break
            if changed:
                break
    return n


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

    floors = sorted({w["floor"] for w in walls})
    snap_ft = config.CORNER_SNAP_M * config.FT
    per_floor = {f: [w for w in walls if w["floor"] == f and _length(w) > 1e-9] for f in floors}
    joints = {f: record_joints(per_floor[f], snap_ft) for f in floors}

    moved = {}
    theta = dominant_angle(walls, main_floor) if walls else 0.0
    n_orth = orthogonalize(walls, theta, moved=moved)
    n_stack = stack_exterior(walls, main_floor, moved=moved)
    for f in floors:
        restore_joints(per_floor[f], joints[f], REJOIN_MAX_M * config.FT)
        _join_floor(per_floor[f])

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

    n_merged = merge_collinear(doc)

    tops = top_floors(doc.get("levels") or [])
    for r in doc.get("rooms") or []:
        r["top_floor"] = tops.get(r["floor"])
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

    doc["room_separations"] = room_separations(doc)

    info = {"theta_deg": round(math.degrees(theta), 3), "orthogonalized": n_orth,
            "stacked": n_stack, "skipped": [ID_PREFIX + s for s in skipped],
            "separations": len(doc["room_separations"]), "merged": n_merged,
            "params": params()}
    doc["prototype"] = info
    doc.setdefault("params", {})["prototype"] = params()
    return doc


# --------------------------------------------------------------------------
# Oda ayiricilari (Room Separation Line)
# --------------------------------------------------------------------------

SEP_WALL_COVER_M = 0.25     # oda kenari bir duvar hattina bu kadar yakinsa duvarli sayilir
SEP_MIN_M = 0.30            # bundan kisa duvarsiz parca icin ayirici konmaz
SEP_DUP_M = 0.05            # iki odanin ortak kenari tek ayirici
SEP_EXTEND_M = SEP_WALL_COVER_M + 0.05   # uclar duvarin icine kadar uzatilir


def _line_parts(g):
    if g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "LineString"]


def room_separations(doc) -> list:
    """Polycam acik plani (mutfak + salon gibi) duvarsiz iki oda olarak
    cizer; Revit duvarla ayrilmamis odalari tek alan sayip birini "Redundant
    Room" yapar. Oda poligon kenarlarinin hicbir duvar hattina
    `SEP_WALL_COVER_M` yakin olmayan parcalari ayirici olur; iki odanin ortak
    kenari tek cizgi; uclar `SEP_EXTEND_M` uzatilir ki duvara degsin.
    [{"id", "floor", "start_ft", "end_ft"}]"""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    ft = config.FT
    out = []
    for f in sorted({r["floor"] for r in doc.get("rooms") or []}):
        walls = [LineString(_line(w)) for w in doc.get("walls") or []
                 if w["floor"] == f and _length(w) > 1e-9]
        cover = unary_union([w.buffer(SEP_WALL_COVER_M * ft) for w in walls]) if walls else None
        accepted = []
        for r in doc.get("rooms") or []:
            pts = [tuple(p) for p in r.get("polygon_ft") or []]
            if r["floor"] != f or len(pts) < 3:
                continue
            for a, b in zip(pts, pts[1:] + pts[:1]):
                if math.dist(a, b) <= 1e-9:
                    continue
                edge = LineString([a, b])
                rest = edge.difference(cover) if cover is not None else edge
                for part in _line_parts(rest):
                    if part.length < SEP_MIN_M * ft:
                        continue
                    if any(part.difference(x.buffer(SEP_DUP_M * ft)).length < SEP_DUP_M * ft
                           for x in accepted):
                        continue
                    accepted.append(part)
        segs = []
        for part in accepted:
            (x1, y1), (x2, y2) = part.coords[0], part.coords[-1]
            seg = ((x1, y1), (x2, y2))
            ux, uy = geom2d.seg_dir(seg)
            d = SEP_EXTEND_M * ft
            segs.append(((x1 - ux * d, y1 - uy * d), (x2 + ux * d, y2 + uy * d)))
        segs.sort(key=lambda s: (round(s[0][0], 2), round(s[0][1], 2), round(s[1][0], 2)))
        for k, (a, b) in enumerate(segs):
            out.append({"id": "{}sep-{}-{}".format(ID_PREFIX, f, k), "floor": f,
                        "start_ft": [float(a[0]), float(a[1])], "end_ft": [float(b[0]), float(b[1])]})
    return out


# --------------------------------------------------------------------------
# Dosemeler
# --------------------------------------------------------------------------

LINE_EXTEND_M = 0.30        # polygonize icin: koselerde 10-20 cm acik kalan hatlar kesissin
ROOM_CLOSE_M = 0.15         # oda araliklari (ic duvar) bu kadar kapatilir
MIN_SLAB_M2 = 0.5
SQFT_TO_M2 = 0.3048 * 0.3048
_MITRE = 2                  # shapely JOIN_STYLE.mitre


def _extended(w, d):
    (x1, y1), (x2, y2) = _line(w)
    ux, uy = geom2d.seg_dir(_line(w))
    return ((x1 - ux * d, y1 - uy * d), (x2 + ux * d, y2 + uy * d))


def footprint(doc, floor, exterior_thickness_m):
    """Katin ayak izi (shapely, feet): katin TUM duvar hatlarindan (dis
    duvarda ic yuz, ic duvarda eksen; ornek taramada cevrenin bir kismi
    'interior' sinifinda) kapanan hucrelerin birlesimi + bunlarin disinda
    kalan odalar (ic duvar araliklari kapatilmis), dis duvar kalinligi
    kadar disa genisletilmis."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union

    ext = [w for w in doc.get("walls") or []
           if w["floor"] == floor and _length(w) > 1e-9]
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


# --------------------------------------------------------------------------
# Onizleme
# --------------------------------------------------------------------------

def render_floor(doc, floor, path):
    """Toparlanmis kat: odalar gri, duvarlar duruma gore renkli, aciklikler
    mavi, kalinliksiz ayak izi siyah ince cizgi. PNG yolunu dondurur."""
    from pathlib import Path

    import cv2
    import numpy as np
    import preview

    walls = [w for w in doc.get("walls") or [] if w["floor"] == floor]
    rooms = [r for r in doc.get("rooms") or [] if r["floor"] == floor]
    ops = [o for o in doc.get("openings") or [] if o["floor"] == floor]
    fp = footprint(doc, floor, 0.0)
    rings = []
    for p in getattr(fp, "geoms", [fp]):
        if not p.is_empty and p.geom_type == "Polygon":
            rings += [list(p.exterior.coords)] + [list(h.coords) for h in p.interiors]
    m = 1.0 / config.FT                         # feet -> metre
    pts = [(x * m, y * m) for w in walls for x, y in _line(w)]
    pts += [(x * m, y * m) for r in rooms for x, y in r["polygon_ft"]]
    pts += [(x * m, y * m) for ring in rings for x, y in ring]
    if not pts:
        pts = [(0.0, 0.0), (1.0, 1.0)]
    arr = np.asarray(pts, dtype=np.float64)
    lo = arr.min(axis=0) - preview.MARGIN_M
    hi = arr.max(axis=0) + preview.MARGIN_M
    scale = min(100.0, preview.MAX_SIDE_PX / max(float((hi - lo).max()), 1e-6))
    width, height = (np.ceil((hi - lo) * scale)).astype(int) + 1
    img = np.full((height, width + 1, 3), 255, np.uint8)

    def px(p):
        return (int(round((p[0] * m - lo[0]) * scale)),
                int(round(height - 1 - (p[1] * m - lo[1]) * scale)))

    for r in rooms:
        cv2.fillPoly(img, [np.array([px(p) for p in r["polygon_ft"]], dtype=np.int32)],
                     preview.ROOM_FILL)
    for ring in rings:
        cv2.polylines(img, [np.array([px(p) for p in ring], dtype=np.int32)], True,
                      (0, 0, 0), 1, cv2.LINE_AA)
    for r in rooms:
        cv2.putText(img, r["name"], px(r["label_point_ft"]), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    preview.TEXT_COLOR, 1, cv2.LINE_AA)
    stroke = max(2, int(round(0.06 * scale)))
    by_id = {}
    for w in walls:
        by_id[w["id"]] = w
        cv2.line(img, px(w["start_ft"]), px(w["end_ft"]),
                 preview.STATUS_COLORS.get(w.get("status"), (0, 0, 0)), stroke, cv2.LINE_AA)
    for o in ops:
        host = by_id.get(o["host_id"])
        if host is None or _length(host) <= 1e-9:
            continue
        half = float(o.get("width_ft") or 0.0) / 2.0
        a = _point_at(_line(host), o["offset_ft"] - half)
        b = _point_at(_line(host), o["offset_ft"] + half)
        cv2.line(img, px(a), px(b), preview.OPENING_COLOR, stroke + 2, cv2.LINE_AA)
    for s in doc.get("room_separations") or []:
        if s["floor"] == floor:
            cv2.line(img, px(s["start_ft"]), px(s["end_ft"]), (200, 0, 200), 2, cv2.LINE_AA)
    for st in doc.get("stairs") or []:
        if st["floor"] != floor:
            continue
        (sx, sy), (ex, ey) = st["start_ft"], st["end_ft"]
        run = math.hypot(ex - sx, ey - sy) or 1.0
        nx, ny = -(ey - sy) / run * st["width_ft"] / 2.0, (ex - sx) / run * st["width_ft"] / 2.0
        box = [(sx + nx, sy + ny), (ex + nx, ey + ny), (ex - nx, ey - ny), (sx - nx, sy - ny)]
        cv2.polylines(img, [np.array([px(p) for p in box], dtype=np.int32)], True,
                      (200, 160, 0), 2, cv2.LINE_AA)
        cv2.arrowedLine(img, px((sx, sy)), px((ex, ey)), (200, 160, 0), 2, cv2.LINE_AA,
                        tipLength=0.15)
        if st.get("kind") == "turn":
            # Donus karesi + donusten once / sonra yon (L ok).
            (cx, cy), w = st["corner_ft"], st["width_ft"]
            u1, u2 = st["u1"], st["u2"]
            sq = [(cx + (a * u1[0] + b * u2[0]) * w / 2.0, cy + (a * u1[1] + b * u2[1]) * w / 2.0)
                  for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            cv2.polylines(img, [np.array([px(p) for p in sq], dtype=np.int32)], True,
                          (200, 160, 0), 1, cv2.LINE_AA)
            a = (cx - u1[0] * w, cy - u1[1] * w)
            b = (cx + u2[0] * w, cy + u2[1] * w)
            cv2.line(img, px(a), px((cx, cy)), (200, 160, 0), 2, cv2.LINE_AA)
            cv2.arrowedLine(img, px((cx, cy)), px(b), (200, 160, 0), 2, cv2.LINE_AA, tipLength=0.3)
    cv2.putText(img, "Kat {} PROTOTIP  yesil=olculdu  turuncu=duzeltildi  kirmizi=varsayildi  "
                "siyah=doseme izi  mor=oda ayirici  camgobegi=merdiven (ok: cikis)".format(floor), (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 0), 1, cv2.LINE_AA)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG kodlanamadi: {}".format(path))
    path.write_bytes(buf.tobytes())
    return path
