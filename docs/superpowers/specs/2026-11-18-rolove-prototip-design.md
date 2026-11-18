# Rölöve Prototip — tasarım

Tarih: 2026-11-18 · Durum: taslak (onay bekliyor)

## Amaç ve neden

Rölöve Aktar her katı ayrı ayrı ve taramaya sadık oluşturur: duvarlar kendi
Level'ında, **taranan tavana kadar** yükselir; döşeme yoktur. Sonuç
(kullanıcı): "zeminsiz, havada duran kat duvarları". Örnek taramada
(`P26-041`) katlar arası açıklık 14 / 55 / 24 cm:

| Kat | Kot | Duvar yük. | Duvar üstü | Üst kata boşluk |
|---|---|---|---|---|
| Kat 1 | −2.04 | 1.90 | −0.14 | 14 cm |
| Kat 2 | 0.00 | 2.45 | 2.45 | 55 cm |
| Kat 3 | 3.00 | 2.30 | 5.30 | 24 cm |
| Kat 4 | 5.54 | 2.30–2.40 | ~7.90 | (çatı) |

Katlar yatayda zaten iyi örtüşüyor (Kat 3'ün %98'i Kat 2'nin, Kat 4'ün
tamamı Kat 3'ün üstünde); kopukluk düşeyde.

Kullanıcı aynı veriden **hızlı bir prototip** istiyor: döşemeleriyle tek
bir bina gibi duran, toparlanmış, "varsayımsal" bir model. İç daire
aralıkları ve ince ölçüler sonradan Polycam'den tekrar ölçülüp elle
düzeltilecek. Yani prototip bir **başlangıç kütlesi**, ölçü belgesi değil.

Bu, Rölöve Aktar'ın "veriyi güzelleştirme" ilkesine bilerek ters düşer.
Bu yüzden ayrı bir buton, ayrı ve açıkça işaretlenmiş bir sonuçtur
(kullanıcı: ayrı buton; "belki üzerinden iyileştirmeler yaparız").

## Hedefler

- `pyKalfa.tab/Duvar.panel/` altında yeni **Rolove Prototip** butonu
  (ad benim kararım; şerit adı ASCII, diğer butonlar gibi).
- Girdiler Rölöve Aktar ile aynı (Input 1–4: DXF/zip, CSV, LAZ, GLB) ve
  aynı girdi penceresiyle seçilir.
- **Plan toparlama (kullanıcı: B):**
  - Neredeyse dik köşeler 90°'ye, neredeyse paralel duvarlar paralele
    oturtulur (binanın baskın yönüne göre).
  - Üst/alt kat **dış duvarları** birbirinin hizasına oturtulur: aynı
    dış hatta olması gerektiği belli olan (paralel, birkaç cm yakın)
    duvarlar tek bir hatta toplanır.
  - Toparlamadan sonra köşeler yeniden kesiştirilir, kapı/pencereler host
    duvarla birlikte taşınır.
- **Döşeme (kullanıcı: döşeme eklensin; yol 1):**
  - Her katın Level'ına bir **Floor**; üst yüzü Level kotunda, kalınlık
    aşağı doğru. Tip kullanıcı tarafından **bir kez** seçilir.
  - Duvarlar alttaki Level'dan başlar, **üstteki katın Level'ına
    bağlanır**, üst ofset = −(döşeme kalınlığı) → duvar döşemenin altında
    biter. Kalınlık ne olursa olsun boşluk ve çakışma kalmaz; sonradan
    döşeme tipi değişirse duvar üst ofsetinin elle güncellenmesi gerekir
    (Revit "attach top" yerine sabit ofset; bkz. Builder'a bırakılanlar).
  - En üst kat (üstünde Level yok): duvarlar taranan yükseklikte,
    bağlantısız kalır (eğik tavan; çatı kapsam dışı).
- Kapı, pencere, Opening ve Room'lar Rölöve Aktar'daki gibi oluşturulur
  (aynı aile/tip seçimleri).
- **Dürüst etiket:** her eleman Rölöve Aktar'daki `pyKalfa Tarama Durumu`
  parametresini taşır. Toparlamanın yerinden oynattığı duvarlarda durum
  en az `duzeltildi`, sapma (cm) = toparlamanın taramadan uzaklaştırdığı
  mesafe. Kullanıcı neyin varsayıldığını filtreyle görür.
  *(benim kararım)* Durum ve sapma **plan konumunu** anlatır. Duvar
  yüksekliği prototipte tasarım gereği Level'dan gelir (örnekte Kat 2
  duvarı 2.45 m taramadan ~2.80 m'ye çıkar); bu, durumu değiştirmez —
  yoksa neredeyse her duvar `duzeltildi` olur ve etiket plan için bilgi
  vermez. Bunun yerine her duvarın `warnings`'ine ve rapora "yükseklik:
  taranan X m → Level'a bağlı Y m" yazılır; taranan yükseklik JSON'da
  korunur.
- Tek Undo (TransactionGroup), yeniden çalıştırma güvenli (Rölöve Aktar'ın
  defter mantığı).

## Hedef dışı

- Çatı, eğik tavan, merdiven, tavan (Ceiling) elemanı, döşeme boşlukları
  (merdiven boşluğu).
- İç duvarları başka katların iç duvarlarına hizalamak (kullanıcı iç
  aralıkları sonradan ölçecek; iç duvarlarda yalnız açı düzeltmesi).
- Rölöve Aktar'ın davranışını değiştirmek (kod paylaşılabilir, sonuç
  aynı kalmalı; mevcut selftest geçmeli).
- Mevcut bir Rölöve Aktar sonucunu Revit'te dönüştürmek (prototip
  taramadan baştan üretilir).

## Anti-hedefler

- Prototipin ölçülmüş rölöve gibi görünmesi (durum etiketi taşımayan ya
  da sapması 0 gösterilen yerinden oynatılmış duvar).
- Rölöve Aktar sonucu ile prototipin aynı projede üst üste binmesi
  (sessizce çift duvar).
- Toparlamanın binayı bozması: büyük açılı duvarları dikleştirmek, metre
  mertebesinde kaydırmak. Toparlama küçük düzeltmedir; eşiği aşan duvar
  olduğu gibi kalır ve raporlanır.
- Döşemenin duvarın içine girmesi ya da duvarla döşeme arasında açıklık.
- Rölöve Aktar'da gerileme.

## Yaklaşımlar

1. **Rölöve Aktar içinde seçenek** ("ölçülen / prototip"). Her şeyi
   paylaşır ama akışa soru ekler.
2. **Ayrı buton (seçilen).** Aynı girdiler, aynı hazırlık, üstüne
   toparlama adımı ve döşeme aşaması. Rölöve Aktar'a dokunmaz; ileride
   prototipe özgü iyileştirmeler kolay. Bedeli: aynı projede ikisinin
   çakışmasını ayrıca engellemek.
3. **Revit'teki rölöveyi toparlayan buton.** Elle düzenlemelerin
   üstünde çalışır ama tüm geometri IronPython'da, en kırılgan yol.

Döşeme–duvar ilişkisi için: (1) döşeme + duvar döşeme altına kadar
**(seçilen)**; (2) döşeme kalınlığı = ölçülen boşluk (14/55/24 cm gibi
garip tipler) reddedildi.

## Akış

1. Belge kontrolü (proje belgesi).
2. Girdi seçimi — `rolove.ui.pick_inputs` aynen.
3. Hazırlık — tek CPython alt süreci, ilerleme çubuğu:
   `prepare_rolove_input.py` ile aynı hat, sonra **toparlama**; çıktı
   `output/prototip_input.json` + kat başına önizleme PNG (toparlanmış
   duvarlar ve döşeme hattı). Soru sorulmaz.
4. Özet/onay: kat kotları, toparlama sayıları (dikleştirilen, hizalanan,
   eşik aşımı yüzünden dokunulmayan duvarlar), döşeme sayısı ve alanları.
   Projede Rölöve Aktar sonucu varsa uyarı (aşağıda, "Çakışma koruması").
5. Seçimler: dış duvar tipi, iç kalınlık grubu tipleri, kapı/pencere
   (Rölöve Aktar ile aynı) + **döşeme tipi** (Floor Type, bir kez).
6. Oluşturma: parametreler → Level → duvar → birleşimler → döşeme →
   açıklıklar → odalar → defter. Tek TransactionGroup.
7. Rapor.

## Toparlama (CPython, yeni modül)

Girdi: Rölöve hazırlığının duvar/açıklık/oda listesi (feet, LAZ yerel
çerçeve). Çıktı: aynı şemada duvarlar + `floors[]`.

1. **Baskın yön.** Ana katın (kot 0.00) dış duvarlarından uzunluk
   ağırlıklı yön (mod 90°).
2. **Dikleştirme.** Yönü baskın yöne ya da dikine **±A°** içinde olan
   her duvar o yöne döndürülür; dönüş merkezi duvarın taranmış hattının
   orta noktası (dış duvarda iç yüz hattı korunur, yalnız açı değişir).
   Eşik dışı duvar dokunulmaz, raporlanır.
3. **Katlar arası dış duvar hizası.** Dikleştirmeden sonra, farklı
   katlardaki paralel dış duvarlar dik mesafeleri **≤ D cm** ve planda
   örtüşmeleri varsa bir küme sayılır; küme tek hatta toplanır (hat:
   uzunluk ağırlıklı ortalama, ana kat duvarı varsa ona ağırlık verilir —
   ayrıntı builder'ın). Dış duvarlarda karşılaştırılan hat iç yüz hattıdır
   (aynı dış tip → dış yüzler de hizalanır).
4. **Köşeler.** Kat içinde komşu duvar hatları yeniden kesiştirilir
   (mevcut `refine.join_corners` mantığı).
5. **Açıklıklar** yeni host hattına izdüşürülür (merkez, genişlik aynı).
6. **Etiket.** Yerinden oynayan her duvar: durum
   `max(eski, duzeltildi)`, `deviation_cm` = taranmış hattan en büyük
   uzaklık (uç noktalarda), `warnings`'e "prototip: dikleştirildi /
   kat hizası" notu.
7. **Döşeme hatları.** Level N'deki döşeme = katın kendi ayak izi ∪
   **altındaki katın ayak izi** (alt katın tavanı; örnekte Kat 2'nin üstü
   açık kalan kısmı Kat 3 kotunda döşeme/düz çatı olarak kapanır —
   varsayım, benim kararım, raporda belirtilir). Ayak izi = oda
   poligonlarının birleşimi, iç duvar aralıkları kapatılmış, dış
   duvarların **dış yüzüne** kadar genişletilmiş (dış tip kalınlığı Revit
   tarafında bilindiği için genişletme kalınlığı JSON'da değil Revit
   tarafında uygulanabilir — builder'ın). Delikli/çok parçalı sonuç
   destekli (birden çok CurveLoop).
8. En alttaki kat döşemesi kendi ayak izidir (zemin döşemesi).

Eşik başlangıç değerleri (benim önerim, builder ayarlar ve JSON'a
"kullanılan parametreler" olarak yazar): A = 5°, D = 15 cm, köşe yakalama
mevcut değer.

## Revit tarafı

- Level adları `Kat N (Prototip)`; Rölöve Aktar'ın Level'larıyla
  paylaşılmaz.
- Duvar: `Wall.Create(..., height, 0, ...)` sonra
  `WALL_HEIGHT_TYPE` = üst katın Level'ı, `WALL_TOP_OFFSET` = −döşeme
  kalınlığı (seçilen Floor Type'ın `GetCompoundStructure().GetWidth()`).
  Üst katı olmayan duvar bağlantısız, taranan yükseklik.
- Döşeme: `Floor.Create(doc, IList<CurveLoop>, floorTypeId, levelId)`
  (Revit 2022+); yapısal değil. Duvar–döşeme otomatik birleşim
  hatalarında Parsel/Bina GIS'teki `WarningSwallowerUnjoin` mantığı.
- Kapı/pencere/Opening/Room: Rölöve Aktar oluşturucusu yeniden kullanılır.
  Room üst sınırı = üst Level (kat yüksekliği boyunca).
- Kararlı id'ler `p-` önekiyle (prototip ve rölöve aynı defterde
  karışmasın); yeni eleman türü `floor` defterde tutulur.
- **Çakışma koruması** *(benim kararım)*: yalnız **prototip tarafında**.
  Defterde `p-` öneki taşımayan (Rölöve Aktar'ın) canlı eleman varsa özet
  penceresi açıkça uyarır ve devam için onay ister; önerilen kullanım ayrı
  proje. Prototipin kendi yeniden çalıştırması uyarı vermez. Rölöve Aktar
  tarafına uyarı eklenmez (davranışı değişmesin); bu bilinen bir boşluktur:
  önce prototip, sonra aynı projede Rölöve Aktar çalıştırılırsa uyarı yok.
- Rölöve Aktar'ın kodu (`creator.py`) paylaşılırken onun davranışı
  değişmemeli: genelleştirme varsayılanları eski davranışı korur.

## Kod yapısı (öneri, bölümleme builder'ın)

- `pyKalfa.tab/Duvar.panel/RolovePrototip.pushbutton/` — `script.py`,
  `bundle.yaml`, `icon.png`.
- `pysrc/rolove/prototype.py` — saf toparlama + döşeme hatları (numpy/
  shapely; shapely env'de zaten var).
- `pysrc/rolove/prepare_prototype_input.py` — giriş noktası: rölöve
  hazırlığını çağırır, toparlar, JSON + PNG yazar. Çıkış kodları rölöve
  ile aynı.
- `lib/pykalfa/rolove/` — prototip için döşeme aşaması ve duvar üst
  kısıtı; ui'ye döşeme tipi seçimi ve prototip özeti.
- `pysrc/rolove/selftest.py` — sentetik testler: dikleştirme (4° → 0°,
  8° dokunulmaz), katlar arası hiza (10 cm → tek hat, 30 cm → ayrı),
  döşeme ayak izi (alt kat ∪ kat, iç duvar aralığı kapanır, L-plan),
  açıklığın host ile taşınması, etiket/sapma.
- README (TR/EN/FR): Rölöve Prototip bölümü.

## Kısıtlar

- Revit 2026, pyRevit IronPython 2.7; CPython `env/`.
- Yeni ağır bağımlılık yok.
- Polycam girdi gereksinimleri Rölöve Aktar ile aynı.

## Doğrulama

- Selftest (çevrimdışı).
- Örnek taramada uçtan uca hazırlık: dikleştirilen/hizalanan sayıları,
  en büyük sapma, döşeme alanları raporlanır; önizleme gözle kontrol.
- Revit'te elle kontrol listesi (kullanıcı): katlar arası boşluk yok,
  döşeme duvara girmiyor, dış duvarlar katlar arasında hizalı, tek
  Ctrl+Z, yeniden çalıştırma çoğaltmıyor, Rölöve Aktar hâlâ aynı.

## Builder'a bırakılanlar

- Eşik değerlerinin son hali, küme hattı hesabı, ayak izi kapatma yöntemi.
- Dış yüze genişletmenin hangi tarafta (CPython / Revit) yapılacağı.
- Duvar üstünün sabit ofset mi yoksa döşemeye "attach" mi olacağı
  (sabit ofset önerilir: daha öngörülebilir).
- Önizleme görünümü, diyalog metinleri, ikon.
