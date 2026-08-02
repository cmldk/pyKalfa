# -*- coding: utf-8 -*-
"""Kuruluma ozel dosya logu (`install.log`).

pyRevit'in kendi log penceresinden (`script.get_logger()`) AYRIDIR: bu log
`startup.py` sirasinda calisir ve o an pyRevit'in log penceresi henuz acik
olmayabilir; kurulum basarisiz olursa kullaniciya "ayrintilar icin
install.log'a bakin" diyebilmek icin diske yazan ayri, kalici bir kayit
gerekir.
"""

import logging
import os

from pykalfa.installer import env_location

_logger = None


def get_file_logger():
    global _logger
    if _logger is not None:
        return _logger

    if not os.path.isdir(env_location.root()):
        try:
            os.makedirs(env_location.root())
        except OSError:
            pass

    logger = logging.getLogger("pykalfa.installer")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        try:
            handler = logging.FileHandler(env_location.install_log_path())
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            )
            logger.addHandler(handler)
        except (IOError, OSError):
            # Log dosyasi yazilamiyorsa (ör. yetki sorunu) sessizce devam
            # et -- pyRevit'in kendi logu zaten ayrica calisiyor.
            pass
    _logger = logger
    return logger
