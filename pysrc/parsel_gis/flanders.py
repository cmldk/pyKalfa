"""Parsel-Bina GIS: Digitaal Vlaanderen servisleri (Flaman bolgesi).

`services.py` (Valonya) ile ayni imzalar ve ayni donus bicimleri; boylece
`layout`, `preview` ve Revit tarafi bolgeden habersizdir. Koordinatlar
EPSG:31370 (Lambert 72, metre).

Kaynaklar (2026-11-18'de dogrulandi):
  - adres: geo.api.vlaanderen.be/geolocation/v4 (Location, Suggestion)
  - parsel: Adpf WFS `Adpf:Adpf` (CAPAKEY)
  - bina: GRB WFS `GRB:GBG`
  - yol/kaldirim kenari: GRB WFS `GRB:WGO` (rijbaan kenari, zayif yol
    kullanicisi bolgesi siniri, stabilize bolge siniri)
  - sokak adi: GRB WFS `GRB:Wegsegment` (LSTRNM, yoksa RSTRNM)

WFS `startIndex` sayfalamasi bu sunucuda 45 s'de 504 veriyor; bu yuzden
sayfalama yok: tek istek `WFS_COUNT` kayit, sinir dolarsa kutu dorde
bolunup yeniden sorulur (OIDN/UIDN ile tekillestirilir).
"""

from __future__ import annotations

import services
from gis_http import QUERY_TIMEOUT, UpstreamError, get_json

GEOLOC = "https://geo.api.vlaanderen.be/geolocation/v4"
ADPF_WFS = "https://geo.api.vlaanderen.be/Adpf/wfs"
GRB_WFS = "https://geo.api.vlaanderen.be/GRB/wfs"
PARCEL_LAYER = "Adpf:Adpf"
BUILDING_LAYER = "GRB:GBG"
ROAD_EDGE_LAYER = "GRB:WGO"
STREET_LAYER = "GRB:Wegsegment"
WFS_COUNT = 5000
MAX_SPLIT_DEPTH = 3
SUGGEST_LIMIT = 5
REGION = "vla"


# --- Adres onerisi -------------------------------------------------------------

def _geoloc(path, q, count):
    return get_json(GEOLOC + path, {"q": q, "c": count},
                    timeout=services.SUGGEST_TIMEOUT, retries=0)


def _candidate(loc):
    label = " ".join(str(loc.get("FormattedAddress") or "").split())
    if "huisnummer" in str(loc.get("LocationType") or ""):
        p = loc.get("Location") or {}
        x, y, precision = p.get("X_Lambert72"), p.get("Y_Lambert72"), "house"
    else:
        b = loc.get("BoundingBox") or {}
        lo, hi = b.get("LowerLeft") or {}, b.get("UpperRight") or {}
        try:
            x = (float(lo["X_Lambert72"]) + float(hi["X_Lambert72"])) / 2.0
            y = (float(lo["Y_Lambert72"]) + float(hi["Y_Lambert72"])) / 2.0
        except (KeyError, TypeError, ValueError):
            p = loc.get("Location") or {}
            x, y = p.get("X_Lambert72"), p.get("Y_Lambert72")
        precision = "street-bbox-centre"
    if not label or not services._xy_ok(x, y):
        return None
    return {"label": label, "x": round(float(x), 3), "y": round(float(y), 3),
            "precision": precision, "region": REGION}


def suggest(q, limit=SUGGEST_LIMIT):
    """Adres adaylari [{"label", "x", "y", "precision", "region"}]. Tam adres
    `Location`'dan dogrudan gelir; kismi metinde `Suggestion` metinleri tek
    tek `Location` ile koordinata cevrilir."""
    locs = list(_geoloc("/Location", q, limit).get("LocationResult") or [])
    if not locs:
        for text in (_geoloc("/Suggestion", q, limit).get("SuggestionResult") or [])[:limit]:
            if isinstance(text, str) and text.strip():
                locs.extend((_geoloc("/Location", text, 1).get("LocationResult") or [])[:1])
    seen, out = set(), []
    for loc in locs:
        c = _candidate(loc) if isinstance(loc, dict) else None
        key = c and c["label"].lower()
        if c and key not in seen:
            seen.add(key)
            out.append(c)
    return out[:limit]


# --- WFS -----------------------------------------------------------------------

def _wfs_params(type_name):
    return {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": type_name, "outputFormat": "application/json",
            "srsName": "EPSG:31370", "count": WFS_COUNT}


def _bbox(box):
    return ",".join("{:.2f}".format(v) for v in box) + ",EPSG:31370"


def _features(res):
    return [f for f in (res.get("features") or []) if isinstance(f, dict)]


def _wfs_box(url, type_name, box, depth=0):
    params = _wfs_params(type_name)
    params["bbox"] = _bbox(box)
    feats = _features(get_json(url, params, timeout=QUERY_TIMEOUT))
    if len(feats) < WFS_COUNT or depth >= MAX_SPLIT_DEPTH:
        return feats
    x0, y0, x1, y1 = box
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    out = []
    for q in ((x0, y0, mx, my), (mx, y0, x1, my), (x0, my, mx, y1), (mx, my, x1, y1)):
        out.extend(_wfs_box(url, type_name, q, depth + 1))
    return out


def _fid(f):
    p = f.get("properties") or {}
    for k in ("OIDN", "UIDN"):
        if p.get(k) is not None:
            return (k, p[k])
    return ("obj", id(f))


def _points(seq):
    try:
        pts = [[float(p[0]), float(p[1])] for p in seq]
    except (TypeError, ValueError, IndexError):
        return None
    return pts if all(services._xy_ok(x, y) for x, y in pts) else None


def _rings(geom):
    t, c = (geom or {}).get("type"), (geom or {}).get("coordinates") or []
    polys = [c] if t == "Polygon" else (c if t == "MultiPolygon" else [])
    rings = []
    for poly in polys:
        for r in poly or []:
            pts = _points(r)
            if pts and len(pts) >= 4:
                rings.append(pts)
    return rings


def _paths(geom):
    t, c = (geom or {}).get("type"), (geom or {}).get("coordinates") or []
    lines = [c] if t == "LineString" else (c if t == "MultiLineString" else [])
    paths = []
    for line in lines:
        pts = _points(line or [])
        if pts and len(pts) >= 2:
            paths.append(pts)
    return paths


def _dedupe(feats):
    return services._first_seen(feats, _fid)


# --- Parsel --------------------------------------------------------------------

def capakey_parts(ck):
    """CaPaKey -> parsel_numero alanlari (iki bolgede de ayni bicim)."""
    ck = (ck or "").strip().upper()
    if not services.CAPAKEY_RE.match(ck):
        return {}
    return {"RADICAL": ck[6:10], "BIS": ck[11:13], "EXPOSANT": ck[13], "PUISSANCE": ck[14:17]}


def _parcel_items(feats):
    out = []
    for f in _dedupe(feats):
        props = f.get("properties") or {}
        ck = str(props.get("CAPAKEY") or "").strip()
        rings = _rings(f.get("geometry"))
        if ck and rings:
            attrs = dict(props)
            attrs.update(capakey_parts(ck))
            out.append({"capakey": ck, "attributes": attrs, "rings": rings})
    return out


def parcel_by_capakey(ck):
    ck = services.normalise_capakey(ck)
    params = _wfs_params(PARCEL_LAYER)
    params["CQL_FILTER"] = "CAPAKEY='{}'".format(ck)
    items = _parcel_items(_features(get_json(ADPF_WFS, params, timeout=QUERY_TIMEOUT)))
    return items[0] if items else None


def parcel_by_point(x, y, search_m=0):
    """Noktayi iceren ya da `search_m` icindeki en yakin parsel."""
    s = max(float(search_m), 0.5)
    items = _parcel_items(_wfs_box(ADPF_WFS, PARCEL_LAYER, (x - s, y - s, x + s, y + s)))
    items = [p for p in items if services.point_rings_distance(x, y, p["rings"]) <= max(search_m, 0)]
    items.sort(key=lambda p: services.point_rings_distance(x, y, p["rings"]))
    return items[0] if items else None


def parcels_in_box(box):
    return _parcel_items(_wfs_box(ADPF_WFS, PARCEL_LAYER, box))


# --- Bina, yol kenari, sokak adi -----------------------------------------------

def buildings_in_box(box):
    out = []
    for f in _dedupe(_wfs_box(GRB_WFS, BUILDING_LAYER, box)):
        rings = _rings(f.get("geometry"))
        if rings:
            p = f.get("properties") or {}
            nature = " ".join(str(p.get("LBLTYPE") or "").split())[:60] or None
            out.append({"id": _fid(f)[1], "nature": nature, "rings": rings})
    return out


def road_lines_in_box(box):
    """Yol ve kaldirim kenarlari: [{"id", "nature", "paths"}]."""
    out = []
    for f in _dedupe(_wfs_box(GRB_WFS, ROAD_EDGE_LAYER, box)):
        paths = _paths(f.get("geometry"))
        if paths:
            out.append({"id": _fid(f)[1], "nature": (f.get("properties") or {}).get("LBLTYPE"),
                        "paths": paths})
    return out


def street_axes_in_box(box):
    """Yol eksenleri: [{"id", "name", "paths"}]; ad = LSTRNM, yoksa RSTRNM."""
    out = []
    for f in _dedupe(_wfs_box(GRB_WFS, STREET_LAYER, box)):
        p = f.get("properties") or {}
        name = services._name(p.get("LSTRNM")) or services._name(p.get("RSTRNM"))
        paths = _paths(f.get("geometry"))
        if name and paths:
            out.append({"id": _fid(f)[1], "name": name, "paths": paths})
    return out


__all__ = ["suggest", "parcel_by_capakey", "parcel_by_point", "parcels_in_box",
           "buildings_in_box", "road_lines_in_box", "street_axes_in_box", "UpstreamError"]
