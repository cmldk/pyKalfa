# -*- coding: utf-8 -*-
"""Rolove Prototip - merdiven asamasi (istege bagli).

`data["stairs"]` (`pysrc/rolove/stairs.py`): her kayit alt kattan ust kata
bir merdiven (kullanici: yarida kesilmesin, ust kattaki acikliga tam denk
gelsin). Kol TARANAN uzunlukta kalir; riht sayisi kat yuksekligi / secilen
tipin en yuksek rihti, basamak derinligi taranan kol uzunlugu / duz basamak
(`stairs_calc.fit_run`). Basamak tipin alt sinirindan kisa kalabilir
(merdiven diklesir); rapora yazilir.

- "straight": duz kol, taranan baslangictan taranan sona.
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

from Autodesk.Revit.DB import (
    Curve,
    FilteredElementCollector,
    Line,
    StairsEditScope,
    SubTransaction,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Architecture import (
    StairsRun,
    StairsRunJustification,
    StairsRunType,
    StairsType,
    StairsUndersideSurfaceStyle,
)
from System.Collections.Generic import List

from pykalfa.revitutils import elem_name
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


def _straight(ctx, stairs_id, s, width, z):
    """Duz kol, taranan baslangictan taranan sona."""
    (sx, sy), (ex, ey) = s["start_ft"], s["end_ft"]
    run = StairsRun.CreateStraightRun(ctx.doc, stairs_id,
                                      Line.CreateBound(_xyz((sx, sy), z), _xyz((ex, ey), z)),
                                      StairsRunJustification.Center)
    run.ActualRunWidth = width
    return []


def _lines(points, z):
    out = []
    for a, b in zip(points, points[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > MIN_CURVE_FT:
            out.append(Line.CreateBound(_xyz(a, z), _xyz(b, z)))
    return out


def _turn(ctx, stairs_id, s, fit, width, z):
    """Ceyrek donuslu, yelpaze basamakli cizimli kol; duz basamaklar taranan
    kol(lar)a sigdirilir. Notlari dondurur."""
    winders = int(s["winders"])
    n1, n2 = stairs_calc.split_fitted(fit["straight_treads"], s["run1_treads"], s["run2_treads"])
    lay = stairs_calc.winder_layout(tuple(s["corner_ft"]), tuple(s["u1"]), tuple(s["u2"]),
                                    width, n1, winders, n2, fit["tread_ft"])
    boundary = List[Curve](_lines(lay["inner"], z) + _lines(lay["outer"], z))
    risers = List[Curve]([Line.CreateBound(_xyz(a, z), _xyz(b, z)) for a, b in lay["risers"]])
    path = List[Curve](_lines(lay["path"], z))
    StairsRun.CreateSketchedRun(ctx.doc, stairs_id, 0.0, boundary, risers, path)
    return ["donen merdiven (donus {}): {} duz + {} yelpaze + {} duz basamak".format(
        "altta" if s.get("turn_at") == "bottom" else "ustte", n1, winders, n2)]


def _turn_scan_len(s, width):
    """Donen merdivende duz kol(lar)in taranan uzunlugu, GERCEK genislikle:
    donus karesinin kenarindan taranan kol ucuna (genislik tipin alt sinirina
    cikinca kare buyur; kol yine taranan uca biter)."""
    (cx, cy), u1, u2 = s["corner_ft"], s["u1"], s["u2"]
    hw = float(width) / 2.0
    (sx, sy), (ex, ey) = s["start_ft"], s["end_ft"]
    total = 0.0
    if int(s["run1_treads"]) > 0:                  # donus ustte: kol -> kare
        m1 = (cx - u1[0] * hw, cy - u1[1] * hw)
        total += max(0.0, (m1[0] - sx) * u1[0] + (m1[1] - sy) * u1[1])
    if int(s["run2_treads"]) > 0:                  # donus altta: kare -> kol
        m2 = (cx + u2[0] * hw, cy + u2[1] * hw)
        total += max(0.0, (ex - m2[0]) * u2[0] + (ey - m2[1]) * u2[1])
    return total


def _fit(stairs, height, s, stype, winders, width):
    if winders:
        scan_len = _turn_scan_len(s, width)
    else:
        (sx, sy), (ex, ey) = s["start_ft"], s["end_ft"]
        scan_len = math.hypot(ex - sx, ey - sy)
    fit = stairs_calc.fit_run(height, scan_len, _attr(stype, "MaxRiserHeight"), winders)
    stairs.DesiredRisersNumber = fit["risers"]
    stairs.ActualTreadDepth = fit["tread_ft"]
    return fit


def _by_name(doc, cls, name):
    for el in FilteredElementCollector(doc).OfClass(cls):
        if elem_name(el) == name:
            return el
    return None


def _smooth_turn_type(ctx, stairs_type, recorder_cls):
    """Monolitik kolda "Underside of Winder" = Stepped ise yelpaze
    basamaklarin alti blok blok cikar. Secilen tipe dokunmadan kopyasi
    (merdiven + kol tipi, "- Prototip") alti Smooth olarak hazirlanir;
    yalniz donen merdivenlerde kullanilir. Varsa ayni adli kopya kullanilir."""
    rt = ctx.doc.GetElement(stairs_type.RunType)
    if rt is None or not rt.IsMonolithic or rt.UndersideSurfaceStyle != StairsUndersideSurfaceStyle.Stepped:
        return stairs_type
    t = Transaction(ctx.doc, "pyKalfa Rolove: donen merdiven tipi")
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(recorder_cls(ctx.revit_messages, "merdivenler"))
    t.SetFailureHandlingOptions(opts)
    t.Start()
    try:
        rt_name = "{} - Prototip".format(elem_name(rt))
        new_rt = _by_name(ctx.doc, StairsRunType, rt_name) or rt.Duplicate(rt_name)
        new_rt.UndersideSurfaceStyle = StairsUndersideSurfaceStyle.Smooth
        st_name = "{} - Prototip".format(elem_name(stairs_type))
        new_st = _by_name(ctx.doc, StairsType, st_name) or stairs_type.Duplicate(st_name)
        new_st.RunType = new_rt.Id
        t.Commit()
    except Exception as ex:  # noqa: BLE001 - tip olmazsa secilen tiple devam
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        ctx.report.warnings.append(u"Donen merdiven icin duz altli tip hazirlanamadi ({}); "
                                   u"donus alti basamakli gorunebilir".format(ex))
        return stairs_type
    ctx.report.warnings.append(u"Donen merdivenler '{}' tipiyle kuruldu: secilen tipin kopyasi, "
                               u"donus alti duz (Smooth)".format(st_name))
    return new_st


def stage_stairs(ctx, recorder_cls):
    """`recorder_cls(sink, stage)`: uyarilari silen ama rapora yazan
    failures preprocessor (creator._Recorder)."""
    items = ctx.data.get("stairs") or []
    ledger_plan = ctx.plan([s["id"] for s in items])
    stairs_type = ctx.choices.stairs_type
    turn_type = stairs_type
    if stairs_type is not None and any(s.get("kind") == "turn" for s in items):
        turn_type = _smooth_turn_type(ctx, stairs_type, recorder_cls)
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
            use_type = turn_type if s.get("kind") == "turn" else stairs_type
            if use_type is not None:
                stairs.ChangeTypeId(use_type.Id)
            stype = ctx.doc.GetElement(stairs.GetTypeId())
            height = top.Elevation - base.Elevation       # kot duzenlemeleri dahil
            width = max(float(s["width_ft"]), _attr(stype, "MinRunWidth"))
            z = base.Elevation
            built = False
            fit = None
            if s.get("kind") == "turn":
                sub = SubTransaction(ctx.doc)
                sub.Start()
                try:
                    fit = _fit(stairs, height, s, stype, int(s["winders"]), width)
                    notes += _turn(ctx, stairs_id, s, fit, width, z)
                    sub.Commit()
                    built = True
                except Exception as ex:  # noqa: BLE001 - duz kola dus
                    if sub.HasStarted() and not sub.HasEnded():
                        sub.RollBack()
                    notes.append("donen kol kurulamadi ({}); ana kol duz kuruldu".format(ex))
            if not built:
                fit = _fit(stairs, height, s, stype, 0, width)
                notes += _straight(ctx, stairs_id, s, width, z)
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
        notes.insert(0, "{} riht x {:.1f} cm, basamak {:.1f} cm (taranan kol uzunluguna "
                        "sigdirildi)".format(fit["risers"], _cm(stairs_calc.riser_ft(height, fit["risers"])),
                                             _cm(fit["tread_ft"])))
        min_tread = _attr(stype, "MinTreadDepth")
        if min_tread and fit["tread_ft"] < min_tread - 1e-6:
            notes.append("basamak tipin alt siniri {:.1f} cm'nin altinda (merdiven dik)".format(
                _cm(min_tread)))
        if width > float(s["width_ft"]) + 1e-6:
            notes.append("genislik tipin alt siniri {:.0f} cm'ye cikarildi".format(_cm(width)))
        if s.get("direction_status") != "olculdu":
            notes.append("cikis yonu varsayildi")
        ctx.report.add("created", "stairs", sid, "; ".join(notes))
        ctx.report.warnings.append(u"Merdiven {}: {}".format(sid, "; ".join(notes)))
