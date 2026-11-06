"""
pyKalfa / Rolove - Polycam kat plani DXF okuyucu

Polycam'in RoomPlan tabanli kat plani DXF'i semantigi katman adinda
tasir: `Polycam-Floor_<n>-Walls`, `-Openings-Doors`, `-Openings-Windows`,
`-Openings-Openings`, `-Floors`, `-Labels-Rooms`. Bu modul yalniz bunlari
okur; diger katmanlar (Objects, Dimensions, Hatch, Compass) yok sayilir.

Sonuc METRE ve DXF cercevesindedir. Dikkat: Polycam katlari paftaya yan
yana dizer; her katin taramaya donusumu `align.py`'nin isidir.

Geometri okuma ve duvar dis hattindan eksen cikarma mevcut `pysrc/duvar`
modullerinden gelir (yalniz import edilir, degistirilmez).
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_DUVAR = Path(__file__).resolve().parent.parent / "duvar"
if str(_DUVAR) not in sys.path:
    sys.path.insert(0, str(_DUVAR))

import ezdxf  # noqa: E402

import config  # noqa: E402
import geom2d  # noqa: E402
from dxf_reader import meters_per_unit, read_dxf  # noqa: E402
from wall_detector import outline_to_centerline  # noqa: E402

LAYER_RE = re.compile(
    r"^Polycam-Floor_(\d+)-(Walls|Openings-Doors|Openings-Windows|Openings-Openings"
    r"|Floors|Labels-Rooms)$"
)
OPENING_KINDS = {
    "Openings-Doors": "door",
    "Openings-Windows": "window",
    "Openings-Openings": "opening",
}


@dataclass
class DxfWall:
    floor: int
    center: tuple
    thickness: float

    def faces(self):
        half = self.thickness / 2.0
        return (geom2d.offset_seg(self.center, half), geom2d.offset_seg(self.center, -half))


@dataclass
class DxfOpening:
    floor: int
    kind: str
    center: tuple
    width: float
    direction: tuple


@dataclass
class DxfRoom:
    floor: int
    name: str
    polygon: list


@dataclass
class FloorLayers:
    walls: list = field(default_factory=list)
    openings: list = field(default_factory=list)
    rooms: list = field(default_factory=list)


@dataclass
class FloorPlan:
    floors: dict
    insunits: int
    warnings: list


def _parse_layer(layer):
    m = LAYER_RE.match(layer or "")
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def _scale_points(points, s):
    return [(x * s, y * s) for x, y in points]


def _dedupe_walls(walls):
    seen = set()
    out = []
    tol = config.DUPLICATE_TOL_M
    for w in walls:
        (x1, y1), (x2, y2) = w.center
        key = (round(x1 / tol), round(y1 / tol), round(x2 / tol), round(y2 / tol))
        rev = (key[2], key[3], key[0], key[1])
        if key in seen or rev in seen:
            continue
        seen.add(key)
        out.append(w)
    return out


def _opening_from_ring(ring, floor, kind):
    if len(ring) != 4:
        return None
    edges = [(ring[i], ring[(i + 1) % 4]) for i in range(4)]
    longest = max(edges, key=geom2d.seg_length)
    width = geom2d.seg_length(longest)
    if width <= 0:
        return None
    cx = sum(p[0] for p in ring) / 4.0
    cy = sum(p[1] for p in ring) / 4.0
    return DxfOpening(floor, kind, (cx, cy), width, geom2d.seg_dir(longest))


def _read_labels(path, scale):
    """{kat: [(metin, (x, y))]} — `Labels-Rooms` MTEXT'leri."""
    doc = ezdxf.readfile(str(path))
    labels = {}
    for e in doc.modelspace().query("MTEXT"):
        floor, kind = _parse_layer(e.dxf.layer)
        if kind != "Labels-Rooms":
            continue
        text = e.plain_text().strip()
        ins = e.dxf.insert
        labels.setdefault(floor, []).append((text, (ins[0] * scale, ins[1] * scale)))
    return labels


def read_floorplan(path: Path) -> FloorPlan:
    path = Path(path)
    result = read_dxf(path)
    warnings = list(result.warnings)

    scale = 1.0
    if result.insunits != 6:
        mpu = meters_per_unit(result.insunits)
        if mpu is None:
            warnings.append("DXF birimi belirtilmemis ($INSUNITS={}); metre kabul edildi."
                            .format(result.insunits))
        else:
            scale = mpu
            warnings.append("DXF birimi metre degil ($INSUNITS={}); metreye cevrildi."
                            .format(result.insunits))

    floors = {}
    raw_walls = {}
    room_polys = {}

    for poly in result.polys:
        floor, kind = _parse_layer(poly.layer)
        if floor is None or not poly.is_ring():
            continue
        ring = _scale_points(poly.ring(), scale)
        layers = floors.setdefault(floor, FloorLayers())
        if kind == "Walls":
            res = outline_to_centerline(ring, 1.0)
            if res is None:
                warnings.append("Kat {}: duvar dis hatti eksene cevrilemedi.".format(floor))
                continue
            c1, c2, t = res
            raw_walls.setdefault(floor, []).append(DxfWall(floor, (c1, c2), t))
        elif kind in OPENING_KINDS:
            op = _opening_from_ring(ring, floor, OPENING_KINDS[kind])
            if op is not None:
                layers.openings.append(op)
        elif kind == "Floors":
            room_polys.setdefault(floor, []).append(ring)

    for floor, walls in raw_walls.items():
        floors[floor].walls = _dedupe_walls(walls)

    labels = _read_labels(path, scale)
    for floor, polys in room_polys.items():
        used = set()
        for idx, polygon in enumerate(polys, start=1):
            name = None
            for li, (text, pt) in enumerate(labels.get(floor, [])):
                if li not in used and geom2d.point_in_polygon(pt, polygon):
                    name = text
                    used.add(li)
                    break
            floors[floor].rooms.append(DxfRoom(floor, name or "Oda {}".format(idx), polygon))

    # Hicbir semantik eleman tasimayan kat girdilerini birakma.
    floors = {k: v for k, v in floors.items() if v.walls or v.openings or v.rooms}
    return FloorPlan(dict(sorted(floors.items())), result.insunits, warnings)
