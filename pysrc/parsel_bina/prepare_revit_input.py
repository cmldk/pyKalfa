"""
pyKalfa / Parsel-Bina - pyRevit icin hazir ara format

Uc gorseli alir, katman katman geometriye cevirir ve tek bir JSON'da
toplar. Girdilerin is bolumu:

    bina.png    -> bina birimleri (FilledRegion)
    parsel.png  -> parsel cizgileri (DetailLine), parsel hucreleri,
                   numara etiketleri (OCR), olcek cubugu, kuzey oku, cerceve
    both.png    -> YALNIZ hizalama referansi (bkz. align.py)

`both.png`'den hic geometri okunmaz: iki katman ust uste cizildigi icin
orada bina cizgilerinin govdesi parsel cizgileri ve etiketlerle delinir,
binalarin altinda kalan parsel cizgileri de gorunmez. Gorevi tek: iki
kaynagin birbirine gore kaymasini olcmek, boylece parsel-bina eslesmesi
"iki gorsel zaten hizalidir" varsayimina dayanmasin.

Cikti karesi `parsel.png`'dir: butun koordinatlar onun piksel karesinde
uretilir, bina konturlari oraya olculen kaymayla tasinir. Olcek de tek bir
goruntuden (parsel.png) bir kez hesaplanip her katmana uygulanir.

Kullanim:
    env/Scripts/python.exe pysrc/parsel_bina/prepare_revit_input.py --scale 500
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from align import layer_offset, shift_contours
from geometry import extract_buildings, extract_parcel_cells, extract_parcel_lines
from imaging import layer_masks
from map_decorations import detect_north_arrow
from matching import invert_label_match, match_buildings, match_labels, order_by_area
from preview import render as render_preview
from regularize import snap_to_dominant_axes
from scale import compute_scale_info

SIMPLIFY_TOLERANCE_M = 0.3   # gercek dunyada 30 cm; raster "merdiven" noktalarini sadelestirir
                              # (0.4'ten dusuruldu: poligonlar cizgiye daha yakin oturuyor.
                              #  Daha da dusurmek ters teper -- merdiven basamaklari kisa ve
                              #  egik kenarlar olarak hayatta kalip izgaraya oturmayi bozar.)
MIN_POINT_SPACING_M = 0.1    # bu mesafenin altindaki ardisik noktalar birlestirilir
                              # (Revit'te sifira yakin uzunlukta cizgi/loop segmenti
                              # olusmasin diye -- boylesi otomasyonlarda Revit'i
                              # kararsizlastirip cokertebiliyor)


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

    Konturlar alt-piksel (float32) geldigi icin `approxPolyDP` de float32
    uzerinde calisir -- int32'ye cevirmek ondalik kismi kirpip geometriyi
    yeniden bir piksel oynatirdi.
    """
    contour = contour.astype(np.float32)
    epsilon_px = SIMPLIFY_TOLERANCE_M / meters_per_px
    simplified = cv2.approxPolyDP(contour, epsilon_px, True).reshape(-1, 2)
    points_px = (
        snap_to_dominant_axes(simplified.tolist(), max_shift=epsilon_px)
        if square_up
        else simplified
    )
    vertices_ft = [
        [round(float(px) * feet_per_px, 3), round((image_height - float(py)) * feet_per_px, 3)]
        for px, py in points_px
    ]
    vertices_ft = _dedupe_close_points(vertices_ft, MIN_POINT_SPACING_M)
    area_m2 = cv2.contourArea(contour) * (meters_per_px ** 2)
    return vertices_ft, round(area_m2, 2)


def _parcel_lines_to_real_world(
    polylines_px: list[list[tuple[float, float]]], meters_per_px: float, feet_per_px: float, image_height: int
) -> list[list[list[float]]]:
    """Iskelet-grafigi polyline'larini (piksel) sadelestirip gercek birime
    (ft) cevirir ve ardisik nokta ciftlerini DetailLine segmentleri olarak
    dondurur. Her fiziksel cizgi `extract_parcel_lines()` sayesinde zaten
    tam bir kez geldigi icin ekstra bir cift-cizgi birlestirmesine gerek
    yoktur (bkz. geometry.py modul docstring'i)."""
    segments: list[list[list[float]]] = []
    epsilon_px = SIMPLIFY_TOLERANCE_M / meters_per_px
    for polyline in polylines_px:
        contour = np.array(polyline, dtype=np.float32).reshape(-1, 1, 2)
        simplified = cv2.approxPolyDP(contour, epsilon_px, False).reshape(-1, 2)
        # `float()` sart: numpy float32 skalari -- float64'un aksine -- Python
        # float'inin alt sinifi DEGILDIR, dogrudan json'a verilirse
        # "not JSON serializable" hatasi alinir.
        vertices_ft = [
            [round(float(px) * feet_per_px, 3), round((image_height - float(py)) * feet_per_px, 3)]
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
    raw_labels: list[dict], label_parcel: list[int | None], feet_per_px: float, image_height: int
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
                "parcel_id": label_parcel[i] if i < len(label_parcel) else None,
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
    bina_path: Path,
    parsel_path: Path,
    both_path: Path,
    scale_denominator: float,
    output_dir: Path,
    extract_labels: bool = True,
) -> None:
    _progress(4, "Ölçek çubuğu hesaplanıyor")
    scale_info = compute_scale_info(parsel_path, scale_denominator)
    meters_per_px = scale_info["meters_per_pixel"]
    feet_per_px = scale_info["feet_per_pixel"]

    # Hizalama once yapilir: uc goruntunun boyut uyumu burada dogrulanir,
    # yani uyumsuz bir girdi uzun geometri asamalarindan ONCE anlasilir.
    _progress(10, "Katmanlar both.png ile hizalanıyor")
    alignment = layer_offset(bina_path, parsel_path, both_path)
    if alignment["warning"]:
        print("UYARI: {}".format(alignment["warning"]))

    height, width = layer_masks(parsel_path).shape

    _progress(20, "Bina birimleri cıkarılıyor")
    buildings = shift_contours(extract_buildings(bina_path), tuple(alignment["offset_px"]))

    _progress(38, "Parsel hücreleri cıkarılıyor")
    parcel_cells = order_by_area(extract_parcel_cells(parsel_path))

    _progress(50, "Parsel çizgileri izleniyor")
    raw_parcel_lines = extract_parcel_lines(parsel_path)

    _progress(58, "Parsel-bina ilişkisi hesaplanıyor")
    building_parcel_id, parcel_buildings = match_buildings(buildings, parcel_cells)

    _progress(64, "Kuzey oku aranıyor")
    north = detect_north_arrow(parsel_path)
    north_record = None
    if north is not None:
        cx, cy = north["center_px"]
        north_record = {
            "position_ft": [round(cx * feet_per_px, 3), round((height - cy) * feet_per_px, 3)],
            "rotation_deg": north["rotation_deg"],
        }

    raw_labels: list[dict] = []
    label_parcel: list[int | None] = []
    label_warning = None
    if extract_labels:
        # En uzun suren adim: EasyOCR ilk calistirmada modelini de indirir.
        _progress(70, "Parsel numaralari okunuyor")
        try:
            from ocr_labels import extract_parcel_labels

            raw_labels = extract_parcel_labels(parsel_path)
            label_parcel = match_labels([l["center_px"] for l in raw_labels], parcel_cells)
        except Exception as ex:  # OCR (agir/internet gerektiren bagimlilik) basarisiz olsa bile
            label_warning = f"Etiket OCR'i basarisiz oldu, etiketsiz devam edildi: {ex}"
            print(f"UYARI: {label_warning}")

    _progress(88, "Gercek birime cevriliyor")
    parcel_labels = invert_label_match(label_parcel, raw_labels, len(parcel_cells))
    parcel_records = []
    for parcel_id, cell in enumerate(parcel_cells):
        vertices_ft, area_m2 = _to_real_world(cell, meters_per_px, feet_per_px, height)
        parcel_records.append(
            {
                "id": parcel_id,
                "label": parcel_labels[parcel_id],
                "area_m2": area_m2,
                "vertices_ft": vertices_ft,
                "building_ids": parcel_buildings[parcel_id],
            }
        )

    building_records = []
    for building_id, contour in enumerate(buildings):
        vertices_ft, area_m2 = _to_real_world(
            contour, meters_per_px, feet_per_px, height, square_up=True
        )
        parcel_id = building_parcel_id[building_id]
        building_records.append(
            {
                "id": building_id,
                "area_m2": area_m2,
                "vertices_ft": vertices_ft,
                "parcel_id": parcel_id,
                "parcel_label": parcel_labels[parcel_id] if parcel_id is not None else None,
            }
        )

    parcel_lines = _parcel_lines_to_real_world(raw_parcel_lines, meters_per_px, feet_per_px, height)
    frame_lines = _image_frame_lines(width, height, feet_per_px)
    label_records = _labels_to_real_world(raw_labels, label_parcel, feet_per_px, height)

    _progress(94, "Sonuçlar yaziliyor")
    output_dir.mkdir(parents=True, exist_ok=True)
    matched_count = sum(1 for b in building_records if b["parcel_id"] is not None)
    result = {
        "scale": scale_info,
        "image_size_px": {"width": width, "height": height},
        "origin_note": "vertices_ft/position_ft: X sagda artar, Y yukarida artar (piksel Y-ekseni ters cevrilmistir); orijin parsel.png'nin sol-alt kosesidir.",
        "alignment": alignment,
        "parcel_count": len(parcel_records),
        "building_count": len(building_records),
        "matched_building_count": matched_count,
        "parcel_line_count": len(parcel_lines),
        "parcel_lines_note": "DetailLine cizimi icin kullanilacak segment listesi; iskelet grafigi dogrudan izlenerek uretildigi icin her fiziksel cizgi (komsu parsellerin ortak siniri dahil) tam bir kez yer alir.",
        "parcel_lines": parcel_lines,
        "frame_lines_note": "Goruntunun dis sinirini olusturan 4 segment (kapali dikdortgen); Revit'te cizimi cerceveleyen ayri bir line style ile cizilir.",
        "frame_lines": frame_lines,
        "north_note": "Goruntudeki kuzey okunun konumu ve yonu; Revit'te secilen aciklama sembolu (annotation symbol) bu noktaya, yukari bakan bir sembolu ayni yone cevirecek 'rotation_deg' aci ile yerlestirilir. Ok bulunamazsa null.",
        "north": north_record,
        "buildings_note": "Her kayit bir bina BIRIMIDIR ve ayri bir FilledRegion olur; bitisik yapilarda ic bolme (parti) duvarlari korunur.",
        "parcels_note": "Parsel hucreleri cizilmez; alan/eslesme bilgisi tasirlar. 'label' o hucrenin icine dusen OCR okumasidir (sokak/bos alan hucrelerinde null).",
        "label_count": len(label_records),
        "labels_note": "Parsel numara etiketleri (OCR ile okundu, ör. '568C'). 'confidence' (0-1) dusukse (<~0.5) okuma yanlis olabilir -- G/6, A/4, B/8, S/5 gibi benzer karakterler karisabiliyor. OCR basarisiz/atlandiysa bu liste bostur.",
        "labels": label_records,
        "label_warning": label_warning,
        "parcels": parcel_records,
        "buildings": building_records,
    }
    with open(output_dir / "revit_input.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    canvas = render_preview(
        width, height, raw_parcel_lines, buildings, building_parcel_id,
        raw_labels, north, alignment["warning"],
    )
    cv2.imwrite(str(output_dir / "revit_input_preview.png"), canvas)
    _progress(100, "Tamamlandi")

    print(
        f"Olcek: {scale_info['scale_label']} ({meters_per_px:.5f} m/px) | "
        f"Hizalama: {alignment['offset_px']} px | "
        f"Parsel: {len(parcel_records)} | Bina: {len(building_records)} | "
        f"eslesen: {matched_count} | eslesmeyen: {len(building_records) - matched_count} | "
        f"etiket: {len(label_records)} "
        f"-> {output_dir}/revit_input.json"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="pyRevit icin gercek-birim ara format uretimi")
    parser.add_argument("--scale", type=float, required=True, help="Harita olcegi paydasi, ör. 500 (1:500 icin)")
    parser.add_argument("--bina", type=Path, default=Path("assets/bina.png"), help="Yalniz bina katmani")
    parser.add_argument("--parsel", type=Path, default=Path("assets/parsel.png"), help="Yalniz parsel katmani")
    parser.add_argument("--both", type=Path, default=Path("assets/both.png"),
                        help="Iki katman ust uste; yalniz hizalama referansi olarak kullanilir")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--labels", action=argparse.BooleanOptionalAction, default=True,
        help="Parsel numara etiketlerini OCR ile oku (--no-labels ile kapatilabilir; agir/internet gerektirir)",
    )
    args = parser.parse_args()

    prepare(args.bina, args.parsel, args.both, args.scale, args.output_dir, extract_labels=args.labels)


if __name__ == "__main__":
    main()
