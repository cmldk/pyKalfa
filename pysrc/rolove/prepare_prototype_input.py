"""
pyKalfa / Rolove Prototip - Polycam ciktilari -> `prototip_input.json` (+ kat PNG'leri)

    prepare_prototype_input.py --input "<ad>.dxf | <kat plani>.zip" --output-dir output
                               [--csv P --laz P --glb P]

Rolove Aktar'in hazirligi (`prepare_rolove_input.prepare`) aynen calisir,
sonra `prototype.tidy` ile toparlanir. Arguman, `PROGRESS|yuzde|mesaj`
satirlari ve cikis kodlari Rolove Aktar ile ayni: 0 basari; 2 eksik girdi
(JSON yine yazilir, `missing` dolu, toparlama yapilmaz); 1 hata.
Rolove'nin kendi PNG'leri silinir, yerine `prototip_preview_kat<N>.png`.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _extra in (HERE, HERE.parent / "duvar"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import prepare_rolove_input as pri  # noqa: E402

JSON_NAME = "prototip_input.json"
_orig_progress = pri._progress


def _scaled_progress(percent, message):
    _orig_progress(int(percent) * 90 // 100, message)


def build(found, missing, out_dir: Path):
    """(json sozlugu, cikis kodu)."""
    import prototype

    pri._progress = _scaled_progress
    try:
        doc, code = pri.prepare(found, missing, out_dir)
    finally:
        pri._progress = _orig_progress
    if code != 0:
        return doc, code
    _orig_progress(92, "Prototip toparlaniyor")
    prototype.tidy(doc)
    _orig_progress(94, "Merdivenler")
    doc["stairs"] = _find_stairs(doc, found)
    doc["prototype"]["stairs"] = len(doc["stairs"])
    _orig_progress(96, "Prototip onizlemeleri")
    for p in doc.get("previews") or []:
        try:
            Path(p).unlink()
        except OSError:
            pass
    doc["previews"] = []
    for f in sorted({lv["floor"] for lv in doc.get("levels") or []}):
        png = prototype.render_floor(doc, f, Path(out_dir) / "prototip_preview_kat{}.png".format(f))
        doc["previews"].append(str(png.resolve()))
    return doc, 0


def _find_stairs(doc, found):
    """Merdiven istege bagli: bir sey ters giderse uyari + bos liste.
    Yon icin nokta bulutu yeniden okunur (rolove hazirligi onu dondurmuyor)."""
    import stairs
    points = None
    try:
        import cloud
        points = cloud.load_laz(found["laz"])
    except Exception as ex:  # noqa: BLE001
        doc.setdefault("warnings", []).append("Merdiven yonu icin nokta bulutu okunamadi: {}".format(ex))
    try:
        return stairs.find_stairs(doc, found["dxf"], points)
    except Exception as ex:  # noqa: BLE001
        doc.setdefault("warnings", []).append("Merdivenler bulunamadi: {}".format(ex))
        return []


def write_json(doc, out_dir):
    path = Path(out_dir) / JSON_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False), "utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Polycam ciktilari -> Revit rolove prototipi")
    parser.add_argument("--input", type=Path, required=True, help="Kat plani .dxf ya da .zip")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--laz", type=Path)
    parser.add_argument("--glb", type=Path)
    args = parser.parse_args(argv)
    try:
        _orig_progress(1, "Girdiler araniyor")
        found, missing = pri.find_inputs(args.input, args.output_dir,
                                         {"csv": args.csv, "laz": args.laz, "glb": args.glb})
        doc, code = build(found, missing, args.output_dir)
        write_json(doc, args.output_dir)
        _orig_progress(100, "Hazir" if code == 0 else "Eksik girdi")
        return code
    except Exception as exc:  # noqa: BLE001 - arayuze tek satir mesaj
        print("HATA: {}".format(exc), file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
