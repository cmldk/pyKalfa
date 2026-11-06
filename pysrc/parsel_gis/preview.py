"""Parsel-Bina GIS: dogrulama gorseli (`revit_input_preview.png`).

Girdi DEGILDIR; yalniz Revit'e bakmadan "dogru yer mi geldi" kontrolu
icindir. Renkler mevcut `pysrc/parsel_bina/preview.py` ile aynidir.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

FRAME_COLOR = (120, 120, 120)    # BGR - gri
NORTH_COLOR = (110, 60, 20)      # BGR - lacivert
NORTH_MARKER_PX = 45
PARCEL_COLOR = (0, 140, 255)     # BGR - turuncu
BUILDING_COLOR = (255, 120, 0)   # BGR - mavi
BUILDING_FILL = (0, 200, 0)
FILL_ALPHA = 0.35
LINE_THICKNESS = 2
LABEL_COLOR = (120, 0, 120)      # BGR - mor
PX_PER_M = 8.0
MAX_SIDE_PX = 2000


def render(data):
    """`revit_input.json` sozlugunden BGR gorsel."""
    corners = [p for s in data["frame_lines"] for p in s]
    w_ft = max(p[0] for p in corners)
    h_ft = max(p[1] for p in corners)
    scale = PX_PER_M * 0.3048  # px / ft
    longest = max(w_ft, h_ft) * scale
    if longest > MAX_SIDE_PX:
        scale *= MAX_SIDE_PX / longest
    width = max(1, int(math.ceil(w_ft * scale)) + 1)
    height = max(1, int(math.ceil(h_ft * scale)) + 1)

    def px(p):
        return (int(round(p[0] * scale)), int(round(height - 1 - p[1] * scale)))

    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (width - 1, height - 1), FRAME_COLOR, LINE_THICKNESS)

    overlay = canvas.copy()
    contours = [np.array([px(v) for v in b["vertices_ft"]], dtype=np.int32).reshape(-1, 1, 2)
                for b in data.get("buildings") or []]
    for c in contours:
        cv2.drawContours(overlay, [c], -1, BUILDING_FILL, cv2.FILLED)
    canvas = cv2.addWeighted(overlay, FILL_ALPHA, canvas, 1 - FILL_ALPHA, 0)
    cv2.drawContours(canvas, contours, -1, BUILDING_COLOR, LINE_THICKNESS)

    for p1, p2 in data.get("parcel_lines") or []:
        cv2.line(canvas, px(p1), px(p2), PARCEL_COLOR, LINE_THICKNESS)

    for label in data.get("labels") or []:
        x, y = px(label["position_ft"])
        cv2.putText(canvas, label.get("text") or "", (x - 15, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, LABEL_COLOR, 1, cv2.LINE_AA)

    north = data.get("north")
    if north:
        x, y = px(north["position_ft"])
        cv2.arrowedLine(canvas, (x, y + NORTH_MARKER_PX // 2), (x, y - NORTH_MARKER_PX // 2),
                        NORTH_COLOR, LINE_THICKNESS, tipLength=0.35)
    return canvas


def write(data, path):
    ok, buf = cv2.imencode(".png", render(data))
    if ok:
        # cv2.imwrite Windows'ta ASCII disi yollarda sessizce basarisiz olabiliyor
        with open(path, "wb") as f:
            f.write(buf.tobytes())
    return ok
