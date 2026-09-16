# MEMORY_INDEX — KineCapture Studio

Önce bu indeks; `MEMORY.md` yalnız hedefli okunur. Kod önceliklidir.

## Güncel faz

Studio F0–F15 teslim edildi. **15 Eylül denetiminin P0 açıkları 16 Eylül'de
kapatıldı** ve görsel sistem yeniden kuruldu (aşağıda). Sekiz ekran gerçek.
Faz geçmişi: `FAZ_PLANI_PYSIDE6_STUDIO.md` §7. `python -m kinecapture` Studio,
`--legacy-gui` eski GUI. Eski veri uyumluluğu aranmıyor; veri silinmiyor.

## Sürümler

Tam liste: `src/kinecapture/__init__.py`. app 0.11.0 · processing 1.1.0 ·
canonical annotation 1.1.0 · subject review 1.0.0 · canonical release 1.0.0 ·
studio theme tokens **1.1.0** · identity SQLite şema 1.

Ortam: `KineSynth` / Python 3.11.14, PySide6 6.10.1, numpy 2.4.6, opencv 4.12,
pyzed 5.4 / SDK 5.4.1. RTX 2060 6 GB, i7-10750H, ~16 GB RAM. **PyOpenGL
hızlandırıcısı numpy 2.x ile uyumsuz — 3B yalnız Qt GL sınıfları.**

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
| `studio/` | **yeni arayüz**: `services/` `viewmodels/` `theme/` (Qt'siz) `views/` (+`theming` `palette` `qssassets` `toasts` `brand`) |
| `gui/` | eski arayüz; `--legacy-gui`, eski kayıtlar için korunuyor |
| `tools/` | verify_zed_topology, extract_raw, capture_diagnostic |

Durum: `DISCONNECTED→READY→PREVIEWING→RECORDING→STOPPING→REVIEWING`, `ERROR`.
## `MEMORY.md` bölüm dizini (satır no)

1–2 (18) politika/faz · 3–4 (86) ortam, ZED ölçümleri · 5–6 (173) çalışan
özellikler, 16 kalıcı karar · 6B (294) iki seviyeli etiketleme · 6C (393)
özellik katmanı · 6D (600) **SVO2 depth'i geri vermez** · 6E (790) kimlik ·
6H–6I (1197/1289) silme, türetilmiş correctness · 6J–6K (1505/1560) eklem
kanıtı · 6P (1872) squat düz-bacak · 6S–6T (2071/2141) **SDK depth alias
hatası** · 6V (2375) **backend mimarisi** · 6X (2546) canlı ZED — devam ediyor ·
6Y (2580) F0/F1 açıklar · 6Z (2666) F2 katmanlar · 6AA (2748) F3 processing ·
6AB (2858) F4–F7 · 6AC (3305) F8 etiketleme · 6AD (3401) F9–F15 · 6AE **16 Eylül
GUI/UX** · 7–9 (2937/2964/2978) sınırlar, testler, doğrulamalar · 10–12
(3228/3249/3272) sorunlar, uygulanmayanlar, adımlar.

Plan: **`FAZ_PLANI_PYSIDE6_STUDIO.md`** §7. Tespit: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

## 16 Eylül GUI/UX turu (ayrıntı: `MEMORY.md` §6AE)

Kapandı, regresyon testli: etiketleme açılışı `ReviewViewModel.opened` olayına
bağlı; kayıt hedefi tek kaynakta (`SessionService`/`WorkTarget`); kayıt modu
backend profiline giriyor (`profile_for_mode`); kayıt kabukta görünür ve her
ekrandan durdurulabilir (Ctrl+Shift+S), açık kayıt işlenemez; proje listesi
kullanıcıya göre yüklenir; tanılama doğru imza + dört durum. Görsel: tokens
1.1.0, `theming.apply_application_theme` (Fusion+palet+QSS), yüzen bildirim
(geometri sabit), tek denetçi, timeline trim/hover/snap/sabit sınıf renkleri,
sütun politikası + yerel saat, ayarlar rayı+arama, taşıma ikonları, tek başına
çekim, YTÜ logosu, boşluklar.

Kullanım geri bildirimi sonrası (aynı gün): **kayıt butonu hedef yokken devre
dışıydı — gerçek ZED'de kayıt alınamamasının sebebi buydu**; artık bağlıysa hep
etkin, katılımcı yoksa oluşturulup adı söyleniyor. Bildirim katmanı
`WA_TransparentForMouseEvents` yüzünden **tüm alt ağacı tıklanamaz** yapıyordu;
katman artık yalnız kartlar kadar. Projeler'e **proje silme** eklendi
(`ProjectDeletionService` + ad yazarak onay). Yakalama ekranı yeniden
tasarlandı: kaydırma yok, görüntü solda, konsol sağda, taşıma altta; hedef
kutusu kaldırıldı — kişi yalnız görüntüye tıklanarak seçilir.

**Açık:** kişi seçilmemiş sürüm için kare-anchor seçici yok; kurtarma yolu
"yeni sürüm hesapla" + dürüst açıklama. Gerçek ZED ile kayıt turu kullanıcı
tarafından tekrar denenmeli; mock ile doğrulandı.

## Bilinen açıklar (ölçümler 6Y'de)

- Bütçeler ölçüldü (6AD). **Gerçek ZED ile tam tur yok**; iki kişinin karıştığı
  kayıt mock ile üretilemedi.
- **`pytest tests/` dosya dosya çalıştırılmalı.** Studio stil sayfası
  uygulama geneli: eski GUI ölçümleri aynı süreçte etkilenir (fixture sıfırlar).
- **`offscreen`'de font ailesi yok**: yerleşim ölçümü orada anlamsız, gerçek
  `QT_QPA_PLATFORM=windows` gerekir (6Z).
- Canlı ZED doğrulaması eksik: 60 FPS, H264_LOSSLESS, native sayaç, çok kişi.
- SDK ilk model optimizasyonu dakikalar sürer (TaskRunner'da, GUI'yi bloklamaz);
  proxy video Windows uzun yolda açılamaz (6AC).
- `dataset_root` tercihi eski pytest yolunu gösterebilir; proje kilidi yok.

## Görsel kanıt

`python -m kinecapture.tools.ux_shots --output <klasör>`: gerçek
`QT_QPA_PLATFORM=windows`, büyütülmüş pencere, 18 görüntü; tek kullanımlık
kimlik/veri, mock backend. Ölçülen **1920×1009, DPR 1.0**; bildirim
öncesi/sonrası ana dikdörtgenler aynı (her koşuda basılır).

## Sonraki adım

Kişi kare-anchor seçici ve kişisiz sürüm kurtarma akışının tamamlanması; sonra
gerçek ZED turu ve uçtan uca başarılı kanonik paket.
