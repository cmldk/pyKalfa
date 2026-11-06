"""
pyKalfa / Rolove - kat basina PNG onizleme (opencv)

Renkler (spec): `olculdu` yesil, `duzeltildi` turuncu, `varsayildi` kirmizi;
acikliklar mavi; odalar acik gri dolgu + ad. Dis duvarda kisa bir cizgi
`outward` yonunu gosterir.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

import geom2d
import openings as openings_mod

# BGR
STATUS_COLORS = {
    "olculdu": (40, 160, 40),
    "duzeltildi": (0, 140, 255),
    "varsayildi": (30, 30, 220),
}
OPENING_COLOR = (200, 90, 0)
ROOM_FILL = (238, 238, 238)
TEXT_COLOR = (90, 90, 90)
MAX_SIDE_PX = 1800
MARGIN_M = 0.6


def render_floor(floor, walls, openings, rooms, path) -> Path:
    """`walls`: RefinedWall, `openings`: OpeningOut, `rooms`: tarama
    cercevesinde DxfRoom. PNG'yi `path`'e yazar ve yolu dondurur."""
    pts = [p for w in walls for p in w.line] + [p for r in rooms for p in r.polygon]
    if not pts:
        pts = [(0.0, 0.0), (1.0, 1.0)]
    arr = np.asarray(pts, dtype=np.float64)
    lo = arr.min(axis=0) - MARGIN_M
    hi = arr.max(axis=0) + MARGIN_M
    scale = min(100.0, MAX_SIDE_PX / max(float((hi - lo).max()), 1e-6))
    width, height = (np.ceil((hi - lo) * scale)).astype(int) + 1
    img = np.full((height, width + 1, 3), 255, np.uint8)

    def px(p):
        return (int(round((p[0] - lo[0]) * scale)), int(round(height - 1 - (p[1] - lo[1]) * scale)))

    for r in rooms:
        poly = np.array([px(p) for p in r.polygon], dtype=np.int32)
        cv2.fillPoly(img, [poly], ROOM_FILL)
    for r in rooms:
        cv2.putText(img, r.name, px(openings_mod.label_point(r.polygon)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, TEXT_COLOR, 1, cv2.LINE_AA)

    stroke = max(2, int(round(0.06 * scale)))
    for w in walls:
        color = STATUS_COLORS.get(w.status, (0, 0, 0))
        cv2.line(img, px(w.line[0]), px(w.line[1]), color, stroke, cv2.LINE_AA)
        if w.outward is not None:
            (x1, y1), (x2, y2) = w.line
            mid = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            tip = (mid[0] + w.outward[0] * 0.25, mid[1] + w.outward[1] * 0.25)
            cv2.line(img, px(mid), px(tip), color, 1, cv2.LINE_AA)

    for o in openings:
        host = walls[o.host]
        ux, uy = geom2d.seg_dir(host.line)
        (sx, sy), _ = host.line
        a = (sx + ux * (o.offset - o.width / 2.0), sy + uy * (o.offset - o.width / 2.0))
        b = (sx + ux * (o.offset + o.width / 2.0), sy + uy * (o.offset + o.width / 2.0))
        cv2.line(img, px(a), px(b), OPENING_COLOR, stroke + 2, cv2.LINE_AA)

    cv2.putText(img, "Kat {}  yesil=olculdu  turuncu=duzeltildi  kirmizi=varsayildi  mavi=aciklik"
                .format(floor), (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG kodlanamadi: {}".format(path))
    path.write_bytes(buf.tobytes())        # cv2.imwrite Turkce/bosluklu yolda sessizce basarisiz olabilir
    return path
