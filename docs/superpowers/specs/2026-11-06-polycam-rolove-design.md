# Polycam Rölöve Aktar — tasarım

Tarih: 2026-11-06 · Durum: taslak (onay bekliyor)

## Amaç ve neden

Polycam ile içeriden taranmış bir binadan, **ölçüsüne güvenilebilecek bir
mevcut durum modeli (rölöve)** ya da ona olabildiğince yakın bir sonuç
üretmek. Model Revit'te gerçek elemanlardan oluşur (Level, Wall, kapı/pencere
FamilyInstance, Opening, Room); kullanıcı sonra üzerinde düzenleme/tasarım
yapar.

Polycam'in ücretli Revit çıktısı bir partnerin (Transform Engine) elle yaptığı,
sipariş başına ~$200'lık bir hizmettir. Bu buton aynı işi kullanıcının zaten
aldığı Polycam export'larıyla, pyKalfa içinde yapar.

Temel fikir: **iki kaynak, iki ayrı görev.**

- **Kat planı DXF + CSV = ne ve nerede (semantik/topoloji).** Polycam'in
  RoomPlan tabanlı kat planı duvarları, kapıları, pencereleri, boşlukları ve
  odaları kat kat, metre cinsinden zaten ayırıyor. Bunu nokta bulutundan
  yeniden *bulmaya* çalışmıyoruz.
- **Nokta bulutu (LAZ) = ne kadar doğru (ölçü).** RoomPlan duvarları ideal
  düzlemlerdir ve kalınlığı ölçmez (sabit 0.10 m ayarı). Her duvar, LAZ'daki
  gerçek yüzeye oturtulur; iki yüzü taranmışsa kalınlık ölçülür.

Kullanıcının ilkesi: **gerekli yuvarlamalar yapılır ama veri olabildiğince
bozulmaz.** Gerçek ölçülen değerler her zaman elemanda saklanır.

Kullanım bağlamı (kullanıcı): rölöve **boş bir projeye** gelir ve **mimar
için hızlı bir başlangıç** olarak düşünülür; sonradan elle düzeltmeler
yapılacaktır. Mükemmellik değil, güvenilir ve dürüstçe etiketlenmiş bir
başlangıç modeli hedeflenir.

## Yuvarlama kuralı (kullanıcı)

**Ölçüler en yakın 0 veya 5 cm'ye yuvarlanır** (ör. 9.7 → 10, 12.3 → 10,
13.0 → 15): duvar kalınlıkları, kapı/pencere genişlik-yükseklikleri,
parapet, duvar yükseklikleri. Bu doğrudan kalınlık gruplarını da tanımlar
(grup = yuvarlanmış kalınlık).

**Konumlar yuvarlanmaz** *(benim kararım, "veriyi bozmadan" ilkesinden)*:
duvar uç noktaları ve yüz konumları taramadan geldiği gibi kalır; yalnız
konum çizgisinin ölçüsü değil, yüzün kendisi korunur. Kat kotları 1 cm'ye
yuvarlanır *(benim kararım)*. Yuvarlanmamış ölçülen değer her zaman
parametrede saklanır.

Bu kural ±2.5 cm mertebesinde bir doğruluk beklentisi demektir; bu yüzden
kat başına **tek bir rijit 2B hizalama** yeterli sayılır, kat içi LiDAR
kayması düzeltilmez (yalnız sapma raporlanır) *(benim kararım)*.

## Hedefler

- `pyKalfa.tab/Duvar.panel/` altında yeni bir **Rölöve Aktar** butonu.
- Girdi: kullanıcıdan yalnız gerekli Polycam export'ları istenir (aşağıda).
  Eksik dosya varsa ne export edileceği açıkça söylenir.
- **4 kat** (örnek veride: küçük bodrum Floor 1, ana kat Floor 2, Floor 3,
  eğik tavanlı çatı katı Floor 4). Kat sayısı veriden gelir; sabit kodlanmaz.
- Native **Level**'lar (kotlar taramadan ölçülür, kullanıcı onaylar/düzeltir).
- Native **Wall**'lar, her kat kendi Level'ında:
  - Konum taramaya oturtulmuş (düzeltme sınırlı ve raporlu).
  - **Dış duvarlar:** iç yüz taramadan gelir; kalınlık kullanıcının **bir kez**
    seçtiği duvar tipinden, **dışa doğru** eklenir.
  - **Tek yüzü taranmış her duvar dış duvar sayılır** (komşu/ortak duvar,
    taranmamış mekâna bakan duvar ayrımı yapılmaz — kullanıcı: "evi çizmek
    yeterli").
  - **İç duvarlar:** iki yüz görünüyorsa kalınlık ölçülür ve 0/5 cm'ye
    yuvarlanır; her yuvarlanmış kalınlık bir grup, her grup için
    kullanıcıya bir kez duvar tipi sorulur. İki yüzü olan ama kalınlığı
    ölçülemeyen iç duvarlarda DXF ekseni kalır, kalınlık en kalabalık
    grubun tipinden.
  - Köşeler birleştirilmiş (Revit wall join).
- **Kapı ve pencereler** host duvara FamilyInstance olarak; boyutlar
  veriden. Aile yoksa ya da eşleşmiyorsa **Opening** (dikdörtgen boşluk).
  DXF'teki `Openings-Openings` (kapısız geçişler) doğrudan Opening olur.
- **Room**'lar, Polycam oda adlarıyla.
- **Güven etiketi:** her duvar ve açıklıkta görünür parametreler:
  durum (`ölçüldü` / `düzeltildi` / `varsayıldı`), taramadan sapma (cm),
  ölçülen kalınlık (cm, varsa). Kullanıcı neye güvenip neyi sahada kontrol
  edeceğini modelde filtreleyerek görür.
- **Hızlı:** örnek veri setinde (10 M nokta) tüm işlem normal bir dizüstünde
  **yaklaşık 1 dakikanın altında** (benim hedefim; aşağıda "Performans").
- Yeniden çalıştırma **kullanıcının düzenlemelerini ezmez**: daha önce
  üretilmiş elemanlar (kararlı kimlikle tanınır) yerinde bırakılır, yalnız
  eksikler eklenir, farklar raporlanır. *(benim kararlarım:)*
  - "Yeniden çalıştırma" = **aynı export** tekrar işlenir. Aynı binanın
    yeni bir export'u/taraması ayrı bir aktarım sayılır; projede başka
    kaynaktan önceki bir aktarım varsa önizleme bunu açıkça uyarır.
  - Kullanıcının **sildiği eleman geri gelmez**: üretilen id'lerin kaydı
    projede (Extensible Storage, ProjectInformation) tutulur; kayıtta olup
    modelde olmayan id yeniden oluşturulmaz, raporda "silinmiş" görünür.

## Hedef dışı (ilk sürüm)

- Mobilya, armatür, cihaz (DXF `Objects-*` katmanları), tesisat.
- Çatı, eğik tavan geometrisi, merdiven elemanı.
- Döşeme/tavan plakaları (`Floor.Create`/`Ceiling.Create`). Oda poligonları
  JSON'da taşınır ki sonra eklenebilsin. *(benim kararım)*
- Coğrafi konumlandırma (georef LAZ / Lambert 72, Parsel/Bina GIS ile
  hizalama). Rölöve boş projeye gelir (kullanıcı). Sonraki sürüm adayı.
- Kat içi LiDAR kayma düzeltmesi (parçalı hizalama); yalnız sapma raporlanır.
- Komşu/ortak duvar, taranmamış mekân duvarı gibi duvar sınıfları.
- Nokta bulutundan sıfırdan duvar tespiti (RANSAC, mesh'ten duvar vb.).
- Polycam'in ücretli Revit/AutoCAD hizmetine bağımlılık.
- Mevcut **Duvar Aktar** butonunun davranışını değiştirmek.

## Anti-hedefler (çalışsa bile başarısızlık sayılır)

- Veriyi sessizce "güzelleştirmek": duvarları 90°'ye zorlamak, büyük
  boşlukları kapatmak, sapmayı raporlamadan duvar kaydırmak.
- Varsayılan bir değeri ölçülmüş gibi göstermek (durum etiketi yanlış).
- Yeniden çalıştırınca duvarların çoğalması ya da kullanıcı düzenlemesinin
  ezilmesi.
- Dakikalarca süren, ilerleme göstermeyen bir işlem; işlem ortasında soru.
- Hizalaması tutmayan bir katın yine de modele basılması.

## Girdiler — minimum export seti

Örnek: `Desktop/pyKalfa-ext/polycam-exports/P26-041-STEENHOVENSTRAAT INT.*`

| Dosya | Polycam'de | Ne için | Zorunlu |
|---|---|---|---|
| Kat planı **DXF** (~1.5 MB) | Floor plan → DXF (zip içinde de var) | duvar/açıklık/oda semantiği | evet |
| Kat planı **CSV** (~14 KB) | Floor plan → CSV (zip içinde) | tavan yükseklikleri, kapı/pencere ölçüleri, oda adları/alanları | evet |
| **LAZ** (~100 MB, georef **olmayan**) | Point cloud → LAS | ölçü: kat kotları, duvar yüzleri, kalınlık | evet |
| **GLB** (~36 MB) | Mesh → GLTF | kat ayrımı (`Story 0..3` grupları); yalnız başlık JSON'u okunur | evet |

Gerekmeyenler: PLY ve PTS (aynı 10 M nokta, 3–6 kat büyük), OBJ/FBX/DAE,
georef LAZ, PNG/PDF/SVG, "Blueprint" DXF (`(1).dxf`, yalnız
`Polycam-Blueprint-Lines` katmanı).

Kullanıcı tek dosya seçer (DXF ya da kat planı zip'i); diğerleri **aynı
klasörde aynı ad kökünden** otomatik bulunur (`<ad>.dxf`, `<ad>.csv`,
`<ad>.laz`, `<ad>.glb`; zip açılabilir). Bulunamayan için dosya seçtirilir
veya ne export edileceği söylenir.

## Verinin bilinen yapısı (örnek dosyadan doğrulandı)

**Kat planı DXF** (AC1018, `$INSUNITS = 6` → metre):

- Katmanlar kat başına: `Polycam-Floor_N-Walls`, `-Walls-Hatch`,
  `-Openings-Doors`, `-Openings-Windows`, `-Openings-Openings`, `-Floors`,
  `-Floors-Hatch`, `-Labels-Rooms`, `-Labels-Areas`, `-Labels-Floors`,
  `-Dimensions-*`, `-Objects-*`; ayrıca `Polycam-Compass`.
- Duvarlar: duvar başına bir LWPOLYLINE dış hattı, 7 nokta, **flags = 0
  ama ilk nokta = son nokta** (mevcut `dxf_reader._is_closed` bunu açık
  sayar → Polycam okuyucusunda kapalı kabul edilmeli). Kalınlık 0.10 m
  (CSV: `Wall thickness [m] ... 0.100`, bir Polycam **ayarı**, ölçüm değil).
- Kapı/pencere: duvar kalınlığında 5 noktalı dikdörtgen (genişlik =
  açıklık genişliği) + kapı açılış yayları (ELLIPSE) ve 2 noktalı çizgiler.
- **Katlar paftaya yan yana dizilmiş** — her katın DXF koordinatı farklı
  bir ofsette (Floor_2 duvarları x 10.3–22.8, Floor_3 x 0.2–8.5 / y 11.5–19.8
  …). Yani her kat için DXF → tarama dönüşümü ayrıca bulunmalı.

**CSV** (`Floor,Room,Description,Value`): oda başına `Ceiling height [m]`
(bazen aralık: `0.7 - 2.4`), `Window dimensions [m]` / `Door dimensions [m]`
(`G x Y`, konumsuz, oda bazında), alanlar, adres, enlem/boylam, pusula yönü.

**GLB**: kök düğüm altında `Story 0..3` adlı 4 grup, her biri 13 dokulu mesh
(adsız, elemana göre ayrılmamış). glTF Y-yukarı.

**LAZ** (LAS 1.2, format 2 = RGB, 10 000 000 nokta, sıkıştırılmış): yerel
metre çerçevesi. **GLB ile aynı çerçeve:** `LAZ (x, y, z) = glTF (x, −z, y)`
(sınırlar birebir tutuyor: x −6.21…6.37, z −8.80…1.53). GLB `Story`
gruplarının Z bantları (LAZ çerçevesinde): S0 −8.80…−6.80, S1 −6.97…−3.85,
S2 −3.97…−1.20, S3 −3.72…1.53 (bantlar çakışabiliyor → kat kotu bant
sınırından değil ölçümden alınır).

Polycam `Floor_N` ↔ GLB `Story N−1` eşleşmesi beklenen; doğrulanması
builder'ın işi (ör. alan/sınır karşılaştırması).

## Kullanıcı akışı

1. Belge kontrolü (proje belgesi, aile/şablon değil).
2. DXF veya kat planı zip'i seç; diğer dosyalar otomatik bulunur.
3. **Hazırlık** — tek CPython alt süreci, ilerleme çubuğu (`PROGRESS|%|mesaj`).
   Kullanıcıya soru sorulmaz.
4. **Önizleme ve onay** (tek özet penceresi): kat sayısı ve ölçülen kotlar
   (düzeltilebilir), kat başına hizalama kalitesi, duvar/kapı/pencere/
   boşluk/oda sayıları, durum dağılımı (ölçüldü/düzeltildi/varsayıldı),
   sapması yüksek duvarlar, oluşturulacak/atlanacak sayıları. İptal edilebilir.
   Kat başına PNG önizleme (duvarlar duruma göre renkli) yolu gösterilir.
5. **Tip seçimleri** (mevcut `selectors` tarzında): dış duvar tipi (bir kez);
   her iç kalınlık grubu için duvar tipi; kapı ailesi/tipi; pencere
   ailesi/tipi ("Opening kullan" seçeneğiyle).
6. **Oluşturma** — tek `TransactionGroup` (tek Undo), `WarningSwallower`,
   eleman başına hata yakalama (mevcut `revit_creator` gibi).
7. **Rapor** — oluşan/atlanan/başarısız tablo + önizleme görseli.

Diyalog sırası ve tam metinleri builder'ındır; akış bu sırayı korur
(soru → bekleme → soru; bekleme ortasında soru yok).

## İşleme hattı (CPython, `pysrc/rolove/`)

1. **DXF oku (katmana göre).** Kat başına duvar dış hatları → eksen +
   kalınlık (mevcut `wall_detector.outline_to_centerline` yeniden
   kullanılır), açıklık dikdörtgenleri → (host duvar, merkez, genişlik),
   oda poligonları + etiketleri.
2. **Katları ayır.** GLB başlık JSON'undan `Story` Z bantları (vertex
   okumadan, accessor min/max ile). LAZ bir kez okunur (laspy + lazrs,
   float32), bantlara bölünür.
3. **Kat kotu ölçümü.** Her kat için, o katın oda poligonları içindeki
   noktaların Z histogramında bant altına yakın baskın tepe = döşeme kotu;
   benzer şekilde tavan. CSV tavan yüksekliği yalnız tutarlılık kontrolü ve
   yedek. Belirsizse önizlemede işaretlenir.
4. **Hizalama (DXF katı → tarama).** Katın döşemeden ~1.0–1.5 m yüksekliğindeki
   yatay dilimi 2B'ye iz düşürülür; DXF duvar yüzleri bu dilime 2B rijit
   dönüşümle (aday dönüşler 0/90/180/270° + ince ayar, öteleme) oturtulur.
   Sonuç: kat başına dönüşüm + RMS. **RMS eşiği aşılırsa o kat modele
   basılmaz** ve nedeni raporlanır.
5. **Duvar iyileştirme.** Her duvarın her yüzü için, yüz çizgisinin
   ±bant içindeki ve döşeme+0.3 m … tavan−0.3 m arasındaki noktalar
   (mobilya/tavan dışarıda kalsın) alınır; sağlam (trimmed/median) doğru
   uydurma yapılır.
   - Yeterli destek varsa yüz "görüldü".
   - İki yüz görüldü → ölçülen kalınlık ve eksen → `ölçüldü`.
   - Tek yüz görüldü → o yüz kesin; kalınlık tipten, odadan dışa doğru
     (iç taraf oda poligonlarından bilinir) → `düzeltildi`.
   - Hiç yüz yok → DXF konumu kalır → `varsayıldı`.
   - **Düzeltme sınırlı:** öteleme ve dönüş eşiklerini aşan düzeltme
     uygulanmaz, DXF konumu kalır, duvar işaretlenir. Açılar 90°'ye
     zorlanmaz.
6. **Köşeler.** Komşu duvarların yeni doğruları yeniden kesiştirilir; uçlar
   yalnız tolerans içinde yakalanır, yakalanmayanlar raporlanır.
7. **Dış/iç ayrımı ve kalınlık grupları.** Bir yanında oda, öbür yanında
   oda olmayan duvar = dış duvar (komşu/taranmamış ayrımı yok). İç
   duvarların ölçülen kalınlıkları 0/5 cm'ye yuvarlanır → her değer bir
   grup (değer + üye sayısı).
8. **Açıklıklar.** Genişlik ve konum DXF'ten (hizalamadan sonra). Yükseklik
   CSV'den, aynı odadaki genişliği eşleşen kayıtla (`G x Y`); eşleşme
   belirsizse varsayılan + `varsayıldı`. Parapet (pencere alt kotu)
   veride yok → varsayılan + `varsayıldı` (taramadan ölçmek sonraki sürüm
   adayı).
9. **Çıktı:** `output/rolove_input.json` (aşağıda) + kat başına önizleme
   PNG.

Bütün eşikler (bant genişlikleri, öteleme/dönüş sınırları, RMS eşiği,
yakalama toleransı, küme toleransı, varsayılan parapet/kapı yüksekliği)
tek bir yapılandırmada toplanır ve JSON'a "kullanılan parametreler" olarak
yazılır. Başlangıç değerleri builder'ındır.

## Ara JSON (`rolove_input.json`, şema sürümü 1)

- `schema_version`, kaynak dosyalar (ad, boyut, değiştirilme zamanı),
  kullanılan parametreler, işlem istatistikleri ve süreleri.
- **Koordinatlar feet**, Revit iç birimi; XY = LAZ yerel çerçevesi
  (zaten orijine yakın, ±15 m), Z = **ana katın (en büyük döşeme alanlı kat,
  örnekte Floor 2) döşemesi ±0.00** olacak şekilde ötelenmiş *(benim
  kararım; Belçika "0-pas" alışkanlığı)*. Uygulanan öteleme JSON'da.
- `levels[]`: id, ad, kot, güven, kanıt (tepe yüksekliği, nokta sayısı).
- `walls[]`: kararlı id, kat id, başlangıç/bitiş (konum çizgisi), konum
  çizgisi türü (iç bitmiş yüz / eksen), dış/iç, kalınlık grubu, ölçülen
  kalınlık (varsa), yükseklik, durum, sapma (cm), destek nokta sayısı,
  uyarılar.
- `openings[]`: kararlı id, tür (kapı/pencere/boşluk), host duvar id,
  merkez, genişlik, yükseklik, parapet, her ölçünün durumu.
- `rooms[]`: kat id, ad, poligon, CSV alanı.
- `alignment[]`: kat başına dönüşüm + RMS + karar.
- `rejected[]`: modele girmeyenler ve nedenleri.

**Kararlı id:** kat + DXF'teki elemanın yuvarlanmış geometrisinden türeyen
özet (ör. hash). Aynı export tekrar işlenince aynı id çıkar.

## Revit tarafı (IronPython 2.7, `lib/pykalfa/rolove/`)

- **Hedef belge:** boş, yeni bir proje (kullanıcı). Model iç orijine
  yakın, coğrafi konum yok.
- **Level:** yalnız bu butonun daha önce oluşturduğu Level'larla (kayıttaki
  id) eşleşir; şablonun kendi Level'larına (ör. 0 / +3.00) **bağlanmaz**,
  onlara dokunmaz, raporda belirtir *(benim kararım)*. Yoksa
  `Level.Create`. Adlandırma Polycam kat numarasıyla tutarlı (ör.
  `Kat 1 (Scan)`; metin builder'ın).
- **Wall:** `Wall.Create(doc, curve, wallTypeId, levelId, height, offset,
  flip, structural)`; taban kısıtı katın Level'ı, yükseklik **bağlantısız**
  = o duvar çevresinde ölçülen tavan yüksekliği (yoksa CSV, yoksa
  varsayılan), 0/5 cm'ye yuvarlanmış. **Eğik tavan altındaki duvarlar**
  (CSV'de aralıklı tavan, örn. `0.7 - 2.4`): ölçülen **en yüksek** değer
  kullanılır (sonra çatıya bağlanabilsin), yükseklik durumu `varsayıldı`
  *(benim kararım)*. Dış duvarlarda konum çizgisi = **iç bitmiş yüz**
  (`WALL_KEY_REF_PARAM`), kalınlık dışa; iç duvarlarda eksen.
- **Kapı/pencere:** `NewFamilyInstance(pt, symbol, hostWall, level,
  NonStructural)`; boyut başına tip çoğaltılır (ör. `Scan 90x210`), genişlik/
  yükseklik parametreleri ayarlanır, parapet `INSTANCE_SILL_HEIGHT_PARAM`.
  Seçilen ailenin boyut parametreleri bulunamazsa → Opening'e düşülür ve
  raporlanır.
- **Opening:** `doc.Create.NewOpening(wall, p1, p2)`.
- **Room:** `doc.Create.NewRoom(level, UV)` oda poligonunun iç noktasında;
  ad Polycam etiketi.
- **Kimlik ve etiketler:** kararlı id **Extensible Storage**'da (görünmez,
  sağlam). Durum / sapma (cm) / ölçülen kalınlık (cm) **görünür proje
  parametreleri** olarak (buton gerekirse geçici shared parameter dosyasıyla
  bir kez oluşturur). Kurulum gerektirmez.
- **Yeniden çalıştırma:** aynı kararlı id'li eleman varsa dokunulmaz;
  yalnız eksikler eklenir; farklar rapora yazılır.

## Performans

Hedef (benim kararım): örnek veri setinde hazırlık ≲ 60 s, Revit tarafı
≲ 30 s. Bunun için:

- LAZ bir kez okunur, float32 numpy; gereksiz alanlar (renk) atılabilir.
- Tam bulutta normal hesabı, RANSAC, mesh işleme **yok**. Her duvar yalnız
  kendi çevresindeki noktalara bakar (2B ızgara indeksi ile).
- GLB'den yalnız başlık JSON'u okunur (vertex buffer'a dokunulmaz).
- Gerekirse voxel seyreltme parametreyle açılır; varsayılan kapalı.
- Süreler JSON'a ve rapora yazılır (ölçülmeden hız iddiası yok).

## Kod yapısı

- `pyKalfa.tab/Duvar.panel/RoloveAktar.pushbutton/` — `script.py`,
  `bundle.yaml`, `icon.png`. Yalnız akışı kurar (Duvar Aktar gibi).
- `pysrc/rolove/` — CPython: Polycam DXF okuyucu, CSV okuyucu, GLB kat
  bantları, LAZ yükleme, kat kotu, hizalama, duvar iyileştirme, açıklıklar,
  JSON/önizleme üretimi, `prepare_rolove_input.py` giriş noktası,
  `selftest.py`. Modül bölümlemesi builder'ın.
- `lib/pykalfa/rolove/` — IronPython: `ui`, Level/Wall/açıklık/Room
  oluşturucular, kimlik/parametre yardımcıları.
- `pysrc/duvar/` yalnız **okunur/yeniden kullanılır**; Duvar Aktar'ın
  davranışı değişmez.
- `requirements.txt`'ye `laspy[lazrs]` eklenir (numpy, ezdxf zaten var).
  Yeni ağır bağımlılık (open3d, scipy, trimesh) eklenmez.
- README (TR/EN/FR) özellik tablosu ve "Kullanım": Rölöve Aktar + hangi
  Polycam export'larının alınacağı.

## Kısıtlar

- Revit 2026, pyRevit IronPython 2.7 (buton), paylaşılan CPython `env/`
  (`bootstrap.ensure_env()`).
- Polycam export'u en az **Basic** plan gerektirir (DXF/CSV/LAS). Ücretsiz
  plan yalnız glTF verir; bu buton ücretsiz planla çalışmaz (bilinen).
- Orijinal export dosyaları değiştirilmez.

## Doğrulama

- `selftest.py`: sentetik DXF + sentetik nokta bulutu (bilinen öteleme,
  bilinen kalınlıklar, tek yüzlü duvar, eksik duvar) ile çevrimdışı test.
- Örnek veri setinde uçtan uca çalıştırma: kat başına hizalama RMS, duvar
  sapma dağılımı, durum dağılımı, süreler raporlanır.
- Kullanıcı bir odada elle ölçü alırsa (lazer metre) modelle karşılaştırma
  tablosu. Doğruluk ölçülmeden başarı iddia edilmez.

## Builder'a bırakılanlar

- Tüm eşiklerin başlangıç değerleri, kümeleme yöntemi, sağlam doğru
  uydurma yöntemi, 2B hizalama algoritmasının ayrıntısı.
- `Floor_N` ↔ `Story` eşleşmesinin nasıl doğrulanacağı.
- Önizleme PNG'sinin görünümü; diyalog metinleri.
- Parametre adları ve shared parameter oluşturma ayrıntısı.
- Kapı/pencere aile parametrelerinin bulunma yolu (built-in vs. ad).
- Test fixture'ları.
