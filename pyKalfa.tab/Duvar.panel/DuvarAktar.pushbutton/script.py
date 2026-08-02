# -*- coding: utf-8 -*-
"""pyKalfa / Duvar Aktar: kat plani DXF -> gercek Revit duvarlari

Polycam (veya baska bir kaynaktan) gelen kat plani DXF'indeki cizgileri
`ModelCurve` olarak degil, **gercek `Wall` elemanlari** olarak olusturur.

Akis:

  1. DXF sec (`ui.pick_dxf`).
  2. `env/` sanal ortamindaki CPython ile `pysrc/duvar/prepare_wall_input.py`
     calistirilir: ezdxf ile geometri okunur, bloklar patlatilir, birim
     otomatik tespit edilir ve **kapali duvar dis hatlarindan (outline)
     merkez eksen + olculen kalinlik** cikarilir. Sonuc:
     `output/wall_input.json` (koordinatlar feet).
  3. Gerekirse kullaniciya sorulup 2. adim tekrarlanir: birim kesin
     degilse, hic dis hat bulunamadiysa (tek cizgi moduna gecis) veya
     cizim Revit orijininden cok uzaksa.
  4. Katman filtresi, duvar yuksekligi, level ve wall type sorulur.
  5. `revit_creator.create_walls` tek bir transaction icinde duvarlari
     uretir; olusturulamayan cizgiler tablo halinde raporlanir.

Duvar kalinligi cizimden OLCULUR ama Revit'e o kalinlik dayatilmaz --
duvarin kalinligi sectiginiz `WallType`'tan gelir; olculen deger sadece
dogru tipi secmenize yardimci olmak icin gosterilir.

Mimari not: bu dosya sadece AKISI kurar. DXF/geometri isleri
`pysrc/duvar/` altinda (CPython), diyaloglar `pykalfa.duvar.ui`'da,
Revit'e yazma `pykalfa.duvar.revit_creator`'da durur; ortak altyapi
(`paths`, `subproc`, `bootstrap`) butun butonlarla paylasilir.

IronPython 2.7 uyumlu yazilmistir (pyRevit'in varsayilan motoru).
"""

import json
import os
import traceback

from pyrevit import forms, revit, script

from pykalfa import bootstrap, paths
from pykalfa.duvar import revit_creator, ui
from pykalfa.revitutils import elem_name
from pykalfa.subproc import run_python

logger = script.get_logger()
output = script.get_output()

FEATURE = "duvar"

doc = revit.doc

# Bu islev DXF okumak icin CPython'a (ezdxf) ihtiyac duyar.
bootstrap.ensure_env()

OUTPUT_DIR = paths.output_dir()
PREPARE_SCRIPT = paths.pysrc_script(FEATURE, "prepare_wall_input.py")
JSON_PATH = os.path.join(OUTPUT_DIR, "wall_input.json")


def prepare(dxf_path, units="auto", recenter=False, include_lines=False):
    """DXF'i CPython tarafinda isleyip sonucu (dict) dondurur."""
    args = ["--dxf", dxf_path, "--output-dir", OUTPUT_DIR, "--units", units]
    if recenter:
        args.append("--recenter")
    if include_lines:
        args.append("--lines")

    exit_code, proc_output = run_python(PREPARE_SCRIPT, args)
    logger.info("prepare_wall_input.py cikti:\n{}".format(proc_output))

    if exit_code != 0 or not os.path.isfile(JSON_PATH):
        forms.alert(
            "DXF okunamadi (exit code {}).\n\n{}".format(exit_code, proc_output),
            title="pyKalfa hata",
            exitscript=True,
        )
    with open(JSON_PATH, "r") as f:
        return json.load(f)


dxf_path = ui.pick_dxf()

logger.info("DXF isleniyor: {}".format(dxf_path))
data = prepare(dxf_path)

for warning in data.get("warnings", []):
    logger.info("Uyari: {}".format(warning))

# --- Birim: DXF'te belirtilmemisse kullaniciya sor ------------------------
unit = data.get("unit", {})
if not unit.get("confident", True):
    chosen_unit = ui.ask_units(
        unit.get("name", "m"),
        "DXF basliginda birim belirtilmemis ($INSUNITS = 0)",
    )
    if chosen_unit != unit.get("name"):
        logger.info("Birim kullanici tarafindan '{}' olarak degistirildi.".format(chosen_unit))
        data = prepare(dxf_path, units=chosen_unit)
        unit = data.get("unit", {})

# --- Kapali duvar dis hatti yoksa tek cizgi modunu oner -------------------
# Varsayilan mod, duvarlari kapali dis hat (outline) olarak cizen gercek
# kat plani ciktilari icindir; hicbiri bulunamazsa cizim tek cizgiyle
# yapilmis olabilir. Bu mod mobilya/olcu cizgilerini de duvara
# cevirebildigi icin sessizce degil, sorularak acilir.
include_lines = False
if not data.get("counts", {}).get("outline_walls"):
    if not ui.confirm_line_mode():
        script.exit()
    include_lines = True
    data = prepare(dxf_path, units=unit.get("name", "auto"), include_lines=True)

# --- Orijinden uzak cizim: istenirse orijine tasi -------------------------
if data.get("far_from_origin"):
    if ui.confirm_recenter(data.get("distance_from_origin_ft", 0.0)):
        data = prepare(
            dxf_path, units=unit.get("name", "auto"),
            recenter=True, include_lines=include_lines,
        )

walls = data.get("walls") or []
if not walls:
    forms.alert(
        "DXF'te duvara donusturulebilecek geometri bulunamadi.\n\n{}".format(
            "\n".join(data.get("warnings", [])) or "Ayrintili bilgi yok."
        ),
        title="Duvar Aktar",
        exitscript=True,
    )

counts = data.get("counts", {})
logger.info(
    "{} duvar adayi ({} dis hat, {} tek cizgi), {} katman, birim: {} ({})".format(
        len(walls), counts.get("outline_walls", 0), counts.get("line_walls", 0),
        len(data.get("layers", {})), unit.get("name"), unit.get("source"),
    )
)

# --- Kullanici girdileri ---------------------------------------------------
try:
    selected_layers = ui.choose_layers(data.get("layers", {}))
    walls = [w for w in walls if w.get("layer") in selected_layers]
    if not walls:
        forms.alert("Secilen katmanlarda duvar yok.", exitscript=True)

    # Secilen duvarlardan olculen kalinlik (medyan): kullaniciya duvar
    # tipi secerken referans olarak gosterilir.
    measured = sorted(w["thickness_ft"] for w in walls if w.get("thickness_ft"))
    measured_thickness = measured[len(measured) // 2] if measured else None
    if measured_thickness:
        logger.info("Cizimde olculen duvar kalinligi (medyan): {:.1f} cm".format(
            measured_thickness * 0.3048 * 100
        ))

    height_ft = ui.ask_wall_height_ft()
    level = ui.pick_level(doc)
    wall_type = ui.pick_wall_type(doc, measured_thickness_ft=measured_thickness)
except Exception as ex:
    forms.alert(
        "Girdi alinirken hata:\n{}\n\n{}".format(ex, traceback.format_exc()),
        title="pyKalfa hata",
    )
    script.exit()

if not ui.confirm_creation(
    len(walls), height_ft, elem_name(wall_type), elem_name(level),
    measured_thickness_ft=measured_thickness,
    total_length_ft=sum(w.get("length_ft", 0.0) for w in walls),
):
    script.exit()

# --- Duvarlari olustur -----------------------------------------------------
try:
    report = revit_creator.create_walls(doc, walls, wall_type, level, height_ft)
except Exception as ex:
    forms.alert(
        "Islem geri alindi, hata olustu:\n{}\n\n{}".format(ex, traceback.format_exc()),
        title="pyKalfa hata",
        exitscript=True,
    )

logger.info("{} duvar olusturuldu, {} basarisiz.".format(report.created, len(report.failed)))

# Basari sonrasi ara dosyayi temizle (her calistirmada yeniden uretiliyor);
# hata varsa inceleyebilmek icin birakilir.
if not report.failed:
    try:
        os.remove(JSON_PATH)
    except Exception as ex:
        logger.debug("Gecici dosya silinemedi: {}".format(ex))

ui.show_report(report, output)
