# Parsel/Bina GIS — tasarım

Tarih: 2026-11-06 · Durum: taslak (onay bekliyor)

## Amaç ve neden

**Parsel/Bina Aktar** butonu parsel ve bina geometrisini kadastro
görüntülerinden (3 PNG + ölçek) çıkarıyor: görüntü işleme, hizalama, OCR.
Valonya'da bu verinin kendisi SPW geoportal servislerinden zaten metre
cinsinden ve hatasız geliyor. Yeni buton **Parsel/Bina GIS**, aynı çizimi
adres ya da CaPaKey'den, veriyi doğrudan servisten alarak yapar.

Kazanç: ölçek sorusu, PNG dışa aktarma, hizalama belirsizliği ve ~%80
doğruluklu OCR ortadan kalkar; parsel numaraları veriden birebir gelir.

## Hedefler

- `pyKalfa.tab/ParselBina.panel/` altında yeni bir **Parsel/Bina GIS** butonu.
- Girdi: tek kutuda **adres veya CaPaKey**. Adres → aday listesi → seçim.
- Seçilen parselin çevresinde, kullanıcının verdiği **metre payı** kadar
  bir dikdörtgen alan içindeki parseller, binalar ve parsel numaraları
  çizilir.
- **Mevcut butonun akışı ve seçimleri aynen korunur** (kullanıcının açık
  isteği): parsel çizgisi Line Style, çerçeve Line Style (veya "Cerceve
  cizme"), bina Filled Region Type, parsel numarası Text Note Type
  (opsiyonel), kuzey oku sembolü (veya "Kuzey oku ekleme"), ilerleme
  çubuğu, tek transaction, sonda özet + doğrulama görseli.

## Hedef dışı

- Valonya dışı (Flandre, Bruxelles) — yalnız Valonya yeterli.
- Mevcut **Parsel/Bina Aktar** butonunun değiştirilmesi veya kaldırılması.
- planpack'e çalışma zamanı bağımlılığı. planpack yalnız **örnek kod**
  kaynağıdır; gereken kod pyKalfa'ya kopyalanıp uyarlanır.
- Yazdıkça öneri veren canlı arama kutusu (özel WPF pencere). Gerekirse
  sonra eklenir.
- Bina yüksekliği (LiDAR ≈R+n), kısıt katmanları, CadGIS yüzölçümü.

## Anti-hedefler (çalışsa bile başarısızlık sayılır)

- Kullanıcının alıştığı seçim sırası veya seçim seçeneklerinin değişmesi.
- Çizimin, mevcut butonun çıktısından belirgin biçimde farklı görünmesi
  (ör. çerçeve dışına taşan komşu parseller).
- Revit'te dev koordinatlar (Lambert 72 ≈ 200 000 m) — çizim görünüm
  orijininden km'lerce uzağa düşmemeli.
- Bekleme ortasında kullanıcıya soru sorulması.

## Kullanıcı akışı

1. Aktif görünüm kontrolü (mevcut `require_draftable_view`, aynı mesaj).
2. **Arama:** `forms.ask_for_string` ile tek kutu, istem: adres veya
   CaPaKey. Metin CaPaKey kalıbına uyuyorsa (`^\d{5}[A-Z_]\d{4}/\d{2}[A-Z0-9_]\d{3}$`,
   büyük harfe çevrilip boşlukları kırpılarak) doğrudan parsel aranır;
   uymuyorsa adres araması yapılır.
3. **Adres adayları:** en fazla 5 aday `forms.SelectFromList` ile
   gösterilir (etiket + kesinlik: ev / adres noktası / sokak). Sonuç
   yoksa uyarı ve tekrar sorma. Tek aday olsa bile liste gösterilir
   (kullanıcı neyin bulunduğunu görsün).
4. **Pay:** "Parselin etrafında kaç metre?" — varsayılan **30**, pozitif
   sayı olmalı (mevcut ölçek doğrulamasıyla aynı tarz).
5. **Stil seçimleri** — mevcut butonla aynı sıra, aynı başlıklar, aynı
   `selectors` çağrıları, aynı "çizme/ekleme" etiketleri.
6. **Veri çekme** — ilerleme çubuğuyla tek alt süreç (aşağıda).
7. **Çizim** — tek transaction, `WarningSwallower`, mevcut çizim kodu.
8. **Özet** — oluşturulan/atlanan sayıları + seçilen parselin CaPaKey'i ve
   adresi + doğrulama görseli yolu.

Adım 2–3, CaPaKey ya da adres bulunamadığında kullanıcıya tekrar sorulur;
iptal her adımda `script.exit()`.

## Veri kaynakları (planpack'ten kopyalanacak)

Kaynak örnek: `Desktop/planpack/backend/app/gis/client.py`, `chain.py`,
`batiments.py`, `app/analysis.py:parcel_numero`.

| Ne | Servis |
| --- | --- |
| Adres önerisi | ICAR `https://geoservices.wallonie.be/geocodeWS` → `/geocode` (`address`, `geom=true`) ve `/searchAll` (`address`, `bbox=true`); planpack `suggest()` mantığı (birleştir, tekrarları at, ilk 5) |
| Adres → parsel | aday noktası (EPSG:31370) ile `CADMAP_PARCELLES` point query, `distance=20 m` (sokak üstüne düşen geocode için en yakın parsel), planpack `parcel_by_point` |
| CaPaKey → parsel | `CADMAP_PARCELLES/MapServer/0/query` `where CAPAKEY='…'`, planpack `parcel_by_capakey` |
| Alandaki parseller | aynı katman, envelope query (`esriGeometryEnvelope`, `inSR/outSR=31370`) |
| Alandaki binalar | `TOPOGRAPHIE/PICC_VDIFF/MapServer/11` envelope query |
| Parsel numarası | öznitelikler `RADICAL, BIS, EXPOSANT, PUISSANCE` → planpack `parcel_numero` (ör. `515B2`, `38F`) |

SPW kökü planpack `registry.SPW` sabitinden alınır. Tüm istekler kimlik
doğrulamasızdır. Gelen veri güvenilmeyen veri sayılır: sayılar aralık
kontrolünden geçer (Lambert 72 makul sınırları).

## Geometri

- **Alan:** seçilen parselin sınır kutusu, her yönde pay kadar büyütülür.
  Bu dikdörtgen = **çerçeve** (4 segment, `frame_lines`).
- **Kırpma:** komşu parseller ve binalar çerçeveye göre **kırpılır**
  (shapely, zaten `requirements.txt`'de). Kenarı kesilen bina, kırpılmış
  hâliyle FilledRegion olur.
- **Parsel çizgileri:** her ortak sınır **tek kez** çizilir (mevcut
  çıktıda olduğu gibi; komşu iki parselin ortak kenarı çift DetailLine
  olmamalı). Kırpılmış halkalar segmentlere bölünür, çakışan segmentler
  tekilleştirilir.
- **Parsel numaraları:** her parsel için bir TextNote, poligonun içinde bir
  noktada (ör. shapely `representative_point`), döndürme 0°. Numarası
  çerçeve dışında kalan / kırpılınca çok küçülen parseller etiketlenmez.
- **Seçilen parsel** için ayrıca bir işaretleme yapılmaz (diğerleriyle
  aynı stil).
- **Kuzey oku:** veri kuzey yukarı olduğundan dönüş 0°; konumu mevcut
  butondaki gibi çerçevenin bir köşesine yakın.
- **Koordinatlar:** mevcut butonla aynı kural — orijin **çerçevenin
  sol-alt köşesi**, X sağa, Y yukarı, birim **feet** (`m / 0.3048`).

## Kod yapısı

- `pyKalfa.tab/ParselBina.panel/ParselBinaGIS.pushbutton/` — `script.py`,
  `bundle.yaml`, `icon.png`. IronPython 2.7 uyumlu.
- `pysrc/parsel_gis/` — CPython alt süreç kodu (yalnız stdlib `urllib` +
  shapely). İki giriş noktası:
  - `suggest` — metin → aday listesi JSON (adım 3, hızlı; ilerleme
    çubuğu gerekmez).
  - `prepare` — CaPaKey veya (x, y) + pay → `revit_input.json` +
    `revit_input_preview.png`. `PROGRESS|yuzde|mesaj` satırları basar.
- `revit_input.json` **mevcut butonun biçimini aynen kullanır**
  (`parcel_lines`, `frame_lines`, `buildings[].vertices_ft`, `labels[]`
  `{text, position_ft, rotation_deg}`, `north`), böylece Revit tarafındaki
  çizim kodu yeniden kullanılabilir.
- Revit çizim döngüsü iki butonda ortak olacaksa `lib/pykalfa/` altına
  taşınabilir — bu karar builder'ındır, ama mevcut butonun davranışı
  değişmemeli.
- `bundle.yaml` / panel sırası: yeni buton mevcut butonun yanında.
- README (TR/EN/FR) özellik tablosuna ve "Kullanım" bölümüne Parsel/Bina GIS
  eklenir.

## Kısıtlar

- pyRevit IronPython 2.7 (buton), CPython `env/` (alt süreç).
- `bootstrap.ensure_env()` paylaşılan ortamı kurar; ortam yoksa OCR dahil
  tüm paketler kurulur. Bu davranış değiştirilmez (hedef dışı).
- İnternet bağlantısı gerekir; servis cevap vermezse anlaşılır bir hata
  mesajı ve hiçbir şey çizilmez.
- Parsel geometrisi diske kalıcı yazılmaz; `revit_input.json` başarı
  sonrası silinir (mevcut davranış), önizleme görseli kalır.

## Builder'a bırakılanlar

- Envelope query sayfalama (`maxRecordCount`) ve büyük paylarda üst
  sınır.
- Segment tekilleştirme yöntemi, etiket yerleştirme ayrıntısı.
- Önizleme görselinin görünümü (mevcut `preview.py` örnek alınabilir).
- Hata/yeniden deneme politikası, zaman aşımları (planpack: 45 s genel,
  10 s query).
- Testler (çevrimdışı fixture'larla, mevcut `selftest.py` tarzı).
