---
type: legacy-memory-section
status: archived
title: "6Q. İngilizce staj defteri gün 16–25 (2026-09-06)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2005-2047"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6p-6p-squat-bacak-takibi-ve-ertelenmis-iskelet-isleme-tanisi-2026-09-02.md) · [sonraki](6r-6r-staj-defteri-gun-1625-anlatim-akisi-revizyonu-2026-09-06.md) →

Güncel karşılığı: [Staj raporu turları](../../milestones/internship-reports.md).

## 6Q. İngilizce staj defteri gün 16–25 (2026-09-06)

Kullanıcının staj defterinin sonraki on günü İngilizce ve iş odaklı olarak
hazırlandı. Çıktı:
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_16_25_EN.docx`.
Her gün 300–400 sözcük sınırındadır: gün 16–25 sırasıyla 331, 334, 326, 331,
333, 328, 319, 344, 335 ve 327 sözcük. Konular kamera backend sözleşmesi,
deterministik mock backend, ZED 2i adapteri ve BODY topolojileri, threaded
capture/yazıcı kuyrukları, kurtarılabilir skeleton ve RGB-D kayıtları, subject
lock, senkron playback, iki seviyeli interval annotation, anatomik joint
evidence ve feature/release export işidir. Metin deney raporu anlatımından
kaçınıp birinci tekil şahısla yapılan geliştirme, hata önleme ve doğrulama
işlerini anlatır.

Belgede 11 inline görsel vardır. Altısı gerçek kaynak koddan oluşturulan,
dosya ve satırları görünür code screenshot'larıdır; beşi gerçek PySide6
bileşenlerinin disposable mock proje/kamera verisiyle offscreen çalıştırılıp
`grab()` ile alınan Capture, Review, Timeline, JointRolePicker ve
FeatureSelectionDialog görüntüleridir. Görsel üretimi gerçek kullanıcı
kayıtlarına, identity DB'ye veya kullanıcı tercihine dokunmadı; geçici dataset
ve LOCALAPPDATA kullanıldı. Kullanıcının mevcut kirli
`label_dialogs.py`, `test_shell_chrome_gui.py` ve
`test_label_dialog_class_creation.py` değişiklikleri korunup değiştirilmedi.

Gerçekten çalıştırılan doğrulamalar:

- Mevcut `KineSynth` environment'ında
  `tests/test_capture.py`, `tests/test_subject_lock.py`,
  `tests/test_rgbd_archive.py`, `tests/test_timeline_preview.py`,
  `tests/test_joint_annotation_gui.py`, `tests/test_export.py` ve
  `tests/test_export_features.py`: toplanan 189 testin tamamı geçti.
- DOCX, standart renderer ile 14 sayfa PNG ve QA PDF'e çevrildi; her sayfa
  görsel olarak incelendi. Başlıktaki varsayılan mavi çizgi kaldırıldı.
- `a11y_audit.py`: high/medium/low 0; `images_audit.py`: 11/11 inline;
  `heading_audit.py`: 10 adet Heading 1.

Uygulama/package `0.10.0`; project `1.1.0`, session `2.0.0`, take/skeleton
stream `1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature/raw archive
`1.0.0`, identity SQLite `1` olarak kaldı. Bu turda uygulama kodu, package veya
şema değiştirilmedi. Canlı ZED donanım testi, self-test, wheel/package testi ve
tam test paketi çalıştırılmadı; staj belgesindeki donanım adapteri anlatımı
gerçek kod sözleşmesine ve önceki doğrulanmış proje hafızasına dayanır.
