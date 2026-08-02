# -*- coding: utf-8 -*-
"""pyKalfa kurulum baslangici.

pyRevit bu dosyayi extension her yuklendiginde/reload edildiginde otomatik
CALISTIRIR (pyRevit'in extension `startup.py` mekanizmasi). Amac: kullanici
hicbir `.bat`/`.ps1` calistirmadan, sadece bu extension'i (ör. GitHub'dan)
pyRevit'e Custom Extension Folder olarak ekleyip Revit'i actiginda/reload
ettiginde kurulumun kendiliginden tamamlanmasi.

`env/` zaten guncelse (neredeyse her zaman) bu, milisaniyeler icinde biten
bir hash kontrolunden ibarettir. Ilk kurulumda veya `requirements.txt`
degistiginde ise pip kurulumu burada, SENKRON olarak calisir -- pyRevit bu
extension'i yuklemeyi o sure boyunca bekletir (bilinen ve kabul edilen bir
odun; bkz. `installer/orchestrator.py`).
"""

from pykalfa.installer.orchestrator import bootstrap

bootstrap()
