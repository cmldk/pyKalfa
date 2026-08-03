"""
pyKalfa / Parsel-Bina - Faz 3: pyRevit icin hazir ara format

geometry.py'den gelen temiz (tekil) parsel/bina konturlarini alir,
scale.py ile hesaplanan olcege gore gercek dunya birimine (feet, Revit'in
internal birimi) cevirir, piksel Y-eksenini (asagi artan) CAD/Revit
Y-eksenine (yukari artan) cevirir ve parsel-bina iliskisini (Faz 2 mantigi,
artik tekil/duplikasyonsuz konturlarla) yeniden hesaplayip tek bir JSON
dosyasinda toplar.

Not: parsel.png ve bina.png ayni kadastro kesitinin katmanlari oldugundan
(ayni piksel boyutu = ortak referans, bkz. Faz 2), olcek SADECE parsel
goruntusunden bir kez hesaplanip her iki katmana da uygulanir; her katman
icin ayri ayri cubuk tespiti yapmak, anti-alias kaynakli 1 piksellik
farklarla iki katman arasinda tutarsiz bir m/px oranina yol acar.

Kullanim:
    env/Scripts/python.exe pysrc/parsel_bina/prepare_revit_input.py --scale 1000
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from geometry import extract_buildings, extract_parcel_lines, extract_parcels
from map_decorations import detect_north_arrow
from regularize import snap_to_dominant_axes
from scale import compute_scale_info

SIMPLIFY_TOLERANCE_M = 0.4   # gercek dunyada ~40 cm; raster "merdiven" noktalarini sadelestirir
MIN_POINT_SPACING_M = 0.1    # bu mesafenin altindaki ardisik noktalar birlestirilir
                              # (Revit'te sifira yakin uzunlukta cizgi/loop segmenti
                              # olusmasin diye -- boylesi otomasyonlarda Revit'i
                              # kararsizlastirip cokertebiliyor)

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


def _centroid(contour: np.ndarray) -> tuple[float, float]:
    m = cv2.moments(contour)
    if m["m00"] != 0:
        return m["m10"] / m["m00"], m["m01"] / m["m00"]
    x, y, w, h = cv2.boundingRect(contour)
    return x + w / 2.0, y + h / 2.0


def _dedupe_close_points(points: list[list[float]], min_spacing: float) -> list[list[float]]:
    """Ardisik (ve kapanan) noktalar arasinda min_spacing'den kisa mesafe varsa birlestirir.

    Revit'te sifira yakin uzunlukta bir Line/CurveLoop segmenti olusturmak
    otomasyon senaryolarinda Revit'i kararsizlastirip cokertebiliyor; bu
    fonksiyon boyle noktalari kaynaktan (approxPolyDP sonrasi) temizler.
    """
    if len(points) < 2:
        return points
    result = [points[0]]
    for p in points[1:]:
        last = result[-1]
        if math.hypot(p[0] - last[0], p[1] - last[1]) >= min_spacing:
            result.append(p)
    # Kapanan loop'ta son nokta basa cok yakinsa son noktayi at
    if len(result) > 2 and math.hypot(result[-1][0] - result[0][0], result[-1][1] - result[0][1]) < min_spacing:
        result.pop()
    return result


def _to_real_world(
    contour: np.ndarray,
    meters_per_px: float,
    feet_per_px: float,
    image_height: int,
    square_up: bool = False,
) -> tuple[list[list[float]], float]:
    """Piksel konturunu sadelestirip gercek birime (ft) cevirir.

    `square_up=True` ise poligon ayrica kendi baskin izgarasina oturtulur
    (bkz. regularize.py). Bina siniri gercekte duz ve cogunlukla dik
    duvarlardan olusur; sadelestirme tek basina kenar acilarini bir-iki
    derece kaydirip koseleri pahladigi icin dortgenler yamuk gorunur.
    Parsel sinirlarina UYGULANMAZ: onlar dogal olarak egik ve dik acili
    olmayan cokgenlerdir.
    """
    epsilon_px = SIMPLIFY_TOLERANCE_M / meters_per_px
    simplified = cv2.approxPolyDP(contour, epsilon_px, True).reshape(-1, 2)
    points_px = (
        snap_to_dominant_axes(simplified.tolist(), max_shift=epsilon_px)
        if square_up
        else simplified
    )
    vertices_ft = [
        [round(px * feet_per_px, 3), round((image_height - py) * feet_per_px, 3)]
        for px, py in points_px
    ]
    vertices_ft = _dedupe_close_points(vertices_ft, MIN_POINT_SPACING_M)
    area_m2 = cv2.contourArea(contour) * (meters_per_px ** 2)
    return vertices_ft, round(area_m2, 2)


def _parcel_lines_to_real_world(
    polylines_px: list[list[tuple[int, int]]], meters_per_px: float, feet_per_px: float, image_height: int
) -> list[list[list[float]]]:
    """Iskelet-grafigi polyline'larini (piksel) sadelestirip gercek birime
    (ft) cevirir ve ardisik nokta ciftlerini DetailLine segmentleri olarak
    dondurur. Her fiziksel cizgi `extract_parcel_lines()` sayesinde zaten
    tam bir kez geldigi icin ekstra bir cift-cizgi birlestirmesine gerek
    yoktur (bkz. geometry.py modul docstring'i)."""
    segments: list[list[list[float]]] = []
    epsilon_px = SIMPLIFY_TOLERANCE_M / meters_per_px
    for polyline in polylines_px:
        contour = np.array(polyline, dtype=np.int32).reshape(-1, 1, 2)
        simplified = cv2.approxPolyDP(contour, epsilon_px, False).reshape(-1, 2)
        vertices_ft = [
            [round(px * feet_per_px, 3), round((image_height - py) * feet_per_px, 3)]
            for px, py in simplified
        ]
        vertices_ft = _dedupe_close_points(vertices_ft, MIN_POINT_SPACING_M)
        for i in range(len(vertices_ft) - 1):
            segments.append([vertices_ft[i], vertices_ft[i + 1]])
    return segments


def _image_frame_lines(width: int, height: int, feet_per_px: float) -> list[list[list[float]]]:
    """Goruntunun dis sinirini 4 segmentlik kapali bir dikdortgen olarak
    dondurur (parcel_lines ile ayni segment bicimi).

    Butun koordinatlar zaten bu goruntu cercevesine gore uretiliyor
    (orijin = goruntunun sol-alt kosesi), yani bu dikdortgen kadastro
    kesitinin tamamini -- goruntu kenarina degen parseller dahil -- tam
    olarak cevreler. Revit'te bu segmentler ayri bir line style ile
    cizilerek cizime bir pafta cercevesi verilir.
    """
    w = round(width * feet_per_px, 3)
    h = round(height * feet_per_px, 3)
    corners = [[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]]
    return [[corners[i], corners[(i + 1) % 4]] for i in range(4)]


def _labels_to_real_world(
    raw_labels: list[dict], meters_per_px: float, feet_per_px: float, image_height: int
) -> list[dict]:
    records = []
    for i, label in enumerate(raw_labels):
        cx, cy = label["center_px"]
        # Piksel Y-ekseni asagi artar; Y-flip sonrasi bir aci -theta'ya doner (aynali).
        rotation_deg = round(math.degrees(-label["angle_rad_px"]), 2)
        records.append(
            {
                "id": i,
                "text": label["text"],
                "confidence": label["confidence"],
                "position_ft": [
                    round(cx * feet_per_px, 3),
                    round((image_height - cy) * feet_per_px, 3),
                ],
                "rotation_deg": rotation_deg,
            }
        )
    return records


# Arayuzun ilerleme cubugu icin asama bildirimi. Ayristirilmasi kolay,
# insan tarafindan da okunabilir tek satirlik bir bicim kullanilir.
# `flush` sart: cikti bir boruya (pipe) yazildigi icin tamponlanir ve
# flush edilmezse butun satirlar islem bitince topluca gider -- yani
# ilerleme cubugu hic ilerlemez, sonunda bir anda dolardi.
def _progress(percent: int, message: str) -> None:
    print("PROGRESS|{}|{}".format(percent, message), flush=True)


def prepare(
    parsel_path: Path,
    bina_path: Path,
    scale_denominator: float,
    output_dir: Path,
    extract_labels: bool = True,
) -> None:
    _progress(5, "Ölçek çubuğu hesaplanıyor")
    scale_info = compute_scale_info(parsel_path, scale_denominator)
    meters_per_px = scale_info["meters_per_pixel"]
    feet_per_px = scale_info["feet_per_pixel"]

    _progress(15, "Parsel konturları cıkarılıyor")
    parcel_image, parcels = extract_parcels(parsel_path)
    _progress(30, "Bina konturları cıkarılıyor")
    building_image, buildings = extract_buildings(bina_path)
    if parcel_image.shape[:2] != building_image.shape[:2]:
        raise ValueError(
            f"Goruntu boyutlari eslesmiyor: parsel={parcel_image.shape[:2]} bina={building_image.shape[:2]}"
        )
    height, width = parcel_image.shape[:2]
    _progress(45, "Parsel-bina ilişkisi hesaplaniyor")
    parcels_by_area = sorted(parcels, key=cv2.contourArea)

    parcel_to_buildings: dict[int, list[int]] = {i: [] for i in range(len(parcels_by_area))}
    building_parcel_id: list[int | None] = []
    for b_contour in buildings:
        cx, cy = _centroid(b_contour)
        matched = None
        for p_idx, p_contour in enumerate(parcels_by_area):
            if cv2.pointPolygonTest(p_contour, (cx, cy), False) >= 0:
                matched = p_idx
                break
        building_parcel_id.append(matched)
        if matched is not None:
            parcel_to_buildings[matched].append(len(building_parcel_id) - 1)

    parcel_records = []
    for p_idx, p_contour in enumerate(parcels_by_area):
        vertices_ft, area_m2 = _to_real_world(p_contour, meters_per_px, feet_per_px, height)
        parcel_records.append(
            {
                "id": p_idx,
                "area_m2": area_m2,
                "vertices_ft": vertices_ft,
                "building_ids": parcel_to_buildings[p_idx],
            }
        )

    building_records = []
    for b_idx, b_contour in enumerate(buildings):
        vertices_ft, area_m2 = _to_real_world(
            b_contour, meters_per_px, feet_per_px, height, square_up=True
        )
        building_records.append(
            {
                "id": b_idx,
                "area_m2": area_m2,
                "vertices_ft": vertices_ft,
                "parcel_id": building_parcel_id[b_idx],
            }
        )

    _progress(55, "Parsel çizgileri izleniyor")
    _, raw_parcel_lines = extract_parcel_lines(parsel_path)
    parcel_lines = _parcel_lines_to_real_world(raw_parcel_lines, meters_per_px, feet_per_px, height)
    frame_lines = _image_frame_lines(width, height, feet_per_px)

    _progress(62, "Kuzey oku aranıyor")
    north = detect_north_arrow(parsel_path)
    north_record = None
    if north is not None:
        cx, cy = north["center_px"]
        north_record = {
            "position_ft": [
                round(cx * feet_per_px, 3),
                round((height - cy) * feet_per_px, 3),
            ],
            "rotation_deg": north["rotation_deg"],
        }

    label_records: list[dict] = []
    raw_labels: list[dict] = []
    label_warning = None
    if extract_labels:
        # En uzun suren adim: EasyOCR ilk calistirmada modelini de indirir.
        _progress(70, "Parsel numaralari okunuyor")
        try:
            from ocr_labels import extract_parcel_labels

            _, raw_labels = extract_parcel_labels(parsel_path)
            label_records = _labels_to_real_world(raw_labels, meters_per_px, feet_per_px, height)
        except Exception as ex:  # OCR (agir/internet gerektiren bagimlilik) basarisiz olsa bile
            label_warning = f"Etiket OCR'i basarisiz oldu, etiketsiz devam edildi: {ex}"
            print(f"UYARI: {label_warning}")

    _progress(92, "Sonuçlar yaziliyor")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "scale": scale_info,
        "image_size_px": {"width": width, "height": height},
        "origin_note": "vertices_ft/position_ft: X sagda artar, Y yukarida artar (piksel Y-ekseni ters cevrilmistir); orijin goruntunun sol-alt kosesidir.",
        "parcel_count": len(parcel_records),
        "building_count": len(building_records),
        "matched_building_count": sum(1 for b in building_records if b["parcel_id"] is not None),
        "parcel_line_count": len(parcel_lines),
        "parcel_lines_note": "DetailLine cizimi icin kullanilacak segment listesi; iskelet grafigi dogrudan izlenerek uretildigi icin her fiziksel cizgi (komsu parsellerin ortak siniri dahil) tam bir kez yer alir.",
        "parcel_lines": parcel_lines,
        "frame_lines_note": "Goruntunun dis sinirini olusturan 4 segment (kapali dikdortgen); Revit'te cizimi cerceveleyen ayri bir line style ile cizilir.",
        "frame_lines": frame_lines,
        "north_note": "Goruntudeki kuzey okunun konumu ve yonu; Revit'te secilen aciklama sembolu (annotation symbol) bu noktaya, yukari bakan bir sembolu ayni yone cevirecek 'rotation_deg' aci ile yerlestirilir. Ok bulunamazsa null.",
        "north": north_record,
        "label_count": len(label_records),
        "labels_note": "Parsel numara etiketleri (OCR ile okundu, ör. '591G'). 'confidence' (0-1) dusukse (<~0.5) okuma yanlis olabilir -- G/6, A/4, B/8, S/5 gibi benzer karakterler karisabiliyor. OCR basarisiz/atlandiysa bu liste bostur.",
        "labels": label_records,
        "label_warning": label_warning,
        "parcels": parcel_records,
        "buildings": building_records,
    }
    with open(output_dir / "revit_input.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # --- Gorsel dogrulama (fiilen Revit'e gidecek parcel_lines ile ayni kaynak) ---
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (width - 1, height - 1), FRAME_COLOR, LINE_THICKNESS)
    for polyline in raw_parcel_lines:
        pts = np.array(polyline, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [pts], False, PARCEL_COLOR, LINE_THICKNESS)
    overlay = canvas.copy()
    for b_idx, b_contour in enumerate(buildings):
        fill = MATCHED_FILL if building_parcel_id[b_idx] is not None else UNMATCHED_FILL
        cv2.drawContours(overlay, [b_contour], -1, fill, cv2.FILLED)
    canvas = cv2.addWeighted(overlay, FILL_ALPHA, canvas, 1 - FILL_ALPHA, 0)
    cv2.drawContours(canvas, buildings, -1, BUILDING_COLOR, LINE_THICKNESS)
    for i, label in enumerate(label_records):
        cx, cy = raw_labels[i]["center_px"]
        color = LABEL_HIGH_CONF_COLOR if label["confidence"] >= 0.5 else LABEL_LOW_CONF_COLOR
        cv2.putText(
            canvas, label["text"], (int(cx) - 15, int(cy)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA,
        )
    if north is not None:
        # Tespit edilen yon: dunya vektoru (-sin0, cos0) -> piksel uzayinda Y ters.
        angle = math.radians(north["rotation_deg"])
        cx, cy = north["center_px"]
        tip = (int(cx - math.sin(angle) * NORTH_MARKER_PX), int(cy - math.cos(angle) * NORTH_MARKER_PX))
        cv2.arrowedLine(canvas, (int(cx), int(cy)), tip, NORTH_COLOR, LINE_THICKNESS, tipLength=0.35)
    cv2.imwrite(str(output_dir / "revit_input_preview.png"), canvas)
    _progress(100, "Tamamlandi")

    matched = result["matched_building_count"]
    print(
        f"Olcek: {scale_info['scale_label']} ({meters_per_px:.5f} m/px) | "
        f"Parsel: {len(parcel_records)} | Bina: {len(building_records)} | "
        f"eslesen: {matched} | eslesmeyen: {len(building_records) - matched} | "
        f"etiket: {len(label_records)} "
        f"-> {output_dir}/revit_input.json"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="pyRevit icin gercek-birim ara format uretimi (Faz 3)")
    parser.add_argument("--scale", type=float, required=True, help="Harita olcegi paydasi, ör. 1000 (1:1000 icin)")
    parser.add_argument("--parsel", type=Path, default=Path("assets/parsel.png"))
    parser.add_argument("--bina", type=Path, default=Path("assets/bina.png"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--labels", action=argparse.BooleanOptionalAction, default=True,
        help="Parsel numara etiketlerini OCR ile oku (--no-labels ile kapatilabilir; agir/internet gerektirir)",
    )
    args = parser.parse_args()

    prepare(args.parsel, args.bina, args.scale, args.output_dir, extract_labels=args.labels)


if __name__ == "__main__":
    main()
