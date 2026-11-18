"""
pyKalfa / Rolove Prototip - merdivenler (Polycam DXF + LAZ).

Polycam kat plani DXF'inde merdiven ayri katman degildir: `Objects-Fixtures`
katmaninda iki noktali cizgiler olarak durur (dis cerceve + basamak
kenarlari). CSV merdiven sayisini ve olcusunu verir ama konumu vermez.

  1. `find_strips`: ayni uzunlukta, paralel, ortalari hizali ve ESIT
     aralikli >= MIN_LINES cizgi = merdiven (aralik = basamak derinligi,
     uzunluk = merdiven genisligi, cizgi sayisi - 1 = basamak).
  2. `orient`: nokta bulutunda basamak basina medyan yukseklik; yukseklik
     hangi yone artiyorsa merdiven o yone cikar ("olculdu"). Olculemezse
     cizildigi yon kalir ("varsayildi").
  3. `records`: ustunde kat olan her merdiven alt kattan ust kata (Revit
     Stairs iki Level arasinda; riht/kol secilen tipten hesaplanir);
     kimlik `p-stairs-<kat>-<k>`.

Koordinatlar metre; `records` feet yazar (JSON sozlesmesi).
"""

from __future__ import annotations

import math

import config

WIDTH_MIN_M, WIDTH_MAX_M = 0.5, 2.0       # merdiven genisligi (cizgi uzunlugu)
DEPTH_MIN_M, DEPTH_MAX_M = 0.15, 0.45     # basamak derinligi (cizgi araligi)
LEN_TOL_M = 0.03
ALIGN_TOL_M = 0.03
GAP_TOL_M = 0.025
PARALLEL_DEG = 1.0
MIN_LINES = 4                             # >= 3 basamak
DUP_M = 0.01
MIN_POINTS_PER_TREAD = 10
MIN_MEASURED_TREADS = 3
MIN_RISE_M = 0.5                          # olculen toplam yukselme bundan azsa yon belirsiz
MIN_INSIDE_FRAC = 0.75                    # seridin bu kadari kat izinde degilse bina disi
FREE_RAY_M = 30.0
ID_PREFIX = "p-"


def _seg_info(seg):
    (x1, y1), (x2, y2) = seg
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 1e-9:
        return None
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    if ux < -1e-12 or (abs(ux) <= 1e-12 and uy < 0):      # yon kanonik (mod 180)
        ux, uy = -ux, -uy
    return {"len": length, "u": (ux, uy), "n": (-uy, ux),
            "mid": ((x1 + x2) / 2.0, (y1 + y2) / 2.0)}


def _compatible(a, b):
    if abs(a["len"] - b["len"]) > LEN_TOL_M:
        return False
    cross = a["u"][0] * b["u"][1] - a["u"][1] * b["u"][0]
    if abs(cross) > math.sin(math.radians(PARALLEL_DEG)):
        return False
    dx, dy = b["mid"][0] - a["mid"][0], b["mid"][1] - a["mid"][1]
    return abs(dx * a["u"][0] + dy * a["u"][1]) <= ALIGN_TOL_M


def _components(items):
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _compatible(items[i], items[j]):
                parent[find(i)] = find(j)
    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return list(groups.values())


def _runs(lines):
    """Esit aralikli ardisik cizgi dizileri (en az MIN_LINES)."""
    ref = lines[0]
    nx, ny = ref["n"]
    ox, oy = ref["mid"]
    ordered = sorted(lines, key=lambda it: (it["mid"][0] - ox) * nx + (it["mid"][1] - oy) * ny)
    ts = [(it["mid"][0] - ox) * nx + (it["mid"][1] - oy) * ny for it in ordered]
    uniq, uts = [], []
    for it, t in zip(ordered, ts):                       # ust uste cizgiler tek
        if uts and t - uts[-1] < DUP_M:
            continue
        uniq.append(it)
        uts.append(t)
    runs, i = [], 0
    while i < len(uniq) - 1:
        gap = uts[i + 1] - uts[i]
        if not (DEPTH_MIN_M <= gap <= DEPTH_MAX_M):
            i += 1
            continue
        j = i + 1
        while j + 1 < len(uniq) and abs((uts[j + 1] - uts[j]) - gap) <= GAP_TOL_M:
            j += 1
        if j - i + 1 >= MIN_LINES:
            runs.append((uniq[i:j + 1], uts[i:j + 1]))
            i = j
        else:
            i += 1
    return runs


def find_strips(segments):
    """[{"start", "end" (kos ekseni, ilk/son cizginin ortasi), "width_m",
    "depth_m", "treads"}] - DXF ya da tarama cercevesinde, metre."""
    items = [it for it in (_seg_info(s) for s in segments)
             if it and WIDTH_MIN_M <= it["len"] <= WIDTH_MAX_M]
    out = []
    for comp in _components(items):
        if len(comp) < MIN_LINES:
            continue
        for lines, ts in _runs(comp):
            gaps = [b - a for a, b in zip(ts, ts[1:])]
            out.append({"start": tuple(lines[0]["mid"]), "end": tuple(lines[-1]["mid"]),
                        "width_m": sum(it["len"] for it in lines) / len(lines),
                        "depth_m": sum(gaps) / len(gaps), "treads": len(lines) - 1})
    out.sort(key=lambda s: (round(s["start"][0], 3), round(s["start"][1], 3)))
    return out


def orient(strip, points, floor_z, top_z):
    """Kopya dondurur: `direction_status` + gerekirse start/end yer degisir.
    `points` LAZ (N,3) ya da None; z'ler LAZ cercevesinde."""
    s = dict(strip)
    s["direction_status"] = "varsayildi"
    if points is None or len(points) == 0:
        return s
    import numpy as np

    (sx, sy), (ex, ey) = s["start"], s["end"]
    length = math.hypot(ex - sx, ey - sy)
    if length <= 1e-9:
        return s
    ux, uy = (ex - sx) / length, (ey - sy) / length
    nx, ny = -uy, ux
    half = s["width_m"] / 2.0 * 0.8
    lo_x, hi_x = min(sx, ex) - s["width_m"], max(sx, ex) + s["width_m"]
    lo_y, hi_y = min(sy, ey) - s["width_m"], max(sy, ey) + s["width_m"]
    p = points[(points[:, 0] >= lo_x) & (points[:, 0] <= hi_x)
               & (points[:, 1] >= lo_y) & (points[:, 1] <= hi_y)
               & (points[:, 2] >= floor_z - 0.1) & (points[:, 2] <= top_z + 0.3)]
    if len(p) == 0:
        return s
    dx, dy = p[:, 0].astype(np.float64) - sx, p[:, 1].astype(np.float64) - sy
    t = dx * ux + dy * uy
    lat = dx * nx + dy * ny
    keep = (t >= 0) & (t <= length) & (np.abs(lat) <= half)
    t, z = t[keep], p[keep, 2].astype(np.float64)
    depth = length / s["treads"]
    idx, med = [], []
    for i in range(s["treads"]):
        m = (t >= i * depth) & (t < (i + 1) * depth)
        if int(m.sum()) >= MIN_POINTS_PER_TREAD:
            idx.append(i)
            med.append(float(np.median(z[m])))
    if len(idx) < MIN_MEASURED_TREADS:
        return s
    slope = float(np.polyfit(np.asarray(idx, float), np.asarray(med, float), 1)[0])
    if abs(slope) * s["treads"] < MIN_RISE_M:
        return s
    if slope < 0:
        s["start"], s["end"] = s["end"], s["start"]
    s["direction_status"] = "olculdu"
    s["rise_m"] = round(abs(slope) * (s["treads"] + 1), 3)     # olculen toplam yukselme
    return s


def free_space(strip, footprint):
    """Kat izi (shapely, metre) icinde: ust uctan ileri ve alt uctan geri
    bos mesafe, seridin (genislikte dikdortgen) kat izinde kalan orani."""
    from shapely.geometry import LineString, Point, Polygon

    (sx, sy), (ex, ey) = strip["start"], strip["end"]
    length = math.hypot(ex - sx, ey - sy)
    if length <= 1e-9 or footprint is None or footprint.is_empty:
        return {"fwd_free_m": 0.0, "back_free_m": 0.0, "inside_frac": 0.0}
    ux, uy = (ex - sx) / length, (ey - sy) / length
    hw = strip["width_m"] / 2.0
    nx, ny = -uy * hw, ux * hw
    rect = Polygon([(sx + nx, sy + ny), (ex + nx, ey + ny), (ex - nx, ey - ny), (sx - nx, sy - ny)])
    frac = rect.intersection(footprint).area / rect.area if rect.area > 0 else 0.0

    def ray(px, py, dx, dy):
        if not footprint.covers(Point(px, py)):
            return 0.0
        seg = LineString([(px, py), (px + dx * FREE_RAY_M, py + dy * FREE_RAY_M)])
        part = seg.intersection(footprint)
        parts = [part] if part.geom_type == "LineString" else list(getattr(part, "geoms", []))
        best = 0.0
        for g in parts:
            if g.geom_type == "LineString" and g.distance(Point(px, py)) < 1e-6:
                best = max(best, g.length)
        return best

    return {"fwd_free_m": ray(ex, ey, ux, uy), "back_free_m": ray(sx, sy, -ux, -uy),
            "inside_frac": frac}


def records(strips_by_floor, levels, warnings=None, footprints=None):
    """JSON kayitlari: ustunde kat olan HER merdiven alt kattan ust kata
    (kullanici: yarida kesilmesin). Riht sayisi ve kol uzunlugu Revit
    tarafinda secilen tipin sinirlarindan hesaplanir
    (`lib/pykalfa/rolove/stairs_calc.plan_run`); burada taranan basamak
    derinligi, genislik, baslangic ve cikis yonu tasinir. Ustunde kat
    olmayan merdiven `warnings`'e yazilir. `footprints` ({kat: shapely,
    metre}) verilirse: seridin cogu kat izinin disindaysa (ör. giris
    basamaklari) kurulmaz; kol uzatmasi icin ust uctan ileri / alt uctan
    geri bos mesafe kayda yazilir (`fwd_free_ft`, `back_free_ft`)."""
    import prototype
    tops = prototype.top_floors(levels)
    elev = {lv["floor"]: float(lv["elevation_m"]) for lv in levels}
    ft = config.FT
    out = []
    for f in sorted(strips_by_floor):
        top = tops.get(f)
        k = 0
        for s in strips_by_floor[f]:
            if top is None:
                if warnings is not None:
                    warnings.append("Kat {}: {} basamakli merdiven ustte kat olmadigi icin "
                                    "kurulmadi".format(f, s["treads"]))
                continue
            storey = elev.get(top, 0.0) - elev.get(f, 0.0)
            fp = (footprints or {}).get(f)
            space = free_space(s, fp) if fp is not None else None
            if space is not None and space["inside_frac"] < MIN_INSIDE_FRAC:
                if warnings is not None:
                    warnings.append(
                        "Kat {}: {} basamakli merdiven bina izinin disina tasiyor (%{:.0f} icerde; "
                        "giris/dis basamak olabilir), kurulmadi".format(
                            f, s["treads"], space["inside_frac"] * 100))
                continue
            k += 1
            out.append({
                "id": "{}stairs-{}-{}".format(ID_PREFIX, f, k - 1), "floor": f, "top_floor": top,
                "height_m": round(storey, 3), "height_ft": storey * ft,
                "start_ft": [s["start"][0] * ft, s["start"][1] * ft],
                "end_ft": [s["end"][0] * ft, s["end"][1] * ft],
                "width_ft": s["width_m"] * ft, "width_m": round(s["width_m"], 3),
                "depth_ft": s["depth_m"] * ft, "depth_m": round(s["depth_m"], 3),
                "treads": int(s["treads"]),
                "fwd_free_ft": None if space is None else space["fwd_free_m"] * ft,
                "back_free_ft": None if space is None else space["back_free_m"] * ft,
                "direction_status": s.get("direction_status", "varsayildi")})
    return out


# --------------------------------------------------------------------------
# Hazirlik: DXF + hizalama + LAZ -> doc["stairs"]
# --------------------------------------------------------------------------

def _fixture_segments(dxf_path):
    """{kat: [((x1,y1),(x2,y2)), ...]} metre, DXF cercevesi."""
    import re
    from dxf_reader import meters_per_unit, read_dxf

    layer_re = re.compile(r"^Polycam-Floor_(\d+)-Objects-Fixtures$")
    res = read_dxf(dxf_path)
    scale = 1.0
    if res.insunits != 6:
        scale = meters_per_unit(res.insunits) or 1.0
    out = {}
    for poly in res.polys:
        m = layer_re.match(poly.layer or "")
        if not m or len(poly.points) != 2:
            continue
        (x1, y1), (x2, y2) = [(float(p[0]) * scale, float(p[1]) * scale) for p in poly.points]
        out.setdefault(int(m.group(1)), []).append(((x1, y1), (x2, y2)))
    return out


def find_stairs(doc, dxf_path, points=None):
    """Hizalanmis her katin merdivenleri -> `records`. Hata olursa bos liste
    + uyari (merdiven istege bagli, hazirligi durdurmaz)."""
    import align
    import prototype

    try:
        segs = _fixture_segments(dxf_path)
    except Exception as ex:  # noqa: BLE001
        doc.setdefault("warnings", []).append("Merdivenler okunamadi: {}".format(ex))
        return []
    tops = prototype.top_floors(doc.get("levels") or [])
    elev = {lv["floor"]: float(lv["elevation_m"]) for lv in doc.get("levels") or []}
    offset = float((doc.get("z_datum") or {}).get("offset_m") or 0.0)
    by_floor = {}
    for a in doc.get("alignment") or []:
        f = a["floor"]
        if not a.get("ok") or f not in segs:
            continue
        tr = align.Transform2D(float(a["rot_deg"]), bool(a["mirror"]), float(a["tx_m"]), float(a["ty_m"]))
        strips = []
        for s in find_strips(segs[f]):
            s = dict(s)
            s["start"] = tuple(float(v) for v in tr.apply(s["start"]))
            s["end"] = tuple(float(v) for v in tr.apply(s["end"]))
            floor_z = elev.get(f, 0.0) - offset
            top = tops.get(f)
            top_z = (elev[top] - offset) if top in elev else floor_z + 3.5
            strips.append(orient(s, points, floor_z, top_z))
        if strips:
            by_floor[f] = strips
    from shapely import affinity
    footprints = {}
    for f in by_floor:
        try:
            footprints[f] = affinity.scale(prototype.footprint(doc, f, 0.0), 1.0 / config.FT,
                                           1.0 / config.FT, origin=(0, 0))
        except Exception:  # noqa: BLE001 - iz yoksa yerlesim kontrolu yapilmaz
            pass
    return records(by_floor, doc.get("levels") or [], doc.setdefault("warnings", []), footprints)
