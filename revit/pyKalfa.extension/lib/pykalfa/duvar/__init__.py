# -*- coding: utf-8 -*-
"""pyKalfa / Duvar - "Duvar Aktar" islevinin Revit (IronPython) tarafi.

Bu alt paket SADECE bu isleve aittir; butun butonlarin paylastigi kod
bir ust klasordedir (`pykalfa.paths`, `pykalfa.selectors`, ...).

  - `ui.py`            : kullanicidan girdi toplama (dosya, yukseklik,
                         level, wall type, katman filtresi, onaylar)
  - `revit_creator.py` : duvar adaylarindan gercek `Wall` olusturma ve
                         basarisiz olanlarin raporlanmasi

Cizim tarafi (DXF okuma, temizleme, duvar karari) burada degil,
`pysrc/duvar/` altinda CPython ile yapilir -- ezdxf IronPython 2.7'de
calismaz.
"""
