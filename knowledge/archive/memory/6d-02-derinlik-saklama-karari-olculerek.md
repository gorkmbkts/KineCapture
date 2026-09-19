---
type: legacy-memory-section
status: archived
title: "Derinlik saklama kararı (ölçülerek)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "632-650"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-01-olculerek-dogrulanan-gercekler-varsayim-degil.md) · [sonraki](6d-03-ham-arsiv-mimarisi.md) →

Güncel karşılığı: [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Derinlik saklama kararı (ölçülerek)

Gerçek ZED derinliği üzerinde, yeni bağımlılık kurmadan:

| şema | MB/dk | kayıpsız |
|---|---|---|
| zlib float32 | 5153 | evet |
| **byteshuffle + zlib-1 (varsayılan)** | **3534** | **evet** |
| temporal XOR + byteshuffle + zlib-1 | 3286 | evet |
| uint16 @1/4000 m + byteshuffle | 1612 | hayır (max hata 0.126 mm) |

Kayıpsızın zayıf sıkışması veriden: bir karede 200 000 pikselin 196 010'u
farklı değer, medyan komşu fark 9 mikrometre. Kodlama hızı ölçüldü: tek
thread 14.6 fps, 3 thread 38.1 fps → chunk sıkıştırma **3 worker thread**'de
çalışıyor (zlib GIL'i bırakıyor).

Varsayılan **kayıpsız float32**. Nicemlenmiş profil isteğe bağlı ve her yerde
"kayıplı" işaretli; ölçek, geçersiz sentinel, adım ve menzil chunk başlığında.
