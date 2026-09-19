---
type: legacy-memory-section
status: archived
title: "GUI"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "892-910"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · ← [önceki](6e-04-minimum-katilimci-ve-otomatik-cekim-oturumu.md) · [sonraki](6e-06-surumler-ve-dogrulama.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### GUI

- `MainWindow` çalışma shell'ini `AuthPage` arkasında tutar; kimlik doğrulama
  bitmeden sayfalar ve last-project açma görünür/aktif değildir.
- İlk kurulum, normal login, parola göster/gizle, Enter ile login, alan bazlı
  self-registration, zorunlu parola değiştirme ve owner-only
  `Kullanıcılar ve Erişimler` dialogu eklendi.
- Admin dialogu ad/unvan/kullanıcı adı/durum/proje sayısı/son giriş gösterir;
  normal kullanıcı oluşturma, profil düzenleme, aktif/pasif, geçici parola ve
  proje atama/kaldırma sağlar. Fiziksel silme veya rol kontrolü yoktur; servis
  bu çağrıları ayrıca açıkça reddeder.
- Üst bağlam artık **Kullanıcı | Proje | Katılımcı | Kamera | Disk**;
  `Oturum` chip'i kaldırıldı. Kullanıcı menüsü Şifre Değiştir, Oturumu Kapat ve
  owner için Kullanıcıları Yönet eylemlerini içerir.
- Projeler normal kullanıcıda yalnız erişilebilir kayıtları gösterir; teknik
  klasör/root kontrolleri yalnız owner'da görünür. Kayıt Planı formu plan adı,
  satır başına sıralı hareket ve özetle başlar; hedef ayrıntıları varsayılan
  kapalı Gelişmiş hedefler altındadır.
