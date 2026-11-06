"""
pyKalfa / Rolove - DXF katini taramaya 2B rijit hizalama

Polycam katlari paftaya yan yana dizer; her katin DXF koordinati farkli
bir ofsettedir (ve ilke olarak donuk/aynali olabilir). Bu modul bir katin
DXF duvar yuzlerini, o katin dosemeden ~1.0-1.6 m yukseklikteki yatay
dilimine oturtur:

  1. 8 aday (0/90/180/270 derece x ayna) icin yuzler ve dilim ayni
     izgaraya rasterlenir; FFT capraz korelasyonu en iyi otelemeyi verir.
  2. En iyi aday ICP (nokta -> en yakin yuz, 2B Procrustes) ile inceltilir;
     ek donus `ALIGN_MAX_REFINE_DEG` ile sinirli.
  3. RMS ve "destek orani" olculur; esikleri gecmeyen kat `ok=False` olur
     ve nedeni yazilir (sessizce modele basilmaz).

Tek rijit donusum: kat ici LiDAR kaymasi duzeltilmez (spec).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import config


@dataclass
class Transform2D:
    rot_deg: float
    mirror: bool
    tx: float
    ty: float

    def _rot(self):
        a = math.radians(self.rot_deg)
        return math.cos(a), math.sin(a)

    def apply_dir(self, v):
        arr = np.asarray(v, dtype=np.float64)
        single = arr.ndim == 1
        p = arr.reshape(-1, 2).copy()
        if self.mirror:
            p[:, 1] = -p[:, 1]
        c, s = self._rot()
        out = np.stack([c * p[:, 0] - s * p[:, 1], s * p[:, 0] + c * p[:, 1]], axis=1)
        return tuple(out[0]) if single else out

    def apply(self, xy):
        arr = np.asarray(xy, dtype=np.float64)
        single = arr.ndim == 1
        out = np.asarray(self.apply_dir(arr.reshape(-1, 2))) + np.array([self.tx, self.ty])
        return tuple(out[0]) if single else out

    def apply_seg(self, seg):
        a = self.apply(seg[0])
        b = self.apply(seg[1])
        return ((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))


@dataclass
class Alignment:
    floor: int
    transform: Transform2D
    rms_m: float
    support_ratio: float
    ok: bool
    reason: str
    slice_band: tuple = (1.0, 1.6)


def slice_xy(points: np.ndarray, floor_z: float, band=None) -> np.ndarray:
    lo, hi = band or config.ALIGN_SLICE
    z = points[:, 2]
    xy = points[(z >= floor_z + lo) & (z <= floor_z + hi), :2].astype(np.float64)
    if not len(xy):
        return np.zeros((0, 2))
    cell = config.ALIGN_GRID_M
    keys = np.floor(xy / cell).astype(np.int64)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    counts = np.bincount(inv)
    sx = np.bincount(inv, weights=xy[:, 0]) / counts
    sy = np.bincount(inv, weights=xy[:, 1]) / counts
    return np.stack([sx, sy], axis=1)


def _sample_faces(faces, step):
    out = []
    for (x1, y1), (x2, y2) in faces:
        n = max(int(math.hypot(x2 - x1, y2 - y1) / step) + 1, 2)
        t = np.linspace(0.0, 1.0, n)
        out.append(np.stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t], axis=1))
    return np.vstack(out) if out else np.zeros((0, 2))


def _raster(pts, origin, shape, cell):
    img = np.zeros(shape, dtype=np.float64)
    ij = np.floor((pts - origin) / cell).astype(np.int64)
    ok = (ij[:, 0] >= 0) & (ij[:, 1] >= 0) & (ij[:, 0] < shape[0]) & (ij[:, 1] < shape[1])
    img[ij[ok, 0], ij[ok, 1]] = 1.0
    # 1 hucre genisletme: gurultuye ve ince yuz farklarina tolerans
    grown = img.copy()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            grown = np.maximum(grown, np.roll(np.roll(img, di, 0), dj, 1))
    return grown


def _coarse(model_pts, scan_pts, candidates):
    """(skor, Transform2D) — adaylar arasinda FFT korelasyonuyla en iyisi."""
    cell = config.ALIGN_GRID_M
    s_min = scan_pts.min(axis=0)
    s_shape = tuple((np.ceil((scan_pts.max(axis=0) - s_min) / cell) + 1).astype(int))
    B = _raster(scan_pts, s_min, s_shape, cell)
    best = None
    for rot, mirror in candidates:
        t = Transform2D(rot, mirror, 0.0, 0.0)
        m = np.asarray(t.apply(model_pts))
        m_min = m.min(axis=0)
        m_shape = tuple((np.ceil((m.max(axis=0) - m_min) / cell) + 1).astype(int))
        A = _raster(m, m_min, m_shape, cell)
        shape = (s_shape[0] + m_shape[0], s_shape[1] + m_shape[1])
        corr = np.fft.irfft2(np.fft.rfft2(B, shape) * np.conj(np.fft.rfft2(A, shape)), shape)
        k = np.unravel_index(int(np.argmax(corr)), shape)
        di = k[0] - shape[0] if k[0] > shape[0] // 2 else k[0]
        dj = k[1] - shape[1] if k[1] > shape[1] // 2 else k[1]
        score = corr[k] / math.sqrt(A.sum() * B.sum())
        shift = s_min - m_min + np.array([di, dj]) * cell
        cand = Transform2D(rot, mirror, float(shift[0]), float(shift[1]))
        if best is None or score > best[0]:
            best = (score, cand)
    return best


def _closest_on_segments(p, a, b):
    """p (N,2), segmentler a,b (M,2) -> (en yakin nokta (N,2), uzaklik (N,))."""
    best_d = np.full(len(p), np.inf)
    best_q = np.zeros_like(p)
    ab = b - a
    ab2 = np.maximum((ab ** 2).sum(axis=1), 1e-12)
    for start in range(0, len(p), 20000):
        pp = p[start:start + 20000]
        t = np.clip(((pp[:, None, :] - a[None]) * ab[None]).sum(axis=2) / ab2[None], 0, 1)
        q = a[None] + t[..., None] * ab[None]
        d = np.linalg.norm(pp[:, None, :] - q, axis=2)
        k = np.argmin(d, axis=1)
        idx = np.arange(len(pp))
        best_d[start:start + len(pp)] = d[idx, k]
        best_q[start:start + len(pp)] = q[idx, k]
    return best_q, best_d


def _segments(faces, t):
    segs = [t.apply_seg(f) for f in faces]
    a = np.array([s[0] for s in segs])
    b = np.array([s[1] for s in segs])
    return a, b


def _icp(faces, scan_pts, t0):
    t = Transform2D(t0.rot_deg, t0.mirror, t0.tx, t0.ty)
    for _ in range(config.ALIGN_ICP_ITERS):
        a, b = _segments(faces, t)
        q, d = _closest_on_segments(scan_pts, a, b)
        near = d <= config.ALIGN_ICP_MAX_DIST
        if near.sum() < 10:
            break
        # Kirpilmis ICP: duvar dibindeki mobilya/esya noktalarini, yaricapi
        # eslesmelerin medyanina gore daraltarak disarida birak.
        radius = min(config.ALIGN_ICP_MAX_DIST,
                     max(config.ALIGN_ICP_MIN_DIST, 3.0 * float(np.median(d[near]))))
        sel = d <= radius
        if sel.sum() < 10:
            break
        P, Q = scan_pts[sel], q[sel]
        pc, qc = P.mean(axis=0), Q.mean(axis=0)
        H = (Q - qc).T @ (P - pc)
        U, _, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[1] *= -1
            R = Vt.T @ U.T
        dth = math.degrees(math.atan2(R[1, 0], R[0, 0]))
        new_rot = t.rot_deg + dth
        if abs(new_rot - t0.rot_deg) > config.ALIGN_MAX_REFINE_DEG:
            break
        tv = R @ np.array([t.tx, t.ty]) + (pc - R @ qc)
        t = Transform2D(new_rot, t.mirror, float(tv[0]), float(tv[1]))
        if abs(dth) < 1e-4 and np.linalg.norm(pc - R @ qc) < 1e-5:
            break
    return t


def _quality(walls, scan_pts, t):
    """(rms, destek_orani).

    rms: yuzlere `ALIGN_INLIER_M` icindeki noktalarin (duvar noktalari)
    uzaklik RMS'i — mobilya gibi uzak noktalar oturmanin kalitesini
    olcmez.

    Destek DUVAR basina olculur: duvar ekseni `SUPPORT_BIN_M` kutulara
    bolunur; bir kutu, ekseninden dik uzakligi t/2 + `SUPPORT_DIST_M`
    icinde en az bir tarama noktasi varsa desteklidir (iki yuzden biri
    yeter — dis duvarin dis yuzu iceriden gorunmez). Oran uzunluk
    agirliklidir."""
    faces = [f for w in walls for f in w.faces()]
    a, b = _segments(faces, t)
    _, d = _closest_on_segments(scan_pts, a, b)
    near = d[d <= config.ALIGN_INLIER_M]
    rms = float(np.sqrt(np.mean(near ** 2))) if len(near) else float("inf")
    inlier_ratio = len(near) / max(len(scan_pts), 1)

    total = supported = 0
    for w in walls:
        (x1, y1), (x2, y2) = t.apply_seg(w.center)
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            continue
        u = np.array([(x2 - x1) / length, (y2 - y1) / length])
        n = np.array([-u[1], u[0]])
        r = scan_pts - np.array([x1, y1])
        along = r @ u
        perp = np.abs(r @ n)
        sel = (along >= 0) & (along <= length) & (perp <= w.thickness / 2 + config.SUPPORT_DIST_M)
        nbins = max(int(math.ceil(length / config.SUPPORT_BIN_M)), 1)
        hit = np.unique(np.minimum((along[sel] / config.SUPPORT_BIN_M).astype(int), nbins - 1))
        total += nbins
        supported += len(hit)
    return rms, supported / max(total, 1), inlier_ratio


ALL_CANDIDATES = [(rot, mirror) for mirror in (False, True) for rot in (0, 90, 180, 270)]


def align_floor(floor: int, walls: list, slice_pts: np.ndarray, prefer=None) -> Alignment:
    """`walls`: `DxfWall` listesi (DXF cercevesi). `prefer=(rot, ayna)`:
    verilirse o aday da tam olarak denenir ve serbest en iyi aday destekte
    `ALIGN_PREFER_MARGIN`'den fazla ustun degilse tercih edilir (simetrik
    katlarda diger katlarin yonu kullanilsin diye)."""
    ident = Transform2D(0.0, False, 0.0, 0.0)
    if not walls:
        return Alignment(floor, ident, float("inf"), 0.0, False, "katta duvar yok")
    if len(slice_pts) < 50:
        return Alignment(floor, ident, float("inf"), 0.0, False,
                         "taramada bu kat icin yeterli nokta yok")
    faces = [f for w in walls for f in w.faces()]
    model = _sample_faces(faces, config.ALIGN_GRID_M / 2)

    def solve(cands):
        _score, coarse = _coarse(model, slice_pts, cands)
        t = _icp(faces, slice_pts, coarse)
        return (t,) + _quality(walls, slice_pts, t)

    t, rms, support, inliers = solve(ALL_CANDIDATES)
    if prefer is not None:
        pt, prms, psupport, pinl = solve([tuple(prefer)])
        if support - psupport <= config.ALIGN_PREFER_MARGIN and prms <= config.ALIGN_RMS_MAX:
            t, rms, support, inliers = pt, prms, psupport, pinl
    reasons = []
    if inliers < config.ALIGN_INLIER_MIN:
        reasons.append("dilim noktalarinin yalniz %{:.0f}'i duvar yuzlerinde"
                       .format(inliers * 100))
    if rms > config.ALIGN_RMS_MAX:
        reasons.append("hizalama RMS {:.1f} cm > {:.1f} cm".format(rms * 100,
                                                                   config.ALIGN_RMS_MAX * 100))
    if support < config.ALIGN_SUPPORT_MIN:
        reasons.append("duvar yuzlerinin yalniz %{:.0f}'i taramada destekli".format(support * 100))
    return Alignment(floor, t, rms, support, not reasons, "; ".join(reasons))


def align_floor_auto(floor: int, walls: list, points: np.ndarray, floor_z: float,
                     prefer=None) -> Alignment:
    """`ALIGN_SLICES`'teki her dilim yuksekliginde hizalar; gecerli olanlar
    arasinda destegi en yuksek olani dondurur (hicbiri gecerli degilse
    destegi en yuksek gecersiz sonuc). Cati katinda diz duvarlari 1.0 m'nin
    altinda kalir; o katta alcak dilim kazanir."""
    best = None
    for band in config.ALIGN_SLICES:
        a = align_floor(floor, walls, slice_xy(points, floor_z, band), prefer=prefer)
        a.slice_band = tuple(band)
        key = (a.ok, a.support_ratio)
        if best is None or key > (best.ok, best.support_ratio):
            best = a
    return best
