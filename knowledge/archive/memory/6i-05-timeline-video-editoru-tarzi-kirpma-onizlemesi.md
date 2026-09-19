---
type: legacy-memory-section
status: archived
title: "Timeline: video editörü tarzı kırpma önizlemesi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1385-1403"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) · ← [önceki](6i-04-kalici-proje-silme-yalniz-sistem-sahibi.md) · [sonraki](6i-06-export-modelden-bagimsiz.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Timeline: video editörü tarzı kırpma önizlemesi

- Yeni sinyaller: `edit_started`, `preview_position_changed(int)`,
  `edit_finished`, `edit_cancelled`. `position_changed` kalıcı playhead için
  ayrıldı — ikisini aynı saymak playhead'in farenin bırakıldığı yerde
  kalmasının sebebiydi.
- Altı sürükleme türünde de önizleme var: hareket/hata × başlangıç/bitiş
  yeniden boyutlandırma ve yeni aralık çizme. Hata aralığı önizlemesi ana
  hareket sınırına **son hâlle aynı kuralla** kırpılır.
- `_Drag.tentative_start/end` ekranda çizilir (`_drawn_bounds`); repository
  **fare bırakılana kadar hiçbir şey duymaz**. Eskiden her `mouseMove` bir
  mutasyon + bir undo snapshot + bir autosave üretiyordu; tek sürüklemeyi geri
  almak onlarca Ctrl+Z demekti. Artık bir sürükleme = bir yazma.
- Bırakınca: tek commit, sonra `ReviewPage._edit_finished` playhead'i
  **sürükleme başlamadan önceki kareye** döndürür ve oynatmayı başlatmaz.
- `Esc`, odak kaybı ve eşik altı kısa tıklama iptal eder; kısa tıklama eski
  scrub davranışını korur. `ReviewPage._redraw(position)` artık isteğe bağlı
  konum alıyor: önizleme `self._position`'a dokunmuyor.
