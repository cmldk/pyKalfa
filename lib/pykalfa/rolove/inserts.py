# -*- coding: utf-8 -*-
"""Kapi/pencere yerlesim noktasi (saf Python; IronPython 2.7 + CPython 3).

Dis duvarin JSON hatti taranan IC YUZDUR (Location Line = Finish Face:
Interior). Nokta bu hatta birakilirsa duvarin yuzeyinde kalir; Revit
elemani host'a baglar ama duvara oturtamaz ve duvari KESMEZ ("Pick New
Host" ile duzeliyordu). Bu yuzden dis duvarda nokta, duvar kalinliginin
yarisi kadar disa (`outward`), yani duvar eksenine tasinir.
"""

import math


def insert_point_ft(w, offset_ft, wall_width_ft):
    """(x, y) feet: duvar hatti boyunca `offset_ft`, dis duvarda eksene kaydirilmis."""
    (x1, y1), (x2, y2) = w["start_ft"], w["end_ft"]
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    x, y = x1 + ux * offset_ft, y1 + uy * offset_ft
    if w.get("location") == "interior_face" and w.get("outward"):
        half = float(wall_width_ft) / 2.0
        x += float(w["outward"][0]) * half
        y += float(w["outward"][1]) * half
    return x, y
