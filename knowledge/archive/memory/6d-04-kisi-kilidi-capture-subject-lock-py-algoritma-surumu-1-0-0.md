---
type: legacy-memory-section
status: archived
title: "Kişi kilidi (`capture/subject_lock.py`, algoritma sürümü 1.0.0)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "679-711"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-03-ham-arsiv-mimarisi.md) · [sonraki](6d-05-surekli-aktivite-domain-activity-py-export-continuous-py.md) →

Güncel karşılığı: [Kişi seçimi ve subject lock](../../concepts/subject-selection.md).

### Kişi kilidi (`capture/subject_lock.py`, algoritma sürümü 1.0.0)

Qt'siz, deterministik, tamamen test edilebilir.

- `subject_id`: kayda özel, seçimde üretilir, **hiç değişmez**.
- `tracker_body_id`: o karede eşlenen SDK kimliği veya yok.
- Durum makinesi: `UNSELECTED → LOCKED → TEMPORARILY_LOST → REIDENTIFYING →
  LOCKED`, çıkmaz olarak `AMBIGUOUS`.
- **En güçlü kanıt eş-görünürlük**: seçili kişiyle aynı karede görülmüş bir
  tracker kimliği tanım gereği başka bir kişidir ve bir daha seçili kişi
  olamaz. Bu, prompt'ta yazmıyordu; ilk sürümde benzer ölçülü ikinci kişiye
  geçiş yaşandığı için eklendi ve gerçek donanımda çalıştığı doğrulandı.
- Diğer kanıtlar: konum sürekliliği (2 sn'den kısa boşlukta, makul yürüme
  hızıyla), uzuv oranları, boy. Ağırlıklar 0.4/0.4/0.2, eksik kanıt lehte
  sayılmaz (coverage ile iskonto edilir).
- Otomatik geçiş yalnız `skor >= 0.62` **ve** ikinci adaya fark `>= 0.15` ise.
  0.5 sn'lik grace, 20 sn sonra tamamen vazgeçip kullanıcıya soruyor.
- Bütün kararlar **ve reddedilen kararlar** audit'e yazılıyor: kare, zaman
  damgası, eski/yeni kimlik, yöntem, skor, fark, gerekçe, adaylar.
- **Gizlilik sınırı**: yüz tanıma yok, görünüm gömülmesi yok, kayıtlar arası
  biyometrik veritabanı yok. İmza yalnız uzuv oranı + boy, kapsamı tek kayıt.
- `VideoView.clicked` artık `(float, float)` görüntü pikseli taşıyor; letterbox
  ve DPI hesaba katılıyor. Hit testing tracker'ın kendi `joint_positions_2d`
  verisini kullanıyor (kesin), yoksa aday üretilmiyor. İki kişi 25 pikselden
  yakınsa seçim yapılmıyor. Tıklama **görüntülenen** karede çözülüyor
  (`packet=self._last_packet`), sonradan gelen karede değil.
- Kayıt sırasında sıradan tıklama kişiyi değiştirmiyor; ayrı "Kimliği yeniden
  doğrula" eylemi var ve olay üretiyor.
- `skeleton.jsonl` bütün gövdeleri saklamaya devam ediyor; yanına kare başına
  `subject` bloğu yazılıyor. `SkeletonFrame.subject_body()` **fallback
  yapmıyor**; `body()` (görüntüleme yardımcısı) yapıyor ve docstring'i bunu
  söylüyor.
