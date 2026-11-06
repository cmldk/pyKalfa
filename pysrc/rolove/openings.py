"""
pyKalfa / Rolove - kapi / pencere / bosluk yerlestirme ve oda etiket noktasi

Her DXF acikligi, ayni DXF'ten gelen bir duvara baglanir (host): esleme
duvarin donusturulmus DXF ekseniyle yapilir (aciklik ve duvar ayni
cizimden geldigi icin tolerans kesindir); konum (`offset`) ise
iyilestirilmis `line` uzerinde olculur.

Olculer:
  - genislik: DXF'ten, `round_dim`, `olculdu`;
  - yukseklik: komsu odalarin CSV kayitlarinda genisligi `CSV_WIDTH_TOL_M`
    icinde kalan kayitlarin yukseklikleri tek bir degerde birlesiyorsa o
    deger `olculdu`; birden cok farkli yukseklik ya da hic kayit ->
    varsayilan, `varsayildi`;
  - parapet: pencere `DEFAULT_WINDOW_SILL_M` `varsayildi`; kapi/bosluk 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config
import geom2d

_DEFAULT_HEIGHT = {
    "door": config.DEFAULT_DOOR_HEIGHT_M,
    "window": config.DEFAULT_WINDOW_HEIGHT_M,
    "opening": config.DEFAULT_OPENING_HEIGHT_M,
}


@dataclass
class OpeningOut:
    floor: int
    kind: str                    # "door" | "window" | "opening"
    dxf_center: tuple            # DXF cercevesi (izlenebilirlik)
    host: int                    # katin RefinedWall listesindeki indeks
    offset: float                # host `line` basindan merkeze, metre
    width: float
    height: float
    sill: float
    status: dict                 # {"width", "height", "sill"} -> durum
    warnings: list = field(default_factory=list)


def _host_thickness(w):
    return w.measured_thickness if w.measured_thickness is not None else w.thickness_dxf


def _find_host(center, walls, tf):
    best = None
    for i, w in enumerate(walls):
        ref = tf.apply_seg(w.dxf_center)
        t, d = geom2d.project(ref, center)
        if not 0.0 <= t <= geom2d.seg_length(ref):
            continue
        if abs(d) <= _host_thickness(w) / 2.0 + config.HOST_TOL_M:
            if best is None or abs(d) < best[0]:
                best = (abs(d), i)
    return None if best is None else best[1]


def _neighbour_rooms(center, wall, rooms):
    nx, ny = geom2d.seg_normal(wall.line)
    reach = _host_thickness(wall) + config.OPENING_PROBE_M
    names = set()
    for sign in (1.0, -1.0):
        q = (center[0] + nx * reach * sign, center[1] + ny * reach * sign)
        for room in rooms:
            if geom2d.point_in_polygon(q, room.polygon):
                names.add(room.name)
    return names


def _csv_height(kind, width, names, report_by_name):
    if kind not in ("door", "window"):
        return None
    heights = set()
    for name in names:
        r = report_by_name.get(name)
        if r is None:
            continue
        for w, h in (r.doors if kind == "door" else r.windows):
            if abs(w - width) <= config.CSV_WIDTH_TOL_M:
                heights.add(config.round_dim(h))
    return heights.pop() if len(heights) == 1 else None


def _reject(op, reason):
    return {"kind": op.kind, "floor": op.floor,
            "dxf_center": (float(op.center[0]), float(op.center[1])), "reason": reason}


def place_openings(ops, walls, tf, rooms_scan, report_rooms):
    """(yerlesen acikliklar, reddedilenler)."""
    report_by_name = {r.name: r for r in report_rooms}
    out, rejected = [], []
    for op in ops:
        center = tf.apply(op.center)
        center = (float(center[0]), float(center[1]))
        host = _find_host(center, walls, tf)
        if host is None:
            rejected.append(_reject(op, "host duvar bulunamadi"))
            continue
        wall = walls[host]
        length = geom2d.seg_length(wall.line)
        if op.width > length:
            rejected.append(_reject(op, "aciklik duvardan genis ({:.2f} > {:.2f} m)".format(
                op.width, length)))
            continue
        offset, _ = geom2d.project(wall.line, center)
        width = config.round_dim(op.width)
        status = {"width": "olculdu"}
        warnings = []

        h = _csv_height(op.kind, op.width, _neighbour_rooms(center, wall, rooms_scan),
                        report_by_name)
        if h is not None:
            height, status["height"] = h, "olculdu"
        else:
            height, status["height"] = config.round_dim(_DEFAULT_HEIGHT[op.kind]), "varsayildi"
        if op.kind == "window":
            sill, status["sill"] = config.round_dim(config.DEFAULT_WINDOW_SILL_M), "varsayildi"
        else:
            sill, status["sill"] = 0.0, "olculdu"
        if sill + height > wall.height:
            clipped = max(config.round_dim(wall.height - sill), config.DIM_STEP_M)
            warnings.append("yukseklik {:.2f} m duvar yuksekligini asiyor: {:.2f} m'ye kirpildi".format(
                height, clipped))
            height = clipped
        out.append(OpeningOut(op.floor, op.kind, (float(op.center[0]), float(op.center[1])),
                              host, float(offset), width, height, sill, status, warnings))
    return out, rejected


def label_point(polygon) -> tuple:
    """Poligonun icinde garanti bir nokta: agirlik merkezi icerdeyse o;
    degilse yatay tarama cizgilerinde en genis ic araligin ortasi."""
    n = len(polygon)
    cx = sum(p[0] for p in polygon) / n
    cy = sum(p[1] for p in polygon) / n
    if geom2d.point_in_polygon((cx, cy), polygon):
        return (cx, cy)
    ys = [p[1] for p in polygon]
    ymin, ymax = min(ys), max(ys)
    best = None
    for frac in (0.5, 0.25, 0.75, 0.125, 0.375, 0.625, 0.875):
        y = ymin + (ymax - ymin) * frac
        xs = []
        for i in range(n):
            (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            if best is None or b - a > best[0]:
                best = (b - a, ((a + b) / 2.0, y))
    return best[1] if best else (cx, cy)
