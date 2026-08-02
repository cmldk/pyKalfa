# -*- coding: utf-8 -*-
"""Sistemde bir Python bulma ve sanal ortam (`env/`) olusturma.

Saf dosya/surec islemleri -- arayuz (progress bar, alert) burada YOKTUR,
onu cagiran (`installer.orchestrator`) yonetir.
"""

import os

from pykalfa.subproc import run_process


def find_system_python():
    """`env/` olusturmak icin sistemde PATH'te calisan bir Python 3
    yorumlayicisi arar (`py`, `python`, `python3` sirasiyla denenir).
    Bulunamazsa None doner."""
    for candidate in ("py", "python", "python3"):
        try:
            exit_code, _ = run_process(candidate, ["--version"])
        except Exception:
            continue
        if exit_code == 0:
            return candidate
    return None


def create_if_missing(env_root, system_python, on_poll=None):
    """`env_root`'ta bir venv yoksa olusturur. (True, None) veya
    (False, hata_mesaji) dondurur.

    `on_poll`, arayuzun (ilerleme cubugu) canli kalmasi icin ana iş
    parcacigindan cagirilir: `python -m venv` icinde `ensurepip`
    calistirdigi icin saniyeler surebilir ve o sure boyunca arayuz
    bloke olmamalidir (bkz. `subproc.run_process`)."""
    python_exe = os.path.join(env_root, "Scripts", "python.exe")
    if os.path.isfile(python_exe):
        return True, None

    parent = os.path.dirname(env_root)
    if not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError as ex:
            return False, "Kurulum klasoru olusturulamadi ({}): {}".format(parent, ex)

    exit_code, out = run_process(
        system_python, ["-m", "venv", env_root], on_poll=on_poll
    )
    if exit_code != 0:
        return False, "Sanal ortam (env/) olusturulamadi:\n{}".format(out)
    return True, None
