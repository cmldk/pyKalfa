# -*- coding: utf-8 -*-
"""Projedeki MEVCUT stilleri kullaniciya sectirme.

pyKalfa hicbir stil/tip adini koda gommez: line style, filled region tipi,
text note tipi, duvar tipi... hepsi proje sablonuna gore degistigi icin
script calisirken, projede zaten TANIMLI olanlar arasindan secilir.
Bu modul o secim diyaloglarini tek bir yerde toplar.
"""

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilledRegionType,
    FilteredElementCollector,
    GraphicsStyle,
    Level,
    TextNoteType,
    WallKind,
    WallType,
)
from pyrevit import forms, script

from pykalfa.revitutils import elem_name

logger = script.get_logger()


def unwrap_selection(value):
    """`forms.SelectFromList.show` bazi pyRevit surumlerinde tek secimde
    bile liste dondurebiliyor; her iki durumu da guvenle ele alir."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def pick_by_name(elements, title, empty_message, optional=False):
    """Verilen elemanlari adlarina gore listeleyip birini sectirir.

    Hic eleman yoksa veya kullanici diyalogu iptal ederse scripti
    sonlandirir; boylece cagiran taraf her zaman gecerli bir eleman alir.

    `optional=True` ise, projede hic uygun eleman YOKSA hata verip
    cikmak yerine None doner. Zorunlu olmayan bir secim icin (ör. sadece
    OCR bir etiket okursa gerekecek metin tipi) projeyi bastan reddetmek
    dogru olmaz -- o durumda islevin geri kalani calisabilmelidir."""
    by_name = {elem_name(el): el for el in elements}
    logger.info("{}: {} secenek bulundu.".format(title, len(by_name)))
    if not by_name:
        if optional:
            logger.info("{}: proje bos, atlaniyor.".format(title))
            return None
        forms.alert(empty_message, exitscript=True)

    chosen_name = unwrap_selection(
        forms.SelectFromList.show(sorted(by_name.keys()), title=title, multiselect=False)
    )
    logger.info("Secilen: {}".format(chosen_name))
    if not chosen_name:
        script.exit()
    return by_name[chosen_name]


def line_styles(doc):
    """Projedeki line style'lar: sadece "Lines" kategorisinin alt
    kategorileri (ör. LIMITE PARCELLAIRE)."""
    lines_category_id = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines).Id
    return [
        gs
        for gs in FilteredElementCollector(doc).OfClass(GraphicsStyle)
        if gs.GraphicsStyleCategory is not None
        and gs.GraphicsStyleCategory.Parent is not None
        and gs.GraphicsStyleCategory.Parent.Id == lines_category_id
    ]


def pick_line_style(doc, title="Line style secin"):
    return pick_by_name(
        line_styles(doc),
        title,
        "Projede tanimli bir line style (Lines alt kategorisi) bulunamadi.",
    )


def pick_filled_region_type(doc, title="Filled region tipi secin"):
    return pick_by_name(
        FilteredElementCollector(doc).OfClass(FilledRegionType),
        title,
        "Projede tanimli bir Filled Region Type bulunamadi.",
    )


def pick_text_note_type(doc, title="Text note tipi secin", optional=False):
    return pick_by_name(
        FilteredElementCollector(doc).OfClass(TextNoteType),
        title,
        "Projede tanimli bir Text Note Type bulunamadi.",
        optional=optional,
    )


def pick_level(doc, title="Level secin"):
    """Projedeki seviyelerden birini sectirir.

    Liste yuksekligiyle birlikte gosterilir (ör. "Kat 1  (+0.00 m)"):
    projelerde birbirine benzeyen isimler (Level 1 / Niveau 1) oldugunda
    dogru olani secmek yalniz isme bakarak zor olabiliyor."""
    levels = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.Elevation)
    if not levels:
        forms.alert("Projede tanimli bir Level bulunamadi.", exitscript=True)

    # Etiket -> Level esleme: isim ayni olsa bile yukseklik ayirt eder.
    by_label = {}
    for level in levels:
        label = "{}  ({:+.2f} m)".format(elem_name(level), level.Elevation * 0.3048)
        by_label[label] = level

    logger.info("{}: {} seviye bulundu.".format(title, len(by_label)))
    chosen = unwrap_selection(
        forms.SelectFromList.show(list(by_label.keys()), title=title, multiselect=False)
    )
    logger.info("Secilen level: {}".format(chosen))
    if not chosen:
        script.exit()
    return by_label[chosen]


def pick_wall_type(doc, title="Duvar tipi secin"):
    """Projedeki duvar tiplerinden birini sectirir.

    Perde duvar (curtain) tipleri disarida birakilir: tek bir eksen
    cizgisinden perde duvar uretmek neredeyse her zaman istenmeyen bir
    sonuc olur. Projede hic temel/yigin (basic/stacked) tip yoksa,
    kullaniciyi tikamamak icin butun tipler listelenir."""
    all_types = list(FilteredElementCollector(doc).OfClass(WallType))
    basic = [wt for wt in all_types if wt.Kind in (WallKind.Basic, WallKind.Stacked)]
    return pick_by_name(
        basic or all_types,
        title,
        "Projede tanimli bir Wall Type bulunamadi.",
    )
