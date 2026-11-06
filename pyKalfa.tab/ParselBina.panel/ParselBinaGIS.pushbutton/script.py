# -*- coding: utf-8 -*-
"""pyKalfa / Parsel-Bina GIS: adres veya CaPaKey -> SPW verisi -> Revit

Parsel/Bina Aktar ile ayni cizimi, kadastro goruntuleri yerine Valonya
geoportalinin (SPW) dondurdugu veriden yapar: parsel sinirlari CADMAP,
binalar PICC, parsel numaralari parsel ozniteliklerinden. OCR, olcek ve
hizalama yoktur.

Akis (mevcut butonla ayni mantik): once butun girdiler (arama, pay, stiller),
sonra tek alt surec (ilerleme cubugu ile), en sonda tek transaction.

Ag isleri `pysrc/parsel_gis/` altindaki CPython alt surecleriyle yapilir:
  - suggest_cli.py       arama metni -> output/gis_suggest.json
  - prepare_gis_input.py parsel + pay -> output/revit_input.json (+ onizleme)

IronPython 2.7 uyumlu yazilmistir.
"""

import io
import json
import os
import traceback

from pyrevit import forms, revit, script

from pykalfa import bootstrap, paths, selectors
from pykalfa.parsel_draw import draw_revit_input
from pykalfa.revitutils import require_draftable_view
from pykalfa.subproc import run_python

logger = script.get_logger()

FEATURE = "parsel_gis"
NO_FRAME_LABEL = "-- Cerceve cizme --"
NO_NORTH_LABEL = "-- Kuzey oku ekleme --"
NO_ROAD_LABEL = "-- Yol cizme --"
NO_STREET_LABEL = "-- Sokak adi yazma --"
SAME_LINE_LABEL = "-- Parsel cizgisiyle ayni --"
SAME_TEXT_LABEL = "-- Parsel etiketiyle ayni --"
DEFAULT_MARGIN_M = "80"
MAX_MARGIN_M = 200.0
PRECISION_LABELS = {
    "house": u"bina",
    "address-point": u"adres noktasi",
    "street-bbox-centre": u"sokak",
    "capakey": u"CaPaKey",
}

# Bkz. ImportGeometry script.py: asama icinde cubuk yavasca ilerletilir.
PROGRESS_CREEP_LIMIT = 18
PROGRESS_CREEP_EVERY = 5

doc = revit.doc
view = revit.active_view

require_draftable_view(
    view,
    "Aktif view bir plan/detay/kesit/cephe view'i olmali "
    "(DetailLine bir sketch plane'e ihtiyac duyar). "
    "Once uygun bir view acip tekrar calistirin.",
)

bootstrap.ensure_env()

OUTPUT_DIR = paths.output_dir()
SUGGEST_SCRIPT = paths.pysrc_script(FEATURE, "suggest_cli.py")
PREPARE_SCRIPT = paths.pysrc_script(FEATURE, "prepare_gis_input.py")
SUGGEST_JSON = os.path.join(OUTPUT_DIR, "gis_suggest.json")
JSON_PATH = os.path.join(OUTPUT_DIR, "revit_input.json")


def _remove(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as ex:
        logger.debug("Gecici dosya silinemedi ({}): {}".format(path, ex))


def _last_error(output):
    for line in reversed((output or "").splitlines()):
        if line.startswith("ERROR|"):
            return line[len("ERROR|"):]
    return output


# --- 1) Arama: adres veya CaPaKey -> aday secimi -> parsel --------------------
def _run_suggest(args):
    """suggest_cli.py'yi calistirir, aday listesini dondurur; servis hatasinda cikar."""
    _remove(SUGGEST_JSON)
    exit_code, output = run_python(SUGGEST_SCRIPT, args + ["--output", SUGGEST_JSON])
    logger.debug("suggest_cli cikti:\n{}".format(output))
    payload = {}
    if os.path.isfile(SUGGEST_JSON):
        with io.open(SUGGEST_JSON, "r", encoding="utf-8") as f:
            payload = json.load(f)
    if exit_code != 0 or payload.get("error"):
        forms.alert(
            u"Adres servisine ulasilamadi:\n{}".format(payload.get("error") or _last_error(output)),
            title="pyKalfa hata",
            exitscript=True,
        )
    return payload.get("candidates") or []


def _option_label(c):
    return u"{}  ({})".format(c.get("label"), PRECISION_LABELS.get(c.get("precision"), c.get("precision")))


def ask_location():
    """(parsel adayi {capakey, numero, ...}, secilen adres etiketi veya None).

    Parsel stil secimlerinden ONCE bulunur: CaPaKey yanlissa veya adresin
    20 m icinde parsel yoksa kullaniciya bastan tekrar sorulur."""
    default = ""
    while True:
        text = forms.ask_for_string(
            default=default,
            prompt="Adres veya CaPaKey girin (ör. Rue du Parc 4, 4577 Modave  /  92053D0515/00B002)",
            title="Parsel/Bina GIS",
        )
        if not text or not text.strip():
            script.exit()
        # run_process argumanlari cift tirnakla sarar; tirnak/ters bolu ciksin
        query = text.replace('"', " ").replace("\\", " ").strip()
        default = query

        candidates = _run_suggest(["--query", query])
        if not candidates:
            forms.alert(u"Adres / CaPaKey bulunamadi: {}\n\nTekrar deneyin.".format(query),
                        title="Parsel/Bina GIS")
            continue

        by_label = dict((_option_label(c), c) for c in candidates)
        chosen = selectors.unwrap_selection(
            forms.SelectFromList.show([_option_label(c) for c in candidates],
                                      title="Bulunan adresler - birini secin", multiselect=False)
        )
        if not chosen:
            script.exit()
        candidate = by_label[chosen]
        if candidate.get("capakey"):
            return candidate, None

        parcels = _run_suggest(["--x", repr(float(candidate["x"])), "--y", repr(float(candidate["y"]))])
        if parcels:
            return parcels[0], candidate.get("label")
        forms.alert(u"Bu adresin 20 m icinde kadastro parseli yok:\n{}\n\nBaska bir adres "
                    u"veya CaPaKey deneyin.".format(candidate.get("label")), title="Parsel/Bina GIS")


# --- 2) Pay (metre) -----------------------------------------------------------
def ask_margin():
    while True:
        text = forms.ask_for_string(
            default=DEFAULT_MARGIN_M,
            prompt="Parselin etrafinda kac metre alinsin? (ör. 80)",
            title="Alan",
        )
        if not text:
            script.exit()
        try:
            value = float(text.strip().replace(",", "."))
        except ValueError:
            value = -1
        if 0 < value <= MAX_MARGIN_M:
            return value
        forms.alert("Gecersiz deger: {!r}. 0 ile {:.0f} m arasinda bir sayi girin.".format(text, MAX_MARGIN_M))


location, address_label = ask_location()
margin_m = ask_margin()

# --- 3) Stil secimleri (Parsel/Bina Aktar ile ayni sira ve basliklar) ---------
try:
    chosen_line_style = selectors.pick_line_style(
        doc, title="Parsel çizgileri için line style seçin"
    )
    # Secilen (aranan) parselin siniri ayri stille; "ayni" secilirse parsel stili.
    chosen_selected_line_style = selectors.pick_line_style(
        doc,
        title=u"Secilen parselin ({}) siniri icin line style secin".format(location.get("numero")),
        skip_label=SAME_LINE_LABEL,
    )
    chosen_frame_style = selectors.pick_line_style(
        doc,
        title="Cizim cercevesi (goruntunun dis siniri) icin line style secin",
        skip_label=NO_FRAME_LABEL,
    )
    # Yol ve kaldirim kenarlari (PICC) tek bir line style ile cizilir.
    chosen_road_style = selectors.pick_line_style(
        doc,
        title="Yol ve kaldirim kenarlari icin line style secin",
        skip_label=NO_ROAD_LABEL,
    )
    # Sokak adlari parsel numaralarindan farkli boyda yazilabilsin diye ayri sorulur.
    chosen_street_text_type = selectors.pick_text_note_type(
        doc,
        title="Sokak adlari icin text note tipi secin",
        skip_label=NO_STREET_LABEL,
    )
    chosen_region_type = selectors.pick_filled_region_type(
        doc, title="Binalar icin filled region tipi secin"
    )
    chosen_text_note_type = selectors.pick_text_note_type(
        doc,
        title="Parsel etiketleri (ör. '591G') icin text note tipi secin",
        optional=True,
    )
    chosen_selected_text_type = None
    if chosen_text_note_type is not None:
        chosen_selected_text_type = selectors.pick_text_note_type(
            doc,
            title=u"Secilen parselin numarasi ({}) icin text note tipi secin".format(location.get("numero")),
            skip_label=SAME_TEXT_LABEL,
        )
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

# --- 4) Veri cekme (tek alt surec, ilerleme cubugu ile) -----------------------
prepare_args = ["--capakey", location["capakey"], "--margin", repr(margin_m), "--output-dir", OUTPUT_DIR]
if chosen_text_note_type is None:
    prepare_args.append("--no-labels")
if chosen_road_style is None:
    prepare_args.append("--no-roads")
if chosen_street_text_type is None:
    prepare_args.append("--no-streets")

_remove(JSON_PATH)
state = {"percent": 0, "message": "Baslatiliyor", "dirty": True, "display": 0, "ticks": 0}


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


with forms.ProgressBar(title="GIS verisi aliniyor: {value}%", indeterminate=False) as pb:
    pb.update_progress(0, 100)

    def _tick():
        if state["dirty"]:
            state["dirty"] = False
            state["display"] = state["percent"]
            state["ticks"] = 0
            try:
                pb.title = "{} : {{value}}%".format(state["message"])
            except Exception:
                pass
        else:
            state["ticks"] += 1
            ceiling = min(state["percent"] + PROGRESS_CREEP_LIMIT, 99)
            if state["ticks"] % PROGRESS_CREEP_EVERY == 0 and state["display"] < ceiling:
                state["display"] += 1
        pb.update_progress(state["display"], 100)

    exit_code, proc_output = run_python(PREPARE_SCRIPT, prepare_args, on_line=_on_line, on_poll=_tick)
    pb.update_progress(100, 100)

logger.info("prepare_gis_input.py cikti:\n{}".format(proc_output))

if exit_code != 0 or not os.path.isfile(JSON_PATH):
    forms.alert(
        u"GIS verisi alinamadi (exit code {}).\n\n{}".format(exit_code, _last_error(proc_output)),
        title="pyKalfa hata",
        exitscript=True,
    )

with io.open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# --- 5) Cizim (tek transaction) -----------------------------------------------
try:
    counts = draw_revit_input(
        doc, view, data,
        chosen_line_style, chosen_frame_style, chosen_region_type,
        chosen_text_note_type, chosen_north_symbol,
        "pyKalfa: parsel/bina GIS aktarimi",
        road_style=chosen_road_style,
        street_text_type=chosen_street_text_type,
        selected_line_style=chosen_selected_line_style,
        selected_text_type=chosen_selected_text_type,
    )
except Exception as ex:
    forms.alert("Islem geri alindi, hata olustu:\n{}\n\n{}".format(ex, traceback.format_exc()))
    script.exit()

# Parsel geometrisi diskte birakilmaz; onizleme gorseli bilerek kalir.
_remove(JSON_PATH)
_remove(SUGGEST_JSON)
preview_path = os.path.join(OUTPUT_DIR, "revit_input_preview.png")

selected = data.get("selected") or {}
summary = u"Parsel: {} ({})\n".format(selected.get("numero"), selected.get("capakey"))
if address_label:
    summary += u"Adres: {}\n".format(address_label)
summary += u"Alan: parsel ± {:g} m\n\n".format(margin_m)
summary += u"Parsel cizgisi: {} olusturuldu, {} atlandi\n".format(counts["lines"], counts["lines_skipped"])
summary += u"Secilen parsel siniri: {} olusturuldu, {} atlandi{}\n".format(
    counts["selected_lines"], counts["selected_lines_skipped"],
    u"" if chosen_selected_line_style is not None else u" (parsel stiliyle)")
if chosen_frame_style is not None:
    summary += u"Cerceve cizgisi: {} olusturuldu, {} atlandi\n".format(counts["frame"], counts["frame_skipped"])
if chosen_road_style is not None:
    summary += u"Yol/kaldirim cizgisi: {} olusturuldu, {} atlandi\n".format(counts["roads"], counts["roads_skipped"])
summary += u"Bina blogu (filled region): {} olusturuldu, {} atlandi\n".format(
    counts["regions"], counts["regions_skipped"])
summary += u"Parsel etiketi (text): {} olusturuldu, {} atlandi".format(counts["labels"], counts["labels_skipped"])
if chosen_text_note_type is not None:
    summary += u"\nSecilen parsel numarasi: {}".format(
        (u"ayri tiple yazildi" if chosen_selected_text_type is not None else u"parsel tipiyle yazildi")
        if counts["selected_label"] else u"yazilamadi (parsel cerceve icinde cok kucuk olabilir)")
if chosen_street_text_type is not None:
    summary += u"\nSokak adi (text): {} olusturuldu, {} atlandi".format(counts["streets"], counts["streets_skipped"])
if chosen_north_symbol is not None:
    summary += u"\nKuzey oku: {}".format(u"eklendi" if counts["north"] else u"eklenemedi")
summary += u"\n\nDogrulama gorseli:\n{}".format(preview_path)
forms.alert(summary)
