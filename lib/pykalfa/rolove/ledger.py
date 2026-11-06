# -*- coding: utf-8 -*-
"""Rolove defteri: hangi kararli id hangi Revit elemanina (UniqueId) donustu.

Saf Python (IronPython 2.7 + CPython 3); Revit import'u yok, boylece
`pysrc/rolove/selftest.py` Revit olmadan test eder.

Bicim:
    {"version": 1, "sources": [<kaynak anahtari>, ...],
     "items": {<kararli id>: <UniqueId>}}
"""

import json

VERSION = 1


def empty():
    return {"version": VERSION, "sources": [], "items": {}}


def dumps(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def loads(s):
    """Bozuk / bos / eksik alanli metin -> `empty()` (defter hicbir zaman
    akisi durdurmaz; en kotu ihtimalle her sey 'yeni' sayilir)."""
    if not s:
        return empty()
    try:
        d = json.loads(s)
    except (ValueError, TypeError):
        return empty()
    if (not isinstance(d, dict) or not isinstance(d.get("items"), dict)
            or not isinstance(d.get("sources"), list)):
        return empty()
    out = empty()
    out["sources"] = [x for x in d["sources"]]
    out["items"] = dict((k, v) for k, v in d["items"].items())
    return out


def plan_actions(item_ids, ledger_items, existing_unique_ids):
    """Her kararli id icin ne yapilacagi (girdi sirasi korunur):

    - defterde yok                      -> "create"
    - defterde var, eleman duruyor      -> "keep"
    - defterde var, eleman silinmis     -> "deleted" (yeniden olusturulmaz)
    """
    existing = set(existing_unique_ids)
    result = {"create": [], "keep": [], "deleted": []}
    for sid in item_ids:
        uid = ledger_items.get(sid)
        if uid is None:
            result["create"].append(sid)
        elif uid in existing:
            result["keep"].append(sid)
        else:
            result["deleted"].append(sid)
    return result
