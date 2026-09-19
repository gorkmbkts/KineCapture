---
type: legacy-memory-section
status: archived
title: "Sürekli export sözleşmesi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "733-757"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-05-surekli-aktivite-domain-activity-py-export-continuous-py.md) · [sonraki](6d-07-bu-turda-bulunan-gercek-hatalar.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Sürekli export sözleşmesi

Bir örnek = bir kayıt, gerçek `T`. `continuous/` dizini + `activity_spec.json`.
Diziler: `joints_xyz`, `frame_indices`, `camera_timestamps_ns`,
`subject_present_mask`, `subject_source_tracking_id`,
`subject_association_confidence`, `activity_state_code`, `activity_label_mask`,
`exercise_active`, `exercise_class_index`, `exercise_class_valid_mask`,
`exercise_start_target`, `exercise_end_target`, `correctness_code`,
`error_label_mask`, `error_multi_hot` + seçilen feature dizileri.

Üç ayrım hiç bulanıklaşmıyor ve doğrulamada kontrol ediliyor:
etiketlenmemiş ≠ arka plan, kişi yok ≠ kişi hareketsiz, hata etiketi yok ≠
hata yok.

- Ham RGB-D **kopyalanmıyor**; manifest checksum'lu referans taşıyor.
- `split_group_id = take_id`; aynı kayıttan türetilen pencereler bölünemez.
- Fingerprint'e `dataset_modes` ve `activity_contract` sürümü girdi; sürekli
  örneğin anahtarı aktivite aralıklarını, kişi özetini, ham kaynak
  checksum'larını ve dosya checksum'unu içeriyor.
- Varsayılan export **değişmedi**: yalnız hareket örnekleri.
- Sürekli mod seçiliyken `select_rows` "hazır hareket" şartını kaldırıyor —
  aksi hâlde hiç egzersiz içermeyen negatif kayıtlar hiç görünmezdi.
- Kişi kilidinden önce alınmış kayıtlar `legacy_active_body: true` diye
  işaretleniyor ve doğrulama uyarısı üretiyor; otomatik migration yok.
