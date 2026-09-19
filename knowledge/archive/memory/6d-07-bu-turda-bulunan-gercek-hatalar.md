---
type: legacy-memory-section
status: archived
title: "Bu turda bulunan gerçek hatalar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "758-775"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-06-surekli-export-sozlesmesi.md) · [sonraki](6d-08-bilincli-olarak-sonraya-birakilanlar.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md).

### Bu turda bulunan gerçek hatalar

1. **`store_depth_frames` ölü ayardı** ve tooltip'i yanlış bir iddia taşıyordu.
2. **SVO2 "lossless" diye belgeleniyordu**; gerçekte H264 (kayıplı).
3. **`stop_native_recording` hatası yutuluyordu**; take başarılı görünebiliyordu.
4. **`link_activity_to_sample` sessizce çakışma yaratabiliyordu**: hareketin
   sınırlarını benimserken komşuyu kontrol etmiyordu, sonuç etiketli görünen
   fakat export edilemeyen bir kayıttı.
5. **Sürekli export, hazır hareket örneği olmayan kayıtları hiç görmüyordu**
   (`exportable_rows` filtresi) — tam da sürekli datasetin ihtiyaç duyduğu
   negatif örnekler eleniyordu.
6. **Kişi kilidi olmayan eski kayıtlar tamamen NaN sürekli örnek üretiyordu**;
   şimdi dürüst legacy yolu var ve manifestte işaretleniyor.
7. **Türev, kişinin görülmediği karede değer üretiyordu**: merkezi fark yalnız
   iki komşunun sonlu olmasını arıyordu. Artık farkı alınan karenin kendisi de
   sonlu olmalı.
8. **Tıklama sonraki karede çözülüyordu**; artık kullanıcının gördüğü karede.
