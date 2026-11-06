# -*- coding: utf-8 -*-
"""`revit_input.json` -> DetailCurve / FilledRegion / TextNote / kuzey oku.

Parsel/Bina GIS butonu icin. Govde, Parsel/Bina Aktar butonundaki
(`ImportGeometry.pushbutton/script.py`) cizim blogunun aynisidir; o buton
bilerek degistirilmedi, bu yuzden kod burada tekrar ediyor.

Tek Transaction: sonuc begenilmezse Revit'te tek Ctrl+Z ile geri alinir.
Hata olursa RollBack yapilir ve istisna yeniden firlatilir.

IronPython 2.7 uyumlu yazilmistir.
"""

import math

from Autodesk.Revit.DB import (
    XYZ,
    CurveLoop,
    ElementTransformUtils,
    FilledRegion,
    Line,
    TextNote,
    Transaction,
)
from pyrevit import script
from System.Collections.Generic import List

from pykalfa.revitutils import WarningSwallower, distance, view_elevation

logger = script.get_logger()

# Bu uzunlugun altindaki segmentler atlanir (bkz. ImportGeometry script.py).
MIN_SEGMENT_LENGTH_FT = 0.05


def _draw_segments(doc, view, segments, line_style, z, what):
    created = 0
    skipped = 0
    for i, (p1, p2) in enumerate(segments):
        if distance(p1, p2) < MIN_SEGMENT_LENGTH_FT:
            skipped += 1
            continue
        try:
            line = Line.CreateBound(XYZ(p1[0], p1[1], z), XYZ(p2[0], p2[1], z))
        except Exception as ex:
            logger.debug("{} segment {} atlandi: {}".format(what, i, ex))
            skipped += 1
            continue
        detail_curve = doc.Create.NewDetailCurve(view, line)
        try:
            detail_curve.LineStyle = line_style
        except Exception as ex:
            logger.debug("LineStyle atanamadi: {}".format(ex))
        created += 1
    return created, skipped


def _draw_region(doc, view, building, region_type, z):
    verts = building["vertices_ft"]
    n = len(verts)
    if n < 3:
        return False
    loop = CurveLoop()
    for i in range(n):
        p1, p2 = verts[i], verts[(i + 1) % n]
        if distance(p1, p2) < MIN_SEGMENT_LENGTH_FT:
            continue
        try:
            loop.Append(Line.CreateBound(XYZ(p1[0], p1[1], z), XYZ(p2[0], p2[1], z)))
        except Exception as ex:
            logger.debug("Bina {} loop kurulamadi: {}".format(building.get("id"), ex))
            return False
    try:
        FilledRegion.Create(doc, region_type.Id, view.Id, List[CurveLoop]([loop]))
        return True
    except Exception as ex:
        logger.debug("Bina {} FilledRegion olusturulamadi: {}".format(building.get("id"), ex))
        return False


def _create_centered_note(doc, view, position, text, text_type):
    """Metni `position` noktasina ORTALANMIS olarak koyar.

    `TextNote.Create(..., typeId)` noktayi metnin SOL-UST kosesi sayar; bu
    yuzden etiket parselin icindeki noktadan saga-asagi kayiyordu
    (onizleme ise metni noktaya ortalar). TextNoteOptions ile yatay/dikey
    orta hizalama verilir; eski Revit surumlerinde VerticalAlignment yoksa
    yalniz yatay ortalama, o da yoksa varsayilan olusturma kullanilir."""
    try:
        from Autodesk.Revit.DB import HorizontalTextAlignment, TextNoteOptions
        opts = TextNoteOptions(text_type.Id)
        opts.HorizontalAlignment = HorizontalTextAlignment.Center
        try:
            from Autodesk.Revit.DB import VerticalTextAlignment
            opts.VerticalAlignment = VerticalTextAlignment.Middle
        except Exception as ex:
            logger.debug("Dikey ortalama desteklenmiyor: {}".format(ex))
        return TextNote.Create(doc, view.Id, position, text, opts)
    except Exception as ex:
        logger.debug("TextNoteOptions kullanilamadi, varsayilan hizalama: {}".format(ex))
        return TextNote.Create(doc, view.Id, position, text, text_type.Id)


def _rotate(doc, element_id, position, rotation_deg):
    if rotation_deg:
        axis = Line.CreateBound(position, position + XYZ.BasisZ)
        ElementTransformUtils.RotateElement(doc, element_id, axis, math.radians(rotation_deg))


def _draw_notes(doc, view, items, text_type, z, what):
    """Ortalanmis ve `rotation_deg` kadar dondurulmus TextNote'lar; (olusan, atlanan)."""
    created = 0
    skipped = 0
    for item in items:
        try:
            position = XYZ(item["position_ft"][0], item["position_ft"][1], z)
            note = _create_centered_note(doc, view, position, item["text"], text_type)
            # Not noktaya ortali oldugu icin ayni nokta etrafinda dondurmek
            # metni yerinde (yol yonunde) cevirir, kaydirmaz.
            _rotate(doc, note.Id, position, item.get("rotation_deg") or 0.0)
            created += 1
        except Exception as ex:
            logger.debug("{} '{}' olusturulamadi: {}".format(what, item.get("text"), ex))
            skipped += 1
    return created, skipped


def draw_revit_input(doc, view, data, line_style, frame_style, region_type,
                     text_type, north_symbol, transaction_name,
                     road_style=None, street_text_type=None,
                     selected_line_style=None, selected_text_type=None):
    """Sayimlari dondurur: lines, lines_skipped, frame, frame_skipped,
    roads, roads_skipped, regions, regions_skipped, labels, labels_skipped,
    streets, streets_skipped, north (0/1).
    `frame_style`, `text_type`, `north_symbol`, `road_style`,
    `street_text_type` None olabilir (None = o parca cizilmez).
    Secilen parsel: `selected_line_style` / `selected_text_type` None ise
    parsel stili / parsel text tipiyle cizilir (hicbir sey kaybolmaz);
    sayimlar selected_lines, selected_lines_skipped, selected_label (0/1)."""
    z = view_elevation(view)
    counts = dict(lines=0, lines_skipped=0, frame=0, frame_skipped=0, roads=0, roads_skipped=0,
                  regions=0, regions_skipped=0, labels=0, labels_skipped=0,
                  streets=0, streets_skipped=0, north=0,
                  selected_lines=0, selected_lines_skipped=0, selected_label=0)

    t = Transaction(doc, transaction_name)
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(opts)
    t.Start()
    try:
        counts["lines"], counts["lines_skipped"] = _draw_segments(
            doc, view, data.get("parcel_lines") or [], line_style, z, "Parsel")

        # parcel_lines secilen parselin sinirini icermez: o burada, ayri
        # stil secilmediyse parsel stiliyle cizilir.
        counts["selected_lines"], counts["selected_lines_skipped"] = _draw_segments(
            doc, view, data.get("selected_parcel_lines") or [],
            selected_line_style or line_style, z, "Secilen parsel")

        if frame_style is not None:
            counts["frame"], counts["frame_skipped"] = _draw_segments(
                doc, view, data.get("frame_lines") or [], frame_style, z, "Cerceve")

        if road_style is not None:
            counts["roads"], counts["roads_skipped"] = _draw_segments(
                doc, view, data.get("road_lines") or [], road_style, z, "Yol")

        for building in data.get("buildings") or []:
            if _draw_region(doc, view, building, region_type, z):
                counts["regions"] += 1
            else:
                counts["regions_skipped"] += 1

        if text_type is not None:
            labels = data.get("labels") or []
            counts["labels"], counts["labels_skipped"] = _draw_notes(
                doc, view, [l for l in labels if not l.get("selected")], text_type, z, "Etiket")
            sel_created, sel_skipped = _draw_notes(
                doc, view, [l for l in labels if l.get("selected")],
                selected_text_type or text_type, z, "Secilen parsel etiketi")
            counts["labels"] += sel_created
            counts["labels_skipped"] += sel_skipped
            counts["selected_label"] = 1 if sel_created else 0

        if street_text_type is not None:
            counts["streets"], counts["streets_skipped"] = _draw_notes(
                doc, view, data.get("street_labels") or [], street_text_type, z, "Sokak adi")

        north = data.get("north")
        if north_symbol is not None and north:
            try:
                if not north_symbol.IsActive:
                    north_symbol.Activate()
                    doc.Regenerate()
                position = XYZ(north["position_ft"][0], north["position_ft"][1], z)
                instance = doc.Create.NewFamilyInstance(position, north_symbol, view)
                _rotate(doc, instance.Id, position, north.get("rotation_deg") or 0.0)
                counts["north"] = 1
            except Exception as ex:
                logger.debug("Kuzey oku yerlestirilemedi: {}".format(ex))

        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return counts
