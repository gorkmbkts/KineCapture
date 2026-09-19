---
type: legacy-memory-section
status: archived
title: "SQLite kimlik ve erişim katmanı"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "811-846"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · ← [önceki](6e-01-kesin-urun-kararlari.md) · [sonraki](6e-03-proje-sahipligi-ve-yetki.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### SQLite kimlik ve erişim katmanı

Yeni `kinecapture/identity/` paketi katmanları:

```text
database.py    kısa ömürlü bağlantı, PRAGMA, idempotent schema/transaction
repository.py  yalnız parametreli SQL sorguları
passwords.py   sürümlü scrypt türetme ve sabit-zaman karşılaştırma
service.py     kimlik doğrulama, owner kuralları, yetki ve proje koordinasyonu
models.py      User / ProjectAccess değer nesneleri; parola alanı içermez
```

- Windows varsayılan DB konumu:
  `%LOCALAPPDATA%\KineCapture\identity.sqlite3`. Datasetin ve
  `~/.kinecapture/user_state.yaml` tercihlerinin dışında, kullanıcı tarafından
  proje sanılmayacak deterministik bir konumdur. `AppConfig.identity_db_path`
  testlerde geçici yol enjekte eder ve tercih dosyasına yazılmaz.
- **Identity schema v1**: `users`, `projects`, `project_access`, `audit_log`,
  `app_metadata`. Sürüm hem `PRAGMA user_version=1` hem metadata tablosunda.
  Kurulum tekrar çalıştırılabilir. `foreign_keys=ON`, `busy_timeout=5000`,
  açık `BEGIN`/`BEGIN IMMEDIATE` ve bağlantı kapanışı var.
- Journal mode bilinçli olarak **DELETE**: işlemler kısa/yerel; kalıcı WAL
  sidecar'ları olmadan DB'nin yedeklenmesi ve taşınması daha güvenli. Büyük
  bilimsel veri hiçbir zaman SQLite'a girmez.
- Kullanıcı adı NFKC + `casefold` ile normalize edilir ve DB'de case-insensitive
  benzersizdir. Görünen ad 3-64 ASCII harf/rakam/nokta/alt çizgi/kısa çizgiyle
  sınırlıdır. SQL'in tamamı parametrelidir.
- Parola en az 8 karakterdir. `hashlib.scrypt` (`scrypt-v1`, N=16384, r=8,
  p=1, 32-byte çıktı), 16-byte kriptografik rastgele salt ve parametre JSON'u
  ayrı alanlarda tutulur; `secrets.compare_digest` kullanılır. Açık parola,
  geçici parola ve hash loglanmaz. Tercihler yalnız `last_username` saklar.
- Başarısız giriş kullanıcı adı/parola ayrımını açıklamaz; pasif hesap özel
  fakat güvenli bir pasiflik mesajıyla reddedilir. Başarılı giriş
  `last_login_at` günceller. Admin reset'i `must_change_password=1` yapar ve
  zorunlu değişim tamamlanmadan çalışma alanı gösterilmez.
