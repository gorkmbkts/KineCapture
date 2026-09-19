---
type: legacy-memory-section
status: archived
title: "Redesign doğrulaması (2026-08-21, donanımsız)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3048-3072"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · ← [önceki](9-01-donanim-dumani-gercek-zed-2i.md) · [sonraki](9-03-ham-arsiv-kisi-kilidi-surekli-aktivite-dogrulamasi-2026-08-24.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md), [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md).

### Redesign doğrulaması (2026-08-21, donanımsız)

Yeniden tasarım sonrası gerçekten çalıştırıldı:

```text
python -m pytest                    314 passed, 92.9 s
python -m kinecapture --self-test   exit 0
  hareket/hata etiketleme   : OK (2 hareket, 1 zamansal hata aralığı)
  dataset index             : OK (1 kayıt, 2 hazır hareket, 1 hata aralığı)
  export                    : OK (dataset_v001, 2 örnek, 1 hata aralığı,
                                  doğrulama=geçti)
```

Ayrıca elle doğrulandı: v1 sidecar → v2 kayıpsız okuma (eski `segment_id`
korunuyor, `uncertain` → `unlabelled` + `legacy`, `evidence_intervals` →
gerçek `ErrorInterval`, dosya okuma sırasında **değişmiyor**), v2 round-trip
kararlı, çakışan iki sınıfın 5 ortak karesi `error_multi_hot` içinde iki sütun
olarak görünüyor, fingerprint aralık ekle/taşı/sınıf değiştir/sil işlemlerinin
dördünde de değişiyor, sayfalar 1600x980 **ve** 1366x768'de taşmadan
çiziliyor.

**Redesign donanımda test edilmedi.** Etiketleme ve export kamera
gerektirmiyor; bu turda 2026-08-20'deki gerçek ZED 2i kaydı yeniden
alınmadı. Kayıt hattı (`camera/`, `capture/`) bu turda değişmedi.
