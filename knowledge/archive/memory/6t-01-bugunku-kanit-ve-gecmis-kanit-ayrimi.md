---
type: legacy-memory-section
status: archived
title: "Bugünkü kanıt ve geçmiş kanıt ayrımı"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2157-2176"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · ← [önceki](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · [sonraki](6t-02-yeni-ve-oncelikli-hata-sdk-depth-tampon-sahipligi.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md), [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Bugünkü kanıt ve geçmiş kanıt ayrımı

- Eski kötü squat SVO'ları kullanıcı tarafından silinmiş; bulunmayan
  `pytest-386` dataset kökü, stale kullanıcı tercihi ve iki identity proje
  kaydı aynı durumda. Bunlar düzeltilmedi/DB'den silinmedi; kalıcı projeler
  içe aktarılmadı. Kullanıcı profilinin erişilebilir bölümünde yalnız iki
  Ağustos SVO bulundu. `rg` taraması ilgisiz bir Windows CloudStore alt yolunda
  hata verdi; bütün disklerde kesin yokluk iddiası değil.
- 2 Eylül depth kuyruğunda 15 kayıp/PARTIAL/610 kare yaklaşık 14.2 FPS ve
  3 Eylül 1078 kare/45.9 s/23.4 FPS olayları logdan bugün doğrulandı. 3 Eylül
  ayrı testtir, kontrollü 15→23.4 FPS iyileşmesi sayılmaz.
- Önceki squat BODY_34/38 açıları, reprojection medyan 0.00/p95 0.01 px ve
  yanlış diz confidence yaklaşık 0.971 **önceki ölçüm** olarak kaldı. Bugün
  ham kaynakla tekrar hesaplanmadı. Yerel tanı PNG'leri görsel kanıt olarak
  incelendi; hiçbir sporcu görüntüsü dış servise yüklenmedi.
- BODY_38 güçlü aday; eğitimde squat olmadığı bilinmiyor. En güçlü açıklama
  önden görünüm/örtüşme ile SDK poz tahmini/fitting davranışı. Tek sporcu ve
  iki geçmiş klip genelleme kanıtı değil. Offline aynı modelin semantik
  hatasını kendiliğinden çözmez.
