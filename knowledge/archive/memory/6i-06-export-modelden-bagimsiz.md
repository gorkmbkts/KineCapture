---
type: legacy-memory-section
status: archived
title: "Export: modelden bağımsız"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1404-1415"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-05-timeline-video-editoru-tarzi-kirpma-onizlemesi.md) · [sonraki](6i-07-gui-bilgi-mimarisi-ve-viewport-denetimi.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Export: modelden bağımsız

- Export ekranındaki KineSynthV3 yönlendirmesi kaldırıldı; native/kanonik
  seçenek "önerilen" olarak sunuluyor. Yeni `canonical` preset varsayılan
  başlangıç; `kinesynth_compat` **`legacy=True`** ile korunuyor (silmek eski
  otomasyonu bozardı) ve adı "Eski: ..." ile başlıyor.
- Yeni "Çıktı sözleşmesi" kartı ne yazıldığını ve normalizasyon/sabit uzunluk/
  padding/split'in **yapılmadığını** açıkça söylüyor.
- Release doğrulaması artık *sınıflandırılmış* aralıkları sayıyor ve sınıfsız
  aralığı ayrı bir hata olarak bildiriyor; türetilmiş correctness ile aralık
  içeriği çelişemez.
