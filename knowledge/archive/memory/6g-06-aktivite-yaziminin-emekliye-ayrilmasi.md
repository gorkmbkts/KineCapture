---
type: legacy-memory-section
status: archived
title: "Aktivite yazımının emekliye ayrılması"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1132-1152"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-05-sinif-olusturma-iptal-ve-hazir-olma-semantigi.md) · [sonraki](6g-07-yerlesim-1120x700-1366x768-1600x980-iki-tema.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Aktivite yazımının emekliye ayrılması

- `TimelineMode.ACTIVITY`, aktivite şeridi, aktivite kartı, F3 kısayolu,
  bütün aktivite CRUD handler'ları ve `TimelineWidget`'ın aktivite sinyalleri
  **kaldırıldı**. Gizli üçüncü şeride dönüştürülmedi: `list(TimelineMode)`
  artık tam olarak `[MOVEMENT, ERROR]`.
- **Veri korunuyor.** `domain/activity.py`, `AnnotationRepository`'nin aktivite
  okuma/yazma yolu ve `export/continuous.py` yerinde. Mevcut
  `activity_intervals` silinmiyor, dönüştürülmüyor, okuma sırasında migration
  yapılmıyor.
- `ProjectWorkspace.save_samples()` artık **tanımadığı üst düzey blokları**
  aynen koruyor (`_ANNOTATION_KNOWN_KEYS` dışındaki her şey). Böylece emekli
  bir özellik ya da daha yeni bir sürümün yazdığı blok, sonraki ilk kayıtla
  sessizce kaybolmuyor.
- **Export ekranı kararı:** `Sürekli aktivite` seçeneği silinmedi, *koşullu*
  hale getirildi. `_refresh_continuous_availability()` projede aktivite
  etiketi taşıyan kayıt sayar; sıfırsa seçenek pasifleşir ve nedeni yazar.
  Gerekçe: eski etiketli kayıtlardan hâlâ geçerli bir sürekli release
  üretilebilir, fakat aktivite etiketi olmayan bir projede seçenek yalnızca
  tamamı etiketsiz bir dataset üretebilirdi.
