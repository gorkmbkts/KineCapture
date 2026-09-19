---
type: legacy-memory-section
status: archived
title: "Sürekli aktivite (`domain/activity.py`, `export/continuous.py`)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "712-732"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-04-kisi-kilidi-capture-subject-lock-py-algoritma-surumu-1-0-0.md) · [sonraki](6d-06-surekli-export-sozlesmesi.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Sürekli aktivite (`domain/activity.py`, `export/continuous.py`)

- Dört karşılıklı dışlayan durum: `background`(0), `transition`(1),
  `target_exercise`(2), `other_activity`(3). **Etiketlenmemiş = -1 ve bir sınıf
  değil.**
- Çakışma domain'de reddediliyor; yeni aralık boş alana kırpılıyor, tamamen
  doluysa hata.
- `target_exercise` bir `MovementSample`'a bağlanabiliyor; bağlıyken **sınırın
  tek kaynağı hareket**. Bağlı aralığın sınırı doğrudan düzenlenemiyor, hareket
  taşınınca birlikte taşınıyor. Bağlama, komşuyla çakışacaksa reddediliyor.
- "Boşlukları arka plan yap" **açık onay** istiyor (`confirmed=True`), GUI'de
  ayrıca ne iddia edildiğini anlatan bir onay kutusu var.
- `evaluate_continuous` tek kural; hem İnceleme ekranı hem exporter kullanıyor.
  Hareket-sample hazırlığından **bağımsız**.
- Annotation şeması yalnız ekleme yönünde genişledi: sidecar'a
  `activity_intervals` anahtarı eklendi, dosya adı ve `samples` değişmedi.
  Anahtarı olmayan eski dosya boş strip olarak okunuyor ve **okurken yeniden
  yazılmıyor**. `save_samples(activity_intervals=None)` diskte olanı koruyor,
  yani aktivite katmanını bilmeyen bir çağıran onu silemiyor.
- Undo/redo iki katmanı **birlikte** anlık görüntülüyor (`_State`).
