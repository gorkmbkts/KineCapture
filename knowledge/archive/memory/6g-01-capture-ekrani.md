---
type: legacy-memory-section
status: archived
title: "Capture ekranı"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1038-1057"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · [sonraki](6g-02-inceleme-ekrani-yalnizca-kaydedilen-kisi.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Capture ekranı

- Kalıcı sağ sütun kaldırıldı. **Ön kontrol, Kayıt Planı, Kayıt bilgisi,
  Kaydedilecek kişi ve Ham RGB-D arşivi** kartları aynen korundu, fakat artık
  tek örnekli, modeless `InfoWindow` içinde (`gui/widgets/info_window.py`).
  `Kayıt bilgileri` düğmesi ve `F4` açar/kapatır; pencere açıkken kayıt ve
  önizleme sürer.
- İki canlı görünüm (RGB/derinlik + 3B iskelet) splitter'ı ekranın tamamını
  kullanıyor (`setSizes([760, 640])`, eşit stretch).
- **Kritik uyarı şeridi ana ekranda kaldı**: `_build_alerts` + `_refresh_alerts`.
  Öncelik sırası — bağlantı yok → kamera hatası → kayıt kaybı → disk
  yetersizliği → kişi belirsiz → kişi geçici kayıp → kişi seçilmedi.
  `Kimliği yeniden doğrula` ve `Seçimi kaldır` düğmeleri bu şeridin içinde,
  yani sorunun yanında.
- Kişi durumu chip'i canlı RGB kartının başlığında; sayısal ayrıntılar
  (`Mantıksal kimlik`, `Eşlenen tracker ID`, kayıp süresi, yeniden eşleştirme,
  belirsiz kare) info penceresinde.
- `_disk_shortfall` alanı `_refresh_archive_card` tarafından doldurulur ve
  uyarı şeridini besler.
