---
type: protocol
status: current
updated: 2026-09-21
tags:
  - test
  - measurement
  - environment
---

# Test ve ölçüm ortamı

Hangi koşuda alınan sonucun kanıt sayılabileceğini belirler. Bir ölçüm yanlış
ortamda alındıysa "çalıştırılmış test" değildir.

## Ortam

Yalnız mevcut `KineSynth` conda ortamı kullanılır:
`C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`. Betikler ortamı bulamazsa
başka ortama düşmez, durup ne yapılacağını söyler.

## Koşu biçimi

- **Tam `pytest` tek süreçte bitmiyor.** F1'de yaklaşık 28 dakikada
  tamamlanmadı; dosya dosya koşuda 39 dosyanın 38'i yaklaşık 6 dakikada yeşildi.
  Sonraki bütün turlarda kabul koşusu **dosya dosya** yapıldı ve proje kuralı
  hâline geldi. 19 Eylül 2026'da yeniden doğrulandı: tek süreçte 20+ dakikada
  bitmedi, dosya dosya 83 dosya **1786 s**'de yeşildi.
- `verified` **Neden** (23 Eylül 2026, yayın kapısı A1): testlerin kapatıp
  silmediği pencereler süreçte birikiyor (kimlik testlerine gelindiğinde 322
  üst düzey pencere, 15 527 widget) ve her `build_window` uygulama geneli stil
  sayfasını uyguluyor; bu maliyet canlı widget sayısıyla doğrusal (0 / 1 960 /
  3 920 / 7 889 / 15 827 widget için 0,02 / 0,76 / 1,52 / 3,17 / 6,64 s), toplam
  süre ikinci dereceden büyüyor. Ürün tek pencereyle çalıştığı için bu bir test
  düzeneği sorunu. `scripts/run_tests.ps1` artık **varsayılan olarak dosya
  dosya** koşar (`-Files`, `-Report`, `-LogDir`; eski davranış
  `-SingleProcess`). [Faz A raporu](../reports/release-gate-phase-a-2026-09-23.md).
- Tek dosyalık ve hedefli koşular normal biçimde çalışır.

## Qt platformu

- **`QT_QPA_PLATFORM=offscreen` altında font ailesi yoktur.** Bu denetimde
  yeniden ölçüldü: `QFontDatabase.families()` boş liste döndürüyor. Her metin
  tofu kutusu olarak ölçüldüğü için **yerleşim, genişlik, kırpılma ve minimum
  boyut ölçümleri offscreen'de geçersizdir**; aynı kabuk offscreen'de 1514 px
  minimum genişlik iddia ederken gerçek platformda 1120 px'e sığıyordu.
- Yerleşim ve görsel kabul ölçümleri `QT_QPA_PLATFORM=windows` ile, gerçek
  pencerede alınır. Çizim/segfault testleri offscreen'de kalabilir.
- Sonuç: 2026-09-13 öncesindeki offscreen yerleşim ölçümleri şüphelidir.

Bu madde
[eski test komutları notundaki](../archive/memory/8-8-test-komutlari.md)
"GUI testleri offscreen ile çalışır" ifadesini `superseded` yapar.

## Font genişliği: yanlış anda ölçmek

Tema stil sayfası **uygulamaya**, widget'lar kurulduktan sonra veriliyor.
`__init__` içinde `QFontMetrics(widget.font())` ile alınan bir genişlik
varsayılan yüzden ölçülür ve gerçek yüz geldiğinde yanlış kalır.

19 Eylül 2026'da bu iki yerde gerçek kusur üretti: `_Metric` genişlik tabanı
24 px çıkıyordu, dört mono rakam 28 px istiyordu; sayaç dört haneye çıkınca
yanındaki okuma kayıyordu. Geri sayım yuvasında aynı hata `setFixedWidth`
olduğu için kaydırmak yerine **kırpıyordu**.

Kural: ayrılmış genişlik `FontChange` / `StyleChange` /
`ApplicationFontChange` olaylarında **yeniden** ölçülür; sayfa düzeyindeki
olay ayrıca cilalanan bir çocuğa her zaman ulaşmadığı için `showEvent` de
eklenebilir. Bu sınıfın tamamı `offscreen`'de görünmezdir: font veritabanı
yokken bütün glifler aynı genişlikte olduğu için yanlış ölçüm ile doğrusu
aynı sayıyı verir.

## Bir widget'ın `sizeHint`'i önbelleklidir ve yanlış olabilir

`QWidget.sizeHint()` hesaplanmış değeri saklar. Bir kez kötü koşulda ölçülen
widget sonsuza dek o değeri bildirir. 21 Eylül'de bildirim kartı, düğmeleri üç
satıra sarmış hâlde bir kez ölçüldü; sonrasında 134 piksellik içerik için
**286 piksel** bildirdi ve o boyda çizildi.

Kural: yerleşim ölçerken **layout'un** `sizeHint()`'ini oku, widget'ınkini
değil. Layout her çağrıda yeniden hesaplar.

İkinci tuzak aynı gün: geometrisi olmayan bir widget'ın `sizeHint`'i anlamsızdır.
Yakalama ekranının durum bölmesi, yerleşimden **önce** ölçüldüğünde
**2000 piksel** döndü; o değer "ayrılmış yükseklik" olarak dondurulunca konsol
gereksiz yere iki sütuna geçti. Yükseklik ayırmayı ilk gerçek yerleşimden
sonra yap.

Üçüncüsü: "bir daha küçülmesin" kuralını widget'ın **o anki yüksekliğine**
karşı yazma. Yazı tipinden gelen değere karşı yaz; yoksa ilk saçma değer
kalıcı olur.

## Bir bant çözüldükten sonra büyürse üstüne çizer

`QVBoxLayout`, kendisine minimumundan az yer verilince kırpmaz — **üst üste
bindirir**. Bu yüzden bant yüksekliklerini bölüşen bir çözücü, bölüşürken
kullandığı sayıların gerçek olduğundan emin olmalı. 21 Eylül'de etiketleme
ekranının araç çubuğu ilk gösterimde 48, sayfadan çıkıp dönüldüğünde 62 piksel
bildirdi; çözücü küçük sayıyla bölüştü, bant büyük olanı aldı ve editör
sahnenin **10 piksel** üstüne bindi.

Kural: kendi boyunu kendi belirleyen bir bandın yüksekliğini `sizeHint` ile
değil, `max(sizeHint, minimumSizeHint, height)` ile sor; ve o bant yeniden
boyutlanınca **yeniden çöz** (event filter).

## Uzun Windows yolu: uygulama açabilir, SDK açamaz

Bu makinede `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem
\LongPathsEnabled = 0`. 279 karakterlik bir hedefte ölçüldü:

| çağrı | sonuç |
|---|---|
| çıplak `CreateFileW` | başarısız, WinError 3 |
| çıplak `CreateFileA` | başarısız, WinError 3 |
| `\?\` önekli `CreateFileW` | başarılı |

Projenin kendi yazıcıları `core/paths.long_path` ile önek koyduğu için aynı
derinliğe sorunsuz yazar. Çıplak yol alan her kütüphane (ZED SDK, OpenCV)
yazamaz. Bir hedefi kütüphaneye vermeden **önce** uzunluğunu sor.

## `QOpenGLWidget` üstüne yazılan metin görünmez

`QPainter` ile bir `QOpenGLWidget`'in üstüne yazmak **çalışmıyor**: ne
`paintEvent` içinde `super().paintEvent(event)` sonrası, ne de `paintGL`
sonunda. Widget kendi framebuffer'ına çiziyor ve gösterilen o; sonradan
açılan painter kimsenin görmediği bir yüzeye çiziyor.

20 Eylül'de ölçülerek bulundu: GL hazır, not atanmış, picking açıkken
widget'ın grab'inde bannerın renginden **0/99 piksel** vardı. Çocuk widget'a
çevrildikten sonra **85/99**. Bu, 3B görünümdeki bütün notları kapsıyordu -
"Bu sürümde 3B eklem verisi yok." dahil.

Kural: 3B görünümün üstündeki her metin **çocuk widget** olarak çizilir.
Testte "metin atandı mı" değil **görünür mü** sorulur; ilk yazılan test yalnız
dizgeyi okuduğu için iki başarısız denemeden de geçmişti.

## Ölçümden önce oturum açmak

Kabuk giriş ekranında açılıyor. Oturum açılmadan yapılan her GUI ölçümü,
arkasındaki sayfalar haritalanmamış olduğu için anlamsızdır: widget'lar
varsayılan boyutta kalır ve `QOpenGLWidget` hiç `paintGL` çalıştırmaz.
19 Eylül'deki ilk performans koşusu tam olarak bu yüzden **sıfır** boya
örneği üretti.

Aynı şekilde widget sayımıyla sızıntı aranırken taban ölçüm, döngüde
ziyaret edilecek bütün sayfalar **bir kez kurulduktan sonra** alınmalıdır;
yoksa bir sayfanın tek seferlik yapımı (ölçülen örnekte 63 widget) sızıntı
gibi görünür. `deleteLater` da ayrıca boşaltılmalıdır
(`sendPostedEvents(None, DeferredDelete)`).

## Süreç geneli stil sızıntısı

`studio/views/theming.py:44` temayı `QApplication.setStyleSheet` ile
**süreç geneli** uygular. Aynı pytest sürecinde önce Studio testleri koşarsa
eski `gui/` widget ölçümleri bozulur; gözlenen örnek bir butonun 20 px yerine
46 px ölçülmesidir. Gerçek üründe tek arayüz çalıştığı için bu bir ürün hatası
değil, bir **ölçüm tuzağıdır**. Eski GUI ölçüm testi kendi stil sayfasıyla
yalıtılmış fixture kullanır.

## Bilinen aralıklı testler

| Test | Davranış | Durum |
|---|---|---|
| `tests/test_processing_pipeline.py` duraklat/sürdür | yaklaşık üç koşudan birinde takılıyor; alt sürecin `job.json`'a `paused` yazmasını bekleyen zamanlama yarışı | `observed` |
| `tests/test_identity.py:269` `test_participant_codes_are_unique_under_concurrent_allocation` | tam suite yükünde Windows dosya kilidi yarışıyla `PermissionError`; izole koşuda tekrar tekrar geçiyor | `observed`, en az 2026-08-31'den beri |

İkisi de bu çalışmalardan önce vardı ve ilgili modüller değişmeden de
düşebiliyor. Bir turda düştüklerinde önce izole koşuyla ayırt edin.

## Açık çelişki

`scripts/run_tests.ps1` 23 Eylül'den beri dosya dosya koşar; ama hâlâ
`QT_QPA_PLATFORM = 'offscreen'` ayarlar (testlerin varsayılanı da odur). Font ve
yerleşim ölçen **GUI kabul** koşuları `windows` platformuyla yapılmalıdır; genel
regresyon koşusu için betik yeterlidir.

İlgili: [Veri bütünlüğü ve kanıt](../concepts/data-integrity.md),
[AI hafıza iş akışı](ai-memory-workflow.md),
[Açık sorular](../open-questions.md),
[Hafıza aktarım denetimi](../audits/claude-memory-migration-audit-2026-09-18.md).

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [8. Test komutları](../archive/memory/8-8-test-komutlari.md)
- [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](../archive/memory/9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md)
- [QFont::setPointSize uyarısı — Qt kaynaklı, kanıtlandı](../archive/memory/6i-09-qfont-setpointsize-uyarisi-qt-kaynakli-kanitlandi.md)
- [Gerçekten çalıştırılanlar](../archive/memory/6i-10-gercekten-calistirilanlar.md)
- [Bu turda GERÇEKTEN çalıştırılanlar](../archive/memory/6g-09-bu-turda-gercekten-calistirilanlar.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
