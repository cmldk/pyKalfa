# -*- coding: utf-8 -*-
"""Rolove Prototip - diyaloglar (ozet/onay, doseme tipi, cakisma kontrolu).

Girdi secimi, kot duzenleme, duvar/aciklik secimleri ve rapor Rolove
Aktar'in `ui` modulunden gelir. IronPython 2.7.
"""

from Autodesk.Revit.DB import FilteredElementCollector, FloorType
from pyrevit import forms, script

from pykalfa.revitutils import elem_name
from pykalfa.rolove import creator, ledger, storage
from pykalfa.rolove import ui as rolove_ui
from pykalfa.selectors import pick_by_name

TITLE = "Rolove Prototip"
PREFIX = "p-"
REPORT_KINDS = ("level", "wall", "floor", "door", "window", "opening", "separation", "room")


def rolove_conflicts(doc):
    """Projede hala duran Rolove Aktar (p- oneksiz) eleman sayisi."""
    led = storage.get_ledger(doc)
    items = led["items"]
    return len([k for k in ledger.foreign_items(items, PREFIX)
                if creator._alive(doc, items.get(k))])


def existing_slabs(doc):
    """Bu projede daha once olusturulmus prototip dosemeleri: duran / silinmis."""
    items = storage.get_ledger(doc)["items"]
    alive = set(uid for uid in items.values() if creator._alive(doc, uid))
    return ledger.count_prefixed(items, PREFIX + "floor-", alive)


def summary_text(data, plan, conflict_count, slabs=None):
    proto = data.get("prototype") or {}
    lines = []
    if conflict_count:
        lines.append("UYARI: Bu projede eski Rolove Aktar ile olusturulmus {} eleman var. Prototip "
                     "onlarin USTUNE ikinci bir bina olusturur; ayri bir projede "
                     "calistirmaniz onerilir.".format(conflict_count))
        lines.append("")
    lines.append("PROTOTIP: rolove toparlanir, olculen rolove degildir.")
    lines.append("  Baskin yon {:.2f} derece; diklestirilen duvar {}, katlar arasi hizalanan "
                 "dis duvar {}.".format(proto.get("theta_deg", 0.0), proto.get("orthogonalized", 0),
                                        proto.get("stacked", 0)))
    skipped = proto.get("skipped") or []
    if skipped:
        lines.append("  {} duvar {} dereceden fazla egik oldugu icin oldugu gibi birakildi.".format(
            len(skipped), (proto.get("params") or {}).get("angle_max_deg", 5)))
    lines.append("  Yerinden oynayan duvarlar 'duzeltildi' olur, sapma (cm) taramadan uzakligi.")
    lines.append("  Duvarlar ust katin Level'ina baglanir ve dosemenin altinda biter; en ust "
                 "katin duvarlari taranan yukseklikte kalir.")
    lines.append("  Doseme = katin izi + alttaki katin izi (ustu acik kalan kisim duz cati "
                 "varsayilir). Cati, merdiven ve merdiven boslugu yok.")
    lines.append("  Dosemeler dis duvar tipi secildikten sonra hesaplanir (asagidaki "
                 "sayilara dahil degil).")
    if slabs and (slabs.get("alive") or slabs.get("deleted")):
        lines.append("  Bu projede onceki prototip dosemeleri: {} duruyor (korunur), {} silinmis "
                     "(geri gelmez).".format(slabs.get("alive", 0), slabs.get("deleted", 0)))
    lines.append("")
    lines.append(rolove_ui._summary_text(data, plan))
    return "\n".join(lines)


def summary_and_confirm(data, plan, conflict_count, slabs=None):
    """"create" | "edit"; iptal scripti sonlandirir."""
    choice = forms.alert(summary_text(data, plan, conflict_count, slabs),
                         title="{} - onizleme".format(TITLE),
                         options=[rolove_ui.CREATE, rolove_ui.EDIT, rolove_ui.CANCEL])
    if choice == rolove_ui.CREATE:
        return "create"
    if choice == rolove_ui.EDIT:
        return "edit"
    script.exit()


def _floor_label(ft):
    return "{}  ({:.0f} cm)".format(elem_name(ft), creator.floor_type_thickness_ft(ft) * 30.48)


def pick_floor_type(doc):
    types = [t for t in FilteredElementCollector(doc).OfClass(FloorType)
             if creator.floor_type_thickness_ft(t) > 0]
    return pick_by_name(types, "Doseme tipi (ust yuzu kat kotunda, kalinlik asagi dogru)",
                        "Projede kalinligi olan bir Floor Type bulunamadi.",
                        label_fn=_floor_label)


def show_report(report, data, output):
    rolove_ui.show_report(report, data, output, title=TITLE, kinds=REPORT_KINDS)
