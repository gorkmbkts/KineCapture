---
type: legacy-memory-section
status: archived
title: "Diğer doğrulanan sözleşme açıkları"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2250-2279"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · ← [önceki](6t-03-gercek-offline-deneyler-ve-yeni-frame-map-bulgusu.md) · [sonraki](6t-05-calistirilan-testler-ve-sinirlar.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md), [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Diğer doğrulanan sözleşme açıkları

- `start_native_recording` H264 hardcode'u ve manifestte tercih codec'inin
  yazılması sürüyor. Playback `get_recording_parameters()` H265 döndürdü ama
  bu yeni RecordingParameters varsayılanıyla aynı; eski SVO codec'i olarak
  doğrulanmadı. Requested/applied/readback bilinmiyor ayrımı önerildi.
- Backend frame_index başarılı grab başına yerel sayaç; manifestteki “kameranın
  kendi sayacı” açıklaması yanlış. missing_frame_indices=0 sensör kapsamını
  kanıtlamaz. Backend cumulative drop sayısı take içi delta sayılamaz.
- stop_recording native stop → sentinel → writer join sırasındayken acquisition
  `_writer` var oldukça enqueue edebiliyor; zaman aşımı sonrası finalize riski
  var. Gerçek eski indeks farkının nedeni olduğu yalnız hipotezdir.
- finalize, take.json'u checksums'tan önce yazıyor; dosya bazında atomicity bütün
  kapanış işlemini atomik yapmıyor. İki eski take'te raw/proxy/skeleton mevcut
  checksum'la eşleşiyor, take.json eşleşmiyor. İnceleme öncesi/sonrası dosyalar
  aynı. `_ask_verdict` sonrası mutable kalite/not kaydı muhtemel açıklama,
  geçmiş olay nedeni kanıtlanmadı. Ham checksum ve mutable metadata ayrılmalı.
- Raw-only ürün modu ve genel SVO job katmanı yok. Reader sabit skeleton/proxy
  yollarını ve skeleton kare sayısını kullanıyor; export hazır olma durumu
  offline/QC bilmez. CaptureMode guided/free anlamı korunmalı, processing ayrı
  boyut olmalı. Bilinmeyen JSON alanı eklemek model/reader'ı düzeltmez.
- SubjectLock body/keypoint bağımlı; aynı tracker ID dönüşünü güvenilir sayan
  hızlı yol yanlış kişi riski taşıyor. select_subject displayed packet yerine
  yeniden peek timestamp'i alıyor. Yeni hint gösterilen kareye bağlanmalı.
  Genel tracking_coverage seçili kişiyi ölçmez; subject_coverage paydasında
  ambiguous kareler yok. Bunlar ayrı ve bütün ilgili kareler üzerinden ölçülmeli.
- Preview timer zaten acquisition'dan ayrı; yalnız GUI FPS azaltmak her grab'deki
  full RGB/depth/body işini kaldırmaz. FramePacket RGB/depth aynı H×W ister;
  düşük çözünürlüklü preview ayrı sözleşme gerektirir.
