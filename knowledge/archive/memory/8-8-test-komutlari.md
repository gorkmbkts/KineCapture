---
type: legacy-memory-section
status: superseded
superseded_by: knowledge/protocols/test-and-measurement.md
superseded_on: 2026-09-18
title: "8. Test komutları"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2964-2977"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](7-7-mimari-sinirlar.md) · [sonraki](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

> **Superseded (2026-09-18).** Komut listesi hâlâ doğrudur, fakat aşağıdaki iki
> ifade sonraki ölçümlerle geçersiz kaldı: tek süreçte `pytest` koşusu
> bitmiyor (dosya dosya koşulur) ve `offscreen` platformunda font ailesi
> olmadığı için yerleşim ölçümleri geçersizdir. Güncel kural:
> [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).
> Tarihsel kayıt olduğu gibi bırakılmıştır.

## 8. Test komutları

```powershell
.\scripts\run_tests.ps1
.\scripts\run_tests.ps1 -Filter export
conda run -n KineSynth python -m pytest
conda run -n KineSynth python -m kinecapture --self-test
conda run -n KineSynth python -m kinecapture --diagnose
conda run -n KineSynth python -m kinecapture --list-devices
conda run -n KineSynth python -m kinecapture.tools.verify_zed_topology
```

GUI testleri `QT_QPA_PLATFORM=offscreen` ile çalışır (betik bunu ayarlar).
