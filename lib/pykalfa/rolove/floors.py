# -*- coding: utf-8 -*-
"""Rolove Prototip - doseme asamasi (`creator.create_all` icinden).

`data["floors"]` her ogesi: {"id", "floor", "loops_ft": [dis halka, delikler...],
"area_m2"}. Ust yuzu katin Level kotunda, kalinlik asagi dogru (Floor'un
varsayilani). Defter mantigi duvarlarla ayni: korunur / silinmis geri
gelmez / yeni olusturulur.

IronPython 2.7.
"""

from Autodesk.Revit.DB import CurveLoop, Floor, Line, XYZ
from System.Collections.Generic import List

MIN_EDGE_FT = 0.001 / 0.3048            # 1 mm


def _loop(points, z):
    loop = CurveLoop()
    pts = [XYZ(float(x), float(y), z) for x, y in points]
    kept = []
    for p in pts:
        if not kept or kept[-1].DistanceTo(p) >= MIN_EDGE_FT:
            kept.append(p)
    if len(kept) > 1 and kept[-1].DistanceTo(kept[0]) < MIN_EDGE_FT:
        kept.pop()
    if len(kept) < 3:
        raise ValueError("halka 3 noktadan az")
    for i in range(len(kept)):
        loop.Append(Line.CreateBound(kept[i], kept[(i + 1) % len(kept)]))
    return loop


def stage_floors(ctx):
    floors = ctx.data.get("floors") or []
    plan = ctx.plan([f["id"] for f in floors])
    floor_type = ctx.choices.floor_type
    for f in floors:
        sid = f["id"]
        if sid in plan["keep"]:
            ctx.report.add("kept", "floor", sid)
            continue
        if sid in plan["deleted"]:
            ctx.report.add("deleted", "floor", sid, "kullanici silmis")
            continue
        level = ctx.levels.get(f["floor"])
        if level is None:
            ctx.report.add("failed", "floor", sid, "katin Level'i yok")
            continue
        try:
            loops = List[CurveLoop]([_loop(ring, level.Elevation) for ring in f["loops_ft"]])
            el = Floor.Create(ctx.doc, loops, floor_type.Id, level.Id)
        except Exception as ex:  # noqa: BLE001 - eleman hatasi raporlanir
            ctx.report.add("failed", "floor", sid, str(ex))
            continue
        ctx.remember(sid, el)
        ctx.report.add("created", "floor", sid)
