# -*- coding: utf-8 -*-
"""pyKalfa / Parsel-Bina Aktar: parsel.png + bina.png -> DetailLine + FilledRegion

Tum girdiler kullanicidan Revit icinden alinir: parsel.png, bina.png,
harita olcegi (ör. 1000 = 1:1000), line style ve filled region type.

Bu buton sadece KENDI is akisini icerir; ortak isler (yol bulma, alt-surec
calistirma, `env/` kurulumu, stil sectirme) `lib/pykalfa/` altindaki
paylasilan kutuphanededir -- yeni butonlar da ayni katmani kullanir.

Goruntu isleme kodu `pysrc/parsel_bina/` altindadir ve `env/` sanal
ortamindaki CPython ile bir alt-surec olarak calisir (cv2/numpy/
scikit-image IronPython'da calismaz). Ortaya cikan `revit_input.json`
okunup DetailLine/FilledRegion/TextNote'a cevrilir.

Akis sirasi bilinctir: **once butun girdiler** (dosyalar, olcek, uc stil)
alinir, **sonra tek uzun islem** (goruntu isleme + OCR) bir ilerleme
cubugu esliginde calisir, **en sonda** geometri olusturulur. Boylece
kullanici beklemenin ortasinda soruyla karsilasmaz. Alt-surec
`PROGRESS|yuzde|mesaj` satirlari basar; cubuk bunlara gore ilerler.

Parsel sinirlari: her segment ayri bir DetailCurve (LineStyle projeden
secilir). Bina: her biri ayri bir FilledRegion (FilledRegionType projeden
secilir). Parsel numara etiketleri (ör. "591G", OCR ile okunur): her biri
ayri bir TextNote (TextNoteType projeden secilir), okunan dönüş acisina
gore dondurulur. Ucu de proje icinde ONCEDEN VAR OLAN stiller arasindan,
script calisirken secilir -- hicbir isim koda gomulmez (proje sablonuna
gore degisebildigi icin).

OCR (EasyOCR) agir bir bagimliliktir ve dogrulugu ~%80 civarindadir
(bazi benzer karakterler -- G/6, A/4, B/8, S/5 -- karisabilir); her
etiketin `confidence` (guven) skoru `revit_input.json`'da yer alir.

IronPython 2.7 uyumlu yazilmistir (pyRevit'in varsayilan motoru).
"""

import json
import math
import os
import traceback

from Autodesk.Revit.DB import (
    XYZ,
    CurveLoop,
    ElementTransformUtils,
    FilledRegion,
    Line,
    TextNote,
    Transaction,
)
from pyrevit import forms, revit, script
from System.Collections.Generic import List

from pykalfa import bootstrap, paths, selectors
from pykalfa.revitutils import (
    WarningSwallower,
    distance,
    require_draftable_view,
    view_elevation,
)
from pykalfa.subproc import run_python

logger = script.get_logger()
output = script.get_output()

# Bu uzunlugun altindaki (sifira yakin) segmentler atlanir: Revit'te boyle
# dejenere Line/CurveLoop parcalari otomasyon senaryolarinda kararsizlik
# (hatta cokme) yaratabiliyor.
MIN_SEGMENT_LENGTH_FT = 0.05

# `pysrc/` altindaki bu islevin klasoru.
FEATURE = "parsel_bina"

doc = revit.doc
view = revit.active_view

require_draftable_view(
    view,
    "Aktif view bir plan/detay/kesit/cephe view'i olmali "
    "(DetailLine bir sketch plane'e ihtiyac duyar). "
    "Once uygun bir view acip tekrar calistirin.",
)

# Bu islev goruntu islemeye (CPython) ihtiyac duyuyor: kullanicidan girdi
# istemeden once ortamin hazir oldugundan emin ol.
bootstrap.ensure_env()

OUTPUT_DIR = paths.output_dir()
PREPARE_SCRIPT = paths.pysrc_script(FEATURE, "prepare_revit_input.py")

parsel_path = forms.pick_file(file_ext="png", title="parsel.png dosyasini secin")
if not parsel_path:
    script.exit()

bina_path = forms.pick_file(file_ext="png", title="bina.png dosyasini secin")
if not bina_path:
    script.exit()

scale_text = forms.ask_for_string(
    default="500", prompt="Harita olcegi paydasini girin (ör. 500 -> 1:500)", title="Olcek"
)
if not scale_text:
    script.exit()
try:
    scale_value = float(scale_text.strip())
    if scale_value <= 0:
        raise ValueError("olcek pozitif olmali")
except ValueError:
    forms.alert("Gecersiz olcek degeri: {!r}".format(scale_text), exitscript=True)

# --- Stil secimleri (goruntu islemeden ONCE) --------------------------------
# Ucu de projede ONCEDEN tanimli stiller arasindan secilir (bkz.
# lib/pykalfa/selectors.py) -- hicbir isim koda gomulmez.
#
# Bu secimler bilerek goruntu islemeden ONCE alinir: kullanici butun
# girdilerini pesi sira verip tek bir uzun beklemeye girsin, bekleme
# ortasinda tekrar soru sorulmasin diye.
try:
    chosen_line_style = selectors.pick_line_style(
        doc, title="Parsel cizgileri icin line style secin"
    )
    chosen_region_type = selectors.pick_filled_region_type(
        doc, title="Binalar icin filled region tipi secin"
    )
    # Etiketlerin gercekten okunup okunmayacagi ancak islem sonunda belli
    # olur; bu yuzden metin tipi de simdiden sorulur. Projede hic metin
    # tipi yoksa soru atlanir (`optional=True`) ve OCR hic calistirilmaz:
    # olusturulamayacak etiketler icin en uzun adimi beklemek anlamsiz.
    chosen_text_note_type = selectors.pick_text_note_type(
        doc,
        title="Parsel etiketleri (ör. '591G') icin text note tipi secin",
        optional=True,
    )
except Exception as ex:
    forms.alert(
        "Stil secimi sirasinda hata:\n{}\n\n{}".format(ex, traceback.format_exc()),
        title="pyKalfa hata",
    )
    script.exit()

# --- Goruntu isleme (tek uzun adim, ilerleme cubugu ile) --------------------
logger.info("Goruntu isleme baslatiliyor (olcek 1:{})...".format(int(scale_value)))

prepare_args = [
    "--parsel", parsel_path,
    "--bina", bina_path,
    "--scale", str(scale_value),
    "--output-dir", OUTPUT_DIR,
]
if chosen_text_note_type is None:
    logger.info("Projede text note tipi yok; etiket OCR'i atlaniyor (--no-labels).")
    prepare_args.append("--no-labels")

# Alt-surec `PROGRESS|yuzde|mesaj` satirlari basiyor. Bu satirlar .NET'in
# okuma iş parcaciklarindan geldigi icin ARAYUZE DOKUNULMAZ; sadece
# duruma yazilir. Cubuk, ana iş parcacigindan cagirilan `_tick` ile
# guncellenir (bkz. subproc.run_process'teki `on_poll`).
state = {"percent": 0, "message": "Baslatiliyor", "dirty": True, "display": 0, "ticks": 0}

# Bir adimin (ozellikle OCR'in) icinde gercek yuzde bilinemez: EasyOCR
# ilerleme bildirmez ve toplam surenin buyuk kismi orada geciyor. Cubuk
# tamamen sabit kalirsa "kilitlendi" izlenimi veriyor; bu yuzden yeni bir
# asama gelmediginde cubuk, bulundugu asamanin uzerine en fazla bu kadar
# "canlilik puani" ekleyerek yavasca ilerletilir. Sahte ama dogru tarafa
# giden bir gosterge -- asama ADI her zaman gercek olani yazar.
PROGRESS_CREEP_LIMIT = 18
PROGRESS_CREEP_EVERY = 5  # kac yoklamada bir (yoklama ~200 ms)


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


with forms.ProgressBar(title="Goruntu isleniyor: {value}%", indeterminate=False) as pb:
    pb.update_progress(0, 100)

    def _tick():
        if state["dirty"]:
            state["dirty"] = False
            state["display"] = state["percent"]
            state["ticks"] = 0
            logger.info("{} (%{})".format(state["message"], state["percent"]))
            try:
                pb.title = "{} : {{value}}%".format(state["message"])
            except Exception:
                # Baslik guncellenemezse (pyRevit surum farki) cubuk yine
                # de ilerlesin; asama adi loga zaten yaziliyor.
                pass
        else:
            state["ticks"] += 1
            ceiling = min(state["percent"] + PROGRESS_CREEP_LIMIT, 99)
            if state["ticks"] % PROGRESS_CREEP_EVERY == 0 and state["display"] < ceiling:
                state["display"] += 1
        pb.update_progress(state["display"], 100)

    exit_code, proc_output = run_python(
        PREPARE_SCRIPT, prepare_args, on_line=_on_line, on_poll=_tick
    )
    pb.update_progress(100, 100)

logger.info("prepare_revit_input.py cikti:\n{}".format(proc_output))

json_path = os.path.join(OUTPUT_DIR, "revit_input.json")
if exit_code != 0 or not os.path.isfile(json_path):
    forms.alert(
        "Goruntu isleme basarisiz oldu (exit code {}).\n\n{}".format(exit_code, proc_output),
        title="pyKalfa hata",
        exitscript=True,
    )

with open(json_path, "r") as f:
    data = json.load(f)

logger.info("revit_input.json yuklendi: {} parsel, {} bina, {} etiket".format(
    len(data.get("parcels", [])), len(data.get("buildings", [])), len(data.get("labels", []))
))
if data.get("label_warning"):
    logger.info("Etiket uyarisi: {}".format(data["label_warning"]))

labels = data.get("labels") or []
if labels and chosen_text_note_type is None:
    # Buraya normalde dusulmez (metin tipi yoksa OCR zaten atlanir), ama
    # duserse etiketler sessizce kaybolmasin.
    logger.info("{} etiket okundu ama metin tipi secilmedi, atlaniyor.".format(len(labels)))
    labels = []

# --- Geometri olusturma -----------------------------------------------------
level_elevation = view_elevation(view)

created_lines = 0
skipped_lines = 0
created_regions = 0
skipped_regions = 0
created_labels = 0
skipped_labels = 0

t = Transaction(doc, "pyKalfa: parsel/bina aktarimi")
failure_opts = t.GetFailureHandlingOptions()
failure_opts.SetFailuresPreprocessor(WarningSwallower())
t.SetFailureHandlingOptions(failure_opts)
t.Start()
try:
    # parcel_lines: iskelet grafigi dogrudan izlenerek uretildigi icin her
    # fiziksel cizgi (komsu parsellerin ortak siniri dahil) tam bir kez
    # yer alir (bkz. geometry.py: extract_parcel_lines).
    for i, (p1, p2) in enumerate(data["parcel_lines"]):
        if distance(p1, p2) < MIN_SEGMENT_LENGTH_FT:
            skipped_lines += 1
            continue
        try:
            line = Line.CreateBound(
                XYZ(p1[0], p1[1], level_elevation), XYZ(p2[0], p2[1], level_elevation)
            )
        except Exception as ex:
            logger.debug("Parsel segment {} atlandi: {}".format(i, ex))
            skipped_lines += 1
            continue
        detail_curve = doc.Create.NewDetailCurve(view, line)
        try:
            detail_curve.LineStyle = chosen_line_style
        except Exception as ex:
            logger.debug("LineStyle atanamadi: {}".format(ex))
        created_lines += 1

    for building in data["buildings"]:
        verts = building["vertices_ft"]
        n = len(verts)
        if n < 3:
            skipped_regions += 1
            continue
        loop = CurveLoop()
        loop_ok = True
        for i in range(n):
            p1, p2 = verts[i], verts[(i + 1) % n]
            if distance(p1, p2) < MIN_SEGMENT_LENGTH_FT:
                continue
            try:
                loop.Append(
                    Line.CreateBound(
                        XYZ(p1[0], p1[1], level_elevation), XYZ(p2[0], p2[1], level_elevation)
                    )
                )
            except Exception as ex:
                logger.debug("Bina {} loop kurulamadi: {}".format(building.get("id"), ex))
                loop_ok = False
                break
        if not loop_ok:
            skipped_regions += 1
            continue
        try:
            FilledRegion.Create(doc, chosen_region_type.Id, view.Id, List[CurveLoop]([loop]))
            created_regions += 1
        except Exception as ex:
            logger.debug("Bina {} FilledRegion olusturulamadi: {}".format(building.get("id"), ex))
            skipped_regions += 1

    # Parsel numara etiketleri (OCR ile okundu, ör. "591G") -- her biri ayri
    # bir TextNote. Dusuk guven skorlu (`confidence`) okumalar da olusturulur,
    # sadece yanlis olabilecegini gostermek kullaniciya birakilir (bkz.
    # prepare_revit_input.py: labels_note).
    for label in labels:
        try:
            position = XYZ(label["position_ft"][0], label["position_ft"][1], level_elevation)
            text_note = TextNote.Create(doc, view.Id, position, label["text"], chosen_text_note_type.Id)
            rotation_deg = label.get("rotation_deg") or 0.0
            if rotation_deg:
                axis = Line.CreateBound(position, position + XYZ.BasisZ)
                ElementTransformUtils.RotateElement(doc, text_note.Id, axis, math.radians(rotation_deg))
            created_labels += 1
        except Exception as ex:
            logger.debug("Etiket '{}' olusturulamadi: {}".format(label.get("text"), ex))
            skipped_labels += 1

    t.Commit()
except Exception as ex:
    t.RollBack()
    forms.alert("Islem geri alindi, hata olustu:\n{}\n\n{}".format(ex, traceback.format_exc()))
    script.exit()


# Basari sonrasi devir-teslim dosyalarini temizle: bunlar sadece Python
# venv <-> Revit arasindaki gecici ara format, her calistirmada zaten
# yeniden uretiliyor -- kalici olarak saklanmasina gerek yok. Diger eski
# debug ciktilarina (mask/edges/contours vb.) dokunulmaz.
preview_path = os.path.join(OUTPUT_DIR, "revit_input_preview.png")
for path in (json_path, preview_path):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as ex:
        logger.debug("Gecici dosya silinemedi ({}): {}".format(path, ex))

forms.alert(
    "Parsel cizgisi: {} olusturuldu, {} atlandi\n"
    "Bina (filled region): {} olusturuldu, {} atlandi\n"
    "Parsel etiketi (text): {} olusturuldu, {} atlandi".format(
        created_lines, skipped_lines, created_regions, skipped_regions, created_labels, skipped_labels
    )
)
