# pyKalfa

Revit icin, birden fazla yardimci islevi tek catida toplayan bir pyRevit
extension'i. Her islev ust menudeki **pyKalfa** sekmesinde kendi butonu
olarak durur.

**Mevcut islevler**

| Panel | Buton | Ne yapar |
| --- | --- | --- |
| Parsel / Bina | **Parsel/Bina Aktar** | Kadastro goruntulerinden (parsel ve bina sinir cizgileri) OpenCV ile vektor geometri cikarip Revit'e `DetailLine` + `FilledRegion` + `TextNote` olarak aktarir. |
| Duvar | **Duvar Aktar** | Polycam/CAD kat plani DXF'indeki cizgileri ezdxf ile okuyup gercek Revit **duvarlarina** (`Wall`) donusturur. |

Yeni islevler ayri birer buton olarak eklenir; nasil eklendigi asagida
["Yeni buton (islev) ekleme"](#yeni-buton-islev-ekleme) bolumunde
anlatiliyor.

## Nasil calisir (kisa mimari)

Her sey tek bir klasorun (`revit/pyKalfa.extension/`) icinde,
kendi kendine yeterli sekilde durur:

```
revit/pyKalfa.extension/
  startup.py                   <- pyRevit'in extension her yuklemede/reload'da CALISTIRDIGI script
  pyKalfa.tab/                 <- sekme; her panel/buton burada
    ParselBina.panel/ImportGeometry.pushbutton/script.py   <- SADECE bu islevin akisi
    Duvar.panel/DuvarAktar.pushbutton/script.py
  lib/pykalfa/                 <- Revit (IronPython) tarafi
    paths, subproc, bootstrap, revitutils, selectors        <- ortak
    installer/                 <- env kurulumu (bkz. asagida)
    duvar/ui.py, duvar/revit_creator.py                     <- isleve ozel
  pysrc/                       <- islev bazli agir CPython kodu
    parsel_bina/               <- goruntu isleme (cv2/numpy/scikit-image)
    duvar/                     <- DXF okuma/temizleme (ezdxf)
  requirements.txt             <- pysrc'nin bagimliliklari (ortak)
  output/                      <- gecici ara dosyalar (ortak)

C:\pyKalfa\                    <- Python sanal ortami BURADA (extension'in DISINDA), bkz. asagida
  env/
  install.json
  install.log
```

Iki ayri calisma ortami var ama ikisi de bu TEK klasorun icinde:

1. **pyRevit tarafi** (`pyKalfa.tab/...` + `lib/pykalfa/`, Revit'in
   icinde IronPython 2.7 ile calisir): kullaniciyla konusur ve Revit
   elemanlarini olusturur.
2. **CPython tarafi** (`pysrc/<islev>/`, kendi `env/` sanal ortaminda
   calisir): IronPython 2.7'de calismayan kutuphaneler (OpenCV, EasyOCR,
   ezdxf) buraya devredilir. Her islev bir JSON ara format uretir:
   `parsel_bina` -> `revit_input.json`, `duvar` -> `wall_input.json`.
   Koordinatlar JSON'a hep **feet** (Revit'in ic birimi) olarak yazilir,
   boylece Revit tarafi hic birim hesabi yapmaz.

Her butonun `script.py`'si SADECE kendi is akisini icerir; yol bulma,
alt-surec calistirma, `env/` kurulumu ve "projedeki stilleri sectirme"
gibi tekrar eden isler `lib/pykalfa/` altindadir. Bir isleve ozel ama
`script.py`'yi sisirecek kadar buyuk Revit tarafi kod olursa (ör.
Duvar Aktar'in diyaloglari ve duvar olusturma dongusu)
`lib/pykalfa/<islev>/` altina konur.

**Onemli:** Bu iki asamayi ayri ayri calistirmaniza gerek yok. pyRevit
butonu, goruntu isleme asamasini kendisi otomatik olarak (arka planda,
`env/` sanal ortamini kullanarak) tetikler. Gunluk kullanimda hicbir
Python komutu yazmaniz gerekmez -- sadece Revit icinde bir butona
basarsiniz.

**Tek klasoru alip kullanmaya baslayabilirsiniz.** `revit/` klasorunun
disinda (`assets/` haric) hicbir seye bagimli degildir -- baska bir
projeye/bilgisayara tasisaniz da (repo'nun geri kalanini almasaniz da)
calismaya devam eder.

**`env/` sanal ortami tamamen otomatik kurulur, elle hicbir sey
calistirmaniza gerek yoktur.** Extension'in kokunde bulunan
`startup.py`, pyRevit tarafindan extension her yuklendiginde/reload
edildiginde (yani Revit'i actiginizda) otomatik calistirilir: sistemde
bir Python bulur (`py`/`python`), sabit bir sistem yolunda
(`C:\pyKalfa\env`) sanal ortami olusturur ve `requirements.txt`'i
kurar. Ilk kurulumda bu birkac dakika surebilir (bir bilgi penceresi
cikar, o sure boyunca pyRevit'in bu extension'i yuklemesi bekler);
sonraki her Revit acilisinda `env/` zaten guncel oldugu icin bu kontrol
aninda biter. Tek onkosul, sisteminizde herhangi bir Python 3 kurulu
olmasidir (yoksa python.org uzerinden kurmaniz istenir).

`env/`'in extension'in kendi klasorunun **disinda**, sabit ve kisa bir
yolda (`C:\pyKalfa`) tutulmasinin sebebi: pip'in kurdugu bazi
paketlerin (ör. OCR kutuphanesi) kendi ic dosya adlari zaten cok
derin/uzun; extension'i GitHub'dan ne kadar derin bir yola
klonlarsaniz klonlayin (ör. `Belgelerim\Projeler\...`), `env/` her
zaman kisa bir yolda oldugu icin Windows'un 260 karakterlik dosya yolu
sinirina (`WinError 206`) hic takilmazsiniz.

Eger `startup.py` herhangi bir sebeple calismadiysa (ör. cok eski bir
pyRevit surumu) veya `C:\pyKalfa\env` klasoru sonradan silindiyse, ilk
buton tiklamasi ayni kurulumu kendisi tamamlar (`bootstrap.ensure_env()`
-- guvenlik agi).

> **Not (boyut/sure):** parsel numara etiketlerini okumak icin
> kullanilan OCR kutuphanesi (`easyocr`) PyTorch'a bagimlidir ve
> kurulumu ~1-1.5 GB'a, ilk indirmeyi birkac dakikaya cikarir; ayrica
> OCR modelini ilk kullanimda ayrica indirir (internet gerektirir).
> Bu normaldir, sadece ilk calistirmada olur.

## Kurulum (bir kereye mahsus)

### 0. Projeyi indirin

Sadece **`revit/`** klasorunu (yani `revit/pyKalfa.extension/...`)
almaniz yeterli -- geri kalan dosyalar (bu README, ROADMAP, `assets/`
ornekleri) sadece gelistirme/referans amaclidir, calismasi icin gerekli
degildir. Iki yoldan biriyle edinebilirsiniz:

- **`git clone`** ile (Git kuruluysa): `git clone <repo-url>`
- **veya** GitHub'da **Code -> Download ZIP** (ya da bir Release
  sayfasindaki ZIP) ile indirip **zip'i cikartin**.

  GitHub'in olusturdugu zip'i actiginizda icinde `pyKalfa-main`
  (veya `pyKalfa-v1.0.0` gibi) adinda tek bir ust klasor cikar;
  `revit/` klasoru onun icindedir.

Nereye cikardiginiz/klonladiginiz veya `revit/` klasorunu sonradan
baska bir yere tasimaniz onemli degil -- extension kendi konumuna gore
calisir (sabit bir yol varsaymaz), ve `env/` zaten ayri, sabit bir
yolda kuruldugu icin (yukariya bakin) hicbir MAX_PATH riski tasimaz.

### 1. pyRevit'i kurun (kurulu degilse)

pyRevit'in resmi deposu: `github.com/pyrevitlabs/pyRevit` (Releases
sekmesinden kurulum dosyasini indirebilirsiniz). Kurulumdan sonra
Revit'i actiginizda ust menude bir **pyRevit** sekmesi gormelisiniz.

### 2. pyKalfa extension'ini pyRevit'e tanitin

1. Revit'te **pyRevit** sekmesi -> disli ikon (**Settings**).
2. **Custom Extension Folders** bolumune gidin.
3. **Add Folder** ile, adim 0'da indirdiginiz/cikardiginiz proje
   klasorunun icindeki `revit` klasorunu secin (ör.
   `...\pyKalfa-main\revit` veya `...\pyKalfa\revit`,
   nereye cikardiysaniz -- `pyKalfa.extension` klasorunun bir
   ustu).
4. Ayarlari kaydedip pyRevit'i **Reload** edin (veya Revit'i yeniden
   baslatin).

Bu adimdan sonra **baska hicbir sey yapmaniza gerek yok**: reload/acilis
sirasinda `startup.py` calisir ve `env/` kurulumunu kendiliginden
tamamlar (ilk kurulumda birkac dakika surebilir, bkz. yukarida). Kurulum
bitince ust menude yeni bir **pyKalfa** sekmesi, altinda **Parsel /
Bina** ve **Duvar** panelleri gorunmelidir.

Kurulum bu kadar -- bundan sonraki tum kullanim Revit icinden, tek
butonla yapilir.

## Kullanim: Parsel/Bina Aktar

1. Revit'te ilgili projeyi acin, geometri olusturmak istediginiz
   **plan, detay, kesit veya cephe view'ine** gecin (3D view'de
   `DetailLine` olusturulamaz, buton hata verir).
2. **pyKalfa** sekmesi -> **Parsel / Bina** paneli -> **"Parsel/Bina
   Aktar"** butonuna basin.
3. **Once butun girdiler alinir** -- sirasiyla acilan pencerelerde:
   - **parsel.png** dosyasini secin (ör. `assets/parsel.png`).
   - **bina.png** dosyasini secin (ör. `assets/bina.png`).
   - **Harita olcegini** girin -- sadece paydayi yazin (ör. 1:1000 icin
     `1000`, 1:500 icin `500`).
   - Listeden **parsel cizgileri icin bir line style** secin (projenizde
     tanimli olan "Lines" alt kategorilerinden, ör. "LIMITE
     PARCELLAIRE").
   - Listeden **binalar icin bir Filled Region Type** secin (ör. "CHAPE
     DE CIMENT").
   - Listeden **bir Text Note Type** secin (parsel numaralari icin).
4. **Sonra tek uzun islem calisir:** goruntu isleme bir **ilerleme
   cubugu** ile gosterilir; baslikta hangi asamada olundugu yazar
   (olcek -> parsel konturlari -> bina konturlari -> parsel cizgileri ->
   OCR -> yazma). Bu asamada size soru sorulmaz.
5. **En sonda geometri olusturulur:** secilen view'e parsel cizgileri
   (`DetailLine`), bina alanlari (`FilledRegion`) ve parsel numara
   etiketleri (`TextNote`) cizilir; kac cizgi/bina/etiket
   olusturuldugunu (ve kacinin atlandigini) gosteren bir ozet penceresi
   cikar.

**Neden bu sira?** Butun sorular basta toplanir ki uzun beklemenin
ortasinda diyalogla karsilasmayasiniz. Metin tipi de bu yuzden onden
sorulur (etiket bulunup bulunmadigi ancak islem sonunda belli olur).
Projenizde hic Text Note Type yoksa o soru atlanir ve **OCR hic
calistirilmaz** -- olusturulamayacak etiketler icin en uzun adimi
beklemek anlamsiz olurdu, bu da islemi belirgin sekilde hizlandirir.

> Surenin buyuk kismi OCR adiminda gecer (ornek dosyada ~8 saniyenin
> 7,5'i; ilk calistirmada model indirmesiyle dakikalar). Gercek OCR
> yuzdesi olculemedigi icin cubuk o asamada yavasca surunerek
> "calisiyorum" sinyali verir; baslikaki asama adi her zaman gercek
> durumu gosterir.

**Parsel etiketleri hakkinda:** bu OCR (metin okuma) ile yapilir ve
%100 dogru degildir (test edilen dogruluk ~%80) -- bazi benzer
karakterler (G/6, A/4, B/8, S/5 gibi) yanlis okunabilir. Olusturulan
`TextNote`'lari Revit'te orijinal parsel.png ile karsilastirip gerekirse
elle duzeltmeniz onerilir.

### Gecici dosyalar

Islem basarili olursa, Python <-> Revit arasindaki gecici devir-teslim
dosyalari (`pyKalfa.extension/output/revit_input.json`,
`.../revit_input_preview.png`) otomatik silinir. Bir hata olursa (islem
geri alinirsa) bu dosyalar debug icin o `output/` klasorunde kalir.

## Kullanim: Duvar Aktar

Polycam'in (veya baska bir CAD kaynagin) urettigi **kat plani DXF**'ini
gercek Revit duvarlarina cevirir -- `ModelCurve`/detay cizgisi degil,
uzerinde kapi/pencere acilabilen `Wall` elemanlari.

1. Revit'te projeyi acin ve duvarlarin gidecegi kata karsilik gelen bir
   **plan view**'ine gecin (duvarlar model elemani oldugu icin sart
   degil, ama sonucu gorebilmek icin pratiktir).
2. **pyKalfa** sekmesi -> **Duvar** paneli -> **"Duvar Aktar"**.
3. Sirasiyla:
   - **DXF dosyasini** secin.
   - (Sadece gerekirse) **cizim birimi**: DXF basliginda birim
     (`$INSUNITS`) yazmiyorsa, cizim boyutundan tahmin edilen birim
     onaya sunulur.
   - (Sadece gerekirse) **orijine tasima**: cizim Revit orijininden
     ~1.5 km'den uzaktaysa, hassasiyet sorunlarini onlemek icin cizimin
     tamamini orijine kaydirmayi onerir.
   - (Sadece gerekirse) **tek cizgi modu**: cizimde hic kapali duvar
     dis hatti yoksa, cizgileri dogrudan eksen saymayi onerir.
   - **Katman**: program en olasi duvar katmanini onerir (ör.
     "Poly-Walls (7 duvar, 29.3 m, kalinlik 10 cm)"). Kabul ederseniz tek
     tiklama; "Hayir" derseniz butun katmanlarin listesi acilip coklu
     secim yapabilirsiniz. **Bu adim onemli:** kapi/pencere katmanlari
     duvarla ayni sekilde cizildigi icin ancak burada ayrilabilir.
   - **Duvar yuksekligi** (metre, varsayilan 2.80).
   - **Level** (yuksekligiyle birlikte listelenir).
   - **Wall Type** (projede tanimli olanlardan; perde duvar tipleri
     listelenmez). Baslikta cizimden olculen kalinlik yazar.
4. Son onay penceresinde kac duvar, hangi tiple, hangi level'de ve
   olculen kalinligin ne oldugu yazar.
5. Islem bitince olusan/olusamayan duvar sayisi ve toplam duvar uzunlugu
   gosterilir. Olusturulamayan cizgiler pyRevit cikti penceresinde
   **katman, uzunluk, konum ve hata sebebiyle** tablo halinde listelenir.

Aktarimin tamami **tek bir transaction**'dir: sonuc begenilmezse Revit'te
tek bir "Undo" ile geri alinabilir.

### Duvarlar cizimden nasil okunuyor

Gercek kat plani ciktilarinda (Polycam dahil) bir duvar **iki ayri cizgi
degil, tek bir kapali dis hat (outline)** olarak cizilir: bir halka;
iki uzun kenari duvarin iki yuzu, kisa kenarlari komsu duvarlarla
birlesen uclari.

Duvar Aktar bu halkalari tanir ve her birinden **merkez ekseni + gercek
kalinligi** cikarir. Yani:

- Her fiziksel duvar icin **tek** bir Revit duvari olusur (iki yuz iki
  duvar olmaz).
- **Kalinlik cizimden olculur** ve size gosterilir (ör. "cizimde olculen:
  10 cm") -- boylece dogru `WallType`'i secebilirsiniz. Kalinlik
  dayatilmaz; duvarin gercek kalinligi sectiginiz tipten gelir.
- Ayni duvarin cizimde birden fazla kez yer alan **kopyalari elenir**
  (Polycam ciktisinda her duvar iki kez bulunuyor).
- Duvara benzemeyen nesneler (mobilya konturlari, oda poligonlari,
  olculendirme cizgileri) duvar sayilmaz: kalinlik makul bir duvar
  araliginda (3-80 cm) degilse veya sekil kare/kutu gibiyse elenir.

Bunun faydali bir yan etkisi: **yanlis birim secerseniz duvar bulunamaz**
(200 mm'lik duvar 200 m olur, makul araligin disina cikar) -- yani
sessizce 1000 kat buyuk duvar uretilmez.

**Kapi/pencere ayrimi katmanla yapilir.** Kapi, pencere ve gecisler
duvarla tamamen ayni sekilde cizildigi icin geometriden ayirt edilemez;
tek ayirt edici katmandir. Bu yuzden katman secimi bu isleve ozgu degil,
zorunlu bir adimdir. Program en olasi duvar katmanini onerir (adinda
"wall"/"duvar" gecen, yoksa en cok duvar uzunluguna sahip olan).

**Tek cizgi modu:** cizimde hic kapali duvar dis hatti yoksa program
"cizgileri dogrudan duvar ekseni sayayim mi?" diye sorar. Bu modda
kalinlik olculemez ve mobilya/olcu cizgileri de duvara donusebilir; o
yuzden sadece duvarlari tek cizgiyle cizilmis planlar icindir. Bu modda
ek temizlik yapilir: ~5 mm'lik uc nokta farklari kaynatilir, tekrar eden
cizgiler atilir, ayni dogru uzerindeki parcalar birlestirilir ve 20
cm'den kisa parcalar elenir (esikler `pysrc/duvar/geometry.py` basindaki
`DEFAULT_*` sabitleri).

**Beklenti:** sonuc mimari olarak %100 dogru degildir -- amac duvarlarin
buyuk cogunlugunun dogru yerde olmasi, kalan duzeltmelerin Revit icinde
elle yapilmasidir. Kapi/pencere bosluklari duvardan cikarilmaz (Revit'te
kapi/pencere ailesi zaten duvari keser); egri (bulge) duvarlar kirisle
temsil edilir.

## Klasor yapisi

| Klasor/Dosya | Icerik |
| --- | --- |
| `assets/` | Ornek kadastro goruntuleri (`parsel.png`, `bina.png`) -- sadece referans/deneme icin, calismasi icin sart degil. |
| `revit/pyKalfa.extension/` | **Kendi kendine yeterli** pyRevit extension'i -- tek basina alinip kullanilabilir. |
| `.../pyKalfa.tab/` | Sekme; her panel bir islev grubu, her pushbutton bir islev. |
| `.../lib/pykalfa/` | Revit tarafi kod: kokunde ortak moduller, `<islev>/` altinda isleve ozel olanlar (asagida detay). |
| `.../pysrc/<islev>/` | Islev bazli agir CPython kodu (`parsel_bina/`, `duvar/`; asagida detay). |
| `.../requirements.txt` | `pysrc` bagimliliklari (butun islevler icin ortak). |
| `.../env/` | Python sanal ortami (git'e dahil degil, ilk calistirmada otomatik olusur). |
| `.../output/` | Uretilen ara/debug dosyalari (basarili aktarimdan sonra otomatik silinir). |
| `ROADMAP.md` | Proje gelisim gunlugu ve yol haritasi. |

### `lib/pykalfa/` -- ortak kutuphane

pyRevit bir extension'in `lib/` klasorunu otomatik olarak `sys.path`'e
ekler; bu yuzden her buton dogrudan `from pykalfa import ...` diyebilir.

| Modul | Icerik |
| --- | --- |
| `paths.py` | Extension icindeki standart yollar (`env/`, `pysrc/<islev>/`, `output/`). Yollar modulun kendi konumundan turetilir, sabit yol varsayilmaz. |
| `subproc.py` | Alt-surec calistirma (`run_process`) ve `env/` python'i ile script calistirma (`run_python`). |
| `bootstrap.py` | `env/` yoksa ilk kurulumu yapar (`ensure_env`), ilerleme cubugu ile. |
| `revitutils.py` | `elem_name`, uyari yutucu (`WarningSwallower`), aktif view kontrolu, kucuk geometri yardimcilari. |
| `selectors.py` | Projede ONCEDEN tanimli stil/tipleri sectirme (`pick_line_style`, `pick_filled_region_type`, `pick_text_note_type`, `pick_level`, `pick_wall_type`). |
| `duvar/ui.py` | *(isleve ozel)* Duvar Aktar'in butun diyaloglari: dosya, birim, yukseklik, katman filtresi, onaylar, sonuc raporu. |
| `duvar/revit_creator.py` | *(isleve ozel)* Duvar adaylarindan `Wall.Create` ile duvar uretimi; tek tek hata yakalama ve rapor. |

### `pysrc/parsel_bina/` icindeki scriptler

Gunluk kullanimda hicbirini elle calistirmaniza gerek yok (pyRevit butonu
`prepare_revit_input.py`'yi kendisi cagirir). Bunlar tani/debug ve
gelistirme amaclidir:

| Script | Ne yapar |
| --- | --- |
| `detect_lines.py` | Genel amacli cizgi/kontur tespiti; `output/*_mask.png`, `*_edges.png`, `*_contours.png` gorsellerini uretir. |
| `geometry.py` | Katman-bazli temiz kontur/cizgi cikarimi (`extract_parcels`, `extract_buildings`, `extract_parcel_lines`). Diger scriptler bunu kullanir. |
| `scale.py` | Olcek cubugu tespiti ve metre/piksel hesabi (`--scale` parametresiyle). |
| `associate.py` | Parsel-bina iliskilendirme (Faz 2), `output/parsel_bina_eslesme.json` ve gorsel uretir. |
| `ocr_labels.py` | Parsel numara etiketlerini (ör. "591G") OCR (EasyOCR) ile okur. |
| `prepare_revit_input.py` | **Asil aractir.** Yukaridakileri birlestirip `output/revit_input.json`'i uretir; pyRevit butonu bunu cagirir. |

Manuel test etmek isterseniz (Revit acmadan, sadece ciktiyi kontrol
etmek icin), `revit\pyKalfa.extension\` klasorunun icinden:

```powershell
env\Scripts\python.exe pysrc\parsel_bina\prepare_revit_input.py --scale 1000 --parsel ..\..\assets\parsel.png --bina ..\..\assets\bina.png
```

### `pysrc/duvar/` icindeki scriptler

| Script | Ne yapar |
| --- | --- |
| `dxf_reader.py` | ezdxf ile DXF okur: LINE/LWPOLYLINE/POLYLINE -> `Poly` nesneleri (**polyline butunlugu korunur**, duvar tespiti buna dayanir). Blok referanslarini (INSERT) patlatir, OCS->WCS cevirir, `$INSUNITS` birimini tespit eder. |
| `geometry.py` | Birim donusumu (-> feet) ve tek cizgi modu temizligi: uc nokta kaynatma, tekrar/dejenere atma, kolinear birlestirme, kisa parca filtresi. Butun toleranslarin (`DEFAULT_*`) tanimli oldugu yer. |
| `wall_detector.py` | **Duvar karari.** Kapali dis hattan merkez eksen + olculen kalinlik cikarir, kopyalari eler, duvara benzemeyenleri (mobilya, oda poligonu) reddeder. |
| `prepare_wall_input.py` | **Asil aractir.** Zinciri calistirip `output/wall_input.json`'i uretir; pyRevit butonu bunu cagirir. |
| `selftest.py` | Sentetik bir DXF uretip butun zinciri dogrular -- Revit gerekmez. |

Kendi DXF'inizi Revit acmadan denemek icin
(`revit\pyKalfa.extension\` icinden):

```powershell
env\Scripts\python.exe pysrc\duvar\selftest.py
env\Scripts\python.exe pysrc\duvar\prepare_wall_input.py --dxf C:\yol\plan.dxf --output-dir output
```

Faydali parametreler: `--units mm|cm|m|in|ft` (birimi elle ver),
`--lines` (tek cizgi modu), `--recenter` (cizimi orijine tasi). Tek
cizgi moduna ozel: `--min-length 0.3` (metre; daha agresif kisa cizgi
filtresi), `--merge-gap 0.1` (metre; ayni dogru uzerinde daha buyuk
bosluklari da koprule).

Duvar tanima esikleri (kalinlik araligi, paralellik toleransi, en/boy
orani) `pysrc/duvar/wall_detector.py` basindaki sabitlerdedir.

## Yeni buton (islev) ekleme

Her islev kendi klasorunde durur; ortak kod `lib/pykalfa/` altindadir.
Duvar Aktar bu tarifin birebir ornegidir -- yeni bir islev eklerken ona
bakmak en hizli yoldur.

1. **Butonu olusturun:** `pyKalfa.tab/` altinda islev grubu icin bir
   panel (ör. `Cizim.panel/`), onun icinde bir pushbutton klasoru
   (`YeniIslev.pushbutton/`) acin. Icine `script.py`, `bundle.yaml`
   (`title` + `tooltip`) ve bir `icon.png` (96x96 kullaniliyor) koyun.
   Panel adini ozellestirmek isterseniz panel klasorune de bir
   `bundle.yaml` (`title: ...`) koyabilirsiniz.
2. **Is akisini `script.py`'ye yazin.** Ortak islere hazir fonksiyonlari
   kullanin:

   ```python
   from pykalfa import bootstrap, paths, selectors
   from pykalfa.revitutils import WarningSwallower, require_draftable_view

   require_draftable_view(view)
   line_style = selectors.pick_line_style(doc, title="Duvar cizgisi stili secin")
   ```
3. **Agir Python isi varsa** (goruntu isleme, ML, ...) kodunu
   `pysrc/<islev_adi>/` altina koyun, bagimliliklarini ortak
   `requirements.txt`'e ekleyin ve butondan soyle cagirin:

   ```python
   bootstrap.ensure_env()   # env/ yoksa kurar
   exit_code, out = run_python(paths.pysrc_script("duvar", "hesapla.py"), ["--foo", "bar"])
   ```

   Agir Python isi YOKSA `bootstrap.ensure_env()` cagirmayin -- buton o
   zaman 1-1.5 GB'lik ortama hic ihtiyac duymadan calisir.
4. **`script.py` sismeye baslarsa** isleve ozel Revit tarafi kodu
   `lib/pykalfa/<islev>/` altina alin (Duvar Aktar'da `ui.py` ve
   `revit_creator.py` boyle ayrildi). pyRevit `lib/`'i otomatik
   `sys.path`'e ekledigi icin `from pykalfa.<islev> import ...` calisir;
   pushbutton klasorunun yaninda duran modulleri import etmeye
   guvenmeyin.
5. pyRevit'i **Reload** edin; yeni buton sekmede gorunur.

Birden fazla islevin isine yarayacak bir sey yaziyorsaniz
`lib/pykalfa/` kokune koyun (ör. yeni bir `pick_*` secici); tek isleve
ait olan seyler ise `lib/pykalfa/<islev>/` altinda veya `script.py`'de
kalsin.

## Sorun giderme

| Belirti | Olasi neden / cozum |
| --- | --- |
| Buton "Aktif view bir plan/detay/kesit/cephe view'i olmali" diyor | 3D view'desiniz; bir plan/detay/kesit/cephe view'ine gecip tekrar deneyin. |
| "pyKalfa ilk kurulum/guncelleme yapiliyor..." uzun suruyor / sonra hata veriyor | `env/` kurulumu Revit acilirken/pyRevit reload edilirken `startup.py` tarafindan otomatik yapiliyor (internet baglantisi gerekir, birkac dakika surebilir). "pyKalfa otomatik kurulumu basarisiz oldu" hatasi alirsaniz: sisteminizde Python 3 kurulu oldugundan emin olun (python.org, "Add python.exe to PATH" isaretli), ayrinti icin `C:\pyKalfa\install.log` dosyasina bakin, sonra Revit'i yeniden baslatin. |
| "Goruntu isleme basarisiz oldu" (stdout/stderr ile) | Popup'taki hata metnini okuyun -- genelde yanlis dosya yolu veya gecersiz olcek degeridir. |
| "Projede tanimli bir line style / Filled Region Type / Text Note Type bulunamadi" | Revit projenizde en az bir ozel "Lines" alt kategorisi, bir Filled Region Type ve (etiket varsa) bir Text Note Type tanimli olmali (Manage > Object Styles / Additional Settings). |
| Sonuc gorsel olarak beklenmedik (ççift cizgi, eksik parsel vb.) | `output/revit_input_preview.png`'yi (hata sonrasi kalirsa) acip kontrol edin; `ROADMAP.md`'deki "bilinen sinirlar" bolumune bakin. |
| Bazi parsel etiketleri (metin) yanlis/anlamsiz | OCR %100 dogru degildir (~%80 test edildi); benzer karakterler (G/6, A/4, B/8, S/5) karisabilir. `revit_input.json`'daki (hata sonrasi kalirsa) `labels[].confidence` degeri dusukse (<0.5) o okuma supheli demektir. |
| Etiket adimi cok uzun suruyor / hic bitmiyor | Ilk calistirmada OCR modeli internetten indiriliyor olabilir (birkac dakika). `--no-labels` ile (`prepare_revit_input.py --no-labels ...`) etiketleri kapatip test edebilirsiniz. |

### Duvar Aktar'a ozel

| Belirti | Olasi neden / cozum |
| --- | --- |
| **Her duvarin yerinde iki ince duvar var** | Bu, dis hat tanima calismadiginda (tek cizgi moduna dusuldugunde) olur: duvarin iki yuzu iki duvar sayilir. `prepare_wall_input.py --dxf ...` ciktisindaki "dis hat duvari" sayisina bakin; 0 ise duvarlar kapali halka olarak cizilmemis demektir. |
| "Duvara donusturulebilecek geometri bulunamadi" | Cizimde kapali duvar dis hatti yok. Buton tek cizgi modunu onerecektir; o da bir sey bulmazsa DXF'te sadece SPLINE/ARC/HATCH olabilir (bu surumde desteklenmiyor). |
| Duvar bulunamiyor ama cizimde duvar var | Yanlis birim secilmis olabilir: 200 mm'lik duvar "m" olarak okununca 200 m kalinlik olur ve makul araligin disina duser. Dogru birimi secip tekrar deneyin. |
| Duvarlar Revit'te cok uzakta / "cok buyuk koordinat" uyarilari | Cizim orijinden uzak. Buton sordugunda "orijine tasi" deyin. |
| Kapi/pencere yerlerinde de duvar olusmus | Katman secim adiminda kapi/pencere katmanlari da secilmis. Bunlar duvarla ayni sekilde cizildigi icin ancak katmanla ayrilabilir; **Ctrl+Z** ile geri alip sadece duvar katmanini secin. |
| Mobilya/olculendirme cizgileri de duvar olmus | Tek cizgi modundasiniz ve fazla katman sectiniz. Dis hat modu bunlari zaten eler. |
| Bir duvar olmasi gereken yerde onlarca kisa duvar var | Tek cizgi modunda kolinear birlestirme o cizgileri ayni dogru saymamis. `--merge-gap` ve `--angle-tol` degerlerini buyutup `prepare_wall_input.py --lines` ile deneyin. |
| Bazi duvarlar olusmadi | pyRevit cikti penceresindeki tabloya bakin: her satirda katman, uzunluk, konum ve Revit'in verdigi hata yazar. Genelde sebep cok kisa cizgi veya duvar tipinin kabul etmedigi bir durumdur. |

## Bagimliliklar

`requirements.txt` (hepsi `env/` sanal ortamina kurulur; butun islevler
ayni ortami paylasir):

- `opencv-python-headless` -- goruntu isleme (esikleme, kontur cikarma).
  *Parsel/Bina Aktar.*
- `numpy` -- dizi islemleri. *Parsel/Bina Aktar.*
- `scikit-image` -- iskeletlestirme (`skeletonize`). *Parsel/Bina Aktar.*
- `easyocr` -- parsel numara etiketlerini okuma (OCR); agir (PyTorch
  bagimliligi, ~1-1.5 GB), ilk kullanimda ayrica model indirir.
  *Parsel/Bina Aktar.*
- `ezdxf` -- DXF okuma (hafif, saf Python). *Duvar Aktar.*

## Lisans

Bu projenin kodu [MIT Lisansi](LICENSE) ile lisanslanmistir.

**Not:** `assets/` klasorundeki ornek gorseller ("AGDP (2024), IGN"
filigranli parsel.png/bina.png) Fransiz kadastro/IGN kaynaklidir ve
kendi veri lisansina tabi olabilir -- bu MIT lisansinin kapsami disindadir.
Bu ornekleri baska bir yerde yeniden dagitmadan once IGN'in veri kullanim
sartlarini kontrol edin; kendi projenizde kendi parsel/bina gorsellerinizi
kullanmanizda bir sakinca yoktur.
