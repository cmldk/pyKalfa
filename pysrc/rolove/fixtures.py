"""
pyKalfa / Rolove - sentetik Polycam ciktilari (yalniz testler icin)

Gercek ornek dosyalardaki yapiyi taklit eder (bkz. spec "Verinin bilinen
yapisi"): katman adlari `Polycam-Floor_N-*`, duvarlar 7 noktali ve
flags=0 ama ilk nokta = son nokta olan halkalar, her duvar iki kez yazilir,
aciklik 5 noktali dikdortgen.
"""

from __future__ import annotations

import csv
import math

import ezdxf

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
