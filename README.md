# pyKalfa

**Türkçe** · [English](README.en.md) · [Français](README.fr.md)

Revit için pyRevit eklentisi. Kadastro verisinden parsel ve bina
geometrisi, Polycam taramasından da döşemeli bir bina prototipi üretir.

## Özellikler

| Buton | Ne yapar |
| --- | --- |
| **Parsel/Bina GIS** | Valonya ve Flaman bölgesinde adres veya CaPaKey ile bölgenin GIS servislerinden parsel sınırlarını (`DetailLine`), binaları (`FilledRegion`), yol kenarlarını, sokak adlarını ve parsel numaralarını (`TextNote`) alıp aktif görünüme çizer. |
| **Rölöve Prototip** | Aynı Polycam taramasından toparlanmış, döşemeli hızlı prototip: dik köşeler, katlar arası hizalı dış duvarlar, her katta döşeme. |

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
sürer ve bir ilerleme çubuğu gösterilir.
Sonraki açılışlarda kurulum tekrarlanmaz.

> İsteğe bağlı: **Code → Download ZIP** ile indirip klasör adını
> `pyKalfa.extension` yapıp pyRevit → Settings → *Custom Extension
> Folders*'a bu klasörün **üst** klasörünü de ekleyebilirsiniz.

## Kullanım

### Parsel/Bina GIS

**Valonya** ve **Flaman bölgesi** için; internet bağlantısı gerekir.
Görüntü, ölçek ve OCR yoktur. Adres adayları iki bölgeden aynı listede
gelir (her satırda bölge yazar); CaPaKey önce Valonya'da, sonra Flaman
bölgesinde aranır. Brüksel desteklenmez.

| | Valonya | Flaman bölgesi |
|---|---|---|
| Adres | ICAR (SPW) | Digitaal Vlaanderen (geolocation) |
| Parsel | SPW `CADMAP_PARCELLES` | Adpf (idari parseller) |
| Bina | SPW PICC | GRB `GBG` |
| Yol / kaldırım kenarı | PICC "Voirie - Ligne" | GRB `WGO` |
| Sokak adı | PICC yol ekseni | GRB `Wegsegment` |

Parsel numaraları iki bölgede de CaPaKey'den çözülür.

1. **Plan, detay, kesit veya cephe** görünümüne geçin.
2. **pyKalfa** → **Parsel / Bina** → **Parsel/Bina GIS**.
3. Sırasıyla:
   - **adres** (ör. `Rue du Parc 4, 4577 Modave`, `Steenstraat 10, 8000
     Brugge`) veya **CaPaKey**
     (ör. `92053D0515/00B002`) yazın
   - bulunan adaylardan birini seçin (bulunamazsa tekrar sorulur)
   - parselin etrafında **kaç metre** alınacağını yazın (varsayılan 80,
     en fazla 200)
   - **seçilen parselin dış sınırı** için ayrı line style (atlanırsa diğer
     parsellerle aynı stil kullanılır; numarası diğerleriyle aynı yazılır)
   - **stil seçimleri**: parsel çizgileri,
     çerçeve (veya *"Cerceve cizme"*), yol ve kaldırım kenarları (veya
     *"Yol cizme"*), sokak adları için Text Note Type (veya *"Sokak adi
     yazma"*), bina Filled Region Type, parsel
     numarası Text Note Type, kuzey oku (veya *"Kuzey oku ekleme"*)
4. Veri birkaç saniyede bir ilerleme çubuğuyla alınır, sonra çizilir ve
   özet açılır.

> Çizim alanı, seçilen parselin sınır kutusunun verilen pay kadar
> büyütülmüş hâlidir; çerçeve bu dikdörtgendir ve onu kesen komşu
> parseller ile binalar çerçevede kırpılır. Orijin çerçevenin sol-alt
> köşesidir; veri kuzey yukarı olduğu için kuzey
> oku 0° konur.

> Yol ve kaldırım kenarları PICC "Voirie - Ligne" katmanından gelir (yol
> kenarı, patika kenarı, kaldırım arka kenarı; bordür, park yeri, yaya geçidi
> vb. çizilmez). Sokak adları yol eksenlerinden gelir: her ad bir kez, en uzun
> eksen parçasının ortasına, yol yönünde döndürülmüş ve ortalanmış yazılır.
> PICC'nin ayrıntılı olmadığı kırsal yerlerde yol çizgisi çıkmayabilir.
> Flaman bölgesinde yol kenarları GRB `WGO` katmanının üç türüdür: rijbaan
> kenarı, yaya/bisiklet bölgesi (kaldırım) sınırı, stabilize bölge sınırı.

> Parsel numaraları veriden okunduğu için OCR hatası yoktur. Kontrol için
> `output/revit_input_preview.png` görseli bırakılır.
>
> Kaynak — Valonya: Plan parcellaire cadastral © AGDP/SPF Finances, via SPW ;
> Bâtiments, voirie © SPW (PICC_VDIFF). Flaman: Adpf © AAPD/FOD Financiën,
> via Digitaal Vlaanderen ; GRB © Digitaal Vlaanderen.

### Rölöve Prototip

Polycam (iPhone/iPad LiDAR) taramasından boş projeye **hızlı bir başlangıç
kütlesi** üretir: duvarlar, döşemeler, kapı/pencere ve adlı odalar. Ölçü
belgesi değildir; ince ölçüler sonradan elle düzeltilir.

**Gereken girdiler** (Polycam Basic plan):

| Girdi | Dosya | Polycam'de |
|---|---|---|
| **Input 1** – Kat planı | `.dxf` (ya da kat planı `.zip`'i) | Floor plan → DXF |
| **Input 2** – Oda listesi | `.csv` (kat planı zip'indeyse oradan alınır) | Floor plan → CSV |
| **Input 3** – Nokta bulutu | `.laz` / `.las` — **georeferenced kapalı** | Point cloud → LAS |
| **Input 4** – 3B model | `.glb` | Mesh → GLTF |

Polycam'in OBJ (mesh) zip'i Input 1 değildir; içinde DXF yoktur.

- **Ölçü:** her katın duvarları taramaya oturtulur, kat kotları taramadan
  ölçülür (ana kat = 0.00).
- **Toparlama:** neredeyse dik köşeler (5°'ye kadar) 90°'ye, katlar arası
  birbirine 15 cm'den yakın dış duvarlar aynı hatta oturur. Daha eğik
  duvarlar olduğu gibi kalır; taramada kapalı köşeler kapalı kalır.
- **Döşeme:** her katın Level'ına bir döşeme (tipini siz seçersiniz); üst
  yüzü kat kotunda, dış duvarın dış yüzüne kadar. Bir katın döşemesi o
  katın ve altındaki katın izini örter (üstü açık kalan kısım düz çatı
  varsayılır).
- **Duvarlar** üst katın Level'ına bağlanır ve döşemenin altında biter;
  en üst katın duvarları taranan yükseklikte kalır. Dış duvarlar taranan
  **iç yüzden dışa doğru** kalınlaşır. Döşeme tipini sonradan
  değiştirirseniz duvarların üst ofsetini de güncelleyin.
- **Merdiven (isteğe bağlı):** Polycam DXF'indeki basamak çizgilerinden
  bulunur; çıkış yönü nokta bulutundaki basamak yüksekliklerinden ölçülür.
  Alt kattan üst kata düz kollu Revit merdiveni olarak kurulur: riht sayısı
  ve basamak derinliği seçilen merdiven tipinin sınırlarından hesaplanır; kat
  yüksekliğine ulaşmak için kol taramadakinden uzun olursa raporda yazılır.
- **Açık plan:** duvarsız komşu odaların arasına oda ayırıcı (Room
  Separation Line) konur; her oda kendi alanıyla oluşur.
- Çatı ve merdiven boşluğu yok.

1. Boş bir proje açın (Architectural şablon yeterli).
2. **pyKalfa** → **Duvar** → **Rolove Prototip** ve **Input 1**'i seçin.
   Aynı klasörde aynı adlı Input 2–4 kendiliğinden önerilir; girdi
   penceresi her birini `OK` / `EKSIK` olarak gösterir, yanlış ya da eksik
   olanı "Input N seç / değiştir" ile seçin.
3. Özet penceresi kat kotlarını ve toparlama sayılarını gösterir; kotlar
   düzeltilebilir. Kat başına `prototip_preview_katN.png` yazılır.
4. Dış duvar tipini **bir kez**, her iç duvar kalınlık grubu için bir tip
   (ya da listenin başındaki *"Yeni tip olustur: Prototip Ic Duvar N cm"*:
   dış duvar tipinden kopya, tam ölçülen kalınlıkta), kapı ve pencere
   ailesini (ya da "Opening kullan"), **döşeme tipini** ve merdiven bulunduysa
   **merdiven tipini** (ya da *"Merdiven olusturma"*) seçin. İşlem tek
   **Ctrl+Z** ile geri alınabilir.

Her duvar/kapı/pencere `pyKalfa Tarama Durumu` parametresini taşır:
**olculdu** (taramadan ölçüldü), **duzeltildi** (konumu taramaya göre ya da
toparlamada düzeltildi; sapma cm olarak yazılır), **varsayildi**
(varsayılan ya da doğrulanamadı — kontrol edin). Görünüm filtresiyle
renklendirilebilir.

Butonu aynı projede tekrar çalıştırmak güvenlidir: daha önce oluşturulan
elemanlar korunur, sildikleriniz geri gelmez, yalnız eksikler eklenir.

## Lisans

[MIT](LICENSE)
