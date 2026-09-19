---
type: legacy-memory-section
status: archived
title: "Proje sahipliği ve yetki"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "847-864"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · ← [önceki](6e-02-sqlite-kimlik-ve-erisim-katmani.md) · [sonraki](6e-04-minimum-katilimci-ve-otomatik-cekim-oturumu.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### Proje sahipliği ve yetki

- `projects` aynı `project_id`'nin doğrulanmış, normalize edilmiş tek klasör
  yolunu ve `owner_user_id`'yi tutar. Aynı kimliğin farklı klasöre bağlanması
  reddedilir.
- Normal kullanıcı yalnız sahibi olduğu veya `project_access` ile atanmış
  projeleri listeler. Owner bütün kayıtlı projeleri ayrı erişim satırı olmadan
  görür. Normal kullanıcının oluşturduğu proje otomatik onun mülkiyetine ve
  erişimine girer.
- Dosya sistemi proje oluşturma başarılı fakat DB kaydı başarısız olursa yalnız
  o çağrının yeni, doğrulanmış `dataset_root/projects/<project_id>` dizini
  telafi olarak kaldırılır. Erişim kaldırma hiçbir proje dosyasını silmez.
- `AppState.open_project`, proje/katılımcı listeleme-oluşturma,
  `prepare_capture`, kayıt öncesi doğrulama ve admin işlemleri servis katmanında
  aktif kullanıcı + erişim kontrolünü tekrar yapar. `last_project_path`
  doğrudan açılmaz; tek erişilebilir proje otomatik açılır, sıfır/çok projede
  Projeler sayfası gösterilir.
