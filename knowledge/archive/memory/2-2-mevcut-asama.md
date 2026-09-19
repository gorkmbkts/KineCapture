---
type: legacy-memory-section
status: archived
title: "2. Mevcut aşama"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "47-85"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](1-1-bu-belge-nasil-kullanilmali.md) · [sonraki](3-3-ortam-dogrulanmis.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

## 2. Mevcut aşama

**Uçtan uca dikey dilim + iki seviyeli etiketleme çalışıyor.**

- 2026-08-20: PROMPT.md bölüm 5'teki 15 adımlık akış tamamlandı; hem sentetik
  hem gerçek ZED 2i donanımıyla doğrulandı.
- 2026-08-21: `CLAUDE_ANNOTATION_REDESIGN_PROMPT.md` uygulandı. Etiket modeli
  **iki seviyeye** çıkarıldı (hareket sample'ı + zamansal hata aralığı),
  hareket fazı kaldırıldı, doğru/yanlış ikili hale getirildi, İnceleme ekranı
  ve export sözleşmesi yeniden yazıldı. Ayrıntı: bölüm 6B.
- 2026-08-23: `CLAUDE_SKELETON_FEATURE_EXPORT_PROMPT.md` uygulandı. Ham kayıt
  geriye uyumlu biçimde zenginleştirildi, `kinecapture/features/` altında
  **sürümlü seçilebilir özellik katmanı** kuruldu, export ve Export ekranı bu
  katmanı taşıyacak şekilde genişletildi. Ayrıntı: bölüm 6C.
- 2026-08-24: `CLAUDE_CONTINUOUS_ACTIVITY_RGBD_SUBJECT_LOCK_PROMPT.md`
  uygulandı: **zorunlu ham RGB-D arşivi**, **görüntüye tıklayarak kişi seçimi
  ve kalıcı kişi kilidi**, **sürekli aktivite etiketleme ve dataseti**.
  Ayrıntı: bölüm 6D.
- 2026-08-26: `CODEX_AUTH_PROJECT_PARTICIPANT_REDESIGN_PROMPT.md` uygulandı:
  **tek Sistem Sahibi**, normal kullanıcı self-registration, SQLite kimlik ve
  proje erişimi, girişle otomatik operatör bağlama, sade Projeler/Katılımcılar
  akışı ve kullanıcıdan gizlenen otomatik çekim oturumu. Ayrıntı: bölüm 6E.
- 2026-08-28: `CLAUDE_CAPTURE_REVIEW_LABELING_UI_PROMPT.md` uygulandı.
  Capture'ın kalıcı sağ sütunu modeless bilgi penceresine taşındı, İnceleme
  ekranı yalnızca kayıtta seçilmiş kişiyi çizer hale getirildi, RGB bindirme
  hizası kök nedeninden (proxy/kamera piksel uzayı karışması) düzeltildi,
  etiketleme iki küçük diyaloga indirildi ve aktivite yazımı emekliye ayrıldı
  (veri korunarak). Ayrıntı: bölüm 6G.
- 2026-08-30: `CLAUDE_PROJECT_DELETE_LABELING_EXPORT_GUI_PROMPT.md` uygulandı.
  Doğru/hatalı kararı hata aralıklarından türetilir hale geldi (annotation
  2.1.0), yalnız Sistem Sahibinin kullanabildiği kalıcı proje silme eklendi,
  zaman çizelgesi sürüklemesine kare önizlemesi ve tek commit getirildi, export
  modelden bağımsız hale getirildi, Export/Ayarlar/Dataset/Projeler duyarlı
  yapıldı ve NavigationRail'e paketlenmiş YTÜ logosu eklendi. Ayrıntı: bölüm
  6I.

Önceki scaffold aşaması bu sürümle büyük ölçüde değiştirildi. "Değişen
kararlar" bölümleri farkları kaydeder.
