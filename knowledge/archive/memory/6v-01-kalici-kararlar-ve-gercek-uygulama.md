---
type: legacy-memory-section
status: archived
title: "Kalıcı kararlar ve gerçek uygulama"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2384-2437"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6V. Capture → Verileri Hesapla → Etiketleme backend devamı (2026-09-11)](6v-6v-capture-verileri-hesapla-etiketleme-backend-devami-2026-09-11.md) · ← [önceki](6v-6v-capture-verileri-hesapla-etiketleme-backend-devami-2026-09-11.md) · [sonraki](6v-02-surumler.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md).

### Kalıcı kararlar ve gerçek uygulama

- Yeni CaptureProfile: HD720/60, H264_LOSSLESS, policy 2; final canlı body/depth,
  skeleton/proxy ve ayrı RGB/depth arşivi varsayılan kapalı. Kapalı ürünün SDK
  modülü, retrieval/kopya, writer/encoding/sıkıştırması gerçekten devreden çıkar.
  Kullanıcı dosyasını değiştirmeyen `for_new_capture` eski tercihleri bu yeni
  başlangıca taşır; tarihsel take/session `from_dict` legacy profili korur.
- ZED raw kaynak SVO2'dir. Mock, saklanan renk ve sentetik generator provenance'ı
  üzerinden replay edilir. Doğrudan legacy mock test akışı ayrıca korunur.
- Görüntüsüz FramePacket kaynak çözünürlüğünü taşır. RGB preview küçük ve
  seyrektir; tüm çözünürlükte RGB ancak seçilen ürün gerektirirse kopyalanır.
- `preview/LatestWorker` tek slot, bloklamayan offer, latest-frame-wins ile
  inference ve kullanıcı frame listener'larını acquisition thread'inden ayırır.
  `CpuPosePreview`, mevcut OpenCV DNN ile CPU'da hafif 2D kişi/pose gösterir.
  Bu çıktı metrik iskelet veya participant identity değildir. OpenCV Zoo commit
  `47534e27c9851bb1128ccc0102f1145e27f23f98`, Apache-2.0 lisans/NOTICE taşınır.
  İki ONNX model ~/.cache/kinecapture/models altında checksum doğrulamalı veri
  dosyasıdır. Yeni conda environment/paket kurulmadı veya yükseltilmedi.
- Operatör seçimi gösterilen görüntünün source timestamp/resolution, nokta ve
  bbox anchor'ıdır. Kayıt anında raw sidecar'a yazılır; capture lifecycle kilidi
  kapanış/checksum sırasında değiştirilmesini önler. Düzeltme/reprocess için
  yeni processing parametresi olarak anchor verilir, eski raw değiştirilmez.
- SDK dizileri owned/read-only snapshot; RGB-D writer mutable dış girdiyi de
  korur. Sonlu iskelet float32 değerleri JSON'da ondalık quantization olmadan
  geri gelir. Body/image timestamp ve is_new kontrolü eski sonuç kullanımını
  engeller. Malformed zorunlu SDK body alanları integrity issue üretir.
- Kayıt start/stop, grab+enqueue ile aynı sınırda; kontrol işlemi önceliklidir.
  Writer/codec işçisi bitmeden dosya kapatılmaz/finalize edilmez; timeout'ta
  kaynak sahipliği korunur. Dolu kuyruğa sentinel beklenmez. JSONL fsync hatası
  artık yutulmaz. Eksik/boş native SVO2, yazım hatası, queue/backend kaybı veya
  bildirilen bütünlük hatası başarılı take sayılmaz. Checksum final take.json
  commit'inden önce gelir; mutable curation dosyası checksum'a dahil değildir.
- Canlı frame_index **successful-grab ordinal**; fiziksel kamera sayacı veya
  SVO position değildir. Native ingested/encoded değerleri ham telemetridir,
  doğrulanmış sayım değildir. Timestamp gap/jitter, queue loss ve backend delta
  ayrı kaydedilir. `awaiting_processing` take export'a hazır sayılmaz.
- `processing/process_take`: gerçek sıralı SVO replay, svo_real_time_mode=False,
  varsayılan BODY_38/ACCURATE/NEURAL_PLUS/fitting/full precision. GUI/Qt bağımlılığı
  yok. Her deneme farklı .partial dizin; kaynak SHA/provenance + parametreler +
  calibration override SHA + SDK + job state/progress/hata tutulur. Complete
  ancak dosyalar kapanıp kapsam/QC/checksum geçtikten sonra atomik rename ile
  yayımlanır. Restart baştan replay eden yeni denemedir, tracker geçmişini
  atlayarak append etmez. Kaynak değişmişse restart reddedilir.
- Eşleme: tekil camera timestamp floor(ns/1000) eşitliği. Ne yakın komşu ne N−1
  kaydırma kabul edilir. Declared/decode sayısı ve source/capture unmatched,
  source ordinal/timestamp sürekliliği ayrıca denetlenir. Subject belirsiz/eksik
  ise maskeler/NaN korunur. Aynı tracker ID büyük konum/anatomi çelişkisini
  geçersiz kılamaz; belirsizlik onaysız otomatik kilitlenmez (association 1.1.0).
- `ReviewDataset`: checksum'lı complete processing sürümü, hazır proxy/arrays/
  skeleton/features. Yeni annotation sidecar source fingerprint + source
  position + camera timestamp inclusive sınırlarına bağlıdır. Eski segments.json
  anlamı otomatik değiştirilmez; production GUI yeni mimariye göre yeniden
  geliştirilmedi. `tools/capture_diagnostic.py` bağımsız görünür test viewer'ıdır.
