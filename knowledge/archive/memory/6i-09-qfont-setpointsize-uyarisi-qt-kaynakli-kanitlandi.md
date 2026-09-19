---
type: legacy-memory-section
status: archived
title: "QFont::setPointSize uyarısı — Qt kaynaklı, kanıtlandı"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1454-1468"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-08-navigationrail-de-ytu-logosu.md) · [sonraki](6i-10-gercekten-calistirilanlar.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

### QFont::setPointSize uyarısı — Qt kaynaklı, kanıtlandı

- Offscreen platformda **hiç görünmüyor**; `windows` platform eklentisinde
  uygulama açılışında 27 kez düşüyor: `Point size <= 0 (-1)`.
- **Minimal tekrar üretim, hiç kinecapture kodu olmadan:** px tabanlı bir
  stylesheet (`QWidget { font-size: 13px; }`) + `QToolButton` + `QMenu` →
  aynı uyarı 6 kez. `px` stylesheet fontu piksel boyutlu bırakıyor
  (`pointSize() == -1`) ve Qt'nin kendi menü ölçüm kodu bu değeri geri
  `setPointSize`'a veriyor.
- Uygulama kodu **hiçbir zaman** pozitif olmayan punto istemiyor:
  `monospace_font()` tema sabitleriyle çağrılıyor, timeline cetveli
  `max(7, ...)` ile sınırlı — ikisi de testle sabitlendi.
- Menüye açık punto vermeyi denedim: uyarı **6 → 9'a çıktı**. Yukarı akış
  davranışı; kozmetik; düzeltilmedi ve nedeni testte belgelendi.
