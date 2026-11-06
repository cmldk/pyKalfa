# -*- coding: utf-8 -*-
"""pyKalfa / Rolove Aktar: Polycam taramasi -> bos projede hizli rolove

Akis:

  1. Numarali girdiler secilir (`ui.pick_inputs`): Input 1 kat plani
     (.dxf / kat plani .zip), Input 2 oda listesi (.csv), Input 3 nokta
     bulutu (.laz/.las, georef kapali), Input 4 3B model (.glb). Input 1'le
     ayni adli digerleri onerilir; her biri ayrica degistirilebilir.
  2. `env/` CPython'u ile `pysrc/rolove/prepare_rolove_input.py` calisir
     (ilerleme cubugu, `PROGRESS|yuzde|mesaj`): katlar taramaya hizalanir,
     duvar yuzleri LAZ'dan olculur, `output/rolove_input.json` + kat
     PNG'leri yazilir. Cikis 2 = eksik girdi -> ne export edilecegi
     soylenir.
  3. Ozet / onay (kotlar duzenlenebilir), duvar tipleri ve kapi/pencere
     aileleri secilir.
  4. `creator.create_all` tek TransactionGroup'ta uretir; rapor basilir.

IronPython 2.7 uyumlu (pyRevit'in varsayilan motoru).
"""

import json
import os
import traceback

from pyrevit import forms, revit, script

from pykalfa import bootstrap, paths
from pykalfa.rolove import creator, inputs, ui
from pykalfa.subproc import run_python

logger = script.get_logger()
output = script.get_output()

FEATURE = "rolove"
doc = revit.doc
app = doc.Application

if doc.IsFamilyDocument:
    forms.alert("Rolove Aktar bir proje belgesinde calisir (aile belgesinde degil).",
                title="Rolove Aktar", exitscript=True)

bootstrap.ensure_env()

OUTPUT_DIR = paths.output_dir()
PREPARE_SCRIPT = paths.pysrc_script(FEATURE, "prepare_rolove_input.py")
JSON_PATH = os.path.join(OUTPUT_DIR, "rolove_input.json")

selection = ui.pick_inputs()
logger.info("Girdiler: {}".format(selection))

if os.path.isfile(JSON_PATH):
    try:
        os.remove(JSON_PATH)            # eski calistirmanin sonucu okunmasin
    except Exception as ex:  # noqa: BLE001
        logger.debug("Eski JSON silinemedi: {}".format(ex))

# --- Hazirlik (CPython alt sureci) -----------------------------------------
# PROGRESS satirlari .NET okuma is parcaciklarindan gelir: yalniz duruma
# yazilir, cubuk ana is parcacigindaki `_tick` ile guncellenir.
state = {"percent": 0, "message": "Baslatiliyor", "dirty": True}


def _on_line(line):
    if line.startswith("PROGRESS|"):
        parts = line.split("|", 2)
        try:
            state["percent"] = int(parts[1])
        except (IndexError, ValueError):
            return
        state["message"] = parts[2] if len(parts) > 2 else ""
        state["dirty"] = True
    else:
        logger.debug(line)


with forms.ProgressBar(title="Tarama hazirlaniyor: {value}%", indeterminate=False) as pb:
    pb.update_progress(0, 100)

    def _tick():
        if state["dirty"]:
            state["dirty"] = False
            logger.info("{} (%{})".format(state["message"], state["percent"]))
            try:
                pb.title = "{} : {{value}}%".format(state["message"])
            except Exception:  # noqa: BLE001 - pyRevit surum farki
                pass
            pb.update_progress(state["percent"], 100)

    exit_code, proc_output = run_python(
        PREPARE_SCRIPT, inputs.cli_args(selection) + ["--output-dir", OUTPUT_DIR],
        on_line=_on_line, on_poll=_tick)
    pb.update_progress(100, 100)

logger.info("prepare_rolove_input.py cikti:\n{}".format(proc_output))

if exit_code not in (0, 2) or not os.path.isfile(JSON_PATH):
    forms.alert("Hazirlik basarisiz (exit code {}).\n\n{}".format(exit_code, proc_output[-3000:]),
                title="pyKalfa hata", exitscript=True)

with open(JSON_PATH, "r") as f:
    data = json.load(f)

if exit_code == 2 or data.get("missing"):
    ui.show_missing(data)

if not data.get("walls"):
    forms.alert("Hicbir kat taramaya hizalanamadi; olusturulacak duvar yok.\n\n" +
                "\n".join("Kat {}: {}".format(a["floor"], a["reason"])
                          for a in data.get("alignment", [])),
                title="Rolove Aktar", exitscript=True)

# --- Ozet, kotlar, secimler ------------------------------------------------
level_overrides = {}
plan = creator.preview_plan(doc, data)
while ui.summary_and_confirm(data, plan) == "edit":
    level_overrides.update(ui.edit_levels(data))

try:
    choices = ui.pick_choices(doc, data)
    choices.level_overrides = level_overrides
except Exception as ex:  # noqa: BLE001
    forms.alert("Secimler alinirken hata:\n{}\n\n{}".format(ex, traceback.format_exc()),
                title="pyKalfa hata", exitscript=True)

# --- Olusturma -------------------------------------------------------------
try:
    report = creator.create_all(doc, app, data, choices)
except Exception as ex:  # noqa: BLE001
    forms.alert("Islem geri alindi, hata olustu:\n{}\n\n{}".format(ex, traceback.format_exc()),
                title="pyKalfa hata", exitscript=True)

logger.info("Rolove: {} olusturuldu, {} korundu, {} silinmis, {} basarisiz, {:.1f} s".format(
    len(report.created), len(report.kept), len(report.deleted), len(report.failed),
    report.seconds))

# Basarida ara JSON silinir (her calistirmada yeniden uretilir); PNG'ler kalir.
if not report.failed:
    try:
        os.remove(JSON_PATH)
    except Exception as ex:  # noqa: BLE001
        logger.debug("Gecici dosya silinemedi: {}".format(ex))

ui.show_report(report, data, output)
