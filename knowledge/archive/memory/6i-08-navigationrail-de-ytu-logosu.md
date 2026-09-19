---
type: legacy-memory-section
status: archived
title: "NavigationRail'de YTÜ logosu"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1439-1453"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-07-gui-bilgi-mimarisi-ve-viewport-denetimi.md) · [sonraki](6i-09-qfont-setpointsize-uyarisi-qt-kaynakli-kanitlandi.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

### NavigationRail'de YTÜ logosu

- Kaynak `files/Yıldız_Technical_University_Logo.png` **dokunulmadı**;
  bayt-bayt aynı kopya `src/kinecapture/gui/assets/` altına alındı ve
  `pyproject.toml` içinde `package-data` olarak bildirildi. `importlib.resources`
  ile okunuyor — cwd/repository yoluna bağlı değil. **Wheel içinde bulunduğu
  doğrulandı** (`kinecapture-0.9.0-py3-none-any.whl`).
- Rail açıkken Daralt düğmesinin hemen üstünde, yatayda ortalı, en-boy oranı
  ve şeffaflık korunarak `SmoothTransformation` ile ölçekleniyor
  (94x96 px; tavan 96 px, 700 px ekranda navigasyonu itmiyor).
- Daraltıldığında **tamamen gizleniyor** ve `height=0` — boşluk bırakmıyor.
  Her ölçekleme **orijinalden** yapılıyor, art arda collapse/expand görüntüyü
  bozmuyor ve yeni pixmap sızdırmıyor (8 tur test edildi).
- Logo yüklenemezse uygulama çalışmaya devam ediyor, yalnız warning düşüyor.
