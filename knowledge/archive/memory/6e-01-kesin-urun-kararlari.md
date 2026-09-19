---
type: legacy-memory-section
status: archived
title: "Kesin ürün kararları"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "792-810"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · ← [önceki](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · [sonraki](6e-02-sqlite-kimlik-ve-erisim-katmani.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### Kesin ürün kararları

1. **Tek Sistem Sahibi vardır.** İlk kurulumdaki ilk hesap `owner` olur;
   SQLite partial unique index ikinci owner'ı DB düzeyinde de reddeder. Owner
   silinemez, pasifleştirilemez, role dönüştürülemez ve bütün projelere örtük
   erişir. İlk sürümde yalnız `owner | user` rolleri vardır.
2. **Self-registration yalnız normal kullanıcı üretir.** Giriş ekranındaki
   `Yeni Kullanıcı Oluştur` ad, soyad, isteğe bağlı unvan, kullanıcı adı,
   parola ve parola doğrulaması alır. Başarıda giriş formuna yalnız kullanıcı
   adı taşınır; parola taşınmaz veya tercihlere yazılmaz.
3. **Koç akışı** `giriş → proje → katılımcı → Kayda Başla → Capture`'dır.
   Operatör adı, teknik oturum formu ve tek plan varken plan seçimi sorulmaz.
4. **Protokol domain adı korundu, kullanıcı dili değişti.** Python'daki
   `CaptureProtocol` ve dosya alanları geriye uyumluluk için aynı; yeni bütün
   kullanıcı metinlerinde kavram **Kayıt Planı** olarak sunulur.
5. **Eski test datasetleri migrate edilmez ve SQLite'a otomatik kaydedilmez.**
   Owner isterse gelişmiş `Klasörden içe aktar` eylemiyle doğrulanmış bir
   projeyi kaydedebilir. Böylece eski klasör var diye yetkisiz proje açılmaz.
