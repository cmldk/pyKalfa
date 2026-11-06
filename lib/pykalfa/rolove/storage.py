# -*- coding: utf-8 -*-
"""Rolove kimlikleri icin Extensible Storage (gorunmez, kullanici bozamaz).

Tek sema, iki String alan:
  - `StableId` : uretilen her elemanda, JSON'daki kararli id;
  - `Ledger`   : ProjectInformation'da, `ledger.dumps` metni.

`tag` / `set_ledger` belge degistirir: ACIK bir Transaction icinde
cagrilmalidir. Sema GUID'i sabittir; degistirmek eski projelerdeki
etiketleri gorunmez yapar.
"""

from System import Guid, String

from Autodesk.Revit.DB.ExtensibleStorage import AccessLevel, Entity, Schema, SchemaBuilder

from pykalfa.rolove import ledger as ledger_mod

SCHEMA_GUID = "5d0c8b7e-3f41-4a8e-9b6a-7c2f1e9d4a60"
SCHEMA_NAME = "pyKalfaRolove"
FIELD_ID = "StableId"
FIELD_LEDGER = "Ledger"


def schema():
    """Semayi bulur, yoksa olusturur (oturum basina bir kez)."""
    guid = Guid(SCHEMA_GUID)
    existing = Schema.Lookup(guid)
    if existing is not None:
        return existing
    builder = SchemaBuilder(guid)
    builder.SetSchemaName(SCHEMA_NAME)
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.SetDocumentation("pyKalfa Rolove Aktar: kararli id ve proje defteri")
    builder.AddSimpleField(FIELD_ID, String)
    builder.AddSimpleField(FIELD_LEDGER, String)
    return builder.Finish()


def _entity_of(element, sch):
    ent = element.GetEntity(sch)
    if ent is None or not ent.IsValid():
        ent = Entity(sch)
    return ent


def tag(element, stable_id):
    sch = schema()
    ent = _entity_of(element, sch)
    ent.Set[String](FIELD_ID, stable_id)
    element.SetEntity(ent)


def read_tag(element):
    sch = Schema.Lookup(Guid(SCHEMA_GUID))
    if sch is None:
        return None
    ent = element.GetEntity(sch)
    if ent is None or not ent.IsValid():
        return None
    value = ent.Get[String](FIELD_ID)
    return value or None


def get_ledger(doc):
    sch = Schema.Lookup(Guid(SCHEMA_GUID))
    if sch is None:
        return ledger_mod.empty()
    ent = doc.ProjectInformation.GetEntity(sch)
    if ent is None or not ent.IsValid():
        return ledger_mod.empty()
    return ledger_mod.loads(ent.Get[String](FIELD_LEDGER))


def set_ledger(doc, d):
    sch = schema()
    info = doc.ProjectInformation
    ent = _entity_of(info, sch)
    ent.Set[String](FIELD_LEDGER, ledger_mod.dumps(d))
    info.SetEntity(ent)
