---
type: legacy-memory-section
status: archived
title: "Çalıştırılan testler ve sınırlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2280-2306"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · ← [önceki](6t-04-diger-dogrulanan-sozlesme-aciklari.md) · [sonraki](6t-06-oneri-ve-kalici-sinir.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

### Çalıştırılan testler ve sınırlar

- `-B -m kinecapture.tools.verify_zed_topology`: SDK 5.4.1 ile BODY_18 18/19,
  BODY_34 34/35, BODY_38 38/37 eklem/bağlantı eşleşti.
- Seçili 6 test dosyası: `test_zed_adapter.py`, `test_capture.py`,
  `test_rgbd_archive.py`, `test_subject_lock.py`, `test_storage.py`,
  `test_capture_subject_gui.py`.
- İlk koşu uzun audit temp yolu altında 13 failure + 14 setup error verdi
  (WinError 3 uzun yol sorunları). Aynı kapsam yeni kısa
  `C:\Users\gorke\AppData\Local\Temp\kcA3213` basetemp ile,
  `-B -m pytest -o addopts='' -q --tb=short -p no:cacheprovider` üzerinden
  **143 passed in 23.73s**. JUnit `pytest_short_path.xml` deney kökünde.
- Eski hafızadaki uzun yol sorununu yalnız proxy ile sınırlayan kabul doğru
  değil; metadata taraması/depth dosya erişimi de bu uzun yolda etkilendi.
  Kısa yolda test geçmesi uzun yol düzeltmesi değildir.
- Testler offscreen GUI ve mock yolları kapsar; SDK buffer alias regresyonu
  içermedikleri için yeni arşiv hatasını çürütmez. Yeni test kodu yazılmadı.
- Tam suite, self-test, gerçek camera capture, codec/precision/FAST A/B,
  koç pilotu, crash/power-loss/resume, başarılı atomic publish yapılmadı.
- Deneyler ve testler sonunda kaynak/test/config/pyproject, gerçek user_state,
  identity DB ve iki take içindeki 154 dosyanın hash+mtime kontrolünde değişen
  dosya yok. Kontrol MEMORY/raporu ve bütün kullanıcı diskini kapsamaz.
- Rapor teslim kontrolünde 10 ana bölüm, yerel bağlantıların varlığı/satır
  sınırları ve tablo sütunları doğrulandı; JUnit XML'de 143 test, 0 hata,
  0 failure, 0 skipped görüldü. `git diff --check` geçti. Yalnız MEMORY.md
  değişikliği ve yeni rapor working tree'de kaldı.
