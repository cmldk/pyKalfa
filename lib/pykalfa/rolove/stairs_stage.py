# -*- coding: utf-8 -*-
"""Rolove Prototip - merdiven asamasi (istege bagli).

`data["stairs"]` (`pysrc/rolove/stairs.py`): her kayit iki Level arasinda
duz kollu bir merdiven. `StairsEditScope` acik bir Transaction icinde
BASLATILAMAZ; bu yuzden bu asama kendi Transaction'larini yonetir
(`creator.create_all` icinde "own" asama). Her merdiven kendi kapsaminda:
biri patlarsa iptal edilir, raporlanir, digerleri devam eder.

IronPython 2.7.
"""

from Autodesk.Revit.DB import BuiltInParameter, Line, StairsEditScope, Transaction, XYZ
from Autodesk.Revit.DB.Architecture import StairsRun, StairsRunJustification


def _xyz(p, z):
    return XYZ(float(p[0]), float(p[1]), float(z))


def stage_stairs(ctx, recorder_cls):
    """`recorder_cls(sink, stage)`: uyarilari silen ama rapora yazan
    failures preprocessor (creator._Recorder)."""
    items = ctx.data.get("stairs") or []
    plan = ctx.plan([s["id"] for s in items])
    stairs_type = ctx.choices.stairs_type
    for s in items:
        sid = s["id"]
        if sid in plan["keep"]:
            ctx.report.add("kept", "stairs", sid)
            continue
        if sid in plan["deleted"]:
            ctx.report.add("deleted", "stairs", sid, "kullanici silmis")
            continue
        base = ctx.levels.get(s["floor"])
        top = ctx.levels.get(s["top_floor"])
        if base is None or top is None:
            ctx.report.add("failed", "stairs", sid, "alt ya da ust katin Level'i yok")
            continue
        scope = StairsEditScope(ctx.doc, "pyKalfa merdiven")
        t = None
        try:
            stairs_id = scope.Start(base.Id, top.Id)
            t = Transaction(ctx.doc, "pyKalfa Rolove: merdiven")
            opts = t.GetFailureHandlingOptions()
            opts.SetFailuresPreprocessor(recorder_cls(ctx.revit_messages, "merdivenler"))
            t.SetFailureHandlingOptions(opts)
            t.Start()
            stairs = ctx.doc.GetElement(stairs_id)
            if stairs_type is not None:
                stairs.ChangeTypeId(stairs_type.Id)
            # Kismi (ara) merdiven: ust kata kadar degil, olculen/varsayilan
            # yukseklikte biter (ust ofset negatif).
            top_offset = float(s.get("top_offset_ft") or 0.0)
            if abs(top_offset) > 1e-6:
                stairs.get_Parameter(BuiltInParameter.STAIRS_TOP_OFFSET).Set(top_offset)
            stairs.DesiredRisersNumber = int(s["treads"]) + 1
            # Basamak derinligi tipten degil taramadan: yoksa kol uzunlugu
            # riht sayisina yetmez ("cannot reach the top elevation").
            if s.get("depth_ft"):
                stairs.ActualTreadDepth = float(s["depth_ft"])
            z = base.Elevation
            path = Line.CreateBound(_xyz(s["start_ft"], z), _xyz(s["end_ft"], z))
            run = StairsRun.CreateStraightRun(ctx.doc, stairs_id, path, StairsRunJustification.Center)
            run.ActualRunWidth = float(s["width_ft"])
            ctx.remember(sid, stairs)
            t.Commit()
            scope.Commit(recorder_cls(ctx.revit_messages, "merdivenler"))
        except Exception as ex:  # noqa: BLE001 - merdiven istege bagli, akis surer
            if t is not None and t.HasStarted() and not t.HasEnded():
                t.RollBack()
            if scope.IsActive:
                scope.Cancel()
            ctx.items.pop(sid, None)
            ctx.report.add("failed", "stairs", sid, str(ex))
            continue
        notes = []
        if s.get("kind") == "partial":
            notes.append("ara merdiven, {:.2f} m".format(float(s.get("height_m") or 0.0)))
        if s.get("height_status") == "varsayildi":
            notes.append("yukseklik varsayildi (18 cm riht)")
        if s.get("direction_status") != "olculdu":
            notes.append("cikis yonu varsayildi")
        ctx.report.add("created", "stairs", sid, "; ".join(notes))
        if notes:
            ctx.report.warnings.append(u"Merdiven {}: {}".format(sid, "; ".join(notes)))
