"""
pyKalfa / Rolove - DXF duvarlarini taramaya gore iyilestirme

Hizalanmis her DXF duvari icin (tarama cercevesi, metre):

  1. Ic/dis: duvarin %25/%50/%75 noktalarindan iki yana yoklama; iki yan da
     bir odanin icindeyse `interior`, degilse `exterior` (oda tarafi =
     icerde kalan yoklama; hic oda yoksa daha cok nokta goren taraf).
  2. Yuz arama: duvar boyunca ince bir seritteki noktalarin dik uzaklik
     histogrami (her (boy, yukseklik) hucresi bir kez sayilir) — en guclu
     tepe gercek yuzdur. Arama DXF yuzunun `FACE_SEARCH_M` otesine kadar
     gider; boylece buyuk kaymalar "gorulmedi" degil "kayik" olarak
     yakalanir ve duzeltilmez.
  3. Yuz uydurma: tepe etrafindaki `FACE_FIT_M` bandi -> PCA dogru, en kotu
     `FACE_TRIM` atilip yeniden.
  4. Dis duvar: `line` = ic yuz. Ic duvar: iki yuz goruldu ise `line` = orta,
     kalinlik olculur; tek yuz ise DXF kalinligiyla eksen.

Veri trasi yok: uydurulamayan ya da sinirlari asan duvarda DXF konumu
kalir, `status="varsayildi"` ve uyari yazilir. Konumlar yuvarlanmaz;
yalniz kalinlik grubu ve yukseklik `round_dim` ile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

import config
import geom2d


@dataclass
class RefinedWall:
    floor: int
    dxf_center: tuple            # DXF cercevesinde ham eksen (izlenebilirlik)
    side: str                    # "exterior" | "interior"
    location: str                # "interior_face" | "center"
    line: tuple                  # tarama cercevesi
    outward: tuple | None        # dis duvar: odadan disa birim normal
    thickness_dxf: float
    measured_thickness: float | None
    thickness_group_m: float | None
    height: float
    height_status: str
    status: str                  # "olculdu" | "duzeltildi" | "varsayildi"
    deviation_cm: float
    support: int
    warnings: list = field(default_factory=list)
    # Tek yuzu gorulen ic duvar: yuzun `line`'a gore yani (+1 sol normal, -1 sag).
    # Kalinlik sonradan (bina geneli grup) degisirse `line` bu yuz sabit kalacak
    # sekilde kaydirilir (bkz. prepare_rolove_input._assign_interior_groups).
    face_side: float | None = None


# --------------------------------------------------------------------------
# Nokta indeksi
# --------------------------------------------------------------------------

class _GridIndex:
    """XY izgara indeksi: kutu sorgusu, satir basina bir `searchsorted`."""

    def __init__(self, xy: np.ndarray, cell: float):
        self.cell = cell
        self.xy = xy
        if not len(xy):
            self.nx = self.ny = 0
            return
        keys = np.floor(xy / cell).astype(np.int64)
        self.k0 = keys.min(axis=0)
        keys -= self.k0
        self.nx, self.ny = (keys.max(axis=0) + 1).tolist()
        lin = keys[:, 0] * self.ny + keys[:, 1]
        self.order = np.argsort(lin, kind="stable")
        self.sorted = lin[self.order]

    def query(self, xmin, ymin, xmax, ymax) -> np.ndarray:
        if not self.nx:
            return np.zeros(0, dtype=np.int64)
        c = self.cell
        cx0 = max(int(math.floor(xmin / c)) - self.k0[0], 0)
        cx1 = min(int(math.floor(xmax / c)) - self.k0[0], self.nx - 1)
        cy0 = max(int(math.floor(ymin / c)) - self.k0[1], 0)
        cy1 = min(int(math.floor(ymax / c)) - self.k0[1], self.ny - 1)
        if cx0 > cx1 or cy0 > cy1:
            return np.zeros(0, dtype=np.int64)
        cols = np.arange(cx0, cx1 + 1, dtype=np.int64) * self.ny
        lo = np.searchsorted(self.sorted, cols + cy0, side="left")
        hi = np.searchsorted(self.sorted, cols + cy1, side="right")
        parts = [self.order[a:b] for a, b in zip(lo, hi) if b > a]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)


class _Strip:
    """Bir referans dogruya gore yerel (t, d, z) koordinatli noktalar."""

    def __init__(self, ref, xy, z, d_lo, d_hi):
        self.ref = ref
        self.length = geom2d.seg_length(ref)
        self.p1 = np.asarray(ref[0], dtype=np.float64)
        self.u = np.asarray(geom2d.seg_dir(ref))
        self.n = np.asarray(geom2d.seg_normal(ref))
        self.margin = min(config.FACE_END_MARGIN_M, self.length / 4.0)
        rel = xy - self.p1
        t = rel @ self.u
        d = rel @ self.n
        keep = ((t >= self.margin) & (t <= self.length - self.margin)
                & (d >= d_lo) & (d <= d_hi))
        self.xy, self.z, self.t, self.d = xy[keep], z[keep], t[keep], d[keep]
        self.d_lo, self.d_hi = d_lo, d_hi

    def histogram(self):
        """(kutu merkezleri, yumusatilmis agirlik) — her (d, t, z) hucresi 1 kez."""
        hb = config.FACE_HIST_BIN_M
        nb = int(math.ceil((self.d_hi - self.d_lo) / hb)) + 1
        centers = self.d_lo + (np.arange(nb) + 0.5) * hb
        if not len(self.d):
            return centers, np.zeros(nb)
        db = np.clip(((self.d - self.d_lo) / hb).astype(np.int64), 0, nb - 1)
        tc = np.floor(self.t / config.FACE_CELL_M).astype(np.int64)
        zc = np.floor(self.z / config.FACE_CELL_M).astype(np.int64)
        tc -= tc.min()
        zc -= zc.min()
        nt, nz = int(tc.max()) + 1, int(zc.max()) + 1
        key = (db * nt + tc) * nz + zc
        uniq_db = np.unique(key) // (nt * nz)
        hist = np.bincount(uniq_db, minlength=nb).astype(np.float64)
        kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
        return centers, np.convolve(hist, kernel / kernel.sum(), mode="same")


@dataclass
class _Face:
    point: np.ndarray
    direction: np.ndarray
    count: int
    coverage: float
    offset: float               # referansa gore isaretli dik uzaklik (orta noktada)
    rot_deg: float

    @property
    def seen(self):
        return (self.count >= config.FACE_MIN_POINTS
                and self.coverage >= config.FACE_MIN_COVERAGE)


def _pca_line(xy):
    m = xy.mean(axis=0)
    cov = np.cov((xy - m).T)
    w, v = np.linalg.eigh(cov)
    return m, v[:, np.argmax(w)]


def _fit_face(strip: _Strip, peak_d: float):
    sel = np.abs(strip.d - peak_d) <= config.FACE_FIT_M
    xy, t = strip.xy[sel], strip.t[sel]
    if len(xy) < 3:
        return None
    m, v = _pca_line(xy)
    nv = np.array([-v[1], v[0]])
    r = np.abs((xy - m) @ nv)
    keep = r <= np.quantile(r, 1.0 - config.FACE_TRIM)
    if keep.sum() >= 3:
        xy, t = xy[keep], t[keep]
        m, v = _pca_line(xy)
    if float(v @ strip.u) < 0:
        v = -v
    usable = max(strip.length - 2 * strip.margin, config.FACE_CELL_M)
    bins = np.unique(np.floor(t / config.FACE_CELL_M).astype(np.int64)).size
    coverage = min(bins / math.ceil(usable / config.FACE_CELL_M), 1.0)
    mid = strip.p1 + strip.u * (strip.length / 2.0)
    q = _project_on_line(mid, m, v)
    offset = float((q - mid) @ strip.n)
    rot = math.degrees(math.acos(min(abs(float(v @ strip.u)), 1.0)))
    return _Face(m, v, int(len(xy)), coverage, offset, rot)


def _project_on_line(p, m, v):
    p = np.asarray(p, dtype=np.float64)
    return m + ((p - m) @ v) * v


def _line_from(ref, m, v):
    a = _project_on_line(ref[0], m, v)
    b = _project_on_line(ref[1], m, v)
    return ((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))


def _seg_tuple(seg):
    return tuple((float(p[0]), float(p[1])) for p in seg)


def _deviation_cm(ref, line):
    return 100.0 * max(abs(geom2d.project(ref, p)[1]) for p in line)


def _first_peak(hist, start, step, thresh):
    """`start`tan `step` yonunde ilerlerken esigi gecen ilk yerel tepe."""
    n = len(hist)
    i = start
    while 0 <= i < n:
        if (hist[i] >= thresh and (i == 0 or hist[i] >= hist[i - 1])
                and (i == n - 1 or hist[i] >= hist[i + 1])):
            return i
        i += step
    return None


def _edge_peak(strip: _Strip, room_sign: float):
    """Dis duvar: yuz, nokta kutlesinin DIS kenarindaki ilk guclu tepedir
    (esya hep oda tarafinda kalir; duvarin arkasi taranmaz)."""
    centers, hist = strip.histogram()
    if not hist.any():
        return None
    thresh = config.FACE_EDGE_RATIO * hist.max()
    i = (_first_peak(hist, 0, 1, thresh) if room_sign > 0
         else _first_peak(hist, len(hist) - 1, -1, thresh))
    return None if i is None else float(centers[i])


def _void_peaks(strip: _Strip, t: float):
    """Ic duvar: DXF eksenine yakin bos bant (duvar govdesi) bulunur; iki
    yuz, bu bosluktan iki yana ilerlerken rastlanan ilk guclu tepelerdir.
    Doner: [d-, d+] (bulunamayan None)."""
    centers, hist = strip.histogram()
    if not hist.any():
        return [None, None]
    thresh = config.FACE_EDGE_RATIO * hist.max()
    n = len(hist)
    peak = np.array([hist[i] >= thresh and (i == 0 or hist[i] >= hist[i - 1])
                     and (i == n - 1 or hist[i] >= hist[i + 1]) for i in range(n)])
    peak_idx = np.where(peak)[0]
    near = ((np.abs(centers) <= t / 2.0 + config.FACE_VOID_SEARCH_M)
            & (hist <= config.FACE_VOID_RATIO * hist.max()))
    cand = np.where(near)[0]
    if not len(cand):
        return [None, None]
    # Iki yandan yuzle cevrili bosluk (duvar govdesi) tek yanli bosluga
    # (yuzun otesindeki seyrek oda) tercih edilir.
    bracketed = np.array([peak_idx.size > 0 and peak_idx.min() < i < peak_idx.max()
                          for i in cand])
    if bracketed.any():
        cand = cand[bracketed]
    lowest = hist[cand].min()
    ties = cand[hist[cand] <= lowest + 1e-9]
    void = int(ties[np.argmin(np.abs(centers[ties]))])
    lo = _first_peak(hist, void - 1, -1, thresh)
    hi = _first_peak(hist, void + 1, 1, thresh)
    return [None if lo is None else float(centers[lo]),
            None if hi is None else float(centers[hi])]


# --------------------------------------------------------------------------
# Ic / dis
# --------------------------------------------------------------------------

def _probe_sides(center, t, rooms):
    """(sol odalar, sag odalar) — sol = `seg_normal` yonu."""
    (x1, y1), (x2, y2) = center
    nx, ny = geom2d.seg_normal(center)
    reach = t / 2.0 + config.SIDE_PROBE_M
    left, right = set(), set()
    for f in config.SIDE_PROBE_FRACTIONS:
        px, py = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
        for sign, bucket in ((1.0, left), (-1.0, right)):
            q = (px + nx * reach * sign, py + ny * reach * sign)
            for room in rooms:
                if geom2d.point_in_polygon(q, room.polygon):
                    bucket.add(room.name)
    return left, right


def _points_side(center, t, xy, index):
    """Oda bulunamadiginda: hangi yanda daha cok nokta var (+1 sol / -1 sag / 0)."""
    reach = t / 2.0 + 0.50
    pts = xy[_bbox_index(center, reach, index)]
    if not len(pts):
        return 0
    p1 = np.asarray(center[0], dtype=np.float64)
    u = np.asarray(geom2d.seg_dir(center))
    n = np.asarray(geom2d.seg_normal(center))
    length = geom2d.seg_length(center)
    rel = pts - p1
    tt, dd = rel @ u, rel @ n
    mid = (tt > length * 0.2) & (tt < length * 0.8)
    left = int(np.sum(mid & (dd > t / 2.0) & (dd <= reach)))
    right = int(np.sum(mid & (dd < -t / 2.0) & (dd >= -reach)))
    return 0 if left == right else (1 if left > right else -1)


def _bbox_index(seg, reach, index):
    (x1, y1), (x2, y2) = seg
    return index.query(min(x1, x2) - reach, min(y1, y2) - reach,
                       max(x1, x2) + reach, max(y1, y2) + reach)


# --------------------------------------------------------------------------
# Yukseklik
# --------------------------------------------------------------------------

def _height(room_names, report_by_name, level):
    neigh = [report_by_name[n] for n in sorted(room_names) if n in report_by_name]
    sloped = [r for r in neigh if r.ceiling_min is not None and r.ceiling_max is not None
              and r.ceiling_min != r.ceiling_max]
    if sloped:
        return config.round_dim(max(r.ceiling_max for r in sloped)), "varsayildi"
    if level.ceiling_z is not None:
        return config.round_dim(level.ceiling_z - level.floor_z), "olculdu"
    single = [r.ceiling_max for r in neigh if r.ceiling_max is not None]
    if single:
        return config.round_dim(max(single)), "olculdu"
    return config.round_dim(config.DEFAULT_WALL_HEIGHT_M), "varsayildi"


# --------------------------------------------------------------------------
# Duvar
# --------------------------------------------------------------------------

def _too_far(offset, rot):
    return abs(offset) > config.MAX_SHIFT_M or rot > config.MAX_ROT_DEG


def _far_msg(what, offset, rot):
    return "{} {:.0f} cm / {:.1f} derece kayik: duzeltilmedi (siniri {:.0f} cm / {:.1f} derece)".format(
        what, abs(offset) * 100, rot, config.MAX_SHIFT_M * 100, config.MAX_ROT_DEG)


def _refine_exterior(center, t, room_sign, xy, z, index, warnings, info):
    ref = geom2d.offset_seg(center, room_sign * t / 2.0)
    s = config.FACE_SEARCH_M
    idx = _bbox_index(ref, s, index)
    strip = _Strip(ref, xy[idx], z[idx], -s, s)
    peak = _edge_peak(strip, room_sign)
    face = _fit_face(strip, peak) if peak is not None else None
    outward = tuple(float(c) for c in (-room_sign * np.asarray(geom2d.seg_normal(center))))
    if face is None or not face.seen:
        warnings.append("ic yuz taramada gorulmedi: DXF konumu kullanildi")
        return _seg_tuple(ref), outward, "varsayildi", 0, ref
    if _too_far(face.offset, face.rot_deg):
        warnings.append(_far_msg("ic yuz", face.offset, face.rot_deg))
        info["scan_line"] = _line_from(ref, face.point, face.direction)
        return _seg_tuple(ref), outward, "varsayildi", face.count, ref
    return _line_from(ref, face.point, face.direction), outward, "duzeltildi", face.count, ref


def _refine_interior(center, t, xy, z, index, warnings, info):
    """(line, status, support, measured_thickness). `info`: duzeltme
    reddedildiyse "scan_line" (taramanin gosterdigi eksen); tek yuzde
    "face_side" (gorulen yuzun eksene gore yani, +1 sol / -1 sag)."""
    s = t / 2.0 + config.FACE_SEARCH_M
    idx = _bbox_index(center, s, index)
    strip = _Strip(center, xy[idx], z[idx], -s, s)
    faces = [f for f in (_fit_face(strip, p) for p in _void_peaks(strip, t) if p is not None)
             if f is not None and f.seen]
    if len(faces) == 2:
        a, b = sorted(faces, key=lambda f: f.offset)
        angle = math.degrees(math.acos(min(abs(float(a.direction @ b.direction)), 1.0)))
        gap = abs(float((b.point - a.point) @ np.array([-a.direction[1], a.direction[0]])))
        lo, hi = config.THICKNESS_RANGE_M
        if angle <= config.FACE_PARALLEL_DEG and lo <= gap <= hi:
            la = _line_from(center, a.point, a.direction)
            lb = _line_from(center, b.point, b.direction)
            line = tuple(((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0) for pa, pb in zip(la, lb))
            offset = (a.offset + b.offset) / 2.0
            rot = max(a.rot_deg, b.rot_deg)
            if _too_far(offset, rot):
                warnings.append(_far_msg("duvar ekseni", offset, rot))
                info["scan_line"] = line
                return _seg_tuple(center), "varsayildi", a.count + b.count, None
            return line, "olculdu", a.count + b.count, gap
        warnings.append("iki yuz uyumsuz ({:.1f} derece, {:.0f} cm): tek yuz kullanildi".format(
            angle, gap * 100))
        faces = [max(faces, key=lambda f: f.count)]
    if len(faces) == 1:
        f = faces[0]
        sign = 1.0 if f.offset >= 0 else -1.0
        face_line = _line_from(center, f.point, f.direction)
        line = _seg_tuple(geom2d.offset_seg(face_line, -sign * t / 2.0))
        offset = f.offset - sign * t / 2.0
        if _too_far(offset, f.rot_deg):
            warnings.append(_far_msg("duvar ekseni", offset, f.rot_deg))
            info["scan_line"] = line
            return _seg_tuple(center), "varsayildi", f.count, None
        warnings.append("yalniz bir yuz goruldu: kalinlik olculemedi")
        info["face_side"] = sign
        return line, "duzeltildi", f.count, None
    warnings.append("yuzler taramada gorulmedi: DXF konumu kullanildi")
    return _seg_tuple(center), "varsayildi", 0, None


def refine_floor(walls, rooms_scan, tf, points, level, report_rooms) -> list:
    """Bir katin duvarlarini iyilestirir. `walls` DXF cercevesinde, `rooms_scan`
    onceden `tf` ile donusturulmus; sonuc tarama cercevesinde, ayni sirada."""
    zlo = level.floor_z + config.FACE_Z_MARGIN_M
    top = level.ceiling_z if level.ceiling_z is not None else (
        level.floor_z + config.DEFAULT_WALL_HEIGHT_M)
    zhi = top - config.FACE_Z_MARGIN_M
    pz = points[:, 2]
    sel = (pz >= zlo) & (pz <= zhi)
    xy = points[sel, :2].astype(np.float64)
    z = pz[sel].astype(np.float64)
    index = _GridIndex(xy, config.FACE_BAND_M)
    report_by_name = {r.name: r for r in report_rooms}

    out = []
    for w in walls:
        warnings = []
        info = {}
        center = tf.apply_seg(w.center)
        t = w.thickness
        left, right = _probe_sides(center, t, rooms_scan)
        rooms = left | right
        if left and right:
            side = "interior"
            line, status, support, measured = _refine_interior(center, t, xy, z, index, warnings, info)
            ref, outward, location = center, None, "center"
        else:
            side, location, measured = "exterior", "interior_face", None
            if left or right:
                room_sign = 1.0 if left else -1.0
            else:
                room_sign = float(_points_side(center, t, xy, index)) or 1.0
                warnings.append("yaninda oda yok: ic taraf nokta yogunlugundan secildi")
            line, outward, status, support, ref = _refine_exterior(
                center, t, room_sign, xy, z, index, warnings, info)
        height, height_status = _height(rooms, report_by_name, level)
        group = config.round_dim(measured) if measured is not None else None
        out.append(RefinedWall(
            floor=w.floor, dxf_center=w.center, side=side, location=location, line=line,
            outward=outward, thickness_dxf=t, measured_thickness=measured,
            thickness_group_m=group, height=height, height_status=height_status,
            status=status,
            deviation_cm=round(_deviation_cm(ref, info.get("scan_line", line)), 2),
            support=support, warnings=warnings, face_side=info.get("face_side")))
    return out


# --------------------------------------------------------------------------
# Kose birlestirme
# --------------------------------------------------------------------------

def _intersect(s1, s2):
    (x1, y1), (x2, y2) = s1
    (x3, y3), (x4, y4) = s2
    d1x, d1y = x2 - x1, y2 - y1
    d2x, d2y = x4 - x3, y4 - y3
    den = d1x * d2y - d1y * d2x
    l1, l2 = math.hypot(d1x, d1y), math.hypot(d2x, d2y)
    if l1 == 0 or l2 == 0 or abs(den) / (l1 * l2) < math.sin(math.radians(config.PARALLEL_DEG)):
        return None
    s = ((x3 - x1) * d2y - (y3 - y1) * d2x) / den
    return (x1 + d1x * s, y1 + d1y * s)


def _set_end(wall, k, p):
    p = (float(p[0]), float(p[1]))
    wall.line = (p, wall.line[1]) if k == 0 else (wall.line[0], p)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def join_corners(walls: list, snap_m: float) -> int:
    """Farkli duvarlarin `snap_m` icindeki uclarini dogrularin kesisimine
    tasir (paralelse ortalamaya); bos kalan bir uc baska bir duvarin
    govdesine `snap_m` icindeyse (T birlesim) o dogruya uzatilir/kisaltilir.
    Tasinan uc sayisini dondurur."""
    pairs = []
    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            for k in (0, 1):
                for m in (0, 1):
                    d = _dist(walls[i].line[k], walls[j].line[m])
                    if d <= snap_m:
                        pairs.append((d, i, k, j, m))
    pairs.sort()
    used = set()
    moved = 0
    for d, i, k, j, m in pairs:
        if (i, k) in used or (j, m) in used:
            continue
        a, b = walls[i].line[k], walls[j].line[m]
        p = _intersect(walls[i].line, walls[j].line)
        if p is None or _dist(p, a) > 2 * snap_m or _dist(p, b) > 2 * snap_m:
            p = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        _set_end(walls[i], k, p)
        _set_end(walls[j], m, p)
        used.update({(i, k), (j, m)})
        moved += 2

    for i, w in enumerate(walls):
        for k in (0, 1):
            if (i, k) in used:
                continue
            end = w.line[k]
            best = None
            for j, other in enumerate(walls):
                if j == i:
                    continue
                t, d = geom2d.project(other.line, end)
                if abs(d) <= snap_m and 0.0 < t < geom2d.seg_length(other.line):
                    p = _intersect(w.line, other.line)
                    if p is not None and _dist(p, end) <= 2 * snap_m:
                        if best is None or abs(d) < best[0]:
                            best = (abs(d), p)
            if best is not None:
                _set_end(w, k, best[1])
                used.add((i, k))
                moved += 1
    return moved
