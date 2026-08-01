"""
pyKalfa / Duvar - Revit icin hazir ara format

`dxf_reader` -> `geometry` -> `wall_detector` zincirini calistirip tek bir
`wall_input.json` uretir. Revit tarafi (IronPython) sadece bu JSON'i okur;
ezdxf/CPython'a hic dokunmaz.

Iki calisma modu var:

  - **Dis hat modu (varsayilan).** Kapali dis hat (outline) olarak
    cizilmis duvarlarin merkez ekseni ve KALINLIGI cizimden olculur.
    Gercek kat plani ciktilari (Polycam dahil) boyle cizer.
  - **Tek cizgi modu (`--lines`).** Dis hat bulunamayan nesnelerin
    cizgileri temizlenip (kaynatma, tekrar eleme, kolinear birlestirme,
    kisa parca filtresi) dogrudan duvar ekseni sayilir. Duvarlari tek
    cizgiyle cizilmis planlar icindir; acikca istenmedikce kapalidir,
    cunku mobilya/olculendirme cizgilerini de duvara cevirir.

Ciktidaki butun koordinatlar **feet** (Revit'in ic birimi) ve XY
duzlemindedir.

Kullanim:
    env/Scripts/python.exe pysrc/duvar/prepare_wall_input.py --dxf plan.dxf
    ... --units mm --lines --min-length 0.3 --recenter
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geometry
import wall_detector
from dxf_reader import insunits_name, read_dxf

# Revit, orijinden ~1.6 km'den (yaklasik 5000 ft) uzakta modellenen
# geometride hassasiyet uyarilari verir ve islemler kararsizlasir.
FAR_FROM_ORIGIN_FT = 5000.0


def prepare(
    dxf_path: Path,
    output_dir: Path,
    units: str = "auto",
    include_lines: bool = False,
    min_length_m: float = geometry.DEFAULT_MIN_LENGTH_M,
    merge_gap_m: float = geometry.DEFAULT_MERGE_GAP_M,
    snap_m: float = geometry.DEFAULT_SNAP_M,
    offset_tol_m: float = geometry.DEFAULT_OFFSET_TOL_M,
    angle_tol_deg: float = geometry.DEFAULT_ANGLE_TOL_DEG,
    recenter: bool = False,
) -> dict:
    read_result = read_dxf(dxf_path)

    unit = geometry.resolve_units(read_result.insunits, read_result.segments(), units)
    polys_ft = geometry.to_feet_polys(read_result.polys, unit)

    # 1) Dis hat olarak cizilmis duvarlar: merkez eksen + olculen kalinlik.
    walls, leftovers = wall_detector.detect_walls(polys_ft, geometry.FEET_PER_METER)

    # 2) Eslesmeyenler: istenirse temizlenip tek cizgi modunda eksen sayilir.
    line_stats = {}
    if include_lines:
        leftover_segments = []
        for poly in leftovers:
            leftover_segments.extend(poly.segments())
        cleaned, line_stats = geometry.clean_segments(
            leftover_segments,
            min_length_m=min_length_m,
            snap_m=snap_m,
            merge_gap_m=merge_gap_m,
            offset_tol_m=offset_tol_m,
            angle_tol_deg=angle_tol_deg,
        )
        walls = walls + wall_detector.walls_from_segments(cleaned)

    # 3) Orijine tasima (istege bagli).
    box = _walls_bbox(walls)
    offset = [0.0, 0.0]
    if box:
        center = [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]
        distance_from_origin = max(abs(center[0]), abs(center[1]))
        if recenter:
            offset = [-center[0], -center[1]]
            for wall in walls:
                wall.x1 += offset[0]
                wall.x2 += offset[0]
                wall.y1 += offset[1]
                wall.y2 += offset[1]
            box = _walls_bbox(walls)
    else:
        distance_from_origin = 0.0

    warnings = list(read_result.warnings)
    if not unit.confident:
        warnings.append(
            "DXF'te birim ($INSUNITS) belirtilmemis; cizim boyutundan '{}' tahmin "
            "edildi. Duvarlar yanlis olcekte cikarsa birimi elle secin.".format(unit.name)
        )
    outline_count = sum(1 for w in walls if w.source == "outline")
    if not walls:
        warnings.append(
            "Duvar bulunamadi. Bu cizimde duvarlar kapali dis hat olarak cizilmemis "
            "olabilir; tek cizgi modunu (--lines) deneyin."
        )
    elif outline_count == 0:
        warnings.append(
            "Hicbir kapali duvar dis hatti bulunamadi; butun adaylar tek cizgi "
            "modundan geliyor (kalinlik olculemedi)."
        )

    data = {
        "source": str(dxf_path),
        "dxf_version": read_result.dxf_version,
        "unit": {
            "name": unit.name,
            "meters_per_unit": unit.meters_per_unit,
            "source": unit.source,
            "confident": unit.confident,
            "insunits": read_result.insunits,
            "insunits_name": insunits_name(read_result.insunits),
        },
        "counts": {
            "objects_read": len(read_result.polys),
            "entities": read_result.entity_counts,
            "outline_walls": outline_count,
            "line_walls": len(walls) - outline_count,
            "unmatched_objects": len(leftovers),
            "line_mode": line_stats,
        },
        "ignored_entities": read_result.ignored_counts,
        "layers": wall_detector.summarize_by_layer(walls),
        "bbox_ft": list(box) if box else None,
        "recentered": recenter,
        "origin_offset_ft": offset,
        "far_from_origin": distance_from_origin > FAR_FROM_ORIGIN_FT,
        "distance_from_origin_ft": distance_from_origin,
        "total_length_ft": sum(w.length_ft for w in walls),
        "walls": [w.to_dict() for w in walls],
        "warnings": warnings,
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "wall_input.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(
        "Birim: {} ({}) | {} nesne -> {} dis hat duvari + {} tek cizgi | "
        "eslesmeyen {} | katman {} -> {}/wall_input.json".format(
            unit.name, unit.source, len(read_result.polys), outline_count,
            len(walls) - outline_count, len(leftovers), len(data["layers"]), output_dir,
        )
    )
    return data


def _walls_bbox(walls):
    if not walls:
        return None
    xs = [c for w in walls for c in (w.x1, w.x2)]
    ys = [c for w in walls for c in (w.y1, w.y2)]
    return (min(xs), min(ys), max(xs), max(ys))


def main() -> int:
    parser = argparse.ArgumentParser(description="Polycam/CAD DXF -> Revit duvar girdisi")
    parser.add_argument("--dxf", type=Path, required=True, help="Kaynak DXF dosyasi")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--units", default="auto", help="auto (DXF basligindan) veya mm/cm/dm/m/in/ft",
    )
    parser.add_argument(
        "--lines", action="store_true",
        help="Dis hat bulunamayan cizgileri de duvar ekseni say (tek cizgiyle "
             "cizilmis planlar icin; mobilya/olcu cizgilerini de duvara cevirir)",
    )
    parser.add_argument(
        "--min-length", type=float, default=geometry.DEFAULT_MIN_LENGTH_M,
        help="Metre; tek cizgi modunda bundan kisa parcalar atilir",
    )
    parser.add_argument(
        "--merge-gap", type=float, default=geometry.DEFAULT_MERGE_GAP_M,
        help="Metre; tek cizgi modunda ayni dogru uzerinde koprulenen bosluk",
    )
    parser.add_argument("--snap", type=float, default=geometry.DEFAULT_SNAP_M)
    parser.add_argument("--offset-tol", type=float, default=geometry.DEFAULT_OFFSET_TOL_M)
    parser.add_argument("--angle-tol", type=float, default=geometry.DEFAULT_ANGLE_TOL_DEG)
    parser.add_argument(
        "--recenter", action="store_true",
        help="Cizimi Revit orijinine tasi (uzak koordinatlarda hassasiyet sorunu icin)",
    )
    args = parser.parse_args()

    try:
        prepare(
            args.dxf,
            args.output_dir,
            units=args.units,
            include_lines=args.lines,
            min_length_m=args.min_length,
            merge_gap_m=args.merge_gap,
            snap_m=args.snap,
            offset_tol_m=args.offset_tol,
            angle_tol_deg=args.angle_tol,
            recenter=args.recenter,
        )
    except ValueError as exc:
        print("HATA: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
