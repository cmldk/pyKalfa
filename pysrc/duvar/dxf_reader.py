"""
pyKalfa / Duvar - DXF okuma (ezdxf)

Sorumlulugu SADECE okumaktir: bir DXF dosyasindaki cizgi/polyline
geometrisini ortak bir koordinat sisteminde, cizim birimi cinsinden
dondurur. Duvar karari `wall_detector.py`'nin, temizlik `geometry.py`'nin
isidir.

**Onemli tasarim karari -- polyline butunlugu korunur.** Ilk surumde her
polyline hemen tek tek segmentlere parcalaniyordu; bu, en kritik bilgiyi
yok ediyordu: gercek kat plani ciktilarinda (Polycam dahil) bir duvar
"iki ayri cizgi" degil, **tek bir kapali dis hat (outline) polyline'i**
olarak cizilir. Parcalanmis segmentlere bakinca duvarin iki yuzu iki ayri
duvar gibi gorunur ve her fiziksel duvar icin iki ince duvar uretilir.
Bu yuzden okuyucu artik `Poly` nesneleri dondurur; segmentlere inmek
isteyen (ör. geri donus modu) `Poly.segments()` cagirir.

Ele alinan entity turleri: LINE, LWPOLYLINE, POLYLINE (2B) ve bunlarin
blok referanslari (INSERT) icinde olanlari.

"Ortak koordinat sistemi" derken uc ayri sey duzeltilir:

  1. **Blok referanslari (INSERT):** blok icindeki geometri blogun kendi
     yerel koordinatlarindadir; olcek/donme/konum uygulanmadan okunursa
     duvarlar yanlis yere cikar. `virtual_entities()` blogu yerinde
     "patlatip" entity'leri model koordinatlarinda verir; ic ice bloklar
     icin ozyinelemeli (recursive) inilir.
  2. **OCS -> WCS:** LWPOLYLINE/POLYLINE kendi nesne koordinat sisteminde
     (extrusion vektorune bagli) saklanir. Aynaya alinmis/ters extrusion'li
     (0,0,-1) cizimlerde bu goz ardi edilirse plan ayna goruntusu olur.
  3. **Z duzlestirme:** kat plani 2B'dir; Z bilgisi atilir.

Cizim birimi ($INSUNITS) burada TESPIT edilir ama donusum yapilmaz --
donusum `geometry.py`'de tek yerde yapilir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.math import OCS

SUPPORTED_TYPES = ("LINE", "LWPOLYLINE", "POLYLINE")

# Ic ice blok referanslarinda sonsuz donguye karsi guvenlik siniri.
MAX_INSERT_DEPTH = 8

# DXF $INSUNITS kodu -> 1 cizim biriminin metre karsiligi.
INSUNITS_TO_METERS = {
    1: 0.0254,    # inch
    2: 0.3048,    # feet
    4: 0.001,     # millimeter
    5: 0.01,      # centimeter
    6: 1.0,       # meter
    10: 0.9144,   # yard
    14: 0.1,      # decimeter
}

INSUNITS_NAMES = {
    0: "belirtilmemis",
    1: "inch",
    2: "feet",
    4: "mm",
    5: "cm",
    6: "m",
    10: "yard",
    14: "dm",
}

# Kullanicinin/CLI'nin elle verebilecegi birim adlari.
UNIT_NAME_TO_METERS = {
    "mm": 0.001,
    "cm": 0.01,
    "dm": 0.1,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
}


@dataclass
class Segment:
    """Tek bir duz cizgi parcasi (geri donus modu ve temizlik icin)."""

    x1: float
    y1: float
    x2: float
    y2: float
    layer: str = "0"

    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class Poly:
    """Bir cizim nesnesi: nokta dizisi + katman.

    LINE'lar da iki noktali `Poly` olarak temsil edilir; boylece boru
    hattinin geri kalani tek bir veri turuyle calisir.
    """

    points: list          # [(x, y), ...]
    layer: str = "0"
    closed: bool = False
    dxftype: str = "LWPOLYLINE"

    def ring(self) -> list:
        """Kapali bir halka olarak noktalar (son nokta ilkiyle ayniysa atilir).

        Cogu CAD ciktisi kapali sekli "closed" bayragiyla degil, son
        noktayi ilkiyle ayni yaparak ifade eder; ikisini de ayni sekilde
        ele almak icin bu normalize etme gerekir."""
        pts = list(self.points)
        if len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1e-9:
            pts = pts[:-1]
        return pts

    def is_ring(self) -> bool:
        """Kapali bir alan mi (dis hat olabilir mi)?"""
        if len(self.points) < 4:
            return False
        return self.closed or math.dist(self.points[0], self.points[-1]) < 1e-9

    def segments(self) -> list:
        """Nokta dizisini ardisik segmentlere cevirir."""
        pts = list(self.points)
        if self.closed and len(pts) > 2 and math.dist(pts[0], pts[-1]) > 1e-9:
            pts = pts + [pts[0]]
        return [
            Segment(a[0], a[1], b[0], b[1], self.layer)
            for a, b in zip(pts, pts[1:])
        ]


@dataclass
class ReadResult:
    polys: list = field(default_factory=list)
    entity_counts: dict = field(default_factory=dict)
    ignored_counts: dict = field(default_factory=dict)
    insunits: int = 0
    dxf_version: str = ""
    warnings: list = field(default_factory=list)

    def segments(self) -> list:
        """Butun nesnelerin segmentleri (birim tahmini/geri donus modu icin)."""
        out = []
        for poly in self.polys:
            out.extend(poly.segments())
        return out


def _ocs_to_wcs_xy(points, extrusion):
    """OCS'teki (x, y) noktalarini WCS'ye cevirip XY'ye duzlestirir.

    Extrusion (0, 0, 1) ise (olagan durum) donusum birim matristir ve
    noktalar oldugu gibi kullanilir -- gereksiz hesap yapmamak icin bu
    durum kisa devre edilir."""
    if extrusion is None:
        return [(float(p[0]), float(p[1])) for p in points]
    ex, ey, ez = float(extrusion[0]), float(extrusion[1]), float(extrusion[2])
    if abs(ex) < 1e-9 and abs(ey) < 1e-9 and ez > 0:
        return [(float(p[0]), float(p[1])) for p in points]
    ocs = OCS((ex, ey, ez))
    result = []
    for p in points:
        wcs = ocs.to_wcs((float(p[0]), float(p[1]), 0.0))
        result.append((float(wcs.x), float(wcs.y)))
    return result


def _polyline_points(entity):
    """LWPOLYLINE/POLYLINE'in (x, y) noktalarini OCS'te dondurur.

    Not: `bulge` (yay) bilgisi goz ardi edilir, yani yaylar kirisleriyle
    (chord) temsil edilir. Kat plani duvarlari neredeyse her zaman duz
    oldugu icin bu MVP'de kabul edilmis bir sapmadir; egri duvar iceren
    bir cizimde duvarlar koseli cikar."""
    dxftype = entity.dxftype()
    if dxftype == "LWPOLYLINE":
        try:
            return [(p[0], p[1]) for p in entity.get_points("xy")]
        except (TypeError, AttributeError):
            return [(p[0], p[1]) for p in entity.get_points()]
    # POLYLINE: sadece 2B olanlar duvar olabilir; mesh/polyface (3B)
    # yuzeyler kat planinda duvar cizgisi degildir.
    if not entity.is_2d_polyline:
        return []
    return [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]


def _is_closed(entity) -> bool:
    try:
        return bool(entity.closed)
    except AttributeError:
        return bool(entity.dxf.get("flags", 0) & 1)


def _entity_to_poly(entity, layer_override=None):
    """Tek bir entity'yi `Poly`'ye cevirir (bilinmeyen tur -> None)."""
    dxftype = entity.dxftype()
    layer = layer_override or getattr(entity.dxf, "layer", "0")

    if dxftype == "LINE":
        start, end = entity.dxf.start, entity.dxf.end
        # LINE zaten WCS'te saklanir, OCS donusumu gerekmez.
        return Poly(
            [(float(start.x), float(start.y)), (float(end.x), float(end.y))],
            layer, False, "LINE",
        )

    if dxftype in ("LWPOLYLINE", "POLYLINE"):
        points = _polyline_points(entity)
        if len(points) < 2:
            return None
        extrusion = None
        try:
            extrusion = entity.dxf.extrusion
        except AttributeError:
            pass
        points = _ocs_to_wcs_xy(points, extrusion)
        return Poly(points, layer, _is_closed(entity), dxftype)

    return None


def _walk(entities, result: ReadResult, depth: int = 0, layer_override=None) -> None:
    """Entity koleksiyonunu gezer; INSERT'leri yerinde patlatir."""
    for entity in entities:
        dxftype = entity.dxftype()

        if dxftype == "INSERT":
            if depth >= MAX_INSERT_DEPTH:
                result.warnings.append(
                    "Ic ice blok derinligi {} asildi, bir INSERT atlandi.".format(MAX_INSERT_DEPTH)
                )
                continue
            try:
                virtual = list(entity.virtual_entities())
            except Exception as exc:  # bozuk/desteklenmeyen blok
                result.warnings.append(
                    "Blok referansi ('{}') acilamadi, atlandi: {}".format(
                        getattr(entity.dxf, "name", "?"), exc
                    )
                )
                continue
            # Blok icindeki entity'ler kendi katmanlarini tasir; "0"
            # katmanindakiler AutoCAD kuralina gore INSERT'un katmanini
            # devralir -- katman bazli filtreleme dogru calissin diye
            # bu devralma burada uygulanir. Sadece BU blogun urettigi
            # nesnelere dokunmak icin oncesindeki uzunluk isaretlenir.
            insert_layer = getattr(entity.dxf, "layer", "0")
            before = len(result.polys)
            _walk(virtual, result, depth + 1, layer_override)
            if insert_layer != "0":
                for poly in result.polys[before:]:
                    if poly.layer == "0":
                        poly.layer = insert_layer
            continue

        if dxftype in SUPPORTED_TYPES:
            poly = _entity_to_poly(entity, layer_override)
            if poly:
                result.entity_counts[dxftype] = result.entity_counts.get(dxftype, 0) + 1
                result.polys.append(poly)
            continue

        result.ignored_counts[dxftype] = result.ignored_counts.get(dxftype, 0) + 1


def read_dxf(path: Path) -> ReadResult:
    """DXF dosyasini okuyup cizim birimindeki `Poly` listesini dondurur.

    Dosya acilamazsa/bozuksa `ValueError` firlatir (cagiran taraf
    kullaniciya anlamli bir mesaj gosterebilsin diye)."""
    path = Path(path)
    if not path.is_file():
        raise ValueError("DXF dosyasi bulunamadi: {}".format(path))

    try:
        doc = ezdxf.readfile(str(path))
    except IOError as exc:
        raise ValueError("DXF dosyasi acilamadi: {}".format(exc))
    except ezdxf.DXFStructureError as exc:
        # Bozuk/kismi dosyalarda ezdxf'in kurtarma (recover) modulu cogu
        # zaman ise yarar bir sonuc cikarabiliyor; sessizce vazgecmek
        # yerine bir kez de onunla deneriz.
        try:
            from ezdxf import recover

            doc, _auditor = recover.readfile(str(path))
        except Exception:
            raise ValueError("DXF dosyasi okunamadi (bozuk olabilir): {}".format(exc))

    result = ReadResult()
    result.dxf_version = doc.dxfversion
    try:
        result.insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    except (TypeError, ValueError):
        result.insunits = 0

    _walk(doc.modelspace(), result)

    if not result.polys:
        result.warnings.append(
            "Model uzayinda (modelspace) hic LINE/POLYLINE/LWPOLYLINE bulunamadi."
        )
    return result


def meters_per_unit(insunits: int):
    """$INSUNITS kodundan metre/birim orani; bilinmiyorsa None."""
    return INSUNITS_TO_METERS.get(int(insunits or 0))


def insunits_name(insunits: int) -> str:
    return INSUNITS_NAMES.get(int(insunits or 0), "bilinmeyen ({})".format(insunits))
