"""
pyKalfa / Rolove - modul bazli oz-test (Revit gerekmez)

Sentetik Polycam ciktilari (DXF/CSV/GLB/LAZ) uretip `pysrc/rolove`
zincirini parca parca dogrular. Gercek bir tarama veya Revit olmadan
"hala calisiyor mu?" sorusunu cevaplar.

Kullanim:
    C:\\pyKalfa\\env\\Scripts\\python.exe pysrc\\rolove\\selftest.py
    ... selftest.py --only dxf,csv
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
for extra in (HERE, HERE.parent / "duvar"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import fixtures  # noqa: E402

TESTS = []


def test(group):
    def deco(fn):
        TESTS.append((group, fn))
        return fn
    return deco


def check(condition, detail=""):
    if not condition:
        raise AssertionError(detail)


def approx(value, expected, tol):
    return value is not None and abs(value - expected) <= tol


def raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    return False


def seg_len(seg):
    (x1, y1), (x2, y2) = seg
    return math.hypot(x2 - x1, y2 - y1)


# --------------------------------------------------------------------------
# dxf
# --------------------------------------------------------------------------

def _two_floor_dxf(path):
    fixtures.write_polycam_dxf(path, {
        2: {"walls": [((0, 0), (5, 0), 0.10), ((5, 0), (5, 4), 0.10)],
            "doors": [((2.5, 0), 0.90, (1, 0))], "windows": [], "openings": [],
            "rooms": [("Living Room 1", [(0, 0), (5, 0), (5, 4), (0, 4)])]},
        3: {"walls": [((0, 0), (3, 0), 0.10)], "doors": [],
            "windows": [((1.5, 0), 1.20, (1, 0))], "openings": [], "rooms": []},
    })


@test("dxf")
def test_dxf_layers_by_floor(tmp):
    import polycam_dxf
    _two_floor_dxf(tmp / "p.dxf")
    fp = polycam_dxf.read_floorplan(tmp / "p.dxf")
    check(sorted(fp.floors) == [2, 3], sorted(fp.floors))
    check(len(fp.floors[2].walls) == 2, len(fp.floors[2].walls))
    w = min(fp.floors[2].walls, key=lambda w: w.center[0][1] + w.center[1][1])
    check(approx(w.thickness, 0.10, 0.002), w.thickness)
    check(approx(seg_len(w.center), 5.0, 0.11), seg_len(w.center))
    d = fp.floors[2].openings[0]
    check(d.kind == "door" and approx(d.width, 0.90, 0.005)
          and approx(d.center[0], 2.5, 0.01), d)
    check(fp.floors[3].openings[0].kind == "window", fp.floors[3].openings)
    check(fp.floors[2].rooms and fp.floors[2].rooms[0].name == "Living Room 1",
          fp.floors[2].rooms)


@test("dxf")
def test_dxf_faces_offset_by_half_thickness(tmp):
    import polycam_dxf
    _two_floor_dxf(tmp / "p.dxf")
    fp = polycam_dxf.read_floorplan(tmp / "p.dxf")
    w = fp.floors[3].walls[0]
    a, b = w.faces()
    ys = sorted([a[0][1], b[0][1]])
    check(approx(ys[0], -0.05, 0.002) and approx(ys[1], 0.05, 0.002), (a, b))


@test("dxf")
def test_dxf_ignores_non_semantic_layers(tmp):
    import polycam_dxf
    fixtures.write_polycam_dxf(tmp / "p.dxf", {
        2: {"walls": [], "doors": [], "windows": [], "openings": [], "rooms": [],
            "junk": True},
    })
    fp = polycam_dxf.read_floorplan(tmp / "p.dxf")
    layers = fp.floors.get(2)
    check(layers is None or (not layers.walls and not layers.openings and not layers.rooms),
          layers)


# --------------------------------------------------------------------------
# csv
# --------------------------------------------------------------------------

@test("csv")
def test_csv_parses_rooms(tmp):
    import polycam_csv
    fixtures.write_polycam_csv(tmp / "r.csv", [
        ("Floor 2", "Entire Floor", "Total livable floor area [m^2]", "89.4"),
        ("Floor 2", "Living Room 1", "Ceiling height [m]", "2.5 "),
        ("Floor 4", "Bedroom 2", "Ceiling height [m]", "0.7 - 2.4 "),
        ("Floor 3", "Other 2", "Ceiling height [m] (approx)", "1.9 - 2.3 "),
        ("Floor 2", "Living Room 1", "Door dimensions [m]", "0.8 x 2.1"),
        ("Floor 2", "Living Room 1", "Window dimensions [m]", "2.6 x 0.9"),
        ("Floor 2", "Living Room 1", "Floor area [m^2]", "35.2"),
        ("Floor 2", "Living Room 1", "Sofa double dimensions (w x h x d) [m]", "3.6 x 0.8 x 1.1"),
        ("All", "Settings", "Wall thickness [m] (total wall length: 158.878)", "0.100"),
    ])
    r = polycam_csv.read_report(tmp / "r.csv")
    lr = r.rooms[(2, "Living Room 1")]
    check(lr.ceiling_min == lr.ceiling_max == 2.5, lr)
    check(lr.doors == [(0.8, 2.1)] and lr.windows == [(2.6, 0.9)], lr)
    check(lr.area == 35.2, lr.area)
    b = r.rooms[(4, "Bedroom 2")]
    check((b.ceiling_min, b.ceiling_max) == (0.7, 2.4), b)
    check((r.rooms[(3, "Other 2")].ceiling_min, r.rooms[(3, "Other 2")].ceiling_max) == (1.9, 2.3))
    check(r.livable_area_by_floor == {2: 89.4}, r.livable_area_by_floor)
    check(r.wall_thickness_setting == 0.100, r.wall_thickness_setting)


# --------------------------------------------------------------------------
# cloud (GLB kat bantlari, LAZ, kat kotlari)
# --------------------------------------------------------------------------

@test("cloud")
def test_story_bands_axis_swap(tmp):
    import numpy as np
    import glb_stories
    # glTF (x, y, z) -> LAZ (x, -z, y)
    verts = np.array([[-1, -8.8, -4], [2, -6.8, 5], [0, -7, 0]], dtype=np.float32)
    fixtures.write_story_glb(tmp / "s.glb", [("Story 0", verts, np.array([[0, 1, 2]]))])
    b = glb_stories.read_story_bands(tmp / "s.glb")[0]
    check(b.index == 0 and b.name == "Story 0", b)
    check(approx(b.zmin, -8.8, 1e-5) and approx(b.zmax, -6.8, 1e-5), b)
    check(approx(b.ymin, -5, 1e-5) and approx(b.ymax, 4, 1e-5), b)
    check(approx(b.xmin, -1, 1e-5) and approx(b.xmax, 2, 1e-5), b)


@test("cloud")
def test_load_laz_reads_points(tmp):
    import numpy as np
    import cloud
    pts = np.array([[1.0, 2.0, 3.0], [-4.5, 0.25, -8.8]] * 50)
    fixtures.write_laz(tmp / "p.laz", pts)
    got = cloud.load_laz(tmp / "p.laz")
    check(got.shape == (100, 3) and got.dtype == np.float32, (got.shape, got.dtype))
    check(np.allclose(got[:2], pts[:2], atol=1e-4), got[:2])


@test("cloud")
def test_load_laz_rejects_georef(tmp):
    import numpy as np
    import cloud
    pts = np.array([[5.406, 51.028, 70.0], [5.4061, 51.0281, 71.0]] * 50)
    fixtures.write_laz(tmp / "g.laz", pts, georef=True)
    check(raises(cloud.GeorefError, cloud.load_laz, tmp / "g.laz"))


@test("cloud")
def test_levels_ignore_table_and_step(tmp):
    import glb_stories
    import levels
    s = fixtures.synthetic_building(tmp, write_files=True)
    bands = glb_stories.read_story_bands(s["paths"]["glb"])
    tris = glb_stories.read_story_triangles(s["paths"]["glb"])
    lv = levels.measure_levels(tris, bands, [1, 2])
    check([m.floor for m in lv] == [1, 2] and [m.story for m in lv] == [0, 1], lv)
    check(approx(lv[0].floor_z, 0.00, 0.02) and approx(lv[1].floor_z, 2.80, 0.02),
          [m.floor_z for m in lv])
    check(approx(lv[0].ceiling_z, 2.50, 0.03) and approx(lv[1].ceiling_z, 5.30, 0.03),
          [m.ceiling_z for m in lv])
    check(0.0 < lv[0].confidence <= 1.0, lv[0].confidence)


@test("cloud")
def test_levels_floor_count_mismatch(tmp):
    import glb_stories
    import levels
    s = fixtures.synthetic_building(tmp, write_files=True)
    bands = glb_stories.read_story_bands(s["paths"]["glb"])
    tris = glb_stories.read_story_triangles(s["paths"]["glb"])
    check(raises(ValueError, levels.measure_levels, tris, bands, [1, 2, 3]))


# --------------------------------------------------------------------------
# align
# --------------------------------------------------------------------------

@test("align")
def test_align_recovers_rot_and_shift(tmp):
    import align
    faces, pts = fixtures.floor_faces_and_slice(rot_deg=90, mirror=False, shift=(10.3, -1.4),
                                                noise=0.005)
    a = align.align_floor(2, faces, pts)
    check(a.ok, a)
    check(round(a.transform.rot_deg) % 360 == 90 and not a.transform.mirror, a.transform)
    check(approx(a.transform.tx, 10.3, 0.01) and approx(a.transform.ty, -1.4, 0.01), a.transform)
    check(a.rms_m < 0.01, a.rms_m)


@test("align")
def test_align_detects_mirror(tmp):
    import align
    faces, pts = fixtures.floor_faces_and_slice(rot_deg=0, mirror=True, shift=(0, 0), noise=0.005)
    a = align.align_floor(2, faces, pts)
    check(a.ok and a.transform.mirror, a)


@test("align")
def test_align_small_rotation_refined(tmp):
    import align
    faces, pts = fixtures.floor_faces_and_slice(rot_deg=181.5, mirror=False, shift=(-3, 2),
                                                noise=0.005)
    a = align.align_floor(2, faces, pts)
    check(a.ok and approx(a.transform.rot_deg % 360, 181.5, 0.1), a.transform)


@test("align")
def test_align_ok_with_deduped_slice_and_clutter(tmp):
    # Gercek veride dilim 5 cm hucrelere tekillesir (duvar boyunca ~1 nokta /
    # 5 cm) ve duvar dibinde mobilya olur; dogru hizalama yine ok olmali.
    import numpy as np
    import align
    faces, pts = fixtures.floor_faces_and_slice(rot_deg=0, mirror=False, shift=(3, 1),
                                                noise=0.004)
    rng = np.random.default_rng(2)
    clutter = np.column_stack([rng.uniform(4, 7.5, 600), rng.uniform(1.10, 1.25, 600)])
    pts = np.vstack([pts, clutter])
    z = np.full((len(pts), 1), 1.3)
    sl = align.slice_xy(np.hstack([pts, z]).astype(np.float32), 0.0)
    a = align.align_floor(2, faces, sl)
    check(a.ok, a)
    check(approx(a.transform.tx, 3, 0.01) and approx(a.transform.ty, 1, 0.01), a.transform)


@test("align")
def test_support_counts_one_point_per_cell(tmp):
    import numpy as np
    import align
    import polycam_dxf
    wall = [polycam_dxf.DxfWall(2, ((0.0, 0.0), (2.0, 0.0)), 0.10)]
    pts = np.column_stack([np.arange(0, 2.0, 0.05) + 0.025, np.full(40, 0.06)])
    rms, support, _i = align._quality(wall, pts, align.Transform2D(0, False, 0, 0))
    check(support > 0.9 and rms < 0.02, (rms, support))


@test("align")
def test_support_one_visible_face_is_enough(tmp):
    # Dis duvarin dis yuzu iceriden gorunmez: tek yuzu taranmis duvar destekli.
    import numpy as np
    import align
    import polycam_dxf
    wall = [polycam_dxf.DxfWall(2, ((0.0, 0.0), (2.0, 0.0)), 0.10)]
    pts = np.column_stack([np.arange(0, 2.0, 0.05), np.full(40, -0.08)])  # 3 cm iceride
    _rms, support, _i = align._quality(wall, pts, align.Transform2D(0, False, 0, 0))
    check(support > 0.9, support)


@test("align")
def test_align_prefer_resolves_symmetric_floor(tmp):
    # Dikdortgen kat 0/180 derece ve aynaya gore simetrik; Polycam paftasinda
    # butun katlar ayni yonde oldugundan diger katlarin yonu tercih edilir.
    import numpy as np
    import align
    import polycam_dxf
    rect = [((0, 0), (4, 0)), ((4, 0), (4, 2.5)), ((4, 2.5), (0, 2.5)), ((0, 2.5), (0, 0))]
    walls = [polycam_dxf.DxfWall(1, s, 0.10) for s in rect]
    faces = [f for w in walls for f in w.faces()]
    pts = np.vstack([np.linspace(a, b, 200) for a, b in faces]) + np.array([5.0, -2.0])
    a = align.align_floor(1, walls, pts, prefer=(0, False))
    check(a.ok and round(a.transform.rot_deg) % 360 == 0 and not a.transform.mirror, a)
    check(approx(a.transform.tx, 5.0, 0.01) and approx(a.transform.ty, -2.0, 0.01), a)


@test("align")
def test_align_auto_uses_low_slice_for_knee_walls(tmp):
    # Cati kati: duvarlar yalniz 0.8 m (diz duvari); 1.0-1.6 m'de egik cati
    # yuzeyi duvarlardan 0.6 m iceride. Alcak dilim secilmeli.
    import numpy as np
    import align
    walls, xy = fixtures.floor_faces_and_slice(rot_deg=0, mirror=False, shift=(2, 3),
                                               noise=0.004)
    low = np.column_stack([np.repeat(xy, 4, axis=0),
                           np.tile([0.2, 0.45, 0.55, 0.75], len(xy))])
    xs = np.arange(0.0, 8.0, 0.02)
    roof_xy = np.vstack([np.column_stack([xs, np.full_like(xs, 1.2)]),
                         np.column_stack([xs, np.full_like(xs, 4.8)])]) + np.array([2.0, 3.0])
    high = np.column_stack([np.repeat(roof_xy, 3, axis=0),
                            np.tile([1.1, 1.3, 1.5], len(roof_xy))])
    pts = np.vstack([low, high]).astype(np.float32)
    a = align.align_floor_auto(4, walls, pts, 0.0, prefer=(0, False))
    check(a.ok and tuple(a.slice_band) == (0.4, 0.65), a)
    check(approx(a.transform.tx, 2, 0.01) and approx(a.transform.ty, 3, 0.01), a.transform)


@test("align")
def test_align_rejects_unrelated_cloud(tmp):
    import numpy as np
    import align
    faces, _ = fixtures.floor_faces_and_slice(rot_deg=0, mirror=False, shift=(0, 0), noise=0)
    a = align.align_floor(2, faces, np.random.default_rng(1).uniform(-5, 5, (5000, 2)))
    check(not a.ok and a.reason, a)


@test("align")
def test_transform_apply_roundtrip(tmp):
    import numpy as np
    import align
    t = align.Transform2D(rot_deg=90, mirror=True, tx=1.0, ty=2.0)
    got = t.apply(np.array([[1.0, 0.0], [0.0, 1.0]]))
    # ayna (x, -y) -> 90 derece (-y', x') -> oteleme
    check(np.allclose(got, [[1.0, 3.0], [2.0, 2.0]]), got)
    check(np.allclose(t.apply((1.0, 0.0)), (1.0, 3.0)), t.apply((1.0, 0.0)))
    check(np.allclose(t.apply_dir((0.0, 1.0)), (1.0, 0.0)), t.apply_dir((0.0, 1.0)))


@test("align")
def test_slice_xy_band_and_dedupe(tmp):
    import numpy as np
    import align
    pts = np.array([[0.01, 0.01, 1.2], [0.02, 0.02, 1.3], [5, 5, 0.2], [1, 1, 2.0]],
                   dtype=np.float32)
    sl = align.slice_xy(pts, 0.0)
    check(sl.shape == (1, 2), sl)


# --------------------------------------------------------------------------
# refine
# --------------------------------------------------------------------------
# Sentetik binada duvar sirasi fixtures.SYN_WALLS ile ayni:
#   0 alt dis (dogru), 1 sag dis (ic yuz 3 cm kayik), 2 ust dis (dogru),
#   3 sol dis (ic yuz 25 cm kayik), 4 ic duvar (DXF 0.10 / 3.04; gercek 0.20 / 3.00)

_REFINED = {}


def _refined(tmp, floor):
    if floor not in _REFINED:
        import polycam_csv
        import polycam_dxf
        import levels
        import refine
        from align import Transform2D
        s = fixtures.synthetic_building(tmp)
        ox, oy = s["dxf_offset"]
        walls = [polycam_dxf.DxfWall(floor, ((x1 + ox, y1 + oy), (x2 + ox, y2 + oy)), t)
                 for (x1, y1), (x2, y2), t in fixtures.SYN_WALLS]
        rooms = [polycam_dxf.DxfRoom(floor, n, poly) for n, poly in s["rooms_scan"][floor]]
        fz, cz = s["floors"][floor]
        level = levels.LevelMeasure(floor, floor - 1, fz, cz, 1.0)
        report = [polycam_csv.RoomReport(2, "Bedroom 2", 0.7, 2.4),
                  polycam_csv.RoomReport(2, "Room B2", 2.5, 2.5)]
        report = [r for r in report if r.floor == floor]
        tf = Transform2D(0.0, False, -ox, -oy)
        _REFINED[floor] = refine.refine_floor(walls, rooms, tf, s["points"], level, report)
    return _REFINED[floor]


def _room_side_ok(w, rooms):
    import geom2d
    (x1, y1), (x2, y2) = w.line
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    inside = (mx - w.outward[0] * 0.2, my - w.outward[1] * 0.2)
    outside = (mx + w.outward[0] * 0.2, my + w.outward[1] * 0.2)
    in_room = any(geom2d.point_in_polygon(inside, p) for _, p in rooms)
    out_room = any(geom2d.point_in_polygon(outside, p) for _, p in rooms)
    return in_room and not out_room


def _rw(line, side="interior"):
    import refine
    return refine.RefinedWall(
        floor=2, dxf_center=line, side=side, location="center", line=line, outward=None,
        thickness_dxf=0.10, measured_thickness=None, thickness_group_m=None, height=2.5,
        height_status="olculdu", status="duzeltildi", deviation_cm=0.0, support=0,
        warnings=[])


@test("refine")
def test_interior_wall_measured(tmp):
    w = _refined(tmp, 1)[4]
    check(w.side == "interior" and w.status == "olculdu", (w.side, w.status, w.warnings))
    check(w.location == "center" and w.outward is None, (w.location, w.outward))
    check(approx(w.measured_thickness, 0.20, 0.01) and w.thickness_group_m == 0.20,
          (w.measured_thickness, w.thickness_group_m))
    check(approx(w.deviation_cm, 4.0, 1.0), w.deviation_cm)
    check(approx(w.line[0][0], 3.00, 0.01) and approx(w.line[1][0], 3.00, 0.01), w.line)


@test("refine")
def test_exterior_wall_face_corrected(tmp):
    w = _refined(tmp, 1)[1]
    check(w.side == "exterior" and w.location == "interior_face", (w.side, w.location))
    check(w.status == "duzeltildi" and w.outward is not None, (w.status, w.warnings))
    check(w.measured_thickness is None, w.measured_thickness)
    check(approx(w.line[0][0], 6.00, 0.01) and approx(w.line[1][0], 6.00, 0.01), w.line)
    check(approx(w.deviation_cm, 3.0, 1.0), w.deviation_cm)
    check(_room_side_ok(w, fixtures.SYN_ROOMS[1]), (w.line, w.outward))


@test("refine")
def test_correct_exterior_walls_unchanged(tmp):
    ws = _refined(tmp, 1)
    for i, y in ((0, 0.0), (2, 4.0)):
        w = ws[i]
        check(w.side == "exterior" and w.status == "duzeltildi", (i, w.side, w.status))
        check(approx(w.line[0][1], y, 0.01) and approx(w.line[1][1], y, 0.01), (i, w.line))
        check(w.deviation_cm < 1.0, (i, w.deviation_cm))
        check(_room_side_ok(w, fixtures.SYN_ROOMS[1]), (i, w.outward))


@test("refine")
def test_large_shift_not_applied(tmp):
    w = _refined(tmp, 1)[3]
    check(w.side == "exterior" and w.status == "varsayildi" and w.warnings,
          (w.side, w.status, w.warnings))
    check(approx(w.line[0][0], -0.25, 0.005), w.line)       # DXF ic yuzu korunur
    check(w.outward is not None and w.outward[0] < -0.99, w.outward)   # disari = -x
    # Sapma, uygulanmasa da taramanin gosterdigi kaymadir (0 degil).
    check(approx(w.deviation_cm, 25.0, 1.0), w.deviation_cm)


@test("refine")
def test_heights(tmp):
    w1 = _refined(tmp, 1)[4]
    check(w1.height == 2.50 and w1.height_status == "olculdu", (w1.height, w1.height_status))
    w2 = _refined(tmp, 2)[4]                                 # Bedroom 2 | Room B2
    check(w2.height == 2.40 and w2.height_status == "varsayildi",
          (w2.height, w2.height_status))


@test("refine")
def test_join_corners_closes_gap(tmp):
    import refine
    a = _rw(((0.0, 0.0), (5.0, 0.0)))
    b = _rw(((5.0, 0.08), (5.0, 4.0)))
    n = refine.join_corners([a, b], 0.15)
    check(n == 2, n)
    check(seg_len((a.line[1], b.line[0])) < 1e-6 and seg_len((a.line[1], (5.0, 0.0))) < 1e-6,
          (a.line, b.line))


@test("refine")
def test_join_corners_t_junction_and_far(tmp):
    import refine
    a = _rw(((0.0, 0.0), (6.0, 0.0)))
    b = _rw(((3.0, 0.10), (3.0, 4.0)))                       # T: a'nin ortasina 10 cm
    c = _rw(((10.0, 0.0), (12.0, 0.0)))                      # uzak: dokunulmaz
    n = refine.join_corners([a, b, c], 0.15)
    check(n == 1, n)
    check(seg_len((b.line[0], (3.0, 0.0))) < 1e-6, b.line)
    check(a.line == ((0.0, 0.0), (6.0, 0.0)) and c.line == ((10.0, 0.0), (12.0, 0.0)),
          (a.line, c.line))


# --------------------------------------------------------------------------
# openings
# --------------------------------------------------------------------------
# Tek dis duvar: DXF ekseni y=-0.05 (x 0..6, t 0.10) -> taramada ic yuzu y=0.02
# (7 cm duzeltilmis); oda y>0 tarafinda. DXF->tarama donusumu: +10/+5 oteleme.

_OP_TF = (0.0, False, -10.0, -5.0)
L_SHAPE = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]


def _op_wall(height=2.50):
    w = _rw(((0.0, 0.02), (6.0, 0.02)), side="exterior")
    w.dxf_center = ((10.0, 4.95), (16.0, 4.95))
    w.location, w.outward, w.height = "interior_face", (0.0, -1.0), height
    return w


def _op(kind, width, center=(13.0, 4.95)):
    import polycam_dxf
    return polycam_dxf.DxfOpening(2, kind, center, width, (1.0, 0.0))


def _place(ops, csv_doors=(), csv_windows=(), wall_height=2.50):
    import openings
    import polycam_csv
    import polycam_dxf
    from align import Transform2D
    rooms = [polycam_dxf.DxfRoom(2, "Room", [(0, 0), (6, 0), (6, 4), (0, 4)])]
    report = [polycam_csv.RoomReport(2, "Room", doors=list(csv_doors),
                                     windows=list(csv_windows))]
    return openings.place_openings(ops, [_op_wall(wall_height)], Transform2D(*_OP_TF),
                                   rooms, report)


@test("openings")
def test_door_height_from_csv(tmp):
    out, rejected = _place([_op("door", 0.80)], csv_doors=[(0.8, 2.1), (2.9, 2.4)])
    o = out[0]
    check(rejected == [] and o.host == 0, rejected)
    check(o.height == 2.10 and o.status["height"] == "olculdu" and o.status["width"] == "olculdu",
          (o.height, o.status))
    check(o.width == 0.80 and o.sill == 0.0 and o.status["sill"] == "olculdu", (o.width, o.sill))
    check(approx(o.offset, 3.0, 1e-6), o.offset)


@test("openings")
def test_window_ambiguous_csv_defaults(tmp):
    out, _ = _place([_op("window", 1.50)], csv_windows=[(1.5, 1.5), (1.45, 1.3)])
    o = out[0]
    check(o.height == 1.20 and o.status["height"] == "varsayildi", (o.height, o.status))
    check(o.sill == 0.90 and o.status["sill"] == "varsayildi", (o.sill, o.status))


@test("openings")
def test_identical_csv_records_not_ambiguous(tmp):
    out, _ = _place([_op("door", 0.83)], csv_doors=[(0.8, 2.0), (0.8, 2.0)])
    check(out[0].height == 2.00 and out[0].status["height"] == "olculdu", out[0])
    check(out[0].width == 0.85, out[0].width)                 # round_dim(0.83)


@test("openings")
def test_opening_without_host_rejected(tmp):
    out, rejected = _place([_op("door", 0.9, center=(50.0, 50.0))])
    check(out == [] and len(rejected) == 1 and rejected[0]["reason"], rejected)
    check(rejected[0]["kind"] == "door" and rejected[0]["floor"] == 2, rejected)


@test("openings")
def test_opening_wider_than_host_rejected(tmp):
    out, rejected = _place([_op("opening", 7.0)])
    check(out == [] and "genis" in rejected[0]["reason"], rejected)


@test("openings")
def test_opening_height_clipped_to_wall(tmp):
    out, _ = _place([_op("door", 0.9)], csv_doors=[(0.9, 2.3)], wall_height=2.20)
    o = out[0]
    check(o.height == 2.20 and o.warnings, (o.height, o.warnings))


@test("openings")
def test_label_point_inside_concave(tmp):
    import geom2d
    import openings
    p = openings.label_point(L_SHAPE)
    check(geom2d.point_in_polygon(p, L_SHAPE), p)
    sq = [(0, 0), (2, 0), (2, 2), (0, 2)]
    check(geom2d.point_in_polygon(openings.label_point(sq), sq))


# --------------------------------------------------------------------------
# prepare (CLI uctan uca)
# --------------------------------------------------------------------------

def run_cli(args):
    import subprocess
    proc = subprocess.run([sys.executable, str(HERE / "prepare_rolove_input.py")] + list(args),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    run_cli.last = proc
    return proc.returncode


def _load_json(path):
    import json
    return json.loads(Path(path).read_text("utf-8"))


def _ids(j):
    return {k: sorted(x["id"] for x in j[k]) for k in ("levels", "walls", "openings", "rooms")}


@test("prepare")
def test_prepare_end_to_end_synthetic(tmp):
    s = fixtures.synthetic_building(tmp, write_files=True)
    code = run_cli(["--input", str(tmp / "p.dxf"), "--output-dir", str(tmp / "out")])
    check(code == 0, (code, run_cli.last.stderr[-800:]))
    check("PROGRESS|100|" in run_cli.last.stdout, run_cli.last.stdout[-300:])
    j = _load_json(tmp / "out" / "rolove_input.json")
    check(j["schema_version"] == 1 and len(j["levels"]) == 2, j.get("levels"))
    check(all(a["ok"] for a in j["alignment"]), j["alignment"])
    check(j["walls"] and j["openings"] and j["rooms"], j["stats"]["counts"])
    check(j["z_datum"]["floor"] == s["main_floor"], j["z_datum"])
    lv = {x["floor"]: x for x in j["levels"]}
    check(lv[2]["elevation_m"] == 0.0 and lv[1]["elevation_m"] == -2.80, lv)
    check(approx(lv[1]["elevation_ft"], -2.80 / 0.3048, 1e-6), lv[1])
    check(len({w["id"] for w in j["walls"]}) == len(j["walls"]) == 10, len(j["walls"]))
    ids = {w["id"] for w in j["walls"]}
    check(all(o["host_id"] in ids for o in j["openings"]), j["openings"])
    kinds = sorted(o["kind"] for o in j["openings"])
    check(kinds == ["door", "door", "window", "window"], kinds)
    inner = [w for w in j["walls"] if w["floor"] == 1 and w["side"] == "interior"]
    check(len(inner) == 1 and inner[0]["thickness_group_cm"] == 20, inner)
    check(any(g["cm"] == 20 for g in j["thickness_groups"]), j["thickness_groups"])
    check(j["missing"] == [] and all(Path(p).exists() for p in j["previews"]), j["previews"])
    check(set(j["source"]["files"]) == {"dxf", "csv", "laz", "glb"}, j["source"])


@test("prepare")
def test_stable_ids_repeatable(tmp):
    fixtures.synthetic_building(tmp, write_files=True)
    check(run_cli(["--input", str(tmp / "p.dxf"), "--output-dir", str(tmp / "o1")]) == 0)
    check(run_cli(["--input", str(tmp / "p.dxf"), "--output-dir", str(tmp / "o2")]) == 0)
    a, b = _load_json(tmp / "o1" / "rolove_input.json"), _load_json(tmp / "o2" / "rolove_input.json")
    check(_ids(a) == _ids(b), (_ids(a), _ids(b)))


@test("prepare")
def test_stable_id_uses_rounded_dxf_coords(tmp):
    import prepare_rolove_input as pri
    a = pri.stable_id("wall", 2, [(10.001, 5.0), (16.0, 5.0)])
    b = pri.stable_id("wall", 2, [(16.0, 5.0), (10.004, 5.0)])
    check(a == b and len(a) == 12, (a, b))
    check(a != pri.stable_id("wall", 3, [(10.0, 5.0), (16.0, 5.0)]))


@test("prepare")
def test_unmeasured_interior_walls_take_most_common_measured_group(tmp):
    import prepare_rolove_input as pri

    def iw(line, measured=None, status="olculdu", face_side=None):
        w = _rw(line)
        w.measured_thickness = measured
        w.thickness_group_m = None if measured is None else 0.15
        w.status, w.face_side = status, face_side
        return w

    measured = [iw(((0, y), (4, y)), 0.15) for y in (0.0, 1.0)]
    one_face = iw(((0, 5.0), (4, 5.0)), status="duzeltildi", face_side=1.0)  # yuz y=5.05
    unseen = iw(((0, 7.0), (4, 7.0)), status="varsayildi")
    ext = _rw(((0, 9.0), (4, 9.0)), side="exterior")
    ext.location = "interior_face"
    g = pri.assign_interior_groups([measured + [one_face, unseen, ext]])
    check(g == 0.15, g)
    check(one_face.thickness_group_m == 0.15 and unseen.thickness_group_m == 0.15,
          (one_face.thickness_group_m, unseen.thickness_group_m))
    # gorulen yuz (y = 5.0 + 0.10/2 = 5.05) yerinde kalir: yeni eksen 5.05 - 0.15/2
    check(approx(one_face.line[0][1], 4.975, 1e-9) and approx(one_face.line[1][1], 4.975, 1e-9),
          one_face.line)
    check(unseen.line == ((0, 7.0), (4, 7.0)), unseen.line)              # DXF ekseni kalir
    check(ext.thickness_group_m is None, ext.thickness_group_m)
    check(pri.assign_interior_groups([[one_face]]) is None)             # olculen yoksa dokunma


@test("prepare")
def test_prepare_missing_inputs(tmp):
    s = fixtures.synthetic_building(tmp, write_files=True)
    s["paths"]["glb"].unlink()
    code = run_cli(["--input", str(tmp / "p.dxf"), "--output-dir", str(tmp / "out")])
    check(code == 2, (code, run_cli.last.stderr[-500:]))
    j = _load_json(tmp / "out" / "rolove_input.json")
    check(len(j["missing"]) == 1 and j["missing"][0]["file"] == "glb", j["missing"])
    check(j["missing"][0]["polycam_export"], j["missing"])
    check(j["walls"] == [] and j["levels"] == [], j["stats"])


@test("prepare")
def test_prepare_skips_unaligned_floor(tmp):
    s = fixtures.synthetic_building(tmp, write_files=True)
    pts = s["points"][s["points"][:, 2] < 2.7]                # Kat 2 taranmamis
    fixtures.write_laz(s["paths"]["laz"], pts)
    code = run_cli(["--input", str(tmp / "p.dxf"), "--output-dir", str(tmp / "out")])
    check(code == 0, (code, run_cli.last.stderr[-800:]))
    j = _load_json(tmp / "out" / "rolove_input.json")
    al = {a["floor"]: a for a in j["alignment"]}
    check(al[1]["ok"] and not al[2]["ok"] and al[2]["reason"], al)
    check({w["floor"] for w in j["walls"]} == {1}, {w["floor"] for w in j["walls"]})
    check({r["floor"] for r in j["rooms"]} == {1} and {o["floor"] for o in j["openings"]} == {1})
    check(any(r["kind"] == "floor" and r["floor"] == 2 for r in j["rejected"]), j["rejected"])


@test("prepare")
def test_find_inputs_from_zip_ignores_georef(tmp):
    import zipfile
    import prepare_rolove_input as pri
    s = fixtures.synthetic_building(tmp, write_files=True)
    src = tmp / "src"
    src.mkdir()
    with zipfile.ZipFile(src / "p (1).zip", "w") as z:
        z.write(s["paths"]["dxf"], "p.dxf")
        z.write(s["paths"]["csv"], "p.csv")
    s["paths"]["glb"].rename(src / "p.glb")
    s["paths"]["laz"].rename(src / "p georef.laz")
    found, missing = pri.find_inputs(src / "p (1).zip", tmp / "out")
    check(set(found) == {"dxf", "csv", "glb"}, found)
    check(found["dxf"].parent == tmp / "out" / "rolove_src", found["dxf"])
    check(found["glb"] == src / "p.glb", found["glb"])
    check([m["file"] for m in missing] == ["laz"] and "georef" in missing[0]["polycam_export"],
          missing)


# --------------------------------------------------------------------------
# ledger (Revit tarafi defteri; saf Python, Revit import'u yok)
# --------------------------------------------------------------------------

def _ledger():
    lib = HERE.parent.parent / "lib" / "pykalfa" / "rolove"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    import ledger
    return ledger


@test("ledger")
def test_plan_actions_respects_deleted(tmp):
    ledger = _ledger()
    r = ledger.plan_actions(["a", "b", "c"], {"a": "u1", "b": "u2"}, {"u1"})
    check(r == {"create": ["c"], "keep": ["a"], "deleted": ["b"]}, r)


def _xw(sid, a, b, outward):
    return {"id": sid, "location": "interior_face", "start_ft": list(a), "end_ft": list(b),
            "outward": list(outward)}


@test("ledger")
def test_exterior_axes_meet_at_corners(tmp):
    _ledger()
    import wallaxes
    # Dis bukey kose: ic yuzler (5,0)'da bulusur; W = 1 ft.
    walls = [_xw("a", (0, 0), (5, 0), (0, -1)), _xw("b", (5, 0), (5, 4), (1, 0)),
             {"id": "i", "location": "center", "start_ft": [2, 0], "end_ft": [2, 4],
              "outward": None}]
    ax = wallaxes.exterior_axes(walls, 1.0, 0.01)
    check(ax["a"]["axis"][1] == (5.5, -0.5) and ax["b"]["axis"][0] == (5.5, -0.5), ax)
    check(ax["a"]["axis"][0] == (0.0, -0.5), ax["a"])            # serbest uc: duz ofset
    check(ax["a"]["face"][1] == (5.5, 0.0) and ax["b"]["face"][0] == (5.0, -0.5), ax)
    check("i" not in ax, ax)
    # Ic bukey (reflex) kose: (0,0)->(5,0) disari -y, (5,0)->(5,-4) disari +x
    r = wallaxes.exterior_axes([_xw("c", (0, 0), (5, 0), (0, -1)),
                                _xw("d", (5, 0), (5, -4), (1, 0))], 1.0, 0.01)
    check(r["c"]["axis"][1] == (5.5, -0.5) and r["d"]["axis"][0] == (5.5, -0.5), r)
    # Ayni dogrultuda devam eden iki duvar: dokunulmaz
    s = wallaxes.exterior_axes([_xw("e", (0, 0), (5, 0), (0, -1)),
                                _xw("f", (5, 0), (9, 0), (0, -1))], 1.0, 0.01)
    check(s["e"]["axis"][1] == (5.0, -0.5) and s["f"]["axis"][0] == (5.0, -0.5), s)


@test("ledger")
def test_ledger_roundtrip_and_corrupt(tmp):
    ledger = _ledger()
    d = {"version": 1, "sources": ["k"], "items": {"a": "u"}}
    check(ledger.loads(ledger.dumps(d))["items"] == {"a": "u"})
    check(ledger.loads("not json") == ledger.empty())
    check(ledger.loads("") == ledger.empty() and ledger.loads(None) == ledger.empty())
    check(ledger.loads('{"version": 1}') == ledger.empty(), ledger.loads('{"version": 1}'))
    check(ledger.empty() is not ledger.empty())                 # paylasilan sozluk yok


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="virgulle ayrilmis gruplar")
    args = parser.parse_args(argv)
    groups = {g for g in args.only.split(",") if g}

    passed = failed = 0
    for group, fn in TESTS:
        if groups and group not in groups:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            try:
                fn(Path(tmp))
                passed += 1
                print("  [OK]   {}:{}".format(group, fn.__name__))
            except Exception as exc:  # noqa: BLE001 - test raporu
                failed += 1
                print("  [HATA] {}:{} -> {!r}".format(group, fn.__name__, exc))
                tb = traceback.extract_tb(exc.__traceback__)[-1]
                print("         {}:{}".format(Path(tb.filename).name, tb.lineno))

    print("\n{} gecti, {} basarisiz".format(passed, failed))
    return 0 if failed == 0 and passed > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
