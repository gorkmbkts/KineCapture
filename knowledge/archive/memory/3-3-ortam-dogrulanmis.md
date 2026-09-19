---
type: legacy-memory-section
status: archived
title: "3. Ortam — DOĞRULANMIŞ"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "86-125"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](2-2-mevcut-asama.md) · [sonraki](4-4-zed-sdk-ve-donanim-dogrulanmis.md) →

Güncel karşılığı: [Sistem haritası](../../architecture/system-map.md), [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

## 3. Ortam — DOĞRULANMIŞ

```text
Conda environment : KineSynth          (küçük harfli 'Kinesynth' de yol olarak çalışır)
Interpreter       : C:\Users\gorke\anaconda3\envs\KineSynth\python.exe
Python            : 3.11.14 (Anaconda, MSC v.1929, 64-bit)
Platform          : Windows 11 Pro 10.0.26200
```

`conda env list` ile doğrulandı; kanonik ad **`KineSynth`**'tir.
`sys.executable` ile interpreter kanıtlandı.

### Bağımlılıklar

Environment'ta **zaten mevcut** olan ve kullanılan sürümler:

| Paket | Sürüm |
|---|---|
| PySide6 / Addons / Essentials / shiboken6 | 6.10.1 |
| numpy | 2.4.6 |
| PyYAML | 6.0.3 |
| opencv-python | 4.12.0.88 |
| pytest | 9.0.1 |
| pyzed | 5.4 |

**Bu görevde hiçbir paket kurulmadı veya yükseltilmedi.** Yalnızca
`kinecapture` paketi editable modda kuruldu:

```powershell
conda run -n KineSynth python -m pip install -e ".[dev]" --no-deps
```

`--no-deps` bilinçliydi: bütün runtime bağımlılıkları zaten mevcuttu ve
KineSynthV3'ün çalışan sürümlerini (torch 2.5.1, numpy 2.4.6 vb.)
bozmamak gerekiyordu.

`pyproject.toml` bağımlılıkları: PySide6>=6.5, numpy>=1.24, PyYAML>=6.0,
opencv-python>=4.8. Dev extra: pytest>=7.4. `pytest-qt` **kaldırıldı** —
kurulu değildi ve GUI testleri onsuz yazıldı.
