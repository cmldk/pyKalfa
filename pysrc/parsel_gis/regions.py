"""Parsel-Bina GIS: bolgeler (Valonya + Flaman) tek arayuzde.

Kullanici bolge secmez: adres onerileri iki bolgeden ayni listede gelir,
her aday `region` tasir; CaPaKey once Valonya'da, bulunamazsa Flaman'da
aranir. Hazirlik secilen adayin bolgesiyle calisir.
"""

from __future__ import annotations

import flanders
import services
from gis_http import UpstreamError

REGIONS = {"wal": services, "vla": flanders}
ORDER = ("wal", "vla")
NAMES = {"wal": "Valonya", "vla": "Flaman"}
ATTRIBUTION = {
    "wal": "Plan parcellaire cadastral © AGDP/SPF Finances, via SPW ; Bâtiments, voirie © SPW (PICC_VDIFF)",
    "vla": "Adpf (administratieve percelen) © AAPD/FOD Financiën, via Digitaal Vlaanderen ; "
           "GRB (gebouwen, wegen) © Digitaal Vlaanderen",
}


def module(region):
    try:
        return REGIONS[region]
    except KeyError:
        raise ValueError("Bilinmeyen bolge: {!r} (wal / vla)".format(region))


def suggest_all(q):
    """Iki bolgenin adaylari (once Valonya). Bir bolge dusse digerininkiler
    yine doner; ikisi de duserse UpstreamError."""
    out, errors = [], []
    for region in ORDER:
        try:
            cands = module(region).suggest(q)
        except UpstreamError as ex:
            errors.append("{}: {}".format(NAMES[region], ex))
            continue
        for c in cands:
            c = dict(c)
            c["region"] = region
            out.append(c)
    if len(errors) == len(ORDER):
        raise UpstreamError("; ".join(errors))
    return out


def parcel_by_capakey_any(ck):
    """(bolge, parsel) ya da (None, None). Bir bolge servisi duserse digeri
    denenir; parsel bulunamaz ve en az bir servis dustuyse UpstreamError."""
    errors = []
    for region in ORDER:
        try:
            p = module(region).parcel_by_capakey(ck)
        except UpstreamError as ex:
            errors.append("{}: {}".format(NAMES[region], ex))
            continue
        if p:
            return region, p
    if errors:
        raise UpstreamError("; ".join(errors))
    return None, None
