# -*- coding: utf-8 -*-
"""Rolove Prototip - oda ayiricilari (Room Separation Line) asamasi.

Polycam acik plani (ör. mutfak + salon) aralarinda duvar olmayan iki oda
olarak cizer. Revit duvarla ayrilmamis odalari tek alan sayar ve birini
"Redundant Room" yapar (oda olusmaz). `data["room_separations"]`
(`pysrc/rolove/prototype.room_separations`) duvarsiz kenarlara ayirici
koyar; odalardan ONCE calisir. Defter mantigi diger elemanlarla ayni.

IronPython 2.7.
"""

from Autodesk.Revit.DB import (
    CurveArray,
    FilteredElementCollector,
    Line,
    Plane,
    SketchPlane,
    ViewPlan,
    ViewType,
    XYZ,
)


def _plan_view(doc, level):
    for v in FilteredElementCollector(doc).OfClass(ViewPlan):
        if v.IsTemplate or v.ViewType != ViewType.FloorPlan:
            continue
        gl = v.GenLevel
        if gl is not None and gl.Id == level.Id:
            return v
    return None


def stage_separations(ctx):
    seps = ctx.data.get("room_separations") or []
    plan = ctx.plan([s["id"] for s in seps])
    planes = {}
    for s in seps:
        sid = s["id"]
        if sid in plan["keep"]:
            ctx.report.add("kept", "separation", sid)
            continue
        if sid in plan["deleted"]:
            ctx.report.add("deleted", "separation", sid, "kullanici silmis")
            continue
        level = ctx.levels.get(s["floor"])
        if level is None:
            ctx.report.add("failed", "separation", sid, "katin Level'i yok")
            continue
        try:
            if s["floor"] not in planes:
                view = _plan_view(ctx.doc, level)
                sp = SketchPlane.Create(ctx.doc, Plane.CreateByNormalAndOrigin(
                    XYZ.BasisZ, XYZ(0, 0, level.Elevation)))
                planes[s["floor"]] = (view, sp)
            view, sp = planes[s["floor"]]
            if view is None:
                ctx.report.add("failed", "separation", sid, "katin plan gorunumu yok")
                continue
            z = level.Elevation
            curves = CurveArray()
            curves.Append(Line.CreateBound(XYZ(s["start_ft"][0], s["start_ft"][1], z),
                                           XYZ(s["end_ft"][0], s["end_ft"][1], z)))
            created = ctx.doc.Create.NewRoomBoundaryLines(sp, curves, view)
            el = None
            for c in created:
                el = c
                break
            if el is None:
                raise RuntimeError("Revit ayirici olusturmadi")
        except Exception as ex:  # noqa: BLE001 - eleman hatasi raporlanir
            ctx.report.add("failed", "separation", sid, str(ex))
            continue
        ctx.remember(sid, el)
        ctx.report.add("created", "separation", sid)
