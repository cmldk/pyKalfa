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


# --------------------------------------------------------------------------
# Donen merdiven (ceyrek donus, yelpaze basamak)
# --------------------------------------------------------------------------

def split_treads(total_treads, winders, scan1, scan2, tread, free1, free2):
    """(donusten once kol basamak, donusten sonra kol basamak). Duz basamak
    ihtiyaci = toplam - yelpaze. ANA kol (taranan basamagi cok olan) fazlaysa
    kisalir; eksikse once ana kolun dis ucuna (bos yer kadar), sonra diger
    kolun dis ucuna (bos yer kadar), kalan yine ana kola eklenir. `free1`:
    1. kolun basindan geriye, `free2`: 2. kolun sonundan ileriye bos yer
    (None = bilinmiyor -> hepsi ana kola)."""
    rest = int(total_treads) - int(winders)
    n1, n2 = int(scan1), int(scan2)
    main_first = n1 >= n2
    if rest <= n1 + n2:
        if main_first:
            n2 = min(n2, max(0, rest))
            return (max(0, rest - n2), n2)
        n1 = min(n1, max(0, rest))
        return (n1, max(0, rest - n1))
    extra = rest - n1 - n2
    if free1 is None or free2 is None:
        return (n1 + extra, n2) if main_first else (n1, n2 + extra)
    order = [(0, free1), (1, free2)] if main_first else [(1, free2), (0, free1)]
    counts = [n1, n2]
    for idx, free in order:
        add = min(extra, int(math.floor(float(free) / tread + 1e-9)))
        counts[idx] += add
        extra -= add
    counts[order[0][0]] += extra
    return (counts[0], counts[1])


def _add(p, v, k):
    return (p[0] + v[0] * k, p[1] + v[1] * k)


def winder_layout(corner, u1, u2, width, n_run1, n_winders, n_run2, tread):
    """Ceyrek donuslu tek kol (Revit `StairsRun.CreateSketchedRun` icin), 2B.

    `corner`: donus karesinin merkezi; `u1`: alt kolun cikis yonu; `u2`:
    donusten sonraki yon (u1'e dik); kare kenari `width`. Yelpaze rihtleri
    ic kosedeki tek noktadan (pivot) dis kenarlara acilir.
    {"inner": [nokta], "outer": [nokta], "risers": [(ic, dis)], "path": [nokta]}"""
    w = float(width)
    L1, L2 = n_run1 * tread, n_run2 * tread
    pivot = _add(_add(corner, u1, -w / 2.0), u2, w / 2.0)
    entry_far = _add(pivot, u2, -w)
    exit_far = _add(pivot, u1, w)
    outer_corner = _add(entry_far, u1, w)

    inner = [_add(pivot, u1, -L1), pivot]
    outer = [_add(entry_far, u1, -L1), entry_far, outer_corner, exit_far]
    if L2 > 0:
        inner.append(_add(pivot, u2, L2))
        outer.append(_add(exit_far, u2, L2))
    if L1 <= 0:
        inner, outer = inner[1:], outer[1:]

    risers = []
    for k in range(n_run1 + 1):
        back = L1 - k * tread
        risers.append((_add(pivot, u1, -back), _add(entry_far, u1, -back)))
    e1 = (-u2[0], -u2[1])
    for j in range(1, n_winders):
        phi = math.radians(90.0 * j / n_winders)
        if phi <= math.pi / 4:
            cx, cy = 1.0, math.tan(phi)
        else:
            cx, cy = 1.0 / math.tan(phi), 1.0
        risers.append((pivot, _add(_add(pivot, e1, w * cx), u1, w * cy)))
    risers.append((pivot, exit_far))
    for k in range(1, n_run2 + 1):
        risers.append((_add(pivot, u2, k * tread), _add(exit_far, u2, k * tread)))

    m1 = _add(corner, u1, -w / 2.0)
    m2 = _add(corner, u2, w / 2.0)
    path = ([_add(m1, u1, -L1)] if L1 > 0 else []) + [m1, tuple(corner), m2]
    if L2 > 0:
        path.append(_add(m2, u2, L2))
    return {"inner": inner, "outer": outer, "risers": risers, "path": path, "pivot": pivot}
