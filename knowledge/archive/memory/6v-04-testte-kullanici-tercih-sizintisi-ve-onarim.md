---
type: legacy-memory-section
status: archived
title: "Testte kullanıcı tercih sızıntısı ve onarım"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2481-2501"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6V. Capture → Verileri Hesapla → Etiketleme backend devamı (2026-09-11)](6v-6v-capture-verileri-hesapla-etiketleme-backend-devami-2026-09-11.md) · ← [önceki](6v-03-calistirilan-kontroller-ve-sinirlari.md) · [sonraki](6v-05-devam-noktasi-donanim-bekleniyor.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

### Testte kullanıcı tercih sızıntısı ve onarım

Başlangıç baseline'ı 15 kullanıcı dosyasında karşılaştırıldı. 14 dosya (ham eski
kayıtlar ve gerçek identity DB dahil) değişmemişti; `test_gui_viewports.py`
module-scope fixture'ı function-scope autouse izolasyonundan önce çalışıp gerçek
`~/.kinecapture/user_state.yaml` içine kcbtest07/viewports0 yolunu yazmıştı.
Bu çalışma sırasında yakalanan gerçek yan etkidir; gizlenmedi.

Bozuk sürüm kanıt dizinine yedeklendi. Aynı görevin önceki dosya okuma kaydından
özgün byte'lar çıkarıldı; ancak önceki SHA-256
`1df1e90ee374767b56a7e38174567e234baad218c80dd04db7c12ad647a1e2e0` ile birebir
eşleştikten sonra dosya ve baseline mtime geri yüklendi. Session-scope dış
izolasyon ve fixture başlamadan güvenli yol kontrolü eklendi. İlgili fixture
yeniden çalıştırılıp geçti. Kullanıcının zaten eski pytest-386 yolunu içeren
önceden bozulmuş dataset tercihine ayrıca ürün müdahalesi yapılmadı. Diagnostic
bu yüzden açık output yolu ister ve kullanıcının tercih dosyasını okumaz.

Son testlerden sonraki nihai kontrolde korunan 15 kullanıcı dosyasının tamamı
başlangıç SHA-256 ve mtime değerleriyle birebir eşleşti; değişen dosya 0.
Kanıt: `C:\Users\gorke\AppData\Local\Temp\kcb_8af98122\protected_data_final.json`.
