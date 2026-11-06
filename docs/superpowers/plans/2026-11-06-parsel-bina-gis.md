# Parsel/Bina GIS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yeni **Parsel/Bina GIS** butonu: adres veya CaPaKey → SPW geoportal verisi → mevcut Parsel/Bina Aktar butonuyla aynı seçimler ve aynı `revit_input.json` biçimiyle Revit çizimi.

**Architecture:** CPython alt süreç (`pysrc/parsel_gis/`) servisleri sorgular, geometriyi kırpar/tekilleştirir, mevcut biçimde `revit_input.json` + önizleme yazar. IronPython buton (`ParselBinaGIS.pushbutton`) girdileri toplar, alt süreci `run_python` ile çalıştırır, JSON'u yeni `lib/pykalfa/parsel_draw.py` ile çizer. Mevcut buton dokunulmadan kalır.

**Tech Stack:** pyRevit / IronPython 2.7 (buton), CPython 3.14 `C:\pyKalfa\env` (stdlib `urllib`, shapely 2.1, numpy, opencv), ArcGIS REST (SPW), ICAR geocodeWS.

**Spec:** `docs/superpowers/specs/2026-11-06-parsel-gis-design.md`

## Global Constraints

- Yalnız Valonya. Servis kökü `SPW = "https://geoservices.wallonie.be/arcgis/rest/services/"`, geocode `https://geoservices.wallonie.be/geocodeWS`.
- Parsel katmanı `SPW + "PLAN_REGLEMENT/CADMAP_PARCELLES/MapServer/0"`, bina katmanı `SPW + "TOPOGRAPHIE/PICC_VDIFF/MapServer/11"`, SR her yerde `31370`.
- CaPaKey kalıbı `^\d{5}[A-Z_]\d{4}/\d{2}[A-Z0-9_]\d{3}$` (önce `strip().upper()`).
- Adres → parsel arama mesafesi **20 m**; aday sayısı en fazla **5**; pay varsayılanı **30 m**.
- Orijin = çerçevenin sol-alt köşesi, X sağa, Y yukarı, birim feet (`m / 0.3048`), mevcut butonla aynı.
- `revit_input.json` anahtarları mevcut butonla aynı: `parcel_lines`, `frame_lines`, `buildings[].vertices_ft`, `labels[] {text, position_ft, rotation_deg}`, `north {position_ft, rotation_deg}`.
- Yeni pip bağımlılığı yok; `requirements.txt`, `bootstrap`, installer değişmez. Mevcut `ImportGeometry.pushbutton` ve `pysrc/parsel_bina/` değişmez.
- Seçim sırası/başlıkları/"Cerceve cizme"/"Kuzey oku ekleme" mevcut butonla aynı. Bekleme ortasında soru yok.
- Parsel geometrisi kalıcı saklanmaz: `revit_input.json` başarıdan sonra silinir, önizleme PNG kalır.
- Testler projenin `selftest.py` tarzında (pytest yok): `C:\pyKalfa\env\Scripts\python.exe pysrc/parsel_gis/selftest.py`, çevrimdışı, sahte transport ile.

## Review Focus

1. Sokak üstüne düşen adres noktası → 20 m içindeki **en yakın** parsel seçilmeli, "parsel yok" değil (Task 1 `test_parcel_by_point_picks_nearest`).
2. Servis hata JSON'u / zaman aşımı → anlaşılır Türkçe mesaj, sıfırdan farklı çıkış kodu, hiçbir şey çizilmez (Task 1 `test_error_json_raises`, Task 3 `test_prepare_upstream_error_exit_code`).
3. Kırpınca ikiye bölünen bina (MultiPolygon) → her parça ayrı FilledRegion, hiçbiri kaybolmamalı (Task 2 `test_building_split_by_frame`).
4. Aksanlı adres (`Rue de l'Église`) → URL kodlaması ve UTF-8 JSON dosyası bozulmadan Revit listesine ulaşmalı (Task 3 `test_suggest_cli_utf8`).
5. Pay büyükken servis `exceededTransferLimit` döner → sayfalama ile tüm parseller gelmeli (Task 1 `test_query_box_paginates`).

---

## File Structure

| Dosya | Sorumluluk |
| --- | --- |
| `pysrc/parsel_gis/http.py` | JSON GET/POST, yeniden deneme, `UpstreamError`, testte değiştirilebilir transport |
| `pysrc/parsel_gis/services.py` | Sabitler, CaPaKey, adres önerisi, parsel/bina sorguları, `parcel_numero` |
| `pysrc/parsel_gis/layout.py` | Saf geometri: çerçeve, yerel ft, parsel segmentleri, binalar, etiketler, kuzey |
| `pysrc/parsel_gis/preview.py` | ft koordinatlarından doğrulama PNG'si |
| `pysrc/parsel_gis/prepare_gis_input.py` | CLI: parsel çöz → sorgula → `revit_input.json` + önizleme |
| `pysrc/parsel_gis/suggest_cli.py` | CLI: metin → `gis_suggest.json` |
| `pysrc/parsel_gis/selftest.py` | Çevrimdışı testler + `--live` duman testi |
| `lib/pykalfa/parsel_draw.py` | IronPython: `revit_input.json` → DetailCurve/FilledRegion/TextNote/kuzey oku |
| `pyKalfa.tab/ParselBina.panel/ParselBinaGIS.pushbutton/{script.py,bundle.yaml,icon.png}` | Buton akışı |
| `README.md`, `README.en.md`, `README.fr.md` | Özellik tablosu + Kullanım |

`pysrc/parsel_gis/` modülleri birbirini mevcut `pysrc/parsel_bina` gibi düz `import services` ile alır (script klasörü `sys.path`'te).

---

### Task 1: HTTP + servis katmanı

**Files:**
- Create: `pysrc/parsel_gis/http.py`, `pysrc/parsel_gis/services.py`, `pysrc/parsel_gis/selftest.py`

**Interfaces:**
- Produces (`http.py`):
  - `class UpstreamError(Exception)`
  - `TIMEOUT = 45`, `QUERY_TIMEOUT = 10`
  - `get_json(url: str, params: dict, post: bool = False, timeout: float = TIMEOUT, retries: int = 2) -> dict` — `f=json` yoksa ekler; ağ hatası/geçersiz JSON/yanıtta `"error"` anahtarı → `UpstreamError`.
  - `set_transport(fn: Callable[[str, dict, bool, float], dict] | None) -> None` — test için; `None` gerçek `urllib`'e döner.
- Produces (`services.py`):
  - `SPW`, `GEOCODE_WS`, `CADMAP_LAYER`, `PICC_LAYER`, `CAPAKEY_RE`, `ADDRESS_SEARCH_M = 20`, `PARCEL_FIELDS` (planpack `client.py:326` ile aynı)
  - `is_capakey(text: str) -> bool`; `normalise_capakey(text: str) -> str` (geçersizde `ValueError`)
  - `suggest(q: str, limit: int = 5) -> list[dict]` — her öğe `{"label": str, "x": float, "y": float, "precision": "house"|"address-point"|"street-bbox-centre"}`; planpack `client.suggest` mantığı (iki uç, etiket tekilleştirme `re.sub(r"\W+", " ", label.lower()).strip()`), lon/lat yok.
  - `parcel_by_capakey(ck: str) -> dict | None`; `parcel_by_point(x: float, y: float, search_m: float = 0) -> dict | None` — öğe `{"capakey": str, "attributes": dict, "rings": list}`; birden çok sonuçta noktaya en yakın.
  - `parcels_in_box(box: tuple[float, float, float, float]) -> list[dict]` (aynı öğe biçimi); `buildings_in_box(box) -> list[dict]` → `{"id", "nature", "rings"}`. İkisi de `resultOffset` ile `exceededTransferLimit` bitene dek sayfalar, en fazla 10 sayfa.
  - `parcel_numero(attrs: dict) -> str` — planpack `analysis.parcel_numero` birebir.

- [ ] **Step 1: Write the failing tests** in `selftest.py` (her test bir fonksiyon; `main()` hepsini sırayla çalıştırır, sonunda `OK n test` basar, ilk hatada sıfırdan farklı çıkar; sahte transport `(url, params, post, timeout) -> dict` cevapları sözlükten seçer ve çağrıları kaydeder)

```python
def test_capakey_detection():
    assert services.is_capakey(" 92053d0515/00b002 ")
    assert services.normalise_capakey(" 92053d0515/00b002 ") == "92053D0515/00B002"
    assert not services.is_capakey("Rue du Parc 4, 4577 Modave")

def test_parcel_numero():
    assert services.parcel_numero({"RADICAL": "0515", "BIS": "00", "EXPOSANT": "B", "PUISSANCE": "002"}) == "515B2"
    assert services.parcel_numero({"RADICAL": "0038", "BIS": "00", "EXPOSANT": "F", "PUISSANCE": "000"}) == "38F"
    assert services.parcel_numero({"RADICAL": "0012", "BIS": "02", "EXPOSANT": "_", "PUISSANCE": "000"}) == "12/2"

def test_suggest_merges_and_dedupes():
    # /geocode: 1 house aday "Rue du Parc 4, 4577 Modave"; /searchAll: level 4 aynı ad + level 3 sokak
    out = services.suggest("rue du parc 4 modave")
    assert [s["precision"] for s in out] == ["house", "street-bbox-centre"]
    assert len(out) <= 5 and all(set(s) == {"label", "x", "y", "precision"} for s in out)

def test_parcel_by_point_picks_nearest():
    # nokta (100,100), search_m=20; iki parsel: biri 15 m, biri 5 m uzakta
    p = services.parcel_by_point(100, 100, 20)
    assert p["capakey"] == "NEAR"
    assert last_call_params()["distance"] == 20

def test_query_box_paginates():
    # ilk sayfa exceededTransferLimit=True + 2 feature, ikinci sayfa 1 feature
    assert len(services.parcels_in_box((0, 0, 50, 50))) == 3
    assert calls_to(services.CADMAP_LAYER)[1]["resultOffset"] == 2

def test_error_json_raises():
    # transport {"error": {"code": 500, "message": "x"}} döner
    try:
        services.parcel_by_capakey("92053D0515/00B002"); assert False
    except http.UpstreamError:
        pass
```

- [ ] **Step 2: Run to verify failure**

Run: `C:\pyKalfa\env\Scripts\python.exe pysrc/parsel_gis/selftest.py`
Expected: `ModuleNotFoundError: No module named 'services'` (veya `http`)

- [ ] **Step 3: Implement `http.py`** — `urllib.request`, GET için `urlencode` query, POST için form body; `retries` kadar tekrar, sonra `UpstreamError("<url host> yanit vermedi: ...")`. Gerçek ağda User-Agent `pyKalfa`.

- [ ] **Step 4: Implement `services.py`** with the Interfaces above. Envelope query parametreleri: `geometry="xmin,ymin,xmax,ymax"` (2 ondalık), `geometryType=esriGeometryEnvelope`, `inSR=outSR=31370`, `spatialRel=esriSpatialRelIntersects`, `returnGeometry=true`, `geometryPrecision=2`, `timeout=QUERY_TIMEOUT`. Point query planpack `parcel_by_point` ile aynı (`distance`, `units=esriSRUnit_Meter` yalnız `search_m>0`). Geometrisiz/halkasız feature'lar atılır; halka koordinatları sayı ve `0 ≤ x ≤ 400000, 0 ≤ y ≤ 300000` değilse atılır.

- [ ] **Step 5: Run tests** — same command. Expected: `OK 6 test`

- [ ] **Step 6: Commit**

```bash
git add pysrc/parsel_gis/http.py pysrc/parsel_gis/services.py pysrc/parsel_gis/selftest.py
git commit -m "feat(parsel_gis): SPW/ICAR servis katmani"
```

---

### Task 2: Geometri yerleşimi (`layout.py`)

**Files:**
- Create: `pysrc/parsel_gis/layout.py`
- Modify: `pysrc/parsel_gis/selftest.py` (testler eklenir)

**Interfaces:**
- Consumes: Task 1 öğe biçimleri (`rings` = Esri halka listesi, EPSG:31370 metre).
- Produces:
  - `FEET_PER_METER = 1 / 0.3048`, `MIN_LABEL_AREA_M2 = 20.0`, `NORTH_INSET_M = 5.0`, `SNAP_M = 0.01`, `MAX_MARGIN_M = 200.0`
  - `rings_to_geom(rings: list) -> shapely Polygon | MultiPolygon` (Esri halkaları: dış halka + içindeki delikler; `make_valid`)
  - `frame_box(rings: list, margin_m: float) -> tuple[float, float, float, float]` — parselin sınır kutusu ± pay
  - `to_local_ft(x: float, y: float, box) -> list[float]` — `[(x-xmin)*F, (y-ymin)*F]`, 3 ondalık
  - `frame_lines(box) -> list[list[list[float]]]` — 4 segment, `(0,0)`'dan saat yönü tersine (mevcut `_image_frame_lines` sırası)
  - `parcel_segments(parcels: list[dict], box) -> list[list[list[float]]]`
  - `building_regions(buildings: list[dict], box) -> list[dict]` → `{"id": int, "vertices_ft": [[x,y],...], "area_m2": float}` (kapanış noktası tekrar edilmez)
  - `parcel_labels(parcels: list[dict], box) -> list[dict]` → `{"id", "text", "capakey", "position_ft", "rotation_deg": 0.0}`
  - `north_record(box) -> dict` → `{"position_ft": to_local_ft(xmax-5, ymax-5), "rotation_deg": 0.0}`

Ortak sınır algoritması (signature'ın belirlemediği kısım):

```python
lines = [shapely.set_precision(rings_to_geom(p["rings"]).boundary, SNAP_M) for p in parcels]
merged = shapely.unary_union(lines)                 # çakışan kenarları tekilleştirir, düğümler
inside = merged.intersection(shapely.box(*box))     # çerçeve DIŞI atılır, çerçeve kenarı eklenmez
# inside'taki her LineString'in ardışık nokta çiftleri -> segment (ft), < 0.01 m olanlar atılır
```

- [ ] **Step 1: Write the failing tests** (sentetik kareler, metre; `box` hesapları elle)

```python
def test_frame_box_and_origin():
    sq = {"rings": [[[100,100],[120,100],[120,130],[100,130],[100,100]]]}
    box = layout.frame_box(sq["rings"], 30)
    assert box == (70, 70, 150, 160)
    assert layout.to_local_ft(70, 70, box) == [0.0, 0.0]
    assert layout.frame_lines(box)[0] == [[0.0, 0.0], [round(80/0.3048, 3), 0.0]]

def test_shared_edge_drawn_once():
    a = {"rings": [[[0,0],[10,0],[10,10],[0,10],[0,0]]], "attributes": {}}
    b = {"rings": [[[10,0],[20,0],[20,10],[10,10],[10,0]]], "attributes": {}}
    segs = layout.parcel_segments([a, b], (-5, -5, 25, 15))
    total_m = sum(math.dist(*s) for s in segs) * 0.3048
    assert abs(total_m - 70.0) < 0.01          # 2 kare = 80 m çevre, ortak 10 m tek sayılır

def test_segments_clipped_to_frame():
    big = {"rings": [[[0,0],[100,0],[100,100],[0,100],[0,0]]], "attributes": {}}
    segs = layout.parcel_segments([big], (50, -10, 150, 50))
    assert all(0 <= v <= round(100/0.3048, 3) + 1e-6 for s in segs for p in s for v in p)
    # çerçeve içinde kalan: x=100 kenarının y∈[0,50] kısmı + y=0 kenarının x∈[50,100] kısmı = 100 m
    assert abs(sum(math.dist(*s) for s in segs) * 0.3048 - 100.0) < 0.01

def test_building_split_by_frame():
    u = {"id": 1, "rings": [[[0,0],[30,0],[30,30],[20,30],[20,10],[10,10],[10,30],[0,30],[0,0]]]}
    regions = layout.building_regions([u], (-5, 15, 35, 40))   # U'nun iki kolu ayrı kalır
    assert len(regions) == 2 and all(len(r["vertices_ft"]) >= 3 for r in regions)

def test_labels_skip_tiny_and_use_numero():
    p = {"rings": [[[0,0],[10,0],[10,10],[0,10],[0,0]]], "capakey": "X",
         "attributes": {"RADICAL": "0568", "BIS": "00", "EXPOSANT": "C", "PUISSANCE": "000"}}
    assert layout.parcel_labels([p], (-5, -5, 15, 15))[0]["text"] == "568C"
    assert layout.parcel_labels([p], (8, 8, 30, 30)) == []    # çerçeve içinde 4 m² < 20 m²

def test_north_top_right():
    n = layout.north_record((0, 0, 100, 50))
    assert n == {"position_ft": [round(95/0.3048, 3), round(45/0.3048, 3)], "rotation_deg": 0.0}
```

- [ ] **Step 2: Run to verify failure** — `C:\pyKalfa\env\Scripts\python.exe pysrc/parsel_gis/selftest.py` → `No module named 'layout'`

- [ ] **Step 3: Implement `layout.py`** per Interfaces. `building_regions`: her bina `intersection(box)`, `Polygon`/`MultiPolygon` parçalarının yalnız **dış** halkası (mevcut buton tek loop çiziyor), alanı `< 0.5 m²` parça atılır, ardışık 0.01 m'den yakın noktalar birleştirilir. `parcel_labels`: `parcel_numero` Task 1'den (`services.parcel_numero`), konum `clipped.representative_point()`.

- [ ] **Step 4: Run tests** → `OK 12 test`

- [ ] **Step 5: Commit**

```bash
git add pysrc/parsel_gis/layout.py pysrc/parsel_gis/selftest.py
git commit -m "feat(parsel_gis): cerceve, kirpma ve ortak sinir tekillestirme"
```

---

### Task 3: CLI'ler + önizleme

**Files:**
- Create: `pysrc/parsel_gis/prepare_gis_input.py`, `pysrc/parsel_gis/suggest_cli.py`, `pysrc/parsel_gis/preview.py`
- Modify: `pysrc/parsel_gis/selftest.py`

**Interfaces:**
- Consumes: Task 1 `services.*`, `http.UpstreamError`; Task 2 `layout.*`.
- Produces:
  - `suggest_cli.py --query TEXT --output PATH` → UTF-8 `{"query": str, "candidates": [suggest öğeleri]}`; çıkış 0; servis hatasında `{"error": str}` + çıkış 2. `--query` CaPaKey kalıbına uyuyorsa adres yerine `parcel_by_capakey` sorulur: bulunursa tek aday `{"label": "CaPaKey {ck} — parsel {numero}", "capakey": ck, "precision": "capakey"}`, bulunmazsa `candidates: []` (parsel yokluğu stil seçimlerinden ÖNCE anlaşılır).
  - `prepare_gis_input.py (--capakey CK | --x X --y Y) --margin M --output-dir DIR [--no-labels]`
    - `prepare(capakey: str|None, x: float|None, y: float|None, margin_m: float, output_dir: Path, labels: bool = True) -> dict` (yazılan JSON'u da döner)
    - stdout: `PROGRESS|yuzde|mesaj` (mevcut `_progress` biçimi, `flush=True`); aşamalar 5 "Parsel aranıyor", 30 "Komşu parseller", 60 "Binalar", 85 "Geometri", 95 "Önizleme", 100 "Tamamlandi"
    - Çıkış kodları: 0 başarı; 2 `UpstreamError`; 3 parsel bulunamadı; 4 geçersiz girdi. Hata durumunda son satır `ERROR|<Türkçe mesaj>` ve JSON **yazılmaz**.
    - `revit_input.json` = Global Constraints anahtarları + `"source": "GIS"`, `"margin_m"`, `"selected": {"capakey", "numero"}`, `"parcel_count"`, `"building_count"`, `"label_count"`, `"origin_note"` (orijin = çerçevenin sol-alt köşesi), `"attribution": "Plan parcellaire cadastral © AGDP/SPF Finances, via SPW ; Bâtiments © SPW (PICC_VDIFF)"`. `--no-labels` ise `labels: []`.
  - `preview.render(data: dict) -> np.ndarray` — ft'den px (`px = ft * 0.3048 * 8`, yani 8 px/m, uzun kenar en fazla 2000 px'e ölçeklenir), Y ters, mevcut `parsel_bina/preview.py` renk ve kalınlık sabitleri kopyalanır; seçilen parselin etiketi başka renkte değil (spec: vurgu yok). `revit_input_preview.png` olarak yazılır.
  - `margin_m` `0 < m ≤ layout.MAX_MARGIN_M` değilse çıkış 4.

- [ ] **Step 1: Write the failing tests** (sahte transport, `tempfile.TemporaryDirectory`)

```python
def test_prepare_writes_existing_format():
    data = prepare_gis_input.prepare("92053D0515/00B002", None, None, 30, tmp, labels=True)
    for k in ("parcel_lines", "frame_lines", "buildings", "labels", "north"):
        assert k in data
    assert data["source"] == "GIS" and data["selected"]["numero"] == "515B2"
    assert (tmp / "revit_input.json").is_file() and (tmp / "revit_input_preview.png").is_file()
    assert min(v for s in data["frame_lines"] for p in s for v in p) == 0.0

def test_prepare_from_point_uses_20m():
    prepare_gis_input.prepare(None, 100.0, 100.0, 30, tmp)
    assert first_call_to(services.CADMAP_LAYER)["distance"] == 20

def test_prepare_upstream_error_exit_code():
    # transport her çağrıda UpstreamError; CLI'yi subprocess ile çalıştırmak yerine main(argv) çağrılır
    assert prepare_gis_input.main(["--capakey", "92053D0515/00B002", "--margin", "30", "--output-dir", str(tmp)]) == 2
    assert not (tmp / "revit_input.json").exists()

def test_prepare_not_found_and_bad_margin():
    assert prepare_gis_input.main(["--x", "1", "--y", "1", "--margin", "30", "--output-dir", str(tmp)]) == 3
    assert prepare_gis_input.main(["--capakey", "92053D0515/00B002", "--margin", "500", "--output-dir", str(tmp)]) == 4

def test_suggest_cli_utf8():
    # transport label "Rue de l'Église 3, 4000 Liège" döner
    assert suggest_cli.main(["--query", "rue de l'église 3 liège", "--output", str(tmp / "s.json")]) == 0
    assert json.loads((tmp / "s.json").read_text(encoding="utf-8"))["candidates"][0]["label"].startswith("Rue de l'Église")
    assert "%C3%A9" in recorded_urls()[0] or "église" in recorded_params()[0]["address"]

def test_suggest_cli_capakey_mode():
    assert suggest_cli.main(["--query", "92053d0515/00b002", "--output", str(tmp / "c.json")]) == 0
    c = json.loads((tmp / "c.json").read_text(encoding="utf-8"))["candidates"]
    assert c[0]["capakey"] == "92053D0515/00B002" and c[0]["precision"] == "capakey"
    # transport boş feature listesi dönerse candidates == []
```

(`main(argv: list[str] | None = None) -> int` her iki CLI'de; `if __name__ == "__main__": sys.exit(main())`.)

- [ ] **Step 2: Run to verify failure** → `No module named 'prepare_gis_input'`

- [ ] **Step 3: Implement `preview.py`, `suggest_cli.py`, `prepare_gis_input.py`** per Interfaces. `prepare` akışı: parseli çöz (CaPaKey → `parcel_by_capakey`, nokta → `parcel_by_point(x, y, ADDRESS_SEARCH_M)`) → `frame_box` → `parcels_in_box` → `buildings_in_box` → `layout.*` → JSON + önizleme.

- [ ] **Step 4: Run tests** → `OK 18 test`

- [ ] **Step 5: Add `--live` mode to `selftest.py` and run it** — gerçek servislerle `suggest("Rue du Parc 4 Modave")` ≥ 1 aday ve `prepare("92053D0515/00B002", ..., 30)` en az 1 parsel çizgisi + 1 etiket üretmeli.

Run: `C:\pyKalfa\env\Scripts\python.exe pysrc/parsel_gis/selftest.py --live`
Expected: `LIVE OK` ve `output/revit_input_preview.png` gözle kontrol (komşu parseller, binalar, numaralar, çerçeve). Ağ yoksa bu adımı **atlandı** diye raporla.

- [ ] **Step 6: Commit**

```bash
git add pysrc/parsel_gis/
git commit -m "feat(parsel_gis): prepare/suggest CLI ve onizleme"
```

---

### Task 4: Revit butonu, çizim modülü, README

**Files:**
- Create: `lib/pykalfa/parsel_draw.py`, `pyKalfa.tab/ParselBina.panel/ParselBinaGIS.pushbutton/script.py`, `.../bundle.yaml`, `.../icon.png` (şimdilik `ImportGeometry.pushbutton/icon.png` kopyası)
- Modify: `README.md`, `README.en.md`, `README.fr.md`
- Do NOT modify: `ImportGeometry.pushbutton/`, `pysrc/parsel_bina/`

**Interfaces:**
- Consumes: Task 3 CLI'leri, çıkış kodları, `ERROR|` satırı, JSON anahtarları; mevcut `lib/pykalfa` (`bootstrap.ensure_env`, `paths.output_dir`, `paths.pysrc_script`, `subproc.run_python`, `selectors.*`, `revitutils.require_draftable_view/view_elevation/distance/WarningSwallower`).
- Produces (`parsel_draw.py`, IronPython 2.7):
  - `draw_revit_input(doc, view, data, line_style, frame_style, region_type, text_type, north_symbol, transaction_name) -> dict` — anahtarlar `lines, lines_skipped, frame, frame_skipped, regions, regions_skipped, labels, labels_skipped, north`. Gövde mevcut `ImportGeometry/script.py:303-433` çizim bloğunun aynısı (aynı `MIN_SEGMENT_LENGTH_FT = 0.05`, tek `Transaction`, `WarningSwallower`, hata → `RollBack` + yeniden fırlat). `frame_style`/`text_type`/`north_symbol` `None` olabilir.

Buton akışı (`script.py`), spec "Kullanıcı akışı" sırasıyla:
1. `require_draftable_view` (mevcut mesaj), `bootstrap.ensure_env()`.
2. Döngü: `forms.ask_for_string(prompt="Adres veya CaPaKey girin (ör. Rue du Parc 4, 4577 Modave  /  92053D0515/00B002)", title="Parsel/Bina GIS")`; boş/iptal → çık. Metin ne olursa olsun `suggest_cli.py` çalıştır, `output/gis_suggest.json`'ı `io.open(..., encoding="utf-8")` ile oku; aday yoksa `forms.alert("Adres / CaPaKey bulunamadi: ...")` ve tekrar sor; servis hatasında mesaj + çık.
3. `forms.SelectFromList.show` ile adaylar; öğe metni `"{label}  ({kesinlik})"`, kesinlik Türkçe: house → "bina", address-point → "adres noktasi", street-bbox-centre → "sokak", capakey → "CaPaKey". Tek aday olsa da gösterilir. Seçilen aday `capakey` taşıyorsa `--capakey`, yoksa `--x/--y` ile 6. adıma gidilir.
4. `forms.ask_for_string(default="30", prompt="Parselin etrafinda kac metre alinsin? (ör. 30)", title="Alan")`; `0 < m ≤ 200` değilse uyarı + tekrar sor.
5. Stil seçimleri: `ImportGeometry/script.py:139-180` ile aynı çağrılar, aynı başlıklar, aynı `NO_FRAME_LABEL` / `NO_NORTH_LABEL`. Text note tipi yoksa `--no-labels`.
6. `forms.ProgressBar(title="GIS verisi aliniyor: {value}%")` + mevcut `_on_line`/`_tick` deseni ile `prepare_gis_input.py`. Çıkış ≠ 0 → son `ERROR|` satırının mesajı (yoksa tüm çıktı) ile `forms.alert`, çık.
7. `draw_revit_input(..., transaction_name="pyKalfa: parsel/bina GIS aktarimi")`; hata → mevcut "Islem geri alindi" mesajı.
8. `revit_input.json` ve `gis_suggest.json` silinir; özet: mevcut sayım satırları + `"Parsel: {numero} ({capakey})"` + seçilen adres (varsa) + `"Alan: parsel ± {m} m"` + kuzey oku satırı + doğrulama görseli yolu.

`bundle.yaml`: `title: Parsel/Bina GIS`, tooltip: adres veya CaPaKey ile Valonya geoportalından (SPW) parsel, bina ve parsel numaralarını alıp mevcut Parsel/Bina Aktar ile aynı stillerle çizer; internet gerekir.

- [ ] **Step 1: Implement `parsel_draw.py`, `script.py`, `bundle.yaml`, `icon.png`.** IronPython 2.7 uyumu: f-string yok, `print` fonksiyonu yok, `io.open` UTF-8.

- [ ] **Step 2: Syntax check under Python 2 grammar** — Run: `C:\pyKalfa\env\Scripts\python.exe -c "import ast,sys; [ast.parse(open(p,encoding='utf-8').read(), feature_version=(3,4)) for p in sys.argv[1:]]; print('OK')" lib/pykalfa/parsel_draw.py pyKalfa.tab/ParselBina.panel/ParselBinaGIS.pushbutton/script.py` ve `grep -nE "f\"|f'" ` ile f-string yok. Expected: `OK`, grep boş.

- [ ] **Step 3: Update READMEs** — özellik tablosuna satır (TR: "**Parsel/Bina GIS** | Valonya'da adres veya CaPaKey ile SPW geoportalından parsel sınırlarını, binaları ve parsel numaralarını alıp Parsel/Bina Aktar ile aynı stillerle çizer. OCR ve görsel gerekmez."), "Kullanım" altına adım listesi (akış 1–8'in kullanıcı tarafı); EN/FR aynı içerik o dilde.

- [ ] **Step 4: Manual Revit verification (insan)** — pyRevit Reload; bir plan görünümünde:
  - `92053D0515/00B002`, pay 30 → parsel çizgileri, çerçeve, binalar, numaralar, kuzey oku; Ctrl+Z tek adımda geri alıyor.
  - Aksanlı bir adres (ör. `Place Saint-Lambert, Liège`) → liste aksanları doğru gösteriyor.
  - İnternet kapalıyken → anlaşılır hata, hiçbir şey çizilmiyor.
  - Mevcut **Parsel/Bina Aktar** hâlâ eskisi gibi çalışıyor.
  Sonuçları rapora yaz; Revit erişimi yoksa bu adımı **yapılmadı** diye bildir.

- [ ] **Step 5: Commit**

```bash
git add lib/pykalfa/parsel_draw.py pyKalfa.tab/ParselBina.panel/ParselBinaGIS.pushbutton README.md README.en.md README.fr.md
git commit -m "feat: Parsel/Bina GIS butonu"
```
