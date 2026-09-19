---
type: legacy-memory-section
status: archived
title: "6P. Squat bacak takibi ve ertelenmiş iskelet işleme tanısı (2026-09-02)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1872-2004"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6o-6o-ingilizce-staj-raporu-615-is-gunleri-2026-09-02.md) · [sonraki](6q-6q-ingilizce-staj-defteri-gun-1625-2026-09-06.md) →

Güncel karşılığı: [RGB-D ve depth](../../concepts/rgbd-and-depth.md), [Kişi seçimi ve subject lock](../../concepts/subject-selection.md).

## 6P. Squat bacak takibi ve ertelenmiş iskelet işleme tanısı (2026-09-02)

Bu tur bir uygulama geliştirme turu değildir. Kullanıcının squat sırasında bir
veya iki bacağın dizden bükülmeyip gövdeyle birlikte düz aşağı indiği gözlemi
gerçek kayıtlar, kaynak kod ve ZED SVO2 yeniden oynatması üzerinde salt-okunur
incelendi. Uygulama kaynak kodu ve kullanıcı kaydı değiştirilmedi.

### Kök neden hakkında doğrulananlar

- `ZedCameraBackend._retrieve_bodies()` SDK'nın `body.keypoint`,
  `keypoint_2d` ve güven dizilerini eklem sırasını/geometrisini değiştirmeden
  `BodyPose` içine geçiriyor. Uygulama tarafında dizleri düzelten, yeniden
  eşleyen, yumuşatan veya önceki kareyle dolduran gizli bir dönüşüm yok.
- `take_20260902T075335_36a0` kaydının proxy görüntüsünde dip squatta iki diz
  de bükülmüşken BODY_34 çıktısı sporcunun sol kalça-diz-ayak bileğini neredeyse
  aynı düşey çizgiye koydu. Hata yalnız 3B derinlik üretiminde oluşmadı: SDK'nın
  kendi 2B keypoint'i de bu bacağı düz kabul etti. Sol diz güveni hatalı karede
  yaklaşık `0.971` idi; dolayısıyla yalnız güven eşiği yükseltmek bu örneği
  elemez.
- Aynı kayıtta kaydedilen 3B noktaların kamera intrinsics'iyle yeniden
  izdüşümü ile SDK 2B noktaları arasındaki medyan fark `0.00 px`, p95
  `0.01 px` çıktı. RGB/iskelet uzayı veya uygulama çizimi kayması kök neden
  değildir; yanlış poz SDK çıktısının kendi içinde tutarlıdır.
- ZED eğitim dataseti kamuya açık olmadığı için “model squat görselleriyle
  eğitilmedi” iddiası doğrulanamaz. Gözlenen hata bu olasılıkla uyumludur,
  fakat daha somut açıklama BODY_34 pose hattının önden squat geometrisinde
  yanlış bir kinematik çözüme kilitlenmesidir. Önden görünümde diz fleksiyonu
  büyük ölçüde kamera derinlik ekseninde olur; 2B kalça-diz-ayak bileği neredeyse
  üst üste gelebilir. Body fitting'in geçmiş ve insan kinematik kısıtlarıyla
  eksik eklemleri tamamlaması yanlış düz-bacak çözümünü sürdürebilir.
- SDK 5.4.1 varsayılanları yerel `KineSynth` ortamında okundu:
  `skeleton_smoothing=0.0`, `minimum_keypoints_threshold=0`,
  `allow_reduced_precision_inference=False`, `prediction_timeout_s=0.2`.
  Yani hata fazla smoothing veya reduced precision kullanımından gelmiyor.

### Aynı SVO2 üzerinde offline karşılaştırma

Kaynak SVO2 dosyalarına dokunmadan `svo_real_time_mode=False`,
`HUMAN_BODY_ACCURATE`, `NEURAL_PLUS`, body fitting açık olacak şekilde bütün
kareler sırayla yeniden işlendi.

- `take_20260902T075335_36a0`, BODY_34: 176 kare grab, 174 gövdeli kare,
  11.60 s (`15.17 işleme FPS`). Dört dip squat grubunun üçünde sol diz
  `178.8-179.0 derece` ile düz kaldı; yalnız bir tekrar doğru büküldü. Bu,
  offline işlemenin kare kaybını çözse bile aynı BODY_34 model hatasını tek
  başına çözmediğini kanıtlıyor.
- Aynı SVO2, BODY_38: 176 grab ve 176 gövdeli kare, 13.38 s (`13.16 işleme
  FPS`). Dört tekrarın tamamında iki diz de dipte yaklaşık `45-61 derece`
  aralığında büküldü.
- Bağımsız ikinci sorunlu `take_20260902T075046_63e2` kaydında BODY_34 dip
  medyanı sağ diz için `178.4 derece` idi. BODY_38 offline çıktısında dip
  medyanları sol `59.6`, sağ `57.2 derece` oldu (198/198 gövdeli kare).

Bu iki kayıt BODY_38'i squat için güçlü bir çözüm adayı yapıyor; yine de nihai
ürün kararı daha fazla kişi, kıyafet, mesafe ve kamera açısıyla kontrollü A/B
doğrulama sonrasında alınmalıdır. BODY_38 aynı donanımda BODY_34'ten daha yavaş
çalıştığı için canlı modda performans sorununu büyütebilir; offline modla iyi
eşleşmesinin nedeni budur.

### Canlı performans tanısı

- Kullanıcı ayarı HD1080, istek 25 FPS, NEURAL_PLUS,
  HUMAN_BODY_ACCURATE, BODY_34 ve body fitting açık. Kamera bu desteklenmeyen
  kombinasyonda gerçekte `30.0 FPS` raporladı; take profile 25'i saklarken
  `CameraInfo` 30'u saklıyor. GUI 1-120 arası her sayıya izin verdiği için
  çözünürlüğe bağlı desteklenen ZED FPS değerleri doğrulanmıyor.
- İncelenen HD1080 take'lerde ölçülen acquisition `14.17-15.67 FPS`, maksimum
  kare boşluğu `133-334 ms` idi. En son kayıtta 610 kare / 42.99 s,
  `14.17 FPS`; 15 derinlik karesi arşivlenemediği için take `PARTIAL` kaldı.
- Donanım: RTX 2060 6 GB, i7-10750H (6C/12T), 16 GB RAM. Canlı her grab'da
  sırasıyla renk, NEURAL_PLUS derinlik ve Accurate body tracking çalışıyor;
  writer ayrıca kayıpsız float32 derinliği sıkıştırıyor. HD1080/30 kaynak bu
  makinede yaklaşık yarı hızda tüketilebiliyor.
- `backend_dropped_frames` SDK'nın bağlantı boyunca kümülatif sayacının take
  içindeki maksimumudur; take başlangıcındaki değeri çıkarmadığı için kesin
  take-başına kayıp değildir. Mevcut değerler kayıp olduğunu gösterir fakat
  doğrudan toplanmamalıdır.

### Ertelenmiş işleme uygulanabilirliği ve mimari kapsamı

Resmî ZED sözleşmesinde SVO açıldığında depth/body tracking dahil modüller canlı
kamera gibi kullanılabilir. Dolayısıyla yalnız stereo SVO2 + hafif RGB önizleme
kaydedip iskeleti sonra, her kareyi sırayla ve gerekirse BODY_38/daha ağır bir
modelle üretmek teknik olarak uygulanabilir ve bu donanım için anlamlıdır.

Ancak mevcut kodda SVO input backend'i veya post-processing job katmanı yoktur.
Ürünleştirme için en az şunlar gerekir: canlı-iskelet ile raw-only modunu ayrı
provenance olarak saklamak; `awaiting_processing/processing/processed/failed`
durumları; ilerleme/iptal/yeniden deneme; SVO checksum + SDK/model/parametre
manifesti; staging'e yazıp atomik yayınlanan sürümlü `derived` çıktısı; offline
kişi seçimi/subject association; annotation'ın bağlı olduğu iskelet sürümünü
değiştirmeme veya yeniden işlemeyi annotation sonrası engelleme; crash recovery
ve GUI/test kapsamı. Bu nedenle proof-of-concept orta, güvenli ürün entegrasyonu
orta-yüksek zorluktadır.

Raw-only modda canlı derinlik hiç üretilmediği için “kayıt anındaki ölçülmüş
derinliği koruma” şartı uygulanmaz; SVO'dan sonra hesaplanan derinlik açıkça
`reconstructed_offline` provenance taşımalıdır. Ham SVO değişmez kalır.

### Kod/hafıza ile çelişen yan bulgular

- `ZedCameraBackend.start_native_recording()` profilin
  `native_compression` seçimini kullanmıyor ve her zaman `H264` yazıyor; buna
  rağmen manifest profil değerini beyan ediyor. Ayrıca aynı metodun docstring'i
  H264 kayıplı olmasına rağmen hâlâ “lossless-by-default” diyor. Offline kalite
  profili eklenmeden önce gerçek compression seçimi uygulanmalı ve manifest
  SDK'ya verilen gerçek değeri yazmalıdır.
- `configs/default.yaml` içindeki eski yorum SVO2'nin derinliği yeniden
  ürettiği için ikinci derinlik kopyasının gereksiz olduğunu söylüyor; gerçek
  runtime ve bu hafızadaki ölçüm bunun tersidir. Dataclass varsayılanı nedeniyle
  uygulama gerçekte `float32_lossless` arşivliyor, fakat shipped yorum/legacy
  `store_depth_frames: false` yanıltıcıdır.
- Kullanıcının güncel proje ve yedi gerçek take'i
  `C:\Users\gorke\AppData\Local\Temp\pytest-of-gorke\pytest-386\viewports0\...`
  altında. Identity DB ve `~/.kinecapture/user_state.yaml` da bu geçici yolu
  gösteriyor. Bu tur taşımadı veya yeniden yazmadı; Windows/temp temizliği veri
  kaybı yaratabileceği için yeni geliştirmeden önce kontrollü, checksum'lu bir
  kalıcı konuma taşıma/yeniden bağlama planı gereklidir.

### Bu turda gerçekten çalıştırılanlar ve sürümler

- Kaynak inceleme, yedi take metadata/quality/JSONL analizi, gerçek proxy
  karelerinin ve geçici overlay'lerin görsel incelemesi, iki SVO2 üzerinde üç
  offline ZED geçişi (BODY_34 bir kez, BODY_38 iki kez), yerel SDK varsayılan
  parametre introspection'ı ve donanım sorgusu çalıştırıldı. Geçici PNG'ler
  `%LOCALAPPDATA%\Temp\kinecapture_squat_diag_20260902` altında; dataset ve
  repository kaynakları değildir.
- Pytest, self-test, wheel veya canlı kamera testi çalıştırılmadı. Yeni bir
  canlı BODY_38 take alınmadı; BODY_38 sonucu kayıtlı SVO2 replay kanıtıdır.
- Uygulama/package `0.10.0`; project `1.1.0`, session `2.0.0`, take/skeleton
  stream `1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature/raw
  archive `1.0.0`, identity SQLite `1`. Hiçbiri değiştirilmedi.
