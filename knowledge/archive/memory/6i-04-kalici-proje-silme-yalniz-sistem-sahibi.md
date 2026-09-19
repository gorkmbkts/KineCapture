---
type: legacy-memory-section
status: archived
title: "Kalıcı proje silme (yalnız Sistem Sahibi)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1348-1384"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-03-surumler-gercekten-degisenler.md) · [sonraki](6i-05-timeline-video-editoru-tarzi-kirpma-onizlemesi.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### Kalıcı proje silme (yalnız Sistem Sahibi)

Yeni `kinecapture/dataset/deletion.py` + `IdentityService` uzantıları.

- **Yetki servistedir:** `IdentityService.authorize_project_deletion()` owner
  şartını uygular. Normal kullanıcı düğmeyi görmez *ve* GUI'yi atlarsa
  `AuthorizationError` alır (test edildi).
- **Onay:** proje adı + kimlik + **tam, elide edilmemiş, kopyalanabilir yol**,
  ne silineceği ve geri alınamazlığı. Son düğme **proje adı birebir yazılana
  kadar** pasif. İptal/kapatma/yanlış metin = tam no-op. İş başladıktan sonra
  ikinci tıklama yeni iş üretmez ve **İptal düğmesi sunulmaz**.
- **GUI thread bloklanmaz:** `DeletionWorker(QThread)` ölçüm ve silmeyi
  yürütür; dialog ilerlemeyi gösterir. Worker'a servis değil düz bir callable
  verilir, böylece threading hiçbir şey silmeden test edilebilir.
- **Path guard'ları** (`inspect_target`, saf fonksiyon, yalnız DB kaydını alır):
  resolve + kayıtla karşılaştırma, `project.json` içindeki `project_id`
  eşleşmesi, sürücü kökü / home / dataset kökü / kaynak klasör reddi,
  symlink & Windows junction (reparse point) reddi. Proje **içindeki**
  bağlantı izlenmez, yalnız bağın kendisi kaldırılır (test edildi).
- **Sıra:** authorize → preflight → aktif bağlamı bırak (capture service ve
  video handle'ları; Windows açık handle'lı klasörü taşımaz) → `os.replace` ile
  `datasets/.deleting/<id>__<zaman>` tombstone → DB transaction → baytları sil.
- **DB hatası:** proje eski yerine geri taşınır, hiçbir dosya silinmez
  (`StorageError delete_db_failed`). **Dosya kalırsa:** başarı gösterilmez,
  kalan yollar raporlanır, `project_files_remaining` audit olayı yazılır.
- **Audit FK:** `audit_log.project_id → projects` bağı yüzünden geçmiş
  silinmiyor. Önce her olayın metadata'sına proje kimliği/adı kopyalanıyor,
  sonra işaretçi `NULL` yapılıyor; `project_deleted` olayı actor + yol ile
  ekleniyor.
- **Kurtarma:** girişte `.deleting` taranır. `database_cleared: true` ise silme
  tamamlanır; `false` ise proje eski yoluna geri alınır; işareti okunamayan
  klasöre **dokunulmaz** ve bildirilir. Belirsizlik veriyi korumaktan yana.
- **Kayıt sürerken silme reddedilir** (`recording_blocks_delete`); kayıt
  kullanıcının haberi olmadan durdurulmaz.
- Read-only dosyalar `onerror` içinde yazılabilir yapılıp yeniden deneniyor
  (Windows'un klasik yarıda kalan silme sebebi); uzun yollar `long_path()`.
