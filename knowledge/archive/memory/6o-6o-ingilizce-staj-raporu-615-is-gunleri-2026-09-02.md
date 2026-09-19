---
type: legacy-memory-section
status: archived
title: "6O. İngilizce staj raporu, 6–15. iş günleri (2026-09-02)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1830-1871"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6n-6n-zorunlu-staj-raporunun-ilk-5-is-gunu-belgesi-2026-09-01.md) · [sonraki](6p-6p-squat-bacak-takibi-ve-ertelenmis-iskelet-isleme-tanisi-2026-09-02.md) →

Güncel karşılığı: [Staj raporu turları](../../milestones/internship-reports.md).

## 6O. İngilizce staj raporu, 6–15. iş günleri (2026-09-02)

Kullanıcının sonraki raporlar için kalıcı biçim tercihi güncellendi: rapor dili
**İngilizce**, her günün ana metni **300–400 kelime**, düzen ise kopyalamayı
kolaylaştıran sade metin + inline proje görseli olacaktır. Özel kapak, dekoratif
sayfa öğeleri, görsel hizalama çalışması veya yoğun masaüstü yayıncılık düzeni
yapılmayacak. Günler kesin commit tarihlerini taklit etmeyecek; 6M'de
kararlaştırıldığı gibi gerçek çalışmaları teknik bağımlılık sırasına yerleştiren
tematik iş paketleri olarak yazılacaktır.

6–15. günler için düzenlenebilir Word belgesi
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_06_15_EN.docx`
yolunda üretildi. Konular sırasıyla eğitim zamanı preprocessing ve zamansal
standardizasyon, subject-wise split/leakage önleme, 26 eklemli graph ve CTR-GCN,
temporal Transformer + hibrit mimari, exercise-conditioned correctness,
training/checkpoint/reproducibility, Small/Medium/Large kapasite deneyi, pooled
OOF değerlendirme, weak temporal evidence modeli ve masaüstü evidence explorer
entegrasyonudur. Gün 6–15 ana metin sözcük sayıları sırasıyla **381, 377, 389,
367, 382, 364, 371, 344, 341 ve 362**'dir.

Belgede yalnız güncel kod/README ve kayıtlı sonuç artefaktlarıyla doğrulanan
değerler kullanıldı. P1–P9 ana benchmarkı 1.049 örnek ve dokuz katlı LOSO'dur;
conditioned kapasite sonuçları correctness balanced accuracy için Small 0.6163,
Medium 0.6985, Large 0.7514; weak temporal evidence final run sonucu 0.7612 BA
ve 0.7620 macro-F1'dir. Suspected interval'ların frame-level ground truth veya
klinik hata sınırı olmadığı açıkça yazıldı; conditioning müdahalelerinde
bağlantının pratik etkisinin zayıf olduğu da abartılmadan raporlandı.

Nihai DOCX LibreOffice ile 13 sayfaya render edildi ve sayfaların tamamı görsel
olarak incelendi; kırpılma, taşma, bindirme, boş sayfa veya görselden ayrılmış
caption görülmedi. Son erişilebilirlik metadata eklemesinden önceki ve sonraki
13 sayfa PNG'lerinin SHA-256 karşılaştırması tamamen aynıdır. `images_audit.py`
10 görselin tamamının inline olduğunu, `heading_audit.py` 10 adet Heading 1
bulunduğunu, `a11y_audit.py` ise yüksek/orta/düşük önem düzeyinde bulgu
olmadığını doğruladı. Bu turda uygulama kaynak kodu, kullanıcı verisi, paket veya
şema değiştirilmedi; KineCapture **0.10.0** (project 1.1.0, session 2.0.0,
take/skeleton stream 1.1.0, annotation/release 2.2.0, label 2.0.0,
feature/raw archive 1.0.0, identity SQLite 1) ve KineSynthV3 **0.3.0** olarak
kaldı. Uygulama testi, self-test, GUI testi ve ZED donanım testi çalıştırılmadı;
yalnız belge sözcük sayımı, render, görsel, başlık ve erişilebilirlik denetimleri
çalıştırıldı.
