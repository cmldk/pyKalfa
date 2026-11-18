# Rölöve Prototip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yeni "Rolove Prototip" butonu: Polycam taramasından toparlanmış (dik köşe, katlar arası hizalı dış duvar), döşemeli, tek bina gibi duran bir prototip model.

**Architecture:** Rölöve Aktar'ın hazırlık hattı (`prepare_rolove_input.prepare`) aynen çalışır; çıkan sözlük CPython'da `prototype.tidy` ile toparlanır ve `prototip_input.json` olarak yazılır. Tip seçimlerinden sonra ikinci, kısa bir CPython çağrısı (`prototype_floors.py`) seçilen dış duvar kalınlığıyla döşeme hatlarını üretir. Revit tarafında Rölöve Aktar oluşturucusu (`creator.create_all`) geriye uyumlu genişletilir: JSON'da `top_floor` olan duvar üst Level'a bağlanır, `floors[]` varsa döşeme aşaması çalışır.

**Tech Stack:** pyRevit IronPython 2.7 (buton, `lib/`), CPython `C:\pyKalfa\env` (numpy, shapely, opencv — hepsi zaten kurulu), Revit 2026 API.

**Spec:** `docs/superpowers/specs/2026-11-18-rolove-prototip-design.md`

## Global Constraints

- Rölöve Aktar'ın davranışı değişmez; mevcut `pysrc/rolove/selftest.py` testleri geçmeye devam eder.
- Yeni ağır bağımlılık yok (shapely/numpy/opencv mevcut).
- IronPython kodu: f-string yok, `io.open(..., encoding="utf-8")`, sayıları argümana `repr(float)`.
- Prototip kararlı id'leri `p-` önekli; Level adları `Kat N (Prototip)`; şerit adı `Rolove Prototip`.
- Eşikler: dikleştirme `A = 5°`, katlar arası dış duvar hizası `D = 15 cm`, köşe yakalama `config.CORNER_SNAP_M` (0.15 m). JSON'a `params.prototype` olarak yazılır.
- Durum/sapma plan konumunu anlatır; yükseklik değişimi yalnız `warnings`'e ("yukseklik: taranan X m -> Level'a bagli").
- Yerinden oynayan duvar: `status = max(eski, "duzeltildi")` (sıra olculdu < duzeltildi < varsayildi), `deviation_cm` = taranmış hattan uç noktalardaki en büyük uzaklık (eski değerden büyükse).
- Döşeme: üst yüzü Level kotunda; duvar üst ofseti = −(döşeme tipi kalınlığı); en üst katın duvarları bağlantısız, taranan yükseklikte.
- Döşeme alanı Level N = ayak izi(N) ∪ ayak izi(N'in hemen altındaki kat); dış duvarların dış yüzüne kadar.
- Çakışma uyarısı yalnız prototip tarafında: defterde `p-` öneki taşımayan canlı eleman varsa.
- Testler: `C:\pyKalfa\env\Scripts\python.exe pysrc\rolove\selftest.py` (grup `proto` için `--only proto`).

## Review Focus

1. Dış duvarları kapalı bir zincir oluşturmayan kat (açık köşe, eksik duvar) → oda poligonlarından döşeme yine çıkar. (Task 2 testi `test_floor_loops_open_chain_uses_rooms`.)
2. Tek katlı tarama → hiçbir duvarda `top_floor` yok, tek döşeme, çökme yok. (Task 1 `test_top_floor_single_floor`.)
3. Hizalanamayıp duvarsız kalan ara kat → alttaki duvarlar yine o katın Level'ına bağlanır (Level oluşur), döşeme o kotta alt katın ayak iziyle. (Task 1 `test_top_floor_uses_levels_not_walls`, Task 2 `test_floor_loops_level_without_walls`.)
4. 5°'den büyük açılı duvar (cumba) → dokunulmaz, komşu köşeler kapanmaya devam eder. (Task 1 `test_orthogonalize_skips_large_angle`.)
5. Host duvarı kısalan açıklık → ofset duvar içinde kalır (yarım genişlik kadar uçlardan içeride). (Task 1 `test_openings_follow_and_clamp`.)

---

### Task 1: Toparlama çekirdeği (`pysrc/rolove/prototype.py`)

**Files:**
- Create: `pysrc/rolove/prototype.py`
- Test: `pysrc/rolove/selftest.py` (grup `proto`)

**Interfaces:**
- Consumes: Rölöve JSON sözlüğü (`prepare_rolove_input.prepare` çıktısı; duvar alanları `id, floor, side, location, start_ft, end_ft, outward, status, deviation_cm, height_m, warnings`; açıklık `host_id, offset_ft, width_ft`; `levels[] {id, floor, name, elevation_m}`; `z_datum.floor`), `refine.join_corners(walls, snap)` (nesnelerde `.line` bekler).
- Produces:
  - `ANGLE_MAX_DEG = 5.0`, `STACK_TOL_M = 0.15`
  - `dominant_angle(walls: list[dict], floor: int) -> float` — radyan, [0, π/2); yalnız `side == "exterior"` duvarlar, uzunluk ağırlıklı, 4θ vektör ortalaması.
  - `orthogonalize(walls, theta, max_deg=ANGLE_MAX_DEG) -> int` — değişen duvar sayısı; her duvar orta noktası etrafında en yakın `theta + k·90°` yönüne döner (fark ≤ max_deg ise).
  - `stack_exterior(walls, main_floor, tol_m=STACK_TOL_M) -> int` — hizalanan duvar sayısı.
  - `top_floors(levels: list[dict]) -> dict[int, int|None]` — her kat için kotça bir üstteki kat.
  - `tidy(doc: dict) -> dict` — sözlüğü yerinde değiştirir ve döndürür; ekler: `doc["prototype"] = {"theta_deg", "orthogonalized", "stacked", "skipped": [wall id], "params": {...}}`, her duvara `top_floor`, `scan_start_ft`, `scan_end_ft`; id'leri `p-` önekler (levels/walls/openings/rooms ve `host_id`), Level adlarını `Kat N (Prototip)` yapar.

- [ ] **Step 1: Testleri yaz** (sentetik dict duvarlar, feet cinsinden; `_pw(floor, a, b, side="exterior", status="olculdu")` yardımcısı)

```python
@test("proto")
def test_dominant_angle_mod90(tmp):
    import prototype as P, math
    ws = [_pw(2, (0, 0), (10, math.tan(math.radians(3)) * 10)), _pw(2, (0, 0), (0, 8))]
    check(approx(math.degrees(P.dominant_angle(ws, 2)), 1.5, 0.6))  # uzunluk agirlikli

@test("proto")
def test_orthogonalize_small_angle(tmp):   # 4° -> 0°, orta nokta yerinde
    ...
    check(n == 1 and approx(abs(dy), 0.0, 1e-9) and approx(mid_after, mid_before, 1e-9))

@test("proto")
def test_orthogonalize_skips_large_angle(tmp):   # 8° ve 30° dokunulmaz
    check(n == 0 and w["start_ft"] == before)

@test("proto")
def test_stack_exterior_snaps_close_parallel(tmp):
    # Kat 2 (ana) y=0, Kat 3 y=0.10 m (feet'e cevrilmis), planda ortusur -> Kat 3 y=0
    check(n == 1 and approx(k3["start_ft"][1], 0.0, 1e-6) and k2 unchanged)

@test("proto")
def test_stack_exterior_keeps_far_and_interior(tmp):
    # 0.30 m uzak dis duvar ve 0.05 m uzak IC duvar dokunulmaz
    check(n == 0)

@test("proto")
def test_tidy_labels_moved_walls(tmp):
    # 4° donen duvar: status olculdu -> duzeltildi, deviation_cm > 0,
    # warnings 'prototip: diklestirildi' icerir; varsayildi olan varsayildi kalir
    ...

@test("proto")
def test_openings_follow_and_clamp(tmp):
    # host 4° donup kose birlesimiyle kisalirsa: aciklik merkezi eski mutlak noktanin
    # izdusumu; offset_ft in [width/2, len-width/2]
    ...

@test("proto")
def test_top_floor_single_floor(tmp):
    check(P.top_floors([{"floor": 1, "elevation_m": 0.0}]) == {1: None})

@test("proto")
def test_top_floor_uses_levels_not_walls(tmp):
    # kotlar -2.04, 0, 3.0, 5.54 -> {1:2, 2:3, 3:4, 4:None}; kat 3'un duvari olmasa da
    ...

@test("proto")
def test_tidy_prefixes_ids_and_names(tmp):
    # her id 'p-' ile baslar, opening host_id duvar id'leriyle eslesir,
    # level adi 'Kat 2 (Prototip)', duvarlarda top_floor ve scan_start_ft var,
    # yukseklik notu: 'yukseklik: taranan 2.45 m' alt kat duvarlarinda (top_floor != None)
    ...
```

- [ ] **Step 2: Çalıştır, başarısız olduğunu gör** — `C:\pyKalfa\env\Scripts\python.exe pysrc\rolove\selftest.py --only proto` → `ModuleNotFoundError: prototype`.

- [ ] **Step 3: `prototype.py`'yi yaz.** Notlar:
  - Dış duvarda hat = taranan iç yüz; döndürme yalnız açıyı değiştirir.
  - `stack_exterior`: dikleştirmeden sonra; iki hat paralel (açı farkı < 1°), dik mesafe ≤ tol, hat boyunca izdüşüm örtüşmesi > 0 → aynı küme (union-find). Küme hattı: ana kattaki üye varsa onun hattı, yoksa uzunluk ağırlıklı ortalama ofset; her üye bu hatta dik öteleme ile taşınır (uzunluğu korunur).
  - Kat başına `refine.join_corners` için `.line` taşıyan ince sarmalayıcı (metre değil feet: snap = `config.CORNER_SNAP_M * config.FT`), sonra hatlar dict'e geri yazılır.
  - Açıklık: toparlamadan ÖNCE mutlak merkezi hesapla, sonra yeni hatta izdüşür, kenetle.
  - Sapma: `max(dist(scan_end, new_line_through))` iki uçta, cm; uç kaymasını değil yanal uzaklığı ölç (köşe uzaması sapma sayılmaz).
- [ ] **Step 4: Testler geçer** — aynı komut, `proto` grubu tümü `[OK]`; tüm suite de geçer.
- [ ] **Step 5: Commit** `feat(rolove): prototip toparlama cekirdegi`

### Task 2: Döşeme hatları (`prototype.floor_loops` + `pysrc/rolove/prototype_floors.py`)

**Files:**
- Modify: `pysrc/rolove/prototype.py`
- Create: `pysrc/rolove/prototype_floors.py`
- Test: `pysrc/rolove/selftest.py` (grup `proto`)

**Interfaces:**
- Consumes: Task 1'in `tidy` çıktısı (`walls[]`, `rooms[]`, `levels[]`, `top_floor`).
- Produces:
  - `footprint(doc, floor: int, exterior_thickness_m: float) -> shapely geometry` — kat ayak izi, dış yüze kadar.
  - `floor_loops(doc, exterior_thickness_m: float) -> list[dict]` — her öğe `{"id": "p-floor-<floor>-<k>", "floor": int, "loops_ft": [[[x, y], ...], ...], "area_m2": float}`; ilk halka dış sınır, sonrakiler delik; k = alan sırası (büyükten küçüğe).
  - CLI: `prototype_floors.py --json <prototip_input.json> --exterior-thickness-m <m> --output <prototip_floors.json>`; çıktı `{"floors": [...], "warnings": [...]}`; çıkış 0 / 1 (hata stderr'de, `HATA:` ile).
- Algoritma (karar): ayak izi = `polygonize` (katın dış duvar iç-yüz hatları, her biri iki uçtan 0.05 m uzatılmış, `unary_union` ile düğümlenmiş) birleşimi; bu poligonların içinde kalmayan (temsil noktası dışarıda) odalar `buffer(+0.15).buffer(-0.15)` kapatılmış oda birleşimiyle eklenir; sonuç `buffer(exterior_thickness_m, join_style=mitre)`. Level N döşemesi = `footprint(N) ∪ footprint(N'in kotça hemen altındaki kat)`; `set_precision(0.001)`, alanı < 0.5 m² parçalar atılır. Duvarsız kat → yalnız oda kapatması; o da boşsa yalnız alt kat izi.

- [ ] **Step 1: Testleri yaz**

```python
@test("proto")
def test_floor_loops_rectangle_to_outer_face(tmp):
    # 10x8 m dikdortgen dis duvar ic yuzu, kalinlik 0.30 -> alan 10.6*8.6, tek halka
    check(len(fl) == 1 and approx(fl[0]["area_m2"], 10.6 * 8.6, 0.05))

@test("proto")
def test_floor_loops_union_with_floor_below(tmp):
    # Kat 2: 12x8, Kat 3: 6x8 (ust uste) -> Kat 3 dosemesi Kat 2 iziyle ayni alan
    ...

@test("proto")
def test_floor_loops_open_chain_uses_rooms(tmp):
    # bir dis duvari eksik kat -> polygonize bos, oda poligonundan doseme cikar
    check(fl and fl[0]["area_m2"] > 0)

@test("proto")
def test_floor_loops_level_without_walls(tmp):
    # Kat 3'un duvari/odasi yok -> Kat 3 dosemesi = Kat 2 izi; hata yok
    ...

@test("proto")
def test_floor_loops_cli(tmp):
    # tidy edilmis kucuk bir JSON yaz, CLI calistir, cikti 0 ve floors dolu
    ...
```

- [ ] **Step 2: Çalıştır, başarısız** — `--only proto` → `AttributeError: floor_loops`.
- [ ] **Step 3: Uygula** (`floor_loops`, `footprint`, CLI).
- [ ] **Step 4: Tüm suite geçer.**
- [ ] **Step 5: Commit** `feat(rolove): prototip doseme hatlari`

### Task 3: Hazırlık giriş noktası ve önizleme

**Files:**
- Create: `pysrc/rolove/prepare_prototype_input.py`
- Modify: `pysrc/rolove/prototype.py` (önizleme fonksiyonu)
- Test: `pysrc/rolove/selftest.py` (grup `proto`)

**Interfaces:**
- Consumes: `prepare_rolove_input.find_inputs`, `prepare_rolove_input.prepare`, Task 1 `tidy`, Task 2 `footprint`.
- Produces:
  - CLI argümanları `prepare_rolove_input.py` ile aynı (`--input --output-dir --csv --laz --glb`); çıktı `<output-dir>/prototip_input.json`; çıkış kodları aynı (0 / 2 eksik girdi / 1 hata); `PROGRESS|%|mesaj` satırları (rölöve hazırlığı 0–90, toparlama 90–100).
  - `render_floor(doc, floor, path) -> Path` (prototype.py içinde): duvarlar duruma göre renkli (preview.STATUS_COLORS), açıklıklar mavi, oda gri, kalınlıksız (0 m) ayak izi kesikli siyah çizgi. Dosya `prototip_preview_kat<N>.png`; `doc["previews"]` bu yollarla değiştirilir (rölöve PNG'leri listeden çıkar).
- [ ] **Step 1: Test** `test_prepare_prototype_end_to_end_synthetic`: `fixtures.synthetic_building(tmp, write_files=True)`, CLI → 0; JSON: tüm id'ler `p-`, `levels` adları `(Prototip)`, Kat 1 duvarlarında `top_floor == 2`, Kat 2'de `None`, `prototype.theta_deg` var, `previews` var ve `prototip_preview_kat` içerir. `test_prepare_prototype_missing_inputs`: yalnız DXF → çıkış 2, JSON `missing` dolu.
- [ ] **Step 2: Başarısız gör.**
- [ ] **Step 3: Uygula.** `prepare` çağrısından dönen kod 0 değilse toparlama yapılmaz, sözlük olduğu gibi yazılır.
- [ ] **Step 4: Tüm suite geçer; örnek veriyle elle çalıştır:** `C:\pyKalfa\env\Scripts\python.exe pysrc\rolove\prepare_prototype_input.py --input "..\polycam-exports\P26-041-STEENHOVENSTRAAT INT.dxf" --output-dir output` (dosya adı klasörde doğrulanır) → çıkış 0; dikleştirilen/hizalanan sayıları ve en büyük sapma not edilir; PNG gözle kontrol; sonra `prototype_floors.py --exterior-thickness-m 0.30` ile döşeme alanları not edilir.
- [ ] **Step 5: Commit** `feat(rolove): prototip hazirlik giris noktasi ve onizleme`

### Task 4: Revit tarafı — oluşturucu genişletmesi, döşeme aşaması, çakışma kontrolü

**Files:**
- Modify: `lib/pykalfa/rolove/creator.py` (`Choices`, `_create_wall`, `create_all`, `preview_plan`)
- Create: `lib/pykalfa/rolove/floors.py`
- Modify: `lib/pykalfa/rolove/ledger.py` (`foreign_items`)
- Create: `lib/pykalfa/rolove/proto_ui.py`
- Test: `pysrc/rolove/selftest.py` (ledger testi; Revit kodu yalnız sözdizimi + elle kontrol listesi)

**Interfaces:**
- Consumes: JSON alanları `walls[].top_floor`, `floors[]` (Task 2 biçimi), `revitutils.WarningSwallowerUnjoin`.
- Produces:
  - `Choices(..., floor_type=None)`; `Choices.floor_thickness_ft` (floor_type'tan; yoksa 0).
  - `_create_wall`: `w.get("top_floor")` dolu, `choices.floor_type` var ve o katın Level'ı `ctx.levels`'ta ise: `WALL_HEIGHT_TYPE` = üst Level Id, `WALL_TOP_OFFSET` = `-floor_thickness_ft`. Değilse eski davranış (bağlantısız, `height_ft`).
  - `floors.stage_floors(ctx)` — `ctx.data["floors"]` her öğe için defter planına göre create/keep/deleted; `Floor.Create(doc, List[CurveLoop], floor_type.Id, level.Id)` (yapısal değil), halka başına `CurveLoop` (`Line.CreateBound`, 1 mm'den kısa kenar atlanır); rapora tür `"floor"`. Aşama transaction'ı `WarningSwallowerUnjoin` ile.
  - `create_all` aşama sırası: parametreler → Level → duvarlar → birleşimler → **döşeme (yalnız `data.get("floors")` doluysa)** → açıklıklar → odalar → defter. Grup adı `data.get("prototype")` varsa `"pyKalfa: Rolove Prototip"`.
  - `preview_plan` id listesine `floors` eklenir.
  - `ledger.foreign_items(items: dict, prefix: str) -> list[str]` — öneki taşımayan anahtarlar.
  - `proto_ui.pick_floor_type(doc) -> FloorType`, `proto_ui.summary_text(data, plan, conflict_count) -> str` (kotlar, toparlama sayıları ve atlanan duvarlar, döşeme açıklaması "kat + alt kat izi; ust kati olmayan kisim duz cati varsayilir", çakışma uyarısı), `proto_ui.summary_and_confirm(data, plan, conflict_count) -> "create"|"edit"` (iptal scripti bitirir), `proto_ui.rolove_conflicts(doc) -> int` (canlı, `p-` önekli olmayan defter öğesi sayısı).
  - `show_report` tür listesine `"floor"` eklenir (rölöveyi etkilemez: sıfır satır).
- [ ] **Step 1: Test** `test_foreign_items` (`{"p-a":1,"abc":2,"p-b":3}` → `["abc"]`). Çalıştır, başarısız gör.
- [ ] **Step 2: `foreign_items`'ı yaz; test geçer.**
- [ ] **Step 3: Revit kodunu yaz.** Revit API adlarını `RevitAPI.xml` (Revit 2026) ile doğrula: `Floor.Create(Document, IList<CurveLoop>, ElementId, ElementId)`, `FloorType.GetCompoundStructure().GetWidth()`, `BuiltInParameter.WALL_HEIGHT_TYPE`, `WALL_TOP_OFFSET`. `WALL_HEIGHT_TYPE` Set'i `Wall.Create`'den sonra, Location Line ayarından sonra.
- [ ] **Step 4: Sözdizimi** — `C:\pyKalfa\env\Scripts\python.exe -m py_compile` IronPython dosyalarında yapılamaz (Revit importları); bunun yerine `python -c "import ast,sys; [ast.parse(open(p,encoding='utf-8').read()) for p in sys.argv[1:]]"` ile ayrıştırma + f-string taraması (`grep -n 'f"' ...` boş). Tüm suite geçer.
- [ ] **Step 5: Commit** `feat(rolove): prototip icin duvar ust kisiti ve doseme asamasi`

### Task 5: Buton, README

**Files:**
- Create: `pyKalfa.tab/Duvar.panel/RolovePrototip.pushbutton/script.py`, `bundle.yaml`, `icon.png` (RoloveAktar ikonundan türetilmiş, aynı boyut)
- Modify: `pyKalfa.tab/Duvar.panel/bundle.yaml` (layout varsa ekle), `README.md`, `README.en.md`, `README.fr.md`

**Interfaces:**
- Consumes: `rolove.ui.pick_inputs`, `rolove.inputs.cli_args`, `ui.show_missing`, `ui.edit_levels`, `ui.pick_choices`, `proto_ui.*`, `creator.create_all/preview_plan`, `run_python`.
- Akış (`RoloveAktar.pushbutton/script.py` kalıbı): belge kontrolü → `pick_inputs` → eski `prototip_input.json`/`prototip_floors.json` silinir → ilerleme çubuğuyla `prepare_prototype_input.py` → eksikse `show_missing` → duvar yoksa uyarı → `summary_and_confirm` (edit → `edit_levels`) → `pick_choices` + `pick_floor_type` → `prototype_floors.py --exterior-thickness-m repr(exterior.Width*0.3048)` (hata → alert, çık) → `data["floors"]` = çıktı → `create_all` → başarıda iki JSON silinir → `show_report`.
- Başlıklar `Rolove Prototip`. Tooltip: rölövenin toparlanmış, döşemeli varsayımsal hali; ince ölçüler sonradan elle; Rölöve Aktar ile aynı projede kullanmayın.
- README (TR/EN/FR): özellik tablosuna satır + "Rölöve Prototip" kullanım bölümü (girdiler Rölöve Aktar ile aynı; neyi toparlar; döşeme/duvar ilişkisi; durum etiketi; ayrı proje önerisi; çatı/merdiven yok).
- [ ] **Step 1: Yaz.** **Step 2:** ast ayrıştırma + f-string taraması; tüm suite geçer. **Step 3: Commit** `feat(rolove): Rolove Prototip butonu`.
- [ ] **Step 4: Elle kontrol listesi kullanıcıya** (Revit): katlar arası boşluk yok; döşeme duvara girmiyor; dış duvarlar katlar arasında hizalı; tek Ctrl+Z; yeniden çalıştırma çoğaltmıyor; Rölöve Aktar aynı.
