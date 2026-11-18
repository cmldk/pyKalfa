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


def plan_run(height_ft, scan_depth_ft, max_riser_ft, min_tread_ft):
    """{"risers", "tread_ft", "run_ft"}; tip sinirlari okunamadiysa (<= 0)
    19 cm riht / taranan derinlik (o da yoksa 28 cm) kullanilir."""
    max_riser = max_riser_ft if max_riser_ft and max_riser_ft > 0 else DEFAULT_MAX_RISER_FT
    risers = max(2, int(math.ceil(float(height_ft) / max_riser - 1e-9)))
    tread = max(float(scan_depth_ft or 0.0), float(min_tread_ft or 0.0))
    if tread <= 0:
        tread = DEFAULT_TREAD_FT
    return {"risers": risers, "tread_ft": tread, "run_ft": (risers - 1) * tread}
