"""Parsel-Bina GIS: SPW / ICAR servisleri (yalniz Valonya).

Mantik planpack'in `backend/app/gis/client.py`, `batiments.py` ve
`analysis.parcel_numero` kodundan uyarlanmistir. Butun koordinatlar
EPSG:31370 (Lambert 72, metre). Gelen veri guvenilmeyen veri sayilir:
halka koordinatlari sayi ve Lambert 72 sinirlari icinde degilse atilir.
"""

from __future__ import annotations

import math
import re

from gis_http import QUERY_TIMEOUT, UpstreamError, get_json

SPW = "https://geoservices.wallonie.be/arcgis/rest/services/"
GEOCODE_WS = "https://geoservices.wallonie.be/geocodeWS"
CADMAP_LAYER = SPW + "PLAN_REGLEMENT/CADMAP_PARCELLES/MapServer/0"
PICC_LAYER = SPW + "TOPOGRAPHIE/PICC_VDIFF/MapServer/11"
CAPAKEY_RE = re.compile(r"^\d{5}[A-Z_]\d{4}/\d{2}[A-Z0-9_]\d{3}$")
ADDRESS_SEARCH_M = 20
PARCEL_FIELDS = "CAPAKEY,CAPATY,COMMUNE,NOM_COMMUNE,CODE_DIV,DIV_NOM,SECT,RADICAL,BIS,EXPOSANT,PUISSANCE,VER"
BUILDING_FIELDS = "OBJECTID,NATUR_DESC"
MAX_PAGES = 10
_BOUNDS = (0.0, 0.0, 400000.0, 300000.0)


# --- CaPaKey / parsel numarasi -------------------------------------------------

def is_capakey(text):
    return bool(CAPAKEY_RE.match((text or "").strip().upper()))


def normalise_capakey(text):
    ck = (text or "").strip().upper()
    if not CAPAKEY_RE.match(ck):
        raise ValueError("CaPaKey bicimi taninmadi: {!r} (ör. 92053D0515/00B002)".format(text))
    return ck


def parcel_numero(attrs):
    """'0515','00','B','002' -> '515B2' ; '0038','00','F','000' -> '38F'."""
    def num(v):
        try:
            return int(str(v or "0"))
        except ValueError:
            return 0
    rad, bis, pui = num(attrs.get("RADICAL")), num(attrs.get("BIS")), num(attrs.get("PUISSANCE"))
    exp = str(attrs.get("EXPOSANT") or "").strip("_ ")
    return "{}{}{}{}".format(rad, "/" + str(bis) if bis else "", exp, pui or "")


# --- Adres onerisi (ICAR geocodeWS) -------------------------------------------

def _clean(address):
    # searchAll: kesme isaretleri arka ucu bozuyor (SQL hatasi) -> kaldir
    return re.sub(r"['’`]", " ", address).strip()


def _candidate_label(c):
    street = (c.get("street") or {}).get("name")
    house = (c.get("house") or {}).get("name")
    zone = (c.get("zone") or {}).get("ident")
    city = (c.get("city") or {}).get("name")
    left = " ".join(str(v) for v in (street, house) if v)
    right = " ".join(str(v) for v in (zone, city) if v)
    return ", ".join(v for v in (left, right) if v)


def _tidy_name(name):
    """'Rue du Parc 4 4577 Modave' -> 'Rue du Parc 4, 4577 Modave'."""
    m = re.match(r"^(.*\S)\s+(\d{4})\s+(\D.*)$", name or "")
    return "{}, {} {}".format(m.group(1), m.group(2), m.group(3)) if m else (name or "")


def _xy_ok(x, y):
    return (isinstance(x, (int, float)) and isinstance(y, (int, float))
            and _BOUNDS[0] <= x <= _BOUNDS[2] and _BOUNDS[1] <= y <= _BOUNDS[3])


def suggest(q, limit=5):
    """Adres adaylari: [{"label", "x", "y", "precision"}], en fazla `limit`."""
    results, errors = [], 0
    for url, params in ((GEOCODE_WS + "/geocode", {"address": q, "geom": "true"}),
                        (GEOCODE_WS + "/searchAll", {"address": _clean(q), "bbox": "true"})):
        try:
            results.append(get_json(url, params, retries=0))
        except UpstreamError:
            errors += 1
            results.append({})
    if errors == 2:
        raise UpstreamError("ICAR geocodeWS yanit vermedi")

    cands = []
    for c in results[0].get("candidates") or []:
        house_geom = (c.get("house") or {}).get("geometry")
        street_geom = (c.get("street") or {}).get("geometry")
        g = house_geom or street_geom
        if g and g.get("coordinates"):
            x, y = g["coordinates"][:2]
            cands.append((_candidate_label(c), x, y, "house" if house_geom else "street-bbox-centre"))
    for c in results[1].get("candidates") or []:
        g = c.get("geotag") or {}
        b = g.get("bbox")
        if b and g.get("level") in (4, 3):
            cands.append((_tidy_name(g.get("name")), (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0,
                          "address-point" if g["level"] == 4 else "street-bbox-centre"))

    seen, out = set(), []
    for label, x, y, precision in cands:
        key = re.sub(r"\W+", " ", (label or "").lower()).strip()
        if not key or key in seen or not _xy_ok(x, y):
            continue
        seen.add(key)
        out.append({"label": label, "x": round(float(x), 3), "y": round(float(y), 3), "precision": precision})
    return out[:limit]


# --- Parsel / bina sorgulari ---------------------------------------------------

def _clean_rings(geom):
    rings = []
    for r in (geom or {}).get("rings") or []:
        try:
            pts = [[float(p[0]), float(p[1])] for p in r]
        except (TypeError, ValueError, IndexError):
            continue
        if len(pts) >= 4 and all(_xy_ok(x, y) for x, y in pts):
            rings.append(pts)
    return rings


def _parcel_items(res):
    out = []
    for f in res.get("features") or []:
        if not isinstance(f, dict):
            continue
        rings = _clean_rings(f.get("geometry"))
        a = f.get("attributes") or {}
        if rings and a.get("CAPAKEY"):
            out.append({"capakey": a["CAPAKEY"], "attributes": a, "rings": rings})
    return out


def _in_ring(x, y, r):
    inside = False
    for i in range(len(r) - 1):
        (x1, y1), (x2, y2) = r[i], r[i + 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def point_rings_distance(x, y, rings):
    if sum(_in_ring(x, y, r) for r in rings) % 2:
        return 0.0
    best = math.inf
    for r in rings:
        for i in range(len(r) - 1):
            (x1, y1), (x2, y2) = r[i], r[i + 1]
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)))
            best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return best


def parcel_by_capakey(ck):
    ck = normalise_capakey(ck)
    res = get_json(CADMAP_LAYER + "/query", {
        "where": "CAPAKEY='{}'".format(ck), "outFields": PARCEL_FIELDS,
        "returnGeometry": "true", "outSR": 31370}, timeout=QUERY_TIMEOUT)
    items = _parcel_items(res)
    return items[0] if items else None


def parcel_by_point(x, y, search_m=0):
    """Noktayi iceren parsel; `search_m > 0` ise o mesafedeki en yakin parsel."""
    params = {"geometry": "{},{}".format(x, y), "geometryType": "esriGeometryPoint", "inSR": 31370,
              "spatialRel": "esriSpatialRelIntersects", "outFields": PARCEL_FIELDS,
              "returnGeometry": "true", "outSR": 31370}
    if search_m:
        params.update({"distance": search_m, "units": "esriSRUnit_Meter"})
    items = _parcel_items(get_json(CADMAP_LAYER + "/query", params, timeout=QUERY_TIMEOUT))
    items.sort(key=lambda p: point_rings_distance(x, y, p["rings"]))
    return items[0] if items else None


def _query_box(layer, box, fields):
    """Envelope ile kesisen tum feature'lar, `exceededTransferLimit` bitene dek sayfalanir."""
    base = {"geometry": ",".join("{:.2f}".format(v) for v in box), "geometryType": "esriGeometryEnvelope",
            "inSR": 31370, "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
            "returnGeometry": "true", "outSR": 31370, "geometryPrecision": 2}
    pages, offset = [], 0
    for _ in range(MAX_PAGES):
        params = dict(base)
        if offset:
            params["resultOffset"] = offset
        res = get_json(layer + "/query", params, timeout=QUERY_TIMEOUT)
        feats = res.get("features") or []
        pages.append(res)
        offset += len(feats)
        if not res.get("exceededTransferLimit") or not feats:
            break
    return pages


def parcels_in_box(box):
    out = []
    for res in _query_box(CADMAP_LAYER, box, PARCEL_FIELDS):
        out.extend(_parcel_items(res))
    return out


def buildings_in_box(box):
    out = []
    for res in _query_box(PICC_LAYER, box, BUILDING_FIELDS):
        for f in res.get("features") or []:
            if not isinstance(f, dict):
                continue
            rings = _clean_rings(f.get("geometry"))
            if not rings:
                continue
            a = f.get("attributes") or {}
            nature = " ".join(str(a.get("NATUR_DESC") or "").split())[:60] or None
            out.append({"id": a.get("OBJECTID"), "nature": nature, "rings": rings})
    return out

