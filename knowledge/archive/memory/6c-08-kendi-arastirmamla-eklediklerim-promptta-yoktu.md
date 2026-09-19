---
type: legacy-memory-section
status: archived
title: "Kendi araştırmamla EKLEDİKLERİM (promptta yoktu)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "541-563"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-07-gui.md) · [sonraki](6c-09-degerlendirilip-eklenmeyenler-gerekceleriyle.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Kendi araştırmamla EKLEDİKLERİM (promptta yoktu)

1. **Sol kamera iç parametreleri take provenance'ında.** 2B eklem noktaları
   piksel; görüntü boyutu ve intrinsics olmadan yeniden kullanılamaz.
   Kayıttan sonra güvenilir biçimde geri üretilemediği için raw-capture
   alanı yapıldı. Birim piksel, uzay sol kamera görüntüsü.
2. **`body_state` ailesi** (`body_present_mask`, `body_confidence`,
   `tracking_state_code`, `action_state_code`). Takip boşluğu ile "kişi
   duruyor" ayrımı ancak böyle yapılabilir; maskesiz bir NaN neden NaN
   olduğunu söylemez. Kod tablosu spec'te.
3. **`frame_timing` / `delta_time_s`.** Gerçek örnekleme düzensizliğini
   modele göstermenin tek yolu; hedef FPS'ten üretilemez.
4. **`joint_centroid_proxy_xyz`.** COM istenirdi fakat antropometrik model
   yok; dürüst isimle ve "COM değildir" açıklamasıyla eklendi.
5. **`segment_ratios`.** Ham mesafeler kişi boyuna bağlı; kişinin kendi kalça
   genişliğine oranlamak kişiler arası karşılaştırmayı mümkün kılar ve
   dataset genelinden bir şey öğrenmez (leakage yok).
6. **`body_frame_rotation` + `body_frame_valid_mask` ayrı diziler.** Kare
   başına yönelim ile sekans düzeyi ölçek aynı isim altında karışmasın diye.
7. **`root_path_length`** ve **`bone_unit_vectors_xyz`.** İkisi de ucuz,
   yönden bağımsız ve birden çok yaklaşımda anlamlı.
8. **Yazma anında checksum → fingerprint.** Yukarıdaki hata.
