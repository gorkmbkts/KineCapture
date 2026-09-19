---
type: legacy-memory-section
status: archived
title: "11. Henüz uygulanmayanlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3249-3271"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](10-10-bilinen-sorunlar-riskler-ve-sinirlar.md) · [sonraki](12-12-sonraki-onerilen-adim.md) →

Güncel karşılığı: [Açık sorular](../../open-questions.md).

## 11. Henüz uygulanmayanlar

- Otomatik tekrar algılama (veri modeli `model_suggestion` kaynağıyla hazır).
- Yapay zekâ ile hata sınıflandırma / ön etiket.
- Çok uzmanlı consensus ve reviewer yorumları.
- Çok kameralı kayıt, bulut senkronizasyonu, gelişmiş yetkilendirme.
- Yüz bulanıklaştırma / skeleton-only privacy export.
- Çok kişili eşzamanlı kayıt (birden fazla subject lock).
- Görünüm tabanlı re-identification (gizlilik sınırını genişletir).
- SVO2 özel veri kanalına (`ingest_data_into_svo`) subject association yazmak.
- `other_activity` için kullanıcı tanımlı alt türler.
- Zaman çizelgesinde reviewer yorum katmanı.
- Hata sınıflarının hiyerarşisi/gruplanması (şu an düz liste).
- Bir hata aralığını başka bir harekete taşıma (şu an sil + yeniden çiz).
- Kovaryanstan türetilen belirsizlik (eleman sırası doğrulanmadı).
- Zemin/dünya kalibrasyonu ve ona bağlı özellikler (ayak teması, adım).
- Sürümlü ve açıkça işaretlenmiş smoothing/filtre özellikleri.
- Hata aralığı başına etkilenen eklem / body region, şiddet rubriği,
  annotator confidence ve zamansal faz aralıkları. Bunlar ayrı bir ontoloji
  kararı gerektirir; feature/export mimarisi ileride bu hedef dizilerinin
  eklenmesini engellemiyor (yeni FeatureDefinition + yeni array key yeter).
- Paketleme / dağıtım (installer).
