# -*- coding: utf-8 -*-
"""Rolove Aktar - `rolove_input.json`'dan Revit elemanlari.

Diyalog acmaz, girdi sormaz: hazir veriyi ve kullanici secimlerini
(`Choices`) alir, tek bir TransactionGroup icinde asama asama uretir:

    parametreler -> Level -> Wall -> kapi/pencere/Opening -> Room -> defter

Kurallar:
  - Her uretilen eleman kararli id ile etiketlenir (`storage.tag`) ve
    defterde (`ledger.items`) UniqueId'siyle tutulur. Yeniden calistirmada
    defterde olup hala duran eleman KORUNUR (yerinden oynatilmis olsa da),
    kullanicinin sildigi YENIDEN OLUSTURULMAZ, yalniz yeni olanlar eklenir.
  - Tek bir elemanin hatasi raporlanir, akis devam eder. Bir ASAMANIN
    kendisi patlarsa (beklenmeyen istisna) butun grup geri alinir.
  - Uyarilar yutulur (`WarningSwallower`); gercek hatalar Revit'e kalir.

IronPython 2.7.
"""

import math
import time

from Autodesk.Revit.DB import (
    BuiltInParameter,
    FailureProcessingResult,
    FailureResolutionType,
    FailureSeverity,
    FilteredElementCollector,
    IFailuresPreprocessor,
    Level,
    Line,
    Transaction,
    TransactionGroup,
    TransactionStatus,
    UV,
    ViewFamily,
    ViewFamilyType,
    ViewPlan,
    Wall,
    WallLocationLine,
    WallUtils,
    XYZ,
)
from Autodesk.Revit.DB.Structure import StructuralType
from pyrevit import script

from pykalfa.revitutils import WarningSwallower, elem_name
from pykalfa.rolove import ledger as ledger_mod
from pykalfa.rolove import params, storage

logger = script.get_logger()

FT_PER_M = 1.0 / 0.3048
LINE_CHECK_FT = 0.001 * FT_PER_M        # 1 mm
MIN_CURVE_FT = 0.01
JOIN_ATTEMPTS = 4

WIDTH_BIPS = {
    "door": ("DOOR_WIDTH", "FAMILY_WIDTH_PARAM", "FAMILY_ROUGH_WIDTH_PARAM"),
    "window": ("WINDOW_WIDTH", "FAMILY_WIDTH_PARAM", "FAMILY_ROUGH_WIDTH_PARAM"),
}
HEIGHT_BIPS = {
    "door": ("DOOR_HEIGHT", "FAMILY_HEIGHT_PARAM", "FAMILY_ROUGH_HEIGHT_PARAM"),
    "window": ("WINDOW_HEIGHT", "FAMILY_HEIGHT_PARAM", "FAMILY_ROUGH_HEIGHT_PARAM"),
}
WIDTH_NAMES = ("Width", "Breedte", "Largeur", "Genislik")
HEIGHT_NAMES = ("Height", "Hoogte", "Hauteur", "Yukseklik")


class Choices(object):
    """Kullanici secimleri (ui.pick_choices doldurur)."""

    def __init__(self, exterior_type, group_types, door_symbol=None, window_symbol=None,
                 level_overrides=None):
        self.exterior_type = exterior_type
        self.group_types = group_types or {}
        self.door_symbol = door_symbol
        self.window_symbol = window_symbol
        self.level_overrides = level_overrides or {}


class Report(object):
    def __init__(self):
        self.created = []
        self.kept = []
        self.deleted = []
        self.failed = []
        self.warnings = []
        self.seconds = 0.0

    def add(self, bucket, kind, ident, reason=""):
        getattr(self, bucket).append({"kind": kind, "id": ident, "reason": reason})

    def count(self, bucket, kind=None):
        return len([x for x in getattr(self, bucket) if kind is None or x["kind"] == kind])


# --------------------------------------------------------------------------
# Yardimcilar
# --------------------------------------------------------------------------

def _xyz(p, z=0.0):
    return XYZ(float(p[0]), float(p[1]), float(z))


def _transaction(doc, name):
    t = Transaction(doc, name)
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(opts)
    return t


def _alive(doc, uid):
    try:
        return uid is not None and doc.GetElement(uid) is not None
    except Exception:  # noqa: BLE001
        return False


def _set_bip_or_name(element, bip_names, names, value):
    for bip_name in bip_names:
        bip = getattr(BuiltInParameter, bip_name, None)
        if bip is None:
            continue
        p = element.get_Parameter(bip)
        if p is not None and not p.IsReadOnly:
            p.Set(value)
            return True
    for name in names:
        p = element.LookupParameter(name)
        if p is not None and not p.IsReadOnly:
            p.Set(value)
            return True
    return False


def _unique_level_name(doc, name):
    taken = set(elem_name(l) for l in FilteredElementCollector(doc).OfClass(Level))
    if name not in taken:
        return name
    n = 2
    while "{} {}".format(name, n) in taken:
        n += 1
    return "{} {}".format(name, n)


class _Ctx(object):
    """Bir calistirmanin durumu: defter, eleman haritalari, rapor."""

    def __init__(self, doc, app, data, choices):
        self.doc = doc
        self.app = app
        self.data = data
        self.choices = choices
        self.ledger = storage.get_ledger(doc)
        self.items = self.ledger["items"]
        self.report = Report()
        self.levels = {}          # floor -> Level
        self.walls = {}           # wall id -> Wall
        self.wall_json = {}       # wall id -> JSON
        self.param_names = None
        self.type_cache = {}
        self.created_sids = []
        self.new_walls = []        # (JSON, Wall): bu calistirmada olusturulanlar

    def plan(self, ids):
        existing = set(uid for uid in self.items.values() if _alive(self.doc, uid))
        return ledger_mod.plan_actions(ids, self.items, existing)

    def remember(self, sid, element):
        storage.tag(element, sid)
        self.items[sid] = element.UniqueId
        self.created_sids.append(sid)


# --------------------------------------------------------------------------
# Asamalar
# --------------------------------------------------------------------------

def _stage_levels(ctx):
    levels = ctx.data.get("levels", [])
    plan = ctx.plan([lv["id"] for lv in levels])
    for lv in levels:
        sid = lv["id"]
        if sid in plan["keep"]:
            ctx.levels[lv["floor"]] = ctx.doc.GetElement(ctx.items[sid])
            ctx.report.add("kept", "level", sid)
        elif sid in plan["deleted"]:
            ctx.report.add("deleted", "level", sid, "kullanici silmis: kat atlandi")
        else:
            elev_m = ctx.choices.level_overrides.get(sid, lv["elevation_m"])
            level = Level.Create(ctx.doc, float(elev_m) * FT_PER_M)
            level.Name = _unique_level_name(ctx.doc, lv["name"])
            ctx.remember(sid, level)
            ctx.levels[lv["floor"]] = level
            ctx.report.add("created", "level", sid)
            _plan_view(ctx, level)


def _plan_view(ctx, level):
    """Yeni Level icin kat plani gorunumu (Level.Create gorunum uretmez)."""
    vft = None
    for t in FilteredElementCollector(ctx.doc).OfClass(ViewFamilyType):
        if t.ViewFamily == ViewFamily.FloorPlan:
            vft = t
            break
    if vft is None:
        ctx.report.warnings.append("Projede Floor Plan gorunum tipi yok: {} icin plan "
                                   "olusturulmadi".format(elem_name(level)))
        return
    try:
        view = ViewPlan.Create(ctx.doc, vft.Id, level.Id)
        view.Name = elem_name(level)
    except Exception as ex:  # noqa: BLE001 - ad cakismasi vb.; gorunum yine de var
        ctx.report.warnings.append("{} plan gorunumu: {}".format(elem_name(level), ex))


def _wall_type_for(ctx, w):
    if w["location"] == "interior_face":
        return ctx.choices.exterior_type
    t = ctx.choices.group_types.get(w.get("thickness_group_cm"))
    if t is None and ctx.choices.group_types:
        groups = ctx.data.get("thickness_groups") or []
        if groups:
            top = max(groups, key=lambda g: g["count"])["cm"]
            t = ctx.choices.group_types.get(top)
        if t is None:
            t = list(ctx.choices.group_types.values())[0]
    return t or ctx.choices.exterior_type


def _json_line(w, level):
    return _xyz(w["start_ft"], level.Elevation), _xyz(w["end_ft"], level.Elevation)


def _outward(w):
    return XYZ(w["outward"][0], w["outward"][1], 0.0)


def _create_wall(ctx, w, level):
    """JSON cizgisi dis duvarda taranan IC YUZ, ic duvarda EKSEN'dir.

    `Wall.Create` verilen egriyi projenin o anki "Location Line" ayarina
    gore yorumlar (eksen olmayabilir) ve yeni duvarin `Orientation`'i
    regenerate edilmeden okunamaz. Bu yuzden: olustur -> uc birlesimlerini
    kapat -> regenerate -> (dis duvarda) yon kontrolu/Flip -> Location
    Line'i acikca ayarla -> egriyi JSON cizgisine tasi.

    Uclar bu sirada birlesik olursa, egri tasinirken Revit daha once
    birlesmis KOMSU duvarin ucunu da surukler; birlesimler butun duvarlar
    commit edildikten sonra `_join_walls` icinde acilir. Herhangi bir adim
    patlarsa yarim duvar silinir (etiketsiz kalip cogalmasin)."""
    wall_type = _wall_type_for(ctx, w)
    p1, p2 = w["start_ft"], w["end_ft"]
    if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < MIN_CURVE_FT:
        raise ValueError("duvar cok kisa")
    exterior = w["location"] == "interior_face"
    a, b = _json_line(w, level)
    wall = Wall.Create(ctx.doc, Line.CreateBound(a, b), wall_type.Id, level.Id,
                       float(w["height_ft"]), 0.0, False, False)
    try:
        WallUtils.DisallowWallJoinAtEnd(wall, 0)
        WallUtils.DisallowWallJoinAtEnd(wall, 1)
        ctx.doc.Regenerate()
        if exterior and wall.Orientation.DotProduct(_outward(w)) < 0:
            wall.Flip()
            ctx.doc.Regenerate()
        key = WallLocationLine.FinishFaceInterior if exterior else WallLocationLine.WallCenterline
        wall.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM).Set(int(key))
        ctx.doc.Regenerate()
        wall.Location.Curve = Line.CreateBound(a, b)
        # Bazi projelerde yeni duvar "Room Bounding = No" gelir; odalar
        # duvarlardan sinir aldigi icin acikca acilir.
        bounding = wall.get_Parameter(BuiltInParameter.WALL_ATTR_ROOM_BOUNDING)
        if bounding is not None and not bounding.IsReadOnly:
            bounding.Set(1)
        params.set_values(wall, ctx.param_names, w["status"], w.get("deviation_cm"),
                          w.get("measured_thickness_cm"))
    except Exception:
        try:
            ctx.doc.Delete(wall.Id)
        except Exception:  # noqa: BLE001 - asil hatayi gizleme
            pass
        raise
    return wall


def _check_wall(ctx, w, wall):
    """Birlesimlerden sonra: konum cizgisi JSON cizgisi UZERINDE mi, dis yuz
    disa mi? Revit kose/T birlesiminde uclari cizgi boyunca uzatip
    kisaltabilir (kosenin kapanmasi, beklenen); yalniz YANAL sapma olculur."""
    (x1, y1), (x2, y2) = w["start_ft"], w["end_ft"]
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    curve = wall.Location.Curve
    err = max(abs((p.X - x1) * uy - (p.Y - y1) * ux)
              for p in (curve.GetEndPoint(0), curve.GetEndPoint(1)))
    exterior = w["location"] == "interior_face"
    if err > LINE_CHECK_FT:
        ctx.report.warnings.append(
            "Duvar {}: {} konumu JSON'dan {:.1f} mm sapti (tip: {})".format(
                w["id"], "ic yuz" if exterior else "eksen", err / FT_PER_M * 1000.0,
                elem_name(wall.WallType)))
    if exterior and wall.Orientation.DotProduct(_outward(w)) < 0:
        ctx.report.warnings.append("Duvar {}: dis yuzu iceri bakiyor".format(w["id"]))


def _stage_walls(ctx):
    walls = ctx.data.get("walls", [])
    plan = ctx.plan([w["id"] for w in walls])
    for w in walls:
        sid = w["id"]
        ctx.wall_json[sid] = w
        if sid in plan["keep"]:
            ctx.walls[sid] = ctx.doc.GetElement(ctx.items[sid])
            ctx.report.add("kept", "wall", sid)
            continue
        if sid in plan["deleted"]:
            ctx.report.add("deleted", "wall", sid, "kullanici silmis")
            continue
        level = ctx.levels.get(w["floor"])
        if level is None:
            ctx.report.add("failed", "wall", sid, "katin Level'i yok (silinmis)")
            continue
        try:
            wall = _create_wall(ctx, w, level)
        except Exception as ex:  # noqa: BLE001 - eleman hatasi raporlanir
            ctx.report.add("failed", "wall", sid, str(ex))
            continue
        ctx.remember(sid, wall)
        ctx.walls[sid] = wall
        ctx.report.add("created", "wall", sid)
        ctx.new_walls.append((w, wall))


class _JoinFailures(IFailuresPreprocessor):
    """Birlesim islemi icin: uyarilar silinir, "Can't keep elements joined"
    birlesim kaldirilarak cozulur (geometri degismez). Baska bir HATA
    (ör. "Element is reversed": kisa/kayik duvarlarda birlesim duvari ters
    cevirir) varsa hatali elemanlar not edilir ve islem geri alinir;
    cagiran onlari birlestirmeden yeniden dener. Kullaniciya diyalog
    cikmaz, hicbir duvar sessizce silinmez."""

    def __init__(self):
        self.bad_ids = set()

    def PreprocessFailures(self, fa):
        resolved = False
        for failure in fa.GetFailureMessages():
            severity = failure.GetSeverity()
            if severity == FailureSeverity.Warning:
                fa.DeleteWarning(failure)
            elif failure.HasResolutionOfType(FailureResolutionType.DetachElements):
                failure.SetCurrentResolutionType(FailureResolutionType.DetachElements)
                fa.ResolveFailure(failure)
                resolved = True
            else:
                for eid in failure.GetFailingElementIds():
                    self.bad_ids.add(eid.ToString())
        if self.bad_ids:
            return FailureProcessingResult.ProceedWithRollBack
        if resolved:
            return FailureProcessingResult.ProceedWithCommit
        return FailureProcessingResult.Continue


def _join_walls(ctx):
    """Duvarlar birlesimsiz commit edildikten sonra uclarini ac: Revit
    uca/govdeye degen duvarlari (kose, T) kendisi birlestirir ve uclari
    cizgi boyunca uzatir/kisaltir. Birlesimi hata veren duvarlar
    birlesimsiz birakilir (en cok JOIN_ATTEMPTS deneme)."""
    skipped = set()
    for _ in range(JOIN_ATTEMPTS):
        pre = _JoinFailures()
        t = Transaction(ctx.doc, "pyKalfa Rolove: birlesimler")
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(pre)
        opts.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(opts)
        t.Start()
        try:
            for w, wall in ctx.new_walls:
                if wall.Id.ToString() in skipped:
                    continue
                WallUtils.AllowWallJoinAtEnd(wall, 0)
                WallUtils.AllowWallJoinAtEnd(wall, 1)
            status = t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
        if status == TransactionStatus.Committed:
            break
        new_bad = pre.bad_ids - skipped
        if not new_bad:
            raise RuntimeError("duvar birlesimleri Revit tarafindan geri alindi ({})".format(status))
        skipped |= new_bad
    else:
        raise RuntimeError("duvar birlesimleri {} denemede tamamlanamadi".format(JOIN_ATTEMPTS))
    for w, wall in ctx.new_walls:
        if wall.Id.ToString() in skipped:
            ctx.report.warnings.append(
                "Duvar {}: komsu duvarlarla birlestirilemedi (Revit hatasi); uclari "
                "serbest birakildi, kontrol edin".format(w["id"]))
        _check_wall(ctx, w, wall)


def _scan_type(ctx, kind, base_symbol, width_ft, height_ft, w_cm, h_cm):
    """"Scan {w}x{h}" tipi: ailede varsa o, yoksa secilen tipten kopya.
    Genislik/yukseklik yazilamazsa None (cagiran Opening'e duser)."""
    key = (kind, w_cm, h_cm)
    if key in ctx.type_cache:
        return ctx.type_cache[key]
    name = "Scan {}x{}".format(w_cm, h_cm)
    symbol = None
    for sid in base_symbol.Family.GetFamilySymbolIds():
        s = ctx.doc.GetElement(sid)
        if elem_name(s) == name:
            symbol = s
            break
    if symbol is None:
        symbol = base_symbol.Duplicate(name)
        ok_w = _set_bip_or_name(symbol, WIDTH_BIPS[kind], WIDTH_NAMES, width_ft)
        ok_h = _set_bip_or_name(symbol, HEIGHT_BIPS[kind], HEIGHT_NAMES, height_ft)
        if not (ok_w and ok_h):
            ctx.doc.Delete(symbol.Id)
            symbol = None
    if symbol is not None and not symbol.IsActive:
        symbol.Activate()
        ctx.doc.Regenerate()
    ctx.type_cache[key] = symbol
    return symbol


def _worst(status):
    """Aciklik olculerinin en zayif durumu (parametrede tek deger gorunur)."""
    values = set(status.values())
    for s in ("varsayildi", "duzeltildi"):
        if s in values:
            return s
    return "olculdu"


def _point_on(w, offset_ft, z):
    (x1, y1), (x2, y2) = w["start_ft"], w["end_ft"]
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    return XYZ(x1 + ux * offset_ft, y1 + uy * offset_ft, z), (ux, uy)


def _create_opening(ctx, o, host, level):
    w = ctx.wall_json[o["host_id"]]
    base = level.Elevation
    symbol = None
    base_symbol = {"door": ctx.choices.door_symbol,
                   "window": ctx.choices.window_symbol}.get(o["kind"])
    if base_symbol is not None:
        w_cm = int(round(o["width_m"] * 100))
        h_cm = int(round(o["height_m"] * 100))
        symbol = _scan_type(ctx, o["kind"], base_symbol, o["width_ft"], o["height_ft"],
                            w_cm, h_cm)
        if symbol is None:
            ctx.report.warnings.append(
                "{}: '{}' ailesinde genislik/yukseklik parametresi yok; Opening kullanildi".format(
                    o["id"], elem_name(base_symbol)))
    if symbol is not None:
        pt, _ = _point_on(w, o["offset_ft"], base)
        inst = ctx.doc.Create.NewFamilyInstance(pt, symbol, host, level,
                                                StructuralType.NonStructural)
        if o["kind"] == "window":
            sill = inst.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)
            if sill is not None and not sill.IsReadOnly:
                sill.Set(float(o["sill_ft"]))
        params.set_values(inst, ctx.param_names, _worst(o["status"]), None, None)
        return inst
    half = o["width_ft"] / 2.0
    p1, _ = _point_on(w, o["offset_ft"] - half, base + o["sill_ft"])
    p2, _ = _point_on(w, o["offset_ft"] + half, base + o["sill_ft"] + o["height_ft"])
    return ctx.doc.Create.NewOpening(host, p1, p2)


def _stage_openings(ctx):
    ops = ctx.data.get("openings", [])
    plan = ctx.plan([o["id"] for o in ops])
    for o in ops:
        sid = o["id"]
        if sid in plan["keep"]:
            ctx.report.add("kept", o["kind"], sid)
            continue
        if sid in plan["deleted"]:
            ctx.report.add("deleted", o["kind"], sid, "kullanici silmis")
            continue
        host = ctx.walls.get(o["host_id"])
        level = ctx.levels.get(o["floor"])
        if host is None or level is None:
            ctx.report.add("failed", o["kind"], sid, "host duvar ya da Level yok")
            continue
        try:
            el = _create_opening(ctx, o, host, level)
        except Exception as ex:  # noqa: BLE001
            ctx.report.add("failed", o["kind"], sid, str(ex))
            continue
        ctx.remember(sid, el)
        ctx.report.add("created", o["kind"], sid)


def _stage_rooms(ctx):
    rooms = ctx.data.get("rooms", [])
    plan = ctx.plan([r["id"] for r in rooms])
    for r in rooms:
        sid = r["id"]
        if sid in plan["keep"]:
            ctx.report.add("kept", "room", sid)
            continue
        if sid in plan["deleted"]:
            ctx.report.add("deleted", "room", sid, "kullanici silmis")
            continue
        level = ctx.levels.get(r["floor"])
        if level is None:
            ctx.report.add("failed", "room", sid, "katin Level'i yok")
            continue
        try:
            x, y = r["label_point_ft"]
            room = ctx.doc.Create.NewRoom(level, UV(x, y))
            ctx.doc.Regenerate()
            if room.Area <= 0:
                ctx.doc.Delete(room.Id)
                ctx.report.add("failed", "room", sid, "kapali duvar siniri yok ({})".format(r["name"]))
                continue
            name = room.get_Parameter(BuiltInParameter.ROOM_NAME)
            if name is not None:
                name.Set(r["name"])
        except Exception as ex:  # noqa: BLE001
            ctx.report.add("failed", "room", sid, str(ex))
            continue
        ctx.remember(sid, room)
        ctx.report.add("created", "room", sid)


def _stage_ledger(ctx):
    # Bu calistirmada olusturulup commit sirasinda Revit'in sildigi
    # elemanlar defterde kalmasin (yoksa sonraki calistirmada "kullanici
    # silmis" sayilip bir daha hic olusturulmazlar).
    for sid in ctx.created_sids:
        if not _alive(ctx.doc, ctx.items.get(sid)):
            ctx.items.pop(sid, None)
            for entry in ctx.report.created:
                if entry["id"] == sid:
                    ctx.report.created.remove(entry)
                    ctx.report.add("failed", entry["kind"], sid, "Revit commit sirasinda sildi")
                    break
    key = (ctx.data.get("source") or {}).get("key")
    if key and key not in ctx.ledger["sources"]:
        ctx.ledger["sources"].append(key)
    storage.set_ledger(ctx.doc, ctx.ledger)


def create_all(doc, app, data, choices):
    """Butun asamalari calistirir; `Report` dondurur. Beklenmeyen bir asama
    hatasinda grubu geri alir ve istisnayi yukari iletir."""
    t0 = time.time()
    ctx = _Ctx(doc, app, data, choices)
    stages = (
        ("parametreler", lambda: setattr(ctx, "param_names", params.ensure_parameters(doc, app))),
        ("Level", lambda: _stage_levels(ctx)),
        ("duvarlar", lambda: _stage_walls(ctx)),
        ("birlesimler", None),             # kendi islemlerini yonetir (_join_walls)
        ("acikliklar", lambda: _stage_openings(ctx)),
        ("odalar", lambda: _stage_rooms(ctx)),
        ("defter", lambda: _stage_ledger(ctx)),
    )
    group = TransactionGroup(doc, "pyKalfa: Rolove Aktar")
    group.Start()
    try:
        for name, fn in stages:
            if fn is None:
                _join_walls(ctx)
                logger.info("Rolove asamasi tamam: {}".format(name))
                continue
            t = _transaction(doc, "pyKalfa Rolove: {}".format(name))
            t.Start()
            try:
                fn()
                status = t.Commit()
                if status != TransactionStatus.Committed:
                    raise RuntimeError("'{}' asamasi Revit tarafindan geri alindi ({})".format(
                        name, status))
            except Exception:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise
            logger.info("Rolove asamasi tamam: {}".format(name))
    except Exception:
        group.RollBack()
        raise
    group.Assimilate()
    ctx.report.seconds = time.time() - t0
    return ctx.report


def preview_plan(doc, data):
    """Onizleme icin (Revit'e yazmadan): olusturulacak / korunacak /
    silinmis sayilari ve defterde baska kaynak olup olmadigi."""
    led = storage.get_ledger(doc)
    items = led["items"]
    existing = set(uid for uid in items.values() if _alive(doc, uid))
    ids = [x["id"] for k in ("levels", "walls", "openings", "rooms") for x in data.get(k, [])]
    plan = ledger_mod.plan_actions(ids, items, existing)
    key = (data.get("source") or {}).get("key")
    other = [s for s in led["sources"] if s != key]
    return {"create": len(plan["create"]), "keep": len(plan["keep"]),
            "deleted": len(plan["deleted"]), "other_sources": other}
