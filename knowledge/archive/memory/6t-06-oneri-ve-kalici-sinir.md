---
type: legacy-memory-section
status: archived
title: "Öneri ve kalıcı sınır"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2307-2334"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · ← [önceki](6t-05-calistirilan-testler-ve-sinirlar.md) · [sonraki](6u-6u-ingilizce-staj-defteri-gun-2630-2026-09-11.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md), [Açık sorular](../../open-questions.md).

### Öneri ve kalıcı sınır

Raporda dört plan, 13 alanlı karşılaştırma, Faz 0–5, coach GUI/failure states,
offline kişi kartları/hafif tracker/hibrit/tek kişi alanı karşılaştırması,
en az 5 sporcu için kontrollü ZED matrisi ve önerilen başarı kapıları var.
Öneri: önce depth sahiplik + gözlemleme, ardından Plan 2 raw-only + sürümlü
offline BODY_38; canlı kişi ipucu ancak pilotta koç yükü gerektirirse Plan 3.
Plan 4 referans doğruluk yetersizse araştırma. Planlar **onaylanmış uygulama
kararı değildir**. Kaynak FPS ve squat doğruluğu garanti edilmedi.

Önerilen yeni mimaride raw hash/ledger, derived version, source frame map,
subject association revision ve annotation/release bağı ayrı korunmalı.
Tespitsiz kare atlanmamalı; canonical skeleton kural tabanlı sessiz düzeltilmemeli.
Resume'da tracker state saklanamıyorsa baştan/history replay gerekeceği açık
olmalı; N'ye seek edip ID sürekliliği varsayılmamalı. Şema numarası atanmadı.

Gerçek sürümler değişmedi: app/package `0.10.0`; project `1.1.0`, session
`2.0.0`, take/skeleton stream `1.1.0`, annotation/release `2.2.0`, label
`2.0.0`, feature/raw archive `1.0.0`, identity SQLite `1`. Eski iki take
app `0.3.0`, take/skeleton `1.0.0`; migration yapılmadı. Yerel Python 3.11.14,
SDK 5.4.1, driver 616.56, RTX 2060 6 GB, i7-10750H, yaklaşık 15.84 GiB RAM
yeniden sorgulandı; kamera listesi boştu. Resmî Stereolabs belgeleri güncel
olarak kontrol edildi; belgedeki başka donanım FPS'i bu makineye taşınmadı.

Görev talimatı gereği rapor tesliminden sonra duruldu. Uygulama geliştirmesi
ayrı kullanıcı onayını bekler; bu tur onay için yeniden kamera bağlama şartı
konmadı ve gereksiz veri/yol düzeltmesi yapılmadı.
