---
type: legacy-memory-section
status: archived
title: "1. Bu belge nasıl kullanılmalı?"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "18-46"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](00-kinecapture-studio-proje-hafizasi.md) · [sonraki](2-2-mevcut-asama.md) →

Güncel karşılığı: [Hafıza ve token mimarisi](../../architecture/memory-system.md).

## 1. Bu belge nasıl kullanılmalı?

Bu dosya, ZED 2i tabanlı veri toplama ve etiketleme uygulamasının Claude ve
Codex tarafından paylaşılan kalıcı proje hafızasıdır. Bir arşivdir; oturum
başına tamamını okumak ciddi bağlam israfıdır ve bu kural **kaldırılmıştır**.

### Okuma

1. Her görevde önce `MEMORY_INDEX.md` okunur.
2. Bu dosyadan yalnız ilgili bölüm, hedefli olarak (grep veya satır aralığı)
   açılır. Görevin dokunmadığı bölüm açılmaz.
3. Ardından repository içindeki gerçek dosyalar incelenir.
4. Buradaki kararlarla kod arasında çelişki varsa bu belirtilmeli ve **gerçek
   kod** doğrulanmalıdır; kod hafızadan önceliklidir.
5. Kararlaştırılmamış ürün ayrıntıları kendiliğinden kesinleştirilmez.

### Yazma

6. Buraya **yalnızca kalıcı bir şey öğrenildiğinde** yazılır: mimari karar,
   gerçekten çalıştırılmış doğrulama sonucu, sürüm/şema değişikliği, kapanmış
   veya yeni açılmış bir bilinmeyen. Küçük düzeltme, biçimlendirme, yeniden
   adlandırma ve başarısız deneme yazılmaz.
7. "Her görev sonunda hafıza güncellenir" kuralı kaldırılmıştır; yerine
   "kalıcı bilgi üretildiğinde yazılır" geçmiştir.
8. Durum değiştiyse `MEMORY_INDEX.md` güncellenir — bu kısa dosyanın güncel
   kalması arşivin güncel kalmasından önemlidir.
9. Bu dosya sonsuza kadar büyümez: şişen bölümün eski ayrıntısı özetlenerek
   sıkıştırılır, aynı bilgi iki yere yazılmaz.
