# Polycam Rölöve Aktar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yeni **Rölöve Aktar** butonu: Polycam kat planı DXF + CSV + LAZ + GLB → taramaya oturtulmuş, durum etiketli native Revit Level / Wall / kapı-pencere / Opening / Room.

**Architecture:** CPython alt süreç (`pysrc/rolove/`) DXF'ten semantiği okur, GLB'den kat bantlarını, LAZ'dan ölçüyü alır; her katı taramaya 2B rijit hizalar, duvar yüzlerini noktalara oturtur ve `output/rolove_input.json` (feet) + kat başına PNG yazar. IronPython buton (`RoloveAktar.pushbutton`) özet/onay ve tip seçimlerini alır, `lib/pykalfa/rolove/` ile tek `TransactionGroup` içinde elemanları kurar; kararlı id'ler Extensible Storage'da.

**Tech Stack:** pyRevit / IronPython 2.7, Revit 2026 API; CPython 3.14 `C:\pyKalfa\env` (numpy 2.5, ezdxf 1.4, opencv-headless, **yeni:** `laspy[lazrs]`).

**Spec:** `docs/superpowers/specs/2026-11-06-polycam-rolove-design.md`

## Global Constraints

- `pysrc/rolove/` CPython 3.14; `lib/pykalfa/rolove/` ve buton **IronPython 2.7** (f-string, type hint, `pathlib` yok). Kod içi metinler mevcut kod gibi ASCII Türkçe.
- Tek yeni bağımlılık: `requirements.txt`'ye `laspy[lazrs]>=2.5` (cp314 wheel doğrulandı: laspy 2.7.0, lazrs 0.8.2). open3d / scipy / trimesh eklenmez.
- `pysrc/duvar/` ve `DuvarAktar.pushbutton` **değişmez**; `pysrc/duvar` modülleri yalnız import edilir.
- Ara JSON koordinatları **feet** (`FT = 1 / 0.3048`); iç hesaplar metre.
- Yuvarlama: **ölçüler en yakın 0.05 m** (kalınlık, açıklık genişlik/yükseklik, parapet, duvar yüksekliği); **konumlar yuvarlanmaz**; kat kotları **0.01 m**. Yuvarlanmamış ölçülen değer de JSON'da taşınır.
- Z datum: CSV'de `Total livable floor area` en büyük olan katın döşemesi = 0.00. XY = LAZ yerel çerçevesi.
- Durum değerleri tam olarak: `olculdu`, `duzeltildi`, `varsayildi`. Anlamları: `olculdu` = LAZ'dan ölçüldü **veya** Polycam'in ölçtüğü sayı birebir eşleşti (açıklık genişliği, tek değerli CSV yüksekliği); `duzeltildi` = DXF konumu LAZ ile kısmen düzeltildi (tek yüz); `varsayildi` = varsayılan değer, belirsiz eşleşme, aralıklı CSV ya da LAZ ile doğrulanamamış duvar konumu.
- Gerekli girdiler: `<ad>.dxf`, `<ad>.csv`, `<ad>.laz` (georef **olmayan**), `<ad>.glb`; kullanıcı DXF veya kat planı zip'i seçer. Orijinal dosyalar değiştirilmez; zip `output/rolove_src/` altına açılır.
- Alt süreç sırasında soru yok; `PROGRESS|yuzde|mesaj` satırları basılır.
- Performans hedefi: örnek veride hazırlık ≲ 60 s, Revit ≲ 30 s; süreler JSON `stats.timings_s`'e yazılır.
- Testler projenin `selftest.py` tarzında (pytest yok): `C:\pyKalfa\env\Scripts\python.exe pysrc\rolove\selftest.py [--only <grup>]`, çevrimdışı, sentetik fixture'larla. Örnek veri: `C:\Users\cmldk\Desktop\pyKalfa-ext\polycam-exports\P26-041-STEENHOVENSTRAAT INT.dxf` (repoya girmez).

## Review Focus

1. Kardeş dosya eksik (ör. GLB yok, ya da yalnız `georef.laz` var) → hangi Polycam export'unun alınacağını söyleyen mesaj, çıkış kodu 2, hiçbir şey oluşturulmaz (Task 7 `test_prepare_missing_inputs`).
2. Yanlışlıkla georef LAZ (derece koordinatı) verilmesi → reddedilir, açık mesaj (Task 3 `test_load_laz_rejects_georef`).
3. Hizalaması tutmayan bir kat (ör. çok az duvarlı bodrum) → yalnız o kat `alignment.ok=false` ve atlanır, diğer katlar üretilir (Task 7 `test_prepare_skips_unaligned_floor`).
4. Kullanıcının sildiği eleman → yeniden çalıştırmada oluşturulmaz, raporda "silinmis" (Task 8 `test_plan_actions_respects_deleted`).
5. Hiçbir duvara oturmayan açıklık → `rejected[]`'a nedeniyle düşer, çökme yok (Task 6 `test_opening_without_host_rejected`).

---

## File Structure

| Dosya | Sorumluluk |
|---|---|
| `pysrc/rolove/config.py` | Tüm eşik/varsayılanlar, `FT`, `round_dim`, `round_level` |
| `pysrc/rolove/polycam_dxf.py` | Polycam kat planı DXF → kat başına duvar/açıklık/oda (metre, DXF çerçevesi) |
| `pysrc/rolove/polycam_csv.py` | CSV → oda bazında tavan, kapı/pencere ölçüleri, alan |
| `pysrc/rolove/glb_stories.py` | GLB başlık JSON'u → `Story` Z/XY bantları (LAZ çerçevesi) |
| `pysrc/rolove/cloud.py` | LAZ yükleme (float32), bant/dilim seçimi, georef reddi |
| `pysrc/rolove/levels.py` | Kat döşeme/tavan kotu ölçümü |
| `pysrc/rolove/align.py` | DXF katı → tarama 2B rijit hizalama |
| `pysrc/rolove/refine.py` | Duvar yüz uydurma, iç/dış, kalınlık, yükseklik, köşe birleştirme |
| `pysrc/rolove/openings.py` | Açıklık → host duvar, ölçüler (CSV), odalar |
| `pysrc/rolove/prepare_rolove_input.py` | CLI: girdileri bul → hat → `rolove_input.json` + PNG |
| `pysrc/rolove/preview.py` | Kat başına durum renkli PNG |
| `pysrc/rolove/fixtures.py` | Sentetik DXF/CSV/GLB/LAZ üreticileri (testler için) |
| `pysrc/rolove/selftest.py` | `--only` gruplu çevrimdışı testler |
| `lib/pykalfa/rolove/ledger.py` | Saf mantık (Revit import'u yok): yeniden çalıştırma kararları |
| `lib/pykalfa/rolove/storage.py` | Extensible Storage: eleman id etiketi + proje defteri |
| `lib/pykalfa/rolove/params.py` | Görünür proje parametreleri (shared parameter) |
| `lib/pykalfa/rolove/creator.py` | Level/Wall/kapı-pencere/Opening/Room oluşturma, rapor |
| `lib/pykalfa/rolove/ui.py` | Girdi seçimi, özet/onay, kot düzeltme, tip seçimleri, rapor |
| `pyKalfa.tab/Duvar.panel/RoloveAktar.pushbutton/{script.py,bundle.yaml,icon.png}` | Buton akışı |

`pysrc/rolove/` modülleri birbirini düz `import config` ile alır; `pysrc/duvar`'ı kullanan modül başında `sys.path.insert(0, <pysrc/duvar>)` yapar.

---

### Task 1: Config + Polycam DXF okuyucu

**Files:**
- Create: `pysrc/rolove/config.py`, `pysrc/rolove/polycam_dxf.py`, `pysrc/rolove/fixtures.py`, `pysrc/rolove/selftest.py`

**Interfaces:**
- Consumes: `pysrc/duvar/dxf_reader.read_dxf(path) -> ReadResult` (`.polys: list[Poly]`, `Poly.ring()`, `.layer`), `pysrc/duvar/wall_detector.outline_to_centerline(points, feet_per_meter) -> (c1, c2, thickness) | None` (metre için `feet_per_meter=1.0`).
- Produces:
  - `config.py`: `FT: float`, `round_dim(m: float) -> float` (0.05 m), `round_level(m: float) -> float` (0.01 m) ve aşağıdaki görevlerin sabitleri (her görev kendi sabitini buraya ekler).
  - `Seg2 = tuple[tuple[float, float], tuple[float, float]]`
  - `@dataclass DxfWall(floor: int, center: Seg2, thickness: float)` + `faces() -> tuple[Seg2, Seg2]` (merkezden ±t/2).
  - `@dataclass DxfOpening(floor: int, kind: str, center: tuple[float, float], width: float, direction: tuple[float, float])` — `kind ∈ {"door","window","opening"}`.
  - `@dataclass DxfRoom(floor: int, name: str, polygon: list[tuple[float, float]])`
  - `@dataclass FloorLayers(walls: list[DxfWall], openings: list[DxfOpening], rooms: list[DxfRoom])`
  - `@dataclass FloorPlan(floors: dict[int, FloorLayers], insunits: int, warnings: list[str])`
  - `read_floorplan(path: Path) -> FloorPlan`
  - `fixtures.write_polycam_dxf(path, floors: dict[int, dict], offset=(0,0))` — `floors[n] = {"walls": [((x1,y1),(x2,y2),t)], "doors"/"windows"/"openings": [((cx,cy), width, (ux,uy))], "rooms": [(name, polygon)]}`; Polycam katman adlarıyla, duvarlar 7 noktalı flags=0 halka (ilk=son) ve **iki kez** yazılır, açıklıklar 5 noktalı dikdörtgen (kalınlık 0.10), oda adı `Labels-Rooms` MTEXT olarak poligon içine.

- [ ] **Step 1: Write the failing tests** (`selftest.py`, grup `dxf`)

```python
def test_dxf_layers_by_floor(tmp):
    fixtures.write_polycam_dxf(tmp/"p.dxf", {
        2: {"walls": [((0,0),(5,0),0.10), ((5,0),(5,4),0.10)],
            "doors": [((2.5,0),0.90,(1,0))], "windows": [], "openings": [],
            "rooms": [("Living Room 1", [(0,0),(5,0),(5,4),(0,4)])]},
        3: {"walls": [((0,0),(3,0),0.10)], "doors": [], "windows": [((1.5,0),1.20,(1,0))],
            "openings": [], "rooms": []}})
    fp = polycam_dxf.read_floorplan(tmp/"p.dxf")
    check(sorted(fp.floors) == [2, 3])
    check(len(fp.floors[2].walls) == 2)              # iki kez yazilan duvar tekillesir
    w = fp.floors[2].walls[0]
    check(approx(w.thickness, 0.10, 0.002))
    check(approx(seg_len(w.center), 5.0, 0.11))
    d = fp.floors[2].openings[0]
    check(d.kind == "door" and approx(d.width, 0.90, 0.005) and approx(d.center[0], 2.5, 0.01))
    check(fp.floors[3].openings[0].kind == "window")
    check(fp.floors[2].rooms[0].name == "Living Room 1")

def test_dxf_ignores_non_semantic_layers(tmp):
    # Objects-*, Dimensions-*, Compass, Walls-Hatch -> hicbir sey uretmez
```

- [ ] **Step 2: Run to verify fail** — `C:\pyKalfa\env\Scripts\python.exe pysrc\rolove\selftest.py --only dxf` → `ModuleNotFoundError: polycam_dxf`.

- [ ] **Step 3: Implement.** Katman adı `^Polycam-Floor_(\d+)-(Walls|Openings-Doors|Openings-Windows|Openings-Openings|Floors|Labels-Rooms)$` ile ayrıştırılır; diğerleri yok sayılır. Duvarlar: `Poly.is_ring()` olanların `ring()`'i → `outline_to_centerline(..., 1.0)`; tekilleştirme uç noktalar (her iki yön) 0.005 m içinde. Açıklık: 5 noktalı halka → uzun kenar = genişlik, yön = uzun kenar birim vektörü, merkez = köşe ortalaması; 2 noktalı çizgi ve ELLIPSE yok sayılır. Odalar: `Floors` halkaları + `Labels-Rooms` MTEXT (`plain_text()`, ezdxf ile ayrıca okunur) → etiket noktası hangi poligonun içindeyse o ad; adsız poligon `"Oda <n>"`. `$INSUNITS != 6` ise `warnings`'e yazılır ve metreye çevrilir.

- [ ] **Step 4: Run** `... selftest.py --only dxf` → tüm `[OK]`. Ayrıca örnek veride: `C:\pyKalfa\env\Scripts\python.exe -c "import sys; sys.path[:0]=['pysrc/rolove','pysrc/duvar']; import polycam_dxf as p; fp=p.read_floorplan(r'C:\Users\cmldk\Desktop\pyKalfa-ext\polycam-exports\P26-041-STEENHOVENSTRAAT INT.dxf'); print({k:(len(v.walls),len(v.openings),len(v.rooms)) for k,v in fp.floors.items()})"` → 4 kat (1–4), Floor 2 ≈ 25 duvar (50 kopya / 2), ≥ 1 kapı, 8 oda.

- [ ] **Step 5: Commit** — `git add pysrc/rolove && git commit -m "feat(rolove): Polycam kat plani DXF okuyucu"`

---

### Task 2: CSV rapor okuyucu

**Files:**
- Create: `pysrc/rolove/polycam_csv.py`; Modify: `fixtures.py` (`write_polycam_csv`), `selftest.py` (grup `csv`)

**Interfaces:**
- Produces:
  - `@dataclass RoomReport(floor: int, name: str, ceiling_min: float | None, ceiling_max: float | None, doors: list[tuple[float, float]], windows: list[tuple[float, float]], area: float | None)`
  - `@dataclass Report(rooms: dict[tuple[int, str], RoomReport], livable_area_by_floor: dict[int, float], wall_thickness_setting: float | None)`
  - `read_report(path: Path) -> Report`
  - `fixtures.write_polycam_csv(path, rows: list[tuple[str, str, str, str]])` (başlık `Floor,Room,Description,Value`).

- [ ] **Step 1: Failing tests**

```python
def test_csv_parses_rooms(tmp):
    fixtures.write_polycam_csv(tmp/"r.csv", [
        ("Floor 2","Entire Floor","Total livable floor area [m^2]","89.4"),
        ("Floor 2","Living Room 1","Ceiling height [m]","2.5 "),
        ("Floor 4","Bedroom 2","Ceiling height [m]","0.7 - 2.4 "),
        ("Floor 2","Living Room 1","Door dimensions [m]","0.8 x 2.1"),
        ("Floor 2","Living Room 1","Window dimensions [m]","2.6 x 0.9"),
        ("All","Settings","Wall thickness [m] (total wall length: 158.878)","0.100")])
    r = polycam_csv.read_report(tmp/"r.csv")
    lr = r.rooms[(2, "Living Room 1")]
    check(lr.ceiling_min == lr.ceiling_max == 2.5)
    check(lr.doors == [(0.8, 2.1)] and lr.windows == [(2.6, 0.9)])
    b = r.rooms[(4, "Bedroom 2")]
    check((b.ceiling_min, b.ceiling_max) == (0.7, 2.4))
    check(r.livable_area_by_floor[2] == 89.4 and r.wall_thickness_setting == 0.100)
```

- [ ] **Step 2: Run** `--only csv` → FAIL.
- [ ] **Step 3: Implement** with stdlib `csv`; `Description` eşleşmesi önek ile (`startswith("Ceiling height")` "(approx)" varyantını da kapsar); bilinmeyen satırlar yok sayılır.
- [ ] **Step 4: Run** `--only csv` → `[OK]`; örnek CSV'de `livable_area_by_floor == {1: 8.4, 2: 89.4, 3: 56.7, 4: 31.9}`.
- [ ] **Step 5: Commit** — `feat(rolove): Polycam CSV rapor okuyucu`

---

### Task 3: GLB kat bantları, LAZ yükleme, kat kotları

**Files:**
- Create: `pysrc/rolove/glb_stories.py`, `pysrc/rolove/cloud.py`, `pysrc/rolove/levels.py`; Modify: `requirements.txt` (+ `laspy[lazrs]>=2.5`, "rolove (Rolove Aktar)" başlığıyla), `fixtures.py` (`write_story_glb`, `write_laz`, `synthetic_building`), `selftest.py` (grup `cloud`)

**Interfaces:**
- Produces:
  - `@dataclass StoryBand(index: int, name: str, zmin: float, zmax: float, xmin: float, xmax: float, ymin: float, ymax: float)` (LAZ çerçevesi: `laz = (gx, -gz, gy)`)
  - `glb_stories.read_story_bands(path: Path) -> list[StoryBand]` — yalnız 12 bayt başlık + JSON chunk; kök sahnenin `Story <n>` adlı çocukları, mesh accessor `min/max`'larından; `index` ada göre artan.
  - `cloud.GeorefError(Exception)`; `cloud.load_laz(path: Path) -> np.ndarray` (N×3 float32; X/Y aralığı |x|≤180, |y|≤90 ve her iki açıklık < 0.01 ise `GeorefError`)
  - `cloud.in_band(points, zmin, zmax) -> np.ndarray` (boolean maske)
  - `@dataclass LevelMeasure(floor: int, story: int, floor_z: float, ceiling_z: float | None, confidence: float, evidence: dict)`
  - `levels.measure_levels(points: np.ndarray, bands: list[StoryBand], floors: list[int]) -> list[LevelMeasure]` — `floors` artan sırada `bands` ile birebir eşlenir (Floor_N ↔ Story N−1); sayılar farklıysa `ValueError`.
  - `fixtures.synthetic_building(...) -> dict` iki katlı, bilinen döşeme kotları (0.00 ve 2.80), tavanlar, iki yüzü 0.20 m ayrık iç duvar, tek yüzlü dış duvarlar ve bir masa üstü (0.75 m, 1 m²) içeren nokta bulutu + eşleşen DXF/GLB tanımı döndürür; `write_laz(path, pts, georef=False)`, `write_story_glb(path, bands)`.
- Config: `LEVEL_BIN_M = 0.02`, `LEVEL_CELL_M = 0.10`.

- [ ] **Step 1: Failing tests**

```python
def test_story_bands_axis_swap(tmp):   # glTF (x, y, z) -> LAZ (x, -z, y)
    fixtures.write_story_glb(tmp/"s.glb", [("Story 0", (-1,-8.8,-4), (2,-6.8,5))])
    b = glb_stories.read_story_bands(tmp/"s.glb")[0]
    check((b.zmin, b.zmax) == (-8.8, -6.8) and (b.ymin, b.ymax) == (-5, 4))

def test_load_laz_rejects_georef(tmp):
    fixtures.write_laz(tmp/"g.laz", np.array([[5.406, 51.028, 70.0]]*100), georef=True)
    check(raises(cloud.GeorefError, cloud.load_laz, tmp/"g.laz"))

def test_levels_ignore_table(tmp):
    s = fixtures.synthetic_building(tmp)
    lv = levels.measure_levels(s["points"], s["bands"], [1, 2])
    check(approx(lv[0].floor_z, 0.00, 0.02) and approx(lv[1].floor_z, 2.80, 0.02))
    check(approx(lv[0].ceiling_z, 2.50, 0.03))        # masa (0.75) secilmez
```

- [ ] **Step 2: Run** `--only cloud` → FAIL. Önce `C:\pyKalfa\env\Scripts\python.exe -m pip install "laspy[lazrs]>=2.5"`.
- [ ] **Step 3: Implement.** Kat kotu: bant içindeki noktalar `LEVEL_BIN_M` Z kutularına; her kutunun değeri = dolu `LEVEL_CELL_M` XY hücre sayısı (alan vekili — masa/raf küçük alan). Döşeme = bandın alt yarısındaki en büyük değerli kutu; tavan = üst yarısındaki en büyük (yoksa `None`). `confidence` = tepe alanı / bant XY kapsama alanı (0–1); `evidence` = `{"floor_area_m2", "ceiling_area_m2", "points"}`.
- [ ] **Step 4: Run** `--only cloud` → `[OK]`. Örnek veride: `load_laz` süresi yazdırılır (hedef < 10 s), `measure_levels` → 4 kat, artan döşeme kotları, ardışık farklar 1.5–3.5 m.
- [ ] **Step 5: Commit** — `feat(rolove): GLB kat bantlari, LAZ yukleme, kat kotlari`

---

### Task 4: Kat hizalama (DXF → tarama)

**Files:**
- Create: `pysrc/rolove/align.py`; Modify: `selftest.py` (grup `align`), `config.py`

**Interfaces:**
- Consumes: `DxfWall.faces()`, `cloud.in_band`, `LevelMeasure.floor_z`.
- Produces:
  - `@dataclass Transform2D(rot_deg: float, mirror: bool, tx: float, ty: float)` + `apply(xy: np.ndarray | tuple) -> same`, `apply_dir(v) -> v` (önce ayna `y→−y`, sonra dönüş, sonra öteleme).
  - `@dataclass Alignment(floor: int, transform: Transform2D, rms_m: float, support_ratio: float, ok: bool, reason: str)`
  - `align.slice_xy(points, floor_z) -> np.ndarray` (N×2; `floor_z + ALIGN_SLICE = (1.0, 1.6)` arası, `ALIGN_GRID_M` hücrelerinde tekilleştirilmiş)
  - `align.align_floor(floor: int, faces: list[Seg2], slice_pts: np.ndarray) -> Alignment`
- Config: `ALIGN_SLICE = (1.0, 1.6)`, `ALIGN_GRID_M = 0.05`, `ALIGN_ICP_ITERS = 15`, `ALIGN_ICP_MAX_DIST = 0.15`, `ALIGN_MAX_REFINE_DEG = 3.0`, `ALIGN_RMS_MAX = 0.03`, `ALIGN_SUPPORT_MIN = 0.5`, `SUPPORT_DIST_M = 0.03`.

- [ ] **Step 1: Failing tests**

```python
def test_align_recovers_rot_and_shift():
    faces, pts = fixtures.floor_faces_and_slice(rot_deg=90, mirror=False, shift=(10.3, -1.4), noise=0.005)
    a = align.align_floor(2, faces, pts)
    check(a.ok and a.transform.rot_deg % 360 == 90 and not a.transform.mirror)
    check(approx(a.transform.tx, 10.3, 0.01) and approx(a.transform.ty, -1.4, 0.01))
    check(a.rms_m < 0.01)

def test_align_detects_mirror():
    faces, pts = fixtures.floor_faces_and_slice(rot_deg=0, mirror=True, shift=(0, 0), noise=0.005)
    check(align.align_floor(2, faces, pts).transform.mirror)

def test_align_rejects_unrelated_cloud():
    faces, _ = fixtures.floor_faces_and_slice(rot_deg=0, mirror=False, shift=(0,0), noise=0)
    a = align.align_floor(2, faces, np.random.default_rng(1).uniform(-5, 5, (5000, 2)))
    check(not a.ok and a.reason)
```

(`fixtures.floor_faces_and_slice` bu görevde eklenir: L biçimli 6 duvarlı bir kat, faces DXF çerçevesinde, noktalar dönüştürülmüş yüzlerden örneklenmiş.)

- [ ] **Step 2: Run** `--only align` → FAIL.
- [ ] **Step 3: Implement** — algoritma:

```text
8 aday (rot ∈ {0,90,180,270} × mirror ∈ {F,T}):
  yüzleri dönüştür (öteleme yok) → ALIGN_GRID_M ızgarasına rasterle
  dilim noktalarını aynı ızgaraya rasterle
  numpy.fft ile çapraz korelasyon → en iyi öteleme + normalize skor
en iyi skorlu aday → ICP (nokta→en yakın yüz segmenti, ALIGN_ICP_MAX_DIST içi,
  2B Procrustes), toplam ek dönüş ≤ ALIGN_MAX_REFINE_DEG
rms = içerdeki noktaların yüze uzaklık RMS'i
support_ratio = yüzler 5 cm aralıkla örneklenir; SUPPORT_DIST_M içinde ≥ 3 nokta olan örnek oranı
ok = rms ≤ ALIGN_RMS_MAX ve support_ratio ≥ ALIGN_SUPPORT_MIN; değilse reason Türkçe ASCII metin
```

- [ ] **Step 4: Run** `--only align` → `[OK]`. Örnek veride Floor 2: `ok=True`, `rms_m` ve `support_ratio` yazdırılır, süre < 5 s.
- [ ] **Step 5: Commit** — `feat(rolove): DXF katini taramaya 2B rijit hizalama`

---

### Task 5: Duvar iyileştirme, iç/dış, kalınlık, yükseklik, köşeler

**Files:**
- Create: `pysrc/rolove/refine.py`; Modify: `selftest.py` (grup `refine`), `config.py`

**Interfaces:**
- Consumes: `DxfWall`, `DxfRoom`, `Transform2D.apply`, `RoomReport`, `LevelMeasure`.
- Produces:
  - `@dataclass RefinedWall(floor: int, dxf_center: Seg2, side: str, location: str, line: Seg2, outward: tuple[float, float] | None, thickness_dxf: float, measured_thickness: float | None, thickness_group_m: float | None, height: float, height_status: str, status: str, deviation_cm: float, support: int, warnings: list[str])`
    - `side ∈ {"exterior","interior"}`; `location = "interior_face"` (dış: `line` = iç yüz, `outward` = odadan dışa birim normal) veya `"center"` (iç: `line` = eksen, `outward=None`). Tüm koordinatlar tarama çerçevesi, metre.
  - `refine.refine_floor(walls: list[DxfWall], rooms_scan: list[DxfRoom], tf: Transform2D, points: np.ndarray, level: LevelMeasure, report_rooms: list[RoomReport]) -> list[RefinedWall]` (`rooms_scan` önceden `tf` ile dönüştürülmüş)
  - `refine.join_corners(walls: list[RefinedWall], snap_m: float) -> int` (yakalanan uç sayısı)
- Config: `FACE_BAND_M = 0.12`, `FACE_Z_MARGIN_M = 0.30`, `FACE_MIN_POINTS = 200`, `FACE_MIN_COVERAGE = 0.30`, `FACE_TRIM = 0.20`, `MAX_SHIFT_M = 0.10`, `MAX_ROT_DEG = 2.0`, `THICKNESS_RANGE_M = (0.05, 0.60)`, `PARALLEL_DEG = 1.0`, `SIDE_PROBE_M = 0.20`, `CORNER_SNAP_M = 0.15`, `DEFAULT_WALL_HEIGHT_M = 2.50`.

Kurallar (spec'ten):
- Her yüz: tarama çerçevesindeki yüz çizgisinin ±`FACE_BAND_M` bandında, Z ∈ [`floor_z+0.30`, `ceiling_z−0.30`] noktalar → PCA doğru, en kötü `FACE_TRIM` atılıp yeniden uydurma. Yüz "görüldü" = ≥ `FACE_MIN_POINTS` ve uzunluğun ≥ `FACE_MIN_COVERAGE`'ı 5 cm kutularda dolu.
- Düzeltme (yüz ötelemesi > `MAX_SHIFT_M` ya da dönüş > `MAX_ROT_DEG`) uygulanmaz → DXF konumu, `status="varsayildi"`, uyarı.
- İç/dış: orta noktadan ±normal·(t/2+`SIDE_PROBE_M`) iki yoklama; ikisi de bir oda içinde → `interior`, değilse `exterior` (oda tarafı = içeride olan yoklama; hiçbiri değilse daha çok nokta gören taraf).
- `exterior`: iç yüz uydurulduysa `line` = uydurulmuş iç yüz, `duzeltildi`; değilse DXF iç yüzü, `varsayildi`. `measured_thickness=None`.
- `interior`: iki yüz görüldü ve paralel (≤ `PARALLEL_DEG`) ve aralık `THICKNESS_RANGE_M` içinde → `line` = iki yüzün ortası, `measured_thickness` = aralık, `thickness_group_m = round_dim(aralık)`, `olculdu`. Tek yüz → `line` = yüz + normal·(t_dxf/2), `duzeltildi`. Hiç → DXF ekseni, `varsayildi`.
- `deviation_cm` = DXF (dönüştürülmüş) referans çizgi ile son `line`'ın uçlardaki en büyük dik uzaklığı ×100.
- Yükseklik (sırayla ilk uyan): komşu odalardan birinin CSV tavanı aralıklıysa (`ceiling_min != ceiling_max`) → en yüksek `ceiling_max`, `varsayildi`; `level.ceiling_z` varsa → `ceiling_z - floor_z`, `olculdu`; komşu odanın tek değerli CSV tavanı → o değer, `olculdu`; yoksa `DEFAULT_WALL_HEIGHT_M`, `varsayildi`. Sonuç `round_dim`.
- `join_corners`: farklı duvarların uçları `snap_m` içinde ise iki `line`'ın doğru kesişimine taşınır (paralelse ortalama); dış duvarlarda iç yüzler kesişir.

- [ ] **Step 1: Failing tests** (`fixtures.synthetic_building` bu görevde genişletilir: iç duvar gerçek kalınlık 0.20, DXF'te 0.10 ve 4 cm kaydırılmış; bir dış duvarın iç yüzü 3 cm kaydırılmış; bir duvar 25 cm kaydırılmış; `Bedroom 2` odası CSV'de `0.7 - 2.4`)

```python
def test_interior_wall_measured():
    w = interior_wall_of(refined)
    check(w.side == "interior" and w.status == "olculdu")
    check(approx(w.measured_thickness, 0.20, 0.01) and w.thickness_group_m == 0.20)
    check(approx(w.deviation_cm, 4.0, 1.0))

def test_exterior_wall_face_corrected():
    w = exterior_wall_of(refined)
    check(w.location == "interior_face" and w.status == "duzeltildi" and w.outward is not None)
    check(points_room_side(w))            # outward odadan uzaga bakar

def test_large_shift_not_applied():
    check(shifted_wall_of(refined).status == "varsayildi" and shifted_wall_of(refined).warnings)

def test_sloped_ceiling_height_flagged():
    w = wall_next_to_room(refined, "Bedroom 2")    # CSV 0.7 - 2.4
    check(w.height == 2.40 and w.height_status == "varsayildi")

def test_join_corners_closes_gap():
    check(refine.join_corners(walls_with_8cm_gap, 0.15) == 2 and corner_distance(walls_with_8cm_gap) < 1e-6)
```

- [ ] **Step 2: Run** `--only refine` → FAIL.
- [ ] **Step 3: Implement** `refine_floor`, `join_corners` per rules above; noktalar kat bandına göre önceden süzülmüş gelir, duvar başına yakın noktalar 2B ızgara indeksiyle (`FACE_BAND_M` hücre) bulunur — tam bulutta normal/RANSAC yok.
- [ ] **Step 4: Run** `--only refine` → `[OK]`.
- [ ] **Step 5: Commit** — `feat(rolove): duvar yuz uydurma, ic/dis, kalinlik, kose birlestirme`

---

### Task 6: Açıklıklar ve odalar

**Files:**
- Create: `pysrc/rolove/openings.py`; Modify: `selftest.py` (grup `openings`), `config.py`

**Interfaces:**
- Consumes: `DxfOpening`, `RefinedWall`, `RoomReport`, `Transform2D`.
- Produces:
  - `@dataclass OpeningOut(floor: int, kind: str, dxf_center: tuple[float, float], host: int, offset: float, width: float, height: float, sill: float, status: dict)` — `host` = o katın `RefinedWall` listesindeki indeks, `offset` = host `line` başından merkeze metre; `status = {"width": ..., "height": ..., "sill": ...}`.
  - `openings.place_openings(ops: list[DxfOpening], walls: list[RefinedWall], tf: Transform2D, rooms_scan: list[DxfRoom], report_rooms: list[RoomReport]) -> tuple[list[OpeningOut], list[dict]]` (ikinci = `rejected` kayıtları `{"kind","floor","dxf_center","reason"}`)
  - `openings.label_point(polygon) -> tuple[float, float]` (poligon içinde garanti nokta)
- Config: `HOST_TOL_M = 0.05`, `CSV_WIDTH_TOL_M = 0.10`, `DEFAULT_DOOR_HEIGHT_M = 2.10`, `DEFAULT_WINDOW_HEIGHT_M = 1.20`, `DEFAULT_WINDOW_SILL_M = 0.90`, `DEFAULT_OPENING_HEIGHT_M = 2.10`.

Kurallar: host = dönüştürülmüş merkezin dik uzaklığı ≤ t/2 + `HOST_TOL_M` ve izdüşümü duvar içinde olan en yakın duvar; yoksa `rejected` ("host duvar bulunamadi"); açıklık host'tan uzunsa `rejected` ("acıklik duvardan genis"). Genişlik = `round_dim(DXF genişliği)`, `olculdu`. Yükseklik = açıklığa komşu odaların CSV kayıtlarında genişliği `CSV_WIDTH_TOL_M` içinde **tek** en yakın kayıt → `round_dim(h)`, `olculdu`; değilse varsayılan, `varsayildi`. Parapet: pencere `DEFAULT_WINDOW_SILL_M` `varsayildi`, kapı/boşluk 0.0 `olculdu`. Yükseklik host duvar yüksekliğini aşarsa host yüksekliğine kırpılır + uyarı.

- [ ] **Step 1: Failing tests**

```python
def test_door_height_from_csv():
    o = place([door(width=0.80)], csv_doors=[(0.8, 2.1), (2.9, 2.4)])[0][0]
    check(o.height == 2.10 and o.status["height"] == "olculdu" and o.status["width"] == "olculdu")

def test_window_ambiguous_csv_defaults():
    o = place([window(width=1.50)], csv_windows=[(1.5, 1.5), (1.45, 1.3)])[0][0]
    check(o.height == 1.20 and o.status["height"] == "varsayildi" and o.sill == 0.90)

def test_opening_without_host_rejected():
    out, rejected = place([door(width=0.9, center=(50, 50))])
    check(out == [] and rejected[0]["reason"])

def test_label_point_inside_concave():
    check(point_in_polygon(openings.label_point(L_SHAPE), L_SHAPE))
```

- [ ] **Step 2: Run** `--only openings` → FAIL.
- [ ] **Step 3: Implement** per rules.
- [ ] **Step 4: Run** `--only openings` → `[OK]`.
- [ ] **Step 5: Commit** — `feat(rolove): aciklik host eslestirme ve olculer`

---

### Task 7: Hazırlık CLI, JSON şeması v1, önizleme

**Files:**
- Create: `pysrc/rolove/prepare_rolove_input.py`, `pysrc/rolove/preview.py`; Modify: `selftest.py` (grup `prepare`)

**Interfaces:**
- Consumes: Task 1–6'nın tüm `Produces`'ları.
- Produces (Revit tarafının tek sözleşmesi):
  - CLI: `prepare_rolove_input.py --input PATH --output-dir DIR [--csv P --laz P --glb P]`; `--input` = `.dxf` veya `.zip`. Çıkış kodu `0` başarı, `2` eksik girdi (JSON yine yazılır, `missing` dolu), `1` hata (stderr mesajı). `PROGRESS|<0-100>|<mesaj>` satırları.
  - `find_inputs(input_path: Path, out_dir: Path) -> tuple[dict[str, Path], list[dict]]` — zip ise `out_dir/rolove_src/`'a açar; `<kök>.dxf/.csv/.laz/.glb` arar (`<kök> georef.laz` **seçilmez**); eksikler `{"file": "laz", "polycam_export": "Point cloud -> LAS (georef kapali)"}` biçiminde.
  - `stable_id(kind: str, floor: int, pts_m: list[tuple[float, float]]) -> str` = `sha1("kind|floor|" + ";".join(sorted("%.2f,%.2f")))[:12]` — **DXF çerçevesi** koordinatlarıyla.
  - `output/rolove_input.json`:

```text
schema_version: 1
source: {key, files: {dxf|csv|laz|glb: {name, size, mtime}}}
params: {config sabitlerinin tamamı}
z_datum: {floor: <ana kat>, offset_m: <eklenen>}
missing: [], rejected: [{kind, floor, id?, reason}]
alignment: [{floor, rot_deg, mirror, tx_m, ty_m, rms_m, support_ratio, ok, reason}]
levels: [{id, floor, name: "Kat <n> (Scan)", elevation_ft, elevation_m, confidence, ceiling_m}]
walls: [{id, floor, side, location, start_ft, end_ft, outward, thickness_group_cm,
         thickness_dxf_cm, measured_thickness_cm, height_ft, height_m, height_status,
         status, deviation_cm, support, warnings}]
openings: [{id, floor, kind, host_id, offset_ft, width_ft, height_ft, sill_ft,
            width_m, height_m, sill_m, status}]
rooms: [{id, floor, name, label_point_ft, polygon_ft, area_csv_m2}]
thickness_groups: [{cm, count}]
stats: {counts: {...}, status_counts: {...}, timings_s: {...}}
previews: [<png yolu>]
```

  (`*_cm` ve `*_m` ölçüleri `round_dim` sonrası, `levels.elevation_m` `round_level` sonrası; `measured_thickness_cm` yuvarlanmamış; konumlar (`start_ft`, `end_ft`, `polygon_ft`, `label_point_ft`) yuvarlanmaz. `ok=false` katın duvar/açıklık/odası yazılmaz, `rejected`'a "kat hizalanamadi" eklenir. `fixtures.synthetic_building` bu görevde `write_files=True` (p.dxf/csv/laz/glb yazar) ve dönüşte `main_floor` alır.)
  - `preview.render_floor(floor, walls, openings, rooms, path)` — opencv; renk: `olculdu` yeşil, `duzeltildi` turuncu, `varsayildi` kırmızı; açıklıklar mavi.

- [ ] **Step 1: Failing tests**

```python
def test_prepare_end_to_end_synthetic(tmp):
    s = fixtures.synthetic_building(tmp, write_files=True)     # p.dxf/csv/laz/glb
    code = run_cli(["--input", str(tmp/"p.dxf"), "--output-dir", str(tmp/"out")])
    j = json.loads((tmp/"out"/"rolove_input.json").read_text("utf-8"))
    check(code == 0 and j["schema_version"] == 1 and len(j["levels"]) == 2)
    check(all(a["ok"] for a in j["alignment"]) and j["walls"] and j["openings"])
    check(j["z_datum"]["floor"] == s["main_floor"])
    check(len({w["id"] for w in j["walls"]}) == len(j["walls"]))

def test_stable_ids_repeatable(tmp):            # iki kosu -> ayni id kumesi

def test_prepare_missing_inputs(tmp):            # glb silinir -> code 2, missing[0].file == "glb"

def test_prepare_skips_unaligned_floor(tmp):     # 2. katin noktalari silinir -> o kat ok=false, 1. kat duvarlari var

def test_find_inputs_from_zip_ignores_georef(tmp)
```

- [ ] **Step 2: Run** `--only prepare` → FAIL.
- [ ] **Step 3: Implement** — sıra: girdiler → DXF → CSV → GLB bantları → LAZ (bir kez) → kotlar → kat başına: dilim, hizalama, oda dönüşümü, `refine_floor`, `join_corners(CORNER_SNAP_M)`, `place_openings` → Z datum ötelemesi → feet'e çevirme → JSON (UTF-8, `ensure_ascii=False`) → PNG'ler. Her aşama sonunda `PROGRESS` ve `timings_s`.
- [ ] **Step 4: Run** `--only prepare` → `[OK]`; tüm grup: `selftest.py` → tüm `[OK]`.
- [ ] **Step 5: Örnek veri doğrulaması** — `C:\pyKalfa\env\Scripts\python.exe pysrc\rolove\prepare_rolove_input.py --input "C:\Users\cmldk\Desktop\pyKalfa-ext\polycam-exports\P26-041-STEENHOVENSTRAAT INT.dxf" --output-dir output` → çıkış 0; `stats.timings_s` toplamı ≤ 60; 4 kat; en az Floor 2 ve 3 `alignment.ok`; `status_counts` ve PNG'ler göz ile kontrol edilir. Sonuçlar (süreler, RMS'ler, durum dağılımı) commit mesajına yazılır. Hedefler tutmuyorsa durup rapor et — eşikleri sessizce gevşetme.
- [ ] **Step 6: Commit** — `feat(rolove): hazirlik CLI, JSON semasi v1, onizleme`

---

### Task 8: Revit tarafı — defter, Extensible Storage, parametreler

**Files:**
- Create: `lib/pykalfa/rolove/__init__.py`, `lib/pykalfa/rolove/ledger.py`, `lib/pykalfa/rolove/storage.py`, `lib/pykalfa/rolove/params.py`; Modify: `pysrc/rolove/selftest.py` (grup `ledger`: `lib/pykalfa/rolove`'u `sys.path`'e ekleyip yalnız `ledger`'ı import eder)

**Interfaces:**
- Produces:
  - `ledger.plan_actions(item_ids, ledger_items, existing_unique_ids) -> dict` — `ledger_items: {stable_id: unique_id}`; dönüş `{"create": [...], "keep": [...], "deleted": [...]}` (defterde yok → create; defterde var ve eleman var → keep; defterde var, eleman yok → deleted).
  - `ledger.empty() -> dict` = `{"version": 1, "sources": [], "items": {}}`; `ledger.dumps(d) -> str`, `ledger.loads(s) -> dict` (bozuk/boş → `empty()`).
  - `storage.SCHEMA_GUID = "5d0c8b7e-3f41-4a8e-9b6a-7c2f1e9d4a60"` (sabit, değiştirilmez); alanlar `StableId` (eleman) ve `Ledger` (ProjectInformation), ikisi de `String`.
  - `storage.tag(element, stable_id)`, `storage.read_tag(element) -> str | None`, `storage.get_ledger(doc) -> dict`, `storage.set_ledger(doc, d)` (açık transaction içinde çağrılır).
  - `params.ensure_parameters(doc, app) -> dict` — `{"status": "pyKalfa Tarama Durumu", "deviation": "pyKalfa Tarama Sapma cm", "thickness": "pyKalfa Olculen Kalinlik cm"}`; Text / Number / Number; kategoriler Walls, Doors, Windows; instance binding, `GroupTypeId.Data`; geçici shared parameter dosyası `output/pykalfa_rolove_params.txt`, `app.SharedParametersFilename` sonra eski değerine döner; zaten bağlıysa dokunmaz.
  - `params.set_values(element, names, status, deviation_cm, thickness_cm)` (`None` değerler atlanır).

- [ ] **Step 1: Failing tests** (CPython ile, Revit gerekmez)

```python
def test_plan_actions_respects_deleted():
    r = ledger.plan_actions(["a", "b", "c"], {"a": "u1", "b": "u2"}, {"u1"})
    check(r == {"create": ["c"], "keep": ["a"], "deleted": ["b"]})

def test_ledger_roundtrip_and_corrupt():
    check(ledger.loads(ledger.dumps({"version": 1, "sources": ["k"], "items": {"a": "u"}}))["items"] == {"a": "u"})
    check(ledger.loads("not json") == ledger.empty())
```

- [ ] **Step 2: Run** `--only ledger` → FAIL.
- [ ] **Step 3: Implement** `ledger.py` (Python 2.7 + 3 uyumlu, Revit import'u yok), sonra `storage.py` ve `params.py` (Revit 2026 API: `SchemaBuilder`, `Entity`, `ExternalDefinitionCreationOptions(name, SpecTypeId.String.Text | SpecTypeId.Number)`, `doc.ParameterBindings.Insert(defn, InstanceBinding(cats), GroupTypeId.Data)`).
- [ ] **Step 4: Run** `--only ledger` → `[OK]`. Revit'te manuel: boş projede pyRevit konsolundan `storage.set_ledger` → kaydet/kapat/aç → `get_ledger` aynı içeriği döndürür; `ensure_parameters` iki kez çağrılır → parametreler bir kez görünür.
- [ ] **Step 5: Commit** — `feat(rolove): Revit defteri, extensible storage, tarama parametreleri`

---

### Task 9: Revit oluşturucu, buton akışı, README

**Files:**
- Create: `lib/pykalfa/rolove/creator.py`, `lib/pykalfa/rolove/ui.py`, `pyKalfa.tab/Duvar.panel/RoloveAktar.pushbutton/script.py`, `bundle.yaml`, `icon.png` (DuvarAktar ikonundan kopya, builder değiştirebilir); Modify: `README.md`, `README.en.md`, `README.fr.md`

**Interfaces:**
- Consumes: `rolove_input.json` (Task 7), `ledger`/`storage`/`params` (Task 8), `pykalfa.selectors.pick_by_name/pick_wall_type`, `pykalfa.revitutils.WarningSwallower`, `pykalfa.subproc.run_python`, `pykalfa.paths`, `pykalfa.bootstrap.ensure_env`.
- Produces:
  - `creator.Choices` (düz nesne): `exterior_type: WallType`, `group_types: {cm: WallType}`, `door_symbol: FamilySymbol | None`, `window_symbol: FamilySymbol | None` (None = Opening kullan), `level_overrides: {level_id: elevation_m}`.
  - `creator.create_all(doc, app, data, choices) -> creator.Report` — `Report`: `created`, `kept`, `deleted`, `failed` (her biri `{kind, id, reason}` listesi / sayaç).
  - `ui.pick_input() -> str`, `ui.summary_and_confirm(data) -> "create" | "edit"` (iptal → `script.exit()`), `ui.edit_levels(data) -> dict`, `ui.pick_choices(doc, data) -> Choices`, `ui.show_report(report, data, output)`.

Oluşturma kuralları (spec "Revit tarafı"):
- `TransactionGroup("pyKalfa: Rolove Aktar")`; aşama başına `Transaction` (params → levels → walls → openings → rooms → defter), hepsi `WarningSwallower`; aşama hatasında grup `RollBack`, eleman hatası raporlanıp devam. Başarıda `Assimilate`.
- Level: defterde varsa ve duruyorsa onu kullan (kot `level_overrides`'tan güncellenmez — mevcut), yoksa `Level.Create(doc, elevation_ft)` + `Name`; şablon Level'larına dokunulmaz.
- Wall (`location == "interior_face"`): `W = wall_type.Width`; eksen = `line + outward·W/2`; `Wall.Create(doc, Line, typeId, levelId, height_ft, 0.0, False, False)`; `wall.Orientation · outward < 0` ise `wall.Flip()`; sonra `WALL_KEY_REF_PARAM = int(WallLocationLine.FinishFaceInterior)`; doğrulama: `LocationCurve` uçları JSON `line`'a ≤ 1 mm, değilse uyarı. (`"center"`: tip = `group_types[thickness_group_cm]`, yoksa en kalabalık grubun tipi.)
- Kapı/pencere: tip `"Scan {w_cm}x{h_cm}"` (yoksa seçilen symbol'den `Duplicate`); genişlik parametresi sırayla `DOOR_WIDTH`/`WINDOW_WIDTH`, `FAMILY_WIDTH_PARAM`, `FAMILY_ROUGH_WIDTH_PARAM`, ad `Width`/`Breedte`/`Largeur`/`Genislik` (yükseklik aynı kalıpla); bulunamazsa Opening'e düşülür + rapor. `symbol.Activate()`; `NewFamilyInstance(pt, symbol, host, level, StructuralType.NonStructural)`; pencere `INSTANCE_SILL_HEIGHT_PARAM = sill_ft`.
- Opening: `doc.Create.NewOpening(host, p1, p2)`, p1/p2 eksen üzerinde `offset ∓ w/2`, Z = level + sill / + sill + height.
- Room: `doc.Create.NewRoom(level, UV(label_point_ft))`; `Area <= 0` ise silinir + rapor; `Name` = JSON adı.
- Her oluşan elemana `storage.tag` ve (Wall/Door/Window) `params.set_values`; defter `items` + `sources` (JSON `source.key`) güncellenir. Defterde başka bir `source.key` varsa `summary_and_confirm` bunu uyarı olarak gösterir.

Akış (`script.py`, DuvarAktar örüntüsü): `ensure_env` → belge `IsFamilyDocument` ise uyarı + çıkış → `pick_input` → `ProgressBar` + `run_python(prepare, on_line, on_poll)` (ImportGeometry'deki `PROGRESS` ayrıştırma örüntüsü) → çıkış 2 ise `missing` listesini gösterip çık → `summary_and_confirm` (kat kotları, hizalama, sayılar, durum dağılımı, oluşturulacak/korunacak/silinmiş, PNG yolları) → `"edit"` ise `edit_levels` ve özet tekrar → `pick_choices` (dış tip bir kez; her kalınlık grubu `"Ic duvar ~{cm} cm ({n} duvar)"`; kapı ailesi; pencere ailesi; ikisinde de `skip_label="Opening kullan"`) → `create_all` → `show_report`. Başarıda `rolove_input.json` silinir, PNG kalır.

- [ ] **Step 1: Implement** `creator.py`, `ui.py`, buton dosyaları (`bundle.yaml` title `Rolove Aktar`, tooltip: hangi 4 Polycam export'unun gerektiği).
- [ ] **Step 2: Revit 2026'da manuel doğrulama (boş Architectural şablon)** — örnek veriyle butonu çalıştır; beklenen: 4 Level `Kat 1..4 (Scan)` (ana kat 0.00), hizalanan katlarda duvarlar, dış duvarlar iç yüzden dışa kalın, kapı/pencere host'lu, odalar adlı; parametre filtresiyle `varsayildi` duvarlar seçilebilir; toplam Revit süresi ≤ 30 s (rapor).
- [ ] **Step 3: Yeniden çalıştırma doğrulaması** — bir duvar sil, bir duvarı taşı, butonu tekrar çalıştır → silinen gelmez ("silinmis: 1"), taşınan yerinde kalır, yeni eleman 0.
- [ ] **Step 4: README** (TR/EN/FR) özellik tablosu + "Kullanım": Rölöve Aktar ve gerekli export'lar (DXF+CSV kat planı zip'i, georef kapalı LAS, GLTF; Basic plan gerekir).
- [ ] **Step 5: Commit** — `feat(rolove): Rolove Aktar butonu ve Revit olusturucu`
