---
type: legacy-memory-section
status: archived
title: "6AB. Studio F4–F7 — ekranlar, ayrı süreç, kütüphane (2026-09-13)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2858-2936"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6aa-6aa-studio-f3-backend-toplamsal-ekleri-processing-1-1-0-2026-09-13.md) · [sonraki](7-7-mimari-sinirlar.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

## 6AB. Studio F4–F7 — ekranlar, ayrı süreç, kütüphane (2026-09-13)

Kullanıcı F4'ten F7'ye kadar onay beklemeden devam edilmesini istedi. Plan ve
ölçüm tabloları `FAZ_PLANI_PYSIDE6_STUDIO.md` bölüm 7'de; burada yalnız kalıcı
kararlar ve ölçümle bulunan gerçekler.

### Kalıcı mimari kararlar

1. **`TaskRunner` arayüzü** (`studio/viewmodels/tasks.py`): viewmodel yavaş işi
   bir arayüze veriyor, Qt'yi görmüyor. `QtTaskRunner` `QThreadPool` kullanıyor
   ve sonucu **kuyruklu sinyalle GUI thread'ine** taşıyor. Testler
   `InlineRunner` ile senkron çalışıyor; viewmodel davranışı işin ertelenip
   ertelenmediğine bağlı olamaz.
2. **Tek tablo modeli** (`studio/views/models.py`): `QAbstractTableModel` +
   arama proxy'si. Sütun, satır nesnesinden metne bir fonksiyondur; model
   take/katılımcı/proje bilmez.
3. **İşleme alt süreçte.** `python -m kinecapture.processing` import edilmiyor,
   `subprocess` ile başlatılıyor. Gerekçe sırayla: SDK orada açılıyor, hiçbir
   davranışı çizimi bloklayamaz, işletim sistemi onu duraklatıp
   sonlandırabilir. İlerleme **`job.json`'dan** okunuyor; ikinci bir kopya yok.
4. **Kütüphane satırı hiçbir şey açmıyor.** Sürüm açmak checksum doğrulaması
   demek; satırlar yalnız türetilmiş indeksten ve `job.json`'dan kuruluyor.
   Önizlemeler F3'te üretildi, ekran yalnız dosya okuyor.
5. **Giriş kapısı**: çalışma alanı kapının arkasında, giriş yapılmadan hiçbir
   sayfa kurulmuyor. Parola hiçbir yerde saklanmıyor, kullanıldığı anda
   alandan siliniyor.
6. **Ayarlar all-or-nothing**: bir alan geçersizse hiçbiri yazılmıyor, eski
   değer yürürlükte kalıyor, sorun kendi alanının altında söyleniyor.
7. **Kişi seçimi gösterilen kareye bağlanıyor**; iki kişi örtüşüyorsa seçim
   yapılmıyor. Yanlış kişi, tekrar sormaktan kötüdür.

### Ölçümle bulunan gerçekler

- **Python tablo modeli çizimde C++ `QTableWidget`'tan pahalı**: 1000 satırda
  tam viewport çizimi 21 ms / 15 ms. Karşılığında doldurma satır sayısından
  **bağımsız** (1000 ve 5000 satırda ~45 ms; eski desen 36 / 183 ms) ve hücre
  başına nesne üretilmiyor. Bu bir takas, kazanç değil.
- **`view.setSortingEnabled(True)` proxy'yi her veri sıfırlamasında yeniden
  sıralatıyor** ve sıralama her karşılaştırmada `data()` ile Python'a giriyor:
  1000 satır doldurma **224 ms**. Sıralama modelin içine alınınca
  (önbelleklenmiş anahtarlar üzerinde tek `list.sort`) **42 ms**. Aynı sebeple
  arama da satır başına birleştirilmiş metin önbelleğine alındı (5000 satırda
  308 → 74 ms).
- **PySide6 6.10'da `invalidateFilter` ve `invalidateRowsFilter` deprecated**;
  `invalidate()` kullanılmalı. Proje kendi DeprecationWarning'lerini hata
  sayıyor.
- **Mock backend varsayılan olarak hız sınırlaması yapmıyor** (`real_time`
  parametresi var ve Studio onu vermiyordu). Kaynak istenen 60 FPS yerine
  ~350 FPS üretip 120 karelik yazıcı kuyruğunu taşırıyor, 45–96 kare kaybına
  yol açıyordu. Take doğru biçimde `partial` kalıyordu — sistem doğru
  davranıyordu, ölçüm ortamı yanlıştı. `real_time=True` ile kayıp **sıfır**.
  Ders: GUI'nin kayıt hattına etkisi ancak **A/B** ile söylenebilir; tek
  ölçümle "GUI kayıp yaratıyor" denemez.
- **`psutil` 7.1.3 ortamda mevcut** ve iş duraklatma onu kullanıyor (Windows'ta
  `SIGSTOP` yok). Bağımlılık olarak eklenmedi; yoksa arayüz duraklatmanın
  desteklenmediğini söyleyip iptali öneriyor.
- **Ayarlarda `backend` düz metin saklanırsa** tercih dosyası yazılırken
  `'str' object has no attribute 'value'` ile sessizce başarısız oluyor. Tip
  dönüşümü zorunlu.

### Ölçülen bütçeler

| Ölçüm                                              | Sonuç                       | Bütçe         |
| -------------------------------------------------- | --------------------------- | ------------- |
| Soğuk açılış (gerçek süreç)                        | 1,29–1,34 s                 | ≤3 s ✓        |
| GUI kare süresi, canlı kayıt sırasında             | medyan 0,09 ms · p95 3,7 ms | ≤8 ms ✓       |
| GUI kare süresi, offline işleme sürerken           | medyan 2,88 ms · p95 7,7 ms | ≤8 ms ✓       |
| Kayıt kaybı (mock, GUI açık/kapalı, 60 ve 200 FPS) | **0**                       | kayıp yok ✓   |
| Liste doldurma, 1000 / 5000 satır                  | 43 / 48 ms                  | takılma yok ✓ |
| Kütüphane kaydırma, 500 sürüm                      | medyan 20,6 ms              | —             |
| Kaydırırken thumbnail üretimi                      | **0 çağrı**                 | üretim yok ✓  |

Zaman çizelgesi bütçesi (≤16 ms) **F8'e aittir ve henüz ölçülmemiştir.**

### Sürümler

Hiçbir veri şeması değişmedi. `studio.STUDIO_VERSION` 0.1.0; app 0.11.0,
processing 1.1.0 (F3), diğerleri 6V'deki gibi.
