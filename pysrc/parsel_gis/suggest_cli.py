"""Parsel-Bina GIS: arama metni -> aday listesi (UTF-8 JSON dosyasi).

Sonuc stdout yerine dosyaya yazilir: Revit tarafi alt surec ciktisini
hangi kod sayfasiyla okursa okusun aksanli adresler bozulmasin.

    suggest_cli.py --query "Rue du Parc 4 Modave" --output output/gis_suggest.json

Metin CaPaKey kalibina uyuyorsa adres yerine parsel sorulur; bulunursa tek
aday (`precision: "capakey"`), bulunmazsa bos liste. `--x/--y` ile secilen
adres noktasinin 20 m icindeki parseli ayni bicimde dondurulur.
Cikis kodlari: 0 basari (bos liste dahil), 2 servis hatasi.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import services
from gis_http import UpstreamError


def _parcel_candidate(p):
    numero = services.parcel_numero(p["attributes"])
    return {"label": "CaPaKey {} - parsel {}".format(p["capakey"], numero), "capakey": p["capakey"],
            "numero": numero, "precision": "capakey"}


def resolve_point(x, y):
    """Secilen adres noktasinin 20 m icindeki parseli (stil secimlerinden ONCE)."""
    p = services.parcel_by_point(x, y, services.ADDRESS_SEARCH_M)
    return [_parcel_candidate(p)] if p else []


def candidates(query):
    if services.is_capakey(query):
        ck = services.normalise_capakey(query)
        p = services.parcel_by_capakey(ck)
        return [_parcel_candidate(p)] if p else []
    return services.suggest(query)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adres / CaPaKey aday listesi")
    parser.add_argument("--query")
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.query is None and (args.x is None or args.y is None):
        parser.error("--query veya --x/--y gerekli")
    try:
        if args.query is not None:
            cands = candidates(args.query.strip())
        else:
            cands = resolve_point(args.x, args.y)
    except UpstreamError as ex:
        _write(args.output, {"query": args.query, "error": str(ex)})
        print("ERROR|{}".format(ex), flush=True)
        return 2
    _write(args.output, {"query": args.query, "candidates": cands})
    print("{} aday -> {}".format(len(cands), args.output), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
