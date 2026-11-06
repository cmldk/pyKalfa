"""
pyKalfa / Rolove - Polycam GLB kat gruplari

Polycam'in mesh GLB'sinde kok dugumun altinda `Story 0..n` adli gruplar
vardir; her grup o katin dokulu mesh parcalarini tasir (elemana gore
ayrilmamis). Burada iki sey okunur:

  - `read_story_bands`: yalniz JSON'daki accessor min/max'larindan kat
    basina sinir kutusu (hizli, vertex okumadan);
  - `read_story_triangles`: kat basina ucgenlerin Z'si, alani ve normalinin
    Z bileseni. Doseme = yukari bakan, tavan = asagi bakan buyuk yatay
    yuzeyler (bkz. `levels.py`). Katlar ayri gruplarda oldugu icin alt
    katin tavani ust katin dosemesine karismaz.

Eksen: glTF Y-yukari; LAZ ile ayni cerceveye `laz = (gx, -gz, gy)` ile
gecilir (ornek veride sinirlar birebir tutuyor).
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_STORY_RE = re.compile(r"^Story\s+(\d+)$")
_COMPONENT = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
_TRANSFORM_KEYS = ("matrix", "translation", "rotation", "scale")


@dataclass
class StoryBand:
    index: int
    name: str
    zmin: float
    zmax: float
    xmin: float
    xmax: float
    ymin: float
    ymax: float


def _read_glb(path, with_bin):
    with open(path, "rb") as f:
        head = f.read(12)
        magic, _version, _length = struct.unpack("<4sII", head)
        if magic != b"glTF":
            raise ValueError("GLB dosyasi degil: {}".format(path))
        clen, ctype = struct.unpack("<I4s", f.read(8))
        gltf = json.loads(f.read(clen))
        binary = None
        if with_bin:
            blen, _btype = struct.unpack("<I4s", f.read(8))
            binary = f.read(blen)
    return gltf, binary


def _stories(gltf):
    """[(index, ad, [mesh_id, ...])] — `Story <n>` gruplari."""
    nodes = gltf.get("nodes", [])
    out = []
    for node in nodes:
        m = _STORY_RE.match(node.get("name", "") or "")
        if not m:
            continue
        meshes = []
        stack = list(node.get("children", []))
        for key in _TRANSFORM_KEYS:
            if key in node:
                raise ValueError("GLB kat dugumunde donusum var; desteklenmiyor.")
        while stack:
            child = nodes[stack.pop()]
            for key in _TRANSFORM_KEYS:
                if key in child:
                    raise ValueError("GLB mesh dugumunde donusum var; desteklenmiyor.")
            if "mesh" in child:
                meshes.append(child["mesh"])
            stack.extend(child.get("children", []))
        out.append((int(m.group(1)), node["name"], meshes))
    if not out:
        raise ValueError("GLB'de 'Story <n>' adli kat grubu bulunamadi.")
    return sorted(out)


def _to_laz(v):
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)


def read_story_bands(path: Path) -> list:
    gltf, _ = _read_glb(path, with_bin=False)
    bands = []
    for index, name, mesh_ids in _stories(gltf):
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        for mid in mesh_ids:
            for prim in gltf["meshes"][mid]["primitives"]:
                acc = gltf["accessors"][prim["attributes"]["POSITION"]]
                corners = _to_laz(np.array([acc["min"], acc["max"]], dtype=np.float64))
                lo = np.minimum(lo, corners.min(axis=0))
                hi = np.maximum(hi, corners.max(axis=0))
        bands.append(StoryBand(index, name, float(lo[2]), float(hi[2]), float(lo[0]),
                               float(hi[0]), float(lo[1]), float(hi[1])))
    return bands


def _accessor(gltf, binary, idx):
    acc = gltf["accessors"][idx]
    view = gltf["bufferViews"][acc["bufferView"]]
    n = _NCOMP[acc["type"]]
    offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    arr = np.frombuffer(binary, dtype=_COMPONENT[acc["componentType"]],
                        count=acc["count"] * n, offset=offset)
    return arr.reshape(-1, n) if n > 1 else arr


def read_story_triangles(path: Path) -> dict:
    """{kat_index: (z, alan, nz)} — ucgen agirlik merkezi Z'si, alani ve
    birim normalin Z bileseni (LAZ cercevesi)."""
    gltf, binary = _read_glb(path, with_bin=True)
    out = {}
    for index, _name, mesh_ids in _stories(gltf):
        zs, areas, nzs = [], [], []
        for mid in mesh_ids:
            for prim in gltf["meshes"][mid]["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                v = _to_laz(_accessor(gltf, binary, prim["attributes"]["POSITION"])
                            .astype(np.float64))
                if "indices" in prim:
                    f = _accessor(gltf, binary, prim["indices"]).astype(np.int64).reshape(-1, 3)
                else:
                    f = np.arange(len(v)).reshape(-1, 3)
                a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
                n = np.cross(b - a, c - a)
                norm = np.linalg.norm(n, axis=1)
                ok = norm > 1e-12
                zs.append(((a[:, 2] + b[:, 2] + c[:, 2]) / 3.0)[ok])
                areas.append(norm[ok] / 2.0)
                nzs.append(n[ok, 2] / norm[ok])
        out[index] = (np.concatenate(zs) if zs else np.zeros(0),
                      np.concatenate(areas) if areas else np.zeros(0),
                      np.concatenate(nzs) if nzs else np.zeros(0))
    return out
