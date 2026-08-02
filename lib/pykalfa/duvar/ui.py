# -*- coding: utf-8 -*-
"""Duvar Aktar - kullanici girdileri.

Butun diyaloglar tek yerde toplanir; `script.py` sadece akisi kurar,
`revit_creator.py` hic diyalog acmaz (boylece ikisi de ayri ayri
okunabilir/degistirilebilir kalir).

Olcu birimi konusu: kullaniciyla **metre** uzerinden konusulur (kat
plani baglaminda en dogal birim), Revit API'sine **feet** verilir --
donusum bu modulun sinirinda yapilir, disari hep feet cikar.
"""

from pyrevit import forms, script

from pykalfa import selectors

FEET_PER_METER = 1.0 / 0.3048

DEFAULT_WALL_HEIGHT_M = 2.80

# Kullanicinin elle secebilecegi cizim birimleri (DXF'te birim
# belirtilmemisse sorulur).
UNIT_CHOICES = ("mm", "cm", "m", "in", "ft")


def pick_dxf():
    """DXF dosyasi sectirir; iptal edilirse scripti sonlandirir."""
    path = forms.pick_file(file_ext="dxf", title="Kat plani DXF dosyasini secin")
    if not path:
        script.exit()
    return path


def ask_units(detected_name, reason):
    """Cizim birimi kesin degilse kullaniciya sordurur.

    Tespit edilen birim onerilen secenek olarak basa alinir."""
    options = [detected_name] + [u for u in UNIT_CHOICES if u != detected_name]
    chosen = forms.CommandSwitchWindow.show(
        options,
        message="Cizim birimi: {}\nTahmin: {} -- dogru mu?".format(reason, detected_name),
    )
    if not chosen:
        script.exit()
    return chosen


def ask_wall_height_ft():
    """Duvar yuksekligini metre olarak sorar, feet dondurur."""
    text = forms.ask_for_string(
        default="{:.2f}".format(DEFAULT_WALL_HEIGHT_M),
        prompt="Duvar (kat) yuksekligini metre olarak girin",
        title="Duvar yuksekligi",
    )
    if not text:
        script.exit()
    try:
        height_m = float(text.strip().replace(",", "."))
    except ValueError:
        forms.alert("Gecersiz yukseklik degeri: {!r}".format(text), exitscript=True)
    if height_m <= 0:
        forms.alert("Duvar yuksekligi sifirdan buyuk olmali.", exitscript=True)
    return height_m * FEET_PER_METER


def pick_level(doc):
    return selectors.pick_level(doc, title="Duvarlarin baglanacagi level'i secin")


def pick_wall_type(doc, measured_thickness_ft=None):
    """Duvar tipi sectirir.

    Cizimden bir kalinlik olculebildiyse baslikta gosterilir: kullanici
    "10 cm" bilgisini gorup projesindeki uygun tipi secebilsin diye.
    Tip OTOMATIK secilmez -- proje sablonundaki tip adlari/katmanlari
    ongorulemez oldugu icin karar kullanicida birakilir."""
    title = "Duvar tipini secin"
    if measured_thickness_ft:
        title = "Duvar tipini secin (cizimde olculen: {:.0f} cm)".format(
            measured_thickness_ft * 0.3048 * 100
        )
    return selectors.pick_wall_type(doc, title=title)


# Katman adinda bunlardan biri geciyorsa "duvar katmani" onerisi one
# cikar (ör. Polycam'in "Poly-Walls"i). Sadece bir ONERI'dir, filtre
# degil -- son karar her zaman kullanicida.
WALL_LAYER_HINTS = ("wall", "duvar", "mur", "wand")


def _layer_label(name, info):
    parts = ["{} duvar".format(info["count"]), "{:.1f} m".format(info["length_ft"] * 0.3048)]
    if info.get("thickness_ft"):
        parts.append("kalinlik {:.0f} cm".format(info["thickness_ft"] * 0.3048 * 100))
    return "{}  ({})".format(name, ", ".join(parts))


def _suggest_layer(layer_summary):
    """En olasi duvar katmani: once ad ipucu, yoksa en uzun toplam."""
    by_length = sorted(layer_summary.items(), key=lambda kv: -kv[1]["length_ft"])
    for name, _info in by_length:
        lowered = name.lower()
        if any(hint in lowered for hint in WALL_LAYER_HINTS):
            return name
    return by_length[0][0] if by_length else None


def choose_layers(layer_summary):
    """Hangi DXF katmanlarindan duvar uretilecegini sectirir.

    Kat plani ciktilarinda duvarin yani sira kapi, pencere, mobilya,
    olculendirme ve logo katmanlari da bulunur -- ve bunlarin bir kismi
    (kapi/pencere) duvarla ayni sekilde cizildigi icin geometriden
    ayirt edilemez. Ayrim ancak KATMAN uzerinden yapilabilir.

    Once tek bir oneri sunulur (çogu durumda dogru olan); kullanici
    reddederse tam liste acilir. Secilen katman adlarinin kumesini
    dondurur."""
    if not layer_summary:
        return set()
    if len(layer_summary) == 1:
        return set(layer_summary.keys())

    suggested = _suggest_layer(layer_summary)
    if suggested:
        others = sorted(
            (n for n in layer_summary if n != suggested),
            key=lambda n: -layer_summary[n]["length_ft"],
        )
        if forms.alert(
            "Duvar katmani olarak su oneriliyor:\n\n    {}\n\n"
            "Diger katmanlar: {}\n\n"
            "Bu katman kullanilsin mi? ('Hayir' derseniz tum katmanlari "
            "listeleyip coklu secim yapabilirsiniz.)".format(
                _layer_label(suggested, layer_summary[suggested]),
                ", ".join(others) or "yok",
            ),
            title="Katman secimi",
            yes=True,
            no=True,
        ):
            return {suggested}

    # En uzun toplam duvar iceren katman basta gorunsun.
    ordered = sorted(layer_summary.items(), key=lambda kv: -kv[1]["length_ft"])
    label_to_layer = {_layer_label(name, info): name for name, info in ordered}

    chosen_labels = forms.SelectFromList.show(
        list(label_to_layer.keys()),
        title="Duvara donusturulecek katmanlari secin",
        multiselect=True,
    )
    if not chosen_labels:
        script.exit()
    if not isinstance(chosen_labels, list):
        chosen_labels = [chosen_labels]
    return set(label_to_layer[label] for label in chosen_labels)


def confirm_line_mode():
    """Hic kapali duvar dis hatti bulunamadiysa tek cizgi moduna gecis onayi."""
    return forms.alert(
        "Bu DXF'te kapali duvar dis hatti (outline) bulunamadi.\n\n"
        "Duvarlar tek cizgiyle cizilmis olabilir. Cizgileri dogrudan duvar "
        "ekseni olarak kullanmayi deneyeyim mi?\n\n"
        "Not: bu modda duvar kalinligi cizimden olculemez (sectiginiz duvar "
        "tipinden gelir) ve mobilya/olculendirme cizgileri de duvara "
        "donusebilir -- katman secimi bu yuzden onemli olur.",
        title="Duvar bulunamadi",
        yes=True,
        no=True,
    )


def confirm_recenter(distance_ft):
    """Cizim Revit orijininden cok uzaksa tasima onayi ister."""
    return forms.alert(
        "Cizim Revit orijininden yaklasik {:.0f} m uzakta.\n\n"
        "Revit bu kadar uzakta modellenen geometride hassasiyet uyarilari "
        "verir ve islemler kararsizlasabilir.\n\n"
        "Cizimi orijine tasiyayim mi? (Duvarlarin birbirine gore konumu "
        "degismez, sadece tamami orijine kaydirilir.)".format(distance_ft * 0.3048),
        title="Orijinden uzak cizim",
        yes=True,
        no=True,
    )


def confirm_creation(count, height_ft, wall_type_name, level_name,
                     measured_thickness_ft=None, total_length_ft=0.0):
    """Olusturmadan once son ozet/onay."""
    lines = [
        "{} adet duvar olusturulacak (toplam {:.1f} m).".format(
            count, total_length_ft * 0.3048
        ),
        "",
        "Tip: {}".format(wall_type_name),
        "Level: {}".format(level_name),
        "Yukseklik: {:.2f} m".format(height_ft * 0.3048),
    ]
    if measured_thickness_ft:
        lines.append(
            "Cizimde olculen kalinlik: {:.0f} cm (duvar tipininki kullanilacak)".format(
                measured_thickness_ft * 0.3048 * 100
            )
        )
    lines += ["", "Devam edilsin mi?"]
    return forms.alert("\n".join(lines), title="Duvar Aktar - onay", yes=True, no=True)


def show_report(report, output):
    """Sonucu ozetler; basarisiz cizgiler varsa pyRevit ciktisina tablo basar."""
    if report.failed:
        output.print_md("### Duvar Aktar - olusturulamayan cizgiler")
        try:
            output.print_table(
                table_data=[
                    [
                        f["index"],
                        f["layer"],
                        "{:.2f} m".format(f["length_ft"] * 0.3048),
                        "({:.2f}, {:.2f}) -> ({:.2f}, {:.2f})".format(
                            f["start"][0] * 0.3048, f["start"][1] * 0.3048,
                            f["end"][0] * 0.3048, f["end"][1] * 0.3048,
                        ),
                        f["reason"],
                    ]
                    for f in report.failed
                ],
                columns=["#", "Katman", "Uzunluk", "Konum (m)", "Hata"],
            )
        except Exception:
            # print_table pyRevit surumune gore degisebiliyor; rapor
            # kaybolmasin diye duz metne duseriz.
            for f in report.failed:
                output.print_md("- **{}** ({}) -- {}".format(
                    f["index"], f["layer"], f["reason"]))

    forms.alert(
        "Olusturulan duvar: {}\n"
        "Olusturulamayan: {}\n"
        "Toplam duvar uzunlugu: {:.1f} m".format(
            report.created, len(report.failed), report.created_length_ft * 0.3048
        ),
        title="Duvar Aktar - sonuc",
    )
