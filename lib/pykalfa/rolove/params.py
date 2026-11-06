# -*- coding: utf-8 -*-
"""Rolove tarama parametreleri (duvar / kapi / pencere, ornek parametresi).

Mimarin modelde filtreleyip renklendirebilmesi icin uc gorunur parametre:
durum (`olculdu` / `duzeltildi` / `varsayildi`), sapma (cm) ve olculen
kalinlik (cm). Shared parameter olarak gecici bir dosyadan baglanir;
kullanicinin kendi shared parameter dosyasi yolu islem sonunda geri
yuklenir. GUID'ler sabittir: ayni parametre baska projelere kopyalansa da
ayni kimlikte kalir.

`ensure_parameters` belge degistirir: ACIK bir Transaction icinde cagrilir.
"""

import os

from System import Guid

from Autodesk.Revit.DB import (
    BuiltInCategory,
    Category,
    CategorySet,
    ExternalDefinitionCreationOptions,
    GroupTypeId,
    InstanceBinding,
    SpecTypeId,
)

from pykalfa import paths

NAMES = {
    "status": "pyKalfa Tarama Durumu",
    "deviation": "pyKalfa Tarama Sapma cm",
    "thickness": "pyKalfa Olculen Kalinlik cm",
}
_GUIDS = {
    "status": "a3f1c0de-5b2e-4f7a-9c11-1e0b7d2c4a01",
    "deviation": "a3f1c0de-5b2e-4f7a-9c11-1e0b7d2c4a02",
    "thickness": "a3f1c0de-5b2e-4f7a-9c11-1e0b7d2c4a03",
}
CATEGORIES = (BuiltInCategory.OST_Walls, BuiltInCategory.OST_Doors, BuiltInCategory.OST_Windows)
GROUP_NAME = "pyKalfa Rolove"
PARAM_FILE = "pykalfa_rolove_params.txt"


def _specs():
    return {"status": SpecTypeId.String.Text, "deviation": SpecTypeId.Number,
            "thickness": SpecTypeId.Number}


def _bound_names(doc):
    names = set()
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        names.add(it.Key.Name)
    return names


def ensure_parameters(doc, app):
    """Eksik parametreleri baglar; zaten bagli olanlara dokunmaz.
    Doner: {"status": ad, "deviation": ad, "thickness": ad}."""
    bound = _bound_names(doc)
    todo = [k for k in ("status", "deviation", "thickness") if NAMES[k] not in bound]
    if not todo:
        return dict(NAMES)

    path = os.path.join(paths.output_dir(), PARAM_FILE)
    with open(path, "w"):
        pass                                  # bos dosya: Revit basligi kendisi yazar
    old = app.SharedParametersFilename
    try:
        app.SharedParametersFilename = path
        sp_file = app.OpenSharedParameterFile()
        if sp_file is None:
            raise RuntimeError("Gecici shared parameter dosyasi acilamadi: {}".format(path))
        group = sp_file.Groups.get_Item(GROUP_NAME) or sp_file.Groups.Create(GROUP_NAME)
        cats = CategorySet()
        for bic in CATEGORIES:
            cat = Category.GetCategory(doc, bic)
            if cat is not None:
                cats.Insert(cat)
        specs = _specs()
        for key in todo:
            definition = group.Definitions.get_Item(NAMES[key])
            if definition is None:
                opts = ExternalDefinitionCreationOptions(NAMES[key], specs[key])
                opts.GUID = Guid(_GUIDS[key])
                opts.Description = "pyKalfa Rolove Aktar (Polycam taramasi)"
                definition = group.Definitions.Create(opts)
            doc.ParameterBindings.Insert(definition, InstanceBinding(cats), GroupTypeId.Data)
    finally:
        try:
            app.SharedParametersFilename = old or ""
        except Exception:  # noqa: BLE001 - eski yol artik yoksa Revit reddedebilir
            pass
    return dict(NAMES)


def _set(element, name, value):
    if value is None:
        return
    p = element.LookupParameter(name)
    if p is None or p.IsReadOnly:
        return
    p.Set(value)


def set_values(element, names, status, deviation_cm, thickness_cm):
    """`None` degerler atlanir (ör. dis duvarda olculen kalinlik yok)."""
    _set(element, names["status"], status)
    _set(element, names["deviation"], None if deviation_cm is None else float(deviation_cm))
    _set(element, names["thickness"], None if thickness_cm is None else float(thickness_cm))
