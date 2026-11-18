# -*- coding: utf-8 -*-
"""Merdiven kolu hesabi (saf Python; IronPython 2.7 + CPython 3).

Kullanici: merdiven yarida kesilmesin, alt kattan ust kata ulassin. Riht
sayisi kat yuksekliginden ve SECILEN merdiven tipinin en yuksek rihtinden
hesaplanir; basamak derinligi taranan derinlik, tipin alt sinirindan
kucukse tipinki. Kol uzunlugu = (riht - 1) x basamak; taramadaki kolu
gerekirse uzatir (cagiran raporlar).
"""

import math

FT_PER_M = 1.0 / 0.3048
DEFAULT_MAX_RISER_FT = 0.19 * FT_PER_M
DEFAULT_TREAD_FT = 0.28 * FT_PER_M


def riser_ft(height_ft, risers):
    return float(height_ft) / risers


def place_run(scan_run_ft, run_ft, fwd_free_ft, back_free_ft):
    """(geri, ileri) uzatma. Eksik kol once ust uctan ileri, bina icindeki
    bos yer kadar; kalan alt uctan geri, o da bos yer kadar; hala kalan
    varsa yine ileri (kat yuksekligine ulasmak oncelikli). Bos yer bilinmiyorsa
    (None) her sey ileri."""
    extra = max(0.0, float(run_ft) - float(scan_run_ft))
    if extra <= 0:
        return (0.0, 0.0)
    if fwd_free_ft is None or back_free_ft is None:
        return (0.0, extra)
    fwd = min(extra, max(0.0, float(fwd_free_ft)))
    back = min(extra - fwd, max(0.0, float(back_free_ft)))
    return (back, extra - back)


def plan_run(height_ft, scan_depth_ft, max_riser_ft, min_tread_ft):
    """{"risers", "tread_ft", "run_ft"}; tip sinirlari okunamadiysa (<= 0)
    19 cm riht / taranan derinlik (o da yoksa 28 cm) kullanilir."""
    max_riser = max_riser_ft if max_riser_ft and max_riser_ft > 0 else DEFAULT_MAX_RISER_FT
    risers = max(2, int(math.ceil(float(height_ft) / max_riser - 1e-9)))
    tread = max(float(scan_depth_ft or 0.0), float(min_tread_ft or 0.0))
    if tread <= 0:
        tread = DEFAULT_TREAD_FT
    return {"risers": risers, "tread_ft": tread, "run_ft": (risers - 1) * tread}
