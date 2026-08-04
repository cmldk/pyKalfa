# -*- coding: utf-8 -*-
"""pyKalfa / Parsel-Bina Aktar: 3 PNG -> DetailLine + FilledRegion

Tum girdiler kullanicidan Revit icinden alinir: UC gorsel (bina.png,
parsel.png, both.png), harita olcegi (ör. 1000 = 1:1000), line style ve
filled region type.

Ucuncu gorsel (`both.png` -- iki katman ust uste) geometri kaynagi
DEGILDIR, yalnizca hizalama referansidir: `bina.png` ile `parsel.png`
ayri ayri disa aktarildigi icin ayni kadraji gosterdikleri garanti
degildir ve kaymis bir parsel-bina eslesmesi ciktida hata gibi gorunmez.
Iki katman `both.png` uzerinden birbirine hizalanir; hizalama
dogrulanamazsa kullaniciya uyari gosterilir (bkz. pysrc/parsel_bina/align.py).

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
secilir). Goruntunun dis siniri (cerceve) ayrica, parsel cizgilerinden
FARKLI bir line style ile 4 DetailCurve olarak cizilir -- boylece cizim
Revit'e cerceveli gider; kullanici istemezse bu adim atlanabilir. Bina:
her BIRIM ayri bir FilledRegion (FilledRegionType projeden secilir);
bitisik yapilarda ic bolme (parti) duvarlari korunur.
Parsel numara etiketleri (ör. "568C", OCR ile okunur): her biri
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

# Cerceve line style listesinin basina eklenen "cizme" secenegi (bkz.
# selectors.pick_by_name'deki `skip_label`).
NO_FRAME_LABEL = "-- Cerceve cizme --"

# Ayni sekilde kuzey oku sembolu icin.
NO_NORTH_LABEL = "-- Kuzey oku ekleme --"

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

# Uc gorsel de ayni gorunumden disa aktarilmis olmali; ucuncusu iki
# katmani birden icerir ve hizalama referansi olarak kullanilir.
bina_path = forms.pick_file(
    file_ext="png", title="1/3: Yalnız BİNA katmani (bina.png)"
)
if not bina_path:
    script.exit()

parsel_path = forms.pick_file(
    file_ext="png", title="2/3: Yalnız PARSEL katmani (parsel.png)"
)
if not parsel_path:
    script.exit()

both_path = forms.pick_file(
    file_ext="png", title="3/3: İKİSİ BİRLİKTE - hizalama icin (both.png)"
)
if not both_path:
    script.exit()

scale_text = forms.ask_for_string(
    default="500", prompt="Harita ölçeği paydasını girin (ör. 500 -> 1:500)", title="Olcek"
)
if not scale_text:
    script.exit()
try:
    scale_value = float(scale_text.strip())
    if scale_value <= 0:
        raise ValueError("ölçek pozitif olmali")
except ValueError:
    forms.alert("Geçersiz ölçek değeri: {!r}".format(scale_text), exitscript=True)

# --- Stil secimleri (goruntu islemeden ONCE) --------------------------------
# Ucu de projede ONCEDEN tanimli stiller arasindan secilir (bkz.
# lib/pykalfa/selectors.py) -- hicbir isim koda gomulmez.
#
# Bu secimler bilerek goruntu islemeden ONCE alinir: kullanici butun
# girdilerini pesi sira verip tek bir uzun beklemeye girsin, bekleme
# ortasinda tekrar soru sorulmasin diye.
try:
    chosen_line_style = selectors.pick_line_style(
        doc, title="Parsel çizgileri için line style seçin"
    )
    # Cerceve = goruntunun dis siniri. Parsel cizgilerinden ayri bir style
    # sorulur (pafta cercevesi genelde farkli/kalin bir kalemdir); cerceve
    # istemeyen kullanici icin liste basinda NO_FRAME_LABEL secenegi var.
    chosen_frame_style = selectors.pick_line_style(
        doc,
        title="Cizim cercevesi (goruntunun dis siniri) icin line style secin",
        skip_label=NO_FRAME_LABEL,
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
    # Kaynak goruntudeki kuzey oku sadece bir sagolcumdur ve geometriye
    # dahil edilmez; ama yonu olculup projenin KENDI kuzey oku sembolu
    # ayni yone cevrilerek yerlestirilebilir.
    chosen_north_symbol = selectors.pick_annotation_symbol(
        doc,
        title="Kuzey oku icin aciklama sembolu (annotation symbol) secin",
        skip_label=NO_NORTH_LABEL,
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
    "--bina", bina_path,
    "--parsel", parsel_path,
    "--both", both_path,
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

# Hizalama dogrulanamadiysa parsel-bina eslesmesi sessizce yanlis olabilir
# -- ciktida hata gibi gorunmeyen tek sorun budur, bu yuzden kullaniciya
# sorulur. Geometri yine de dogru cizilir; supheli olan yalnizca hangi
# binanin hangi parsele ait sayildigidir.
alignment = data.get("alignment") or {}
if alignment.get("warning"):
    logger.info("Hizalama uyarisi: {}".format(alignment["warning"]))
    if not forms.alert(
        "{}\n\nYine de devam edilsin mi?".format(alignment["warning"]),
        title="pyKalfa - hizalama",
        yes=True,
        no=True,
    ):
        script.exit()

labels = data.get("labels") or []
if labels and chosen_text_note_type is None:
    # Buraya normalde dusulmez (metin tipi yoksa OCR zaten atlanir), ama
    # duserse etiketler sessizce kaybolmasin.
    logger.info("{} etiket okundu ama metin tipi secilmedi, atlaniyor.".format(len(labels)))
    labels = []

# --- Geometri olusturma -----------------------------------------------------
level_elevation = view_elevation(view)


def draw_segments(segments, line_style, what):
    """[p1, p2] nokta ciftlerini birer DetailCurve olarak cizer.

    Hem parsel cizgileri hem cerceve ayni sekilde cizilir, sadece line
    style (ve loga yazilan ad) degisir. `(olusturulan, atlanan)` doner."""
    created = 0
    skipped = 0
    for i, (p1, p2) in enumerate(segments):
        if distance(p1, p2) < MIN_SEGMENT_LENGTH_FT:
            skipped += 1
            continue
        try:
            line = Line.CreateBound(
                XYZ(p1[0], p1[1], level_elevation), XYZ(p2[0], p2[1], level_elevation)
            )
        except Exception as ex:
            logger.debug("{} segment {} atlandi: {}".format(what, i, ex))
            skipped += 1
            continue
        detail_curve = doc.Create.NewDetailCurve(view, line)
        try:
            detail_curve.LineStyle = line_style
        except Exception as ex:
            logger.debug("LineStyle atanamadi: {}".format(ex))
        created += 1
    return created, skipped


created_lines = 0
skipped_lines = 0
created_frame_lines = 0
skipped_frame_lines = 0
created_regions = 0
skipped_regions = 0
created_labels = 0
skipped_labels = 0
created_north = 0

t = Transaction(doc, "pyKalfa: parsel/bina aktarimi")
failure_opts = t.GetFailureHandlingOptions()
failure_opts.SetFailuresPreprocessor(WarningSwallower())
t.SetFailureHandlingOptions(failure_opts)
t.Start()
try:
    # parcel_lines: iskelet grafigi dogrudan izlenerek uretildigi icin her
    # fiziksel cizgi (komsu parsellerin ortak siniri dahil) tam bir kez
    # yer alir (bkz. geometry.py: extract_parcel_lines).
    created_lines, skipped_lines = draw_segments(
        data["parcel_lines"], chosen_line_style, "Parsel"
    )

    # Cerceve: goruntunun dis siniri (4 segment). Butun koordinatlar bu
    # cerceveye gore uretildigi icin cizimin tamamini tam olarak cevreler.
    if chosen_frame_style is not None:
        created_frame_lines, skipped_frame_lines = draw_segments(
            data.get("frame_lines") or [], chosen_frame_style, "Cerceve"
        )

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

    # Kuzey oku: kaynak goruntudeki ok geometriye dahil edilmez, sadece
    # KONUMU ve YONU olculur; buraya projenin kendi sembolu ayni yone
    # cevrilerek konur.
    north = data.get("north")
    if chosen_north_symbol is not None and north:
        try:
            if not chosen_north_symbol.IsActive:
                chosen_north_symbol.Activate()
                doc.Regenerate()
            position = XYZ(north["position_ft"][0], north["position_ft"][1], level_elevation)
            instance = doc.Create.NewFamilyInstance(position, chosen_north_symbol, view)
            rotation_deg = north.get("rotation_deg") or 0.0
            if rotation_deg:
                axis = Line.CreateBound(position, position + XYZ.BasisZ)
                ElementTransformUtils.RotateElement(doc, instance.Id, axis, math.radians(rotation_deg))
            created_north = 1
        except Exception as ex:
            logger.debug("Kuzey oku yerlestirilemedi: {}".format(ex))

    t.Commit()
except Exception as ex:
    t.RollBack()
    forms.alert("Islem geri alindi, hata olustu:\n{}\n\n{}".format(ex, traceback.format_exc()))
    script.exit()


# Basari sonrasi ara format dosyasini temizle: `revit_input.json` sadece
# Python venv <-> Revit arasindaki devir-teslim bicimi ve her calistirmada
# yeniden uretiliyor.
#
# `revit_input_preview.png` BILEREK BIRAKILIR: cizimin dogrulugu (hangi
# bina hangi parsele dustu, hizalama tuttu mu) Revit'e bakarak degil bu
# gorsele bakarak hizlica denetlenebiliyor. Her calistirmada ustune
# yazilir, yani birikmez.
preview_path = os.path.join(OUTPUT_DIR, "revit_input_preview.png")
try:
    if os.path.isfile(json_path):
        os.remove(json_path)
except Exception as ex:
    logger.debug("Gecici dosya silinemedi ({}): {}".format(json_path, ex))

summary = "Parsel cizgisi: {} olusturuldu, {} atlandi\n".format(created_lines, skipped_lines)
if chosen_frame_style is not None:
    summary += "Cerceve cizgisi: {} olusturuldu, {} atlandi\n".format(
        created_frame_lines, skipped_frame_lines
    )
summary += (
    "Bina blogu (filled region): {} olusturuldu, {} atlandi\n"
    "Parsel etiketi (text): {} olusturuldu, {} atlandi\n"
    "Parseliyle eslesen bina: {}/{}".format(
        created_regions, skipped_regions, created_labels, skipped_labels,
        data.get("matched_building_count", 0), data.get("building_count", 0),
    )
)
if chosen_north_symbol is not None:
    if created_north:
        summary += "\nKuzey oku: eklendi ({:+.1f} derece)".format(
            data["north"].get("rotation_deg") or 0.0
        )
    else:
        summary += "\nKuzey oku: goruntude bulunamadi"
summary += "\n\nDogrulama gorseli:\n{}".format(preview_path)
forms.alert(summary)
