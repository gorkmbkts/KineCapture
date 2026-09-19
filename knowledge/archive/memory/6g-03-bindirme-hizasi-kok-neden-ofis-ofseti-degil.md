---
type: legacy-memory-section
status: archived
title: "Bindirme hizası — KÖK NEDEN, ofis ofseti değil"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1076-1096"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-02-inceleme-ekrani-yalnizca-kaydedilen-kisi.md) · [sonraki](6g-04-etiketleme-arayuzu-iki-katman-iki-kucuk-pencere.md) →

Güncel karşılığı: [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Bindirme hizası — KÖK NEDEN, ofis ofseti değil

- **Sebep:** `joint_positions_2d` *kameranın* görüntüsünün pikselleri;
  inceleme ekranındaki resim ise küçültülmüş proxy video. `VideoView`
  gösterilen görüntünün genişliğine bölüyordu.
- **Ölçüm (gerçek kayıt):** kamera 960x540, proxy 640x360, 2B x aralığı
  402–557 → her eklem **1.5x** fazla sağda. HD720 + `proxy_video_width=640`
  ile çarpan **2.0x**.
- **Düzeltme:** `VideoView.set_joint_space(resolution, calibration=...)`.
  İzdüşüm normalize koordinatlar üzerinden yapılıyor, çizim boyutundan
  bağımsız. `LoadedTake.joint_pixel_space` (`camera_info.resolution`) ve
  `LoadedTake.camera_calibration` (`extra.left_camera_calibration`) besliyor.
- Tahmini `_focal_ratio = 0.75` izdüşümü **silindi**. 2B yoksa doğrulanmış
  kalibrasyonla pinhole izdüşüm; o da yoksa `can_overlay()` False döner,
  bindirme çizilmez ve nedeni ekrana yazılır.
- Canlı Capture etkilenmiyordu çünkü orada tam çözünürlüklü kare gösteriliyor;
  iki uzay çakışıyor. Hata yalnız İnceleme'de görünüyordu.
- `LoadedTake.video_position_for()` artık **clamp etmiyor**, `Optional[int]`
  döndürüyor. Renkli kare yoksa `SceneView.set_frame(..., rgb_missing_reason=)`
  ile resim temizlenir ve neden yazılır; başka bir anın resmi gösterilmez.
