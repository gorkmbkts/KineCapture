# MEMORY_INDEX — KineCapture Studio

Önce bu indeks; `MEMORY.md` yalnız hedefli okunur. Kod önceliklidir.

## Güncel faz · sürümler

Studio F0–F15 teslim edildi; 15 Eylül P0 açıkları 16 Eylül'de,
**kayıt→işleme→etiketleme zinciri 17 Eylül'de** kapatıldı (§6AF). Sekiz ekran
gerçek. Faz geçmişi: `FAZ_PLANI_PYSIDE6_STUDIO.md` §7. `python -m kinecapture`
Studio, `--legacy-gui` eski GUI. Veri silinmez; eski veri uyumluluğu aranmıyor.

Tam liste: `src/kinecapture/__init__.py`. app 0.11.0 · processing 1.1.0 ·
canonical annotation 1.1.0 · subject review 1.0.0 · canonical release 1.0.0 ·
studio theme tokens 1.1.0 · **subject association 1.2.0** · identity şema 1.

Ortam: `KineSynth` / Python 3.11.14, PySide6 6.10.1, numpy 2.4.6, opencv 4.12,
pyzed 5.4 / SDK 5.4.1. RTX 2060 6 GB, i7-10750H, ~16 GB. **PyOpenGL numpy 2.x
ile uyumsuz — 3B yalnız Qt GL sınıfları.**

## Modül haritası (`src/kinecapture/`, ~43k satır)

| Paket | İş |
|---|---|
| `core/` | errors, ids, jsonio (atomik), paths (uzun yol), config, fingerprint |
| `domain/` | enums, models, project, labels, arrays |
| `camera/` | `base` · `mock` · `zed` (pyzed yalnız burada, gecikmeli import) |
| `capture/` | `service` acquisition+writer; `subject_lock` |
| `preview/` `recording/` | LatestWorker, CPU 2B pose; `take_writer`, `rgbd_archive` |
| `processing/` | **offline**: `jobs` `sources` `review` `annotations` `arrays` `summary` `thumbnails` `depth` |
| `playback/` `annotations/` | `take_reader` + proxy; `repository` undo/autosave (eski) |
| `dataset/` | `workspace` · `index` · `deletion` · `summary_index` |
| `export/` `features/` | atomik yayın; 31 sürümlü özellik |
| `identity/` `visualization/` | SQLite+scrypt; `skeleton_spec` ZED tabloları |
| `studio/` | **yeni arayüz**: `services/` `viewmodels/` `theme/` (Qt'siz) `views/` |
| `gui/` `tools/` | eski arayüz (`--legacy-gui`); verify_zed_topology, ux_shots… |

Durum: `DISCONNECTED→READY→PREVIEWING→RECORDING→STOPPING→REVIEWING`, `ERROR`.

## `MEMORY.md` bölüm dizini (satır no)

1–2 (18) politika · 3–4 (86) ortam, ZED ölçümleri · 5–6 (173) özellikler +
16 kalıcı karar · 6B (294) etiketleme · 6C (393) özellik katmanı · 6D (600)
**SVO2 depth'i geri vermez** · 6E (790) kimlik · 6H–6I (1197/1289) silme,
correctness · 6J–6K (1505/1560) eklem kanıtı · 6P (1872) squat düz-bacak ·
6S–6T (2071/2141) **SDK depth alias hatası** · 6V (2375) backend · 6X (2546)
canlı ZED · 6Y–6AD (2580/2666/2748/2858/3305/3401) F0–F15 · 6AE 16 Eylül
GUI/UX · **6AF (3462) 17 Eylül kayıt→etiketleme zinciri** · 7–9
(2937/2964/2978) sınırlar, testler · 10–12 (3228/3249/3272) sorunlar, adımlar.

## 16 Eylül GUI/UX (ayrıntı §6AE)

Etiketleme açılışı `ReviewViewModel.opened` olayına bağlı; kayıt hedefi tek
kaynakta (`SessionService`/`WorkTarget`); kayıt modu backend profiline giriyor;
kayıt kabukta görünür, Ctrl+Shift+S ile durdurulur. Görsel: tokens 1.1.0,
`theming.apply_application_theme` (Fusion+palet+QSS), yüzen bildirim, tek
denetçi, timeline trim/hover/snap, YTÜ logosu. Aynı gün: **kayıt butonu hedef
yokken devre dışıydı** (ZED'de kayıt alınamama sebebi); bildirim katmanı
`WA_TransparentForMouseEvents` yüzünden tıklanamıyordu; Projeler'e proje
silme; Yakalama kaydırmasız, kişi görüntüye tıklanarak seçiliyor.

## 17 Eylül zincir turu (ayrıntı §6AF) — gerçek kayıtlarla

Beş kusur üst üsteydi; hepsi ölçülerek düzeltildi:
1. **Yayımlama artık kullanılabilirliğe bakıyor.** `BLOCKING_ISSUES` yalnız üç
   kod (`source_empty`, `source_position_discontinuity`,
   `review_proxy_desynchronised`). `is_published`/`published_runs`;
   `job.published`, `blocking_issues`, `coverage`. CLI: 0/1/2.
2. **Kayıt öncesi seçilen kişi** ilk kareye uygulanıyor
   (`subject_anchor_before_recording`, `offset_ms` yazılıyor).
3. **Vücut imzası yalnız `tracking_state == ok` karelerinden** ölçülüyor: ZED
   ısınırken 0,877 m / 7 segment, 17 ms sonra 1,740 m / 11 segment veriyor.
4. **ZED'in uzuv boyları duruşla değişiyor** (squat dibinde boy 1,709→1,064 m,
   uyluk %25). İmza vetosu artık yalnız karede birden fazla beden varken;
   tek karelik çelişki ilişkiyi bitirmiyor (`contradiction_frames=3`).
5. **Kayıtta ölçülen kusur ile kayıp veri ayrıldı.** Aynı mikrosaniyeli iki kare
   artık `camera_timestamp_repeated` (take'i düşürmez); SDK'nın SVO'ya yazmadığı
   kareler sayılıyor. İşlemede aynı mikrosaniyeli satırlar sırayla eşleşiyor.

Sonuç: squat 1641/1645, capture 522/522 karede kişi; ikisi de yayımlandı.
Ayrıca sürümler artık `created_at` ile üretim sırasına göre listeleniyor;
`QTabWidget::pane` ve `kcSurface` yüzeylerine padding; bildirim katmanı
sayfanın alt eylem çubuğunu (`bottom_reserve()`) boş bırakıyor.

## Bilinen açıklar

- **Gerçek ZED ile canlı tur yok** (kullanıcı onayı bekleniyor): 60 FPS,
  canlı iskelet, gerçek derinlik, çok kişi. Kanonik export paketi de
  doğrulanmadı. Kişi seçilmemiş sürüm için kare-anchor seçici yok.
- Studio stil sayfası uygulama geneli: eski GUI ölçümleri aynı süreçte
  etkilenir (fixture sıfırlar). `offscreen`'de font ailesi yok — yerleşim
  ölçümü orada anlamsız, `QT_QPA_PLATFORM=windows` gerekir (6Z).
- `test_processing_pipeline.py` duraklat/sürdür testi ~1/3 koşuda takılıyor
  (önceden beri; `processing/` bu turda o yönden değişmedi).
- SDK ilk model optimizasyonu dakikalar sürer; proxy video Windows uzun yolda
  açılamaz (6AC). `dataset_root` eski yolu gösterebilir; proje kilidi yok.

## Görsel kanıt · sonraki adım

`python -m kinecapture.tools.ux_shots --output <klasör>`: gerçek
`QT_QPA_PLATFORM=windows`, büyütülmüş pencere (ölçülen **1920×1009, DPR 1.0**),
18 görüntü, tek kullanımlık kimlik/veri, mock backend; bildirim öncesi/sonrası
ana dikdörtgenler her koşuda basılır. Sonraki: kullanıcı onayıyla gerçek ZED
turu, sonra kare-anchor kişi seçici ve uçtan uca kanonik paket.
