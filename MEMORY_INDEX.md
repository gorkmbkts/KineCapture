# MEMORY_INDEX — KineCapture Studio

Her görevde **yalnız bu dosya** okunur. `MEMORY.md` arşivdir; yalnız ilgili
bölüm hedefli açılır. Kod hafızadan önceliklidir.

## Güncel faz

Yeni arayüz `kinecapture/studio/` altında **tamamlandı (F0–F15)**. Sekiz
ekranın hepsi gerçek; uçtan uca tur mock ile çalıştırıldı. Plan ve faz
sonuçları: **`FAZ_PLANI_PYSIDE6_STUDIO.md`** bölüm 7. `python -m kinecapture` Studio'yu, `--legacy-gui`
eski arayüzü açar. Kullanıcı kararı: **geriye dönük veri uyumluluğu aranmıyor;
mevcut veri silinmiyor.**

## Sürümler (kaynak: `src/kinecapture/__init__.py`)

| Sözleşme | Sürüm |
|---|---|
| app / paket | 0.11.0 |
| project / session | 1.1.0 / 2.0.0 |
| take / skeleton stream | 1.2.0 / 1.2.0 |
| raw archive · capture policy | 1.1.0 · 2 |
| processing · canonical annotation | **1.1.0** · **1.1.0** |
| subject review · canonical release | **1.0.0** · **1.0.0** |
| subject association | 1.1.0 |
| eski annotation / release | 2.2.0 / 2.2.0 |
| label / feature spec | 2.0.0 / 1.0.0 |
| identity SQLite schema | 1 |

Ortam: `KineSynth` / Python 3.11.14, PySide6 6.10.1, numpy 2.4.6, opencv 4.12,
pyzed 5.4 / SDK 5.4.1. RTX 2060 6 GB, i7-10750H, ~16 GB RAM. **PyOpenGL kurulu
ama hızlandırıcısı numpy 2.x ile uyumsuz — 3B görünüm yalnız Qt GL sınıflarını
kullanır.**

## Modül haritası (`src/kinecapture/`, ~42,7k satır)

| Paket | İş |
|---|---|
| `core/` | errors, ids, jsonio (atomik), paths (uzun yol), config, fingerprint |
| `domain/` | enums, models, project, labels, arrays |
| `camera/` | `base` · `mock` · `zed` (pyzed yalnız burada, gecikmeli import) |
| `capture/` | `service` acquisition+writer; `subject_lock` |
| `preview/` | `worker` LatestWorker; `pose` CPU 2B pose |
| `recording/` | `take_writer`; `rgbd_archive` |
| `processing/` | **offline katman**: `jobs` · `sources` · `review` · `annotations` · `arrays` memmap · `summary` piramit · `thumbnails` · `depth` |
| `playback/` | `take_reader` iskelet akışı + proxy video, kurtarma |
| `annotations/` | `repository` undo/redo, autosave (eski) |
| `dataset/` | `workspace` · `index` · `deletion` · `summary_index` (türetilmiş) |
| `export/` | `release` staging → atomik yayın |
| `features/` | sürümlü seçilebilir özellik katmanı (31 özellik) |
| `identity/` | SQLite, scrypt, auth |
| `visualization/` | `skeleton_spec` ZED tabloları |
| `studio/` | **yeni arayüz**: `services/` · `viewmodels/` · `theme/` (Qt'siz) · `views/` |
| `gui/` | eski arayüz; `--legacy-gui`, eski kayıtlar için korunuyor |
| `tools/` | verify_zed_topology, extract_raw, capture_diagnostic |

Durum: `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING →
REVIEWING`; `ERROR` her yerden.

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
| 6H–6I | 1197 / 1289 | Proje silme; **türetilmiş correctness** |
| 6J–6K | 1505 / 1560 | Eklem kanıtı: kanonik roller, `JointAnnotationStatus` |
| 6P | 1872 | Squat düz-bacak tanısı: BODY_34 hatası, BODY_38 adayı |
| 6S–6T | 2071 / 2141 | Squat/offline: **SDK depth tampon alias hatası** |
| 6V | 2375 | **BACKEND MİMARİSİ:** min ham kayıt, anchor, process_take |
| 6X | 2546 | Canlı ZED tek kişi testi — **devam ediyor**, tamamlanmadı |
| 6Y | 2580 | **F0/F1:** arayüz-backend kopukluğu, ölçülen performans açıkları |
| 6Z | 2666 | **F2:** studio/ katmanları, tokens.json, kabuk, offscreen font |
| 6AA | 2748 | **F3:** processing 1.1.0 — memmap, özet, thumbnail, derinlik |
| 6AB | 2858 | **F4–F7:** ekranlar, TaskRunner, alt süreç, kütüphane, ölçümler |
| 6AC | 3305 | **F8:** Etiketleme, kanonik sidecar, 7 backend açığı, bütçeler |
| 6AD | 3401 | **F9–F15 (en güncel):** 3B, sporcu, dışa aktarım, cila, ölçümler |
| 7–9 | 2937 · 2964 · 2978 | Mimari sınırlar; test komutları; doğrulamalar |
| 10–12 | 3228 · 3249 · 3272 | Bilinen sorunlar; uygulanmayanlar; adımlar |

Plan ve faz sonuçları: **`FAZ_PLANI_PYSIDE6_STUDIO.md`** (bölüm 7).
Tespit: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

## Bilinen açıklar (ölçümler 6Y'de)

- Studio'da Projeler · Yakalama · Verileri Hesapla · İşlenen Videolar ·
  **Etiketleme** · Ayarlar çalışıyor. **Veri Seti ve Dışa Aktarım yer tutucu.**
- Bütçeler ölçüldü ve karşılandı (6AD). **Gerçek ZED ile tam tur yok**; iki
  kişinin karıştığı kayıt mock ile üretilemedi.
- Python tablo modeli çizimde `QTableWidget`'tan pahalı (21/15 ms);
  karşılığında doldurma satır sayısından bağımsız — bilinçli takas.
- **`pytest tests/` tek süreçte tamamlanmıyor**; dosya dosya çalıştırılmalı.
- **`offscreen` Qt platformunda font ailesi yok**: genişlik/yerleşim ölçümleri
  orada anlamsız, `QT_QPA_PLATFORM=windows` gerekir (bkz. 6Z).
- Canlı ZED doğrulaması eksik: 60 FPS, H264_LOSSLESS bilgi koruması, native
  sayaç güvenilirliği, çok kişili anchor.
- SDK ilk model optimizasyonu (dakikalar) bağlan düğmesini bloklar; proxy video
  Windows uzun yolda (OpenCV) açılamaz — uzun `pytest` kökünde koşu dürüstçe
  `partial` olur (6AC).
- `dataset_root` tercihi eski pytest yolunu gösteriyor; proje kilidi yok.

## Sonraki adım

**Gerçek ZED ile doğrulama.** Kamera karşısında tek kişilik bir kayıt alıp
yakalama → işleme → etiketleme → dışa aktarım turunu gerçek veriyle tekrarlamak;
60 FPS sürdürülebilirliği ve canlı iskeletin doğruluğu ancak orada ölçülebilir.
Ayrıca yakalama ekranının tıkla-seç kişi akışı uçtan uca bağlanmalı (6AD).
