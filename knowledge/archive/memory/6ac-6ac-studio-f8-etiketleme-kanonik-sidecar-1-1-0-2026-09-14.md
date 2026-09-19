---
type: legacy-memory-section
status: archived
title: "6AC. Studio F8 — Etiketleme, kanonik sidecar 1.1.0 (2026-09-14)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3305-3400"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](12-12-sonraki-onerilen-adim.md) · [sonraki](6ad-6ad-studio-f9f15-3b-sporcu-disa-aktarim-cila-2026-09-14.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6AC. Studio F8 — Etiketleme, kanonik sidecar 1.1.0 (2026-09-14)

Etiketleme ekranı ve altındaki kanonik etiket katmanı. Bu fazın kuralı:
**yanlış etiket, eksik etiketten kötüdür** — eksik olan dışa aktarımı durdurur,
yanlış olan modeli sessizce zehirler. Aşağıdaki kararların çoğu bu yüzden
"reddet" yönünde.

### Kanonik şema 1.1.0 (`processing/annotations.py`)

Bir etiketin zamanı `Anchor(source_fingerprint, source_position,
camera_timestamp_ns)`. Çözüm **tam eşleşme veya ret**; en yakın kareye kaydırma
yok. Sınırlar kapsayıcı (`4..9` dokuzuncu kareyi içerir). `Correctness`
türetilir: incelenmemiş → `unreviewed`, sınıflı hata var → `incorrect`, yok →
`correct`. `Readiness` neyin eksik olduğunu söyler; **sınıfsız bir hata aralığı
bütün hareketi bloklar** (aralığı atmak, tekrarı "hatasız" diye etiketlemek
olurdu).

### Tek yazıcı (`studio/services/annotation_store.py`)

Bir kullanıcı kararı = bir geri alma adımı. Doğrulama **bütün belge** üzerinde
çalışır ve düzenleme bütün olarak reddedilir; reddedilen düzenleme geri alma
yığınından da düşer, yani hiçbir iz bırakmaz. `label_movement` sınıf +
`reviewed_at` damgasını tek adımda yazar; `label_error` sınıf + eklem + durum +
notu tek adımda yazar (ayrı yazılsa bir aralık yeni sınıfla eski eklemleri
taşıyabilirdi — tamamlanmış görünen yanlış etiket).

### GUI yazarken ortaya çıkan backend açıkları (hepsi kapatıldı)

1. **`FeatureContext.raw` işleme tarafında hiç doldurulmuyordu.** Bütün
   ham tracker alanları (2B eklemler, oryantasyonlar, kovaryanslar, kök) offline
   bir koşuda **her zaman NaN** çıkıyordu; özellik kendini "üretilemedi" diye
   raporluyordu, oysa veri paketin içindeydi. `jobs.py` artık seçili bedenlerden
   istifliyor. `tracker_joint_positions_2d` varsayılan özellik setine alındı:
   etiketleme ekranı iskeleti videonun üstüne çiziyor ve pikselleri 3B'den geri
   üretmek mümkün değil.
2. **Kaynak haritası 222 MB tutuyordu.** 216000 satır dict + tuple anahtarlı
   indeks. İki `int64` diziye indirildi; pozisyonlar kesin artansa ikili arama,
   değilse sözlüğe düşülüyor. Açılış maliyeti 222 MB → **4,8 MB**.
3. **Tekrarlanan kare kimliği sessizce çözülüyordu.** Bozuk bir kaynakta aynı
   `(pozisyon, zaman)` iki kez geçebilir; dict'te son satır kazanıyordu. Artık
   belirsizlik tespit edilip çözüm reddediliyor.
4. **Hata aralığı sessizce kırpılıyordu.** Hareketin tamamen dışına çizilen
   aralık sınır karesine sıfır uzunlukta yapıştırılıyordu — kullanıcının
   yapmadığı, göremediği bir etiket. Örtüşen kırpılır, örtüşmeyen reddedilir.
5. **`joint_status` sessizce yükseltiliyordu.** Eklem işaretlenince durum
   kendiliğinden `selected` oluyordu; bu, yapılmamış bir insan incelemesini
   kayda geçirmek demek. Çelişkili bileşim reddediliyor.
6. **Kütüphane var olmayan sürüm listeliyordu.** `process_take` önce
   `state: complete` yazıyor, sonra checksum'ları yazıp klasörü
   `.run_x.partial` → `run_x` olarak adlandırıyor. Arada okuyan herkes "hazır"
   diyen ama açılamayan bir sürüm görüyordu. Artık **"tamamlandı" = terfi
   etmiş**: `ProcessingRunSummary.is_complete` terfiyi de şart koşuyor, satır
   gerçek klasör adını taşıyor, işleme ekranı terfiye kadar "çalışıyor"
   gösteriyor.
7. **`ReviewDataset` açılışta bütün `skeleton.jsonl`'i ayrıştırıyordu.**
   Tembelleştirildi; etiketleme ekranı ona hiç dokunmuyor (dizilerden pencere
   okuyor).

### Zaman çizelgesi (`studio/views/timeline.py`)

Şeritler per-bin `fillRect` yerine numpy ile `uint8 [h,w,4]` kurulup tek
`drawImage` ile basılıyor. 600 aralıkla tam görünüm **12,13 ms** (F1 tabanı
292–323 ms). Statik katmanlar `QPixmap`'te önbellekli; oynatma çizgisi ve
sürükleme üstte çiziliyor → çizgi hareketi **0,11 ms**.

### Ölçümler (60 dk / 60 FPS / BODY_38)

Boşta kare 0,38 ms (bütçe 8) · tarama 0,64 ms (bütçe 50) · 600 karelik 3B
pencere 0,12 ms · **zirve RSS 139 MB** (bütçe 1,5 GB). Diziler memmap,
iskelet akışı hiç yüklenmiyor.

### Test ortamı tuzakları (yine)

- `pytest` geçici kökü altında take yolu yeterince uzun olunca **OpenCV proxy
  videoyu açamıyor** → koşu dürüstçe `partial` oluyor. `test_studio_processing`
  artık "tek şikâyeti proxy olan partial" durumunu bitmiş sayıyor ve nedeni
  yazıyor. Ekran görüntüsü/uçtan uca betikleri kısa bir kökte (`C:\kc8`)
  çalıştırıldı; orada koşu `complete` ve video gerçekten var.
- `test_processing_pipeline` içinde dört `assert`'te düz `Path.exists()`
  kullanılıyordu; uzun yolda sessizce `False` döndüğü için **olumsuz
  iddialar boşuna geçiyordu**. Hepsi `path_exists()`e çevrildi.
- Kişi çapası (`subject_anchors.json`) yoksa işleme hiçbir bedeni seçmez ve
  **bütün diziler NaN kalır**; ekran doğru şekilde "iskelet yok" der. Testlerin
  gerçek sayılara dokunması için çapa yazılmalı. Yakalama ekranının tıkla-seç
  akışı F10'da bağlanacak.

### Ekran

Video editörü düzeni; canlı kırpma önizlemesi (kenar sürüklenirken görüntü o
kareye gider, oynatma çizgisi yerinde kalır); 1–9 sayı tuşlarıyla sınıf atama;
"Sınıfsızların hepsine uygula" (sınıfı olanı değiştirmez); "Sonraki eksik".
Seçili hata aralığının eklemleri görüntüde kırmızı; düşük güvenli eklem içi
boş; **tracker'ın üretmediği eklem çizilmez**. Denetçi kaydırma alanında —
ekranın istediği en küçük pencere 880×923 → **880×672** (1366×768 sığıyor).
