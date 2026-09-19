---
type: legacy-memory-section
status: archived
title: "Ek olarak: donanımsız gövde dönüşümü testleri"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3181-3189"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · ← [önceki](9-04-ozellik-katmani-dogrulamasi-2026-08-23.md) · [sonraki](9-06-gelistirme-sirasinda-bulunup-duzeltilen-gercek-hatalar.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

### Ek olarak: donanımsız gövde dönüşümü testleri

`tests/test_zed_adapter.py` (17 test) `ZedCameraBackend._retrieve_bodies`
dönüşümünü SDK'nınkine benzer stub nesnelerle donanımsız test ediyor: güven
ölçeği 0..100→0..1, yanlış eklem sayısında **yeniden şekillendirmeden
düşürme**, tracking-state eşlemesi, eksik eklemin non-finite kalması,
orientation kontrolü ve sidecar round-trip'i. Bunlar canlı kamera
gerektirmeden regresyonu yakalar.
