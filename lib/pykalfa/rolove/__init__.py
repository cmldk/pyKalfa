# -*- coding: utf-8 -*-
"""Rolove Aktar - Revit tarafi (IronPython 2.7).

Polycam taramasindan `pysrc/rolove/prepare_rolove_input.py`'nin urettigi
`rolove_input.json`'u okuyup Level / Wall / kapi-pencere / Opening / Room
olusturur. Uretilen her eleman kararli bir id ile (Extensible Storage)
etiketlenir; proje defteri (`ledger`) ProjectInformation'da tutulur, boylece
yeniden calistirmada var olanlar korunur, kullanicinin sildikleri yeniden
olusturulmaz.

`ledger` saf Python'dur (CPython testlerinden de import edilir); diger
moduller Revit API'si ister.
"""
