---
type: legacy-memory-section
status: archived
title: "GUI: bilgi mimarisi ve viewport denetimi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1416-1438"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-06-export-modelden-bagimsiz.md) · [sonraki](6i-08-navigationrail-de-ytu-logosu.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

### GUI: bilgi mimarisi ve viewport denetimi

- **Export**: 5 sekme (Kapsam / İskelet / Özellikler / Doğrulama / Sürümler),
  her biri kendi dikey scroll'u; **Sürüm oluştur** sekmelerin dışında sabit
  eylem çubuğunda, pasifse nedeni yanında yazıyor. Release tablosu
  `ResizeToContents` yerine `Interactive` + ilk sütun `Stretch`.
- **Ayarlar**: 6 sekme (Genel / Yakalama / Sentetik / Sınıflar / Tanılama /
  Konumlar); iki bağımsız scroll kolonu kaldırıldı. **Kaydet** sekmelerin
  dışında, yanında kirli/temiz durumu. Tanılama raporu monospace ve esnek
  yükseklikte. Sınıf listeleri splitter içinde, birbirini ezmiyor.
- **Dataset**: 8 filtre ve 12 metrik kutusu `flow_row` ile sarıyor; tablolar
  `Interactive` sütunlarla; sayfa dikey scroll'a alındı.
- **Projeler**: sabit 2:3 kolon yerine splitter; plan düğmeleri sarıyor.
- **Dashboard**: yatay scrollbar kapatıldı.
- Yeni ortak yardımcılar: `make_wrapped_label` (sarar, genişlik dayatmaz),
  `Card(compact=True)`, `ElidedLabel` kullanımı yaygınlaştı.
- **Ölçülen minimumlar (1120x700, dark/light):** dashboard 290x133,
  projects 861x245, participants 586x342, capture 1101x593, review 938x598,
  dataset 517x133, export 550x523, settings 551x447. Hepsi 1120'nin altında;
  `pages with problems: 0`.
- **Minimum pencere boyutu büyütülmedi**; kök neden layout/size-policy
  üzerinden çözüldü.
