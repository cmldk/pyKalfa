# -*- coding: utf-8 -*-
"""Extension icindeki standart klasor/dosya yollari.

Butun islevler ayni duzeni paylasir:

    pyKalfa.extension/
      lib/pykalfa/        <- bu paket (Revit tarafi, IronPython)
      pyKalfa.tab/        <- panel/buton tanimlari
      pysrc/<islev>/      <- islev bazli CPython kodu (venv icinde calisir)
      env/                <- butun islevlerin paylastigi sanal ortam
      output/             <- gecici ara dosyalar (her calistirmada yeniden uretilir)
      requirements.txt    <- env/ icin bagimliliklar

Yollar bu modulun KENDI konumundan turetilir (`lib/pykalfa/paths.py` ->
uc ust klasor extension kokudur); boylece hicbir buton, kac klasor
derinde oldugunu bilmek zorunda kalmaz ve extension tasinsa/yeniden
adlandirilsa da yollar bozulmaz.
"""

import os

# lib/pykalfa/paths.py -> lib/pykalfa -> lib -> <extension kokü>
EXTENSION_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def extension_root():
    """`pyKalfa.extension` klasorunun tam yolu."""
    return EXTENSION_ROOT


def python_exe():
    """Ortak sanal ortamin (`env/`) CPython yorumlayicisi.

    Var olup olmadigi KONTROL EDILMEZ; ilk calistirmada henuz kurulmamis
    olabilir (bkz. `bootstrap.ensure_env`)."""
    return os.path.join(EXTENSION_ROOT, "env", "Scripts", "python.exe")


def requirements_file():
    return os.path.join(EXTENSION_ROOT, "requirements.txt")


def pysrc_dir(feature):
    """Bir islevin CPython kodunun bulundugu klasor (ör. "parsel_bina")."""
    return os.path.join(EXTENSION_ROOT, "pysrc", feature)


def pysrc_script(feature, script_name):
    """Bir islevin CPython scriptinin tam yolu.

    Ör: `pysrc_script("parsel_bina", "prepare_revit_input.py")`."""
    return os.path.join(pysrc_dir(feature), script_name)


def output_dir(ensure=True):
    """Gecici ara dosyalarin yazildigi ortak klasor.

    `ensure=True` ise klasor yoksa olusturulur (temiz bir kopyada
    `output/` bos oldugu icin surum kontrolunde bulunmayabilir)."""
    path = os.path.join(EXTENSION_ROOT, "output")
    if ensure and not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            # Yarista baska bir surec olusturmus olabilir; sorun degil.
            pass
    return path
