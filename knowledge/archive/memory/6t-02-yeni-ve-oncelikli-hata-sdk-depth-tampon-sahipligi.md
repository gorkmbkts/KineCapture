---
type: legacy-memory-section
status: archived
title: "Yeni ve öncelikli hata: SDK depth tampon sahipliği"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2177-2204"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · ← [önceki](6t-01-bugunku-kanit-ve-gecmis-kanit-ayrimi.md) · [sonraki](6t-03-gercek-offline-deneyler-ve-yeni-frame-map-bulgusu.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md), [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Yeni ve öncelikli hata: SDK depth tampon sahipliği

**Bugün gerçek SDK ve değiştirilmemiş RgbdArchiveWriter ile yeniden üretildi.**
`camera/zed.py:533` içindeki
`np.ascontiguousarray(self._mat_depth.get_data(), dtype=np.float32)`, SDK'nin
varsayılan `deep_copy=False` dönüşü zaten contiguous float32 olduğu için
kopya oluşturmuyor. FramePacket ve `RgbdArchiveWriter.add_frame()` de kopya
sahipliğini sağlamıyor; writer `np.asarray` ile veriyi chunk dolana kadar
tutuyor. Sonraki retrieve_measure önceki kare belleğini değiştirebiliyor.

Üç SDK depth karesi, her birinin bağımsız referans kopyası alınarak mevcut
yazıcıya chunk_frames=3 ile verildi. Arşivden geri okunan 0/1/2 karelerinin
kendi özgün verisine eşitliği `[false, false, true]`; son kareye eşitliği
`[true, true, true]`; ilk/son array ortak bellek taşıyor. Dört tam BODY
geçişindeki iki karelik probes da retained_previous_changed=true verdi.
Bu test canlı GUI üzerinden tam oturum değildir; etkilenen geçmiş kare sayısı
bilinmiyor. Fakat gerçek buffer/yazıcı kusuru doğrulanmış durumda.

Bu bulgu, eski “lossless canlı depth birebir korunuyor” genel kabulünü
geçersiz kılan önemli sınırlamadır: sıkıştırmanın kayıpsızlığı doğru anın
ölçümünün saklandığını kanıtlamaz. Önceki canlı/SVO replay depth farkının
büyüklüğü, tampon alias etkisi dışlanmadan yalnız SDK farkı sayılamaz. SVO
depth'i yine reconstructed_offline olarak tutulmalı; geçmiş ham depth
üzerine düzeltme yazılmamalı. Bu hata SDK'nin kendi squat skeleton geometrisi
ile ayrı bir sorundur. Onay sonrası en küçük öneri: SDK sınırında owned
snapshot, yeniden kullanılan tamponla regresyon, RAM/kopyalama ölçümü.
**Bu turda düzeltme uygulanmadı.**
