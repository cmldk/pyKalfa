"""
pyKalfa / Parsel-Bina - gorsel dogrulama ciktisi

`revit_input.json`a giden verinin AYNISINI bir PNG uzerine cizer: Revit'i
acmadan once "bu cizim dogru mu" sorusuna bakarak cevap verilebilsin diye.
Onizleme bilerek JSON'la ayni kaynaklardan beslenir (ayni konturlar, ayni
eslesme) -- ayri bir yoldan yeniden hesaplanan bir onizleme, ciktiyla
uyusmadigi anda yaniltici olurdu.

Renk anlamlari:
    turuncu       parsel cizgileri (fiilen DetailLine olacak segmentler)
    gri           goruntu cercevesi
    yesil dolgu   parseliyle eslesmis bina blogu
    kirmizi dolgu hicbir parsele dusmeyen bina blogu
    mor/siyah     OCR etiketi (siyah = dusuk guven, supheli okuma)
"""

from __future__ import annotations

import math

import cv2
import numpy as np

FRAME_COLOR = (120, 120, 120)    # BGR - gri
NORTH_COLOR = (110, 60, 20)      # BGR - lacivert (kaynak goruntudeki kuzey oku rengi)
NORTH_MARKER_PX = 45             # onizlemede kuzey yonu okunun uzunlugu
PARCEL_COLOR = (0, 140, 255)     # BGR - turuncu
BUILDING_COLOR = (255, 120, 0)   # BGR - mavi
MATCHED_FILL = (0, 200, 0)
UNMATCHED_FILL = (0, 0, 220)
FILL_ALPHA = 0.35
LINE_THICKNESS = 2
LABEL_HIGH_CONF_COLOR = (120, 0, 120)   # BGR - mor (guven >= 0.5)
LABEL_LOW_CONF_COLOR = (0, 0, 0)        # BGR - siyah (guven < 0.5, supheli okuma)
LABEL_CONFIDENCE_SPLIT = 0.5
WARNING_COLOR = (0, 0, 200)


def _as_int_contours(contours: list[np.ndarray]) -> list[np.ndarray]:
    """Alt-piksel konturlari cizim icin yuvarlar.

    Kirpma degil YUVARLAMA: yarim piksellik sistematik bir kayma
    onizlemede gozle gorunur hale gelebiliyor."""
    return [np.round(c).astype(np.int32) for c in contours]


def render(
    width: int,
    height: int,
    parcel_lines_px: list[list[tuple[float, float]]],
    buildings_px: list[np.ndarray],
    building_parcel_id: list[int | None],
    labels_px: list[dict],
    north: dict | None = None,
    warning: str | None = None,
) -> np.ndarray:
    """Dogrulama gorselini uretir (BGR). Butun koordinatlar PARSEL karesinde
    ve piksel biriminde beklenir -- yani binalar hizalama kaymasi
    uygulandiktan sonraki halleriyle verilmelidir."""
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (width - 1, height - 1), FRAME_COLOR, LINE_THICKNESS)

    for polyline in parcel_lines_px:
        points = np.round(np.array(polyline, dtype=np.float64)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [points], False, PARCEL_COLOR, LINE_THICKNESS)

    contours = _as_int_contours(buildings_px)
    overlay = canvas.copy()
    for index, contour in enumerate(contours):
        matched = index < len(building_parcel_id) and building_parcel_id[index] is not None
        cv2.drawContours(overlay, [contour], -1, MATCHED_FILL if matched else UNMATCHED_FILL, cv2.FILLED)
    canvas = cv2.addWeighted(overlay, FILL_ALPHA, canvas, 1 - FILL_ALPHA, 0)
    cv2.drawContours(canvas, contours, -1, BUILDING_COLOR, LINE_THICKNESS)

    for label in labels_px:
        cx, cy = label["center_px"]
        color = (
            LABEL_HIGH_CONF_COLOR
            if float(label.get("confidence") or 0.0) >= LABEL_CONFIDENCE_SPLIT
            else LABEL_LOW_CONF_COLOR
        )
        cv2.putText(canvas, label.get("text") or "", (int(cx) - 15, int(cy)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)

    if north is not None:
        # Tespit edilen yon: dunya vektoru (-sin0, cos0) -> piksel uzayinda Y ters.
        angle = math.radians(north["rotation_deg"])
        cx, cy = north["center_px"]
        tip = (int(cx - math.sin(angle) * NORTH_MARKER_PX), int(cy - math.cos(angle) * NORTH_MARKER_PX))
        cv2.arrowedLine(canvas, (int(cx), int(cy)), tip, NORTH_COLOR, LINE_THICKNESS, tipLength=0.35)

    if warning:
        # Hizalama uyarisi onizlemenin UZERINE yazilir: bu gorseli acan
        # kisi uyariyi konsol ciktisinda aramak zorunda kalmasin.
        cv2.putText(canvas, "UYARI: hizalama dogrulanamadi", (12, height - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, WARNING_COLOR, 1, cv2.LINE_AA)
    return canvas
