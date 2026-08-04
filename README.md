# pyKalfa

**Türkçe** · [English](README.en.md) · [Français](README.fr.md)

Revit için pyRevit eklentisi. Kadastro görüntülerinden parsel ve bina
geometrisi, kat planı DXF'inden de gerçek duvarlar üretir.

## Özellikler

| Buton | Ne yapar |
| --- | --- |
| **Parsel/Bina Aktar** | Kadastro görüntülerinden (PNG) parsel sınırlarını `DetailLine`, bina alanlarını `FilledRegion`, parsel numaralarını `TextNote` olarak Revit'e çizer. |
| **Duvar Aktar** | Kat planı DXF'indeki duvarları gerçek Revit `Wall` elemanlarına dönüştürür. |

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

## Lisans

[MIT](LICENSE)
