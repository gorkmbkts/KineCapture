---
type: legacy-memory-section
status: archived
title: "Fingerprint düzeltmesi (gerçek hata)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "521-529"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-05-export-sozlesmesi-eklemeleri.md) · [sonraki](6c-07-gui.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Fingerprint düzeltmesi (gerçek hata)

Örnek sağlama toplamları `_validate()` içinde, yani fingerprint hesaplandıktan
**sonra** ekleniyordu; dolayısıyla fingerprint yazılan dizilerin içeriğine
duyarlı değildi. Artık `.npz` yazılır yazılmaz hash alınıyor, fingerprint
anahtarına giriyor ve doğrulama sırasında yeniden hesaplanıp karşılaştırılıyor.
Fingerprint bileşenleri: `samples`, `export_config`, `skeleton_spec`,
`label_schema`, **`features`**.
