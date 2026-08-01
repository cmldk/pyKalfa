# -*- coding: utf-8 -*-
"""pyKalfa - butonlarin ortak kullandigi yardimci kutuphane.

pyRevit, bir extension'in `lib/` klasorunu otomatik olarak `sys.path`'e
ekler; bu yuzden her pushbutton scripti dogrudan `from pykalfa import ...`
diyebilir -- goreli yol/`sys.path` oynamasina gerek yoktur.

Modul dagilimi (butun butonlar icin ortak):

  - `paths`      : extension icindeki standart klasor/dosya yollari
  - `subproc`    : alt-surec (exe) calistirma
  - `bootstrap`  : `env/` sanal ortaminin ilk kurulumu
  - `revitutils` : Revit API'siyle calisirken tekrar eden kucuk yardimcilar
  - `selectors`  : projedeki mevcut stilleri (line style, filled region,
                   text note, ...) kullaniciya sectirme

Butona OZEL is mantigi buraya konmaz: o, ilgili pushbutton klasorundeki
`script.py`'de (Revit tarafi) ve `pysrc/<islev>/` altinda (goruntu isleme
gibi agir CPython isleri) durur.

IronPython 2.7 uyumlu yazilmistir (pyRevit'in varsayilan motoru).
"""
