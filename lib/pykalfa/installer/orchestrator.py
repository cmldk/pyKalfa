# -*- coding: utf-8 -*-
"""Kurulum akisinin orkestrasyonu: `env_location` + `venv` + `packages` +
`state` + `logger` modullerini bir araya getirir.

Iki cagiran vardir:

- `startup.py` (extension koku): pyRevit bunu extension her
  yuklendiginde/reload edildiginde CALISTIRIR -- asil (eager) kurulum
  burasidir.
- `pykalfa.bootstrap.ensure_env()`: butonlarin cagirdigi guvenlik agi --
  `startup.py` herhangi bir sebeple calismadiysa veya `env/` sonradan
  silindiyse, butona basildigi anda tamamlar.

Ikisi de ayni `ensure_installed()`'i cagirir; tekil kurulum mantigi
buradadir.
"""

from pyrevit import forms, script

from pykalfa.installer import env_location, packages, state, venv
from pykalfa.installer import logger as install_logger

logger = script.get_logger()

# `venv` olusturulduktan sonra, pip kurulumuna girerken cubugun degeri.
PIP_PROGRESS_START = 20

# `venv` olusturulurken (0 -> 19) kac yoklamada bir 1 puan ilerlensin.
# `python -m venv` icinde `ensurepip` calistirdigi icin genelde 5-15
# saniye surer; ~0.6 sn/puan ile 19 puan ~11 saniyeye yayilir, boylece
# cubuk adimin ortasinda tavana vurup donmus gorunmez.
VENV_CREEP_EVERY_TICKS = 3

# pip'ten yeni satir gelmeyen kac yoklamada bir cubuk 1 puan ilerlesin
# (yoklama araligi ~200 ms -> ~4 saniyede 1 puan). Gercek indirme yuzdesi
# bilinemez; bu, "calisiyorum" sinyali veren kasitli olarak yaklasik bir
# gostergedir.
PIP_CREEP_EVERY_TICKS = 20


def ensure_installed():
    """`env/` kurulu ve guncel degilse (sifirdan veya `requirements.txt`
    degismisse) kurar. (True, None) veya (False, hata_mesaji) dondurur.

    `env/` zaten guncelse (neredeyse her zaman -- `startup.py` bunu
    onceden hallettigi icin) bu, bir hash karsilastirmasindan ibarettir ve
    aninda doner."""
    current_hash = packages.requirements_hash()
    if state.is_up_to_date(current_hash):
        return True, None

    forms.alert(
        "pyKalfa ilk kurulum/guncelleme yapiliyor. Bu birkac dakika "
        "surebilir; pencere kapaninca islem otomatik devam edecek.",
        title="pyKalfa - kurulum",
    )

    file_logger = install_logger.get_file_logger()
    env_root = env_location.env_dir()
    file_logger.info("Kurulum/guncelleme baslatiliyor (env: {})".format(env_root))

    system_python = venv.find_system_python()
    if not system_python:
        error = (
            "Sistemde calisan bir Python bulunamadi (PATH'te 'py'/'python' "
            "yok). Once python.org uzerinden Python 3 kurun (kurulum "
            "sihirbazinda 'Add python.exe to PATH' kutusunu isaretleyin), "
            "sonra Revit'i yeniden baslatin."
        )
        file_logger.error(error)
        return False, error

    with forms.ProgressBar(title="pyKalfa kurulum: {value}%") as pb:
        pb.update_progress(0, 100)

        # `venv` olusturma birkac saniye surer (ensurepip); cubugun o
        # sirada da canli kalmasi icin ana iş parcacigindan yoklaniyor.
        venv_progress = {"value": 0, "ticks": 0}

        def _venv_tick():
            venv_progress["ticks"] += 1
            if (venv_progress["ticks"] % VENV_CREEP_EVERY_TICKS == 0
                    and venv_progress["value"] < PIP_PROGRESS_START - 1):
                venv_progress["value"] += 1
            pb.update_progress(venv_progress["value"], 100)

        ok, error = venv.create_if_missing(
            env_root, system_python, on_poll=_venv_tick
        )
        if not ok:
            file_logger.error(error)
            return False, error
        pb.update_progress(PIP_PROGRESS_START, 100)

        progress = {
            "lines": 0,                    # arka plan iş parcacigi artirir
            "seen": 0,                     # ana iş parcaciginin gordugu son deger
            "display": PIP_PROGRESS_START,
            "idle_ticks": 0,
        }

        def _on_pip_line(line):
            # ARKA PLAN iş parcacigindan cagirilir (bkz. subproc.run_process).
            # Burada SADECE veri saklanir/dosyaya loglanir; arayuze
            # DOKUNULMAZ. `forms.ProgressBar` WPF tabanlidir ve baska bir iş
            # parcacigindan guncellenemez -- denenirse firlattigi istisna
            # `run_process` icinde yutulur ve cubuk sessizce donar (kurulumun
            # "%20'de takili kalmasi" tam olarak buydu).
            file_logger.info(line)
            progress["lines"] += 1

        def _tick():
            # ANA iş parcacigindan cagirilir: arayuzu guncellemenin dogru yeri.
            if progress["lines"] > progress["seen"]:
                progress["seen"] = progress["lines"]
                progress["idle_ticks"] = 0
                advance = True
            else:
                # pip, buyuk paketleri (torch ~1-1.5 GB) indirirken
                # DAKIKALARCA hic satir basmaz; cubuk sadece satir basina
                # ilerleseydi o sure boyunca donmus gorunurdu. Satir
                # gelmeyen turlarda da yavasca ilerletiyoruz.
                progress["idle_ticks"] += 1
                advance = progress["idle_ticks"] >= PIP_CREEP_EVERY_TICKS
                if advance:
                    progress["idle_ticks"] = 0
            if advance and progress["display"] < packages.PIP_INSTALL_PROGRESS_CAP:
                progress["display"] += 1
            # Deger degismese bile her turda cagiriliyor: pencerenin
            # repaint edilip "yanit vermiyor" durumuna dusmemesi icin.
            pb.update_progress(progress["display"], 100)

        exit_code, out = packages.install(
            env_root, on_line=_on_pip_line, on_poll=_tick
        )
        if exit_code != 0:
            error = "Bagimliliklar kurulamadi:\n{}".format(out)
            file_logger.error(error)
            return False, error
        pb.update_progress(100, 100)

    state.save(current_hash)
    file_logger.info("Kurulum tamamlandi.")
    return True, None


def bootstrap():
    """`startup.py` tarafindan cagirilir: pyRevit extension'i her
    yukledigin/reload ettiginde CALISIR.

    Bilinen odun: ilk kurulumda (veya `requirements.txt` guncellendiginde)
    bu fonksiyon birkac dakika surebilir ve pyRevit'in bu extension'i
    yuklemesini o sure boyunca bloke eder. Karsiligi: kullanicinin hicbir
    `.bat`/`.ps1` calistirmasina, hatta bir butona basmasina bile gerek
    kalmamasidir -- Revit'i actiginda kurulum kendiliginden biter."""
    ok, error = ensure_installed()
    if not ok:
        forms.alert(
            "pyKalfa otomatik kurulumu basarisiz oldu:\n\n{}\n\n"
            "Ayrintilar icin: {}".format(error, env_location.install_log_path()),
            title="pyKalfa hata",
        )
