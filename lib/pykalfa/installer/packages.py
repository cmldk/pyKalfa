# -*- coding: utf-8 -*-
"""`requirements.txt` kurulumu ve icerik hash'i.

Hash, `installer.state` tarafindan "env/ hala guncel mi" kontrolunde
kullanilir: `requirements.txt` degismedigi surece pip tekrar calistirilmaz.
"""

import hashlib
import os

from pykalfa import paths
from pykalfa.subproc import run_process

# pip'in gercek indirme yuzdesini guvenilir sekilde ayristirmak riskli
# (surume gore cikti formati degisebilir); onun yerine kurulum sirasinda
# gelen her yeni log satirinda cubugu 1 puan ilerletip bu tavanda
# "bekletiyoruz" (sahte ama canli bir ilerleme hissi); islem bitince
# cagiran taraf cubugu %100'e atlar.
PIP_INSTALL_PROGRESS_CAP = 95


def requirements_hash():
    """`requirements.txt` icindeki bagimlilik listesinin sha256 hash'i."""
    with open(paths.requirements_file(), "rb") as f:
        content = f.read()
    return hashlib.sha256(content).hexdigest()


def install(env_root, on_line=None, on_poll=None):
    """`env_root` altindaki CPython ile `requirements.txt`'i kurar.
    (exit_code, birlesik_cikti) dondurur.

    `pip.exe` yerine `python.exe -m pip`: pip.exe baslaticisi icinde
    venv olusturuldugu andaki mutlak yolu tasir, klasor tasinirsa
    yanlis ortama kurulum yapabilir. `-m pip` her zaman calisan
    yorumlayicinin ortamini hedefler.

    `on_poll` MUTLAKA verilmelidir (bkz. `subproc.run_process`): verilmezse
    ana iş parcacigi bloklayan `WaitForExit()`'e duser ve kurulum boyunca
    (dakikalarca) hicbir pencere repaint edilemez."""
    python_exe = os.path.join(env_root, "Scripts", "python.exe")
    return run_process(
        python_exe,
        ["-m", "pip", "install", "-r", paths.requirements_file()],
        on_line=on_line,
        on_poll=on_poll,
    )
