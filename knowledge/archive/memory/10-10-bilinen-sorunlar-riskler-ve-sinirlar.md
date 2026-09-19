---
type: legacy-memory-section
status: archived
title: "10. Bilinen sorunlar, riskler ve sınırlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3228-3248"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](9-06-gelistirme-sirasinda-bulunup-duzeltilen-gercek-hatalar.md) · [sonraki](11-11-henuz-uygulanmayanlar.md) →

Güncel karşılığı: [Açık sorular](../../open-questions.md).

## 10. Bilinen sorunlar, riskler ve sınırlar

- ZED SDK'nın **ilk** model optimizasyonu dakikalar sürer. GUI uyarı veriyor
  fakat bu sırada bağlan düğmesi bloklanıyor — iptal edilebilir bir arka plan
  işine dönüştürülmesi iyi olur.
- Proxy video Windows uzun yol sınırında devre dışı kalıyor (OpenCV `\\?\`
  kabul etmiyor). İskelet verisi etkilenmiyor.
- `get_recording_status()` sayaçları bu SDK sürümünde güvenilmez; uygulama
  kendi sayaçlarını kullanıyor.
- Eş zamanlı iki uygulama örneği aynı projeyi açarsa kilitleme yok.
- Dataset index metadata dosyalarını her yenilemede tarıyor; çok büyük
  datasetlerde kalıcı bir index/cache gerekebilir.
- Üç doğrulanmış legacy test projesi runtime silme politikası nedeniyle diskte
  kaldı (kesin yollar bölüm 6E'de). Identity DB'ye otomatik kaydedilmezler;
  owner içe aktarmadıkça GUI'de görünmezler.
- Mevcut kullanıcı tercihindeki `dataset_root`, önceki donanım testinin geçici
  `shots4_iu_kvaue` klasörünü gösteriyor. Bu görev tercih dosyasını silmedi;
  owner Projeler → Veri klasörü ile kalıcı hedefi seçmelidir.
- `kinecapture.exe` script'i PATH'te değil (pip uyarısı); `python -m
  kinecapture` kullanılıyor.
