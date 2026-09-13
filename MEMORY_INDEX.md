# MEMORY_INDEX — KineCapture Studio

Her görevde **yalnız bu dosya** okunur. `MEMORY.md` arşivdir; dizinden yalnız
ilgili bölüm hedefli açılır. Kod hafızadan önceliklidir.

## Güncel faz

Yeni arayüz `kinecapture/studio/` altında yeniden yazılıyor (F0–F2 bitti,
**F3 sırada**). Plan ve ilerleme: **`FAZ_PLANI_PYSIDE6_STUDIO.md`** — yeni bir
oturumda sıra oradan alınır. `python -m kinecapture` Studio'yu, `--legacy-gui`
eski arayüzü açar. Kullanıcı kararı: **geriye dönük veri uyumluluğu aranmıyor;
mevcut veri silinmiyor.**

## Sürümler (kaynak: `src/kinecapture/__init__.py`)

| Sözleşme | Sürüm |
|---|---|
| app / paket | 0.11.0 |
| project / session | 1.1.0 / 2.0.0 |
| take / skeleton stream | 1.2.0 / 1.2.0 |
| raw archive · capture policy | 1.1.0 · 2 |
| processing · canonical annotation | 1.0.0 · 1.0.0 |
| subject association | 1.1.0 |
| eski annotation / release | 2.2.0 / 2.2.0 |
| label / feature spec | 2.0.0 / 1.0.0 |
| identity SQLite schema | 1 |

Ortam: `KineSynth` / Python 3.11.14, PySide6 6.10.1, numpy 2.4.6, opencv 4.12,
pyzed 5.4 / SDK 5.4.1. Donanım: RTX 2060 6 GB, i7-10750H, ~16 GB RAM.

## Modül haritası (`src/kinecapture/`, ~42,7k satır)

| Paket | İş |
|---|---|
| `core/` | errors, ids, jsonio (atomik), paths (uzun yol), config, logging, fingerprint |
| `domain/` | enums, models, project, labels, activity, arrays |
| `camera/` | `base` · `mock` · `zed` (pyzed yalnız burada, gecikmeli import) |
| `capture/` | `service.py` acquisition+writer thread; `subject_lock.py` |
| `preview/` | `worker.py` LatestWorker; `pose.py` CPU 2B pose; `vendor/` |
| `recording/` | `take_writer.py`; `rgbd_archive.py` ham RGB-D |
| `processing/` | **offline katman**: `jobs.py` process_take · `sources.py` SVO replay · `review.py` ReviewDataset |
| `playback/` | `take_reader.py` iskelet akışı + proxy video, kurtarma |
| `annotations/` | `repository.py` undo/redo, autosave |
| `dataset/` | `workspace.py` disk · `index.py` sorgu/QA · `deletion.py` silme |
| `export/` | `release.py` staging → atomik yayın; `continuous.py` |
| `features/` | sürümlü seçilebilir özellik katmanı (31 özellik) |
| `identity/` | SQLite şema, scrypt, auth/erişim |
| `visualization/` | `skeleton_spec.py` ZED tabloları; `mapping.py` |
| `studio/` | **yeni arayüz**: `services/` · `viewmodels/` · `theme/` (Qt'siz) · `views/` |
| `gui/` | eski arayüz; `--legacy-gui` ile açılır, eski kayıtlar için korunuyor |
| `tools/` | verify_zed_topology, extract_raw, capture_diagnostic |

Durum makinesi: `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING →
REVIEWING`; `ERROR` her yerden erişilir.

## `MEMORY.md` bölüm dizini (satır no)

| # | Satır | İçerik |
|---|---|---|
| 1–2 | 18 | Kullanım politikası; faz geçmişi |
| 3–4 | 86 | Ortam; ZED SDK/donanım ölçümleri (ilk açılış, BGRA, confidence) |
| 5–6 | 173 | Çalışan özellikler; 16 kalıcı teknik karar (kare indeksi, uzun yol) |
| 6B | 294 | İki seviyeli etiketleme (MovementSample + ErrorInterval) |
| 6C | 393 | Seçilebilir özellik katmanı, registry, export sözleşmesi |
| 6D | 600 | **Ölçüm:** SVO2 depth'i geri vermez, H264 kayıplı; ham RGB-D arşivi |
| 6E | 790 | Kimlik/SQLite, tek Sistem Sahibi, proje erişimi |
| 6F–6G | 955 / 1033 | Capture+Review sadeleştirme; bindirme hizası kök nedeni |
| 6H–6I | 1197 / 1289 | Proje silme; **türetilmiş correctness**; trim preview |
| 6J–6K | 1505 / 1560 | Eklem kanıtı: kanonik roller, `JointAnnotationStatus`, release 2.2.0 |
| 6L | 1715 | Dialogda sınıf oluşturma düzeltmesi |
| 6M–O, 6Q–R, 6U, 6W | 1756+ | Staj raporu turları — kodu ilgilendirmez |
| 6P | 1872 | Squat düz-bacak tanısı: BODY_34 hatası, BODY_38 adayı |
| 6S–6T | 2071 / 2141 | Squat/offline: **SDK depth tampon alias hatası**, frame-map |
| 6V | 2375 | **BACKEND MİMARİSİ:** minimum ham kayıt, anchor, process_take, ReviewDataset |
| 6X | 2546 | Canlı ZED tek kişi testi — **devam ediyor**, tamamlanmadı |
| 6Y | 2580 | **F0/F1:** arayüz-backend kopukluğu, ölçülen performans açıkları |
| 6Z | 2666 | **F2 (en güncel):** studio/ katmanları, tokens.json, kabuk, offscreen font uyarısı |
| 7–9 | 2748 · 2775 · 2789 | Mimari sınırlar; test komutları; geçmiş doğrulamalar |
| 10–12 | 3039 · 3060 · 3083 | Bilinen sorunlar; uygulanmayanlar; önerilen adımlar |

Raporlar: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`,
`KINECAPTURE_BACKEND_MIMARI_UYGULAMA_RAPORU_2026-09-11.md`.

## Bilinen açıklar (ölçümler 6Y'de)

- **Studio'da henüz gerçek ekran yok** (F4'ten itibaren gelecek); yer tutucular
  hangi fazın yapacağını yazıyor. Eski arayüz yeni kayıtları açamıyor.
- **Eski timeline 292–323 ms/çizim** (hedef ≤16 ms); etiketleme açılışı GUI
  thread'inde senkron (20 000 kare = 5,95 s); diziler memmap değil (135 MB);
  `DatasetIndex` 1000 kayıtta 650 ms tarıyor.
- Backend ekleri (memmap, timeline özeti, thumbnail, derinlik erişimi, özet
  indeksi) **F3'te** yapılacak; OpenGL 3B görünüm ve yardımcı pencereler yok.
- `pytest tests/` tek süreçte tamamlanmıyor; dosya dosya çalıştırılmalı.
- **`offscreen` Qt platformunda font ailesi yok**: genişlik/yerleşim ölçümleri
  orada anlamsız, `QT_QPA_PLATFORM=windows` gerekir (bkz. 6Z).
- Canlı ZED doğrulaması eksik: 60 FPS sürdürülebilirliği, H264_LOSSLESS bilgi
  koruması, native sayaç güvenilirliği, çok kişili anchor.
- SDK ilk model optimizasyonu (dakikalar) bağlan düğmesini bloklar; proxy
  video Windows uzun yolda (OpenCV) kullanılamaz.
- Kullanıcı tercihindeki `dataset_root` var olmayan eski pytest yolunu
  gösteriyor; iki identity proje kaydı yetim. Proje kilidi yok.

## Sonraki adım

**F3 — backend toplamsal ekleri** (`PROCESSING_SCHEMA_VERSION` 1.0.0 → 1.1.0):
`.npy` memmap dizileri, çok çözünürlüklü timeline özeti, thumbnail üretimi,
`ReviewDataset`'te derinlik + anchor indeks erişimi, `job.json` duraklat/ETA,
türetilmiş özet indeksi. Ayrıntı ve bitti ölçütü `FAZ_PLANI_PYSIDE6_STUDIO.md`
bölüm 4'te.
