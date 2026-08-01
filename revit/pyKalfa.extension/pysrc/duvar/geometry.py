"""
pyKalfa / Duvar - geometri temizligi

`dxf_reader.py`'den gelen ham segmentleri Revit'e verilebilecek hale
getirir. Sira onemlidir:

  1. **Birim donusumu** (cizim birimi -> feet, Revit'in ic birimi).
     Butun toleranslar bundan sonra feet cinsinden tek bir dilde konusur.
  2. **Yuvarlama/kaynak (snap):** tarama kaynakli DXF'lerde ayni kose
     0.4 mm farkla iki ayri nokta olabiliyor; birlestirme adiminin
     calisabilmesi icin uc noktalar bir izgaraya oturtulur.
  3. **Dejenere ve tekrar eden segmentlerin atilmasi.**
  4. **Kolinear birlestirme:** ayni dogru uzerindeki, ucuca eklenen veya
     ust uste binen parcalar tek bir uzun parcaya indirgenir. Polycam
     ciktisinda tek bir duvar cogu zaman onlarca kisa parcaya bolunmus
     halde gelir; birlestirmeden duvar olusturmak Revit'te yuzlerce
     kucuk duvar demek olur.
  5. **Kisa parca filtresi:** birlestirmeden SONRA uygulanir -- once
     filtrelenirse, tek bir duvari olusturan kisa parcalar birbirine
     eklenemeden silinir.

Birim tespiti: oncelik DXF basligindaki `$INSUNITS`. O yoksa (0 =
belirtilmemis) cizimin buyuklugunden bir tahmin uretilir; tahmin
"kesin degil" olarak isaretlenir ki arayuz kullaniciya sorabilsin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dxf_reader import Poly, Segment, UNIT_NAME_TO_METERS, meters_per_unit

FEET_PER_METER = 1.0 / 0.3048

# --- Varsayilan toleranslar (metre cinsinden; feet'e cevrilerek kullanilir) ---
DEFAULT_SNAP_M = 0.005        # 5 mm: ayni kose sayilacak uc nokta farki
DEFAULT_MIN_LENGTH_M = 0.20   # 20 cm'den kisa duvar parcasi gurultu sayilir
DEFAULT_MERGE_GAP_M = 0.05    # ayni dogru uzerinde 5 cm'e kadar bosluk koprulenir
DEFAULT_OFFSET_TOL_M = 0.02   # dogruya dik 2 cm'e kadar sapma "ayni dogru" sayilir
DEFAULT_ANGLE_TOL_DEG = 1.5   # yon farki bu acinin altindaysa "ayni yon"

# Cizim birimi belirtilmemisse, modelin kosegen boyuna bakip tahmin
# yurutulur: bir kat plani gercekte 3-100 m arasidir; kosegen bu araligin
# neresine dusuyorsa birim odur.
UNIT_GUESS_THRESHOLDS = (
    (3000.0, "mm"),   # kosegen > 3000 birim ise mm (yani > 3 m)
    (300.0, "cm"),
    (0.0, "m"),
)


@dataclass
class UnitInfo:
    name: str
    meters_per_unit: float
    source: str
    confident: bool


def resolve_units(insunits: int, segments, override: str = "auto") -> UnitInfo:
    """Cizim birimini belirler.

    `override` "auto" disinda bir sey ise (mm/cm/m/in/ft) o kullanilir --
    kullanici arayuzden birimi elle secebilsin diye."""
    override = (override or "auto").strip().lower()
    if override != "auto":
        if override not in UNIT_NAME_TO_METERS:
            raise ValueError("Bilinmeyen birim: {}".format(override))
        return UnitInfo(override, UNIT_NAME_TO_METERS[override], "kullanici", True)

    mpu = meters_per_unit(insunits)
    if mpu:
        name = next(
            (n for n, v in UNIT_NAME_TO_METERS.items() if abs(v - mpu) < 1e-12),
            "{}m/birim".format(mpu),
        )
        return UnitInfo(name, mpu, "$INSUNITS", True)

    diagonal = _bbox_diagonal(segments)
    guess = "m"
    for threshold, name in UNIT_GUESS_THRESHOLDS:
        if diagonal > threshold:
            guess = name
            break
    return UnitInfo(guess, UNIT_NAME_TO_METERS[guess], "tahmin (cizim boyutu)", False)


def _bbox_diagonal(segments) -> float:
    if not segments:
        return 0.0
    xs = [s.x1 for s in segments] + [s.x2 for s in segments]
    ys = [s.y1 for s in segments] + [s.y2 for s in segments]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def to_feet(segments, unit: UnitInfo):
    """Segmentleri cizim biriminden feet'e cevirir (yeni liste dondurur)."""
    factor = unit.meters_per_unit * FEET_PER_METER
    return [
        Segment(s.x1 * factor, s.y1 * factor, s.x2 * factor, s.y2 * factor, s.layer)
        for s in segments
    ]


def to_feet_polys(polys, unit: UnitInfo):
    """`Poly` nesnelerini cizim biriminden feet'e cevirir.

    Duvar tespiti (dis hat -> merkez eksen) polyline butunlugune ihtiyac
    duydugu icin donusum segment seviyesine inmeden burada yapilir."""
    factor = unit.meters_per_unit * FEET_PER_METER
    return [
        Poly(
            [(x * factor, y * factor) for x, y in poly.points],
            poly.layer, poly.closed, poly.dxftype,
        )
        for poly in polys
    ]


def bbox_polys(polys):
    """(minx, miny, maxx, maxy); nesne yoksa None."""
    xs = [x for poly in polys for x, _ in poly.points]
    ys = [y for poly in polys for _, y in poly.points]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def bbox(segments):
    """(minx, miny, maxx, maxy); segment yoksa None."""
    if not segments:
        return None
    xs = [s.x1 for s in segments] + [s.x2 for s in segments]
    ys = [s.y1 for s in segments] + [s.y2 for s in segments]
    return (min(xs), min(ys), max(xs), max(ys))


def translate(segments, dx: float, dy: float):
    return [Segment(s.x1 + dx, s.y1 + dy, s.x2 + dx, s.y2 + dy, s.layer) for s in segments]


def snap_and_dedupe(segments, snap_tol: float):
    """Uc noktalari `snap_tol` izgarasina oturtur, dejenere ve tekrar
    eden segmentleri atar. (temiz_segmentler, atilan_dejenere) dondurur."""
    if snap_tol <= 0:
        snap_tol = 1e-9
    seen = set()
    cleaned = []
    degenerate = 0
    for s in segments:
        x1 = round(s.x1 / snap_tol) * snap_tol
        y1 = round(s.y1 / snap_tol) * snap_tol
        x2 = round(s.x2 / snap_tol) * snap_tol
        y2 = round(s.y2 / snap_tol) * snap_tol
        if math.hypot(x2 - x1, y2 - y1) < snap_tol:
            degenerate += 1
            continue
        # Yonden bagimsiz anahtar: A->B ile B->A ayni cizgidir.
        key = (round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6), s.layer)
        rkey = (round(x2, 6), round(y2, 6), round(x1, 6), round(y1, 6), s.layer)
        if key in seen or rkey in seen:
            continue
        seen.add(key)
        cleaned.append(Segment(x1, y1, x2, y2, s.layer))
    return cleaned, degenerate


def _direction_key(dx: float, dy: float, angle_tol_deg: float):
    """Segmentin yonunu, yon-duyarsiz (A->B == B->A) bir kovaya atar.

    Aci 0-180 araligina indirgenir, sonra tolerans kadar kovalanir; son
    kova basa sarilir (179.9 derece ile 0.1 derece ayni yondur).

    Bilinen sinir: tam kova sinirina denk dusen iki segment (ör. tolerans
    1.5 derece iken 0.74 ve 0.76 derece) ayri kovalara duser ve
    birlestirilmez. Sonuc, olmasi gerekenden bir fazla duvar parcasidir;
    yanlis geometri degil. Kullanici son duzeltmeleri Revit'te yaptigi
    icin bu, cozumu karmasiklastirmaya degmeyen kabul edilmis bir
    sapmadir."""
    angle = math.degrees(math.atan2(dy, dx)) % 180.0
    bucket_count = max(1, int(round(180.0 / angle_tol_deg)))
    return int(round(angle / angle_tol_deg)) % bucket_count


def merge_collinear(
    segments,
    angle_tol_deg: float = DEFAULT_ANGLE_TOL_DEG,
    offset_tol: float = 0.0,
    gap_tol: float = 0.0,
):
    """Ayni dogru uzerindeki segmentleri birlestirir.

    Yontem: segmentler once (katman, yon) kovalarina ayrilir; her kovada
    ayni dogruya (normal yonundeki uzakligi `offset_tol` icinde) ait
    olanlar gruplanir; her grupta segmentler dogru boyunca 1B araliklara
    (interval) donusturulup ust uste binen/`gap_tol` kadar yakin olanlar
    birlestirilir.

    Bu, "her segmenti her segmentle karsilastir" (O(n^2)) yaklasimindan
    hem hizli hem de zincirleme birlesmelerde (A-B, B-C, C-D) dogrudur:
    araliklar sirali islenir, zincir kendiliginden tek parcaya iner."""
    if not segments:
        return []

    buckets: dict[tuple, list[Segment]] = {}
    for s in segments:
        dx, dy = s.x2 - s.x1, s.y2 - s.y1
        key = (s.layer, _direction_key(dx, dy, angle_tol_deg))
        buckets.setdefault(key, []).append(s)

    merged: list[Segment] = []
    for (layer, _), bucket in buckets.items():
        merged.extend(_merge_bucket(bucket, layer, offset_tol, gap_tol))
    return merged


def _merge_bucket(bucket, layer: str, offset_tol: float, gap_tol: float):
    """Ayni katman ve (yaklasik) ayni yondeki segmentleri birlestirir."""
    # Kovanin ortak yonu: en uzun segmentin yonu (kisa parcalarin acisi
    # yuvarlama hatasina daha duyarli oldugu icin en uzun olan referans
    # alinir).
    longest = max(bucket, key=lambda s: math.hypot(s.x2 - s.x1, s.y2 - s.y1))
    dx, dy = longest.x2 - longest.x1, longest.y2 - longest.y1
    norm = math.hypot(dx, dy)
    if norm < 1e-12:
        return list(bucket)
    ux, uy = dx / norm, dy / norm
    nx, ny = -uy, ux  # dogruya dik birim vektor

    # Her segmenti (dogru uzerindeki uzaklik, dogru boyunca aralik) yap.
    entries = []
    for s in bucket:
        offset = s.x1 * nx + s.y1 * ny
        t1 = s.x1 * ux + s.y1 * uy
        t2 = s.x2 * ux + s.y2 * uy
        entries.append((offset, min(t1, t2), max(t1, t2)))

    # Ayni dogruya ait olanlari grupla (offset'e gore sirala, tolerans
    # icinde kalanlari ayni gruba koy).
    #
    # Karsilastirma grubun ILK uyesine (capa) gore yapilir, sonuncusuna
    # gore degil: sonuncuya gore bakmak zincirlemeye yol acar (0, 0.019,
    # 0.038, 0.057... hepsi 2 cm tolerans icinde "ayni dogru" sayilip tek
    # gruba duser) ve birbirinden 10 cm uzaktaki paralel duvarlar tek bir
    # ortalama dogruya cokerdi -- yani duvarlar yanlis yere kayardi.
    entries.sort(key=lambda e: e[0])
    groups: list[list[tuple]] = []
    for entry in entries:
        if groups and abs(entry[0] - groups[-1][0][0]) <= offset_tol:
            groups[-1].append(entry)
        else:
            groups.append([entry])

    result = []
    for group in groups:
        # Grubun temsili offset'i: uyelerin ortalamasi (tek bir kenara
        # yapismak yerine ortada kalsin).
        offset = sum(e[0] for e in group) / len(group)
        intervals = sorted((e[1], e[2]) for e in group)
        current_start, current_end = intervals[0]
        spans = []
        for start, end in intervals[1:]:
            if start <= current_end + gap_tol:
                current_end = max(current_end, end)
            else:
                spans.append((current_start, current_end))
                current_start, current_end = start, end
        spans.append((current_start, current_end))

        for start, end in spans:
            x1 = ux * start + nx * offset
            y1 = uy * start + ny * offset
            x2 = ux * end + nx * offset
            y2 = uy * end + ny * offset
            result.append(Segment(x1, y1, x2, y2, layer))
    return result


def filter_short(segments, min_length: float):
    """(uzun_olanlar, atilan_adet) dondurur."""
    kept = [s for s in segments if s.length() >= min_length]
    return kept, len(segments) - len(kept)


def clean_segments(
    segments,
    min_length_m: float = DEFAULT_MIN_LENGTH_M,
    snap_m: float = DEFAULT_SNAP_M,
    merge_gap_m: float = DEFAULT_MERGE_GAP_M,
    offset_tol_m: float = DEFAULT_OFFSET_TOL_M,
    angle_tol_deg: float = DEFAULT_ANGLE_TOL_DEG,
):
    """FEET cinsinden segmentleri temizler (tek cizgi modu icin).

    Birim donusumu daha once, polyline seviyesinde yapilmis olmalidir
    (bkz. `to_feet_polys`) -- duvar tespiti polyline butunlugune ihtiyac
    duydugu icin segmentlere inmek en sona birakilir.

    (temiz_segmentler, istatistik_sozlugu) dondurur."""
    stats = {"raw": len(segments)}

    snapped, degenerate = snap_and_dedupe(segments, snap_m * FEET_PER_METER)
    stats["degenerate_dropped"] = degenerate
    stats["after_dedupe"] = len(snapped)

    merged = merge_collinear(
        snapped,
        angle_tol_deg=angle_tol_deg,
        offset_tol=offset_tol_m * FEET_PER_METER,
        gap_tol=merge_gap_m * FEET_PER_METER,
    )
    stats["after_merge"] = len(merged)

    kept, short_dropped = filter_short(merged, min_length_m * FEET_PER_METER)
    stats["short_dropped"] = short_dropped
    stats["final"] = len(kept)
    return kept, stats


def total_length(segments) -> float:
    return sum(s.length() for s in segments)
