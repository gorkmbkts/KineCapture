---
type: legacy-memory-section
status: archived
title: "Bilinçli olarak sonraya bırakılanlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "776-789"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-07-bu-turda-bulunan-gercek-hatalar.md) · [sonraki](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) →

Güncel karşılığı: [Açık sorular](../../open-questions.md).

### Bilinçli olarak sonraya bırakılanlar

- SVO2 özel veri kanalı (`ingest_data_into_svo`) ile subject association'ı
  SVO'nun içine yazmak. Mümkün görünüyor fakat ikinci bir doğruluk kaynağı
  yaratır; şimdilik indeks + sidecar tek kaynak.
- Görünüm tabanlı re-identification (kıyafet crop deskriptörü). Gizlilik
  sınırını genişletir; eş-görünürlük + oran kanıtı gerçek testte yeterli oldu.
- Çok kişili eşzamanlı kayıt (birden fazla subject lock).
- `other_activity` için kullanıcı tanımlı alt türler (ontoloji kararı).
- Hata aralığı başına etkilenen eklem / şiddet rubriği / annotator confidence
  ve zamansal faz aralıkları — hâlâ ayrı bir uzman ontoloji kararı gerektiriyor;
  mimari eklenmelerini engellemiyor.
- Sürekli örnekten pencere üretimi ve dengeleme: eğitim katmanının işi.
