---
type: legacy-memory-section
status: archived
title: "Değerlendirilip EKLENMEYENLER (gerekçeleriyle)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "564-584"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-08-kendi-arastirmamla-eklediklerim-promptta-yoktu.md) · [sonraki](6c-10-bu-turda-bulunan-gercek-hatalar.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Değerlendirilip EKLENMEYENLER (gerekçeleriyle)

1. **Kovaryanstan türetilen std / belirsizlik elipsoidi.** Altı elemanın sırası
   yerel SDK'dan doğrulanamadı; yanlış sıra sessizce yanlış belirsizlik üretir.
   Ham altı değer saklanıyor, yorum yapılmıyor.
2. **Zemin yüksekliği, ayak teması, adım uzunluğu.** Doğrulanmış world/floor
   kalibrasyonu yok; kamera koordinatındaki `y=0` zemin değildir.
3. **Center of mass, eklem torku, ters dinamik.** Antropometrik model ve
   kuvvet ölçümü gerektirir; uydurma olurdu.
4. **Frekans alanı özellikleri (FFT, spektral güç).** Örnekleme düzensiz ve
   sekanslar kısa; anlamlı bir pencere seçimi ürün kararı gerektirir.
5. **Smoothing / Savitzky-Golay türevleri.** Sessiz yumuşatma yapılmaması
   kuralına aykırı; ileride ayrı ve sürümlü bir özellik olarak eklenebilir.
6. **DTW-to-correct-template, sınıf ortalamasına uzaklık, dataset scaler.**
   Split leakage. Eğitim katmanına ait.
7. **Mask / RGB crop / segmentasyon.** Prompt kapsam dışı bıraktı; boyut ve
   gizlilik açısından da ayrı bir karar.
8. **`bounding_box`, `head_bounding_box`, `dimensions`, `unique_object_id`.**
   SDK'da var fakat iskelet tabanlı ML için yeni bilgi taşımıyor; koordinatlardan
   yaklaşık üretilebilir.
