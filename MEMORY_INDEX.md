# MEMORY_INDEX — KineCapture Studio

Her görevde **yalnız bu dosya** okunur. `MEMORY.md` arşivdir; dizinden yalnız
ilgili bölüm hedefli açılır. Kod hafızadan önceliklidir.

## Güncel faz

Yeni arayüz `kinecapture/studio/` altında yeniden yazılıyor (**F0–F7 bitti,
F8 sırada**: Etiketleme + timeline). Plan ve ilerleme: **`FAZ_PLANI_PYSIDE6_STUDIO.md`** — yeni bir
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
| processing · canonical annotation | **1.1.0** · 1.0.0 |
| subject association | 1.1.0 |
| eski annotation / release | 2.2.0 / 2.2.0 |
| label / feature spec | 2.0.0 / 1.0.0 |
| identity SQLite schema | 1 |

Ortam: `KineSynth` / Python 3.11.14, PySide6 6.10.1, numpy 2.4.6, opencv 4.12,
pyzed 5.4 / SDK 5.4.1. Donanım: RTX 2060 6 GB, i7-10750H, ~16 GB RAM.

## Modül haritası (`src/kinecapture/`, ~42,7k satır)

| Paket | İş |
|---|---|
| `core/` | errors, ids, jsonio (atomik), paths (uzun yol), config, fingerprint |
| `domain/` | enums, models, project, labels, arrays |
| `camera/` | `base` · `mock` · `zed` (pyzed yalnız burada, gecikmeli import) |
| `capture/` | `service.py` acquisition+writer; `subject_lock.py` |
| `preview/` | `worker.py` LatestWorker; `pose.py` CPU 2B pose |
| `recording/` | `take_writer.py`; `rgbd_archive.py` |
| `processing/` | **offline katman**: `jobs.py` · `sources.py` · `review.py` · `arrays.py` memmap · `summary.py` piramit · `thumbnails.py` · `depth.py` |
| `playback/` | `take_reader.py` iskelet akışı + proxy video, kurtarma |
| `annotations/` | `repository.py` undo/redo, autosave |
| `dataset/` | `workspace.py` · `index.py` · `deletion.py` · `summary_index.py` (türetilmiş) |
| `export/` | `release.py` staging → atomik yayın |
| `features/` | sürümlü seçilebilir özellik katmanı (31 özellik) |
| `identity/` | SQLite, scrypt, auth |
| `visualization/` | `skeleton_spec.py` ZED tabloları |
| `studio/` | **yeni arayüz**: `services/` · `viewmodels/` · `theme/` (Qt'siz) · `views/` |
| `gui/` | eski arayüz; `--legacy-gui` ile açılır, eski kayıtlar için korunuyor |
| `tools/` | verify_zed_topology, extract_raw, capture_diagnostic |

Durum makinesi: `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING →
REVIEWING`; `ERROR` her yerden erişilir.

## `MEMORY.md` bölüm dizini (satır no)

| # | Satır | İçerik |
|---|---|---|
| 1–2 | 18 | Kullanım politikası; faz geçmişi |
| 3–4 | 86 | Ortam; ZED SDK/donanım ölçümleri (ilk açılış, BGRA) |
| 5–6 | 173 | Çalışan özellikler; 16 kalıcı teknik karar (kare indeksi) |
| 6B | 294 | İki seviyeli etiketleme (MovementSample + ErrorInterval) |
| 6C | 393 | Seçilebilir özellik katmanı, registry, export |
| 6D | 600 | **Ölçüm:** SVO2 depth'i geri vermez, H264 kayıplı; RGB-D arşivi |
| 6E | 790 | Kimlik/SQLite, tek Sistem Sahibi, proje erişimi |
| 6F–6G | 955 / 1033 | Capture+Review sadeleştirme; bindirme hizası |
| 6H–6I | 1197 / 1289 | Proje silme; **türetilmiş correctness** |
| 6J–6K | 1505 / 1560 | Eklem kanıtı: kanonik roller, `JointAnnotationStatus` |
| 6L | 1715 | Dialogda sınıf oluşturma düzeltmesi |
| 6M–O, 6Q–R, 6U, 6W | 1756+ | Staj raporu turları — kodu ilgilendirmez |
| 6P | 1872 | Squat düz-bacak tanısı: BODY_34 hatası, BODY_38 adayı |
| 6S–6T | 2071 / 2141 | Squat/offline: **SDK depth tampon alias hatası** |
| 6V | 2375 | **BACKEND MİMARİSİ:** minimum ham kayıt, anchor, process_take |
| 6X | 2546 | Canlı ZED tek kişi testi — **devam ediyor**, tamamlanmadı |
| 6Y | 2580 | **F0/F1:** arayüz-backend kopukluğu, ölçülen performans açıkları |
| 6Z | 2666 | **F2:** studio/ katmanları, tokens.json, kabuk, offscreen font uyarısı |
| 6AA | 2748 | **F3:** processing 1.1.0 — memmap, özet, thumbnail, derinlik, indeks |
| 6AB | 2858 | **F4–F7 (en güncel):** ekranlar, TaskRunner, alt süreç, kütüphane, ölçümler |
| 7–9 | 2937 · 2964 · 2978 | Mimari sınırlar; test komutları; geçmiş doğrulamalar |
| 10–12 | 3228 · 3249 · 3272 | Bilinen sorunlar; uygulanmayanlar; önerilen adımlar |

Plan ve faz sonuçları: **`FAZ_PLANI_PYSIDE6_STUDIO.md`** (bölüm 7).
Tespit: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

## Bilinen açıklar (ölçümler 6Y'de)

- Studio'da Projeler · Yakalama · Verileri Hesapla · İşlenen Videolar ·
  Ayarlar çalışıyor. **Etiketleme, Veri Seti ve Dışa Aktarım yer tutucu.**
- **Timeline bütçesi (≤16 ms) henüz ölçülmedi — F8'e ait.** Eski timeline
  292–323 ms çiziyordu; veri tarafı F3'te hazırlandı.
- Python tablo modeli çizimde C++ `QTableWidget`'tan pahalı (21/15 ms);
  karşılığında doldurma satır sayısından bağımsız. Bu bir takas.
- OpenGL 3B görünüm ve altı yardımcı pencere yok.
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

**F8 — Etiketleme: timeline ve senkronizasyon.** F3'teki çok çözünürlüklü
özetten çizim, statik katman pixmap önbelleği, timestamp üzerinden senkron,
canonical sidecar 1.1.0. **Performans bütçeleri burada ölçülüp raporlanacak.**
Ayrıntı `FAZ_PLANI_PYSIDE6_STUDIO.md` bölüm 4'te.
