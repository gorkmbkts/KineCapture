---
type: legacy-memory-section
status: archived
title: "Donanımda doğrulanamayanlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1491-1504"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-10-gercekten-calistirilanlar.md) · [sonraki](6j-6j-etkilenen-eklem-kaniti-ve-gui-iyilestirmeleri-promptu-2026-08-31.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md), [Açık sorular](../../open-questions.md).

### Donanımda doğrulanamayanlar

- **Bu turda ZED 2i ile canlı kayıt alınmadı.** Capture ekranı düzeni bu görevde
  değişmedi; mock backend ve önceki turların gerçek kayıt dosyaları kullanıldı.
- **Gerçek büyük proje silinmedi.** Silme yalnız `tmp_path` altında oluşturulan
  tek kullanımlık fixture'larda çalıştırıldı. Onlarca GB'lık gerçek bir ham
  arşivde silme süresi, açık handle davranışı ve gerçek disk kazancı
  ölçülmedi.
- **Paketlenmiş installer denenmedi.** Logo bir wheel içinde doğrulandı;
  PyInstaller/MSI gibi bir dağıtım biçimi üretilmedi.
- `test_participant_codes_are_unique_under_concurrent_allocation` tam suite
  yükünde ara sıra Windows `.lock` dosyası yarışından düşüyor; tek başına
  üst üste geçiyor. Bu görevden önce de vardı, bu görevde değişmedi.
