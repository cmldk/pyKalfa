# -*- coding: utf-8 -*-
"""Extension icindeki standart klasor/dosya yollari.

Butun islevler ayni duzeni paylasir:

    pyKalfa.extension/
      lib/pykalfa/        <- bu paket (Revit tarafi, IronPython)
      pyKalfa.tab/        <- panel/buton tanimlari
      pysrc/<islev>/      <- islev bazli CPython kodu (venv icinde calisir)
      output/             <- gecici ara dosyalar (her calistirmada yeniden uretilir)
      requirements.txt    <- ortak sanal ortam (env/) icin bagimliliklar

Yollar bu modulun KENDI konumundan turetilir (`lib/pykalfa/paths.py` ->
uc ust klasor extension kokudur); boylece hicbir buton, kac klasor
derinde oldugunu bilmek zorunda kalmaz ve extension tasinsa/yeniden
adlandirilsa da yollar bozulmaz.

Istisna `env/`: MAX_PATH sorunlarindan kacinmak icin extension'in
ICINDE DEGIL, sabit bir sistem yolunda tutulur -- bkz. `python_exe()` ve
`installer.env_location`.
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

    `env/`, extension'in kendi klasorunun ICINDE DEGIL, sabit ve kisa bir
    sistem yolunda tutulur (bkz. `installer.env_location`) -- boylece
    extension GitHub'dan ne kadar derin bir yola klonlanirsa klonlansin,
    pip'in kurdugu paketler (ör. OCR kutuphanesi) Windows'un 260 karakter
    MAX_PATH sinirina takilmaz.

    Var olup olmadigi KONTROL EDILMEZ; ilk calistirmada henuz kurulmamis
    olabilir (bkz. `installer.orchestrator.ensure_installed`)."""
    from pykalfa.installer import env_location
    return env_location.python_exe_path()


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
