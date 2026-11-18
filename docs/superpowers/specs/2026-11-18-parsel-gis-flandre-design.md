# Parsel/Bina GIS — Flaman bölgesi (kısa tasarım)

Tarih: 2026-11-18 · Durum: kullanıcı onayladı ("Ekle")

## Amaç

Parsel/Bina GIS butonu bugün yalnız Valonya'da çalışıyor (SPW/ICAR). Kullanıcı
Flaman bölgesinde de aynı butonu kullanmak istiyor. Adres arandığında iki
bölgenin sonuçları **aynı listede** gelir, kullanıcı seçer (kullanıcı). Bölge
sorulmaz. Brüksel kapsam dışı (kullanıcı: "Valonya ve Flaman yeterli").

## Hedefler / hedef dışı

- Aynı akış, aynı stil seçimleri, aynı çizim (`revit_input.json` biçimi değişmez).
- Adres önerisi: Valonya (ICAR) + Flaman (Digitaal Vlaanderen geolocation v4) birleşik.
- CaPaKey: önce Valonya, bulunamazsa Flaman.
- Flaman verisi: parsel `Adpf:Adpf`, bina `GRB:GBG`, yol/kaldırım kenarı `GRB:WGO`
  (TYPE 1 zayıf yol kullanıcısı bölgesi sınırı = kaldırım/bisiklet, 2 stabilize
  bölge sınırı, 3 rijbaan kenarı — üçü de), sokak adı `GRB:Wegsegment`
  (`LSTRNM`, yoksa `RSTRNM`).
- Hedef dışı: Brüksel, eski `loc.geopunt.be` (cevap vermiyor).

## Doğrulanmış servis davranışı (2026-11-18)

- `geo.api.vlaanderen.be/geolocation/v4/Location?q=..&c=N` → `LocationResult[]`,
  `Location.X_Lambert72/Y_Lambert72`, `FormattedAddress`, `LocationType`
  (`..huisnummer..` = adres noktası). Kısmi sorguda boş dönebilir.
- `.../Suggestion?q=..&c=N` → yalnız metin listesi (koordinatsız).
- Yalnız kendi bölgesini döndürür (Valonya adresi → boş).
- WFS (`/Adpf/wfs`, `/GRB/wfs`), `outputFormat=application/json`,
  `srsName=EPSG:31370`, `bbox=..,EPSG:31370`; `CQL_FILTER` çalışıyor.
- `startIndex` sayfalaması 45 s'de 504 veriyor → **sayfalama yok**: tek istek
  `count=5000`; sınır dolarsa kutu 4'e bölünür (derinlik ≤ 3), `OIDN`/`UIDN`
  ile tekilleştirilir. 1 km² Brugge merkezi: her katman < 1 s, ≤ 3800 kayıt.

## Yaklaşım (benim kararım)

- `pysrc/parsel_gis/flanders.py`: `services.py` ile aynı imzalar ve aynı dönüş
  biçimleri (`suggest`, `parcel_by_capakey`, `parcel_by_point`, `parcels_in_box`,
  `buildings_in_box`, `road_lines_in_box`, `street_axes_in_box`).
- `pysrc/parsel_gis/regions.py`: `REGIONS = {"wal": services, "vla": flanders}`,
  `suggest_all`, `parcel_by_capakey_any`, `module(region)`, adlar/kaynak notları.
- Her aday `region` taşır; Revit betiği listede bölgeyi gösterir
  ("..., Valonya" / "..., Flaman") ve `--region` ile `suggest_cli --x/--y` ve
  `prepare_gis_input`'a iletir. Varsayılan `wal` (eski çağrılar bozulmaz).
- Parsel numarası her iki bölgede CaPaKey'den çözülür (Flaman `attributes`
  CaPaKey'den üretilir).
- Bir bölge servisi düşerse öbürünün adayları yine gösterilir; ikisi de düşerse hata.
- Kaynak notu (attribution) bölgeye göre.

## Doğrulama

Sahte HTTP ile çevrimdışı testler + `selftest.py --live` (her iki bölge).
Revit'te kullanıcı: Flaman adresi seç → çizim, Valonya hâlâ aynı.
