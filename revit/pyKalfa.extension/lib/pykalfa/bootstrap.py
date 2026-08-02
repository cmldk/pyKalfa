# -*- coding: utf-8 -*-
"""Geriye donuk uyumluluk katmani.

Asil kurulum artik `startup.py` araciligiyla, pyRevit extension'i her
yukledigin/reload ettiginde EAGER olarak yapiliyor (bkz.
`installer.orchestrator.bootstrap`). Bu modul, mevcut buton kodlarinin
(`ImportGeometry.pushbutton`, `DuvarAktar.pushbutton`) hala cagirdigi
`ensure_env()` fonksiyonunu, imzasini degistirmeden korur: `env/` herhangi
bir sebeple eksik/guncel degilse (ör. `startup.py` hic calismadi, kullanici
`C:\\pyKalfa\\env` klasorunu sildi) butona basildigi anda tamamlayan bir
GUVENLIK AGI olarak calismaya devam eder.
"""

from pyrevit import forms

from pykalfa.installer.orchestrator import ensure_installed


def ensure_env():
    """`env/` hazir degilse kurar. Kurulum basarisiz olursa scripti
    sonlandirir."""
    ok, error = ensure_installed()
    if not ok:
        forms.alert(
            "Otomatik kurulum basarisiz oldu:\n\n{}".format(error),
            title="pyKalfa hata",
            exitscript=True,
        )
