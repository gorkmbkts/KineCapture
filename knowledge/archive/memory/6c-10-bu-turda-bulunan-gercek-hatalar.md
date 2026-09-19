---
type: legacy-memory-section
status: archived
title: "Bu turda bulunan gerçek hatalar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "585-599"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-09-degerlendirilip-eklenmeyenler-gerekceleriyle.md) · [sonraki](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Bu turda bulunan gerçek hatalar

1. **Fingerprint dizi içeriğine duyarsızdı** (yukarıda).
2. **`root_orientation` diske yazılmıyordu**; model alanı vardı, serileştirme
   yoktu.
3. **Export ekranı ilk açılışta `joint_confidences`'ı düşürüyordu**: kayıtlı
   tercih yokken seçim boş kalıyor, `store_confidences` False oluyordu.
   Tercih yoksa `DEFAULT_FEATURE_IDS` ile açılıyor.
4. **`_build_into` içinde `name` gölgelendi**: opsiyonel alan sayacının döngü
   değişkeni sürüm adının üzerine yazıyordu (self-test sürüm adını
   `tracker_root_velocity_xyz` diye bastı).
5. **Türev maskesinin rankı belirsizdi**: `[T,3]` bir dizi "üç skaler seri" mi
   "bir 3-vektör serisi" mi olduğu tahmin ediliyordu. `vector` parametresi
   zorunlu hale getirildi.
