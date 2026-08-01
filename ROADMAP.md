# pyKalfa - Yol Haritasi

Amac: Revit icin, birden fazla yardimci islevi tek catida toplayan bir
pyRevit eklentisi. Ilk islev ("Parsel/Bina Aktar"): `assets/` altindaki
kadastro goruntulerinden (parsel ve bina sinirlari) OpenCV (cv2) ile
cizgi/kontur tespiti yaparak bu sinirlari dijital poligonlara donusturup
Revit'e aktarmak.

> **Not (Faz 9):** Faz 0-8 boyunca proje `pyParcelTrace` adiyla, tek
> islevli bir arac olarak gelistirildi. Faz 9'da ad `pyKalfa` olarak
> degistirildi ve yapi cok islevli hale getirildi; asagidaki eski faz
> notlarindaki isim/yol referanslari yeni ada gore guncellenmistir.

## Faz 0 - Ortam Kurulumu (Tamamlandi)

- [x] `env/` adinda venv olusturuldu (Python 3.14).
- [x] `opencv-python-headless`, `numpy` kuruldu -> `requirements.txt`.
- [x] Proje iskeleti: `src/`, `output/`, `assets/`.

## Faz 1 - Temel Cizgi/Kontur Yakalama (Tamamlandi)

- [x] `src/detect_lines.py`: goruntuyu okur (alfa kanalini beyaz zemine
      duzlestirir), gri tonlamaya cevirir, esikleme (threshold) ile
      cizgi/metin pikselini ayirir.
- [x] Baglantili bilesen analiziyle (connected components) kucuk/kompakt
      bilesenler (metin etiketleri, parsel/bina numaralari) elenir.
- [x] Morfolojik kapama ile cizgilerdeki kucuk kopukluklar giderilir.
- [x] `cv2.findContours` ile kapali/acik konturlar (parsel ve bina sinirlari)
      cikarilir, `cv2.approxPolyDP` ile sadelestirilir.
- [x] Ciktilar `output/` klasorune yazilir:
      `*_mask.png`, `*_edges.png`, `*_contours.png`, `*_polygons.json`.

**Bilinen sinirlar:** Olcek cubugu, kuzey oku ve harita disi metinler (ör.
"AGDP (2024), IGN") suanki filtreden tam gecmeyebilir; bazi kucuk gurultu
konturlari kalabilir.

## Faz 2 - Parsel-Bina Iliskilendirme (Tamamlandi)

- [x] `src/associate.py`: parsel.png ve bina.png ayni piksel boyutunda
      oldugu icin (ortak referans), ek hizalama/donusum yapilmadan
      dogrudan ayni koordinat sisteminde islenir.
- [x] Her binanin agirlik merkezi (centroid) hesaplanip
      `cv2.pointPolygonTest` ile hangi parsel konturunun icinde kaldigi
      bulunur; birden fazla parsele "giren" durumlarda en kucuk (en
      spesifik) parsel esleme olarak secilir.
- [x] Agin dis hattini/dev artefakt konturlarini (goruntu alaninin
      %50'sinden buyuk) eslesmeden haric tutuldu.
- [x] Ciktilar `output/` klasorune yazilir:
      `parsel_bina_birlesim.png` (parsel=turuncu, bina=mavi cizgi;
      eslesen bina=yesil dolgu, eslesmeyen bina=kirmizi dolgu) ve
      `parsel_bina_eslesme.json` (parsel<->bina id eslesmesi, alan,
      centroid).

**Bilinen sinirlar:** Goruntu kirpma sinirinda acik kalan (kapanmamis)
parsel sinirlari icin kontur bir "delik" olusturmadigindan, o parsel
icindeki binalar eslesmeyen (kirmizi) olarak isaretlenebilir.

## Faz 3 - Geometri Iyilestirme ve Olcek Kalibrasyonu (Tamamlandi)

pyRevit'te `DetailLine`/`FilledRegion` olusturmadan once gerekli hazirlik
adimlari. Iki katmanin Revit'teki hedefi farkli oldugu icin cikarim
yontemi de katmana gore ayrildi:

- **Parsel -> `DetailLine`:** sinirlar duz cizgi olarak cizilecek, kapali
  bir alan/dolgu degil. Bu yuzden kapaniklik aranmaz; agin butun
  cizgileri (goruntu kenarina degen acik parseller dahil) polyline
  olarak alinir. Sadece agin kendi dis hattini temsil eden dev artefakt
  kontur (goruntu alaninin >%50'si) elenir.
- **Bina -> `FilledRegion`:** her bina ayri, kapali bir dolgu alani
  olacak; bu yuzden her izole bina icin tek (dis hat) kontur gerekir.

- [x] `src/geometry.py`: `extract_buildings()` -> `cv2.RETR_EXTERNAL` ile
      her bina icin tek dis hat kontur (ic/dis cift kontur sorunu cozuldu,
      274 -> 67 tekil kontur, FilledRegion'a hazir).
      `extract_parcels()` -> `cv2.RETR_LIST` ile agin butun cizgileri
      (kenardakiler dahil) alinir, yalniz dev artefakt kontur elenir
      (DetailLine'a hazir, 92 kontur).
      **Not:** Ilk denemede parsel icin de bina gibi "hole" bazli
      (`RETR_CCOMP`, sadece cocuk konturlar) bir filtre kullanilmisti;
      ancak bu, goruntu kenarina degen/acik parselleri tamamen
      kaybettirdi (RETR_CCOMP'ta kenara degen bosluklar "hole" degil
      ust-seviye/parent=-1 sayiliyor). Cizgi hedefi icin kapaniklik zaten
      gerekmedigi fark edilince `RETR_LIST`'e donuldu.
- [x] `src/scale.py`: kullanici harita olcegini CLI parametresi olarak
      girer (`--scale 1000` = 1:1000); OCR/otomatik tahmin yok. Gercek
      metre karsiligi IGN kuraliyla hesaplanir (1:1000 -> 20 m,
      1:500 -> 10 m, yani `gercek_m = olcek / 50`). Goruntudeki olcek
      cubugunun piksel uzunlugu sabit navy renginden (BGR ~ (131,85,39))
      renk+sekil bazli (genis/dolu dikdortgen) otomatik olculur; boylece
      `metre/piksel = gercek_m / cubuk_px` hesaplanir.
- [x] `src/prepare_revit_input.py`: olcek SADECE parsel goruntusunden bir
      kez hesaplanip her iki katmana da uygulanir (katman basina ayri
      olcum, anti-alias kaynakli ~1 piksellik sapmayla tutarsizlik
      yaratiyordu). Kontur sadelestirme gercek dunya biriminde sabit
      tolerans (~15 cm) ile yapilir (`approxPolyDP` epsilon'u piksele
      donusturulerek). Piksel Y-ekseni (asagi artan) -> Revit Y-ekseni
      (yukari artan) donusumu ve metre -> feet cevrimi uygulanir. Parsel-
      bina iliskisi (Faz 2 mantigi) artik temiz konturlarla yeniden
      hesaplanir.
- [x] `src/associate.py` (Faz 2) `geometry.py`'nin katman-bazli kontur
      cikarimini kullanacak sekilde guncellendi (dev artefakt filtresi
      artik `geometry.extract_parcels()` icinde, tek yerde).
- [x] Ciktilar `output/` klasorune yazilir: `revit_input.json` (olcek
      bilgisi, katman basina `id`, `area_m2`, `vertices_ft`,
      parsel<->bina iliskisi) ve `revit_input_preview.png` (gorsel
      dogrulama).

**Gercek Revit testinde cikan 3. sorun (duzeltildi):** parsel numara
etiketleri (ör. "1024W") parsel cizgisi saniliyordu ve komsu iki parselin
ortak siniri iki kez (hafif kaymis) ciziliyordu. Iki ayri kok neden ve
duzeltme:
1. **Metin/etiket sorunu:** genel grayscale esikleme (`build_line_mask`)
   metni de "cizgi" sayiyordu (renk ayrimi yok). `geometry.py`'ye
   `build_parcel_line_mask()` eklendi: parsel cizgileri gorselde
   kirmizimsi/kahverengi (R kanali G/B'den belirgin yuksek), etiketler
   ise notr gri/siyah (R~G~B) -- sadece kirmizimsi pikseller alinarak
   metin/kuzey oku/olcek cubugu (hepsi notr/lacivert) bastan disarida
   birakilir. `extract_parcels()` artik bu maskeyi kullanir (bina tarafi
   etkilenmedi, orada etiket sorunu yoktu).
2. **Ortak sinir cift cizim sorunu:** komsu iki parsel, ortak sinirlarini
   kendi konturlerinde ayri ayri (cizginin iki farkli tarafindan) izliyor,
   bu da DetailLine'a cevrilince neredeyse ayni yerde iki segment
   olusturuyordu.
   - Ilk deneme: maskeyi `skimage.morphology.skeletonize` ile 1 piksele
     inceltip (yeni bagimlilik: `scikit-image`) kaymayi azaltmak, sonra
     `prepare_revit_input.py`'de tum parsellerin kenarlarini tek global
     listede toplayip ayni aci+yakin orta nokta+benzer uzunluktaki
     segmentleri birlestirmek (`_dedupe_parcel_segments`, 1036->938
     segment). **Yetersiz kaldi:** komsu iki parsel ayni fiziksel siniri
     bagimsiz sadelestirdigi (approxPolyDP) icin farkli noktalardan
     bolunebiliyor, segment uzunluklari/orta noktalari tam ortusmuyor.
   - Kalici cozum: kontur tabanli yaklasim (her parselin KENDI kapali
     bolgesini ayri ayri izlemek) tamamen degistirildi. `geometry.py`'ye
     `extract_parcel_lines()` eklendi: 1 piksellik iskelet bir GRAF olarak
     ele alinir (dugumler = uc noktalar/kesisimler, kenarlar = aralarindaki
     yollar), her fiziksel cizgi -- kac parsel paylasirsa paylassin --
     tam olarak BIR KEZ izlenir. Boylece "iki farkli tarafindan izleme"
     sorunu yapisal olarak ortadan kalkar, sonradan duzeltmeye gerek
     kalmaz. `extract_parcels()` (kapali kontur) sadece parsel-bina
     eslesmesi/alan hesabi icin kaldi; DetailLine cizimi
     `extract_parcel_lines()`'dan gelen `parcel_lines`'i kullanir.

**Bilinen sinirlar:**
- Birbirine (8-baglantili raster anlaminda) fiilen degen/cok yakin
  binalar `RETR_EXTERNAL` ile tek bir kontur/footprint olarak birlesir
  (ör. bitisik siralarin ayrimi kaybolabilir); bu, kontur cikariminin
  degil kaynak cizimin cozunurlugunun bir sinirlamasidir.
- Goruntu kirpma sinirinda acik kalan parsel sinirlari artik `DetailLine`
  cizimi icin dogru sekilde ciziliyor (RETR_LIST sayesinde), ama bu
  bolgelerdeki binalarin parsel-eslesmesi (point-in-polygon) hala
  guvenilmez olabilir (Faz 2'den kalan sinirlama, sadece eslesme adimini
  etkiler).
- Olcek cubugu tespiti bu iki gorsele (navy renk, ~75px @ 1:1000) gore
  kalibre edildi; farkli renk/temada bir kaynaktan gelen goruntülerde
  `BAR_COLOR_*` esiklerinin (`src/scale.py`) gozden gecirilmesi gerekir.

## Faz 4 - pyRevit Entegrasyonu (Tamamlandi)

pyRevit klasor yapisi: `revit/pyKalfa.extension/pyKalfa.tab/
ParselBina.panel/ImportGeometry.pushbutton/`. IronPython 2.7 ile yazildi
(pyRevit'in her kurulumunda calisan varsayilan motor; ekstra CPython3
engine kurulumu gerekmez).

Gercek Revit 2026 + pyRevit ortaminda test edildi ve calisir durumda
("Tamam güzel çalışıyor" -- kullanici onayi). Asagidaki bilinen sorunlar
bu surecte bulunup duzeltildi (detaylar altta).

- [x] Tum girdiler dogrudan Revit icinden alinir -- ayrica manuel olarak
      venv'de `prepare_revit_input.py` calistirmaya gerek yok:
      `script.py` sirasiyla `forms.pick_file()` ile parsel.png,
      `forms.pick_file()` ile bina.png, `forms.ask_for_string()` ile
      harita olcegini (ör. 1000) ister. Sonra proje kokunu
      (`src/prepare_revit_input.py`'nin bulundugu klasoru yukari dogru
      arayarak, `_find_project_root()`) bulup `env/Scripts/python.exe`
      ile `prepare_revit_input.py`'yi bir alt-surec (`System.Diagnostics.Process`)
      olarak calistirir (goruntu isleme -- cv2/numpy/scikit-image --
      IronPython'da degil, bu ayri CPython venv'inde yapilir), stdout/
      stderr'i loglar, basarisiz olursa (exit code != 0 veya JSON
      olusmadiysa) tam ciktiyi gosteren bir hata popup'i verir. Basarili
      olursa uretilen `output/revit_input.json` otomatik okunur.
- [x] Line style (parsel) ve Filled Region Type (bina) **koda gomulmez**;
      script calisirken projede o an var olan stiller arasindan
      `forms.SelectFromList` ile kullaniciya secmesi icin listelenir
      (ör. kullanicinin projesindeki "LIMITE PARCELLAIRE" line style'i,
      "CHAPE DE CIMENT" filled region type'i) -- boylece proje/sablon
      degisse bile script degismeden calisir.
- [x] Parsel: her segment icin ayri `DetailCurve` (`doc.Create.NewDetailCurve`),
      secilen line style `CurveElement.LineStyle` ile atanir.
- [x] Bina: her biri icin ayri kapali `CurveLoop` -> `FilledRegion.Create`.
- [x] Aktif view turu kontrol edilir (plan/detay/kesit/cephe olmali, 3D
      view'de DetailCurve olusturulamaz).
- [x] Gecersiz/kapanmayan loop'lar ve olusturulamayan cizgiler
      `try/except` ile atlanip sayilir; islem sonunda ozet popup
      (`kac cizgi/bina olusturuldu, kac atlandi`) gosterilir; herhangi bir
      hata durumunda `Transaction` tamamen geri alinir (`RollBack`).
- [x] Basarili `Commit()` sonrasi devir-teslim dosyalari
      (`output/revit_input.json`, `output/revit_input_preview.png`)
      otomatik silinir -- bunlar sadece Python venv <-> Revit arasindaki
      gecici ara format, her calistirmada yeniden uretiliyor. Hata
      durumunda (RollBack) silinmez, debug icin kalir. Diger eski
      debug ciktilarina (mask/edges/contours vb.) dokunulmaz.

- [x] Kullaniciyla birlikte gercek Revit 2026 ortaminda test edildi,
      cikan hatalar (asagida 1-3) duzeltildi.

**Gercek testte cikan 1. sorun (duzeltildi):** ilk denemede
parsel line style secildikten hemen sonra Revit "Geometry" basligiyla bir
uyari gosterip ardindan cokuyordu ("unrecoverable error"). Kok neden:
`prepare_revit_input.py`'deki sadelestirme toleransi (`SIMPLIFY_TOLERANCE_M
= 0.15` m) piksel karsiligi 1 pikselin altinda kaliyordu, yani neredeyse
hic sadelestirme yapmiyordu -> 92 parselde toplam 8594 nokta/segment (parsel
basina ort. 93 nokta). Bu kadar yogun/bitisik segment Revit'i cokertebiliyor.
Iki duzeltme yapildi:
1. `prepare_revit_input.py`: tolerans 0.4 m'ye cikarildi ve ardisik
   noktalari (>=0.1 m araliktan yakinsa) birlestiren bir temizleme adimi
   eklendi -> ayni 92 parsel icin toplam nokta 8594'ten 1184'e dustu
   (parsel basina ort. ~13), min segment uzunlugu 0.86 ft'ten 1.93 ft'e
   cikti (sifira yakin segment kalmadi).
2. `script.py`: `MIN_SEGMENT_LENGTH_FT` (0.05 ft) altindaki segmentler
   ekstra bir guvenlik onlemi olarak atlaniyor; `Transaction`'a
   `IFailuresPreprocessor` (`WarningSwallower`) eklendi -- commit
   sirasinda cikan UYARILARI (hatalari degil) otomatik siler, boylece
   modal "Geometry" diyalogu akisi kesmiyor.

**Gercek testte cikan 2. sorun (duzeltildi):** yukaridaki
duzeltmeden sonra tam traceback alindi: `rt.Name` satirinda
`AttributeError: Name`. Sebep: Revit API'de `FilledRegionType.Name`
(Element uzerinden gelen, explicit interface implementasyonu ile
tanimli) IronPython'da dogrudan `.Name` seklinde erisilemiyor -- bilinen
bir pyRevit/IronPython tuhafligi. Standart cozum: `Element.Name.__get__(el)`.
`_elem_name()` yardimci fonksiyonu eklendi (once `el.Name` dener, olmazsa
bu descriptor'a duser); hem line style hem filled region type isimleri
icin kullaniliyor.

**Gercek testte cikan 3. sorun (duzeltildi):** parsel numara etiketleri
metin sanildi ve komsu parsellerin ortak siniri iki kez ciziliyordu --
bkz. Faz 3'teki "Gercek Revit testinde cikan 3. sorun" (renk bazli
maske + iskelet-grafigi tabanli cizgi cikarimi ile cozuldu).

**Denendi ama vazgecildi:** kaynak veriyi tek bir birlesik gorselden
(`assets/parsel_bina_both.png`, parsel+bina ayni renkte tek katmanda)
almak istendi. Baglanti bilesen boyutu ve kontur hiyerarsi derinligi ile
otomatik ayrim denendi; guvenilir cikmadi (67 binadan sadece 4'u temiz
ayrilabildi, geri kalani parsel agiyla karisiyor -- bircok bina parsel
cizgisine değecek kadar yakin/bitisik). Karar: ayri `parsel.png` +
`bina.png` dosyalariyla devam edilecek; birlesik gorsel sadece gorsel
referans olarak `assets/` altinda duruyor, pipeline'da kullanilmiyor.

## Faz 5 - Paketleme ve Kullanim (Tamamlandi)

Gercek kullanim artik Revit-tetikli oldugu icin (Faz 4), asil ihtiyac
"tek python komutuyla toplu CLI" degil, **kurulumu ve gunluk kullanimi
mumkun oldugunca basitlestirmekti**:

- [x] `setup.ps1`: `env/` sanal ortamini olusturur (yoksa) ve
      `requirements.txt`'i kurar -- kurulum tek komuta indi
      (`.\setup.ps1`).
- [x] **Elle `setup.ps1` calistirmaya bile gerek kalmadi:** `script.py`
      butona ilk basildiginda `env/Scripts/python.exe` yoksa bunu fark
      edip kendisi `_bootstrap_venv()` ile sistemde bir Python bulur
      (`py`/`python`/`python3`, `_find_system_python()`), `env/`'i
      olusturur ve `requirements.txt`'i kurar (aynen `setup.ps1` gibi,
      ama tetikleyici kullanicidan degil script'ten). Kullaniciya once
      "ilk kurulum yapiliyor, birkac dakika surebilir" bilgi penceresi
      gosterilir; basarisiz olursa (ör. sistemde Python yok) hata
      mesaji + `setup.ps1`'i elle calistirma onerisiyle biter.
      Test edildi: izole bir klasorde ayni venv-olustur+pip-kur
      dizisi (`py -m venv env` + `pip install -r requirements.txt`)
      calistirilip dogrulandi.
- [x] `README.md`: kurulum (bir kereye mahsus: `setup.ps1` + pyRevit
      extension'ini tanitma) ve kullanim (her seferinde: buton -> parsel
      png -> bina png -> olcek -> line style -> filled region type)
      adim adim anlatilir; `src/` altindaki her scriptin ne ise yaradigi
      bir tabloda ozetlenir; sorun giderme tablosu eklendi.
- [x] Tek giris noktasi zaten mevcut: gunluk kullanicinin hicbir CLI
      komutu calistirmasina gerek yok (pyRevit butonu
      `prepare_revit_input.py`'yi kendisi cagirir); bu yuzden ayrica bir
      `python -m pyparceltrace` paketlemesi eklenmedi -- gercek kullanim
      deseniyle uyusmayacakti. Manuel/gelismis kullanim icin
      `prepare_revit_input.py` zaten tek/yeterli giris noktasi.
- [x] Gorsel onizleme zaten Faz 3'ten beri var (`revit_input_preview.png`,
      basarili Revit aktariminda otomatik silinir, hata durumunda kalir).

## Faz 6 - Genel Kullanima Acma (GitHub Release) (Tamamlandi)

Proje GitHub'da public olarak paylasilmak uzere hazirlandi.

- [x] `LICENSE`: MIT lisansi eklendi (telif sahibi: cmldk).
- [x] `requirements.txt`: sabit `==` sürüm pinleri `>=` minimum surumlere
      gevsetildi (`opencv-python-headless>=4.9`, `numpy>=1.26`,
      `scikit-image>=0.22`) -- farkli Python surumu olan kullanicilarda
      "bu tam surum bulunamadi" kurulum hatasi riskini azaltir.
- [x] Kod icinde hardcoded kisisel/yerel yol (ör. kullanicinin kendi
      `C:\Users\...` yolu) olmadigi dogrulandi (grep ile tarandi, temiz).
- [x] `README.md`'ye Lisans bolumu eklendi: kod MIT, ama `assets/`
      altindaki ornek IGN gorsellerinin (parsel.png/bina.png, "AGDP
      (2024), IGN" filigrali) kendi veri lisansina tabi olabilecegi ve
      yeniden dagitmadan once kontrol edilmesi gerektigi acikca belirtildi.
- [ ] **Kullanicinin kendisi yapacak:** IGN/AGDP veri lisansini kontrol
      edip `assets/parsel.png` + `bina.png`'in public repoda kalip
      kalamayacagina karar verme (bu konuda henuz karar verilmedi,
      bilerek ertelendi).
- [ ] Istege bagli/kullaniciya birakildi: GitHub'da repo olusturup
      `v1.0.0` gibi bir tag/release acmak, release notlarina kisa bir
      ozet + ekran goruntusu/GIF eklemek.

**Karar:** Dokumantasyon dili sadece Turkce kaldi (Ingilizce ceviri
istenmedi); hedef kitle Turkce konusan AEC/Revit kullanicilari.

**Yeniden yapilandirma: `revit/` klasoru tamamen kendi kendine yeterli
hale getirildi.** Kullanici "sadece revit klasorunu alip kullanabilir
miyim?" diye sordu -- eskiden `script.py` disaridaki (repo kokundeki)
`src/`, `requirements.txt`, `env/`'e bagimliydi, bu yuzden HAYIR cevabi
verildi. Bunun uzerine tasindi:
- `src/*.py` -> `revit/pyKalfa.extension/pysrc/*.py`
- `requirements.txt` -> `revit/pyKalfa.extension/requirements.txt`
- `setup.ps1` -> `revit/pyKalfa.extension/setup.ps1`
- `env/` de ayni klasore tasindi (ve **yeniden olusturuldu** -- bir
  venv'i `mv` ile tasimak `pip.exe` gibi baslatici dosyalarin icindeki
  mutlak yollari bozuyor; venv'ler tasinabilir degil, bu hatayla
  karsilasilip duzeltildi).
- `script.py`: `_find_project_root()` -> `_find_extension_root()`
  olarak yeniden adlandirildi, artik `src/` yerine
  `pysrc/prepare_revit_input.py`'yi arar; `PROJECT_ROOT` ->
  `EXTENSION_ROOT`.
- Sonuc: `revit/pyKalfa.extension/` (yani `revit/` klasorunun
  tamami) tek basina alinip baska bir yere tasinsa/paylasilsa bile
  calisir; repo'nun geri kalanina (README, ROADMAP, `assets/`) bagimli
  degildir. Test edildi: `pysrc/prepare_revit_input.py` yeni
  konumundan calistirilip dogrulandi, `setup.ps1` yeni konumdan sifirdan
  venv kurup calistigi test edildi.

## Faz 7 - Parsel Numara Etiketleri (OCR) (Tamamlandi)

Kullanici parsel cizgileriyle birlikte uzerlerindeki numara etiketlerini
(ör. "591G") de Revit'te (secilebilir/gercek metin olarak) gormek istedi.
Bu, konum tespiti degil, GERCEK METNI okumayi (OCR) gerektiriyordu --
onemli bir mimari karar noktasi:

- **Degerlendirilen secenekler:** (1) Tesseract OCR -- hafif pip paketi
  ama Tesseract-OCR programinin kendisi ayrica sisteme kurulmali (pip
  disi bagimlilik, otomatik kurulum akisini bozar). (2) EasyOCR -- pip
  ile kurulur ama PyTorch'a bagimli (~1-1.5 GB, ilk kullanimda model
  indirir). (3) Vazgec. **Kullanici EasyOCR'i secti.**
- [x] `pysrc/ocr_labels.py`: parsel etiketleri notr gri/siyah renkte
      oldugu icin (parsel cizgileri kirmizimsi, geometry.py'deki ayrimla
      ayni mantik), renk bazli izole edilip beyaz zemine bindirilir,
      ardindan EasyOCR'a verilir.
  - **Test edilen dogruluk:** ham (buyutmesiz, serbest karakter) OCR
    ~%30-40 dogruydu (kucuk harita fontu icin cok kucuk). 3x buyutme +
    sadece rakam/buyuk harf izin verilmesi (`allowlist`) ile ~%80'e
    cikti. Kalan hatalar genelde birbirine benzeyen karakterler (G/6,
    A/4, B/8, S/5); superscript numaralar (ör. 598A**²**) duz rakam
    olarak okunuyor. Her okumanin `confidence` (0-1) skoru JSON'a
    dahil edilir.
  - **Bulunan ve duzeltilen hata:** `easyocr.Reader()` ilk model
    indirmesinde, Turkce (cp1254) gibi Windows konsol kod sayfalarinda
    ilerleme cubugundaki bir Unicode karakteri (█) basarken
    `UnicodeEncodeError` ile cokuyordu. Cozum: alt-surec cagrilarina
    (`script.py`: `_run_process`) `PYTHONUTF8=1` ortam degiskeni
    eklendi.
- [x] `prepare_revit_input.py`: OCR sonuclari gercek birime (ft) cevrilip
      `labels` (metin, guven, konum, dönüş acisi) olarak JSON'a eklendi;
      OCR basarisiz olursa (ör. internet yoksa ilk model indirmesi icin)
      `try/except` ile yakalanip geri kalan pipeline (parsel/bina)
      etkilenmeden devam eder, `label_warning` alaninda sebep belirtilir.
      `--labels`/`--no-labels` CLI bayragi eklendi (varsayilan acik).
- [x] `script.py`: parsel etiketleri icin ayrica bir **Text Note Type**
      secimi eklendi (line style/filled region type ile ayni mantik --
      projeden secilir, koda gomulmez). Her etiket ayri bir
      `TextNote.Create()`, okunan aciya gore `ElementTransformUtils.RotateElement`
      ile dondurulur.
- [x] `requirements.txt`'e `easyocr` eklendi. **Bilinen etki:** otomatik
      ilk kurulum suresi/boyutu onemli olcude artti (PyTorch ~530 MB +
      ilk kullanimda ayrica OCR modeli indirimi); README'de belirtildi.

## Faz 8 - Ilk Kurulumda Ilerleme Cubugu (Test edilecek)

Kullanici, ilk calistirmadaki (Faz 7'nin agirlastirdigi) paket kurulum
suresinin ekranda hicbir gorsel geri bildirim olmadan gecmesinden
rahatsizdi ("donmus gibi görünüyor").

- [x] `script.py`: `_run_process()` `ReadToEnd()` yerine
      `BeginOutputReadLine`/`BeginErrorReadLine` ile satir-satir/
      esazamansiz okumaya cevrildi. **Bu ayrica gercek bir hata
      duzeltmesidir:** eski yontemde once stdout'un TAMAMEN bitmesi
      beklenip sonra stderr okunuyordu; buyuk ciktida (pip'in
      torch/easyocr indirirken bastigi uzun loglar) stderr'in pipe
      tamponu dolarsa alt-surec kilitlenebiliyordu (deadlock riski).
- [x] `_bootstrap_venv()`: `forms.ProgressBar` ile 0-100 arasi bir
      ilerleme cubugu eklendi (Python arama ~%10, venv olusturma ~%20,
      pip kurulumu %20'den baslayip her yeni log satirinda 1 puan
      artarak %95'te "bekletiliyor", bitince %100). Pip'in gercek
      indirme yuzdesini ayristirmak surume gore degisebildigi icin
      guvenilmez bulundu; bunun yerine bu "sahte ama canli" ilerleme
      + pip ciktisinin `logger.info` ile pyRevit konsoluna canli
      akitilmasi tercih edildi.
- [ ] **Test edilmedi:** `forms.ProgressBar` ve `{value}` sablon
      degiskeninin tam davranisi bu ortamda (Revit yok) dogrulanamadi.
      Kullanicinin gercek Revit'te test edip sonucu bildirmesi
      bekleniyor.

## Faz 9 - pyKalfa: Cok Islevli Yapiya Gecis (Tamamlandi)

Kullanici karari: arac tek islevli bir "parsel izleyici" olmaktan cikip,
Revit icin birden fazla yardimci islevi barindiran bir eklentiye
donusuyor (ör. ileride "Duvar Ciz"). Bu yuzden ad `pyParcelTrace` ->
**`pyKalfa`** olarak degistirildi ve klasor yapisi islev bazinda ayrildi.

- [x] Yeniden adlandirma: `revit/pyParcelTrace.extension` ->
      `revit/pyKalfa.extension`, `pyParcelTrace.tab` -> `pyKalfa.tab`;
      dokumanlar, `setup.bat`, `setup.ps1` ve kod icindeki basliklar
      (`forms.alert` basliklari, Transaction adi) guncellendi.
- [x] **Ortak kutuphane: `lib/pykalfa/`.** pyRevit bir extension'in
      `lib/` klasorunu otomatik `sys.path`'e ekler; boylece her buton
      `from pykalfa import ...` diyebilir. `script.py` icinde tekrar
      eden ve islevle ilgisi olmayan ne varsa buraya tasindi:
      - `paths.py` -- extension icindeki standart yollar. Eski
        `_find_extension_root()` (yukari dogru `pysrc/...` arama) yerini,
        modulun KENDI konumundan (`lib/pykalfa/paths.py` -> 3 ust klasor)
        turetilen sabit bir koke birakti: daha basit ve butonun kac
        klasor derinde oldugundan bagimsiz.
      - `subproc.py` -- `run_process` (satir satir/eszamansiz okuma,
        deadlock korumasi, `PYTHONUTF8=1`) ve `run_python`.
      - `bootstrap.py` -- `env/` ilk kurulumu (`ensure_env`), ilerleme
        cubugu ile.
      - `revitutils.py` -- `elem_name`, `WarningSwallower`, aktif view
        kontrolu, `distance`, `view_elevation`.
      - `selectors.py` -- projede ONCEDEN tanimli stilleri sectirme
        (`pick_line_style`, `pick_filled_region_type`,
        `pick_text_note_type`). Uc ayri yerde tekrarlanan
        "topla -> ada gore sozluk -> `SelectFromList` -> iptal kontrolu"
        akisi tek bir `pick_by_name()`'de birlesti.
- [x] **Islev bazli CPython kodu: `pysrc/<islev>/`.** Goruntu isleme
      modulleri `pysrc/` -> `pysrc/parsel_bina/` altina tasindi. Birbirlerini
      duz isimle (`from geometry import ...`) import etmeye devam ediyorlar;
      alt-surec olarak calisan scriptin kendi klasoru zaten `sys.path[0]`
      oldugu icin bir degisiklik gerekmedi.
- [x] `ensure_env()` artik buton basinda degil, **ihtiyac aninda**
      cagriliyor: sadece Revit API'siyle calisan gelecekteki butonlar
      (ör. cizim islevleri) 1-1.5 GB'lik OCR/PyTorch ortamina hic
      dokunmadan calisabilsin diye.
- [x] Panel basligi `bundle.yaml` ile "Parsel / Bina" yapildi (klasor
      adi `ParselBina.panel` kaldi).
- [x] README'ye "Yeni buton (islev) ekleme" tarifi eklendi.
- [ ] **Test edilmedi:** yeniden yapilandirma sonrasi buton gercek
      Revit'te calistirilmadi (bu ortamda Revit yok). Kullanicinin
      pyRevit'te "Reload" edip "Parsel/Bina Aktar"i bir kez calistirmasi
      bekleniyor. Ayrica `env/` klasoru rename sirasinda birlikte tasindi;
      venv'ler tam anlamiyla tasinabilir olmadigi icin (bkz. Faz 6)
      bozulursa `env/` silinip yeniden kurulmali (buton kendisi kurar).

## Faz 10 - Duvar Aktar: DXF'ten Gercek Duvar (MVP tamam, Revit'te test edilecek)

Ikinci islev: Polycam Floor Plan (veya baska CAD) DXF'indeki cizgilerden
**gercek `Wall` elemanlari** uretmek -- `ModelCurve`/detay cizgisi degil,
uzerinde kapi/pencere acilabilen duvarlar.

**Mimari karar: DXF okuma nerede yapilacak?** ezdxf saf Python ama
Python 3 gerektirir; pyRevit'in varsayilan motoru IronPython 2.7. Iki
secenek vardi: (1) Revit'in kendi DXF import'unu kullanmak -- ama o,
cizgileri duvara cevirmiyor; (2) parsel_bina'daki kalibi tekrarlamak:
agir isi `env/` sanal ortamindaki CPython'a alt-surec olarak devretmek.
(2) secildi; boylece iki islev ayni altyapiyi (subproc + bootstrap +
JSON ara format) paylasiyor ve `pysrc/duvar/` tek basina, Revit
olmadan calistirilabilir/test edilebilir kaliyor.

- [x] `pysrc/duvar/dxf_reader.py`: LINE/LWPOLYLINE/POLYLINE okuma.
      Uc "ortak koordinat sistemi" sorunu bilerek ele alindi:
      **INSERT bloklari** `virtual_entities()` ile yerinde patlatilir
      (olcek/donme/konum uygulanmis olarak; ic ice bloklar icin
      ozyinelemeli, derinlik siniriyla), **OCS -> WCS** donusumu yapilir
      (ters extrusion'li cizimlerde plan ayna goruntusu olmasin diye),
      **Z duzlestirilir**. Blok icindeki "0" katmanindaki geometri,
      AutoCAD kuralina uygun olarak INSERT'un katmanini devralir --
      katman filtresi dogru calissin diye.
- [x] Birim: `$INSUNITS` basligindan otomatik. Basligin bos oldugu
      (0 = belirtilmemis) dosyalarda cizimin kosegen boyundan tahmin
      yurutulur ve `confident=False` isaretlenir; arayuz o zaman
      kullaniciya sorar. Sessizce yanlis olcekte duvar uretmektense
      sormak tercih edildi.
- [x] `pysrc/duvar/geometry.py`: birim -> feet, uc nokta kaynatma (5 mm),
      tekrar/dejenere atma, **kolinear birlestirme**, kisa parca filtresi.
      Birlestirme yontemi: (katman, yon) kovalari -> ayni dogruya ait
      olanlari grupla -> dogru boyunca 1B araliklara cevirip ust uste
      binen/yakin olanlari birlestir. "Her segmenti her segmentle
      karsilastir" (O(n^2)) yaklasimindan hem hizli hem de zincirleme
      birlesmelerde (A-B, B-C, C-D) dogru.
      **Sira onemli:** once birlestir, sonra kisa olanlari at -- tersi
      yapilirsa bir duvari olusturan kisa parcalar birbirine eklenemeden
      silinir.
- [x] `pysrc/duvar/wall_detector.py`: "hangi cizgi duvar olacak" karari
      tek bir yerde. MVP'de bire bir (her segment bir duvar ekseni);
      Faz 2'de sadece bu modul degisecek sekilde ayrildi.
- [x] `pysrc/duvar/prepare_wall_input.py`: zinciri calistirip
      `output/wall_input.json` uretir (koordinatlar feet).
- [x] Revit tarafi `lib/pykalfa/duvar/` altinda ikiye ayrildi:
      `ui.py` (butun diyaloglar, metre <-> feet donusumu burada) ve
      `revit_creator.py` (`Wall.Create` dongusu, hic diyalog acmaz).
      Buton `script.py`'si sadece akisi kuruyor.
- [x] Ortak `selectors.py`'ye `pick_level` (yukseklikle birlikte
      listeler) ve `pick_wall_type` (perde duvar tiplerini eler) eklendi.
- [x] **Stabilite:** her cizgi tek tek try/except icinde olusturulur --
      bozuk bir cizgi butun aktarimi iptal etmez, sadece raporlanir.
      Uyari yutucu (Faz 4'ten) burada da kullanilir. Aktarimin tamami
      tek transaction: tek "Undo" ile geri alinabilir.
- [x] Orijinden uzak cizim korumasi: merkez orijinden ~1.5 km'den
      uzaksa kullaniciya "orijine tasiyayim mi?" diye sorulur (Revit bu
      mesafeden sonra hassasiyet uyarilari veriyor).
- [x] Katman filtresi: DXF'te birden fazla katman varsa hangilerinin
      duvara donusecegi sorulur (mobilya/olculendirme/metin disarida
      kalsin diye). Katman ADINDAN tahmin YURUTULMEZ -- Polycam disi
      cizimlerde katman adlari ongorulemez oldugu icin isim tahmini
      kirilgan olurdu; karar kullanicinin.
- [x] `pysrc/duvar/selftest.py`: sentetik DXF (parcalanmis duvarlar,
      tekrar eden cizgi, 4 cm gurultu, kapali polyline, dondurulmus
      blok) uretip butun zinciri dogrular. Revit gerekmez, saniyeler
      icinde calisir. **Gecti.**
- [x] Revit tarafi (revit_creator) sahte Revit API'siyle duman testinden
      gecirildi: rapor muhasebesi, Z sabitleme, tek duvarin patlamasinin
      digerlerini durdurmamasi. **Gecti** (bu test repoda degil; gercek
      API ile drift edecek bir mock'u bakimda tutmak, faydasindan cok
      yanlis guven uretirdi).
- [x] `bootstrap.py` ve `setup.ps1` artik `pip.exe` yerine
      `python.exe -m pip` kullaniyor: pip.exe baslaticisi venv'in
      olusturuldugu andaki MUTLAK yolu tasidigi icin, klasor
      tasindiginda/yeniden adlandirildiginda **baska bir projenin
      ortamina** kurulum yapabiliyor (gelistirme sirasinda tam olarak
      bu yasandi).
- [x] **Gercek Polycam DXF'i ile test edildi** (`assets/simple.dxf`,
      ~9.4 x 8.6 m bir mekan). Sonuclar ve ogrenilenler:
      - `$INSUNITS = 6` (metre) dogru okundu, birim sorusu hic cikmadi.
      - 316 LWPOLYLINE -> 1473 ham segment -> 117 duvar adayi.
        Elenenlerin cogu (914) 5 mm'den kisa dejenere parca: Polycam
        polyline'lari cok yogun/tekrarli nokta iceriyor.
      - HATCH (25) ve MTEXT (23) yok sayildi -- beklenen davranis.
      - **Katman adlari `Poly-` onekli ve konusuyor:** `Poly-Walls`,
        `Poly-Doors`, `Poly-Windows`, `Poly-Rooms`, `Poly-Furniture`,
        `Poly-DimensionsInterior/Exterior`, `Poly-Openings`,
        `Poly-Compass`, `Poly-Logo`, `Poly-Fixtures`, `Scalebar`.
        Katman filtresi olmasa logo, pusula ve olculendirme cizgileri de
        duvara donusecekti -- filtre sart oldugu dogrulandi.
      - `Poly-Walls`: 13 cizgi, toplam 58.56 m. Geometri elle
        dogrulandi (dis hat ~23.6 m x 2 + ic duvar ~12 m).
- [x] **Onemli bulgu -- Polycam duvarlari CIFT CIZGI ciziyor:**
      `Poly-Walls` icindeki 13 segmentin 7'si birbirine tam paralel ve
      **tam 10 cm** araliktaki ciftler (yani duvarin iki yuzu). MVP
      kurali "her cizgi bir duvar" oldugu icin bu dosyada her fiziksel
      duvar **iki ince duvar** olarak cikar. Faz 2'deki "cift cizgiden
      kalinlik algilama" bu yuzden kozmetik bir iyilestirme degil, bu
      veri kaynagi icin asil dogru davranis. Iyi haber: ciftler cok
      temiz (tam paralel, sabit 10 cm, boyunca ust uste biniyor), yani
      eslestirme algoritmasi basit kalabilir.
- [ ] **Test edilmedi:** gercek Revit'te hic calistirilmadi (bu ortamda
      Revit yok). Kullanicinin pyRevit'i Reload edip denemesi bekleniyor.

**Faz 2 icin planlananlar** (bunlarin ilk ikisi Faz 11'de, tahmin
edilenden farkli ve daha dogru bir yoldan -- dis hat tanima ile --
gerceklesti):

- [x] ~~Cift cizgiden duvar kalinligi algilama~~ -> dis hattan olculuyor.
- [x] ~~Merkez eksen uretme~~ -> dis hattan cikariliyor.
- [ ] Olculen kalinliga en yakin `WallType`'i otomatik secme (kalinlik
      artik olculuyor, veri hazir; su an sadece kullaniciya gosteriliyor).
- [ ] Kapi boslugu algilama: kapi/pencere dis hatlari da okunuyor ama
      duvardan cikarilmiyor (Revit'te kapi/pencere ailesi duvari zaten
      kestigi icin dusuk oncelikli).
- [ ] Oda siniri olusturma (`Poly-Rooms` poligonlari mevcut).
- [ ] Egri (bulge) duvarlar: su an kirisle temsil ediliyor.

## Faz 11 - Duvar Aktar: Dis Hat Tanima (MVP'nin yeniden yazimi)

Faz 10 gercek Revit'te denendi ve **kullanilamaz** cikti: "duvarlarin
ustune tekrar duvar koyuyor, sacma yerlere duvar ekliyor, DXF'i Revit'e
surukle-birak yapmakla alakasi yok". Sebep tek bir yanlis varsayimdi:
**"her cizgi bir duvar eksenidir".**

**Kok neden analizi** (`assets/simple.dxf` uzerinde, DXF yapisi tek tek
incelenerek):

1. **Polycam duvari dis hat olarak ciziyor.** Her duvar 6 noktali kapali
   bir halka: iki uzun kenar duvarin iki yuzu, kisa kenarlar gonyeli
   uclar. "Her cizgi bir duvar" kurali her fiziksel duvari **iki ince
   duvara** ceviriyordu (10 cm arayla) -- "ustune tekrar duvar" sikayeti.
2. **DXF'te her duvar iki kez var.** `Poly-Walls` katmaninda 14 polyline
   vardi ama sadece 7 essiz duvar; kalan 7'si birebir kopya. Tekrar
   eleme segment seviyesinde yapildigi icin bunlarin bir kismi
   kurtulup ikinci kat duvar uretiyordu.
3. **Kapi/pencere/gecisler duvarla ayni formatta.** `Poly-Doors`,
   `Poly-Windows`, `Poly-Openings` da 10 cm kalinliginda dis hatlar;
   geometriden ayirt edilemiyorlar. Ayrim ancak KATMANLA yapilabilir.
4. **Katman secimi coklu ve varsayilansizdi.** Kullanici birden fazla
   katman secince olculendirme (32 m + 20 m), logo, pusula cizgileri de
   duvara donusuyordu -- "sacma yerlere duvar" sikayeti.
5. **Kolinear birlestirmede zincirleme hatasi.** Gruplama son uyeye gore
   yapildigi icin (0, 0.019, 0.038, ...) tolerans zincirleniyor ve
   birbirinden uzak paralel dogrular tek bir ORTALAMA dogruya
   cokebiliyordu -- yani duvarlar yerinden kayabiliyordu.

**Yapilan degisiklikler:**

- [x] `dxf_reader.py`: artik segment degil **`Poly` (nokta dizisi)**
      donduruyor. Polyline butunlugunu bozmak, en kritik bilgiyi (bunun
      bir duvar dis hatti oldugunu) yok ediyordu. `Poly.ring()` /
      `Poly.is_ring()` ile kapali sekiller normalize ediliyor ("closed"
      bayragi ile "son nokta = ilk nokta" ayni sekilde ele aliniyor).
- [x] `wall_detector.py` bastan yazildi: `outline_to_centerline()` bir
      halkanin en uzun iki kenarini alip (komsu olmamali, paralel
      olmali, zit yonlu olmali, aradaki dik mesafe 3-80 cm olmali,
      uzunluk/kalinlik orani >1.2 olmali) **merkez ekseni ve olculen
      kalinligi** cikariyor. Kopyalar eksen konumuna gore eleniyor.
- [x] Tek cizgi modu (`--lines`) **geri donus** haline geldi: sadece
      hicbir dis hat bulunamazsa ve kullanici onaylarsa devreye giriyor.
- [x] `geometry.py`: zincirleme gruplama hatasi duzeltildi (karsilastirma
      artik grubun ilk uyesine gore). Birim donusumu polyline seviyesine
      tasindi (`to_feet_polys`).
- [x] Katman secimi tek tiklamalik bir ONERI ile basliyor: adinda
      "wall"/"duvar" gecen katman, yoksa en cok duvar uzunluguna sahip
      olan. Reddedilirse tam liste aciliyor. Onerinin yaninda kac duvar,
      kac metre ve olculen kalinlik yaziyor.
- [x] Olculen kalinlik duvar tipi secim basliginda ve onay penceresinde
      gosteriliyor (tip OTOMATIK secilmiyor -- proje sablonundaki tip
      adlari ongorulemez, karar kullanicida).

**Beklenmedik guzel yan etki:** kalinlik araligi filtresi, yanlis birim
secimini de yakaliyor. 200 mm'lik duvar "m" olarak okununca 200 m
kalinlik olur, makul araligin disina duser ve duvar bulunamaz. Yani
program sessizce 1000 kat buyuk duvar uretmek yerine hic uretmiyor.
Bu ozellik `selftest.py`'de acikca test ediliyor.

**Gercek DXF'te sonuc** (`assets/simple.dxf`):

| | Once (Faz 10) | Sonra (Faz 11) |
| --- | --- | --- |
| `Poly-Walls` duvar sayisi | 13 (cift + uc parcalari) | **7** (gercek duvar sayisi) |
| Kalinlik | olculmuyor | **10 cm** (cizimden) |
| Kopyalar | kaliyor | eleniyor |
| Mobilya/logo/olcu | duvar olabiliyor | dis hat testinde eleniyor |

Merkez eksenlerin duvar dis hatlarinin tam ortasindan gectigi, ham DXF
geometrisiyle ust uste bindirilerek gorsel olarak da dogrulandi.

- [x] `selftest.py` gercek yapiya gore yeniden yazildi: sentetik plan
      artik duvarlari dis hat olarak ciziyor, ayni duvari iki kez
      ekliyor, kapi/mobilya/oda poligonu/olcu cizgisi iceriyor.
      **20 testin tamami geciyor.**
- [ ] **Test edilmedi:** yeni surum gercek Revit'te henuz denenmedi.

## Faz 13 - Parsel/Bina Aktar: Akis Sirasi ve Ilerleme Cubugu (Tamam, Revit'te test edilecek)

Kullanici sordu: "olcegi sectikten sonra, parsel cizgisi secimi oncesi
goruntu islemi mi yapiyor?" -- evet, oyleydi: olcek girildikten hemen
sonra butun goruntu isleme + OCR calisiyor, kullanici hicbir geri
bildirim olmadan bekliyor, sonra stil sorulari geliyordu.

- [x] **Sira degisti:** butun girdiler (dosyalar, olcek, uc stil) once
      alinir; goruntu isleme tek uzun adim olarak sonra calisir;
      geometri en sonda olusturulur. Amac: uzun beklemenin ORTASINDA
      kullaniciya soru sorulmamasi.
- [x] Metin (TextNote) tipi artik kosulsuz sorulur. Eskiden "etiket
      okunduysa" soruluyordu ama bu bilgi ancak islem BITTIKTEN sonra
      olusuyor -- yani soruyu one almak icin kosulu kaldirmak gerekti.
      Etiket cikmazsa secilen tip kullanilmadan kalir (zararsiz).
- [x] `selectors.pick_by_name`'e `optional` eklendi: projede hic Text
      Note Type yoksa hata verip cikmak yerine None donuyor. O durumda
      `--no-labels` ile OCR HIC CALISTIRILMIYOR -- olusturulamayacak
      etiketler icin en uzun adimi beklemek anlamsiz. (Yan fayda:
      etiket istemeyen kullanici icin belirgin hizlanma.)
- [x] **Ilerleme cubugu:** `prepare_revit_input.py` artik
      `PROGRESS|yuzde|mesaj` satirlari basiyor (7 asama). `flush=True`
      sart: cikti bir boruya yazildigi icin tamponlanir, flush
      edilmezse butun satirlar en sonda topluca gelir ve cubuk hic
      ilerlemezdi. Gercek zamanli aktigi olculerek dogrulandi.
- [x] **Iş parcacigi guvenligi (onemli):** `.NET` alt-surec cikti
      geri cagirimlari ARKA plan iş parcaciklarindan gelir; WPF tabanli
      `forms.ProgressBar`'i oradan guncellemek kararsizlik yaratabilir.
      Bu yuzden `subproc.run_process`'e `on_poll` eklendi: zaman asimili
      `WaitForExit(ms)` dongusuyle, arayuz **ana iş parcacigindan**
      guncelleniyor. `on_line` sadece duruma yaziyor, ekrana dokunmuyor.
      (Not: `bootstrap.py`'deki eski ilerleme cubugu hala geri cagirim
      icinden guncelliyor -- Faz 8'den beri test edilmemis durumda.)
- [x] OCR asamasinda cubugun donmus gorunmemesi icin sinirli bir
      "canlilik" surunmesi eklendi (asama uzerine en fazla +18 puan,
      ~1 saniyede 1 puan). Asama ADI her zaman gercek olani yazar.
- [x] Sahte bir .NET `Process` ile uctan uca test edildi: PROGRESS
      ayristirma, `on_line`'in arka planda / `on_poll`'un ana iş
      parcaciginda calismasi, yuzdenin geri gitmemesi, ciktinin
      kaybolmamasi. **Gecti.**
- [ ] **Test edilmedi:** gercek Revit'te cubugun gorunumu (ozellikle
      `pb.title` guncellemesi) dogrulanmadi; basarisiz olursa cubuk
      baslik degistirmeden ilerlemeye devam edecek sekilde korumaya
      alindi.

## Ilerleme Ozeti

| Faz                             | Durum      |
| -------------------------------- | ---------- |
| 0. Ortam Kurulumu                | Tamamlandi |
| 1. Temel Tespit                  | Tamamlandi |
| 2. Parsel-Bina Iliski            | Tamamlandi |
| 3. Geometri Iyilestirme          | Tamamlandi |
| 4. pyRevit Entegrasyonu          | Tamamlandi |
| 5. Paketleme ve Kullanim         | Tamamlandi |
| 6. Genel Kullanima Acma          | Tamamlandi |
| 7. Parsel Numara Etiketleri (OCR) | Tamamlandi |
| 8. Ilk Kurulum Ilerleme Cubugu   | Test edilecek |
| 9. pyKalfa - Cok Islevli Yapi    | Test edilecek |
| 10. Duvar Aktar (DXF -> Wall)    | MVP -- Faz 11'de yeniden yazildi |
| 11. Duvar Aktar: Dis Hat Tanima  | Tamam, Revit'te test edilecek |
