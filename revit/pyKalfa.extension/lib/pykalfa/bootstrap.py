# -*- coding: utf-8 -*-
"""`env/` sanal ortaminin ilk kurulumu (butun islevler icin ortak).

Ortam extension'in icindedir ve butun islevler ayni `env/`'i paylasir:
bagimliliklar tek bir `requirements.txt`'te toplanir, boylece kullanici
hangi butona once basarsa bassin tek seferlik bir kurulum yasar.

Kullanici `setup.bat`/`setup.ps1` calistirmadiysa, ilk buton tiklamasinda
`ensure_env()` kurulumu kendisi yapar.
"""

import os

from pyrevit import forms, script

from pykalfa import paths
from pykalfa.subproc import run_process

logger = script.get_logger()

# pip'in gercek indirme yuzdesini guvenilir sekilde ayristirmak riskli
# (surume gore cikti formati degisebilir); bunun yerine kurulum sirasinda
# gelen her yeni log satirinda cubugu 1 puan ilerletip %95'te "bekletiyoruz"
# (sahte ama canli bir ilerleme hissi), islem bitince %100'e atliyoruz.
PIP_INSTALL_PROGRESS_CAP = 95


def find_system_python():
    """venv olusturmak icin sistemde PATH'te calisan bir Python 3
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


def install_env():
    """`env/`'i sifirdan olusturup `requirements.txt`'i kurar; `setup.ps1`
    ile ayni isi yapar. Ilerlemeyi bir `forms.ProgressBar` ile gosterir
    (kaba adimlar + pip kurulumu sirasinda satir-basi canli ilerleme).
    (True, None) veya (False, hata_mesaji) dondurur."""
    root = paths.extension_root()
    with forms.ProgressBar(title="pyKalfa ilk kurulum: {value}%") as pb:
        pb.update_progress(0, 100)

        system_python = find_system_python()
        if not system_python:
            return False, (
                "Sistemde calisan bir Python bulunamadi (PATH'te 'py'/'python' yok). "
                "Once python.org uzerinden Python 3 kurun, sonra tekrar deneyin."
            )
        pb.update_progress(10, 100)

        exit_code, out = run_process(system_python, ["-m", "venv", "env"], cwd=root)
        if exit_code != 0:
            return False, "Sanal ortam (env/) olusturulamadi:\n{}".format(out)
        pb.update_progress(20, 100)

        # `pip.exe` yerine `python.exe -m pip`: pip.exe baslaticisinin
        # icinde venv'in olusturuldugu andaki MUTLAK python yolu gomulu
        # durur, dolayisiyla klasor tasinirsa/yeniden adlandirilirsa
        # yanlis (hatta baska bir projenin) ortamina kurulum yapabilir.
        # `-m pip` her zaman calisan yorumlayicinin ortamini hedefler.
        venv_python = paths.python_exe()

        progress = {"value": 20}

        def _on_pip_line(line):
            logger.info(line)
            if progress["value"] < PIP_INSTALL_PROGRESS_CAP:
                progress["value"] += 1
                pb.update_progress(progress["value"], 100)

        exit_code, out = run_process(
            venv_python,
            ["-m", "pip", "install", "-r", paths.requirements_file()],
            on_line=_on_pip_line,
        )
        if exit_code != 0:
            return False, "Bagimliliklar kurulamadi:\n{}".format(out)
        pb.update_progress(100, 100)

    return True, None


def ensure_env():
    """`env/` hazir degilse kullaniciyi bilgilendirip kurulumu yapar.

    Sadece CPython (goruntu isleme vb.) tarafina ihtiyaci OLAN islevler
    cagirmalidir; saf Revit API'siyle calisan butonlar (ör. cizim
    islevleri) bu agir ortama hic dokunmadan calisabilsin diye kurulum
    buton basinda degil, ihtiyac aninda tetiklenir.

    Kurulum basarisiz olursa scripti sonlandirir."""
    if os.path.isfile(paths.python_exe()):
        return

    logger.info("env/ bulunamadi, ilk kurulum otomatik yapiliyor...")
    forms.alert(
        "Ilk calistirma: goruntu isleme ortami (env/) kuruluyor. "
        "Bu birkac dakika surebilir, pencere kapaninca islem otomatik devam edecek.",
        title="pyKalfa - ilk kurulum",
    )
    ok, error = install_env()
    if not ok:
        forms.alert(
            "Otomatik kurulum basarisiz oldu:\n\n{}\n\n"
            "Elle kurulum icin su klasorde 'setup.ps1' calistirabilirsiniz:\n{}".format(
                error, paths.extension_root()
            ),
            title="pyKalfa hata",
            exitscript=True,
        )
    logger.info("Kurulum tamamlandi.")
