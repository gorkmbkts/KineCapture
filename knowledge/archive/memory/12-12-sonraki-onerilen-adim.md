---
type: legacy-memory-section
status: archived
title: "12. Sonraki önerilen adım"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3272-3304"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](11-11-henuz-uygulanmayanlar.md) · [sonraki](6ac-6ac-studio-f8-etiketleme-kanonik-sidecar-1-1-0-2026-09-14.md) →

Güncel karşılığı: [Açık sorular](../../open-questions.md).

## 12. Sonraki önerilen adım

1. **Daha uzun ve kontrollü çekim yapın** (2–3 dakika, tam görüş alanında).
   4 saniyelik dumanda `tracking_coverage` 0.45 çıktı; kişinin çerçeveye
   girip çıkmasından kaynaklanıyor olabilir. Gerçek çekim mesafesi ve
   kamera yüksekliği için kapsamın ne olduğunu ölçüp bu dosyaya yazın.
2. Proje etiket şemasına gerçek egzersiz listesini ve hata ontolojisini
   girin (Ayarlar → Etiket şeması). Kod içinde uydurulmuş sınıf yok.
3. ZED ilk-açılış optimizasyonunu iptal edilebilir arka plan işine taşıyın.
4. Birkaç gerçek kaydı iki seviyeli modelle baştan sona etiketleyip
   export alın; hata sınıfı listesi ancak gerçek kullanımla oturur.
5. Otomatik tekrar algılamayı `SegmentSource.MODEL_SUGGESTION` olarak
   ekleyin; insan onayı olmadan ground truth sayılmamalı (altyapı hazır).
6. Zamansal hedefi (`error_multi_hot`) tüketen ilk eğitim betiğini yazıp
   sözleşmenin gerçekten kullanışlı olduğunu doğrulayın.
7. `Klasik ML` presetiyle bir sürüm alıp `summary_features` üzerinde bir
   Random Forest baseline'ı çalıştırın; 307 elemanın hangilerinin gerçekten
   ayırt edici olduğunu ölçün ve işe yaramayanları bir sonraki summary
   sürümünde ayıklayın.
8. Kovaryans eleman sırasını Stereolabs dokümantasyonundan veya bilinen bir
   duruşla deneysel olarak doğrulayın; doğrulanırsa `joint_position_std`
   türetilmiş özelliği eklenebilir.
9. **Disk planlaması yapın.** Kayıpsız derinlik 3.5 GB/dakika. 20 dakikalık bir
   oturum ~70 GB. Uzun protokoller için ya ayrı bir disk ya da nicemlenmiş
   derinlik profili gerekiyor; ikisi de bilinçli bir karar olmalı, kayıt
   sırasında sürpriz olmamalı.
10. **Otomatik yeniden ilişkilendirmeyi gerçek donanımda tetikleyin**: seçili
   kişi kadrajdan tamamen çıkıp geri girsin, kadrajda başka biri varken de
   deneyin. Şu ana kadar yalnız stub testleriyle doğrulandı.
11. Birkaç gerçek oturumu AKTİVİTE modunda baştan sona etiketleyip sürekli
   dataset alın; sınıf dengesi ve `unlabelled` oranı ancak gerçek kullanımla
   görülür.
