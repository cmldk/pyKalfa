"""
pyKalfa / Parsel-Bina GIS - modul bazli oz-test (Revit ve internet gerekmez)

Servisler sahte bir transport ile taklit edilir (`gis_http.set_transport`);
geometri testleri elle kurulmus metre karelerle calisir.

Kullanim:
    C:\\pyKalfa\\env\\Scripts\\python.exe pysrc/parsel_gis/selftest.py
    C:\\pyKalfa\\env\\Scripts\\python.exe pysrc/parsel_gis/selftest.py --live
"""

from __future__ import annotations

import sys
import traceback

import gis_http
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
    assert fake.calls_to(services.CADMAP_LAYER)[1]["resultOffset"] == 2


def test_error_json_raises():
    install([(services.CADMAP_LAYER, {"error": {"code": 500, "message": "x"}})])
    try:
        services.parcel_by_capakey("92053D0515/00B002")
        assert False, "UpstreamError bekleniyordu"
    except gis_http.UpstreamError:
        pass


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


def live():
    print("LIVE: henuz tanimli degil")
    return 1


if __name__ == "__main__":
    sys.exit(main())
