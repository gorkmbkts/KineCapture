---
type: concept
status: verified
updated: 2026-09-18
tags:
  - rgbd
  - depth
  - svo2
---

# RGB-D, SVO2 ve depth sınırları

## Kalıcı kararlar

- Ham kayıt değişmez ve yeniden işlenebilir olmalıdır.
- SVO2 tek başına beklenen depth dizisi sözleşmesini güvenilir biçimde geri
  vermediği için ayrı RGB-D arşiv yolu vardır.
- Capture ürünleri atomik kapanış, checksum, zaman eşleme ve provenance ile
  tamamlanır; yarım sonuç tamamlanmış gibi yayımlanmaz.
- Önizleme maliyeti ile kaydedilen veri maliyeti ayrı ölçülür.

## Ölçülmüş SDK sınırı

ZED SDK depth tamponunun sahiplik/alias davranışı, ardışık karelerin aynı
bellek içeriğine dönüşmesine yol açabildi. Depth kareleri SDK tamponundan
bağımsız kopyalanmadan saklanmış veri güvenilir sayılmaz.

Offline işleme yalnız gerçekten okunabilen kareleri işler; beyan edilen kaynak
kare sayısına ulaşamamak ayrıca raporlanır. SVO konumu ile canlı skeleton
konumu birebir aynı kabul edilmez.

Kaynaklar:
[backend raporu](../archive/reports/KINECAPTURE_BACKEND_MIMARI_UYGULAMA_RAPORU_2026-09-11.md),
[squat/offline raporu](../archive/reports/KINECAPTURE_SQUAT_OFFLINE_INCELEME_RAPORU_2026-09-10.md),
.

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [4. ZED SDK ve donanım — DOĞRULANMIŞ](../archive/memory/4-4-zed-sdk-ve-donanim-dogrulanmis.md)
- [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](../archive/memory/6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md)
- [6P. Squat bacak takibi ve ertelenmiş iskelet işleme tanısı (2026-09-02)](../archive/memory/6p-6p-squat-bacak-takibi-ve-ertelenmis-iskelet-isleme-tanisi-2026-09-02.md)
- [6S. GPT-6 Astra squat/offline inceleme handoff'u (2026-09-10)](../archive/memory/6s-6s-gpt-6-astra-squat-offline-inceleme-handoff-u-2026-09-10.md)
- [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](../archive/memory/6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
