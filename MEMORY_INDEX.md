# MEMORY_INDEX — KineCapture Studio

Önce bu indeks; `MEMORY.md` yalnız hedefli okunur. Kod önceliklidir.

## Güncel faz · sürümler

Studio F0–F15 teslim edildi; 15 Eylül P0 açıkları 16 Eylül'de,
**kayıt→işleme→etiketleme zinciri 17 Eylül'de** kapatıldı, 18 Eylül'de gerçek
ZED ile doğrulandı. Faz geçmişi: `FAZ_PLANI_PYSIDE6_STUDIO.md` §7.
`python -m kinecapture` Studio, `--legacy-gui` eski. Veri silinmez.

Tam liste: `src/kinecapture/__init__.py`. app 0.11.0 · processing 1.1.0 ·
canonical annotation 1.1.0 · subject review 1.0.0 · canonical release 1.0.0 ·
studio theme tokens 1.1.0 · **subject association 1.2.0** · identity şema 1.

Ortam: `KineSynth` / Py 3.11.14, PySide6 6.10.1, numpy 2.4.6, opencv 4.12,
pyzed 5.4 / SDK 5.4.1. RTX 2060, i7-10750H, ~16 GB. **PyOpenGL numpy 2.x ile
uyumsuz — 3B yalnız Qt GL sınıfları.**

## Modül haritası (`src/kinecapture/`, ~43k satır)

| Paket | İş |
|---|---|
| `core/` | errors, ids, jsonio (atomik), paths (uzun yol), config, fingerprint |
| `domain/` `dataset/` | enums/models/project/labels; workspace, index, deletion, summary_index |
| `camera/` | `base` · `mock` · `zed` (pyzed yalnız burada, gecikmeli import) |
| `capture/` `preview/` `recording/` | `service`, `subject_lock`; CPU 2B pose; `take_writer`, `rgbd_archive` |
| `processing/` | **offline**: `jobs` `sources` `review` `annotations` `arrays` `summary` `thumbnails` `depth` `subject_review` |
| `playback/` `annotations/` `export/` `features/` `identity/` `visualization/` | proxy okuma; eski undo/autosave; atomik yayın; 31 özellik; SQLite+scrypt; `skeleton_spec` |
| `studio/` | **yeni arayüz**: `services/` `viewmodels/` `theme/` (Qt'siz) `views/` |
| `gui/` `tools/` | eski arayüz (`--legacy-gui`); verify_zed_topology, ux_shots… |

Durum: `DISCONNECTED→READY→PREVIEWING→RECORDING→STOPPING→REVIEWING`, `ERROR`.
## `MEMORY.md` bölüm dizini (satır no)

1–2 (18) politika · 3–4 (86) ortam · 5–6 (173) özellikler + 16 kalıcı karar ·
6B (294) etiketleme · 6C (393) özellik katmanı · 6D (600) **SVO2 depth'i geri
vermez** · 6E (790) kimlik · 6H–6I (1197/1289) silme, correctness · 6J–6K
(1505/1560) eklem kanıtı · 6P (1872) squat düz-bacak · 6S–6T (2071/2141) **SDK
depth alias** · 6V (2375) backend · 6Y–6AD (2580…3401) F0–F15 · 6AE 16 Eylül
GUI/UX · 6AF (3462) 17 Eylül zincir · **6AG (3580) 18 Eylül canlı ZED + veri
kalitesi** · 7–9 (2937/2964/2978) sınırlar · 10–12 (3228…) sorunlar, adımlar.

## 16–17 Eylül (ayrıntı §6AE, §6AF)

16 Eylül: etiketleme açılışı `opened` olayına bağlı; kayıt hedefi tek kaynakta;
kayıt modu profile giriyor; kayıt kabukta görünür (Ctrl+Shift+S). tokens 1.1.0,
`apply_application_theme`, yüzen bildirim, tek denetçi, timeline trim/snap, YTÜ
logosu, proje silme, kaydırmasız Yakalama. **Kayıt butonu hedef yokken devre
dışıydı** — ZED'de kayıt alınamamasının sebebi buydu.

17 Eylül, beş kusur üst üsteydi: (1) **yayımlama kullanılabilirliğe bakıyor** —
`BLOCKING_ISSUES` yalnız `source_empty`, `source_position_discontinuity`,
`review_proxy_desynchronised`; `is_published`/`published_runs`, `job.published`,
`blocking_issues`, `coverage`, CLI 0/1/2; (2) kayıt öncesi çapa ilk kareye
uygulanıyor; (3) vücut imzası yalnız `tracking_state == ok` karelerinden;
(4) imza vetosu yalnız çok bedenli karelerde, `contradiction_frames=3`;
(5) ölçülen kusur ile kayıp veri ayrıldı (`camera_timestamp_repeated`).
Sürümler `created_at` ile sıralanıyor; `QTabWidget::pane` ve `kcSurface`
padding; bildirim `bottom_reserve()` ile alt çubuğu boş bırakıyor.

## 18 Eylül canlı ZED turu (ayrıntı §6AG)

Üç gerçek kayıt, kullanıcı başında. **60 FPS H264_LOSSLESS HD720'de tutuyor,
kuyruk kaybı 0**; SDK her kayıtta son 1–3 kareyi SVO'ya yazmıyor (take PARTIAL,
hiçbir aşamayı engellemiyor). Kişi seçili kayıt uçtan uca çalıştı: 1370/1370
karede kişi, tek NaN yok, Sporcu sekmesinde yanıtsız aralık 0.

Kalıcı ZED bulguları: (1) uzuv boyları **simetrik rijit model çıktısı**,
antropometri değil; (2) **güven ısınmayı yakalamaz, kemik uzunluğu CV'si
yakalar** — ilk 6 kare yanlış, güven sabit; etiketleme ~10. kareden başlamalı;
(3) `joint_positions_2d` 3B'nin izdüşümü (geri yansıtma **0,00 px**) — veri
kendini doğruluyor, **tek bağımsız kontrol RGB videoya bindirmek**; (4) kaliteyi
kadraj/mesafe belirliyor: 2,48 m eksik kadrajda uyluk CV %6,91 / diz tabanı
103°, 3,02 m tam kadrajda **%0,21 / 52°**; (5) gürültü tabanı ayak bileği 3 mm,
eller 62–72 mm, diz açısı std **2,95°**.

Kişi seçimi **zorunlu**: çapa yoksa `_can_record()` reddediyor, sebebini hem
pencerede hem **görüntü üstünde** söylüyor (3 sn sonra sönen kart). Seçilen
kişinin çerçevesi çiziliyor; bildirim başlığı kendi satırını aldı.

## Bilinen açıklar

- **Kadrajda iki kişi senaryosu üretilemiyor** (kullanıcı tek başına). Kişi
  kilidinin çok kişili davranışı yalnız sentetik olarak test edildi.
- Kanonik export paketi uçtan uca doğrulanmadı. Kişi seçilmemiş sürüm için
  kare-anchor seçici yok: 17 Eylül'ün iki çapasız kaydı bekliyor.
- **Testler dosya dosya koşulmalı**; Studio stil sayfası uygulama geneli.
  `offscreen`'de font yok — yerleşim ölçümü orada anlamsız (6Z).
- `test_processing_pipeline.py` duraklat/sürdür ~1/3 koşuda takılıyor (eskiden
  beri). SDK ilk model optimizasyonu dakikalar sürer; proxy video Windows uzun
  yolda açılamaz (6AC). `dataset_root` eski yolu gösterebilir; proje kilidi yok.

## Görsel kanıt · sonraki adım

`python -m kinecapture.tools.ux_shots --output <klasör>`: gerçek
`QT_QPA_PLATFORM=windows`, büyütülmüş pencere (**1920×1009, DPR 1.0**), 18
görüntü, tek kullanımlık kimlik/veri, mock backend. Sonraki: kişi seçilmemiş
sürüm için kare-anchor seçici (17 Eylül'ün iki çapasız kaydı bekliyor), sonra
uçtan uca kanonik paket.
