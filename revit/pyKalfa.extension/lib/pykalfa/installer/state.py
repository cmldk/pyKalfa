# -*- coding: utf-8 -*-
"""Kurulum durumu (`install.json`): hangi `requirements.txt` surumunun
kurulu oldugunu tutar.

Bu, sadece "python.exe var mi" kontrolunden farkli olarak,
`requirements.txt` sonradan degistiginde (ör. yeni bir paket eklendiginde)
`env/`'in otomatik olarak guncellenmesini saglar -- venv'i silip yeniden
kurmadan, sadece `pip install` tekrar calistirilarak.
"""

import json
import os

from pykalfa.installer import env_location


def is_up_to_date(current_hash):
    """`env/` kurulu VE en son kurulan `requirements.txt` hash'i
    `current_hash` ile ayniysa True doner."""
    if not os.path.isfile(env_location.python_exe_path()):
        return False
    saved = _read()
    if saved is None:
        return False
    return saved.get("requirements_hash") == current_hash


def save(requirements_hash):
    with open(env_location.install_state_path(), "w") as f:
        json.dump({"requirements_hash": requirements_hash, "installed": True}, f)


def _read():
    path = env_location.install_state_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (IOError, ValueError):
        return None
