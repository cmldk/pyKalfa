# -*- coding: utf-8 -*-
"""Rolove Aktar girdileri: numarali "Input 1..4" tanimlari ve klasorden
tahmin (saf Python; Revit import'u yok, CPython selftest'ten de calisir).

Kullaniciya dosya turu yerine sirali, adli girdiler gosterilir:

    Input 1 - Kat plani      (.dxf ya da kat plani .zip)
    Input 2 - Oda listesi    (.csv)
    Input 3 - Nokta bulutu   (.laz / .las, georef KAPALI)
    Input 4 - 3B model       (.glb)

Input 1 secilince ayni klasorde ayni adli digerleri onerilir; dosya
adlarinin uymasi zorunlu degildir, her girdi ayrica secilebilir.
"""

import os
import re
import zipfile

INPUTS = (
    {"n": 1, "key": "dxf", "title": "Kat plani", "ext": ".dxf ya da kat plani .zip",
     "polycam": "Floor plan -> DXF (ya da Floor plan zip'i)",
     "filter": "Kat plani (*.dxf;*.zip)|*.dxf;*.zip", "exts": (".dxf", ".zip")},
    {"n": 2, "key": "csv", "title": "Oda listesi", "ext": ".csv",
     "polycam": "Floor plan -> CSV",
     "filter": "Oda listesi (*.csv)|*.csv", "exts": (".csv",)},
    {"n": 3, "key": "laz", "title": "Nokta bulutu", "ext": ".laz / .las, georef KAPALI",
     "polycam": "Point cloud -> LAS ('Georeferenced' KAPALI)",
     "filter": "Nokta bulutu (*.laz;*.las)|*.laz;*.las", "exts": (".laz", ".las")},
    {"n": 4, "key": "glb", "title": "3B model", "ext": ".glb",
     "polycam": "Mesh -> GLTF (.glb)",
     "filter": "3B model (*.glb)|*.glb", "exts": (".glb",)},
)
BY_KEY = dict((i["key"], i) for i in INPUTS)
FROM_ZIP = "zip"                 # Input 2, Input 1 zip'inin icinden gelecek

_DUP_SUFFIX = re.compile(r"\s*\(\d+\)$")      # tarayicinin "ad (1).zip" eki


def label(key):
    i = BY_KEY[key]
    return "Input {} - {} ({})".format(i["n"], i["title"], i["ext"])


def short_label(key):
    i = BY_KEY[key]
    return "Input {} - {}".format(i["n"], i["title"])


def is_georef(path):
    return "georef" in os.path.basename(path).lower()


def zip_members(path):
    """Zip'teki dosya uzantilari (kucuk harf); okunamazsa bos kume."""
    try:
        with zipfile.ZipFile(path) as z:
            return set(os.path.splitext(n)[1].lower() for n in z.namelist())
    except Exception:  # noqa: BLE001 - bozuk/kilitli zip: tahmin yok
        return set()


def guess(input1, listdir=os.listdir):
    """Input 1'e gore {anahtar: yol | FROM_ZIP} onerisi (bulunamayanlar yok).
    Ad koku Input 1'in adi; tarayicinin " (1)" eki de denenir. Adinda
    'georef' gecen nokta bulutu ONERILMEZ (yanlis koordinat sistemi)."""
    folder = os.path.dirname(input1)
    stem, ext = os.path.splitext(os.path.basename(input1))
    stems = [stem]
    if _DUP_SUFFIX.search(stem):
        stems.append(_DUP_SUFFIX.sub("", stem))
    out = {"dxf": input1}
    if ext.lower() == ".zip":
        members = zip_members(input1)
        if ".csv" in members:
            out["csv"] = FROM_ZIP
    try:
        names = listdir(folder)
    except OSError:
        names = []
    lower = dict((n.lower(), n) for n in names)
    for key in ("csv", "laz", "glb"):
        if key in out:
            continue
        for s in stems:
            hit = None
            for e in BY_KEY[key]["exts"]:
                name = lower.get((s + e).lower())
                if name and not is_georef(name):
                    hit = os.path.join(folder, name)
                    break
            if hit:
                out[key] = hit
                break
    return out


def problems(selection):
    """Secimdeki sorunlar: [(anahtar, mesaj)]. Bos liste = devam edilebilir."""
    out = []
    for i in INPUTS:
        value = selection.get(i["key"])
        if not value:
            out.append((i["key"], "secilmedi"))
        elif value != FROM_ZIP and not os.path.isfile(value):
            out.append((i["key"], "dosya yok: {}".format(value)))
        elif value != FROM_ZIP and os.path.splitext(value)[1].lower() not in i["exts"]:
            out.append((i["key"], "uzanti {} olmali".format(" / ".join(i["exts"]))))
        elif i["key"] == "laz" and value != FROM_ZIP and is_georef(value):
            out.append((i["key"], "georef'li nokta bulutu: Polycam'de 'Georeferenced' "
                                  "KAPALI export edin"))
    if selection.get("dxf", "").lower().endswith(".zip") and \
            ".dxf" not in zip_members(selection["dxf"]):
        out.append(("dxf", "bu zip'te DXF yok (Polycam'in OBJ/mesh zip'i olabilir)"))
    return out


def cli_args(selection):
    """prepare_rolove_input.py argumanlari."""
    args = ["--input", selection["dxf"]]
    for key in ("csv", "laz", "glb"):
        value = selection.get(key)
        if value and value != FROM_ZIP:
            args += ["--" + key, value]
    return args
