# -*- coding: utf-8 -*-
"""pyKalfa / Rolove Prototip: Polycam taramasi -> toparlanmis, dosemeli prototip

Akis:

  1. Numarali girdiler secilir (`ui.pick_inputs`).
  2. `pysrc/rolove/prepare_prototype_input.py` (ilerleme cubugu): Rolove
     hazirligi + toparlama (diklestirme, katlar arasi dis duvar hizasi) ->
     `output/prototip_input.json` + kat PNG'leri.
  3. Ozet / onay (eski Rolove Aktar elemanlari varsa uyari), duvar tipleri,
     kapi/pencere aileleri ve doseme tipi secilir.
  4. `pysrc/rolove/prototype_floors.py`: secilen dis duvar kalinligiyla
     doseme hatlari -> `output/prototip_floors.json`.
  5. `creator.create_all` tek TransactionGroup'ta uretir; rapor basilir.

IronPython 2.7 uyumlu (pyRevit'in varsayilan motoru).
"""

import io
import json
import os
import traceback

from pyrevit import forms, revit, script

from pykalfa import bootstrap, paths
from pykalfa.rolove import creator, inputs, proto_ui, ui
from pykalfa.subproc import run_python

logger = script.get_logger()
output = script.get_output()

FEATURE = "rolove"
TITLE = proto_ui.TITLE
doc = revit.doc
app = doc.Application

if doc.IsFamilyDocument:
    forms.alert("Rolove Prototip bir proje belgesinde calisir (aile belgesinde degil).",
                title=TITLE, exitscript=True)

bootstrap.ensure_env()

OUTPUT_DIR = paths.output_dir()
PREPARE_SCRIPT = paths.pysrc_script(FEATURE, "prepare_prototype_input.py")
FLOORS_SCRIPT = paths.pysrc_script(FEATURE, "prototype_floors.py")
JSON_PATH = os.path.join(OUTPUT_DIR, "prototip_input.json")
FLOORS_PATH = os.path.join(OUTPUT_DIR, "prototip_floors.json")


def _remove(path):
    if os.path.isfile(path):
        try:
            os.remove(path)
        except Exception as ex:  # noqa: BLE001
            logger.debug("Silinemedi {}: {}".format(path, ex))


def _read_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


selection = ui.pick_inputs()
logger.info("Girdiler: {}".format(selection))
_remove(JSON_PATH)                      # eski calistirmanin sonucu okunmasin
_remove(FLOORS_PATH)

# --- Hazirlik (CPython alt sureci) -----------------------------------------
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


with forms.ProgressBar(title="Prototip hazirlaniyor: {value}%", indeterminate=False) as pb:
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

logger.info("prepare_prototype_input.py cikti:\n{}".format(proc_output))

if exit_code not in (0, 2) or not os.path.isfile(JSON_PATH):
    forms.alert("Hazirlik basarisiz (exit code {}).\n\n{}".format(exit_code, proc_output[-3000:]),
                title="pyKalfa hata", exitscript=True)

data = _read_json(JSON_PATH)

if exit_code == 2 or data.get("missing"):
    ui.show_missing(data)

if not data.get("walls"):
    forms.alert("Hicbir kat taramaya hizalanamadi; olusturulacak duvar yok.\n\n" +
                "\n".join("Kat {}: {}".format(a["floor"], a["reason"])
                          for a in data.get("alignment", [])),
                title=TITLE, exitscript=True)

# --- Ozet, kotlar, secimler ------------------------------------------------
level_overrides = {}
plan = creator.preview_plan(doc, data)
conflicts = proto_ui.rolove_conflicts(doc)
slabs = proto_ui.existing_slabs(doc)
while proto_ui.summary_and_confirm(data, plan, conflicts, slabs) == "edit":
    level_overrides.update(ui.edit_levels(data))

try:
    choices = ui.pick_choices(doc, data)
    choices.level_overrides = level_overrides
    choices.floor_type = proto_ui.pick_floor_type(doc)
except Exception as ex:  # noqa: BLE001
    forms.alert("Secimler alinirken hata:\n{}\n\n{}".format(ex, traceback.format_exc()),
                title="pyKalfa hata", exitscript=True)

# --- Doseme hatlari (secilen dis duvar kalinligiyla) -----------------------
exterior_m = choices.exterior_type.Width * 0.3048
code, floors_output = run_python(
    FLOORS_SCRIPT, ["--json", JSON_PATH, "--exterior-thickness-m", repr(float(exterior_m)),
                    "--output", FLOORS_PATH])
logger.info("prototype_floors.py cikti:\n{}".format(floors_output))
if code != 0 or not os.path.isfile(FLOORS_PATH):
    forms.alert("Doseme hatlari hesaplanamadi (exit code {}).\n\n{}".format(
        code, floors_output[-3000:]), title="pyKalfa hata", exitscript=True)
floors_data = _read_json(FLOORS_PATH)
data["floors"] = floors_data.get("floors") or []
data.setdefault("warnings", []).extend(floors_data.get("warnings") or [])

# --- Olusturma -------------------------------------------------------------
try:
    report = creator.create_all(doc, app, data, choices)
except Exception as ex:  # noqa: BLE001
    forms.alert("Islem geri alindi, hata olustu:\n{}\n\n{}".format(ex, traceback.format_exc()),
                title="pyKalfa hata", exitscript=True)

logger.info("Prototip: {} olusturuldu, {} korundu, {} silinmis, {} basarisiz, {:.1f} s".format(
    len(report.created), len(report.kept), len(report.deleted), len(report.failed),
    report.seconds))

# Basarida ara JSON'lar silinir (her calistirmada yeniden uretilir); PNG'ler kalir.
if not report.failed:
    _remove(JSON_PATH)
    _remove(FLOORS_PATH)

proto_ui.show_report(report, data, output)
