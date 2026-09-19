---
type: legacy-memory-section
status: archived
title: "Sınıf oluşturma, iptal ve hazır olma semantiği"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1115-1131"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-04-etiketleme-arayuzu-iki-katman-iki-kucuk-pencere.md) · [sonraki](6g-06-aktivite-yaziminin-emekliye-ayrilmasi.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Sınıf oluşturma, iptal ve hazır olma semantiği

- `LabelSchema.match_exercise/search_exercises/ensure_exercise` eklendi;
  `add_exercise` artık `add_error_type` ile **aynı** NFKC/casefold/boşluk
  yinelenen-ad kuralını kullanıyor. `ensure_exercise("Squat")` ve
  `ensure_exercise("  SQUAT ")` aynı `squat` seçeneğini döndürür.
- `AnnotationRepository.ensure_movement_class` / `assign_new_movement_class`
  eklendi; `ensure_error_class` ile aynı sözleşme.
- **Sınıf eklemek proje düzeyinde bir değişikliktir**: `label_schema.json`
  dosyasına anında ve atomik yazılır, etiketleme undo yığınına **girmez**, ve
  diyalog **İptal** ile kapatılsa bile tanımlı kalır. İptal yalnızca "bu
  aralığa atama"yı geri alır. Gerekçe: sınıf başka take'lerde kullanılıyor
  olabilir; bir pencerenin kapatılması onu tanımsız yapamaz.
- Yarım kalmış aralık **hazır sayılmaz**: türsüz hata aralığı hem
  `evaluate_sample()` hem ekran metninde eksik görünür; export aynı kuralı
  okur.
