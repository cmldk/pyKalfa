# -*- coding: utf-8 -*-
"""Rolove Aktar - diyaloglar (girdi secimi, ozet/onay, secimler, rapor).

Iptal edilen her diyalog scripti sonlandirir (`script.exit()`); boylece
akis her zaman gecerli bir cevapla ilerler. IronPython 2.7.
"""

from collections import Counter

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FamilySymbol,
    FilteredElementCollector,
    WallKind,
    WallType,
)
from pyrevit import forms, script

from pykalfa.revitutils import elem_name
from pykalfa.rolove.creator import Choices
from pykalfa.selectors import _symbol_label, pick_by_name

logger = script.get_logger()

CREATE = "Olustur"
EDIT = "Kotlari duzenle"
CANCEL = "Iptal"


def pick_input():
    path = forms.pick_file(
        files_filter="Polycam kat plani (*.dxf;*.zip)|*.dxf;*.zip",
        title="Polycam kat plani DXF'i ya da kat plani zip'i secin",
    )
    if not path:
        script.exit()
    return path


def show_missing(data):
    lines = []
    for m in data.get("missing", []):
        if m.get("note"):
            lines += [m["note"], ""]
    lines += ["Ayni klasorde ayni adla bulunamayan Polycam ciktilari:", ""]
    for m in data.get("missing", []):
        lines.append("- {}  ->  Polycam'de: {}".format(m.get("expected") or m["file"],
                                                       m["polycam_export"]))
    lines += ["", "Bu dosyalari ayni klasore ayni adla export edip tekrar deneyin.",
              "(Polycam Basic plan gerekir; LAS'ta 'georeferenced' KAPALI olmali.)"]
    forms.alert("\n".join(lines), title="Rolove Aktar - eksik girdi", exitscript=True)


def _summary_text(data, plan):
    lines = []
    al = {a["floor"]: a for a in data.get("alignment", [])}
    z = data.get("z_datum") or {}
    lines.append("Kat kotlari (Kat {} dosemesi = 0.00):".format(z.get("floor", "?")))
    for lv in data.get("levels", []):
        a = al.get(lv["floor"], {})
        if a.get("ok"):
            fit = "hizali (sapma {:.1f} cm, destek %{:.0f})".format(
                (a.get("rms_m") or 0) * 100, a.get("support_ratio", 0) * 100)
        else:
            fit = "HIZALANAMADI - kat atlanir: {}".format(a.get("reason", "?"))
        ceiling = lv.get("ceiling_m")
        lines.append("  {}: {:+.2f} m{}  |  {}".format(
            lv["name"], lv["elevation_m"],
            "" if ceiling is None else " (tavan {:+.2f})".format(ceiling), fit))
    st = data.get("stats", {})
    c = st.get("counts", {})
    sc = st.get("status_counts", {})
    lines.append("")
    lines.append("Duvar {}  |  aciklik {}  |  oda {}  |  modele girmeyen {}".format(
        c.get("walls", 0), c.get("openings", 0), c.get("rooms", 0), c.get("rejected", 0)))
    lines.append("Duvar durumu: " + ", ".join(
        "{} {}".format(k, v) for k, v in sorted((sc.get("walls") or {}).items())))
    groups = data.get("thickness_groups") or []
    if groups:
        lines.append("Ic duvar kalinlik gruplari: " + ", ".join(
            "{} cm x{} ({} olculen)".format(g["cm"], g["count"], g.get("measured", 0))
            for g in groups))
    if plan:
        lines.append("")
        lines.append("Bu projede: olusturulacak {}, korunacak {}, kullanicinin sildigi {} "
                     "(silinenler yeniden olusturulmaz)".format(
                         plan["create"], plan["keep"], plan["deleted"]))
        if plan.get("other_sources"):
            lines.append("UYARI: Bu projeye daha once BASKA bir Polycam kaynagindan aktarim "
                         "yapilmis; elemanlar ust uste gelebilir.")
    if data.get("previews"):
        lines.append("")
        lines.append("Onizleme PNG'leri (yesil olculdu / turuncu duzeltildi / kirmizi varsayildi):")
        lines += ["  " + p for p in data["previews"]]
    t = (st.get("timings_s") or {}).get("total")
    if t is not None:
        lines.append("")
        lines.append("Hazirlik suresi: {:.1f} s".format(t))
    return "\n".join(lines)


def summary_and_confirm(data, plan=None):
    """"create" | "edit"; iptal scripti sonlandirir."""
    choice = forms.alert(_summary_text(data, plan), title="Rolove Aktar - onizleme",
                         options=[CREATE, EDIT, CANCEL])
    if choice == CREATE:
        return "create"
    if choice == EDIT:
        return "edit"
    script.exit()


def edit_levels(data):
    """Her kat kotunu sorar; degisenleri `data`'ya yazar ve
    {level_id: kot_m} dondurur. Bos/iptal = degismez."""
    overrides = {}
    for lv in data.get("levels", []):
        text = forms.ask_for_string(
            default="{:.2f}".format(lv["elevation_m"]),
            prompt="{} kotu (metre, ana kat 0.00)".format(lv["name"]),
            title="Rolove Aktar - kat kotlari",
        )
        if not text:
            continue
        try:
            value = round(float(text.replace(",", ".")), 2)
        except ValueError:
            forms.alert("Gecersiz sayi: {}".format(text), title="Rolove Aktar")
            continue
        if abs(value - lv["elevation_m"]) > 1e-9:
            overrides[lv["id"]] = value
            lv["elevation_m"] = value
            lv["elevation_ft"] = value / 0.3048
    return overrides


def _wall_types(doc):
    all_types = list(FilteredElementCollector(doc).OfClass(WallType))
    basic = [wt for wt in all_types if wt.Kind in (WallKind.Basic, WallKind.Stacked)]
    return basic or all_types


def _wall_label(wt):
    return "{}  ({:.0f} cm)".format(elem_name(wt), wt.Width * 30.48)


def _symbols(doc, bic):
    return list(FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(bic))


def pick_choices(doc, data):
    types = _wall_types(doc)
    exterior = pick_by_name(
        types, "Dis duvar tipi (taranan ic yuzden disa dogru kalinlasir)",
        "Projede tanimli bir Wall Type bulunamadi.", label_fn=_wall_label)
    group_types = {}
    for g in data.get("thickness_groups") or []:
        group_types[g["cm"]] = pick_by_name(
            types, "Ic duvar ~{} cm ({} duvar, {} tanesi taramadan olculdu)".format(
                g["cm"], g["count"], g.get("measured", 0)),
            "Projede tanimli bir Wall Type bulunamadi.", label_fn=_wall_label)
    kinds = Counter(o["kind"] for o in data.get("openings", []))
    door = window = None
    if kinds.get("door"):
        door = pick_by_name(
            _symbols(doc, BuiltInCategory.OST_Doors),
            "Kapi ailesi ({} kapi; olculere gore 'Scan GxY' tipleri turetilir)".format(kinds["door"]),
            "", skip_label="Opening kullan", label_fn=_symbol_label)
    if kinds.get("window"):
        window = pick_by_name(
            _symbols(doc, BuiltInCategory.OST_Windows),
            "Pencere ailesi ({} pencere)".format(kinds["window"]),
            "", skip_label="Opening kullan", label_fn=_symbol_label)
    return Choices(exterior, group_types, door, window)


def _status_text(status):
    if isinstance(status, dict):
        return ", ".join("{} {}".format(k, v) for k, v in sorted(status.items()))
    return status or ""


def show_report(report, data, output):
    kinds = ("level", "wall", "door", "window", "opening", "room")
    output.print_md("## Rolove Aktar - sonuc")
    output.print_table(
        table_data=[[k, report.count("created", k), report.count("kept", k),
                     report.count("deleted", k), report.count("failed", k)] for k in kinds],
        columns=["Tur", "Olusturulan", "Korunan", "Kullanici silmis", "Basarisiz"],
    )
    if report.failed:
        output.print_md("### Olusturulamayanlar")
        output.print_table(table_data=[[f["kind"], f["id"], f["reason"]] for f in report.failed],
                           columns=["Tur", "Kimlik", "Neden"])
    rejected = data.get("rejected") or []
    if rejected:
        output.print_md("### Modele girmeyenler (hazirlik)")
        output.print_table(
            table_data=[[r.get("kind"), r.get("floor"), r.get("id", ""), r.get("reason")]
                        for r in rejected],
            columns=["Tur", "Kat", "Kimlik", "Neden"])
    element_warnings = [[x.get("kind", "wall"), x["floor"], x["id"], _status_text(x.get("status")),
                         "; ".join(x["warnings"])]
                        for k in ("walls", "openings") for x in data.get(k, [])
                        if x.get("warnings")]
    if element_warnings:
        output.print_md("### Eleman uyarilari (taramayla dogrulanamayanlar)")
        output.print_table(table_data=element_warnings,
                           columns=["Tur", "Kat", "Kimlik", "Durum", "Uyari"])
    warnings = list(report.warnings) + list(data.get("warnings") or [])
    if warnings:
        output.print_md("### Uyarilar")
        for w in warnings:
            output.print_md("- {}".format(w))
    if data.get("previews"):
        output.print_md("### Onizlemeler")
        for p in data["previews"]:
            output.print_md("- `{}`".format(p))
    output.print_md(
        "Duvarlar `pyKalfa Tarama Durumu` parametresiyle filtrelenebilir "
        "(olculdu / duzeltildi / varsayildi). Revit suresi: {:.1f} s".format(report.seconds))
    forms.alert(
        "Olusturulan {}  |  korunan {}  |  kullanici silmis {}  |  basarisiz {}\n"
        "Revit suresi {:.1f} s. Ayrinti pyRevit cikti penceresinde.".format(
            len(report.created), len(report.kept), len(report.deleted), len(report.failed),
            report.seconds),
        title="Rolove Aktar - sonuc")
