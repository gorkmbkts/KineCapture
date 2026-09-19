---
type: legacy-memory-section
status: archived
title: "6Y. PySide6 arayüz yeniden yapımı — F0 hafıza politikası + F1 tespiti (2026-09-13)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2580-2665"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6x-6x-tek-kisiyle-operator-kontrollu-zed-testi-devam-ediyor-2026-09-13.md) · [sonraki](6z-6z-studio-arayuzu-f2-katman-token-kabuk-2026-09-13.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

## 6Y. PySide6 arayüz yeniden yapımı — F0 hafıza politikası + F1 tespiti (2026-09-13)

`CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md` F0 ve F1 yapıldı. Üretim
kodu **değiştirilmedi**. Ayrıntılı rapor:
`F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

**F0 — hafıza politikası.** `MEMORY_INDEX.md` (6138 bayt) eklendi; bu dosyanın
başına arşiv uyarısı kondu ve "her oturumda tamamını oku" kuralı kaldırıldı.
Giriş noktası artık indekstir; buradan yalnız ilgili bölüm hedefli okunur.

### F1 — ölçülen kalıcı gerçekler

Hepsi bu makinede, `KineSynth` / `QT_QPA_PLATFORM=offscreen` ile çalıştırıldı.

- **Üretim arayüzü yeni backend'i tanımıyor.** Yeni varsayılan profille alınan
  bir ham kayıt (`store_skeleton=False`, `store_proxy=False`,
  `processing_status=awaiting_processing`) mevcut `load_take()` yolundan
  açıldığında 302 kare, **0 gövde**, `spec=None`, proxy yok veriyor:
  `take_reader.py:677` bu durumda `raw/rgbd/index.jsonl` dosyasını iskelet
  akışı sanıyor. `ReviewPage` `derived/processing/run_*` dizinine hiç bakmıyor,
  `ReviewDataset` GUI'de hiç kullanılmıyor. **Yeni kayıtlar arayüzden
  etiketlenemiyor.**
- **Capture'da kişi seçimi ölü.** `select_subject_at_pixel` → `packet.bodies`;
  yeni profilde canlı body tracking kapalı olduğu için liste hep boş. Yeni
  mimarinin `set_subject_anchor` + `CpuPosePreview` yolu yalnız
  `tools/live_validation.py` ve `tools/capture_diagnostic.py` içinde; `gui/`
  altında tek referansı yok.
- **Offline hat CLI'dan uçtan uca çalışıyor:** mock raw-only take →
  `python -m kinecapture.processing` → `state=complete`, 302 kare, 4,7 s,
  `issues: []`; `ReviewDataset` 0,11 s'de açılıyor, 9 dizi + 302 karelik proxy
  + canonical anchor veriyor.
- **Zaman çizelgesi bütçenin ~18 katı üstünde.** `TimelineWidget` tam görünüm
  yeniden çizimi: 5 dk/30 FPS **323 ms**, 60 dk/60 FPS **292 ms**, 1000 kareye
  zoom **84 ms** (hedef ≤16 ms). Maliyet kare sayısından değil piksel sütunu
  başına Python/numpy çağrısından geliyor: cProfile'da `_paint_availability`,
  `_x_to_frame` ve `np.clip` (10 boyamada 38 550 çağrı) baskın. Statik katman
  pixmap önbelleği ve çok çözünürlüklü özet yok.
- **Etiketleme açılışı GUI thread'ini kilitliyor.** `load_skeleton_stream`
  senkron ve bütün kareleri Python nesnesine çeviriyor: 20 000 kare × 1 gövde
  (BODY_38) = **5,95 s / 28,5 MB**; × 2 gövde = **12,41 s / 51,4 MB**.
  Doğrusal tahminle 60 dk/60 FPS ≈ 64 s / 308 MB (tek gövde). *Tahmin gerçek
  60 dakikalık kayıtla doğrulanmadı; kare başına ölçüm gerçektir.*
- **Diziler bellek eşlemeli değil.** `savez_compressed` + tam RAM okuma:
  60 dk/60 FPS/BODY_38 için 0,73 s / **135 MB**; aynı veri `.npy` memmap ile
  600 karelik pencere 7,5 ms / 0,27 MB.
- **`DatasetIndex` her yenilemede klasör tarıyor** (önbellek isabet etse bile):
  1000 kayıt / 2000 json için `rglob`+`stat` **650 ms**, GUI thread'inde.
  `DatasetPage` `QTableWidget` + hücre başına item kullanıyor: 1000 satır ×
  9 sütun = 36 ms, 5000 satır = 183 ms.
- **Bütçeyi tutanlar (körlemesine "optimize" edilmemeli):** soğuk açılış
  **0,96 s** (hedef ≤3 s); proxy scrub **8,6 ms** medyan, p95 11,3 ms
  (hedef ≤50 ms); sıralı oynatmada kare okuma 0,7 ms. `ProxyVideoReader`
  seek'i darboğaz değildir.
- **Promptun öngördüğü backend eksiklerinin hepsi doğru çıktı:** `.npy` memmap
  yok, timeline özeti yok, thumbnail yok, `ReviewDataset`'te derinlik erişimi
  yok, iş kuyruğunda duraklatma/ETA yok, özet indeksi yok. Ek olarak
  `ReviewDataset.position_of_anchor` her çağrıda `source_map`'i doğrusal
  tarıyor.
- Mimari katman (`viewmodels/`, `services/`), `tokens.json`/QSS üretici,
  pencere durumu kalıcılığı ve altı yardımcı pencereden beşi yok; 3B görünüm
  hâlâ `QPainter` (`QOpenGLWidget` değil).

### Test durumu (2026-09-13)

- `python -m kinecapture --self-test` → **exit 0** (eski canlı-iskelet profili;
  raw-only → processing → review zincirini kapsayan self-test yok).
- 39 test dosyası tek tek çalıştırıldı, toplam ≈6 dk: **38 dosya yeşil**,
  `tests/test_raw_capture_fields.py` **5 test kırmızı** —
  `AttributeError: 'object' object has no attribute 'ERROR_CODE'`. Test
  yardımcısı `sl` yerine düz `object()` veriyor; 6V'de `_retrieve_bodies`
  içine eklenen `_check_retrieval` `sl.ERROR_CODE` okuyor. Uygulama hatası
  değil, stub eskimesi — ama adapter bütünlük kontrolü şu an korumasız.
- `pytest tests/` **tek süreçte** ~28 dakikada bitmedi; süreç bu sürede yalnız
  ~289 s CPU harcadı (bekliyordu), elle durduruldu. Aynı belirti 6V'de de
  kayıtlı. Neden bulunamadı. **"Tam paket geçiyor" denemez.**

Sürümler değişmedi: app 0.11.0; take/skeleton 1.2.0, raw 1.1.0, processing
1.0.0, canonical annotation 1.0.0, subject association 1.1.0, project 1.1.0,
session 2.0.0, eski annotation/release 2.2.0, label 2.0.0, feature 1.0.0,
identity SQLite 1.

**Onay bekleyen:** F1 önceliklendirmesi ve `PROCESSING_SCHEMA_VERSION`
1.0.0 → 1.1.0 gerektirecek toplamsal backend ekleri (memmap dizileri, timeline
özeti, thumbnail, derinlik/anchor erişimi, türetilmiş özet indeksi). Onaysız
F2'ye başlanmadı.
