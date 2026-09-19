---
type: legacy-memory-section
status: archived
title: "Eklem eşleştirmesi altında davranış"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "493-505"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-03-feature-registry-mimarisi.md) · [sonraki](6c-05-export-sozlesmesi-eklemeleri.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Eklem eşleştirmesi altında davranış

Her özellik `mapping_support` beyan eder:
- `recompute` — geometrik olanlar hedef iskeletin koordinatlarından yeniden
  hesaplanır (test: aynı hareketin diz açısı native ve mapped exportta birebir
  aynı çıkıyor).
- `index_remap` — 2B noktalar, eklem kovaryansları, güven değerleri.
- `native_only` — local quaternionlar ve parent'a göre konumlar. Eşleştirme
  seçiliyken **yazılmaz** (dizi NaN, availability "absent", neden manifestte);
  GUI bunu seçimden önce gri satır ve gerekçeyle gösterir.
- Kısmi eşleştirmede yalnız ilgili kemik/sütun NaN kalır (test: 23/26
  eşleşmede yalnız `Head_end`, `*ToeBase_end` bağlantılı kemikler geçersiz).
