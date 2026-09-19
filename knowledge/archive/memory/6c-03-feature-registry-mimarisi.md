---
type: legacy-memory-section
status: archived
title: "Feature registry mimarisi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "474-492"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-02-ham-kayit-zenginlestirmesi.md) · [sonraki](6c-04-eklem-eslestirmesi-altinda-davranis.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Feature registry mimarisi

```text
features/base.py         FeatureDefinition, ArrayContract, MappingSupport, SourceField
features/roles.py        anatomik rol -> eklem indeksi (5 iskelet biçimi)
features/definitions.py  sürümlü açı / mesafe / oran listeleri (sütun sırası)
features/temporal.py     dt, boşluk güvenli merkezi/ikinci fark, yol uzunluğu
features/geometry.py     üç noktalı açı, gövde çerçevesi, kemikler, gövde ölçeği
features/compute.py      özellik başına bir fonksiyon + FeatureContext
features/summary.py      sabit uzunluklu özet vektörü ve eleman adları
features/registry.py     sıralı katalog, uygulanabilirlik, presetler, boyut tahmini
features/spec.py         feature_spec.json belgesi
```

Registry bir **tuple**'dır, set değil: fingerprint ve GUI sırası Python set
sırasına bağlı olamaz. 31 özellik, 64 dizi anahtarı. Bağımlılıklar
(`depends_on`) geçişli olarak çözülür; kullanıcı özet vektörünü seçince açılar
otomatik gelir.
