---
type: concept
status: verified
updated: 2026-09-18
tags:
  - capture
  - processing
  - annotation
  - export
---

# Kayıt, işleme, etiketleme ve export hattı

```text
Kişi seçimi → Kayıt → Değişmez take → Offline işleme
     → İşlenen sürüm → Sporcu incelemesi → Kanonik sidecar
     → Kullanılabilirlik kapıları → Export paketi
```

## Kalıcı sözleşmeler

- Kayıt başlamadan görünür kişiden anchor seçilir.
- Ham varlık manifesti etiketleme tarafından değiştirilmez.
- İşleme sürümleri `created_at` ile sıralanır.
- Yayımlama kusursuzluk değil kullanılabilirlik sorusudur.
- Engelleyici kalite sorunları yalnız `source_empty`,
  `source_position_discontinuity` ve `review_proxy_desynchronised`.
- Canlı önizleme kaybı ile kayıt kaybı ayrı sayılır.
- Canonical export bir sonraki gerçek cihaz doğrulama hedefidir.

İlgili: [Kişi seçimi](subject-selection.md),
[Veri bütünlüğü](data-integrity.md), [Açık sorular](../open-questions.md).

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [5. Gerçekten çalışan özellikler](../archive/memory/5-5-gercekten-calisan-ozellikler.md)
- [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](../archive/memory/6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md)
- [6V. Capture → Verileri Hesapla → Etiketleme backend devamı (2026-09-11)](../archive/memory/6v-6v-capture-verileri-hesapla-etiketleme-backend-devami-2026-09-11.md)
- [6AA. Studio F3 — backend toplamsal ekleri, processing 1.1.0 (2026-09-13)](../archive/memory/6aa-6aa-studio-f3-backend-toplamsal-ekleri-processing-1-1-0-2026-09-13.md)
- [6AF. 17 Eylül — gerçek ZED kaydından etiketlemeye giden zincir](../archive/memory/6af-6af-17-eylul-gercek-zed-kaydindan-etiketlemeye-giden-zincir.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
