"""Parsel-Bina GIS: arama metni -> aday listesi (UTF-8 JSON dosyasi).

Sonuc stdout yerine dosyaya yazilir: Revit tarafi alt surec ciktisini
hangi kod sayfasiyla okursa okusun aksanli adresler bozulmasin.

    suggest_cli.py --query "Rue du Parc 4 Modave" --output output/gis_suggest.json

Metin CaPaKey kalibina uyuyorsa adres yerine parsel sorulur; bulunursa tek
aday (`precision: "capakey"`), bulunmazsa bos liste.
Cikis kodlari: 0 basari (bos liste dahil), 2 servis hatasi.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import services
from gis_http import UpstreamError


def candidates(query):
    if services.is_capakey(query):
        ck = services.normalise_capakey(query)
        p = services.parcel_by_capakey(ck)
        if not p:
            return []
        numero = services.parcel_numero(p["attributes"])
        return [{"label": "CaPaKey {} - parsel {}".format(ck, numero), "capakey": ck,
                 "numero": numero, "precision": "capakey"}]
    return services.suggest(query)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adres / CaPaKey aday listesi")
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cands = candidates(args.query.strip())
    except UpstreamError as ex:
        _write(args.output, {"query": args.query, "error": str(ex)})
        print("ERROR|{}".format(ex), flush=True)
        return 2
    _write(args.output, {"query": args.query, "candidates": cands})
    print("{} aday -> {}".format(len(cands), args.output), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
