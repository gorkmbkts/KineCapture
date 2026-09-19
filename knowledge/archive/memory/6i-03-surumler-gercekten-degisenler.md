---
type: legacy-memory-section
status: archived
title: "Sürümler (gerçekten değişenler)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1336-1347"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-02-legacy-annotation-politikasi.md) · [sonraki](6i-04-kalici-proje-silme-yalniz-sistem-sahibi.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Sürümler (gerçekten değişenler)

- `APP_VERSION` / paket: **0.8.0 → 0.9.0**
- `ANNOTATION_SCHEMA_VERSION`: **2.0.0 → 2.1.0** — `reviewed_at` ve
  `correctness_source` eklendi, `correctness`'in otoritesi değişti. Minor:
  2.0 reader 2.1 dosyada bildiği alanda geçerli bir ikili değer bulur; 2.1
  reader 2.0 dosyada kararı verbatim korur ve çelişkiyi gösterir.
- `RELEASE_SCHEMA_VERSION`: **2.0.0 → 2.1.0** — manifest `correctness_source`
  ve `reviewed_at` taşıyor. Toplamsal; hiçbir 2.0 alanı anlam değiştirmedi.
- **Değişmeyenler:** project 1.1.0, session 2.0.0, take 1.1.0, skeleton stream
  1.1.0, label 2.0.0, feature spec 1.0.0, raw archive 1.0.0, identity SQLite 1.
