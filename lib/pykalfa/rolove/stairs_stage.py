# -*- coding: utf-8 -*-
"""Rolove Prototip - merdiven asamasi (istege bagli).

`data["stairs"]` (`pysrc/rolove/stairs.py`): her kayit alt kattan ust kata
duz kollu bir merdiven (kullanici: yarida kesilmesin). Riht sayisi, basamak
derinligi ve kol uzunlugu SECILEN tipin sinirlarindan hesaplanir
(`stairs_calc.plan_run`); kol taramadaki baslangictan, olculen yonde
gerekirse uzatilir ve bu rapora yazilir. `StairsEditScope` acik bir Transaction icinde
BASLATILAMAZ; bu yuzden bu asama kendi Transaction'larini yonetir
(`creator.create_all` icinde "own" asama). Her merdiven kendi kapsaminda:
biri patlarsa iptal edilir, raporlanir, digerleri devam eder.

IronPython 2.7.
"""

import math

from Autodesk.Revit.DB import Line, StairsEditScope, Transaction, XYZ
from Autodesk.Revit.DB.Architecture import StairsRun, StairsRunJustification

from pykalfa.rolove import stairs_calc

M_PER_FT = 0.3048
EXTEND_NOTE_FT = 0.05 / M_PER_FT        # bundan uzun uzatma raporlanir


def _xyz(p, z):
    return XYZ(float(p[0]), float(p[1]), float(z))


def _attr(obj, name):
    try:
        return float(getattr(obj, name))
    except Exception:  # noqa: BLE001 - tip siniri okunamazsa stairs_calc varsayilani
        return 0.0


def stage_stairs(ctx, recorder_cls):
    """`recorder_cls(sink, stage)`: uyarilari silen ama rapora yazan
    failures preprocessor (creator._Recorder)."""
    items = ctx.data.get("stairs") or []
    ledger_plan = ctx.plan([s["id"] for s in items])
    stairs_type = ctx.choices.stairs_type
    for s in items:
        sid = s["id"]
        if sid in ledger_plan["keep"]:
            ctx.report.add("kept", "stairs", sid)
            continue
        if sid in ledger_plan["deleted"]:
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
            stype = ctx.doc.GetElement(stairs.GetTypeId())
            height = top.Elevation - base.Elevation       # kot duzenlemeleri dahil
            run_plan = stairs_calc.plan_run(height, s.get("depth_ft"), _attr(stype, "MaxRiserHeight"),
                                        _attr(stype, "MinTreadDepth"))
            stairs.DesiredRisersNumber = run_plan["risers"]
            stairs.ActualTreadDepth = run_plan["tread_ft"]
            (sx, sy), (ex, ey) = s["start_ft"], s["end_ft"]
            scan_run = math.hypot(ex - sx, ey - sy)
            ux, uy = ((ex - sx) / scan_run, (ey - sy) / scan_run) if scan_run > 1e-9 else (1.0, 0.0)
            z = base.Elevation
            # Eksik kol once bina icindeki bos yer kadar ust uctan ileri, kalan
            # alt uctan geri uzatilir (bodrum merdiveni duvari delip disari
            # cikmasin); bos yer bilinmiyorsa hepsi ileri.
            back, fwd = stairs_calc.place_run(scan_run, run_plan["run_ft"],
                                              s.get("fwd_free_ft"), s.get("back_free_ft"))
            p0 = (sx - ux * back, sy - uy * back)
            end = (p0[0] + ux * run_plan["run_ft"], p0[1] + uy * run_plan["run_ft"])
            path = Line.CreateBound(_xyz(p0, z), _xyz(end, z))
            run = StairsRun.CreateStraightRun(ctx.doc, stairs_id, path, StairsRunJustification.Center)
            width = max(float(s["width_ft"]), _attr(stype, "MinRunWidth"))
            run.ActualRunWidth = width
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
        notes = ["{} riht x {:.1f} cm, basamak {:.1f} cm".format(
            run_plan["risers"], stairs_calc.riser_ft(height, run_plan["risers"]) * M_PER_FT * 100,
            run_plan["tread_ft"] * M_PER_FT * 100)]
        if run_plan["run_ft"] > scan_run + EXTEND_NOTE_FT:
            notes.append("kat yuksekligine ulasmak icin kol taramadan {:.2f} m uzatildi: ust uctan "
                         "{:.2f} m, alt uctan {:.2f} m (taranan {} basamak)".format(
                             (run_plan["run_ft"] - scan_run) * M_PER_FT, fwd * M_PER_FT,
                             back * M_PER_FT, s["treads"]))
            free = s.get("fwd_free_ft")
            if free is not None and fwd > float(free) + EXTEND_NOTE_FT:
                notes.append("UYARI: ust uc bina izinin {:.2f} m disina tasiyor, kontrol "
                             "edin".format((fwd - float(free)) * M_PER_FT))
        if width > float(s["width_ft"]) + 1e-6:
            notes.append("genislik tipin alt siniri {:.0f} cm'ye cikarildi".format(
                width * M_PER_FT * 100))
        if s.get("direction_status") != "olculdu":
            notes.append("cikis yonu varsayildi")
        ctx.report.add("created", "stairs", sid, "; ".join(notes))
        if notes:
            ctx.report.warnings.append(u"Merdiven {}: {}".format(sid, "; ".join(notes)))
