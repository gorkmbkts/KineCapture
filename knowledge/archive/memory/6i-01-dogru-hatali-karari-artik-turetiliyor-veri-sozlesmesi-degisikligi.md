---
type: legacy-memory-section
status: archived
title: "Doğru/hatalı kararı artık TÜRETİLİYOR — veri sözleşmesi değişikliği"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1293-1314"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · [sonraki](6i-02-legacy-annotation-politikasi.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Doğru/hatalı kararı artık TÜRETİLİYOR — veri sözleşmesi değişikliği

**Kural:** sınıflandırılmış hata aralığı olan hareket HATALI, olmayan DOĞRU.
Kullanıcıya ayrıca sorulmaz. Son aralık silinince hareket yeniden DOĞRU olur.
Sınıfsız/geçersiz/dışarı taşan aralık hareketi doğru yapmaz — eksik bırakır.

- Tek kaynak: `MovementSample.derived_correctness`. Domain, repository,
  Dataset filtre/dağılımları, timeline bandı rengi, release manifesti ve
  continuous export **hepsi** bunu okur; hiçbiri kendi hesabını yapmaz.
- `MovementSample.correctness` alanı korunuyor fakat **türetilmiş önbellek**:
  `label_sample()` ve `apply_to_all()` artık `correctness` parametresi
  **kabul etmiyor**, `to_dict()` reviewed örneklerde türetilmiş değeri yazıyor.
  Divergence üretebilecek public API yok.
- **"Hata yok" ile "kimse bakmadı" ayrımı:** yeni `reviewed_at` alanı. Hareket
  penceresinin Kaydet'i onu damgalar (`mark_reviewed()`); damgasız hareket hata
  aralığı olmasa da `UNLABELLED` kalır. Bu, aralıkların tek başına söyleyemediği
  tek şeydir.
- `MovementLabelDialog`'dan Doğru/Hatalı düğmeleri, `KARAR` bölümü,
  `correctness` property'si, `_set_verdict` ve `1`/`2` kısayolları **kaldırıldı**
  (hem dialogdan hem ReviewPage'den). Kaydet, sınıf seçilmeden **etkin olmuyor**.
- Yeni readiness durumu: `SampleReadiness.LEGACY_CONFLICT`.
