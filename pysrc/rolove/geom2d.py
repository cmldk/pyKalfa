"""
pyKalfa / Rolove - kucuk 2B geometri yardimcilari (saf Python).
"""

from __future__ import annotations

import math


def point_in_polygon(pt, polygon) -> bool:
    """Isin atma (ray casting); kenar ustu belirsiz kabul edilir."""
    x, y = pt
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


def polygon_area(polygon) -> float:
    s = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def seg_length(seg) -> float:
    (x1, y1), (x2, y2) = seg
    return math.hypot(x2 - x1, y2 - y1)


def seg_dir(seg):
    (x1, y1), (x2, y2) = seg
    length = math.hypot(x2 - x1, y2 - y1)
    return ((x2 - x1) / length, (y2 - y1) / length)


def seg_normal(seg):
    """Yonun soluna bakan birim normal."""
    ux, uy = seg_dir(seg)
    return (-uy, ux)


def offset_seg(seg, d):
    """Segmenti sol normal yonunde `d` kadar oteler."""
    nx, ny = seg_normal(seg)
    (x1, y1), (x2, y2) = seg
    return ((x1 + nx * d, y1 + ny * d), (x2 + nx * d, y2 + ny * d))


def project(seg, pt):
    """(t_metre, dik_uzaklik_isaretli) — t baslangictan, isaret sol=+."""
    (x1, y1), _ = seg
    ux, uy = seg_dir(seg)
    dx, dy = pt[0] - x1, pt[1] - y1
    return dx * ux + dy * uy, -dx * uy + dy * ux
