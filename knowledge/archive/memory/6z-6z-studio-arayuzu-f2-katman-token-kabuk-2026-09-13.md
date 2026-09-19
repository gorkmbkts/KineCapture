---
type: legacy-memory-section
status: archived
title: "6Z. Studio arayüzü F2 — katman, token, kabuk (2026-09-13)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2666-2747"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6y-6y-pyside6-arayuz-yeniden-yapimi-f0-hafiza-politikasi-f1-tespiti-2026-09.md) · [sonraki](6aa-6aa-studio-f3-backend-toplamsal-ekleri-processing-1-1-0-2026-09-13.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

## 6Z. Studio arayüzü F2 — katman, token, kabuk (2026-09-13)

Plan dosyası: `FAZ_PLANI_PYSIDE6_STUDIO.md` (faz sırası, kapsam dışı, ilerleme
kaydı orada; burada yalnız kalıcı kararlar ve ölçümler).

### Kullanıcı kararı — geriye dönük uyumluluk aranmıyor

Bugüne kadar toplanan veri test amaçlıydı; **yeni arayüzde görünmesi
gerekmiyor**. Mevcut veri **silinmeyecek**, ileride test için duracak. Bu karar
göç kodunu, çift okuma yolunu ve `segments.json` dönüştürücüsünü kapsam dışına
çıkardı.

### Kalıcı mimari kararlar

1. **Yeni arayüz ayrı pakettir: `kinecapture/studio/`.** Eski `gui/` silinmedi,
   bozulmadı ve `python -m kinecapture --legacy-gui` ile açılıyor — raw-first
   politikasından önceki kayıtları açabilen tek arayüz odur. Varsayılan
   `python -m kinecapture` artık Studio'yu açar.
2. **Üç katman, fiziksel sınır.** `studio/services/` ve `studio/viewmodels/`
   (ve `studio/theme/`) Qt import etmez. `tests/test_studio_layers.py` bunu iki
   şekilde denetler: PySide6 import'unun `AssertionError` fırlattığı bir alt
   süreçte paketleri gerçekten kullanır, ayrıca AST ile import taraması yapar
   (grep değil — bu dosyaların docstring'leri kuralın kendisinden bahsediyor).
3. **ViewModel → View iletişimi saf Python.** `Observable` (yalnız gerçek
   değişimde bildirir), `Event` (değer tutmaz; geç abone eski hatayı almaz),
   `Subscriptions`. Qt sinyaline çevirme yalnız `views/qt_bridge.py` içinde.
4. **`tokens.json` tek gerçek kaynak.** Renk/ölçü/tipografi oradan;
   `studio.qss.tmpl` yalnız `@Token@` yer tutucuları içerir; üretici çözülmemiş
   token bırakırsa hata verir. Widget'ta literal renk yasak ve testle sabit.
   Token adları WinUI kaynak adı gibi (`KcSurfaceBase`, `KcStatusRecording`).
   Renk anlam taşır: kırmızı kayıt/hata, sarı uyarı, yeşil canlı/tamam, mavi
   seçim.
5. **QSS'te evrensel `QWidget` kuralı arka plan boyamaz.** Yalnız `QMainWindow`
   ve adlandırılmış yüzeyler boyar; aksi hâlde her düz konteyner kendi
   dikdörtgenini ebeveyninin üstüne damgalıyor ve panel içinde hayalet kutular
   çıkıyordu (gerçekten görüldü ve düzeltildi).
6. **İkon seti: Lucide 0.462.0, ISC.** 25 SVG + lisans metni paket verisi.
   `currentColor` çalışma anında token rengiyle değiştiriliyor (Qt SVG'de
   cascade yok), device pixel ratio'da render ediliyor. Ürün sözlüğü
   (`record`, `cpu`) ile dosya adı arasında bir eşleme tablosu var; set
   değiştirilirse yalnız o tablo değişir.
7. **Pencere durumu `core/jsonio` ile atomik yazılıyor** (`QSettings` değil);
   bozuk/okunamayan dosya varsayılana düşer ve açılışı engellemez.
8. **İki katmanlı hata dili veri olarak modellendi** (`services/messages.py`):
   görünen `headline`/`detail`, "Ayrıntılar" altında `code` + `technical`.
   `sys.excepthook` yakalanmamış istisnayı bu mesaja çevirir; arayüz ayakta
   kalır.

### Ölçülenler (gerçekten çalıştırıldı)

- Soğuk açılış, gerçek süreç, `windows` platformu, üç koşu: **1,29 / 1,34 /
  1,29 s** (hedef ≤3 s).
- Kabuk kurulumu + `show()` süreç içinde 806 ms.
- 1120×700, 1366×768, 1600×980 × koyu/açık: `minimumSizeHint` hepsinde sığıyor,
  kırpılma yok.
- Sayfalar tembel kuruluyor: açılışta 1 sayfa.
- Qt-bağımsızlık alt süreç testi geçiyor.

### Önemli ortam gerçeği — `offscreen` platformunda font yok

`QFontDatabase.families()` **offscreen** Qt platformunda **boş liste** döndürür.
Bütün metin tofu kutusu olarak çizilir ve gerçek metinden geniş ölçülür: aynı
kabuk offscreen'de 1514 px minimum genişlik iddia ederken `windows`
platformunda 1120'ye sığıyor. **Yerleşim/genişlik ölçümleri offscreen'de
yapılamaz.** Studio yerleşim testleri bu yüzden offscreen'de atlanıyor ve
`QT_QPA_PLATFORM=windows` ile çalıştırılıyor. Bu, eski turlardaki offscreen
ölçümlerinin de yeniden değerlendirilmesini gerektirebilir.

### Onarılan gerçek hata

`tests/test_raw_capture_fields.py` içindeki beş kırmızı test: yardımcı `sl`
yerine düz `object()` veriyordu, 6V'de eklenen `_check_retrieval` ise
`sl.ERROR_CODE.SUCCESS` okuyor. Stub gerçek SDK sözleşmesini taklit edecek
biçimde düzeltildi ve başarısız retrieval'ın `CameraError` fırlattığını sabitleyen
yeni bir test eklendi. Uygulama kodu değişmedi.

### Sürümler

Hiçbir veri şeması değişmedi. `studio.STUDIO_VERSION = 0.1.0` eklendi (arayüz
sürümü, veri sözleşmesi değil). app/package 0.11.0 ve diğer bütün şema
sürümleri 6V'deki gibi.
