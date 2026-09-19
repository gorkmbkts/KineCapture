---
type: legacy-memory-section
status: archived
title: "Ham kayıt zenginleştirmesi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "447-473"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-01-urun-kararlari.md) · [sonraki](6c-03-feature-registry-mimarisi.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Ham kayıt zenginleştirmesi

`BodyPose` şu opsiyonel alanları kazandı; hepsi opsiyonel, eksikse `None`:
`joint_positions_2d [J,2]`, `joint_position_covariances [J,6]`,
`local_joint_positions_xyz [J,3]`, `root_orientation [4]`,
`tracker_root_velocity_xyz [3]`, `root_position_covariance [6]`,
`action_state` (`idle`/`moving`/`unknown`).

- `SKELETON_STREAM_SCHEMA_VERSION` 1.0.0 → **1.1.0** (yalnız ekleme).
  v1 JSONL **migration olmadan** okunur; alanı olmayan kayıtta özellik
  "yok" olarak raporlanır, uydurulmaz.
- Yanlış şekil **reddedilir** (`ValidationError`), asla yeniden şekillendirilmez.
  ZED adapter tarafında ise yanlış/boş şekil `None` olur ve kayıt sürer;
  `BODY_18` gibi biçimlerde fitting çıktılarının olmaması normaldir.
- `root_orientation` daha önce modelde vardı fakat `to_record`/`from_record`
  içinde kayboluyordu — düzeltildi (regresyon testi var).
- **Kovaryansın altı elemanının sırası doğrulanmadı**, bu yüzden ham
  saklanıyor ve "SDK native order" deniyor. Bundan std/belirsizlik
  TÜRETİLMİYOR; prompt'un izin verdiği koşul (sıra doğrulanmışsa) sağlanmadı.
- `keypoint_2d` piksel olduğu için anlamsız kalmasın diye **sol kamera iç
  parametreleri** bağlantı sırasında bir kez okunup take provenance'ına
  yazılıyor (`camera_info.extra.left_camera_calibration`): fx, fy, cx, cy,
  görüntü boyutu, distortion, model. Gerçek kamerada doğrulandı.
- Mock backend yalnız kendi modelinden dürüstçe türetebildiklerini üretir
  (2B projeksiyon, parent'a göre konum, analitik kök hızı, action state);
  quaternion ve kovaryanslar NaN'dır — "ölçülmedi" demek için.
