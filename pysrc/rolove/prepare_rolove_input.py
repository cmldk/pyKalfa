"""
pyKalfa / Rolove - Polycam ciktilari -> `rolove_input.json` (+ kat PNG'leri)

    prepare_rolove_input.py --input "<ad>.dxf | <kat plani>.zip" --output-dir output
                            [--csv P --laz P --glb P]

Kullanici yalniz DXF'i (ya da kat plani zip'ini) secer; CSV/LAZ/GLB ayni
klasorde ayni ad kokuyle bulunur (`<ad> georef.laz` secilmez).

Arayuz icin `PROGRESS|yuzde|mesaj` satirlari basilir.
Cikis kodlari: 0 basari; 2 eksik girdi (JSON yine yazilir, `missing` dolu,
baska hicbir sey uretilmez); 1 hata (mesaj stderr'de).

Revit tarafinin tek sozlesmesi bu dosyanin yazdigi JSON'dur (sema 1):
koordinatlar feet, XY = LAZ yerel cercevesi, Z = ana katin dosemesi 0.00.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import traceback
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _extra in (HERE, HERE.parent / "duvar"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import config  # noqa: E402

SCHEMA_VERSION = 1
FILE_KEYS = ("dxf", "csv", "laz", "glb")
POLYCAM_EXPORTS = {
    "dxf": "Floor plan -> DXF",
    "csv": "Floor plan -> CSV",
    "laz": "Point cloud -> LAS (georef kapali)",
    "glb": "Mesh -> GLTF (.glb)",
}
_DUP_SUFFIX = re.compile(r"\s*\(\d+\)$")      # tarayicinin "ad (1).zip" eki


def _progress(percent, message):
    print("PROGRESS|{}|{}".format(int(percent), message), flush=True)


# --------------------------------------------------------------------------
# Girdiler
# --------------------------------------------------------------------------

def find_inputs(input_path: Path, out_dir: Path, overrides=None):
    """({anahtar: yol}, eksikler). Zip ise DXF/CSV `out_dir/rolove_src`'a
    acilir; kardes dosyalar zip'in klasorunde DXF'in ad kokuyle aranir."""
    input_path = Path(input_path)
    folder = input_path.parent
    found = {}
    suffix = input_path.suffix.lower()
    if suffix == ".zip":
        src = Path(out_dir) / "rolove_src"
        src.mkdir(parents=True, exist_ok=True)
        root = None
        with zipfile.ZipFile(input_path) as z:
            for info in z.infolist():
                name = Path(info.filename).name          # yalniz ad: zip-slip yok
                ext = Path(name).suffix.lower().lstrip(".")
                if ext not in ("dxf", "csv") or ext in found or info.is_dir():
                    continue
                target = src / name
                with z.open(info) as fin, open(target, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                found[ext] = target
                if ext == "dxf":
                    root = Path(name).stem
        if root is None:
            root = _DUP_SUFFIX.sub("", input_path.stem)
    elif suffix == ".dxf":
        found["dxf"] = input_path
        root = input_path.stem
    else:
        raise ValueError("Girdi .dxf ya da kat plani .zip olmali: {}".format(input_path.name))

    roots = [root]
    if _DUP_SUFFIX.search(root):
        roots.append(_DUP_SUFFIX.sub("", root))
    for key in ("csv", "laz", "glb"):
        if key in found:
            continue
        for r in roots:
            cand = folder / "{}.{}".format(r, key)
            if cand.is_file():
                found[key] = cand
                break
    for key, path in (overrides or {}).items():
        if path:
            found[key] = Path(path)
    missing = [{"file": k, "polycam_export": POLYCAM_EXPORTS[k],
                "expected": "{}.{}".format(root, k)}
               for k in FILE_KEYS if k not in found or not Path(found[k]).is_file()]
    found = {k: Path(v) for k, v in found.items() if Path(v).is_file()}
    return found, missing


def stable_id(kind: str, floor: int, pts_m) -> str:
    """Kat + DXF cercevesindeki 1 cm'ye yuvarlanmis geometriden kararli id."""
    def fmt(p):
        return "%.2f,%.2f" % (round(float(p[0]), 2) + 0.0, round(float(p[1]), 2) + 0.0)
    text = "{}|{}|{}".format(kind, floor, ";".join(sorted(fmt(p) for p in pts_m)))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _unique(ident, seen):
    out, n = ident, 1
    while out in seen:
        n += 1
        out = "{}-{}".format(ident, n)
    seen.add(out)
    return out


def _file_info(path):
    st = Path(path).stat()
    return {"name": Path(path).name, "size": st.st_size,
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime))}


def _source_key(dxf_path):
    h = hashlib.sha1()
    with open(dxf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _empty_doc(found, missing):
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {"key": _source_key(found["dxf"]) if "dxf" in found else None,
                   "files": {k: _file_info(v) for k, v in found.items()}},
        "params": config.as_params(),
        "z_datum": None,
        "missing": missing,
        "rejected": [],
        "warnings": [],
        "alignment": [],
        "levels": [],
        "walls": [],
        "openings": [],
        "rooms": [],
        "thickness_groups": [],
        "stats": {"counts": {}, "status_counts": {}, "timings_s": {}},
        "previews": [],
    }


# --------------------------------------------------------------------------
# Hazirlik
# --------------------------------------------------------------------------

def _ft(p):
    return [float(p[0]) * config.FT, float(p[1]) * config.FT]


def _main_floor(report, rooms_by_floor, floors):
    """En buyuk doseme alanli kat: CSV yasanabilir alan, yoksa DXF oda alanlari."""
    import geom2d
    areas = {f: report.livable_area_by_floor.get(f) for f in floors}
    if not any(a for a in areas.values()):
        areas = {f: sum(geom2d.polygon_area(r.polygon) for r in rooms_by_floor.get(f, []))
                 for f in floors}
    return max(floors, key=lambda f: (areas.get(f) or 0.0, -f))


def _quantized(t):
    return (int(round(t.rot_deg / 90.0)) % 4 * 90, bool(t.mirror))


def _align_all(floors, fp, pts, levels_by_floor):
    import align
    result = {}
    for f in floors:
        result[f] = align.align_floor_auto(f, fp.floors[f].walls, pts, levels_by_floor[f].floor_z)
    good = [a for a in result.values() if a.ok]
    if good:
        prefer = _quantized(max(good, key=lambda a: a.support_ratio).transform)
        for f in floors:
            if _quantized(result[f].transform) != prefer:
                result[f] = align.align_floor_auto(f, fp.floors[f].walls, pts,
                                                   levels_by_floor[f].floor_z, prefer=prefer)
    return result


def prepare(found, missing, out_dir: Path):
    """(json sozlugu, cikis kodu)."""
    import align  # noqa: F401  (erken import hatasi icin)
    import cloud
    import glb_stories
    import levels as levels_mod
    import openings as openings_mod
    import polycam_csv
    import polycam_dxf
    import preview
    import refine

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timings = {}
    t_all = time.perf_counter()
    doc = _empty_doc(found, missing)
    if missing:
        _progress(100, "eksik girdi: " + ", ".join(m["file"] for m in missing))
        return doc, 2

    def lap(name, t0):
        timings[name] = round(time.perf_counter() - t0, 3)
        return time.perf_counter()

    t = time.perf_counter()
    _progress(3, "DXF okunuyor")
    fp = polycam_dxf.read_floorplan(found["dxf"])
    if not fp.floors:
        raise ValueError("DXF'te Polycam kat plani katmani yok (Polycam-Floor_<n>-Walls ...). "
                         "Polycam'de Floor plan -> DXF secin.")
    doc["warnings"].extend(fp.warnings)
    t = lap("dxf", t)
    _progress(6, "CSV okunuyor")
    report = polycam_csv.read_report(found["csv"])
    t = lap("csv", t)
    _progress(9, "GLB kat gruplari okunuyor")
    bands = glb_stories.read_story_bands(found["glb"])
    tris = glb_stories.read_story_triangles(found["glb"])
    t = lap("glb", t)
    _progress(12, "Nokta bulutu yukleniyor")
    pts = cloud.load_laz(found["laz"])
    t = lap("laz", t)
    _progress(30, "Kat kotlari olculuyor")
    floors = sorted(fp.floors)
    measures = levels_mod.measure_levels(tris, bands, floors)
    lv = {m.floor: m for m in measures}
    main_floor = _main_floor(report, {f: fp.floors[f].rooms for f in floors}, floors)
    offset = -lv[main_floor].floor_z
    doc["z_datum"] = {"floor": main_floor, "offset_m": round(offset, 4)}
    t = lap("levels", t)

    _progress(35, "Katlar taramaya hizalaniyor")
    aligns = _align_all(floors, fp, pts, lv)
    t = lap("align", t)

    wall_ids, op_ids, room_ids = set(), set(), set()
    per_floor = {}
    for k, f in enumerate(floors):
        _progress(55 + int(30 * k / max(len(floors), 1)), "Kat {} duvarlari".format(f))
        a = aligns[f]
        tr = a.transform
        doc["alignment"].append({
            "floor": f, "rot_deg": round(tr.rot_deg, 4), "mirror": bool(tr.mirror),
            "tx_m": round(tr.tx, 4), "ty_m": round(tr.ty, 4),
            "rms_m": None if a.rms_m == float("inf") else round(a.rms_m, 4),
            "support_ratio": round(a.support_ratio, 3), "ok": bool(a.ok), "reason": a.reason,
            "slice_band": list(a.slice_band)})
        if not a.ok:
            doc["rejected"].append({"kind": "floor", "floor": f,
                                    "reason": "kat hizalanamadi: {}".format(a.reason)})
            continue
        layer = fp.floors[f]
        rooms_scan = [polycam_dxf.DxfRoom(r.floor, r.name,
                                          [tuple(float(c) for c in tr.apply(p)) for p in r.polygon])
                      for r in layer.rooms]
        report_rooms = [r for (rf, _n), r in report.rooms.items() if rf == f]
        walls = refine.refine_floor(layer.walls, rooms_scan, tr, pts, lv[f], report_rooms)
        refine.join_corners(walls, config.CORNER_SNAP_M)
        ops, rejected = openings_mod.place_openings(layer.openings, walls, tr, rooms_scan,
                                                    report_rooms)
        per_floor[f] = (walls, ops, rooms_scan)

        ids = [_unique(stable_id("wall", f, w.dxf_center), wall_ids) for w in walls]
        for wid, w in zip(ids, walls):
            group = None
            if w.location == "center":
                group = w.thickness_group_m if w.thickness_group_m is not None else \
                    config.round_dim(w.thickness_dxf)
            doc["walls"].append({
                "id": wid, "floor": f, "side": w.side, "location": w.location,
                "start_ft": _ft(w.line[0]), "end_ft": _ft(w.line[1]),
                "outward": None if w.outward is None else [float(w.outward[0]), float(w.outward[1])],
                "thickness_group_cm": None if group is None else int(round(group * 100)),
                "thickness_dxf_cm": int(round(config.round_dim(w.thickness_dxf) * 100)),
                "measured_thickness_cm": None if w.measured_thickness is None
                else w.measured_thickness * 100,
                "height_ft": w.height * config.FT, "height_m": w.height,
                "height_status": w.height_status, "status": w.status,
                "deviation_cm": w.deviation_cm, "support": int(w.support),
                "warnings": list(w.warnings)})
        for o in ops:
            oid = _unique(stable_id(o.kind, f, [o.dxf_center]), op_ids)
            doc["openings"].append({
                "id": oid, "floor": f, "kind": o.kind, "host_id": ids[o.host],
                "offset_ft": o.offset * config.FT, "width_ft": o.width * config.FT,
                "height_ft": o.height * config.FT, "sill_ft": o.sill * config.FT,
                "width_m": o.width, "height_m": o.height, "sill_m": o.sill,
                "status": dict(o.status), "warnings": list(o.warnings)})
        for r in rejected:
            r = dict(r)
            r["id"] = stable_id(r["kind"], f, [r["dxf_center"]])
            doc["rejected"].append(r)
        for r_dxf, r in zip(layer.rooms, rooms_scan):
            rr = report.rooms.get((f, r.name))
            doc["rooms"].append({
                "id": _unique(stable_id("room", f, r_dxf.polygon), room_ids),
                "floor": f, "name": r.name,
                "label_point_ft": _ft(openings_mod.label_point(r.polygon)),
                "polygon_ft": [_ft(p) for p in r.polygon],
                "area_csv_m2": None if rr is None else rr.area})
    t = lap("floors", t)

    for f in floors:
        m = lv[f]
        elev = config.round_level(m.floor_z + offset)
        doc["levels"].append({
            "id": stable_id("level", f, []), "floor": f, "name": "Kat {} (Scan)".format(f),
            "elevation_m": elev, "elevation_ft": elev * config.FT,
            "confidence": round(float(m.confidence), 3),
            "ceiling_m": None if m.ceiling_z is None else config.round_level(m.ceiling_z + offset),
            "evidence": {k: (float(v) if isinstance(v, (int, float)) else v)
                         for k, v in (m.evidence or {}).items()}})

    groups = Counter(w["thickness_group_cm"] for w in doc["walls"]
                     if w["thickness_group_cm"] is not None)
    doc["thickness_groups"] = [{"cm": cm, "count": n} for cm, n in sorted(groups.items())]

    _progress(88, "Onizlemeler ciziliyor")
    for f, (walls, ops, rooms_scan) in per_floor.items():
        png = preview.render_floor(f, walls, ops, rooms_scan,
                                   out_dir / "rolove_preview_kat{}.png".format(f))
        doc["previews"].append(str(png.resolve()))     # Revit sureci ayni cwd'de degil
    t = lap("previews", t)

    doc["stats"] = {
        "counts": {"floors": len(floors), "aligned_floors": len(per_floor),
                   "walls": len(doc["walls"]), "openings": len(doc["openings"]),
                   "rooms": len(doc["rooms"]), "rejected": len(doc["rejected"]),
                   "points": int(len(pts))},
        "status_counts": {
            "walls": dict(Counter(w["status"] for w in doc["walls"])),
            "wall_heights": dict(Counter(w["height_status"] for w in doc["walls"])),
            "opening_heights": dict(Counter(o["status"]["height"] for o in doc["openings"])),
        },
        "timings_s": timings,
    }
    timings["total"] = round(time.perf_counter() - t_all, 3)
    return doc, 0


def write_json(doc, out_dir):
    path = Path(out_dir) / "rolove_input.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False), "utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Polycam ciktilari -> Revit rolove girdisi")
    parser.add_argument("--input", type=Path, required=True, help="Kat plani .dxf ya da .zip")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--laz", type=Path)
    parser.add_argument("--glb", type=Path)
    args = parser.parse_args(argv)
    try:
        _progress(1, "Girdiler araniyor")
        found, missing = find_inputs(args.input, args.output_dir,
                                     {"csv": args.csv, "laz": args.laz, "glb": args.glb})
        doc, code = prepare(found, missing, args.output_dir)
        write_json(doc, args.output_dir)
        _progress(100, "Hazir" if code == 0 else "Eksik girdi")
        return code
    except Exception as exc:  # noqa: BLE001 - arayuze tek satir mesaj
        print("HATA: {}".format(exc), file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
