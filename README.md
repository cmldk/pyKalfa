# pyKalfa

**Türkçe** · [English](README.en.md) · [Français](README.fr.md)

Revit için pyRevit eklentisi. Kadastro görüntülerinden parsel ve bina
geometrisi, kat planı DXF'inden de gerçek duvarlar üretir.

## Özellikler

| Buton | Ne yapar |
| --- | --- |
| **Parsel/Bina Aktar** | Kadastro görüntülerinden (PNG) parsel sınırlarını `DetailLine`, bina alanlarını `FilledRegion`, parsel numaralarını `TextNote` olarak Revit'e çizer. |
| **Parsel/Bina GIS** | Valonya'da adres veya CaPaKey ile SPW geoportalından parsel sınırlarını, binaları ve parsel numaralarını alıp Parsel/Bina Aktar ile aynı stillerle çizer. OCR ve görsel gerekmez. |
| **Duvar Aktar** | Kat planı DXF'indeki duvarları gerçek Revit `Wall` elemanlarına dönüştürür. |
| **Rölöve Aktar** | Polycam taramasından boş projeye hızlı rölöve: ölçülen kat kotları, taranan yüzlere oturtulmuş duvarlar, kapı/pencere ve adlı odalar. |

## Gereksinimler

- Windows + Autodesk Revit
- [pyRevit](https://github.com/pyrevitlabs/pyRevit)
- [Python 3](https://www.python.org) — kurulumda **"Add python.exe to PATH"** işaretli olmalı

## Kurulum

1. Revit'te **pyRevit** sekmesi → **Extensions**.
2. Yeni eklenti olarak şu adresi girin:
   ```
   https://github.com/cmldk/pyKalfa.git
   ```
3. **Reload** edin (veya Revit'i yeniden başlatın).

İlk açılışta gerekli Python paketleri otomatik kurulur. Bu birkaç dakika
sürer (OCR kütüphanesi ~1-1.5 GB) ve bir ilerleme çubuğu gösterilir.
Sonraki açılışlarda kurulum tekrarlanmaz.

> İsteğe bağlı: **Code → Download ZIP** ile indirip klasör adını
> `pyKalfa.extension` yapıp pyRevit → Settings → *Custom Extension
> Folders*'a bu klasörün **üst** klasörünü de ekleyebilirsiniz.

## Kullanım

### Parsel/Bina Aktar

| Girdi: bina | Girdi: parsel | Girdi: ikisi birlikte | Çıktı: Revit |
| :---: | :---: | :---: | :---: |
| ![Bina görseli](assets/bina.png) | ![Parsel görseli](assets/parsel.png) | ![İki katman birlikte](assets/both.png) | ![Revit çıktısı](assets/output_revit_img.png) |

Kendi görselleriniz `assets/` klasöründeki bu örneklere benzer
olmalıdır: aynı kadastro kesitinin **aynı görünümünden** dışa
aktarılmış üç PNG, **aynı piksel boyutunda** ve ölçek çubuğu görünür
durumda.

Üçüncü görsel (ikisi birlikte) geometri kaynağı **değildir**; iki
katmanı birbirine hizalamak için kullanılır. Bina ve parsel görselleri
ayrı ayrı dışa aktarıldığı için aynı kadrajı gösterdikleri garanti
değildir, kaymış bir parsel-bina eşleşmesi de çıktıda hata gibi
görünmez. Üçüncü görsel bu belirsizliği ortadan kaldırır; hizalama
doğrulanamazsa uyarı verilir.

1. **Plan, detay, kesit veya cephe** görünümüne geçin (3D görünümde
   çalışmaz).
2. **pyKalfa** → **Parsel / Bina** → **Parsel/Bina Aktar**.
3. Sırasıyla sorulan girdileri verin:
   - yalnızca **bina** katmanını içeren görseli (PNG) seçin
   - yalnızca **parsel** katmanını içeren görseli (PNG) seçin
   - **ikisini birlikte** içeren görseli (PNG) seçin
   - harita ölçeğinin paydasını yazın (1:500 için `500`)
   - parsel çizgileri için bir **Line Style** seçin
   - çizim çerçevesi (görüntünün dış sınırı) için ayrı bir **Line
     Style** seçin — çerçeve istemiyorsanız listenin başındaki
     *"Cerceve cizme"* seçeneğini işaretleyin
   - bina birimleri için bir **Filled Region Type** seçin
   - parsel numaraları için bir **Text Note Type** seçin
   - kuzey oku için bir **Generic Annotation** sembolü seçin —
     istemiyorsanız listenin başındaki *"Kuzey oku ekleme"* seçeneğini
     işaretleyin
4. Görüntü işleme bir ilerleme çubuğuyla çalışır; bu sırada soru
   sorulmaz.
5. Geometri çizilir ve kaç eleman oluştuğunu gösteren özet açılır.

> Görselin alt kısmındaki kuzey oku, ölçek çubuğu ve künye yazısı
> geometriye dahil edilmez. Kuzey okunun yalnızca **konumu ve yönü**
> ölçülür; çizime projenin kendi sembolü aynı yöne çevrilerek konur.

> Bitişik yapılarda (sıra ev blokları) **her birim ayrı bir Filled
> Region** olur; aradaki bölme (parti) duvarları korunur. Komşu iki
> birimin ortak kenarı piksel piksel aynı çizgiden geldiği için
> aralarında boşluk kalmaz.

> Parsel numaraları OCR ile okunur, doğruluk ~%80'dir. Benzer
> karakterler (G/6, A/4, B/8, S/5) karışabilir; sonucu kaynak görselle
> karşılaştırıp gerekirse elle düzeltin.

### Parsel/Bina GIS

Yalnız **Valonya** için ve internet bağlantısı gerekir. Görüntü, ölçek ve
OCR yoktur: parsel sınırları SPW `CADMAP_PARCELLES`, binalar SPW PICC,
parsel numaraları parselin kadastro özniteliklerinden gelir.

1. **Plan, detay, kesit veya cephe** görünümüne geçin.
2. **pyKalfa** → **Parsel / Bina** → **Parsel/Bina GIS**.
3. Sırasıyla:
   - **adres** (ör. `Rue du Parc 4, 4577 Modave`) veya **CaPaKey**
     (ör. `92053D0515/00B002`) yazın
   - bulunan adaylardan birini seçin (bulunamazsa tekrar sorulur)
   - parselin etrafında **kaç metre** alınacağını yazın (varsayılan 80,
     en fazla 200)
   - **seçilen parselin dış sınırı** için ayrı line style (atlanırsa diğer
     parsellerle aynı stil kullanılır; numarası diğerleriyle aynı yazılır)
   - Parsel/Bina Aktar'daki **aynı stil seçimleri**: parsel çizgileri,
     çerçeve (veya *"Cerceve cizme"*), yol ve kaldırım kenarları (veya
     *"Yol cizme"*), sokak adları için Text Note Type (veya *"Sokak adi
     yazma"*), bina Filled Region Type, parsel
     numarası Text Note Type, kuzey oku (veya *"Kuzey oku ekleme"*)
4. Veri birkaç saniyede bir ilerleme çubuğuyla alınır, sonra çizilir ve
   özet açılır.

> Çizim alanı, seçilen parselin sınır kutusunun verilen pay kadar
> büyütülmüş hâlidir; çerçeve bu dikdörtgendir ve onu kesen komşu
> parseller ile binalar çerçevede kırpılır. Orijin Parsel/Bina Aktar'daki
> gibi çerçevenin sol-alt köşesidir; veri kuzey yukarı olduğu için kuzey
> oku 0° konur.

> Yol ve kaldırım kenarları PICC "Voirie - Ligne" katmanından gelir (yol
> kenarı, patika kenarı, kaldırım arka kenarı; bordür, park yeri, yaya geçidi
> vb. çizilmez). Sokak adları yol eksenlerinden gelir: her ad bir kez, en uzun
> eksen parçasının ortasına, yol yönünde döndürülmüş ve ortalanmış yazılır.
> PICC'nin ayrıntılı olmadığı kırsal yerlerde yol çizgisi çıkmayabilir.

> Parsel numaraları veriden okunduğu için OCR hatası yoktur. Kontrol için
> `output/revit_input_preview.png` görseli bırakılır.
>
> Kaynak: Plan parcellaire cadastral © AGDP/SPF Finances, via SPW ;
> Bâtiments, voirie © SPW (PICC_VDIFF).

### Duvar Aktar

1. Duvarların gideceği kata ait bir **plan görünümüne** geçin.
2. **pyKalfa** → **Duvar** → **Duvar Aktar**.
3. Sırasıyla:
   - **DXF dosyasını** seçin
   - *(gerekirse)* çizim birimini, orijine taşımayı veya tek çizgi
     modunu onaylayın
   - **katmanı** seçin — program en olası duvar katmanını önerir.
     Kapı ve pencereler duvarla aynı şekilde çizildiği için ancak
     katmanla ayrılabilir, bu yüzden bu adım önemlidir
   - **duvar yüksekliği**, **Level** ve **Wall Type** seçin
4. Onay penceresini geçin; işlem bitince oluşan/oluşamayan duvar sayısı
   ve toplam uzunluk gösterilir.

> Aktarımın tamamı tek bir işlemdir: sonucu beğenmezseniz Revit'te tek
> bir **Ctrl+Z** ile geri alabilirsiniz.

### Rölöve Aktar

Polycam (iPhone/iPad LiDAR) taramasından mimar için hızlı bir başlangıç
modeli üretir. Amaç güvenilir bir rölöve: ölçü taramadan gelir, belirsiz
olan uydurulmaz, işaretlenir.

**Gereken girdiler** (Polycam Basic plan):

| Girdi | Dosya | Polycam'de |
|---|---|---|
| **Input 1** – Kat planı | `.dxf` (ya da kat planı `.zip`'i) | Floor plan → DXF |
| **Input 2** – Oda listesi | `.csv` (kat planı zip'indeyse oradan alınır) | Floor plan → CSV |
| **Input 3** – Nokta bulutu | `.laz` / `.las` — **georeferenced kapalı** | Point cloud → LAS |
| **Input 4** – 3B model | `.glb` | Mesh → GLTF |

Polycam'in OBJ (mesh) zip'i Input 1 değildir; içinde DXF yoktur.

1. Boş bir proje açın (Architectural şablon yeterli).
2. **pyKalfa** → **Duvar** → **Rolove Aktar** ve **Input 1**'i seçin.
   Aynı klasörde aynı adlı Input 2–4 kendiliğinden önerilir; girdi
   penceresi her birini `OK` / `EKSIK` olarak gösterir, yanlış ya da eksik
   olanı "Input N seç / değiştir" ile seçin (ad uyması gerekmez).
3. Hazırlık birkaç saniye sürer (örnek 4 katlı evde ~5 s). Özet penceresi
   kat kotlarını (ana kat = 0.00), her katın taramaya oturup oturmadığını
   ve duvar durumlarını gösterir; kotlar düzeltilebilir. Kat başına PNG
   önizleme `output/` altına yazılır.
4. Dış duvar tipini **bir kez**, her iç duvar kalınlık grubu için bir tip,
   kapı ve pencere ailesini seçin (ya da "Opening kullan").
5. Level'lar `Kat N (Scan)` adıyla, duvarlar her katın kendi Level'ında
   oluşur. Dış duvarlar taranan **iç yüzden dışa doğru** kalınlaşır
   (Location Line = Finish Face: Interior).

Her duvar/kapı/pencere `pyKalfa Tarama Durumu` parametresini taşır:
**olculdu** (LAZ'dan ölçüldü), **duzeltildi** (DXF konumu taramaya göre
düzeltildi), **varsayildi** (varsayılan ya da doğrulanamadı — kontrol
edin). Görünüm filtresiyle renklendirilebilir. Ölçüler en yakın 5 cm'ye,
kotlar 1 cm'ye yuvarlanır; konumlar yuvarlanmaz.

Butonu aynı projede tekrar çalıştırmak güvenlidir: daha önce oluşturulan
elemanlar (taşınmış olsalar bile) korunur, sildikleriniz geri gelmez,
yalnız eksikler eklenir.

## Lisans

[MIT](LICENSE)
