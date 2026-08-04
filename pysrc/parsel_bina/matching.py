"""
pyKalfa / Parsel-Bina - parsel-bina-etiket eslesmesi

Uc katman ayri kaynaklardan gelir ama tek bir soruda bulusur: "bu bina
hangi parselde, o parselin numarasi ne?" Bu modul o eslesmeyi yapar --
saf geometri, dosya/goruntu bilmez.

Girdi konturlarinin AYNI piksel karesinde olmasi cagiranin sorumlulugudur;
bina konturlari parsel karesine `align.shift_contours` ile tasinir (bkz.
align.py: kayma `both.png` uzerinden olculur). Bu modulun bir varsayimi
sessizce dogrulamasi mumkun degildir, cunku kaymis bir eslesme de gecerli
gorunur -- bu yuzden hizalama ayri bir katmanda, dogrulamasiyla birlikte
yapilir.

Eslesme kurali: bir noktayi (bina agirlik merkezi ya da etiket merkezi)
ICEREN EN KUCUK parsel hucresi. "En kucuk" olcutu, ic ice gecen hucrelerde
(ör. bir parsel + onu da kapsayan sokak/ada hucresi) en spesifik olani
secer.
"""

from __future__ import annotations

import cv2
import numpy as np


def centroid(contour: np.ndarray) -> tuple[float, float]:
    """Konturun agirlik merkezi; dejenere (sifir alanli) konturda bbox ortasi."""
    moments = cv2.moments(contour.astype(np.float32))
    if moments["m00"] != 0:
        return moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]
    x, y, w, h = cv2.boundingRect(np.round(contour).astype(np.int32))
    return x + w / 2.0, y + h / 2.0


def order_by_area(cells: list[np.ndarray]) -> list[np.ndarray]:
    """Hucreleri alana gore kucukten buyuge sirala (en spesifik once)."""
    return sorted(cells, key=lambda c: cv2.contourArea(c.astype(np.float32)))


def containing_cell(point: tuple[float, float], cells_by_area: list[np.ndarray]) -> int | None:
    """Noktayi iceren en kucuk hucrenin indeksi; hicbiri icermiyorsa None.

    `cells_by_area` `order_by_area`dan gecmis olmalidir."""
    for index, cell in enumerate(cells_by_area):
        if cv2.pointPolygonTest(cell.astype(np.float32), (float(point[0]), float(point[1])), False) >= 0:
            return index
    return None


def match_buildings(
    buildings: list[np.ndarray], cells_by_area: list[np.ndarray]
) -> tuple[list[int | None], dict[int, list[int]]]:
    """Her binayi bir parsel hucresine baglar.

    Doner: `(bina_basina_parsel_id, parsel_id -> bina_id listesi)`.
    Hicbir hucreye dusmeyen bina (ör. goruntu kenarindaki kirpik parsel)
    `None` alir ve hicbir listede yer almaz -- sessizce en yakina
    yapistirilmaz, cunku yanlis parsele baglanmis bir bina ciktida hata
    gibi gorunmez."""
    building_parcel: list[int | None] = []
    parcel_buildings: dict[int, list[int]] = {i: [] for i in range(len(cells_by_area))}

    for building_id, contour in enumerate(buildings):
        parcel_id = containing_cell(centroid(contour), cells_by_area)
        building_parcel.append(parcel_id)
        if parcel_id is not None:
            parcel_buildings[parcel_id].append(building_id)
    return building_parcel, parcel_buildings


def match_labels(
    label_centers_px: list[tuple[float, float]], cells_by_area: list[np.ndarray]
) -> list[int | None]:
    """Her parsel numara etiketini iceren hucreyi bulur (etiket -> parsel).

    Etiket kendi parselinin ICINE yazildigi icin nokta-icinde testi
    dogrudan calisir. Sokak/bos alan hucreleri hicbir etiket almaz, bu da
    onlari ciktida gercek parsellerden ayirt etmeyi saglar."""
    return [containing_cell(center, cells_by_area) for center in label_centers_px]


def invert_label_match(
    label_parcel: list[int | None], labels: list[dict], cell_count: int
) -> list[str | None]:
    """`parsel_id -> etiket metni` tablosu (en yuksek guvenli okuma kazanir).

    Bir hucreye birden fazla okuma dusebilir: OCR bir etiketi ikiye bolmus
    ya da komsu bir yaziyi hucrenin icinde saymis olabilir. Guven skoru en
    yuksek olani secmek, bolunmus/supheli okumalari bastirir."""
    best: list[tuple[float, str] | None] = [None] * cell_count
    for label, parcel_id in zip(labels, label_parcel):
        if parcel_id is None:
            continue
        confidence = float(label.get("confidence") or 0.0)
        if best[parcel_id] is None or confidence > best[parcel_id][0]:
            best[parcel_id] = (confidence, label.get("text") or "")
    return [None if item is None else item[1] for item in best]
