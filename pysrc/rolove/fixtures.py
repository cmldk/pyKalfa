"""
pyKalfa / Rolove - sentetik Polycam ciktilari (yalniz testler icin)

Gercek ornek dosyalardaki yapiyi taklit eder (bkz. spec "Verinin bilinen
yapisi"): katman adlari `Polycam-Floor_N-*`, duvarlar 7 noktali ve
flags=0 ama ilk nokta = son nokta olan halkalar, her duvar iki kez yazilir,
aciklik 5 noktali dikdortgen.
"""

from __future__ import annotations

import csv
import json
import math
import struct
from pathlib import Path

import ezdxf
import numpy as np

OPENING_DEPTH_M = 0.10


def _layer(floor, name):
    return "Polycam-Floor_{}-{}".format(floor, name)


def _wall_ring(p1, p2, thickness):
    (x1, y1), (x2, y2) = p1, p2
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    nx, ny = -uy * thickness / 2.0, ux * thickness / 2.0
    return [
        (x1, y1), (x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2, y2),
        (x2 - nx, y2 - ny), (x1 - nx, y1 - ny), (x1, y1),
    ]


def _rect_ring(center, width, direction, depth=OPENING_DEPTH_M):
    cx, cy = center
    ux, uy = direction
    norm = math.hypot(ux, uy)
    ux, uy = ux / norm, uy / norm
    hx, hy = ux * width / 2.0, uy * width / 2.0
    nx, ny = -uy * depth / 2.0, ux * depth / 2.0
    pts = [
        (cx - hx - nx, cy - hy - ny), (cx - hx + nx, cy - hy + ny),
        (cx + hx + nx, cy + hy + ny), (cx + hx - nx, cy + hy - ny),
    ]
    return pts + [pts[0]]


def _shift(points, offset):
    ox, oy = offset
    return [(x + ox, y + oy) for x, y in points]


def write_polycam_dxf(path, floors, offset=(0.0, 0.0)):
    """Polycam kat plani DXF'i yazar (metre, $INSUNITS=6).

    `floors[n] = {"walls": [((x1,y1),(x2,y2),t)], "doors"/"windows"/
    "openings": [((cx,cy), width, (ux,uy))], "rooms": [(ad, poligon)],
    "junk": bool}`"""
    doc = ezdxf.new("R2004")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for floor, spec in floors.items():
        for p1, p2, t in spec.get("walls", []):
            ring = _shift(_wall_ring(p1, p2, t), offset)
            for _ in range(2):  # Polycam her duvari iki kez yazar
                msp.add_lwpolyline(ring, dxfattribs={"layer": _layer(floor, "Walls")})
        for key, layer in (("doors", "Openings-Doors"), ("windows", "Openings-Windows"),
                           ("openings", "Openings-Openings")):
            for center, width, direction in spec.get(key, []):
                ring = _shift(_rect_ring(center, width, direction), offset)
                msp.add_lwpolyline(ring, dxfattribs={"layer": _layer(floor, layer)})
                if key == "doors":
                    c = _shift([center], offset)[0]
                    msp.add_line(c, (c[0] + 0.5, c[1] + 0.5),
                                 dxfattribs={"layer": _layer(floor, layer)})
                    msp.add_ellipse((c[0], c[1], 0), major_axis=(width, 0, 0), ratio=1.0,
                                    start_param=0, end_param=math.pi / 2,
                                    dxfattribs={"layer": _layer(floor, layer)})
        for name, polygon in spec.get("rooms", []):
            poly = _shift(list(polygon), offset)
            msp.add_lwpolyline(poly + [poly[0]], dxfattribs={"layer": _layer(floor, "Floors")})
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            msp.add_mtext(name, dxfattribs={"layer": _layer(floor, "Labels-Rooms"),
                                            "insert": (cx, cy)})
        if spec.get("junk"):
            sq = _shift([(1, 1), (1.6, 1), (1.6, 1.6), (1, 1.6), (1, 1)], offset)
            msp.add_lwpolyline(sq, dxfattribs={"layer": _layer(floor, "Objects-Furniture")})
            ring = _shift(_wall_ring((0, 0), (4, 0), 0.10), offset)
            msp.add_lwpolyline(ring, dxfattribs={"layer": _layer(floor, "Walls-Hatch")})
            msp.add_lwpolyline(ring, dxfattribs={"layer": _layer(floor, "Dimensions-Interior")})
            msp.add_lwpolyline(ring, dxfattribs={"layer": "Polycam-Compass"})
            msp.add_mtext("12 m2", dxfattribs={"layer": _layer(floor, "Labels-Areas"),
                                               "insert": (2, 2)})
    doc.saveas(str(path))


def write_polycam_csv(path, rows):
    """Polycam kat plani CSV'si (`Floor,Room,Description,Value`)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Floor", "Room", "Description", "Value"])
        w.writerows(rows)


# --------------------------------------------------------------------------
# GLB / LAZ
# --------------------------------------------------------------------------

def laz_to_gltf(points):
    """LAZ (x, y, z) -> glTF (x, z, -y); `glb_stories`'in tersi."""
    p = np.asarray(points, dtype=np.float64)
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)


def quad(x0, y0, x1, y1, z, up=True):
    """LAZ cercevesinde yatay dikdortgen: (verts 4x3, faces 2x3)."""
    v = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], dtype=np.float64)
    f = np.array([[0, 1, 2], [0, 2, 3]]) if up else np.array([[0, 2, 1], [0, 3, 2]])
    return v, f


def merge_meshes(parts):
    verts, faces, base = [], [], 0
    for v, f in parts:
        verts.append(v)
        faces.append(np.asarray(f) + base)
        base += len(v)
    return np.vstack(verts), np.vstack(faces)


def write_story_glb(path, stories):
    """`stories = [(ad, gltf_verts Nx3, faces Mx3)]` -> GLB (Polycam duzeni:
    kok dugum altinda `Story <n>` adli gruplar)."""
    bin_parts, accessors, views, meshes, nodes = [], [], [], [], []
    state = {"offset": 0}

    def add_view(data, target):
        raw = data.tobytes()
        views.append({"buffer": 0, "byteOffset": state["offset"], "byteLength": len(raw),
                      "target": target})
        bin_parts.append(raw)
        state["offset"] += len(raw)
        pad = (-state["offset"]) % 4
        if pad:
            bin_parts.append(bytes(pad))
            state["offset"] += pad
        return len(views) - 1

    story_nodes = []
    for name, verts, faces in stories:
        v = np.asarray(verts, dtype=np.float32)
        f = np.asarray(faces, dtype=np.uint32).reshape(-1)
        pv = add_view(v, 34962)
        accessors.append({"bufferView": pv, "componentType": 5126, "count": len(v),
                          "type": "VEC3", "min": v.min(axis=0).tolist(),
                          "max": v.max(axis=0).tolist()})
        pa = len(accessors) - 1
        iv = add_view(f, 34963)
        accessors.append({"bufferView": iv, "componentType": 5125, "count": len(f),
                          "type": "SCALAR"})
        ia = len(accessors) - 1
        meshes.append({"primitives": [{"attributes": {"POSITION": pa}, "indices": ia}]})
        nodes.append({"mesh": len(meshes) - 1})
        nodes.append({"name": name, "children": [len(nodes) - 1]})
        story_nodes.append(len(nodes) - 1)
    nodes.append({"children": story_nodes})
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [len(nodes) - 1]}],
            "nodes": nodes, "meshes": meshes, "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": state["offset"]}]}
    js = json.dumps(gltf).encode("utf-8")
    js += b" " * ((-len(js)) % 4)
    binary = b"".join(bin_parts)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total))
        fh.write(struct.pack("<I4s", len(js), b"JSON") + js)
        fh.write(struct.pack("<I4s", len(binary), b"BIN" + bytes(1)) + binary)


def write_laz(path, points, georef=False):
    import laspy
    pts = np.asarray(points, dtype=np.float64)
    header = laspy.LasHeader(point_format=2, version="1.2")
    header.scales = np.array([1e-9, 1e-9, 1e-6]) if georef else np.array([1e-5, 1e-5, 1e-5])
    header.offsets = pts.min(axis=0)
    las = laspy.LasData(header)
    las.x, las.y, las.z = pts[:, 0], pts[:, 1], pts[:, 2]
    las.write(str(path))


# --------------------------------------------------------------------------
# Hizalama fixture'i
# --------------------------------------------------------------------------

L_FLOOR_WALLS = [
    ((0, 0), (8, 0)), ((8, 0), (8, 3)), ((8, 3), (4, 3)),
    ((4, 3), (4, 6)), ((4, 6), (0, 6)), ((0, 6), (0, 0)), ((6, 0), (6, 3)),
]


def _transform(xy, rot_deg, mirror, shift):
    p = np.array(xy, dtype=np.float64)
    if mirror:
        p[:, 1] = -p[:, 1]
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    p = np.stack([c * p[:, 0] - s * p[:, 1], s * p[:, 0] + c * p[:, 1]], axis=1)
    return p + np.asarray(shift)


def floor_faces_and_slice(rot_deg, mirror, shift, noise, thickness=0.10, seed=0):
    """L bicimli bir kat: (DXF cercevesinde `DxfWall` listesi, tarama
    cercevesinde yatay dilim noktalari Nx2 — iki yuz de taranmis)."""
    import polycam_dxf
    rng = np.random.default_rng(seed)
    walls = [polycam_dxf.DxfWall(2, (p1, p2), thickness) for p1, p2 in L_FLOOR_WALLS]
    faces = [f for w in walls for f in w.faces()]
    samples = []
    for (x1, y1), (x2, y2) in faces:
        n = max(int(math.hypot(x2 - x1, y2 - y1) / 0.02), 2)
        t = np.linspace(0, 1, n)
        samples.append(np.stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t], axis=1))
    pts = _transform(np.vstack(samples), rot_deg, mirror, shift)
    if noise:
        pts = pts + rng.normal(0, noise, pts.shape)
    return walls, pts


# --------------------------------------------------------------------------
# Sentetik bina
# --------------------------------------------------------------------------

def _plane_points(rng, x0, y0, x1, y1, z, step=0.05, noise=0.003):
    xs = np.arange(x0, x1, step)
    ys = np.arange(y0, y1, step)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, z)], axis=1)
    return pts + rng.normal(0, noise, pts.shape)


def _vwall_points(rng, p1, p2, z0, z1, step=0.05, noise=0.003):
    (x1, y1), (x2, y2) = p1, p2
    length = math.hypot(x2 - x1, y2 - y1)
    ts = np.arange(0, length, step) / length
    zs = np.arange(z0, z1, step)
    gt, gz = np.meshgrid(ts, zs)
    pts = np.stack([x1 + (x2 - x1) * gt.ravel(), y1 + (y2 - y1) * gt.ravel(), gz.ravel()],
                   axis=1)
    return pts + rng.normal(0, noise, pts.shape)


# DXF'te bilerek hatali cizilmis duvarlar (tarama cercevesi koordinatlari;
# DXF'e `SYN_DXF_OFFSET` eklenerek yazilir):
#   - alt/ust dis duvarlarin ic yuzu dogru (y=0 / y=4),
#   - sag dis duvarin ic yuzu 3 cm kayik (6.03; gercek 6.00),
#   - sol dis duvarin ic yuzu 25 cm kayik (-0.25; gercek 0.00) -> duzeltilmez,
#   - ic duvar DXF'te 0.10 kalin ve ekseni 3.04 (gercek 2.90..3.10, 0.20).
SYN_DXF_OFFSET = (10.0, 5.0)
SYN_WALLS = [
    ((-0.30, -0.05), (6.08, -0.05), 0.10),
    ((6.08, -0.05), (6.08, 4.05), 0.10),
    ((6.08, 4.05), (-0.30, 4.05), 0.10),
    ((-0.30, 4.05), (-0.30, -0.05), 0.10),
    ((3.04, 0.0), (3.04, 4.0), 0.10),
]
SYN_ROOMS = {
    1: [("Room A", [(0, 0), (2.9, 0), (2.9, 4), (0, 4)]),
        ("Room B", [(3.1, 0), (6, 0), (6, 4), (3.1, 4)])],
    2: [("Bedroom 2", [(0, 0), (2.9, 0), (2.9, 4), (0, 4)]),
        ("Room B2", [(3.1, 0), (6, 0), (6, 4), (3.1, 4)])],
}


# Ic duvarda bir kapi, alt dis duvarda bir pencere (DXF ekseni uzerinde).
SYN_DOORS = [((3.04, 2.0), 0.80, (0.0, 1.0))]
SYN_WINDOWS = [((1.5, -0.05), 1.20, (1.0, 0.0))]
# CSV: Kat 2'nin yasanabilir alani daha buyuk -> ana kat (Z datum) = Kat 2.
SYN_CSV_ROWS = [
    ("Floor 1", "Entire Floor", "Total livable floor area [m^2]", "22.0"),
    ("Floor 2", "Entire Floor", "Total livable floor area [m^2]", "23.2"),
    ("Floor 1", "Room A", "Ceiling height [m]", "2.5 "),
    ("Floor 1", "Room A", "Door dimensions [m]", "0.8 x 2.1"),
    ("Floor 1", "Room A", "Window dimensions [m]", "1.2 x 1.4"),
    ("Floor 1", "Room A", "Floor area [m^2]", "11.6"),
    ("Floor 1", "Room B", "Ceiling height [m]", "2.5 "),
    ("Floor 2", "Bedroom 2", "Ceiling height [m]", "0.7 - 2.4 "),
    ("Floor 2", "Room B2", "Ceiling height [m]", "2.5 "),
    ("All", "Settings", "Wall thickness [m] (total wall length: 40.0)", "0.100"),
]
SYN_MAIN_FLOOR = 2


def synthetic_dxf_floors():
    floors = {}
    for f, rooms in SYN_ROOMS.items():
        floors[f] = {"walls": list(SYN_WALLS), "doors": list(SYN_DOORS),
                     "windows": list(SYN_WINDOWS), "openings": [], "rooms": rooms}
    return floors


def synthetic_building(tmp, write_files=False, seed=0):
    """Iki katli sentetik bina (tarama cercevesi, metre).

    Her kat: ic yuzleri x=0, x=6, y=0, y=4 olan dis duvarlar; x=2.9..3.1
    arasinda 0.20 m kalin bir ic duvar. Kat 1 dosemesi 0.00 / tavan 2.50
    (+ 0.75 m'de 1 m2 masa), Kat 2 dosemesi 2.80 / tavan 5.30 (+ 2.45'te
    kucuk merdiven basamagi: bantlar cakisir)."""
    rng = np.random.default_rng(seed)
    floors = {1: (0.00, 2.50), 2: (2.80, 5.30)}
    pts, stories = [], []
    for floor, (fz, cz) in floors.items():
        pts.append(_plane_points(rng, 0, 0, 6, 4, fz))
        pts.append(_plane_points(rng, 0, 0, 6, 4, cz))
        faces = [((0, 0), (6, 0)), ((6, 0), (6, 4)), ((6, 4), (0, 4)), ((0, 4), (0, 0)),
                 ((2.9, 0), (2.9, 4)), ((3.1, 0), (3.1, 4))]
        if floor == 1:
            # Esya: duvar onundeki dolap/kitaplik arkasindaki yuzu gizler ve
            # yuzden daha cok hucre doldurur (en guclu tepe = esya).
            faces = [((0, 0), (0.2, 0)), ((3.5, 0), (6, 0))] + faces[1:5] + [
                ((3.1, 0), (3.1, 0.2)), ((3.1, 2.2), (3.1, 4))]
            for p1, p2 in (((0.2, 0.24), (3.5, 0.24)), ((3.35, 0.2), (3.35, 2.2))):
                pts.append(_vwall_points(rng, p1, p2, fz, fz + 2.2))
        for p1, p2 in faces:
            pts.append(_vwall_points(rng, p1, p2, fz, cz))
        parts = [quad(0, 0, 6, 4, fz, up=True), quad(0, 0, 6, 4, cz, up=False)]
        if floor == 1:
            pts.append(_plane_points(rng, 4.0, 1.0, 5.0, 2.0, fz + 0.75))
            parts.append(quad(4.0, 1.0, 5.0, 2.0, fz + 0.75, up=True))
        else:
            parts.append(quad(5.0, 3.0, 5.6, 3.5, fz - 0.35, up=True))
        v, f = merge_meshes(parts)
        stories.append(("Story {}".format(floor - 1), laz_to_gltf(v), f))
    points = np.vstack(pts).astype(np.float32)
    result = {"points": points, "stories": stories, "floors": floors, "paths": {},
              "dxf_offset": SYN_DXF_OFFSET, "dxf_floors": synthetic_dxf_floors(),
              "rooms_scan": {f: list(SYN_ROOMS[f]) for f in SYN_ROOMS},
              "main_floor": SYN_MAIN_FLOOR}
    if write_files:
        tmp = Path(tmp)
        for key in ("dxf", "csv", "laz", "glb"):
            result["paths"][key] = tmp / "p.{}".format(key)
        write_story_glb(result["paths"]["glb"], stories)
        write_laz(result["paths"]["laz"], points)
        write_polycam_dxf(result["paths"]["dxf"], synthetic_dxf_floors(), SYN_DXF_OFFSET)
        write_polycam_csv(result["paths"]["csv"], SYN_CSV_ROWS)
    return result
