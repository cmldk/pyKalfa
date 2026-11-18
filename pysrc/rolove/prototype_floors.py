"""
pyKalfa / Rolove Prototip - doseme hatlari (tip secimlerinden sonra).

    prototype_floors.py --json output/prototip_input.json
                        --exterior-thickness-m 0.30 --output output/prototip_floors.json

Cikti: {"floors": [{id, floor, loops_ft, area_m2}], "warnings": [...]}
Cikis kodlari: 0 basari; 1 hata (mesaj stderr'de, "HATA:" ile).
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rolove Prototip doseme hatlari")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--exterior-thickness-m", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        import prototype
        doc = json.loads(args.json.read_text("utf-8"))
        warnings = []
        floors = prototype.floor_loops(doc, args.exterior_thickness_m, warnings)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"floors": floors, "warnings": warnings},
                                          ensure_ascii=False, allow_nan=False), "utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 - arayuze tek satir mesaj
        print("HATA: {}".format(exc), file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
