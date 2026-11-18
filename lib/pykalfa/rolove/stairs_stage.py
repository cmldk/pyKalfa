# -*- coding: utf-8 -*-
"""Rolove Prototip - merdiven asamasi (istege bagli).

`data["stairs"]` (`pysrc/rolove/stairs.py`): her kayit alt kattan ust kata
bir merdiven (kullanici: yarida kesilmesin). Riht sayisi, basamak derinligi
ve kol uzunlugu SECILEN tipin sinirlarindan hesaplanir
(`stairs_calc.plan_run`).

- "straight": duz kol; eksik kol bina icindeki bos yere gore uzatilir.
- "turn": Polycam'in duz kutulara boldugu donen merdiven (duz kol + 90
  derece donuk kucuk kutu). Ceyrek donuslu, yelpaze basamakli tek cizimli
  kol (`StairsRun.CreateSketchedRun`, geometri `stairs_calc.winder_layout`).
  Revit reddederse alt islem geri alinir, ana kol duz kurulur, nedeni
  rapora yazilir.

`StairsEditScope` acik bir Transaction icinde BASLATILAMAZ; bu yuzden bu
asama kendi Transaction'larini yonetir (`creator.create_all` icinde "own"
asama). Her merdiven kendi kapsaminda: biri patlarsa iptal edilir,
raporlanir, digerleri devam eder.

IronPython 2.7.
"""

import math

from Autodesk.Revit.DB import Curve, Line, StairsEditScope, SubTransaction, Transaction, XYZ
from Autodesk.Revit.DB.Architecture import StairsRun, StairsRunJustification
from System.Collections.Generic import List

from pykalfa.rolove import stairs_calc

M_PER_FT = 0.3048
EXTEND_NOTE_FT = 0.05 / M_PER_FT        # bundan uzun uzatma raporlanir
MIN_CURVE_FT = 0.005


def _xyz(p, z):
    return XYZ(float(p[0]), float(p[1]), float(z))


def _attr(obj, name):
    try:
        return float(getattr(obj, name))
    except Exception:  # noqa: BLE001 - tip siniri okunamazsa stairs_calc varsayilani
        return 0.0


def _cm(ft):
    return ft * M_PER_FT * 100


def _straight(ctx, stairs_id, s, run_plan, width, z):
    """Duz kol (taranan serit boyunca); notlari dondurur."""
    (sx, sy), (ex, ey) = s["start_ft"], s["end_ft"]
    scan_run = math.hypot(ex - sx, ey - sy)
    ux, uy = ((ex - sx) / scan_run, (ey - sy) / scan_run) if scan_run > 1e-9 else (1.0, 0.0)
    # Eksik kol once bina icindeki bos yer kadar ust uctan ileri, kalan alt
    # uctan geri uzatilir (bodrum merdiveni duvari delip disari cikmasin).
    back, fwd = stairs_calc.place_run(scan_run, run_plan["run_ft"],
                                      s.get("fwd_free_ft"), s.get("back_free_ft"))
    p0 = (sx - ux * back, sy - uy * back)
    end = (p0[0] + ux * run_plan["run_ft"], p0[1] + uy * run_plan["run_ft"])
    run = StairsRun.CreateStraightRun(ctx.doc, stairs_id, Line.CreateBound(_xyz(p0, z), _xyz(end, z)),
                                      StairsRunJustification.Center)
    run.ActualRunWidth = width
    notes = []
    if run_plan["run_ft"] > scan_run + EXTEND_NOTE_FT:
        notes.append("kat yuksekligine ulasmak icin kol taramadan {:.2f} m uzatildi: ust uctan "
                     "{:.2f} m, alt uctan {:.2f} m (taranan {} basamak)".format(
                         (run_plan["run_ft"] - scan_run) * M_PER_FT, fwd * M_PER_FT,
                         back * M_PER_FT, s["treads"]))
        free = s.get("fwd_free_ft")
        if free is not None and fwd > float(free) + EXTEND_NOTE_FT:
            notes.append("UYARI: ust uc bina izinin {:.2f} m disina tasiyor, kontrol "
                         "edin".format((fwd - float(free)) * M_PER_FT))
    return notes


def _lines(points, z):
    out = []
    for a, b in zip(points, points[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > MIN_CURVE_FT:
            out.append(Line.CreateBound(_xyz(a, z), _xyz(b, z)))
    return out


def _turn(ctx, stairs_id, s, run_plan, width, z):
    """Ceyrek donuslu, yelpaze basamakli cizimli kol; notlari dondurur."""
    total = run_plan["risers"] - 1
    winders = int(s["winders"])
    n1, n2 = stairs_calc.split_treads(total, winders, s["run1_treads"], s["run2_treads"],
                                      run_plan["tread_ft"], s.get("free1_ft"), s.get("free2_ft"))
    lay = stairs_calc.winder_layout(tuple(s["corner_ft"]), tuple(s["u1"]), tuple(s["u2"]),
                                    width, n1, winders, n2, run_plan["tread_ft"])
    boundary = List[Curve](_lines(lay["inner"], z) + _lines(lay["outer"], z))
    risers = List[Curve]([Line.CreateBound(_xyz(a, z), _xyz(b, z)) for a, b in lay["risers"]])
    path = List[Curve](_lines(lay["path"], z))
    StairsRun.CreateSketchedRun(ctx.doc, stairs_id, 0.0, boundary, risers, path)
    notes = ["donen merdiven (donus {}): {} duz + {} yelpaze + {} duz basamak".format(
        "altta" if s.get("turn_at") == "bottom" else "ustte", n1, winders, n2)]
    scanned = int(s["run1_treads"]) + int(s["run2_treads"])
    if n1 + n2 > scanned:
        notes.append("kat yuksekligine ulasmak icin {} basamak eklendi (taranan {} duz)".format(
            n1 + n2 - scanned, scanned))
    free1, free2 = s.get("free1_ft"), s.get("free2_ft")
    over = []
    if free1 is not None and n1 * run_plan["tread_ft"] > (int(s["run1_treads"]) * float(s["depth_ft"])
                                                            + float(free1) + EXTEND_NOTE_FT):
        over.append("donusten onceki kol")
    if free2 is not None and n2 * run_plan["tread_ft"] > (int(s["run2_treads"]) * float(s["depth_ft"])
                                                            + float(free2) + EXTEND_NOTE_FT):
        over.append("donusten sonraki kol")
    if over:
        notes.append("UYARI: {} bina izinin disina tasiyor, kontrol edin".format(" ve ".join(over)))
    return notes


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
        notes = []
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
            width = max(float(s["width_ft"]), _attr(stype, "MinRunWidth"))
            z = base.Elevation
            built = False
            if s.get("kind") == "turn":
                sub = SubTransaction(ctx.doc)
                sub.Start()
                try:
                    notes += _turn(ctx, stairs_id, s, run_plan, width, z)
                    sub.Commit()
                    built = True
                except Exception as ex:  # noqa: BLE001 - duz kola dus
                    if sub.HasStarted() and not sub.HasEnded():
                        sub.RollBack()
                    notes.append("donen kol kurulamadi ({}); ana kol duz kuruldu".format(ex))
            if not built:
                notes += _straight(ctx, stairs_id, s, run_plan, width, z)
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
        notes.insert(0, "{} riht x {:.1f} cm, basamak {:.1f} cm".format(
            run_plan["risers"], _cm(stairs_calc.riser_ft(height, run_plan["risers"])),
            _cm(run_plan["tread_ft"])))
        if width > float(s["width_ft"]) + 1e-6:
            notes.append("genislik tipin alt siniri {:.0f} cm'ye cikarildi".format(_cm(width)))
        if s.get("direction_status") != "olculdu":
            notes.append("cikis yonu varsayildi")
        ctx.report.add("created", "stairs", sid, "; ".join(notes))
        ctx.report.warnings.append(u"Merdiven {}: {}".format(sid, "; ".join(notes)))
