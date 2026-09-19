---
type: legacy-memory-section
status: archived
title: "Export sözleşmesi eklemeleri"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "506-520"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-04-eklem-eslestirmesi-altinda-davranis.md) · [sonraki](6c-06-fingerprint-duzeltmesi-gercek-hata.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Export sözleşmesi eklemeleri

- `feature_spec.json`: seçilen özellikler ve sürümleri, bütün dizi
  sözleşmeleri, açı/mesafe/kemik/çift/özet sütun adları, birimler, koordinat
  uzayları, zaman hizası, eksik veri politikası, türev politikası, algoritma
  parametreleri, rol tabloları, örnek başına availability istatistiği,
  mapping ve klinik doğrulama uyarısı.
- Manifestte `array_contract` korundu, yanına `feature_contract` eklendi.
- Örnek girdisinde `features` (full/partial/absent), `feature_availability_ratio`,
  `feature_notes`, `array_keys` ve `checksum` var.
- Seçili bir özellik **hiçbir örnekte** üretilemezse `feature_never_available`
  doğrulama hatası verilir ve sürüm "geçti" sayılmaz. Kısmi availability
  uyarıdır.
- `RELEASE_SCHEMA_VERSION` 1.0.0 → **2.0.0**. Eski sürümler değiştirilmez.
