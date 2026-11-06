# -*- coding: utf-8 -*-
"""Dis duvar eksenleri (saf Python; Revit import'u yok, CPython'dan test edilir).

JSON'da dis duvarin `line`'i taranan IC YUZDUR. Revit `Wall.Create` ekseni
(centerline) ister: eksen = ic yuz + outward * W/2. Iki dis duvarin ic
yuzleri bir C kosesinde bulusuyorsa, ayri ayri otelenmis eksenlerin uclari
W/sqrt(2) kadar ayrik kalir ve Revit duvarlari birlestiremez (kosede
centik). Bu modul, uclari bulusan dis duvarlarin eksenlerini kesisim
noktasina uzatir/kisaltir; boylece Revit kendiliginden birlestirir ve ic
yuzler yine C'de bulusur.

Doner: {id: {"axis": [a, b], "face": [a', b']}} — `axis` Wall.Create icin,
`face` ayni uclarin ic yuzdeki karsiligi (Location Line = Finish Face:
Interior yapildiktan sonraki beklenen konum, dogrulama icin).
"""

import math

PARALLEL_SIN = math.sin(math.radians(1.0))


def _intersect(a1, a2, b1, b2):
    d1x, d1y = a2[0] - a1[0], a2[1] - a1[1]
    d2x, d2y = b2[0] - b1[0], b2[1] - b1[1]
    den = d1x * d2y - d1y * d2x
    l1, l2 = math.hypot(d1x, d1y), math.hypot(d2x, d2y)
    if l1 == 0 or l2 == 0 or abs(den) / (l1 * l2) < PARALLEL_SIN:
        return None
    s = ((b1[0] - a1[0]) * d2y - (b1[1] - a1[1]) * d2x) / den
    return (a1[0] + d1x * s, a1[1] + d1y * s)


def _r(p):
    return (round(p[0], 9) + 0.0, round(p[1], 9) + 0.0)


def exterior_axes(walls, width_ft, tol_ft):
    half = width_ft / 2.0
    ext = [w for w in walls if w.get("location") == "interior_face" and w.get("outward")]
    faces = {}
    axes = {}
    for w in ext:
        ox, oy = w["outward"][0] * half, w["outward"][1] * half
        f = [tuple(w["start_ft"]), tuple(w["end_ft"])]
        faces[w["id"]] = f
        axes[w["id"]] = [(f[0][0] + ox, f[0][1] + oy), (f[1][0] + ox, f[1][1] + oy)]

    new_axes = dict((k, list(v)) for k, v in axes.items())
    for w in ext:
        for k in (0, 1):
            p = faces[w["id"]][k]
            for v in ext:
                if v["id"] == w["id"]:
                    continue
                if not any(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol_ft
                           for q in faces[v["id"]]):
                    continue
                aw, av = axes[w["id"]], axes[v["id"]]
                x = _intersect(aw[0], aw[1], av[0], av[1])
                if x is None or math.hypot(x[0] - aw[k][0], x[1] - aw[k][1]) > 4 * width_ft:
                    continue
                new_axes[w["id"]][k] = x
                break

    out = {}
    for w in ext:
        ox, oy = w["outward"][0] * half, w["outward"][1] * half
        axis = [_r(p) for p in new_axes[w["id"]]]
        out[w["id"]] = {"axis": axis, "face": [_r((p[0] - ox, p[1] - oy)) for p in axis]}
    return out
