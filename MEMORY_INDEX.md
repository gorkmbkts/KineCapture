# MEMORY_INDEX — KineCapture Studio

Her görevde **yalnız bu dosya** okunur. `MEMORY.md` bir arşivdir; aşağıdaki
dizinden yalnız ilgili bölüm hedefli açılır. Kod hafızadan önceliklidir.

## Güncel faz

Yeni backend (**Capture → Verileri Hesapla → İşlenen Videolar → Etiketleme**)
donanımsız uygulandı; **üretim PySide6 arayüzü bu mimariye göre henüz yeniden
yazılmadı**, canlı ZED doğrulaması sürüyor. Aktif görev:
`CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md` (F0…F14), F1 onay bekliyor.

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
| `core/` | errors, ids, jsonio (atomik), paths (uzun yol), config, logging, diagnostics, fingerprint |
| `domain/` | enums, models, project, labels, activity, arrays |
| `camera/` | `base` · `mock` · `zed` (pyzed yalnız burada, gecikmeli import) |
| `capture/` | `service.py` acquisition+writer thread; `subject_lock.py` kişi kilidi |
| `preview/` | `worker.py` LatestWorker (tek slot); `pose.py` CPU 2B pose; `vendor/` |
| `recording/` | `take_writer.py`; `rgbd_archive.py` chunk'lı ham RGB-D |
| `processing/` | **yeni offline katman**: `jobs.py` process_take · `sources.py` SVO replay · `review.py` ReviewDataset — Qt/SDK'sız |
| `playback/` | `take_reader.py` iskelet akışı + proxy video, kurtarma |
| `annotations/` | `repository.py` undo/redo, autosave |
| `dataset/` | `workspace.py` disk · `index.py` sorgu/QA · `deletion.py` kalıcı silme |
| `export/` | `release.py` staging → atomik yayın; `continuous.py` |
| `features/` | sürümlü seçilebilir özellik katmanı (31 özellik, 64 dizi) |
| `identity/` | SQLite şema, scrypt, auth/erişim servisi |
| `visualization/` | `skeleton_spec.py` ZED tabloları; `mapping.py` |
| `gui/` | PySide6; `pages/` 8 sayfa (review 1624, capture 1386 satır), `widgets/` (timeline 1232) |
| `tools/` | verify_zed_topology, extract_raw, capture_diagnostic, live_validation |

Durum makinesi: `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING →
REVIEWING`; `ERROR` her yerden erişilir.

## `MEMORY.md` bölüm dizini (satır no)

| # | Satır | İçerik |
|---|---|---|
| 1–2 | 18 | Kullanım politikası; faz geçmişi |
| 3–4 | 86 | Ortam; ZED SDK/donanım ölçümleri (ilk açılış, BGRA, confidence 0..100) |
| 5–6 | 173 | Çalışan özellikler; 16 kalıcı teknik karar (kare indeksi sözleşmesi, uzun yol, JSONL) |
| 6B | 294 | İki seviyeli etiketleme (MovementSample + ErrorInterval) |
| 6C | 393 | Seçilebilir özellik katmanı, registry, export sözleşmesi |
| 6D | 600 | **Ölçüm:** SVO2 depth'i geri vermez, H264 kayıplı; ham RGB-D arşivi; kişi kilidi |
| 6E | 790 | Kimlik/SQLite, tek Sistem Sahibi, proje erişimi |
| 6F–6G | 955 / 1033 | Capture+Review sadeleştirme; bindirme hizası kök nedeni |
| 6H–6I | 1197 / 1289 | Proje silme; **türetilmiş correctness**; timeline trim preview |
| 6J–6K | 1505 / 1560 | Eklem kanıtı: kanonik roller, `JointAnnotationStatus`, release 2.2.0 |
| 6L | 1715 | Dialogda sınıf oluşturma düzeltmesi |
| 6M–6O, 6Q–6R, 6U, 6W | 1756+ | Staj raporu turları — **kodu ilgilendirmez** |
| 6P | 1872 | Squat düz-bacak tanısı: BODY_34 hatası, BODY_38 adayı |
| 6S–6T | 2071 / 2141 | Squat/offline inceleme: **SDK depth tampon alias hatası**, frame-map bulgusu |
| 6V | 2375 | **YENİ MİMARİ:** minimum ham kayıt, LatestWorker, anchor, process_take, ReviewDataset |
| 6X | 2546 | Canlı ZED tek kişi testi — **devam ediyor**, tamamlanmadı |
| 6Y | 2580 | **F0/F1 (en güncel):** arayüz-backend kopukluğu, ölçülen performans açıkları |
| 7–9 | 2666 · 2693 · 2707 | Mimari sınırlar; test komutları; geçmiş doğrulamalar |
| 10–12 | 2957 · 2978 · 3001 | Bilinen sorunlar; uygulanmayanlar; önerilen adımlar |

Raporlar: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md` (güncel durum + ölçümler),
`KINECAPTURE_BACKEND_MIMARI_UYGULAMA_RAPORU_2026-09-11.md` (yeni backend).

## Bilinen açıklar (ölçümler 6Y'de)

- **Arayüz yeni backend'i tanımıyor.** Yeni raw-only kayıt Etiketleme'de
  0 gövde/0 video ile açılıyor; Capture'da kişi seçimi ölü (canlı body kapalı);
  `Verileri Hesapla` ve `İşlenen Videolar` ekranları yok.
- **Zaman çizelgesi 292–323 ms/çizim** (hedef ≤16 ms); etiketleme açılışı GUI
  thread'inde senkron (20 000 kare = 5,95 s); diziler memmap değil (135 MB);
  `DatasetIndex` 1000 kayıtta 650 ms tarıyor; listeler sanallaştırılmamış.
- Katman ayrımı (`viewmodels/`/`services/`), `tokens.json`, thumbnail, timeline
  özeti, OpenGL 3B görünüm ve beş yardımcı pencere yok.
- `tests/test_raw_capture_fields.py` **5 test kırmızı** (stub eskimesi).
- `pytest tests/` tek süreçte tamamlanmıyor; dosya dosya 38/39 dosya yeşil.
- Canlı ZED doğrulaması eksik: 60 FPS sürdürülebilirliği, H264_LOSSLESS bilgi
  koruması, native sayaç güvenilirliği, çok kişili anchor.
- SDK ilk model optimizasyonu (dakikalar) bağlan düğmesini bloklar.
- Proxy video Windows uzun yolda (`\\?\`, OpenCV) devre dışı kalır.
- Kullanıcı tercihindeki `dataset_root` var olmayan eski pytest yolunu
  gösteriyor; iki identity proje kaydı yetim. Proje kilidi yok.

## Sonraki adım

F1 çıktısı kullanıcıya verildi; **onay bekleniyor**. Onaysız F2'ye başlanmaz.
Onaylanırsa sıra: F2 katman+token+kabuk → backend toplamsal ekleri
(processing 1.1.0) → F7 timeline/etiketleme → F5 Verileri Hesapla → F4 Capture
anchor → F6 İşlenen Videolar.
