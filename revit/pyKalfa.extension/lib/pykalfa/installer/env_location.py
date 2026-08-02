# -*- coding: utf-8 -*-
"""`env/` sanal ortaminin kurulacagi SABIT sistem yolu.

`env/`, extension'in kendi klasorunun ICINDE DEGIL, burada tanimli sabit ve
kisa bir yolda tutulur. Sebep: pip'in kurdugu bazi paketlerin (ör. OCR
kutuphanesi) kendi ic dosya adlari zaten cok derin/uzun; extension GitHub'dan
uzun bir yola (ör. `Belgelerim\\Projeler\\...`) klonlanmis olsa bile, `env/`
sabit kisa yolda oldugu icin Windows'un 260 karakterlik MAX_PATH sinirina
hicbir zaman takilmaz.

Bunun onemli bir sonucu var: extension'in KENDISI (`.tab/`, `lib/`, `pysrc/`)
hicbir zaman tasinmaz/kopyalanmaz -- pyRevit onu kullanicinin kaydettigi
Custom Extension Folder'dan calistirmaya devam eder. Sadece agir olan `env/`
buraya kurulur; boylece kullanicinin pyRevit ayarlarinda hicbir sey elle
degistirmesine gerek kalmaz.
"""

import os

FIXED_ROOT = r"C:\pyKalfa"


def root():
    """Kurulum durumunun (env + install.json + install.log) tutuldugu
    sabit kok klasor."""
    return FIXED_ROOT


def env_dir():
    """Sanal ortamin (`venv`) olusturuldugu klasor."""
    return os.path.join(FIXED_ROOT, "env")


def python_exe_path():
    """`env/` icindeki CPython yorumlayicisinin tam yolu.

    Var olup olmadigi KONTROL EDILMEZ; ilk calistirmada henuz kurulmamis
    olabilir (bkz. `installer.orchestrator.ensure_installed`)."""
    return os.path.join(env_dir(), "Scripts", "python.exe")


def install_state_path():
    """Kurulan `requirements.txt` surumunun izini tutan durum dosyasi."""
    return os.path.join(FIXED_ROOT, "install.json")


def install_log_path():
    """Kurulum sirasinda olusan hatalarin/pip ciktisinin yazildigi log
    dosyasi (pyRevit'in kendi log penceresinden BAGIMSIZ -- startup.py
    sirasinda o pencere henuz acik olmayabilir)."""
    return os.path.join(FIXED_ROOT, "install.log")
