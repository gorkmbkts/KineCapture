---
type: open-questions
status: current
updated: 2026-09-18
tags:
  - open
---

# Açık sorular ve sonraki işler

## Öncelikli

1. Kişi seçilmeden alınmış iki eski kayıt için kare-anchor seçici.
2. **Sporcu seçimi ile işlemede kilitlenen kişi arasında uyuşmazlık kapısı
   yok.** `validate_subject_review` yalnız seçilen kimliğin sürümde bulunup
   bulunmadığına bakıyor (`unknown_athlete_tracker`); kanonik export ise yalnız
   "sporcu seçilmedi" durumunu reddediyor. İşleme A kişisini kilitlemişken
   sporcu olarak B seçilirse dışa aktarılan diziler A'nın koordinatlarıdır,
   manifest ise `athlete_tracker_id = B` yazar ve hiçbir kapı itiraz etmez.
   Kilitlenen kimlik `features.json` içindeki `subject_association` alanında
   zaten yazılı olduğundan kapı uygulanabilir durumdadır. Tek kişilik kayıtta
   ortaya çıkamaz. Durum: `verified` açık (18 Eylül 2026 kod denetimi —
   `processing/subject_review.py:391-407`, `export/canonical.py:246`,
   `processing/jobs.py:534`).
3. Gerçek kayıtla kanonik export paketinin uçtan uca doğrulanması.
4. İki kişinin aynı kadrajda olduğu gerçek subject-lock testi.

## Bilinen teknik riskler

- `test_processing_pipeline.py` duraklat/sürdür yaklaşık üç koşudan birinde
  takılabiliyor.
- `test_identity.py` eşzamanlı katılımcı kodu testi tam suite yükünde Windows
  dosya kilidiyle düşebiliyor; izole koşuda geçiyor.
- Test ve ölçüm ortamı sınırları: [Test ve ölçüm ortamı](protocols/test-and-measurement.md).
- SDK ilk model optimizasyonu dakikalar sürebilir.
- Proxy video Windows uzun yolunda açılamayabilir.
- `dataset_root` eski yolu gösterebilir.
- Proje kilidi yok.
- PyOpenGL numpy 2.x ile uyumsuz; 3B yalnız Qt GL sınıflarıyla yürütülür.

Bir madde kapanınca doğrulama kaynağıyla ilgili nota taşınır ve bu liste
kısaltılır.

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [10. Bilinen sorunlar, riskler ve sınırlar](archive/memory/10-10-bilinen-sorunlar-riskler-ve-sinirlar.md)
- [11. Henüz uygulanmayanlar](archive/memory/11-11-henuz-uygulanmayanlar.md)
- [12. Sonraki önerilen adım](archive/memory/12-12-sonraki-onerilen-adim.md)

Tam liste: [Tarihsel MEMORY arşivi](archive/memory/index.md).
