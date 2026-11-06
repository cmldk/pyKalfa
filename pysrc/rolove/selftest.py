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
