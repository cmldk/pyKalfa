# -*- coding: utf-8 -*-
"""Duvar Aktar - duvar adaylarindan gercek `Wall` olusturma.

Bu modul hic diyalog acmaz ve hic girdi sormaz: hazir veriyi alir, bir
transaction icinde `Wall.Create` ile duvarlari uretir ve ne olduguna
dair bir rapor dondurur. Boylece Revit tarafi tek basina okunabilir ve
ileride (Faz 2) duvar kalinligi/kapi boslugu eklendiginde sadece burasi
buyur.

Dayanikliligin (stabilite) iki ayagi var:

  1. **Tek tek hata yakalama:** bir cizgi Revit'i mutsuz ederse (dejenere
     uzunluk, gecersiz egri, tipin izin vermedigi durum) sadece o cizgi
     atlanir ve raporlanir; kalan duvarlar olusmaya devam eder. Tek bir
     bozuk cizgi yuzunden butun aktarimi geri almak, kullaniciyi
     "%100 dogru olmayan ama duzeltilebilir" bir sonuctan mahrum ederdi.
  2. **Uyari yutucu:** cok sayida bitisik duvar olusturulurken Revit
     "duvarlar birbirine baglanamadi" gibi modal uyarilar cikarabiliyor;
     bunlar otomasyon akisini kilitler. UYARILAR yutulur, gercek HATALAR
     Revit'in kendi davranisina birakilir (bkz. `pykalfa.revitutils`).
"""

from Autodesk.Revit.DB import XYZ, Line, Transaction, Wall
from pyrevit import script

from pykalfa.revitutils import WarningSwallower

logger = script.get_logger()

# Revit'in kabul ettigi en kisa egri ~1/32 inch'tir; bunun altindaki
# cizgiler `Line.CreateBound` asamasinda zaten patlar, biz daha once
# yakalayip anlamli bir sebep yazalim.
MIN_CURVE_LENGTH_FT = 0.01


class WallReport(object):
    """Aktarim sonucu: kac duvar olustu, hangileri neden olusmadi."""

    def __init__(self):
        self.created = 0
        self.created_length_ft = 0.0
        self.created_ids = []
        #: {"index", "layer", "start", "end", "length_ft", "reason"} sozlukleri
        self.failed = []

    def add_failure(self, index, wall, reason):
        self.failed.append({
            "index": index,
            "layer": wall.get("layer", "?"),
            "start": wall.get("start", [0.0, 0.0]),
            "end": wall.get("end", [0.0, 0.0]),
            "length_ft": wall.get("length_ft", 0.0),
            "reason": reason,
        })


def _axis_line(wall, elevation):
    """Duvar ekseninden yatay bir `Line` uretir.

    Z, level yuksekligine sabitlenir: kaynak cizimden gelen Z degerleri
    (tarama kaynakli DXF'lerde gurultulu olabilir) duvari egik yapar ve
    `Wall.Create` yatay olmayan egriyi kabul etmez."""
    start = XYZ(wall["start"][0], wall["start"][1], elevation)
    end = XYZ(wall["end"][0], wall["end"][1], elevation)
    return Line.CreateBound(start, end)


def create_walls(doc, walls, wall_type, level, height_ft, structural=False):
    """`walls` (JSON sozlukleri) -> Revit duvarlari. `WallReport` dondurur.

    Tek bir transaction kullanilir: kullanici sonucu begenmezse Revit'te
    tek bir "Undo" ile aktarimin tamamini geri alabilsin diye."""
    report = WallReport()
    elevation = level.Elevation

    transaction = Transaction(doc, "pyKalfa: DXF'ten duvar aktarimi")
    failure_opts = transaction.GetFailureHandlingOptions()
    failure_opts.SetFailuresPreprocessor(WarningSwallower())
    transaction.SetFailureHandlingOptions(failure_opts)
    transaction.Start()
    try:
        for index, wall in enumerate(walls):
            if wall.get("length_ft", 0.0) < MIN_CURVE_LENGTH_FT:
                report.add_failure(index, wall, "Cizgi Revit icin fazla kisa")
                continue

            try:
                axis = _axis_line(wall, elevation)
            except Exception as ex:
                report.add_failure(index, wall, "Egri olusturulamadi: {}".format(ex))
                continue

            try:
                created = Wall.Create(
                    doc,
                    axis,
                    wall_type.Id,
                    level.Id,
                    height_ft,
                    0.0,        # taban ofseti (level'in tam uzerinde)
                    False,      # flip
                    structural,
                )
                report.created += 1
                report.created_length_ft += wall.get("length_ft", 0.0)
                report.created_ids.append(created.Id)
            except Exception as ex:
                logger.debug("Duvar {} olusturulamadi: {}".format(index, ex))
                report.add_failure(index, wall, "Wall.Create hatasi: {}".format(ex))

        transaction.Commit()
    except Exception:
        # Buraya ancak transaction'in kendisiyle ilgili (tek tek duvarlarla
        # degil) bir sorunda dusulur; o durumda yarim kalmis bir model
        # birakmaktansa her seyi geri almak dogrudur.
        transaction.RollBack()
        raise

    return report
