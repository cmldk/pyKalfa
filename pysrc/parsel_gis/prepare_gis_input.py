"""Parsel-Bina GIS: parsel -> `revit_input.json` (+ dogrulama gorseli).

    prepare_gis_input.py --capakey 92053D0515/00B002 --margin 30 --output-dir output
    prepare_gis_input.py --x 210000 --y 120000 --margin 30 --output-dir output [--no-labels]

Cikti bicimi mevcut Parsel/Bina Aktar butonunun `revit_input.json`'u ile
aynidir (`parcel_lines`, `frame_lines`, `buildings`, `labels`, `north`),
boylece Revit tarafinda ayni cizim kodu kullanilir.

Arayuz icin `PROGRESS|yuzde|mesaj`, hata durumunda son satir
`ERROR|mesaj` basilir ve JSON yazilmaz.
Cikis kodlari: 0 basari, 2 servis hatasi, 3 parsel bulunamadi, 4 gecersiz girdi.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import layout
import preview
import services
from gis_http import UpstreamError

ATTRIBUTION = "Plan parcellaire cadastral © AGDP/SPF Finances, via SPW ; Bâtiments © SPW (PICC_VDIFF)"


class NotFound(Exception):
    pass


class BadInput(Exception):
    pass


def _progress(percent, message):
    print("PROGRESS|{}|{}".format(percent, message), flush=True)


def prepare(capakey, x, y, margin_m, output_dir, labels=True):
    if not (0 < margin_m <= layout.MAX_MARGIN_M):
        raise BadInput("Pay 0 ile {:.0f} m arasinda olmali (verilen: {})".format(layout.MAX_MARGIN_M, margin_m))
    output_dir = Path(output_dir)

    _progress(5, "Parsel araniyor")
    if capakey:
        try:
            selected = services.parcel_by_capakey(capakey)
        except ValueError as ex:
            raise BadInput(str(ex))
        if not selected:
            raise NotFound("CaPaKey {} plan parcellaire'de bulunamadi.".format(services.normalise_capakey(capakey)))
    elif x is not None and y is not None:
        selected = services.parcel_by_point(x, y, services.ADDRESS_SEARCH_M)
        if not selected:
            raise NotFound("Bu adreste {} m icinde kadastro parseli yok (kamusal alan veya Valonya disi?).".format(
                services.ADDRESS_SEARCH_M))
    else:
        raise BadInput("--capakey veya --x/--y gerekli")

    box = layout.frame_box(selected["rings"], margin_m)
    _progress(30, "Komsu parseller")
    parcels = services.parcels_in_box(box)
    if not any(p["capakey"] == selected["capakey"] for p in parcels):
        parcels.append(selected)
    _progress(60, "Binalar")
    buildings = services.buildings_in_box(box)

    _progress(85, "Geometri")
    parcel_lines = layout.parcel_segments(parcels, box)
    regions = layout.building_regions(buildings, box)
    label_records = layout.parcel_labels(parcels, box) if labels else []

    data = {
        "source": "GIS",
        "attribution": ATTRIBUTION,
        "margin_m": margin_m,
        "selected": {"capakey": selected["capakey"], "numero": services.parcel_numero(selected["attributes"])},
        "box_lambert72": [round(v, 3) for v in box],
        "origin_note": "vertices_ft/position_ft: X sagda artar, Y yukarida artar; orijin cercevenin sol-alt kosesidir.",
        "parcel_count": len(parcels),
        "building_count": len(regions),
        "label_count": len(label_records),
        "parcel_line_count": len(parcel_lines),
        "parcel_lines": parcel_lines,
        "frame_lines": layout.frame_lines(box),
        "north": layout.north_record(box),
        "buildings": regions,
        "labels": label_records,
    }

    _progress(95, "Onizleme")
    output_dir.mkdir(parents=True, exist_ok=True)
    preview.write(data, str(output_dir / "revit_input_preview.png"))
    with open(output_dir / "revit_input.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _progress(100, "Tamamlandi")
    print("Parsel {} ({}) | parsel: {} | cizgi: {} | bina: {} | etiket: {} -> {}".format(
        data["selected"]["numero"], selected["capakey"], len(parcels), len(parcel_lines),
        len(regions), len(label_records), output_dir / "revit_input.json"), flush=True)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="SPW verisinden Revit ara formati")
    parser.add_argument("--capakey")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--margin", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--labels", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    try:
        prepare(args.capakey, args.x, args.y, args.margin, args.output_dir, labels=args.labels)
    except UpstreamError as ex:
        print("ERROR|Servis hatasi: {}".format(ex), flush=True)
        return 2
    except NotFound as ex:
        print("ERROR|{}".format(ex), flush=True)
        return 3
    except BadInput as ex:
        print("ERROR|{}".format(ex), flush=True)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
