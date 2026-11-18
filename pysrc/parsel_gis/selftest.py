"""
pyKalfa / Parsel-Bina GIS - modul bazli oz-test (Revit ve internet gerekmez)

Servisler sahte bir transport ile taklit edilir (`gis_http.set_transport`);
geometri testleri elle kurulmus metre karelerle calisir.

Kullanim:
    C:\\pyKalfa\\env\\Scripts\\python.exe pysrc/parsel_gis/selftest.py
    C:\\pyKalfa\\env\\Scripts\\python.exe pysrc/parsel_gis/selftest.py --live
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import traceback
from pathlib import Path

import gis_http
import layout
import prepare_gis_input
import suggest_cli
import services


# --- Sahte transport ----------------------------------------------------------

class Fake:
    """`routes`: (url_parcasi, cevap) listesi; cevap dict, dict listesi (sirayla
    verilir) veya bir istisna. Butun cagrilar `calls`'a kaydedilir."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self._seen = {}

    def __call__(self, url, params, post, timeout):
        self.calls.append((url, dict(params), post))
        for i, (part, answer) in enumerate(self.routes):
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                if isinstance(answer, list):
                    n = self._seen.get(i, 0)
                    self._seen[i] = n + 1
                    return answer[min(n, len(answer) - 1)]
                return answer
        return {}

    def calls_to(self, part):
        return [p for (u, p, _) in self.calls if part in u]


def install(routes):
    fake = Fake(routes)
    gis_http.set_transport(fake)
    return fake


def square(x0, y0, size):
    return [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]]


def feature(capakey, rings, **attrs):
    a = {"CAPAKEY": capakey}
    a.update(attrs)
    return {"attributes": a, "geometry": {"rings": rings}}


# --- Task 1: servisler --------------------------------------------------------

def test_capakey_detection():
    assert services.is_capakey(" 92053d0515/00b002 ")
    assert services.normalise_capakey(" 92053d0515/00b002 ") == "92053D0515/00B002"
    assert not services.is_capakey("Rue du Parc 4, 4577 Modave")
    try:
        services.normalise_capakey("abc")
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass


def test_parcel_numero():
    assert services.parcel_numero({"RADICAL": "0515", "BIS": "00", "EXPOSANT": "B", "PUISSANCE": "002"}) == "515B2"
    assert services.parcel_numero({"RADICAL": "0038", "BIS": "00", "EXPOSANT": "F", "PUISSANCE": "000"}) == "38F"
    assert services.parcel_numero({"RADICAL": "0012", "BIS": "02", "EXPOSANT": "_", "PUISSANCE": "000"}) == "12/2"


def test_suggest_merges_and_dedupes():
    install([
        ("geocodeWS/geocode", {"candidates": [{
            "street": {"name": "Rue du Parc"}, "house": {"name": "4", "geometry": {"coordinates": [210000.0, 120000.0]}},
            "zone": {"ident": "4577"}, "city": {"name": "Modave"}}]}),
        ("/searchAll", {"candidates": [
            {"geotag": {"name": "Rue du Parc 4 4577 Modave", "level": 4, "bbox": [210000, 120000, 210002, 120002]}},
            {"geotag": {"name": "Rue du Parc 4577 Modave", "level": 3, "bbox": [209900, 119900, 210100, 120100]}},
        ]}),
    ])
    out = services.suggest("rue du parc 4 modave")
    assert [s["precision"] for s in out] == ["house", "street-bbox-centre"], out
    assert out[0]["label"] == "Rue du Parc 4, 4577 Modave"
    assert len(out) <= 5 and all(set(s) == {"label", "x", "y", "precision"} for s in out)


def test_parcel_by_point_picks_nearest():
    fake = install([(services.CADMAP_LAYER, {"features": [
        feature("FAR", square(115, 90, 10)),   # 15 m uzakta
        feature("NEAR", square(105, 90, 10)),  # 5 m uzakta
    ]})])
    p = services.parcel_by_point(100, 100, 20)
    assert p["capakey"] == "NEAR", p
    assert fake.calls_to(services.CADMAP_LAYER)[-1]["distance"] == 20


def test_query_box_paginates():
    fake = install([(services.CADMAP_LAYER, [
        {"exceededTransferLimit": True, "features": [feature("A", square(0, 0, 10)), feature("B", square(10, 0, 10))]},
        {"features": [feature("C", square(20, 0, 10))]},
    ])])
    assert len(services.parcels_in_box((0, 0, 50, 50))) == 3
    calls = fake.calls_to(services.CADMAP_LAYER)
    assert calls[0]["resultOffset"] == 0 and calls[1]["resultOffset"] == 2, calls
    assert all(c["orderByFields"] == "OBJECTID" for c in calls)


def test_query_box_dedupes_by_objectid():
    # sunucu sayfalar arasinda ayni kaydi tekrar verirse tek sayilmali
    fake = install([(services.PICC_LAYER, [
        {"exceededTransferLimit": True, "features": [
            {"attributes": {"OBJECTID": 1}, "geometry": {"rings": square(0, 0, 5)}},
            {"attributes": {"OBJECTID": 2}, "geometry": {"rings": square(10, 0, 5)}}]},
        {"features": [{"attributes": {"OBJECTID": 2}, "geometry": {"rings": square(10, 0, 5)}}]},
    ])])
    assert [b["id"] for b in services.buildings_in_box((0, 0, 50, 50))] == [1, 2]
    install([(services.CADMAP_LAYER, [
        {"exceededTransferLimit": True, "features": [feature("A", square(0, 0, 10), OBJECTID=1)]},
        {"features": [feature("A", square(0, 0, 10), OBJECTID=1), feature("B", square(10, 0, 10), OBJECTID=2)]},
    ])])
    assert [p["capakey"] for p in services.parcels_in_box((0, 0, 50, 50))] == ["A", "B"]
    assert "OBJECTID" in services.PARCEL_FIELDS.split(",")


def test_suggest_uses_short_timeout():
    seen = []
    gis_http.set_transport(lambda url, params, post, timeout: seen.append(timeout) or {"candidates": []})
    services.suggest("x")
    assert seen and max(seen) <= 10, seen


def test_error_json_raises():
    install([(services.CADMAP_LAYER, {"error": {"code": 500, "message": "x"}})])
    try:
        services.parcel_by_capakey("92053D0515/00B002")
        assert False, "UpstreamError bekleniyordu"
    except gis_http.UpstreamError:
        pass


# --- Task 2: geometri ---------------------------------------------------------

FT = 1 / 0.3048


def _len_m(segs):
    return sum(math.dist(*s) for s in segs) * 0.3048


def test_frame_box_and_origin():
    sq = {"rings": [[[100, 100], [120, 100], [120, 130], [100, 130], [100, 100]]]}
    box = layout.frame_box(sq["rings"], 30)
    assert box == (70, 70, 150, 160), box
    assert layout.to_local_ft(70, 70, box) == [0.0, 0.0]
    assert layout.frame_lines(box)[0] == [[0.0, 0.0], [round(80 * FT, 3), 0.0]]
    assert len(layout.frame_lines(box)) == 4


def test_shared_edge_drawn_once():
    a = {"rings": square(0, 0, 10), "attributes": {}}
    b = {"rings": square(10, 0, 10), "attributes": {}}
    segs = layout.parcel_segments([a, b], (-5, -5, 25, 15))
    # 2 kare = 80 m cevre, ortak 10 m kenar tek sayilir
    assert abs(_len_m(segs) - 70.0) < 0.01, _len_m(segs)


def test_segments_clipped_to_frame():
    big = {"rings": square(0, 0, 100), "attributes": {}}
    segs = layout.parcel_segments([big], (50, -10, 150, 50))
    assert all(-1e-6 <= v <= round(100 * FT, 3) + 1e-6 for s in segs for p in s for v in p)
    # x=100 kenarinin y in [0,50] kismi + y=0 kenarinin x in [50,100] kismi = 100 m
    assert abs(_len_m(segs) - 100.0) < 0.01, _len_m(segs)


def test_building_split_by_frame():
    u = {"id": 1, "rings": [[[0, 0], [30, 0], [30, 30], [20, 30], [20, 10], [10, 10], [10, 30], [0, 30], [0, 0]]]}
    regions = layout.building_regions([u], (-5, 15, 35, 40))  # U'nun iki kolu ayri kalir
    assert len(regions) == 2 and all(len(r["vertices_ft"]) >= 3 for r in regions), regions


def test_labels_skip_tiny_and_use_numero():
    p = {"rings": square(0, 0, 10), "capakey": "X",
         "attributes": {"RADICAL": "0568", "BIS": "00", "EXPOSANT": "C", "PUISSANCE": "000"}}
    labels = layout.parcel_labels([p], (-5, -5, 15, 15))
    assert labels[0]["text"] == "568C" and labels[0]["rotation_deg"] == 0.0
    assert layout.parcel_labels([p], (8, 8, 30, 30)) == []  # cerceve icinde 4 m2 < 20 m2


def test_building_edges_long_enough_for_revit():
    # 0.015 m'lik kenar Revit'te (MIN_SEGMENT_LENGTH_FT = 0.05 ft) atlanir ve loop kopar
    b = {"id": 1, "rings": [[[0, 0], [10, 0], [10, 10], [5.015, 10], [5, 10], [0, 10], [0, 0]]]}
    verts = layout.building_regions([b], (-5, -5, 15, 15))[0]["vertices_ft"]
    edges = [math.dist(verts[i], verts[(i + 1) % len(verts)]) for i in range(len(verts))]
    assert min(edges) >= 0.05, edges


def test_selected_parcel_lines_split_from_others():
    a = {"rings": square(0, 0, 10), "capakey": "SEL", "attributes": {}}
    b = {"rings": square(10, 0, 10), "capakey": "NB", "attributes": {}}
    box = (-5, -5, 25, 15)
    sel = layout.selected_parcel_segments(a, box)
    others = layout.parcel_segments([a, b], box, exclude=a)
    # secilen parselin 4 kenari (40 m, komsuyla ortak kenar dahil) ayri;
    # digerleri yalniz komsunun kalan 3 kenari (30 m) -- ortak kenar iki kez cizilmez
    assert abs(_len_m(sel) - 40.0) < 0.01, _len_m(sel)
    assert abs(_len_m(others) - 30.0) < 0.05, _len_m(others)


def test_labels_mark_selected_parcel():
    a = {"rings": square(0, 0, 10), "capakey": "SEL", "attributes": {"RADICAL": "0001", "BIS": "00", "EXPOSANT": "A", "PUISSANCE": "000"}}
    b = {"rings": square(10, 0, 10), "capakey": "NB", "attributes": {"RADICAL": "0002", "BIS": "00", "EXPOSANT": "A", "PUISSANCE": "000"}}
    labels = layout.parcel_labels([a, b], (-5, -5, 25, 15), selected_capakey="SEL")
    assert {l["text"]: l["selected"] for l in labels} == {"1A": True, "2A": False}, labels


def test_north_top_right():
    n = layout.north_record((0, 0, 100, 50))
    assert n == {"position_ft": [round(95 * FT, 3), round(45 * FT, 3)], "rotation_deg": 0.0}, n


# --- Task 3: CLI'ler ----------------------------------------------------------

NUMERO_515B2 = {"RADICAL": "0515", "BIS": "00", "EXPOSANT": "B", "PUISSANCE": "002"}


def _world():
    """Secilen parsel (200000,100000)'de 20x20 m, yaninda bir komsu ve bir bina."""
    sel = feature("92053D0515/00B002", square(200000, 100000, 20), **NUMERO_515B2)
    nb = feature("92053D0516/00_000", square(200020, 100000, 20), RADICAL="0516", BIS="00", EXPOSANT="_", PUISSANCE="000")
    bld = {"attributes": {"OBJECTID": 7, "NATUR_DESC": "Habitation"}, "geometry": {"rings": square(200005, 100005, 8)}}
    return [
        (services.CADMAP_LAYER, {"features": [sel, nb]}),
        (services.PICC_LAYER, {"features": [bld]}),
    ]


def _tmp():
    return Path(tempfile.mkdtemp(prefix="pykalfa_gis_"))


def test_prepare_writes_existing_format():
    install(_world())
    tmp = _tmp()
    data = prepare_gis_input.prepare("92053D0515/00B002", None, None, 30, tmp, labels=True)
    for k in ("parcel_lines", "frame_lines", "buildings", "labels", "north"):
        assert k in data, k
    assert data["source"] == "GIS" and data["selected"]["numero"] == "515B2", data["selected"]
    assert (tmp / "revit_input.json").is_file() and (tmp / "revit_input_preview.png").is_file()
    assert min(v for s in data["frame_lines"] for p in s for v in p) == 0.0
    assert data["building_count"] == 1 and {l["text"] for l in data["labels"]} == {"515B2", "516"}
    # secilen parselin siniri ayri listede, numarasi isaretli
    assert abs(_len_m(data["selected_parcel_lines"]) - 80.0) < 0.01, _len_m(data["selected_parcel_lines"])
    assert {l["text"]: l["selected"] for l in data["labels"]} == {"515B2": True, "516": False}


def test_prepare_from_point_uses_20m():
    fake = install(_world())
    prepare_gis_input.prepare(None, 200010.0, 100010.0, 30, _tmp())
    assert fake.calls_to(services.CADMAP_LAYER)[0]["distance"] == 20


def test_prepare_upstream_error_exit_code():
    install([(services.CADMAP_LAYER, gis_http.UpstreamError("servis yok"))])
    tmp = _tmp()
    rc = prepare_gis_input.main(["--capakey", "92053D0515/00B002", "--margin", "30", "--output-dir", str(tmp)])
    assert rc == 2, rc
    assert not (tmp / "revit_input.json").exists()


def test_prepare_not_found_and_bad_margin():
    install([(services.CADMAP_LAYER, {"features": []})])
    tmp = _tmp()
    assert prepare_gis_input.main(["--x", "1", "--y", "1", "--margin", "30", "--output-dir", str(tmp)]) == 3
    install(_world())
    assert prepare_gis_input.main(["--capakey", "92053D0515/00B002", "--margin", "500", "--output-dir", str(tmp)]) == 4
    assert not (tmp / "revit_input.json").exists()


def test_suggest_cli_utf8():
    fake = install([
        ("geocodeWS/geocode", {"candidates": [{
            "street": {"name": "Rue de l'Église"}, "house": {"name": "3", "geometry": {"coordinates": [235000.0, 148000.0]}},
            "zone": {"ident": "4000"}, "city": {"name": "Liège"}}]}),
        ("geocodeWS/searchAll", {"candidates": []}),
    ])
    out = _tmp() / "s.json"
    assert suggest_cli.main(["--query", "rue de l'église 3 liège", "--output", str(out)]) == 0
    cands = json.loads(out.read_text(encoding="utf-8"))["candidates"]
    assert cands[0]["label"].startswith("Rue de l'Église"), cands
    assert "église" in fake.calls_to("geocodeWS/geocode")[0]["address"]


def test_suggest_cli_capakey_mode():
    install(_world())
    out = _tmp() / "c.json"
    assert suggest_cli.main(["--query", "92053d0515/00b002", "--output", str(out)]) == 0
    c = json.loads(out.read_text(encoding="utf-8"))["candidates"]
    assert c[0]["capakey"] == "92053D0515/00B002" and c[0]["precision"] == "capakey", c
    install([(services.CADMAP_LAYER, {"features": []})])
    assert suggest_cli.main(["--query", "92053D0515/00B002", "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["candidates"] == []


# --- Yol / kaldirim kenarlari ve sokak adlari ---------------------------------

def _path_feature(oid, path, **attrs):
    a = {"OBJECTID": oid}
    a.update(attrs)
    return {"attributes": a, "geometry": {"paths": [path]}}


def test_road_lines_query_filters_natures():
    fake = install([(services.PICC_ROAD_LINES, {"features": [
        _path_feature(1, [[0, 0], [10, 0]], NATUR_DESC="Voirie - Bord"),
        _path_feature(2, [[0, 5], [10, 5]], NATUR_DESC="Trottoir"),
        _path_feature(2, [[0, 5], [10, 5]], NATUR_DESC="Trottoir"),  # tekrar
    ]})])
    roads = services.road_lines_in_box((0, 0, 50, 50))
    assert [r["id"] for r in roads] == [1, 2] and roads[0]["paths"] == [[[0.0, 0.0], [10.0, 0.0]]]
    where = fake.calls_to(services.PICC_ROAD_LINES)[0]["where"]
    for nature in ("Voirie - Bord", "Chemin - Bord", "Trottoir"):
        assert "'{}'".format(nature) in where, where
    assert "Bordure" not in where and "Parking" not in where


def test_street_axes_name_fallback():
    install([(services.PICC_AXES, {"features": [
        _path_feature(1, [[0, 0], [10, 0]], RUE_NOM1="Rue de l'Évêché"),
        _path_feature(2, [[0, 0], [0, 10]], RUE_NOM1=None, VOIRIE_NOM="N617a"),
        _path_feature(3, [[5, 5], [9, 9]], RUE_NOM1=" ", VOIRIE_NOM=None),
    ]})])
    axes = services.street_axes_in_box((0, 0, 50, 50))
    assert [a["name"] for a in axes] == ["Rue de l'Évêché", "N617a"], axes


def test_road_segments_clipped_and_deduped():
    roads = [{"id": 1, "paths": [[[-10, 0], [30, 0]]]}, {"id": 2, "paths": [[[5, 0], [15, 0]]]}]
    segs = layout.road_segments(roads, (0, -5, 20, 5))
    assert abs(_len_m(segs) - 20.0) < 0.01, _len_m(segs)  # 40 m cizgi cercevede 20 m, ust uste binen tek


def test_street_label_once_on_longest_part_centered():
    axes = [
        {"id": 1, "name": "Rue A", "paths": [[[0, 10], [100, 10]]]},
        {"id": 2, "name": "Rue A", "paths": [[[100, 10], [100, 15]]]},   # ayni sokak, kisa parca
        {"id": 3, "name": "Rue B", "paths": [[[50, 0], [50, 4]]]},       # cok kisa: yazilmaz
    ]
    labels = layout.street_labels(axes, (0, 0, 120, 40))
    assert [l["text"] for l in labels] == ["Rue A"], labels
    # birlesik eksen (0,10)-(100,10)-(100,15) = 105 m; orta nokta 52.5 m -> (52.5, 10)
    assert labels[0]["position_ft"] == [round(52.5 * FT, 3), round(10 * FT, 3)], labels[0]
    assert labels[0]["rotation_deg"] == 0.0


def test_street_label_rotation_follows_road_and_stays_readable():
    up = layout.street_labels([{"id": 1, "name": "Rue N", "paths": [[[10, 0], [10, 50]]]}], (0, 0, 20, 60))
    down = layout.street_labels([{"id": 1, "name": "Rue S", "paths": [[[10, 50], [10, 0]]]}], (0, 0, 20, 60))
    diag = layout.street_labels([{"id": 1, "name": "Rue D", "paths": [[[40, 40], [0, 0]]]}], (0, 0, 50, 50))
    assert up[0]["rotation_deg"] == 90.0 and down[0]["rotation_deg"] == 90.0, (up, down)
    assert diag[0]["rotation_deg"] == 45.0, diag  # ters (225 derece) okunmaz -> 45


def test_prepare_includes_roads_and_streets():
    world = _world() + [
        (services.PICC_ROAD_LINES, {"features": [_path_feature(1, [[199990, 99995], [200050, 99995]], NATUR_DESC="Voirie - Bord")]}),
        (services.PICC_AXES, {"features": [_path_feature(5, [[199980, 99990], [200060, 99990]], RUE_NOM1="Rue du Parc")]}),
    ]
    install(world)
    data = prepare_gis_input.prepare("92053D0515/00B002", None, None, 30, _tmp())
    assert data["road_lines"] and data["road_line_count"] == len(data["road_lines"])
    assert [s["text"] for s in data["street_labels"]] == ["Rue du Parc"]
    install(world)
    off = prepare_gis_input.prepare("92053D0515/00B002", None, None, 30, _tmp(), roads=False, streets=False)
    assert off["road_lines"] == [] and off["street_labels"] == []


def test_suggest_cli_resolves_point():
    install(_world())
    out = _tmp() / "p.json"
    assert suggest_cli.main(["--x", "200010", "--y", "100010", "--output", str(out)]) == 0
    c = json.loads(out.read_text(encoding="utf-8"))["candidates"]
    assert c[0]["capakey"] == "92053D0515/00B002" and c[0]["numero"] == "515B2", c
    install([(services.CADMAP_LAYER, {"features": []})])
    assert suggest_cli.main(["--x", "1", "--y", "1", "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["candidates"] == []


# --- Flaman bolgesi (Digitaal Vlaanderen) -------------------------------------

def _fl():
    import flanders
    return flanders


def _regions():
    import regions
    return regions


class FakeVl:
    """Flaman servisleri: geolocation (path -> cevap) ve WFS (typeNames ->
    feature listesi ya da `fn(params) -> liste`). Valonya yollari icin
    `wal` (Fake routes) verilebilir."""

    def __init__(self, layers=None, geoloc=None, wal=None, fail=()):
        self.layers = layers or {}
        self.geoloc = geoloc or {}
        self.wal = Fake(wal or [])
        self.fail = fail
        self.calls = []

    def __call__(self, url, params, post, timeout):
        self.calls.append((url, dict(params)))
        for part in self.fail:
            if part in url:
                raise gis_http.UpstreamError("{} dustu".format(part))
        if "geo.api.vlaanderen.be/geolocation" in url:
            for key, answer in self.geoloc.items():
                if url.endswith(key[0]) and params.get("q") == key[1]:
                    return answer
            return {"LocationResult": [], "SuggestionResult": []}
        if "geo.api.vlaanderen.be" in url and url.endswith("/wfs"):
            src = self.layers.get(params.get("typeNames"), [])
            feats = src(params) if callable(src) else src
            return {"type": "FeatureCollection", "features": feats}
        return self.wal(url, params, post, timeout)

    def wfs_calls(self, type_name):
        return [p for (u, p) in self.calls if p.get("typeNames") == type_name]


def install_vl(**kw):
    fake = FakeVl(**kw)
    gis_http.set_transport(fake)
    return fake


def gj_poly(oid, rings, multi=False, **props):
    p = {"OIDN": oid}
    p.update(props)
    geom = ({"type": "MultiPolygon", "coordinates": [rings]} if multi
            else {"type": "Polygon", "coordinates": rings})
    return {"type": "Feature", "properties": p, "geometry": geom}


def gj_line(oid, path, multi=False, **props):
    p = {"OIDN": oid}
    p.update(props)
    geom = ({"type": "MultiLineString", "coordinates": [path]} if multi
            else {"type": "LineString", "coordinates": path})
    return {"type": "Feature", "properties": p, "geometry": geom}


def _loc(addr, x, y, kind="basisregisters_huisnummer_afgeleidVanObject", bbox=None):
    b = bbox or (x, y, x, y)
    return {"FormattedAddress": addr, "LocationType": kind,
            "Location": {"X_Lambert72": x, "Y_Lambert72": y},
            "BoundingBox": {"LowerLeft": {"X_Lambert72": b[0], "Y_Lambert72": b[1]},
                            "UpperRight": {"X_Lambert72": b[2], "Y_Lambert72": b[3]}}}


def test_flanders_suggest_from_location():
    fl = _fl()
    install_vl(geoloc={("/Location", "steenstraat 10 brugge"): {"LocationResult": [
        _loc("Steenstraat 10, 8000 Brugge", 69975.93, 211528.5)]}})
    out = fl.suggest("steenstraat 10 brugge")
    assert out == [{"label": "Steenstraat 10, 8000 Brugge", "x": 69975.93, "y": 211528.5,
                    "precision": "house", "region": "vla"}], out


def test_flanders_suggest_falls_back_to_suggestion_list():
    fl = _fl()
    fake = install_vl(geoloc={
        ("/Suggestion", "steenstraat brugge"): {"SuggestionResult": ["Steenstraat, Brugge"]},
        ("/Location", "Steenstraat, Brugge"): {"LocationResult": [
            _loc("Steenstraat, Brugge", 69900.0, 211500.0, kind="basisregisters_straatnaam",
                 bbox=(69800.0, 211400.0, 70000.0, 211600.0))]}})
    out = fl.suggest("steenstraat brugge")
    assert out == [{"label": "Steenstraat, Brugge", "x": 69900.0, "y": 211500.0,
                    "precision": "street-bbox-centre", "region": "vla"}], out
    assert [p["q"] for (u, p) in fake.calls] == ["steenstraat brugge", "steenstraat brugge",
                                                 "Steenstraat, Brugge"], fake.calls


def test_suggest_all_merges_regions_and_tolerates_one_failure():
    rg = _regions()
    wal = [("geocodeWS/geocode", {"candidates": [{
        "street": {"name": "Rue du Parc"}, "house": {"name": "4", "geometry": {"coordinates": [210000.0, 120000.0]}},
        "zone": {"ident": "4577"}, "city": {"name": "Modave"}}]}),
        ("geocodeWS/searchAll", {"candidates": []})]
    vl = {("/Location", "parc 4"): {"LocationResult": [_loc("Parkstraat 4, 8000 Brugge", 70000.0, 211000.0)]}}
    install_vl(geoloc=vl, wal=wal)
    out = rg.suggest_all("parc 4")
    assert [c["region"] for c in out] == ["wal", "vla"], out
    install_vl(geoloc=vl, fail=("geocodeWS",))
    assert [c["region"] for c in rg.suggest_all("parc 4")] == ["vla"]
    install_vl(fail=("geocodeWS", "geo.api.vlaanderen.be"))
    try:
        rg.suggest_all("parc 4")
        assert False, "UpstreamError bekleniyordu"
    except gis_http.UpstreamError:
        pass


def test_flanders_parcel_by_capakey_and_numero():
    fl = _fl()
    fake = install_vl(layers={"Adpf:Adpf": [gj_poly(
        11, [[[70000, 211000], [70010, 211000], [70010, 211010], [70000, 211000]]], multi=True,
        CAPAKEY="31804D0468/00A000")]})
    p = fl.parcel_by_capakey(" 31804d0468/00a000 ")
    assert p["capakey"] == "31804D0468/00A000" and len(p["rings"]) == 1, p
    assert services.parcel_numero(p["attributes"]) == "468A", p["attributes"]
    assert "CAPAKEY='31804D0468/00A000'" in fake.wfs_calls("Adpf:Adpf")[0]["CQL_FILTER"]
    assert fake.wfs_calls("Adpf:Adpf")[0]["srsName"] == "EPSG:31370"


def test_flanders_parcel_by_point_picks_nearest():
    fl = _fl()
    fake = install_vl(layers={"Adpf:Adpf": [
        gj_poly(1, square(115, 90, 10), CAPAKEY="FAR"), gj_poly(2, square(105, 90, 10), CAPAKEY="NEAR")]})
    assert fl.parcel_by_point(100, 100, 20)["capakey"] == "NEAR"
    bbox = fake.wfs_calls("Adpf:Adpf")[0]["bbox"]
    assert bbox.startswith("80.00,80.00,120.00,120.00") and bbox.endswith("EPSG:31370"), bbox


def test_flanders_wfs_splits_full_box_and_dedupes():
    fl = _fl()
    old = fl.WFS_COUNT
    fl.WFS_COUNT = 3
    feats = [gj_poly(i, square(i * 10, 0, 5), CAPAKEY="K{}".format(i)) for i in range(5)]

    def answer(params):
        x0, y0, x1, y1 = [float(v) for v in params["bbox"].split(",")[:4]]
        inside = [f for f in feats
                  if x0 <= f["geometry"]["coordinates"][0][0][0] <= x1]
        return inside[:fl.WFS_COUNT] if x1 - x0 > 30 else inside
    try:
        fake = install_vl(layers={"Adpf:Adpf": answer})
        got = fl.parcels_in_box((0, 0, 60, 60))
    finally:
        fl.WFS_COUNT = old
    assert sorted(p["capakey"] for p in got) == ["K0", "K1", "K2", "K3", "K4"], got
    assert len(fake.wfs_calls("Adpf:Adpf")) > 1


def test_flanders_buildings_roads_streets():
    fl = _fl()
    install_vl(layers={
        "GRB:GBG": [gj_poly(7, square(0, 0, 8), LBLTYPE="hoofdgebouw")],
        "GRB:WGO": [gj_line(1, [[0, 0], [10, 0]], TYPE=3, LBLTYPE="rand van de rijbaan (wrb)"),
                    gj_line(2, [[0, 5], [10, 5]], multi=True, TYPE=1,
                            LBLTYPE="grens zone zwakke weggebruiker (wcz)"),
                    gj_line(2, [[0, 5], [10, 5]], TYPE=1)],
        "GRB:Wegsegment": [gj_line(3, [[0, 0], [50, 0]], LSTRNM="Steenstraat", RSTRNM="Steenstraat"),
                           gj_line(4, [[0, 0], [0, 50]], LSTRNM=None, RSTRNM="Markt"),
                           gj_line(5, [[0, 0], [5, 5]], LSTRNM=" ", RSTRNM=None)]})
    b = fl.buildings_in_box((0, 0, 50, 50))
    assert [x["id"] for x in b] == [7] and b[0]["nature"] == "hoofdgebouw", b
    r = fl.road_lines_in_box((0, 0, 50, 50))
    assert [x["id"] for x in r] == [1, 2] and r[1]["paths"] == [[[0.0, 5.0], [10.0, 5.0]]], r
    s = fl.street_axes_in_box((0, 0, 50, 50))
    assert [x["name"] for x in s] == ["Steenstraat", "Markt"], s


def test_flanders_rejects_bad_coordinates():
    fl = _fl()
    install_vl(layers={"GRB:GBG": [gj_poly(1, [[[0, 0], [1e9, 0], [1e9, 1], [0, 0]]])],
                       "Adpf:Adpf": [gj_poly(2, [[["a", 0], [1, 0], [1, 1], ["a", 0]]], CAPAKEY="X")]})
    assert fl.buildings_in_box((0, 0, 5, 5)) == []
    assert fl.parcels_in_box((0, 0, 5, 5)) == []


def _vl_world():
    sel = gj_poly(1, square(70000, 211000, 20), CAPAKEY="31804D0468/00A000")
    nb = gj_poly(2, square(70020, 211000, 20), CAPAKEY="31804D0469/00_000")
    return {"Adpf:Adpf": [sel, nb], "GRB:GBG": [gj_poly(7, square(70005, 211005, 8))],
            "GRB:WGO": [gj_line(1, [[69990, 210995], [70050, 210995]], TYPE=3)],
            "GRB:Wegsegment": [gj_line(5, [[69980, 210990], [70060, 210990]], LSTRNM="Steenstraat")]}


def test_parcel_by_capakey_any_falls_back_to_flanders():
    rg = _regions()
    install_vl(layers=_vl_world(), wal=[(services.CADMAP_LAYER, {"features": []})])
    region, p = rg.parcel_by_capakey_any("31804D0468/00A000")
    assert region == "vla" and p["capakey"] == "31804D0468/00A000", (region, p)
    install(_world())
    region, p = rg.parcel_by_capakey_any("92053D0515/00B002")
    assert region == "wal", region


def test_suggest_cli_regions():
    install_vl(layers=_vl_world(), wal=[(services.CADMAP_LAYER, {"features": []})])
    out = _tmp() / "r.json"
    assert suggest_cli.main(["--query", "31804D0468/00A000", "--output", str(out)]) == 0
    c = json.loads(out.read_text(encoding="utf-8"))["candidates"]
    assert c[0]["region"] == "vla" and c[0]["numero"] == "468A", c
    assert suggest_cli.main(["--x", "70010", "--y", "211010", "--region", "vla",
                             "--output", str(out)]) == 0
    c = json.loads(out.read_text(encoding="utf-8"))["candidates"]
    assert c[0]["capakey"] == "31804D0468/00A000" and c[0]["region"] == "vla", c
    install(_world())
    assert suggest_cli.main(["--x", "200010", "--y", "100010", "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["candidates"][0]["region"] == "wal"


def test_prepare_region_vla():
    install_vl(layers=_vl_world())
    tmp = _tmp()
    rc = prepare_gis_input.main(["--capakey", "31804D0468/00A000", "--region", "vla",
                                 "--margin", "30", "--output-dir", str(tmp)])
    assert rc == 0, rc
    data = json.loads((tmp / "revit_input.json").read_text(encoding="utf-8"))
    assert data["selected"] == {"capakey": "31804D0468/00A000", "numero": "468A"}, data["selected"]
    assert data["region"] == "vla" and "Digitaal Vlaanderen" in data["attribution"]
    assert data["building_count"] == 1 and data["road_lines"] and \
        [s["text"] for s in data["street_labels"]] == ["Steenstraat"]
    assert {l["text"] for l in data["labels"]} == {"468A", "469"}


# --- Calistirici --------------------------------------------------------------

def _tests():
    return [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--live" in argv:
        return live()
    count = 0
    for name, fn in _tests():
        try:
            fn()
        except Exception:
            print("FAIL {}".format(name))
            traceback.print_exc()
            return 1
        finally:
            gis_http.set_transport(None)
        count += 1
    print("OK {} test".format(count))
    return 0


LIVE_ADDRESS = "Rue du Parc 4 Modave"
LIVE_CAPAKEY = "92053D0515/00B002"


def live():
    """Gercek SPW/ICAR servisleriyle duman testi; cikti `output/` altina yazilir."""
    out_dir = Path(__file__).resolve().parents[2] / "output"
    cands = services.suggest(LIVE_ADDRESS)
    print("suggest({!r}): {} aday".format(LIVE_ADDRESS, len(cands)))
    for c in cands:
        print("  ", c)
    assert cands, "adres adayi yok"
    data = prepare_gis_input.prepare(LIVE_CAPAKEY, None, None, 30, out_dir)
    assert data["parcel_lines"] and data["labels"], "cizgi/etiket yok"
    data2 = prepare_gis_input.prepare(None, cands[0]["x"], cands[0]["y"], 30, out_dir / "live_address")
    print("adres -> parsel {} ({})".format(data2["selected"]["numero"], data2["selected"]["capakey"]))
    _live_flanders(out_dir / "live_vla")
    print("LIVE OK")
    return 0


LIVE_ADDRESS_VLA = "Steenstraat 10 Brugge"


def _live_flanders(out_dir):
    import regions
    cands = regions.suggest_all(LIVE_ADDRESS_VLA)
    print("suggest_all({!r}): {}".format(LIVE_ADDRESS_VLA, [(c["region"], c["label"]) for c in cands]))
    vla = [c for c in cands if c["region"] == "vla"]
    assert vla, "Flaman adayi yok"
    data = prepare_gis_input.prepare(None, vla[0]["x"], vla[0]["y"], 80, out_dir, region="vla")
    ck = data["selected"]["capakey"]
    region, p = regions.parcel_by_capakey_any(ck)
    assert region == "vla" and p, (region, ck)
    print("Flaman: parsel {} ({}) | parsel {} | bina {} | yol cizgisi {} | sokak adi {}".format(
        data["selected"]["numero"], ck, data["parcel_count"], data["building_count"],
        data["road_line_count"], data["street_label_count"]))
    assert data["parcel_lines"] and data["building_count"] and data["road_lines"] and data["street_labels"]


if __name__ == "__main__":
    sys.exit(main())
