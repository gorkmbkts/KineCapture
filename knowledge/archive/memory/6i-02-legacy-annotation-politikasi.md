---
type: legacy-memory-section
status: archived
title: "Legacy annotation politikası"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1315-1335"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-01-dogru-hatali-karari-artik-turetiliyor-veri-sozlesmesi-degisikligi.md) · [sonraki](6i-03-surumler-gercekten-degisenler.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Legacy annotation politikası

`is_review_complete` = `reviewed_at` var **veya** dosyadaki karar türetilmiş
değerle **aynı**. Böylece insan kararı ile kanıt uyuşuyorsa otomatik ve kayıpsız
geçiş olur; uyuşmuyorsa çelişki görünür kalır.

| Eski dosyadaki durum | Sonuç |
|---|---|
| CORRECT + aralık yok | READY (kanıt ve karar aynı) |
| INCORRECT + sınıflı aralık var | READY |
| **INCORRECT + sınıflı aralık yok** | **LEGACY_CONFLICT**, export dışı |
| **CORRECT + sınıflı aralık var** | **LEGACY_CONFLICT**, export dışı |
| UNLABELLED + exercise var | UNLABELLED (sınıf yalnız başına karar değil) |

- **Dosyayı açmak onu yeniden yazmaz.** Çözülmemiş legacy örnek kaydedilse bile
  eski kararı **verbatim** korur (`to_dict()` yalnız `reviewed_at` varsa
  türetilmiş değeri yazar). Sessiz veri kaybı yok.
- Çözüm iki deterministik yoldan biriyle: hareket penceresini yeniden kaydetmek
  (yeni kuralı bilinçli kabul), veya eksik hata aralığını ekleyip
  sınıflandırmak. İkisi de idempotent ve testli.
