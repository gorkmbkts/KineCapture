---
type: legacy-memory-section
status: archived
title: "Gerçekten çalıştırılanlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1469-1490"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-09-qfont-setpointsize-uyarisi-qt-kaynakli-kanitlandi.md) · [sonraki](6i-11-donanimda-dogrulanamayanlar.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

### Gerçekten çalıştırılanlar

| Komut | Sonuç |
|---|---|
| `python -m pytest tests/` | **732 passed**, 241.70 s |
| `.\scripts\run_tests.ps1 -Quiet` | "Testler gecti." (KineSynth, Python 3.11.14) |
| `python -m kinecapture --self-test` | uçtan uca OK, export doğrulama geçti |
| `pip wheel . --no-deps` | `kinecapture-0.9.0-py3-none-any.whl`, logo içinde |
| GUI denetimi (8 sayfa × 3 boyut × 2 tema) | `pages with problems: 0` |
| Gerçek `windows` platform akış testi | hepsi OK (aşağıda) |

Yeni test dosyaları: `test_project_deletion.py` (19), `test_project_deletion_gui.py`
(9), `test_timeline_preview.py` (16), `test_nav_logo.py` (13),
`test_gui_viewports.py` (79). `test_annotations.py` türetilmiş karar ve legacy
migration testleriyle 56'ya çıktı.

`windows` platform eklentisiyle (offscreen değil) doğrulananlar: hareket
penceresinde verdict düğmesi yok ve Kaydet sınıfsız pasif; türetilmiş karar
`correct` + ready; trim preview sonrası playhead 28→28; silme dialogu boş/yanlış
metinde pasif, doğru metinde etkin, tam yol gösteriliyor; logo 94x96 açık,
collapsed height 0, geri geliyor; export/settings/dataset/capture çiziliyor.
