# pyKalfa — Kullanım Kılavuzu

Bu kılavuz, pyKalfa eklentisini **hiç kurulmamış bir bilgisayarda
sıfırdan kurup**, ardından **Revit içinde tek butonla parsel sınırlarını
(DetailLine), bina alanlarını (FilledRegion) ve parsel numara etiketlerini
(TextNote) oluşturana kadar** atılması gereken **her adımı**, en ince
detayına kadar anlatır.

> pyKalfa, Revit için birden fazla yardımcı işlevi tek sekmede toplayan
> bir pyRevit eklentisidir. Kurulum adımları (Bölüm A) tüm işlevler için
> ortaktır; sonra ihtiyacınız olan işlevin bölümüne geçin:
>
> - **Parsel/Bina Aktar** (kadastro görselleri → çizgi/dolgu/metin):
>   Bölüm B
> - **Duvar Aktar** (kat planı DXF → gerçek Revit duvarları): Bölüm B2

---

## İçindekiler

1. Genel Bakış
2. Bölüm A — İlk Kurulum (Bir Kereye Mahsus)
   - A.1. Python Kurulumu
   - A.2. (İsteğe Bağlı) Projeyi Elle İndirme
   - A.3. Otomatik Kurulum Hakkında
   - A.4. pyRevit Kurulumu
   - A.5. pyKalfa'yı pyRevit'e Kurma (GitHub adresi ile)
3. Bölüm B — Günlük Kullanım: Parsel/Bina Aktar
   - B.1. Revit'i Açma ve Doğru View'e Geçme
   - B.2. Butona Basma
   - B.3. (Normalde Görmezsiniz) Otomatik Ortam Kurulumu
   - B.4. Parsel Görselini Seçme
   - B.5. Bina Görselini Seçme
   - B.6. Harita Ölçeğini Girme
   - B.7. Parsel Çizgileri İçin Line Style Seçimi
   - B.8. Binalar İçin Filled Region Type Seçimi
   - B.9. Parsel Etiketleri İçin Text Note Type Seçimi
   - B.10. Görüntü İşleme (İlerleme Çubuğu)
   - B.11. İşlemin Tamamlanması ve Özet Penceresi
4. Bölüm B2 — Günlük Kullanım: Duvar Aktar
   - B2.1. Hazırlık
   - B2.2. Butona Basma ve DXF Seçme
   - B2.3. (Sadece Gerekirse) Çizim Birimi Sorusu
   - B2.4. (Sadece Gerekirse) Çizimi Orijine Taşıma
   - B2.5. Katman Seçimi
   - B2.6. Duvar Yüksekliği, Level ve Duvar Tipi
   - B2.7. Onay ve Sonuç
   - B2.8. Sonucu Kontrol Etme ve Düzeltme
5. Bölüm C — Sonucu Kontrol Etme (Parsel/Bina Aktar)
6. Bölüm D — Sık Karşılaşılan Durumlar ve Çözümleri
7. Ek — Terimler Sözlüğü

---

## 1. Genel Bakış

pyKalfa'nın **"Parsel/Bina Aktar"** işlevi, kadastro görüntülerinden
(parsel sınırları ve bina dış hatları içeren PNG dosyaları) yapay görü
(OpenCV) ve OCR (metin okuma) teknikleriyle vektör geometri çıkarıp bunu
doğrudan bir Autodesk Revit projesine aktarır. Kullanıcı Revit içinde tek
bir butona basar; arka planda çalışan bir görüntü işleme motoru:

- **Parsel sınırlarını** `DetailLine` (ayrıntı çizgisi) olarak,
- **Bina dış hatlarını** `FilledRegion` (dolgulu alan) olarak,
- **Parsel numara etiketlerini** (ör. "591G") `TextNote` (metin notu)
  olarak

aktif Revit görünümüne otomatik olarak çizer.

Bu kılavuzu takip etmek için Revit veya Python bilgisi gerekmez; her
adımda ne yapmanız gerektiği açıkça yazılıdır.

---

## 2. Bölüm A — İlk Kurulum (Bir Kereye Mahsus)

Bu bölümdeki adımlar **sadece bir kez**, aracı ilk defa kullanacağınız
bilgisayarda yapılır. Kurulumu tamamladıktan sonra bir daha bu bölüme
dönmenize gerek kalmaz; doğrudan Bölüm B'deki günlük kullanım adımlarına
geçebilirsiniz.

Genel gereksinimler: **Windows** işletim sistemi, **Autodesk Revit**
(2026 veya uyumlu bir sürüm) ve kurulum sırasında paket indirmek için
**internet bağlantısı**. Aşağıdaki adımlar sırasıyla geri kalanını
(Python, proje dosyaları, pyRevit, extension) kurar.

### A.1. Python Kurulumu

pyKalfa'in görüntü işleme tarafı Python ile çalışır. Sisteminizde
Python kurulu olup olmadığını önce kontrol edin:

1. Klavyeden **Windows tuşu**na basın, `powershell` yazın, **Enter**'a
   basın (PowerShell penceresi açılır).
2. Açılan pencereye şunu yazıp Enter'a basın:
   ```
   python --version
   ```
3. Ekranda `Python 3.x.x` gibi bir sürüm numarası görüyorsanız Python
   kuruludur, doğrudan Adım A.2'ye geçebilirsiniz.
4. Eğer "Python bulunamadı" gibi bir hata görüyorsanız:
   1. Tarayıcınızdan **python.org** adresine gidin.
   2. **"Download Python"** butonuyla en güncel sürümü indirin.
   3. İndirilen kurulum dosyasını çalıştırın.
   4. Kurulum ekranının **en altındaki "Add python.exe to PATH"
      kutucuğunu mutlaka işaretleyin** — bu, pyKalfa'in Python'u
      otomatik bulabilmesi için gereklidir.
   5. **"Install Now"** ile kurulumu tamamlayın.
   6. Kurulum bitince PowerShell penceresini kapatıp yeniden açın,
      `python --version` ile tekrar kontrol edin.

> **İpucu:** Kurulum sırasında (veya kurulumdan sonra "Modify" ile
> tekrar açtığınızda) sihirbazın en son ekranında **"Disable path
> length limit"** adında bir link/seçenek de görürsünüz. Bunu da
> işaretlemeniz/tıklamanız önerilir — Windows'un eski bir dosya yolu
> uzunluğu sınırlamasını kaldırır ve ileride bazı paket kurulumlarında
> ("dosya adı çok uzun" gibi) çıkabilecek hatalari önler.

### A.2. (İsteğe Bağlı) Projeyi Elle İndirme

**Çoğu kullanıcı bu adımı atlayabilir.** Adım A.5'te pyKalfa'nın GitHub
adresini doğrudan pyRevit'e vereceksiniz; pyRevit projeyi kendisi
indirir. Dolayısıyla önceden bir şey indirmenize gerek yoktur.

Bu adım yalnızca, indirmeyi elle yapmak isteyenler içindir (ör. şirket
ağı GitHub'a doğrudan erişimi engelliyorsa):

1. Tarayıcınızdan proje sayfasına gidin.
2. Yeşil **"Code"** butonuna tıklayıp **"Download ZIP"** seçeneğini
   kullanın; dosya `İndirilenler` klasörünüze iner.
3. ZIP'e sağ tıklayıp **"Tümünü Çıkart..."** (Extract All) ile
   çıkartın.
4. Çıkan klasörün adını **`pyKalfa.extension`** olarak değiştirin —
   pyRevit bir klasörü ancak adı `.extension` ile bitiyorsa eklenti
   olarak tanır.
5. Bu klasörü, onu içeren bir **üst** klasöre koyun. Örnek:
   ```
   C:\pyRevitExtensions\pyKalfa.extension
   ```
   **Bu üst klasörün yolunu not edin** (`C:\pyRevitExtensions`) —
   Adım A.5'in alternatif yönteminde bu yola ihtiyacınız olacak.

> **Not:** Projeyi nereye çıkardığınızın bir önemi yok. Kurulum
> sırasında inen büyük paketler (OCR kütüphanesi) her hâlükârda sabit
> ve kısa bir yola (`C:\pyKalfa\env`) kurulur, dolayısıyla Windows'un
> 260 karakterlik dosya yolu sınırına takılmazsınız.

### A.3. Otomatik Kurulum Hakkında

Eski sürümlerde bu adımda `setup.ps1` adlı bir script'i elle
çalıştırmanız isteniyordu. **Artık buna gerek yok** — bu adım tamamen
kaldırıldı.

Python paketlerinin kurulumu artık tamamen otomatiktir: Adım A.5'te
pyKalfa'yı pyRevit'e tanıtıp Revit'i yeniden başlattığınızda (veya
pyRevit'i "Reload" ettiğinizde), extension'ın kendi `startup.py`
dosyası pyRevit tarafından otomatik çalıştırılır ve gerekli kurulumu
kendisi yapar. Ayrıntılı akış Adım B.3'te anlatılıyor.

Doğrudan Adım A.4'e geçebilirsiniz.

### A.4. pyRevit Kurulumu

Eğer bilgisayarınızda pyRevit zaten kuruluysa (Revit'i açtığınızda üst
menüde bir **pyRevit** sekmesi görüyorsanız) bu adımı atlayıp A.5'e
geçebilirsiniz.

1. Tarayıcınızdan pyRevit'in resmi GitHub deposuna gidin:
   `github.com/pyrevitlabs/pyRevit`
2. **"Releases"** sekmesine tıklayın.
3. En üstteki (en güncel) sürümün altındaki kurulum dosyasını (`.exe` veya
   `.msi` uzantılı) indirin.
4. İndirilen kurulum dosyasına çift tıklayıp kurulum sihirbazını
   varsayılan ayarlarla tamamlayın.
5. Kurulum bitince Revit'i açın (zaten açıksa kapatıp yeniden açın). Üst
   menüde yeni bir **pyRevit** sekmesi görmelisiniz — görüyorsanız
   kurulum başarılı demektir.

### A.5. pyKalfa'yı pyRevit'e Kurma (GitHub adresi ile)

Bu adımda pyKalfa'nın GitHub adresini pyRevit'e vereceksiniz; pyRevit
projeyi kendisi indirip kuracak.

1. Revit'i açın (bir proje açık olması gerekmez, boş ekranda da
   yapılabilir).
2. Üst menüden **pyRevit** sekmesine tıklayın.
3. **Extensions** (Eklenti Yöneticisi) butonuna tıklayın.
4. Yeni bir eklenti eklemek için açılan pencerede şu adresi girin:
   ```
   https://github.com/cmldk/pyKalfa.git
   ```
   İsim sorulursa `pyKalfa` yazın.
5. pyRevit projeyi indirip `pyKalfa.extension` adıyla kaydeder.
6. pyRevit sekmesindeki **"Reload"** (Yeniden Yükle) butonuna tıklayın.
   (Bulamazsanız Revit'i tamamen kapatıp yeniden açmak da aynı işi
   görür.)
7. **İlk kurulumda burada birkaç dakika beklersiniz** — Bölüm B.3'te
   anlatılan otomatik ortam kurulumu bu sırada çalışır. Bir ilerleme
   çubuğu görürsünüz.
8. Kurulum bitince üst menüde yeni bir **pyKalfa** sekmesi
   görmelisiniz. Bu sekmeye tıklayınca **Parsel / Bina** ve **Duvar**
   adında paneller ve içlerinde ikonlu butonlar görmelisiniz.

**Alternatif — elle indirdiyseniz (Adım A.2):**

1. **pyRevit** sekmesi → **dişli çark ikonu** (⚙, "Settings").
2. **"Custom Extension Folders"** bölümünü bulun.
3. **"Add Folder"** ile, `pyKalfa.extension` klasörünü **içeren üst
   klasörü** seçin (ör. `C:\pyRevitExtensions`).
   > **Dikkat:** `pyKalfa.extension` klasörünün **kendisini değil**,
   > bir üstünü seçin. pyRevit, verdiğiniz klasörün içinde `.extension`
   > ile biten klasörleri arar.
4. **"Save Settings"** ile kaydedip **"Reload"** edin.

**Kurulum bu kadar!** Bu adımdan sonra bir daha Bölüm A'ya dönmenize
gerek yoktur. Aşağıdaki Bölüm B, aracı her kullanmak istediğinizde
izleyeceğiniz adımları anlatır.

---

## 3. Bölüm B — Günlük Kullanım: Parsel/Bina Aktar

### B.1. Revit'i Açma ve Doğru View'e Geçme

1. Geometri oluşturmak istediğiniz Revit projesini açın (yeni/boş bir
   proje de olabilir).
2. Proje ağacından (Project Browser) veya View sekmesinden, çizgilerin
   çizileceği bir **plan görünümü, detay görünümü, kesit görünümü veya
   cephe görünümüne** geçin.
   > **Önemli:** Aktif görünüm bir **3D görünüm** ise buton hata verip
   > duracaktır — çünkü `DetailLine` elemanları 2D bir çizim düzlemine
   > (sketch plane) ihtiyaç duyar. Mutlaka 2D bir görünümde olduğunuzdan
   > emin olun.

### B.2. Butona Basma

1. Üst menüden **pyKalfa** sekmesine tıklayın.
2. **Parsel / Bina** panelindeki **"Parsel/Bina Aktar"** butonuna tıklayın.
3. Bu noktada bir çıktı/log penceresi açılabilir (pyRevit'in kendi
   konsol penceresi) — bu normaldir, kapatmanıza gerek yoktur, işlem
   ilerledikçe burada bilgi mesajları görünür.

Eğer aktif görünüm uygun değilse (Adım B.1'e bakın), şu mesajla
karşılaşırsınız ve script kendiliğinden sonlanır:

> *"Aktif view bir plan/detay/kesit/cephe view'i olmalı (DetailLine bir
> sketch plane'e ihtiyaç duyar). Önce uygun bir view açıp tekrar
> çalıştırın."*

Bu durumda **Tamam**'a basıp Adım B.1'e dönün, uygun bir görünüme geçip
B.2'yi tekrar deneyin.

### B.3. (Normalde Görmezsiniz) Otomatik Ortam Kurulumu

Görüntü işleme ortamının (`env/`) kurulumu artık **Adım A.5'te**,
pyKalfa'yı pyRevit'e tanıtıp Revit'i yeniden başlattığınızda/pyRevit'i
reload ettiğinizde kendiliğinden olur — extension'ın kök dizinindeki
`startup.py` dosyası, pyRevit tarafından extension her
yüklendiğinde/reload edildiğinde otomatik çalıştırılır. Yani **bu
adıma normalde hiç butona basmadan, Adım A.5'i tamamlarken**
girersiniz; buraya ayrıca bir açıklama olarak bırakılmasının sebebi, o
sırada ne olduğunu anlamanızı sağlamaktır.

1. Şu başlıkla bir bilgi penceresi açılır: **"pyKalfa - kurulum"**,
   içeriği:
   > *"pyKalfa ilk kurulum/güncelleme yapılıyor. Bu birkaç dakika
   > sürebilir; pencere kapanınca işlem otomatik devam edecek."*
2. **Tamam**'a basın.
3. Script, arka planda sisteminizdeki Python'u bulup `C:\pyKalfa\env`
   adında izole bir çalışma ortamı kurar ve gerekli paketleri (görüntü
   işleme + OCR kütüphaneleri) indirir. Bu sırada bir **ilerleme
   çubuğu (progress bar)** görürsünüz; yüzde değeri arttıkça kurulumun
   ilerlediğini anlayabilirsiniz (paket indirme aşamasında yüzde,
   gerçek indirme oranını değil, "bir şeyler oluyor" bilgisini
   yansıtan yaklaşık bir değerdir — %95'e kadar yavaşça ilerler,
   bitince %100'e tamamlanır).
   > **Süre uyarısı:** Bu işlem, internet hızınıza bağlı olarak
   > **birkaç dakika ile on dakika arası** sürebilir (OCR kütüphanesi
   > büyük bir indirmedir, yaklaşık 1-1.5 GB). İlerleme çubuğu bir süre
   > yavaş görünebilir — bu normaldir, bekleyin, kapatmayın. Bu süre
   > boyunca pyRevit, pyKalfa sekmesini yüklemeyi bekler; Revit'in
   > diğer kısımları donmuş görünmez.
4. Kurulum tamamlanınca üst menüde **pyKalfa** sekmesi belirir; Adım
   A.5'in geri kalanına (veya doğrudan Bölüm B.4'e) devam edebilirsiniz.
5. **Sonraki her Revit açılışında** `env/` zaten güncel olduğu için bu
   kontrol anında biter — hiçbir pencere/bekleme görmezsiniz.
6. `requirements.txt` ileride güncellenirse (ör. yeni bir sürümle yeni
   bir paket eklenirse), bir sonraki Revit açılışında sadece eksik
   paket(ler) otomatik olarak kurulur; venv'in tamamı yeniden
   oluşturulmaz.

**Bu adımda bir hata alırsanız:** "pyKalfa otomatik kurulumu başarısız
oldu" başlıklı bir pencere çıkar ve hatanın detayını gösterir. Genelde
sebep, sisteminizde Python'un kurulu olmamasıdır (bkz. Adım A.1).
Ayrıntılı kayıt için `C:\pyKalfa\install.log` dosyasına bakabilirsiniz.

> **Güvenlik ağı:** `startup.py` herhangi bir sebeple çalışmadıysa
> (ör. çok eski bir pyRevit sürümü) veya `C:\pyKalfa\env` klasörü
> sonradan silinmişse, ilk buton tıklaması aynı kurulumu kendisi
> tamamlar — yukarıdaki adımların aynısını, sadece bu kez butona
> bastığınızda görürsünüz.

### B.4. Parsel Görselini Seçme

1. **"parsel.png dosyasını seçin"** başlıklı bir dosya seçme penceresi
   açılır.
2. Parsel sınırlarını içeren PNG dosyanızı bulup seçin (örnek/deneme
   yapmak isterseniz proje klasöründeki `assets\parsel.png` dosyasını
   kullanabilirsiniz).
3. **Aç** (Open) butonuna tıklayın.

> Pencereyi **İptal** ederseniz veya kapatırsanız script tamamen
> sonlanır; baştan (B.2'den) tekrar başlamanız gerekir.

### B.5. Bina Görselini Seçme

1. **"bina.png dosyasını seçin"** başlıklı bir dosya seçme penceresi
   açılır.
2. Bina dış hatlarını içeren PNG dosyanızı bulup seçin (deneme için
   `assets\bina.png` kullanılabilir).
3. **Aç** (Open) butonuna tıklayın.

> **Önemli:** Seçtiğiniz `bina.png`, `parsel.png` ile **aynı coğrafi
> alanı, aynı piksel boyutunda** göstermelidir (aynı haritanın iki
> katmanı olmalıdır) — aksi halde parsel-bina eşleştirmesi ve
> ölçeklendirme yanlış sonuç verir.

### B.6. Harita Ölçeğini Girme

1. **"Ölçek"** başlıklı bir metin girişi penceresi açılır, içinde şu
   soru yazar:
   > *"Harita ölçeği paydasını girin (ör. 500 -> 1:500)"*
2. Kutuya, kaynak haritanızın basım ölçeğinin **sadece paydasını**
   yazın:
   - Harita 1:1000 ölçekli ise → `1000` yazın
   - Harita 1:500 ölçekli ise → `500` yazın (kutuda varsayılan olarak
     zaten `500` yazılı gelir)
3. **Tamam**'a basın.

> Geçersiz bir değer (harf, negatif sayı, boş kutu vb.) girerseniz
> "Geçersiz ölçek değeri" hatası alıp script sonlanır; B.2'den tekrar
> başlamanız gerekir.

### B.7. Parsel Çizgileri İçin Line Style Seçimi

1. **"Parsel çizgileri için line style seçin"** başlıklı bir liste
   penceresi açılır. Bu liste, **açık olan Revit projenizde** o an
   tanımlı olan tüm "Lines" alt kategorilerini (line style'ları) canlı
   olarak gösterir (ör. "LIMITE PARCELLAIRE", "Thin Lines" vb. — proje
   şablonunuza göre değişir).
2. Listeden parsel sınır çizgilerinin çizileceği stili **tek** tıklayıp
   seçin.
3. **Select** (Seç) butonuna tıklayın.

> Eğer projenizde hiç line style tanımlı değilse "Projede tanımlı bir
> line style bulunamadı" hatası alırsınız — bu durumda Revit'te
> **Manage > Object Styles > Lines** altında yeni bir alt kategori
> tanımlayıp tekrar deneyin.

### B.8. Binalar İçin Filled Region Type Seçimi

1. **"Binalar için filled region tipi seçin"** başlıklı bir liste
   penceresi açılır; projenizde tanımlı tüm Filled Region Type'ları
   listeler (ör. "CHAPE DE CIMENT", "Solid Fill" vb.).
2. Bina alanlarının dolgusu için kullanılacak tipi seçin.
3. **Select**'e tıklayın.

> Tanımlı bir Filled Region Type yoksa, Revit'te **Manage > Additional
> Settings > Fill Patterns / Filled Region Types** altından bir tane
> oluşturup tekrar deneyin.

### B.9. Parsel Etiketleri İçin Text Note Type Seçimi

> Bu adım, görselde etiket bulunup bulunmadığına bakılmaksızın sorulur —
> çünkü etiketlerin okunup okunmadığı ancak görüntü işleme bittikten
> sonra belli olur ve o beklemenin ortasında size soru sorulmaması için
> bütün seçimler önden alınır. Etiket bulunamazsa seçtiğiniz tip
> kullanılmadan kalır, bir zararı olmaz.
>
> Projenizde **hiç** Text Note Type tanımlı değilse bu adım atlanır ve
> etiket okuma (OCR) hiç çalıştırılmaz — oluşturulamayacak etiketler
> için en uzun adımı beklemek anlamsız olurdu. Bu, işlemi belirgin
> şekilde hızlandırır.

1. **"Parsel etiketleri (ör. '591G') için text note tipi seçin"**
   başlıklı bir liste penceresi açılır; projenizde tanımlı tüm Text
   Note Type'larını listeler.
2. Etiketlerin yazı stilini seçin.
3. **Select**'e tıklayın.

> **Bilgi:** Etiketler OCR (otomatik metin okuma) ile okunur ve %100
> doğru olmayabilir (ölçülen doğruluk ~%80). Özellikle birbirine
> benzeyen karakterler (G/6, A/4, B/8, S/5 gibi) yanlış okunabilir.
> Oluşan metinleri kaynak görselle karşılaştırıp gerekirse elle
> düzeltmeniz önerilir.

### B.10. Görüntü İşleme (İlerleme Çubuğu)

Bütün seçimleriniz alındıktan sonra asıl işlem başlar. Bu, aracın **en
uzun süren** adımıdır ve bir **ilerleme çubuğu** ile takip edilir.

1. Ekranda yüzde gösteren bir pencere açılır; başlığında o an hangi
   aşamada olunduğu yazar:
   ```
   Ölçek çubuğu ölçülüyor            %5
   Parsel konturları çıkarılıyor     %15
   Bina konturları çıkarılıyor       %30
   Parsel-bina ilişkisi hesaplanıyor %45
   Parsel çizgileri izleniyor        %55
   Parsel numaraları okunuyor (OCR)  %70   <- en uzun adım
   Sonuçlar yazılıyor                %92
   ```
2. İlk beş aşama genelde birkaç saniyede geçer. **Sürenin büyük kısmı
   OCR adımında geçer** (bu örnek dosyada ~8 saniyenin 7,5'i). İlk
   çalıştırmada OCR modeli internetten indirileceği için bu adım
   dakikalar sürebilir — bu normaldir.
3. Bu adımda size soru sorulmaz; beklemeniz yeterlidir.

> **Not:** Çubuk OCR aşamasında bir süre yavaş ilerler. Gerçek OCR
> yüzdesi ölçülemediği için çubuk orada yavaşça sürünerek "çalışıyorum"
> sinyali verir; başlıktaki aşama adı her zaman gerçek durumu gösterir.

### B.11. İşlemin Tamamlanması ve Özet Penceresi

1. Görüntü işleme bitince script, seçtiğiniz görünüme otomatik olarak
   çizgileri, dolgu alanlarını ve (varsa) metin notlarını çizer. Bu,
   parsel/bina sayısına göre birkaç saniye sürebilir.
2. İşlem bitince şu formatta bir özet penceresi çıkar:
   ```
   Parsel çizgisi: X oluşturuldu, Y atlandı
   Bina (filled region): X oluşturuldu, Y atlandı
   Parsel etiketi (text): X oluşturuldu, Y atlandı
   ```
3. **Tamam**'a basarak pencereyi kapatın. İşlem tamamlanmıştır.

> Eğer işlem sırasında beklenmedik bir hata olursa, Revit yaptığı **tüm
> değişiklikleri otomatik olarak geri alır** (hiçbir yarım/bozuk
> geometri projenizde kalmaz) ve hatanın detayını gösteren bir pencere
> açılır.

---

## 3b. Bölüm B2 — Günlük Kullanım: Duvar Aktar

Bu işlev, Polycam (veya başka bir CAD programı) tarafından üretilmiş bir
**kat planı DXF** dosyasındaki çizgileri **gerçek Revit duvarlarına**
(`Wall`) dönüştürür — çizgi/detay elemanı değil, üzerine kapı ve pencere
yerleştirebileceğiniz gerçek duvarlar.

Kurulum adımları (Bölüm A) bu işlev için de aynıdır; ayrıca bir şey
kurmanız gerekmez.

### B2.1. Hazırlık

1. Duvarların oluşacağı Revit projesini açın.
2. İlgili kata ait bir **plan görünümüne** geçin. (Duvarlar model
   elemanı olduğu için teknik olarak şart değildir, ama sonucu hemen
   görebilmek için pratiktir.)
3. Projede en az bir **Level** ve bir **duvar tipi (Wall Type)** tanımlı
   olmalıdır — Revit'in standart şablonlarında zaten vardır.

### B2.2. Butona Basma ve DXF Seçme

1. Üst menüden **pyKalfa** sekmesi → **Duvar** paneli → **"Duvar
   Aktar"** butonuna tıklayın.
2. Açılan dosya seçme penceresinde **DXF dosyanızı** seçin.
3. Script arka planda dosyayı okur (birkaç saniye).

> İlk kez bir pyKalfa butonuna basıyorsanız, önce otomatik ortam kurulumu
> çalışır — bkz. Adım B.3, aynı süreç geçerlidir.

### B2.3. (Sadece Gerekirse) Çizim Birimi Sorusu

Çoğu DXF dosyası hangi birimde çizildiğini kendi içinde belirtir ve bu
adım hiç görünmez. Belirtilmemişse, program çizimin boyutuna bakarak bir
tahmin yapar ve size onaylatır:

- Doğru tahmin edilmişse ilk seçeneği (önerilen) seçin.
- Duvarlar sonradan 1000 kat büyük/küçük çıkarsa, bu adımda yanlış birim
  seçilmiş demektir; tekrar çalıştırıp doğru birimi (genelde **mm** veya
  **m**) seçin.

### B2.4. (Sadece Gerekirse) Çizimi Orijine Taşıma

Çizim Revit'in orijininden ~1,5 km'den uzaktaysa bir soru penceresi
çıkar. **Evet** demeniz önerilir: Revit bu kadar uzakta modellenen
geometride hassasiyet uyarıları verir. Duvarların birbirine göre konumu
değişmez, sadece tamamı orijine kaydırılır.

### B2.5. Katman Seçimi

**Bu adım en önemlisidir.** Kapı, pencere ve geçişler çizimde duvarla
**tamamen aynı şekilde** çizilir (aynı kalınlıkta dış hatlar); onları
duvardan ayıran tek şey hangi katmanda oldukları. Yani doğru katmanı
seçmek, doğru sonucun ön koşuludur.

Program size önce **tek bir öneri** sunar:

```
Duvar katmanı olarak şu öneriliyor:

    Poly-Walls  (7 duvar, 29.3 m, kalınlık 10 cm)

Diğer katmanlar: Poly-Windows, Poly-Openings, Poly-Doors, ...

Bu katman kullanılsın mı?
```

- **Evet** → o katmanla devam edilir (çoğu durumda doğru seçimdir).
- **Hayır** → bütün katmanların listesi açılır, Ctrl ile birden fazla
  seçebilirsiniz.

DXF'te tek katman varsa bu adım atlanır.

### B2.6. Duvar Yüksekliği, Level ve Duvar Tipi

1. **Duvar yüksekliği:** metre cinsinden girin (varsayılan `2.80`).
2. **Level:** duvarların bağlanacağı kat. Liste, her seviyenin adının
   yanında yüksekliğini de gösterir (ör. `Kat 1  (+0.00 m)`).
3. **Wall Type:** projenizde tanımlı duvar tiplerinden biri. (Perde duvar
   tipleri listelenmez.) Pencere başlığında **çizimden ölçülen kalınlık**
   yazar — ör. *"Duvar tipini seçin (çizimde ölçülen: 10 cm)"*. Buna en
   yakın kalınlıktaki tipi seçmeniz önerilir; program tipi sizin yerinize
   seçmez, çünkü projenizdeki tip isimleri/katmanları sizin bileceğiniz
   bir şeydir.

### B2.7. Onay ve Sonuç

1. Son bir onay penceresi kaç duvarın, hangi tiple, hangi level'de ve
   hangi yükseklikte oluşturulacağını özetler. **Evet** deyin.
2. İşlem bitince şu formatta bir özet çıkar:
   ```
   Oluşturulan duvar: X
   Oluşturulamayan: Y
   Toplam duvar uzunluğu: Z m
   ```
3. Oluşturulamayan çizgi varsa, pyRevit'in çıktı penceresinde bunlar
   **katman, uzunluk, konum ve hata sebebiyle** tablo halinde listelenir.

> **Sonucu beğenmediyseniz:** aktarımın tamamı tek bir işlemdir, Revit'te
> tek bir **Ctrl+Z (Undo)** ile hepsini geri alabilirsiniz.

### B2.8. Sonucu Kontrol Etme ve Düzeltme

Bu araç duvarların **çoğunu** doğru yere koymayı hedefler, hepsini
değil. Beklenen çalışma şekli:

1. Aktarımdan sonra planı gözden geçirin.
2. Kaymış/eksik/fazla duvarları Revit'in kendi araçlarıyla elle
   düzeltin — bu normaldir ve tasarım gereğidir.
3. **Kapı/pencere boşlukları duvardan çıkarılmaz.** Duvarlar boydan boya
   sürekli oluşturulur; kapı ve pencereleri Revit'te yerleştirdiğinizde
   Revit duvarı zaten kendisi keser. Bu bilinçli bir tercihtir.
4. Duvar kalınlığı çizimden **ölçülür ve size gösterilir**, ama Revit'e
   dayatılmaz: duvarın gerçek kalınlığı seçtiğiniz `Wall Type`'tan gelir.
   Farklı kalınlıklar istiyorsanız duvarları seçip tipini değiştirin.
5. Eğri (yay) duvarlar düz parçalarla temsil edilir.

> **Not:** Program duvarları çizimdeki **dış hatlarından** tanır ve her
> fiziksel duvar için **tek** bir Revit duvarı üretir. Eğer sonuçta her
> duvarın yerinde iki ince duvar görüyorsanız, bu çizimin duvarları
> kapalı dış hat olarak çizmediği (ve programın "tek çizgi moduna"
> düştüğü) anlamına gelir — Bölüm D'deki ilgili satıra bakın.

---

## 4. Bölüm C — Sonucu Kontrol Etme (Parsel/Bina Aktar)

1. Aktif görünümde (B.1'de seçtiğiniz görünüm), turuncu/varsayılan
   renkte ince çizgilerin (parsel sınırları) ve dolgulu alanların
   (binalar) belirdiğini görmelisiniz.
2. Bir çizgiye veya dolgulu alana tıklayarak Revit'in bunu normal bir
   `Detail Line` / `Filled Region` elemanı olarak tanıdığını
   doğrulayın (Properties panelinde ilgili tip bilgisi görünür).
3. Etiketler varsa, bunların parsel numaralarıyla eşleştiğini kaynak
   `parsel.png` görseliyle karşılaştırarak kontrol edin.
4. Sonuçtan memnun değilseniz (ör. çizgiler yanlış konumda, ölçek
   tutmuyor gibi görünüyorsa): oluşan elemanları seçip silin, Adım
   B.2'den başlayarak farklı bir ölçek değeriyle (Adım B.6) tekrar
   deneyin.

---

## 5. Bölüm D — Sık Karşılaşılan Durumlar ve Çözümleri

| Durum | Muhtemel Sebep / Çözüm |
| --- | --- |
| Buton hiçbir şey yapmıyor / pyKalfa sekmesi görünmüyor | Adım A.5'i (extension tanıtma) tekrar kontrol edin; pyRevit'i "Reload" edin veya Revit'i yeniden başlatın. |
| "Aktif view bir plan/detay/kesit/cephe view'i olmalı" | 3D görünümdesiniz; Adım B.1'e dönüp 2D bir görünüme geçin. |
| Kurulum (ilk açılışta otomatik) çok uzun sürüyor / hiç bitmiyor | İnternet bağlantınızı kontrol edin. OCR kütüphanesi büyük (~1-1.5 GB), yavaş bağlantılarda 10+ dakika sürebilir. |
| **`ERROR: ... [WinError 206] Dosya adı veya uzantısı çok uzun`** | `env/` artık her zaman sabit ve kısa bir yolda (`C:\pyKalfa\env`) kurulduğu için bu hata normalde hiç çıkmaz — extension'ı nereye klonladığınızın önemi yok. Yine de çıkarsa: Yönetici olarak PowerShell açıp şunu çalıştırın: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force`, sonra bilgisayarı yeniden başlatıp `C:\pyKalfa\env` klasörünü silip Revit'i tekrar açın. |
| "pyKalfa otomatik kurulumu başarısız oldu" | Sisteminizde Python kurulu olduğundan emin olun (Adım A.1). Ayrıntı için `C:\pyKalfa\install.log` dosyasına bakın, sonra Revit'i yeniden açın (kurulum otomatik tekrar denenir). |
| "Görüntü işleme başarısız oldu" | Genelde yanlış dosya seçimi veya geçersiz ölçek değeridir; hata mesajındaki detayı okuyun. |
| "Projede tanımlı bir line style / Filled Region Type / Text Note Type bulunamadı" | Revit projenizde ilgili tip tanımlı değil; Manage sekmesinden en az bir tane oluşturup tekrar deneyin. |
| Parsel çizgileri/bina alanları yanlış yerde veya çok küçük/büyük görünüyor | Adım B.6'da girilen ölçek değerini kontrol edin; kaynak haritanın gerçek basım ölçeğiyle eşleştiğinden emin olun. |
| Bazı parsel etiketleri yanlış/anlamsız görünüyor | OCR %100 doğru değildir (~%80); kaynak görselle karşılaştırıp elle düzeltin. |
| İşlem "geri alındı, hata oluştu" diyor | Çıkan hata mesajının tamamını okuyun; genelde geçici bir Revit API sorunudur, işlemi tekrar deneyin. |

### Duvar Aktar'a özel durumlar

| Durum | Muhtemel Sebep / Çözüm |
| --- | --- |
| **Her duvarın yerinde iki ince duvar var** | Çizim, duvarları kapalı dış hat olarak çizmemiş ve program "tek çizgi moduna" düşmüş; bu modda duvarın iki yüzü iki ayrı duvar sanılır. Adım B2.3'te tek çizgi modu sorusu çıktıysa sebep budur. **Ctrl+Z** ile geri alın ve DXF'i üreten programdan duvarları dış hat olarak veren bir dışa aktarım deneyin. |
| **Saçma yerlerde duvarlar var** | Büyük olasılıkla Adım B2.5'te yanlış katman(lar) seçilmiş — ölçülendirme, logo, pusula katmanları da duvara dönüşmüş olabilir. **Ctrl+Z** ile geri alıp sadece önerilen duvar katmanını seçin. |
| Kapı/pencere yerlerinde de duvar oluşmuş | Adım B2.5'te kapı/pencere katmanları da seçilmiş. Bunlar duvarla aynı şekilde çizildiği için ancak katmanla ayrılabilir. |
| "Duvara dönüştürülebilecek geometri bulunamadı" | Çizimde kapalı duvar dış hattı yok; program tek çizgi modunu önerecektir. O da bir şey bulmazsa DXF'te sadece eğri (SPLINE/ARC) veya tarama (HATCH) olabilir — bu sürüm bunları okumaz. |
| Çizimde duvar var ama program bulamıyor | Yanlış birim seçilmiş olabilir: 20 cm'lik bir duvar "m" olarak okunursa 200 m kalınlık olur ve makul duvar aralığının dışına düşer. Adım B2.3'te doğru birimi seçin. (Bu, aracın sessizce 1000 kat büyük duvar üretmesini önleyen kasıtlı bir korumadır.) |
| Duvarlar projede çok uzakta / Revit "koordinat çok büyük" uyarısı veriyor | Adım B2.4'teki "orijine taşı" sorusuna **Evet** deyin. |
| "Oluşturulamayan: N" diyor | pyRevit'in çıktı penceresindeki tabloya bakın; her satırda hangi çizginin neden oluşamadığı yazar. Genelde çok kısa çizgilerdir ve göz ardı edilebilir. |
| Duvar kalınlıkları çizimdeki gibi değil | Kalınlık çizimden ölçülüp size gösterilir ama Revit'e dayatılmaz; seçtiğiniz **Wall Type**'tan gelir. Duvarları seçip tipini değiştirin. |

---

## 7. Ek — Terimler Sözlüğü

| Terim | Açıklama |
| --- | --- |
| **pyRevit** | Revit içinde özel araçlar/butonlar çalıştırmayı sağlayan ücretsiz bir eklenti. |
| **DetailLine** | Revit'te sadece görünüme özel, 2 boyutlu çizilen ince bir çizgi elemanı. |
| **FilledRegion** | Revit'te belirli bir desenle (hatch/solid) doldurulmuş, kapalı sınırlı bir alan elemanı. |
| **TextNote** | Revit'te bir görünüme yazılan metin notu elemanı. |
| **Line Style** | Bir çizginin görünümünü (renk, kalınlık, kesikli/düz) belirleyen tanım. |
| **Filled Region Type** | Bir dolgulu alanın deseni ve rengini belirleyen tanım. |
| **Text Note Type** | Bir metin notunun yazı tipi/boyutunu belirleyen tanım. |
| **OCR** | "Optical Character Recognition" — bir görüntüdeki yazıyı otomatik olarak okuyup metne çeviren teknoloji. |
| **Sanal ortam (venv)** | Python programlarının izole çalıştığı, projeye özel bir klasör; sistemin geri kalanını etkilemez. |
| **Ölçek paydası** | 1:1000 gibi bir ölçek ifadesindeki "1000" sayısı. |
| **DXF** | CAD programları arasında çizim alışverişi için kullanılan dosya biçimi (Polycam kat planlarını bu biçimde verir). |
| **Katman (Layer)** | CAD çizimlerinde elemanların gruplandığı isimli katmanlar (duvar, mobilya, ölçülendirme gibi). |
| **Wall / Wall Type** | Revit'te gerçek duvar elemanı ve onun kalınlık/malzeme tanımı. |
| **Level** | Revit'te bir kat seviyesi; duvarlar bir level'e bağlı olarak yükselir. |

---

*Bu kılavuz pyKalfa projesiyle birlikte gelir. Teknik detaylar ve
geliştirme geçmişi için proje klasöründeki `README.md` ve `ROADMAP.md`
dosyalarına bakabilirsiniz.*
