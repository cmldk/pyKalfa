"""
pyKalfa / Duvar - modul bazli oz-test (Revit gerekmez)

Sentetik bir DXF uretip `dxf_reader -> geometry -> wall_detector ->
prepare_wall_input` zincirini bastan sona calistirir ve beklenen sonuclari
dogrular. Revit veya gercek bir Polycam ciktisi olmadan, degisiklik
sonrasi "hala calisiyor mu?" sorusunu saniyeler icinde cevaplar.

Sentetik plan, gercek Polycam ciktisindaki (`assets/simple.dxf`) yapiyi
taklit eder -- cunku ilk surumun basarisiz olmasinin sebebi tam olarak bu
yapiyi bilmemekti:

  - duvarlar **kapali dis hat (outline)** olarak cizilir, iki cizgi
    olarak degil;
  - ayni duvar dosyada birden fazla kez yer alabilir;
  - kapi/pencere de ayni sekilde cizilir, sadece katmani farklidir;
  - mobilya/oda poligonlari duvarla ayni dosyada durur ve duvar
    sanilmamalidir.

Kullanim:
    env/Scripts/python.exe pysrc/duvar/selftest.py
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import ezdxf

import geometry
import wall_detector
from dxf_reader import read_dxf
from prepare_wall_input import prepare

FT = geometry.FEET_PER_METER


def _wall_outline(msp, p1, p2, thickness, layer):
    """Bir duvari, Polycam'in yaptigi gibi kapali dis hat olarak cizer.

    Halka: uc-ortasi -> yuz A -> uc-ortasi -> yuz B -> kapanis."""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy * thickness / 2.0, ux * thickness / 2.0
    points = [
        (x1, y1),                       # baslangic ucunun ortasi
        (x1 + nx, y1 + ny),             # A yuzu basi
        (x2 + nx, y2 + ny),             # A yuzu sonu
        (x2, y2),                       # bitis ucunun ortasi
        (x2 - nx, y2 - ny),             # B yuzu (ters yon)
        (x1 - nx, y1 - ny),
        (x1, y1),                       # kapanis
    ]
    msp.add_lwpolyline(points, dxfattribs={"layer": layer})


def _build_sample_dxf(path: Path) -> None:
    """Milimetre biriminde, bilinen olculerde bir kat plani uretir."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()

    # Dis duvarlar: 8 m x 6 m dikdortgen, 200 mm kalinlik.
    corners = [(0, 0), (8000, 0), (8000, 6000), (0, 6000)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        _wall_outline(msp, a, b, 200, "Duvar")

    # Ic duvar: 100 mm kalinlik.
    _wall_outline(msp, (3000, 0), (3000, 3000), 100, "Duvar")

    # AYNI ic duvar bir kez daha (Polycam ciktisinda oldugu gibi) --
    # tekrar eleme calismazsa Revit'te ust uste iki duvar olusur.
    _wall_outline(msp, (3000, 0), (3000, 3000), 100, "Duvar")

    # Kapi: duvarla ayni formatta ama baska katmanda.
    _wall_outline(msp, (3000, 1000), (3000, 1900), 100, "Kapi")

    # Mobilya: kare bir kontur (en/boy orani dusuk -> duvar degil).
    msp.add_lwpolyline(
        [(500, 500), (1200, 500), (1200, 1200), (500, 1200)],
        close=True, dxfattribs={"layer": "Mobilya"},
    )
    # Oda poligonu: cok "kalin" -> duvar degil.
    msp.add_lwpolyline(
        [(200, 200), (7800, 200), (7800, 5800), (200, 5800)],
        close=True, dxfattribs={"layer": "Oda"},
    )
    # Tek cizgiler (olculendirme): dis hat degil -> sadece --lines modunda.
    msp.add_line((0, -500), (8000, -500), dxfattribs={"layer": "Olcu"})

    # Blok referansi: 2 m'lik bir duvar, 90 derece dondurulup
    # (6000, 1000) noktasina yerlestiriliyor -> WCS'de dusey olmali.
    block = doc.blocks.new(name="DUVAR_PARCASI")
    _wall_outline(block, (0, 0), (2000, 0), 100, "0")
    msp.add_blockref(
        "DUVAR_PARCASI", (6000, 1000), dxfattribs={"layer": "Duvar", "rotation": 90}
    )

    doc.saveas(str(path))


def _approx(value, expected, tol=0.05):
    return abs(value - expected) <= tol


def _check(name, condition, detail=""):
    print("  {} {}{}".format("[OK]  " if condition else "[HATA]", name,
                             "" if condition else " -> " + str(detail)))
    return bool(condition)


def run() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dxf_path = tmp_path / "ornek_plan.dxf"
        _build_sample_dxf(dxf_path)

        print("1) dxf_reader")
        result = read_dxf(dxf_path)
        ok &= _check("DXF birimi mm ($INSUNITS=4)", result.insunits == 4, result.insunits)
        ok &= _check("Polyline butunlugu korunuyor (segmentlere parcalanmiyor)",
                     all(hasattr(p, "points") for p in result.polys)
                     and any(len(p.points) >= 6 for p in result.polys))
        rings = [p for p in result.polys if p.is_ring()]
        ok &= _check("Kapali halkalar tanindi", len(rings) >= 9, len(rings))

        print("2) geometry - birim")
        unit = geometry.resolve_units(result.insunits, result.segments(), "auto")
        ok &= _check("Birim mm olarak cozuldu ve kesin",
                     unit.name == "mm" and unit.confident, unit.name)
        guessed = geometry.resolve_units(0, result.segments(), "auto")
        ok &= _check("Birim yoksa tahmin uretiliyor ve 'kesin degil' isaretleniyor",
                     guessed.name == "mm" and not guessed.confident, guessed.name)

        print("3) wall_detector - dis hattan merkez eksen")
        polys_ft = geometry.to_feet_polys(result.polys, unit)
        walls, leftovers = wall_detector.detect_walls(polys_ft, FT)
        duvar = [w for w in walls if w.layer == "Duvar"]
        ok &= _check("Dis duvarlar + ic duvar + blok = 6 duvar (tekrar elendi)",
                     len(duvar) == 6,
                     "{} -> {}".format(len(duvar), [round(w.length_ft/FT, 2) for w in duvar]))
        ok &= _check("Dis duvar kalinligi 20 cm olculdu",
                     any(_approx(w.thickness_ft / FT, 0.20, 0.005) for w in duvar),
                     [round(w.thickness_ft/FT, 3) for w in duvar])
        ok &= _check("Ic duvar kalinligi 10 cm olculdu",
                     any(_approx(w.thickness_ft / FT, 0.10, 0.005) for w in duvar),
                     [round(w.thickness_ft/FT, 3) for w in duvar])
        ok &= _check("Merkez eksen dis hattin ortasindan geciyor (8 m'lik duvar)",
                     any(_approx(w.length_ft / FT, 8.0, 0.02) for w in duvar),
                     [round(w.length_ft/FT, 2) for w in duvar])
        ok &= _check("Ayni duvarin ikinci kopyasi elendi",
                     sum(1 for w in duvar if _approx(w.length_ft/FT, 3.0, 0.02)) == 1,
                     [round(w.length_ft/FT, 2) for w in duvar])
        ok &= _check("Blok referansi patlatilip donduruldu (dusey 2 m'lik duvar)",
                     any(_approx(w.length_ft/FT, 2.0, 0.02) and abs(w.x1 - w.x2) < 0.01
                         for w in duvar),
                     [(round(w.x1/FT,2), round(w.y1/FT,2), round(w.x2/FT,2), round(w.y2/FT,2))
                      for w in duvar])
        ok &= _check("Kapi ayri katmanda duvar olarak listelendi (filtre kullanicida)",
                     any(w.layer == "Kapi" for w in walls))
        ok &= _check("Mobilya (kare) duvar sayilmadi",
                     not any(w.layer == "Mobilya" for w in walls))
        ok &= _check("Oda poligonu (cok kalin) duvar sayilmadi",
                     not any(w.layer == "Oda" for w in walls))
        ok &= _check("Olcu cizgisi (dis hat degil) eslesmeyene dusuldu",
                     any(p.layer == "Olcu" for p in leftovers))

        print("4) geometry - tek cizgi modu temizligi")
        segs = []
        for p in leftovers:
            segs.extend(p.segments())
        cleaned, stats = geometry.clean_segments(segs)
        ok &= _check("Temizlik calisti ve istatistik uretti",
                     stats["raw"] > 0 and "final" in stats, stats)
        # Paralel iki dogru (10 cm arali) tek dogruya cokmemeli:
        parallel = [
            geometry.Segment(0.0, 0.0, 10.0, 0.0, "T"),
            geometry.Segment(0.0, 0.328, 10.0, 0.328, "T"),   # 10 cm = 0.328 ft
        ]
        merged = geometry.merge_collinear(parallel, 1.5, 0.0656, 0.164)  # 2 cm / 5 cm
        ok &= _check("10 cm arali paralel iki dogru birlestirilmedi (kayma yok)",
                     len(merged) == 2, [(round(m.y1, 3), round(m.y2, 3)) for m in merged])

        print("5) prepare_wall_input (uctan uca)")
        data = prepare(dxf_path, tmp_path, units="auto")
        ok &= _check("JSON yazildi", (tmp_path / "wall_input.json").is_file())
        ok &= _check("Sadece dis hat duvarlari var (tek cizgi modu kapali)",
                     data["counts"]["outline_walls"] > 0
                     and data["counts"]["line_walls"] == 0, data["counts"])
        ok &= _check("Butun duvarlarda olculen kalinlik var",
                     all(w["thickness_ft"] for w in data["walls"]))
        ok &= _check("Olcu katmani duvara donusmedi",
                     not any(w["layer"] == "Olcu" for w in data["walls"]))
        ok &= _check("Orijine yakin cizimde 'uzak' bayragi kalkmiyor",
                     not data["far_from_origin"], data["distance_from_origin_ft"])

        print("6) prepare_wall_input (--lines geri donus modu)")
        with_lines = prepare(dxf_path, tmp_path, units="auto", include_lines=True)
        ok &= _check("Tek cizgi modunda olcu cizgisi de duvar oldu",
                     any(w["layer"] == "Olcu" for w in with_lines["walls"]),
                     with_lines["counts"])

        print("7) prepare_wall_input (orijine tasima)")
        recentered = prepare(dxf_path, tmp_path, units="auto", recenter=True)
        box = recentered["bbox_ft"]
        ok &= _check("Tasima sonrasi merkez orijinde",
                     _approx((box[0] + box[2]) / 2, 0.0, 0.01)
                     and _approx((box[1] + box[3]) / 2, 0.0, 0.01), box)

        print("8) elle birim secimi ve yanlis birim korumasi")
        as_mm = prepare(dxf_path, tmp_path, units="mm")
        ok &= _check("--units mm (dogru birim) duvarlari buluyor",
                     as_mm["counts"]["outline_walls"] > 0, as_mm["counts"])
        ok &= _check("Dis duvar cevresi 8+6+8+6 = 28 m civari",
                     _approx(sum(w["length_ft"] for w in as_mm["walls"]
                                 if w["layer"] == "Duvar") / FT, 28.0 + 3.0 + 2.0, 0.5),
                     sum(w["length_ft"] for w in as_mm["walls"]
                         if w["layer"] == "Duvar") / FT)
        # Yanlis birim seciminde kalinlik makul duvar araliginin disina
        # cikar (200 mm -> 200 m) ve hicbir dis hat duvar sayilmaz. Bu,
        # sessizce 1000 kat buyuk duvar uretmekten cok daha iyi bir
        # basarisizlik bicimi -- ozellikle test edilir.
        as_meters = prepare(dxf_path, tmp_path, units="m")
        ok &= _check("--units m (yanlis birim) sessizce dev duvar uretmiyor",
                     as_meters["counts"]["outline_walls"] == 0, as_meters["counts"])
        ok &= _check("Yanlis birimde kullaniciya uyari veriliyor",
                     any("duvar" in w.lower() for w in as_meters["warnings"]),
                     as_meters["warnings"])

    print("\n{}".format("TUM TESTLER GECTI" if ok else "BAZI TESTLER BASARISIZ"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
