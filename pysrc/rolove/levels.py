"""
pyKalfa / Rolove - kat doseme / tavan kotu olcumu

Her katin KENDI mesh'inden (GLB `Story` grubu) olculur: yukari bakan
yatay ucgenlerin alan agirlikli Z dagiliminda en buyuk tepe = doseme;
dosemenin en az `LEVEL_MIN_HEIGHT_M` ustundeki asagi bakan ucgenlerin en
buyuk tepesi = tavan. Masa/raf/basamak gibi yuzeyler kucuk alanlidir ve
secilmez. Kat sayisi veriden gelir; "3 kat" gibi bir beklenti dayatilmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import config


@dataclass
class LevelMeasure:
    floor: int
    story: int
    floor_z: float
    ceiling_z: float | None
    confidence: float
    evidence: dict = field(default_factory=dict)


def _peak(z, area, lo, hi):
    """(z, alan) — [lo, hi] araliginda alan agirlikli en buyuk tepe."""
    if len(z) == 0 or hi <= lo:
        return None, 0.0
    step = config.LEVEL_BIN_M
    edges = np.arange(lo, hi + step, step)
    hist, edges = np.histogram(z, bins=edges, weights=area)
    if not len(hist) or hist.max() <= 0:
        return None, 0.0
    k = int(np.argmax(hist))
    sel = (z >= edges[max(k - 1, 0)]) & (z <= edges[min(k + 2, len(edges) - 1)])
    zpk = float(np.average(z[sel], weights=area[sel]))
    return zpk, float(hist[max(k - 1, 0):k + 2].sum())


def measure_levels(tris: dict, bands: list, floors: list) -> list:
    bands = sorted(bands, key=lambda b: b.index)
    floors = sorted(floors)
    if len(bands) != len(floors):
        raise ValueError("DXF'te {} kat, GLB'de {} kat grubu var; eslestirilemedi."
                         .format(len(floors), len(bands)))
    out = []
    for floor, band in zip(floors, bands):
        z, area, nz = tris.get(band.index, (np.zeros(0), np.zeros(0), np.zeros(0)))
        up = nz > config.LEVEL_NORMAL_MIN
        down = nz < -config.LEVEL_NORMAL_MIN
        floor_z, floor_area = _peak(z[up], area[up], band.zmin, band.zmax)
        if floor_z is None:
            raise ValueError("Kat {} icin doseme yuzeyi bulunamadi.".format(floor))
        sel = down & (z > floor_z + config.LEVEL_MIN_HEIGHT_M)
        ceiling_z, ceiling_area = _peak(z[sel], area[sel], floor_z + config.LEVEL_MIN_HEIGHT_M,
                                        band.zmax)
        footprint = max((band.xmax - band.xmin) * (band.ymax - band.ymin), 1e-9)
        out.append(LevelMeasure(
            floor=floor, story=band.index, floor_z=floor_z, ceiling_z=ceiling_z,
            confidence=float(min(1.0, floor_area / footprint)),
            evidence={"floor_area_m2": round(floor_area, 2),
                      "ceiling_area_m2": round(ceiling_area, 2),
                      "triangles": int(len(z))},
        ))
    return out
