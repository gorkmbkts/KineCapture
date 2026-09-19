---
type: legacy-memory-section
status: archived
title: "İnceleme ekranı — yalnızca kaydedilen kişi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1058-1075"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-01-capture-ekrani.md) · [sonraki](6g-03-bindirme-hizasi-kok-neden-ofis-ofseti-degil.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### İnceleme ekranı — yalnızca kaydedilen kişi

- `ReviewPage._redraw()` artık **tek gövde** çiziyor:
  `LoadedTake.review_body_at(position)` → kilit varsa `frame.subject_body()`,
  yoksa `None`. Başka gövde soluk bile çizilmiyor.
- **Gövde/tracker seçicisi kaldırıldı** (`_body_selector` yok).
- Kişi bulunamayan karede iskelet çizilmez, uyarı şeridinde
  `Seçilen kişi bu karede bulunamadı — iskelet çizilmiyor.` yazar, önceki
  karenin pozu **donmaz**.
- Zaman çizelgesindeki kapsam eğrisi `LoadedTake.subject_coverage_curve()`
  ile aynı gövdeden geliyor; eskiden `coverage_curve(None)` en iyi takip
  edilen gövdeyi çiziyordu ve katılımcının kaybolduğu aralıkta "tam kapsam"
  iddia ediyordu.
- **Eski (kilitsiz) kayıtlar:** `SkeletonStream.dominant_tracking_id` — kayıtta
  en çok görünen gövde. Bu bir tahmindir, öyle işaretlenir
  (`Kilit yok · tahmin ID n` + açılış bildirimi) ve `ReleaseBuilder`'ın aynı
  kayıtlara uyguladığı kuralla birebir aynıdır. Uydurma kimlik yazılmaz.
