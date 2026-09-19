# F1 — Mevcut durum tespiti (2026-09-13)

> **Bu raporun izi:** [6Y hafıza kaydı](../memory/6y-6y-pyside6-arayuz-yeniden-yapimi-f0-hafiza-politikasi-f1-tespiti-2026-09.md) · [faz planı](FAZ_PLANI_PYSIDE6_STUDIO.md) · [Studio F0–F15](../../milestones/studio-f0-f15.md) · [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md)
>
> Tarihsel rapor. Güncel durum için [MEMORY_INDEX](../../../MEMORY_INDEX.md) kullanılır.


`CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md` Faz 1. **Bu turda üretim
kodu değiştirilmedi.** Yalnız `MEMORY_INDEX.md` (F0) eklendi ve `MEMORY.md`
kullanım politikası güncellendi.

Aşağıdaki her sayı bu makinede gerçekten çalıştırılarak elde edildi; tahmin
olanlar açıkça **TAHMİN** diye işaretlidir. Ortam: `KineSynth`,
Python 3.11.14, PySide6 6.10.1, `QT_QPA_PLATFORM=offscreen`,
RTX 2060 6 GB / i7-10750H / ~16 GB RAM.

---

## 0. Tek cümlelik durum

Yeni backend (`processing/`, `preview/`, minimum ham kayıt) çalışıyor ve CLI'dan
uçtan uca doğrulandı; **üretim PySide6 arayüzü bu backend'i hiç tanımıyor** —
Etiketleme yeni kayıtlarda boş açılıyor, Capture'da kişi seçimi ölü, iki ekran
hiç yok, ve mevcut zaman çizelgesi performans bütçesinin ~18 katı üstünde.

---

## 1. KIRIK — yeni akış arayüzden yürütülemiyor

### K1. Etiketleme ekranı yeni mimarideki kaydı açamıyor · **kanıtlandı**

Yeni varsayılan profille (`store_skeleton=False`, `store_proxy=False`,
`enable_depth=False`, HD720/60, `processing_status=awaiting_processing`) mock
backend üzerinden gerçek bir kayıt alındı ve mevcut `load_take()` yoluna
verildi:

```
take.state             : finalized
take.processing_status : awaiting_processing
frame_count            : 302
skeleton_format        : ''          <- yok
spec                   : None
toplam gövde sayısı    : 0           <- çizilecek iskelet yok
proxy video            : False · "Proxy video dosyası yok."
review_body_at(0)      : None
```

Kök neden: `playback/take_reader.py:677` `awaiting_processing` durumunda
`raw/rgbd/index.jsonl` dosyasını *iskelet akışı* gibi okuyor. O dosyada gövde
yok; sonuç 302 boş kare. `ReviewPage` (`gui/pages/review.py:662`)
`derived/processing/run_*` dizinine hiç bakmıyor ve `ReviewDataset`'i hiç
kullanmıyor. **Yeni kayıtlar arayüzden etiketlenemez.**

Aynı kayıt CLI'dan işlendiğinde sorun yok — yani eksik olan yalnız arayüz:

```
python -m kinecapture.processing <take>  ->  state=complete, 302 kare, 4.7 s
ReviewDataset(run_...)                   ->  0.11 s; joints (302,16,3),
   confidences, source_positions, camera_timestamps_ns, subject_present,
   joint_valid_mask, frame_valid_mask, delta_time_s, joint_angles_deg;
   proxy.mp4 302 kare okunabilir; anchor_at(10) canonical sınır veriyor
```

### K2. Capture'da kişi seçimi yeni profille ölü · **kanıtlandı (kod yolu)**

`CapturePage._video_clicked` → `CaptureService.select_subject_at_pixel` →
`packet.bodies`. Yeni profilde canlı body tracking kapalı olduğu için
`packet.bodies` her zaman boş; tıklama hiçbir zaman kişi bulamaz.

Yeni mimarinin doğru yolu olan `CaptureService.set_subject_anchor(...)` ve
`preview.pose.CpuPosePreview` **yalnız** `tools/live_validation.py` ve
`tools/capture_diagnostic.py` içinde kullanılıyor; `gui/` altında tek bir
referansı yok. Aynı sebeple Capture ekranındaki hafif 2B pose kaplaması ve
`Derinlik` görünümü ile 3B canlı iskelet paneli de artık hep boş.

### K3. İki ekran hiç yok

`gui/main_window.py:_PAGES` = dashboard · projects · participants · capture ·
review · dataset · export · settings. **Verileri Hesapla** ve **İşlenen
Videolar** yok; işleme başlatma/izleme/iptal/yeniden deneme yalnız komut
satırından yapılabiliyor. Ayarlar'da da `ProcessingConfig` (BODY formatı, model
seviyesi, depth modu, fitting, precision) için hiçbir alan yok.

### K4a. `test_raw_capture_fields.py` — 5 test kırmızı · **kanıtlandı**

Dosya dosya taramada bulundu; commit edilmemiş çalışma ağacında duruyor.

```
FAILED test_adapter_carries_every_verified_sdk_field
FAILED test_adapter_drops_a_field_the_body_format_does_not_produce
FAILED test_adapter_drops_a_wrong_shaped_field_instead_of_reshaping
FAILED test_adapter_maps_an_unknown_action_state_to_unknown
FAILED test_adapter_handles_a_body_with_no_action_state_attribute

AttributeError: 'object' object has no attribute 'ERROR_CODE'
  src/kinecapture/camera/zed.py:658  _check_retrieval
```

Sebep test tarafında: `tests/test_raw_capture_fields.py:210` `sl` yerine düz
`object()` veriyor, fakat 6V turunda `_retrieve_bodies` içine eklenen
`_check_retrieval(sl, status, product)` bütünlük kontrolü `sl.ERROR_CODE`
okuyor. Yani **uygulama davranışı değil, stub eskimiş** — ama testler bugün
kırmızı ve bu hâliyle adapter bütünlük kontrolü regresyona karşı korumasız.
Küçük ve kapalı bir düzeltme; F2'de kapatılmalı.

### K4. Tam test paketi tek süreçte tamamlanmıyor · **gözlem**

`pytest tests/` tek süreçte ~28 dakika boyunca bitmedi; süreç bu sürede
yalnız ~289 s CPU harcadı, yani hesaplamıyor, **bekliyordu**. Elle durduruldu.
Dosya dosya çalıştırıldığında aynı testler geçiyor — örneğin durduğu noktadaki
`test_export_labels.py` tek başına **25 passed / 38.17 s**. Neden
belirlenmedi (dosyalar arası fixture/event-loop etkileşimi olabilir).
`MEMORY.md` 6V aynı belirtiyi 11 Eylül'de de kaydetmiş. **"Bütün testler
geçiyor" denemez.** Dosya bazlı sonuçlar bölüm 5'te.

### K5. Uçtan uca self-test eski yolu doğruluyor

`python -m kinecapture --self-test` **geçiyor** (83 kare, playback, etiketleme,
ham RGB-D arşivi, export doğrulaması). Fakat bu akış canlı iskelet yazan *eski*
profili kullanıyor; Capture(raw-only) → `process_take` → `ReviewDataset`
zincirini doğrulayan bir self-test yok.

---

## 2. YAVAŞ — ölçülen değerler ve bütçeler

| Ölçüm | Hedef | **Ölçülen** | Durum |
|---|---|---|---|
| Timeline tam görünüm yeniden çizimi (60 dk / 60 FPS) | ≤ 16 ms | **292 ms** (p95 328) | ✗ ~18× |
| Timeline, 5 dk / 30 FPS | ≤ 16 ms | **323 ms** | ✗ |
| Timeline, 1000 kareye zoom | ≤ 16 ms | **84 ms** | ✗ ~5× |
| Scrub: rastgele kare + görüntüye çevirme | ≤ 50 ms | **8,6 ms** (p95 11,3) | ✓ |
| Sıralı oynatmada kare okuma | — | **0,7 ms** | ✓ |
| Soğuk açılış (import + `MainWindow` + `show`) | ≤ 3 s | **0,96 s** | ✓ |
| Veri Seti tablosu 1000 kayıt doldurma | takılma yok | **36 ms** / yenileme | ⚠ |
| `DatasetIndex` metadata taraması, 1000 kayıt | takılma yok | **650 ms** / yenileme | ✗ |
| 60 dk sürümün dizilerini açma (`arrays.npz`) | tembel | **0,73 s / 135 MB tamamı** | ✗ |
| Etiketleme açılışında iskelet akışı (20 000 kare, 1 gövde) | tembel | **5,95 s / 28,5 MB** | ✗ |

### Y1. Zaman çizelgesi — en büyük tek problem

`TimelineWidget.paintEvent` her boyamada bütün şeritleri sıfırdan çiziyor;
statik katman pixmap önbelleği yok, çok çözünürlüklü özet yok. Playhead bir
kare ilerlediğinde bütün şerit yeniden çiziliyor. cProfile (10 boyama):

```
0.204 s  numpy _clip            (38 550 çağrı)
0.176 s  _paint_availability    (10 çağrı)
0.163 s  _x_to_frame            (38 550 çağrı)
0.109 s  numpy getlimits.__init__ (77 100 çağrı)
0.040 s  _paint_confidence
```

Yani maliyet kare sayısından değil, **piksel sütunu başına Python + numpy
çağrısından** geliyor: `_paint_availability` ve `_paint_confidence` genişlik
kadar (~1540) sütunun her biri için `_x_to_frame` → `np.clip` çağırıyor. Bu
yüzden 5 dakikalık kayıtta da 60 dakikalıkta da ~300 ms.

### Y2. Etiketleme açılışı GUI thread'ini kilitliyor

`ReviewPage.open_take` → `load_take` → `load_skeleton_stream` senkron; bütün
kareler ve bütün gövdeler Python nesnesi olarak belleğe alınıyor. Ölçülen:

```
20 000 kare x 1 gövde (BODY_38)  dosya 67,5 MB  yükleme 5,95 s  RAM 28,5 MB
20 000 kare x 2 gövde            dosya 133 MB   yükleme 12,41 s RAM 51,4 MB
```

**TAHMİN (doğrusal ölçekleme):** 60 dk / 60 FPS = 216 000 kare →
**~64 s / ~308 MB** (tek gövde), **~134 s / ~556 MB** (iki gövde). Bu tahmin
gerçek 60 dakikalık kayıtla doğrulanmadı; ama ölçülen kare başına maliyet
(0,30 ms, 1,4 kB) gerçek. Önceki sürümde "etiketleme ekranı bilgisayarı
zorluyordu" şikâyetinin en olası kaynağı budur.

### Y3. Diziler bellek eşlemeli değil

`processing/jobs.py` `np.savez_compressed` yazıyor, `ReviewDataset.arrays()`
tamamını RAM'e açıyor. 60 dk / 60 FPS / BODY_38 için ölçüldü:

```
savez_compressed yazma : 4,96 s, dosya 121 MB
arrays() ile açma      : 0,73 s, 135 MB tamamı bellekte
.npy memmap + 600 kare : 7,5 ms, 0,27 MB   <- karşılaştırma
```

### Y4. Liste ve indeks

- `DatasetIndex._metadata_signature` her yenilemede `participants/` altında
  `rglob("*.json")` + her dosyaya `stat()` yapıyor — **önbellek isabet etse
  bile**. Ölçüldü: 100 kayıt / 200 dosya = 65 ms; 1000 kayıt / 2000 dosya =
  **650 ms**, GUI thread'inde.
- `DatasetPage._fill_table` `QTableWidget` + hücre başına `QTableWidgetItem`
  kullanıyor (sanallaştırma yok). Ölçüldü: 1000 satır × 9 sütun = 36 ms
  (9000 nesne), 5000 satır = 183 ms. Her filtre değişiminde yeniden kuruluyor.

### Y5. Kare başına üç kopya

`ProxyVideoReader.read_at` → `cv2.cvtColor` (kopya 1) →
`np.ascontiguousarray` (kopya 2) → `gui/converters.rgb_to_qimage` →
`QImage.copy()` (kopya 3). Önceden ayrılmış tampon yok. Scrub bütçesi yine de
tutuyor (8,6 ms), yani bu **öncelikli değil** ama 60 FPS oynatmada gereksiz
çöp üretiyor.

### Ölçüm notu — yanlış alarm vermeyelim

- Proxy video `mp4v` ile yazılıyor ve sentetik **gürültü** görüntüsünde 20 dk
  için 1,1 GB çıktı. Gürültü her codec için en kötü durumdur; gerçek görüntüde
  bu sayı çok daha küçük olacaktır. **Gerçek içerikle ölçülmedi**, bu yüzden
  "proxy çok büyük" diye bir bulgu yazmıyorum — yalnız codec/kalite seçiminin
  hiç doğrulanmadığını not ediyorum.
- Bütün ölçümler `offscreen` raster platformunda. Gerçek `windows` platformunda
  mutlak değerler değişir; ancak Y1'in maliyeti Python/numpy tarafında olduğu
  için sıralama değişmez.

---

## 3. EKSİK — promptun istediği, kodda olmayan

### Mimari ve tema
- `viewmodels/` ve `services/` katmanları **yok**; durum ve iş mantığı doğrudan
  sayfa sınıflarında (`review.py` 1624, `capture.py` 1386, `export.py` 1014
  satır). Qt-bağımsızlık testi de yok.
- `tokens.json` **yok**; `gui/theme.py` içinde iki adet elle yazılmış `Theme`
  dataclass'ı var. QSS üretici yok.
- İkonlar elle yazılmış SVG path'leri (`gui/icons.py`), serbest lisanslı bir set
  değil.
- Pencere boyutu / panel genişliği / açık sekme **kalıcı saklanmıyor**
  (`QSettings`, `saveGeometry` kullanımı yok).

### Ekran ve yetenek
- **Verileri Hesapla** ve **İşlenen Videolar** ekranları yok (K3).
- 3B görünüm `QPainter` ile (`skeleton_view.py`), `QOpenGLWidget` değil; ve
  Etiketleme'deki 3B görünüm offline veriyle beslenmiyor.
- Yardımcı pencerelerden yalnız `info_window.py` var. Log Konsolu, Tanılama,
  Cihaz Bilgisi, Kaynak Denetimi, Köken, Ham Parametreler **yok**
  (veri kaynağı `core/diagnostics.py` içinde mevcut, yüzeyi yok).
- Ayarlar'da "İşleme" grubu yok (K3).
- Eski `segments.json` → canonical sidecar için **açık dönüştürme yolu yok**;
  `ReviewDataset.save_annotations` docstring'i "asla örtük göç yok" diyor, ama
  açık göç de yok.

### Backend'de kapatılması gereken (promptun Bölüm 9 tahminleri — hepsi doğru çıktı)
- `.npy` **memmap** seçeneği yok (`savez_compressed`).
- Timeline için **çok çözünürlüklü özet** üretimi yok (`decimat*` geçmiyor).
- **Thumbnail** üretimi yok (`thumbnail` geçmiyor).
- 3B görünüm için offline **derinliğe erişim yok**: `process_take` `depth/*.kcd`
  yazıyor fakat `ReviewDataset`'te derinlik okuyucu yok.
- İş kuyruğunda **duraklatma** ve **tahmini süre** alanı yok. `job.json`
  `state`/`frames_processed`/`source_frames_declared`/`elapsed_s`/`issues`
  taşıyor (ilerleme için yeterli); iptal `threading.Event` ile, restart var.
- **Özet indeksi yok** — her liste yenilemesi klasörleri tarıyor (Y4).
- `ReviewDataset.position_of_anchor` her çağrıda tüm `source_map`'i doğrusal
  tarıyor; aralık başına 2, hata aralığı başına 2 çağrı ile etiket sayısı × kare
  sayısı maliyeti çıkar. Sözlük indeksi gerekiyor.

---

## 4. ÖNCELİKLENDİRİLMİŞ LİSTE (önerilen sıra)

| # | İş | Neden bu sırada | Faz |
|---|---|---|---|
| 1 | Katman ayrımı + `tokens.json` + QSS üretici + kabuk/gezinme | Sonraki her ekran bunun üstüne yazılacak; sonra yapılırsa hepsi yeniden yazılır | F2 |
| 2 | **Timeline'ı yeniden yaz**: çok çözünürlüklü özet + statik katman pixmap önbelleği + piksel döngüsünü vektörleştirme | Tek başına en büyük performans açığı (292 ms → ≤16 ms) | F7 (altyapısı F2'de) |
| 3 | **Etiketleme'yi `ReviewDataset`'e bağla**; `load_take` yerine sürüm seçimi | K1 — yeni kayıtlar bugün etiketlenemiyor | F7 |
| 4 | Backend: `.npy` memmap + timeline özeti + thumbnail + depth erişimi + anchor indeks sözlüğü + özet indeksi | 2 ve 3 bunlara dayanıyor; hepsi **toplamsal**, ham veriye dokunmaz, processing sürümünü 1.1.0'a çıkarır | F5–F7 öncesi |
| 5 | **Verileri Hesapla** ekranı (başlat/iptal/yeniden dene, gerçek ilerleme) | İşleme olmadan 3 numaranın girdisi üretilemez | F5 |
| 6 | **Capture**: hafif 2B pose kaplaması + `set_subject_anchor` ile kişi seçimi | K2 — kişi seçimi ölü; offline eşleme anchor'a bağlı | F4 |
| 7 | **İşlenen Videolar** ekranı + thumbnail önbelleği + sürüm karşılaştırma | Etiketlemeye giriş noktası | F6 |
| 8 | Listeleri sanallaştır (`QAbstractItemModel`) + indeks taramasını thread'e ve özet dosyasına al | Y4/Y5; 1000 kayıtta 650 ms + 36 ms | F3 |
| 9 | 3B görünüm `QOpenGLWidget` + offline veriyle | Promptun açıkça eksik dediği ekran | F8 |
| 10 | Sporcu seçimi / belirsiz aralık onayı | 6 ve 3 tamamlanmadan anlamlı değil | F9 |
| 11 | Yardımcı pencereler, Ayarlar "İşleme" grubu, `segments.json` açık dönüştürme | Ana akışı bloklamıyor | F11 / F9 |
| 12 | `test_raw_capture_fields.py` stub'ını onar (K4a) + tam paketin tek süreçte bitmesi (K4) | Her fazın "bitti" ölçütü buna bağlı; K4a küçük ve hemen yapılabilir | K4a → F2, K4 → F2'de araştır / F12'de kapat |

**Kritik yol:** 1 → 4 → 2+3 → 5 → 6 → 7. Yani F2'den sonra, F7'nin (etiketleme)
ihtiyaç duyduğu backend eklerini F5'ten önce yapmak gerekiyor; aksi hâlde
timeline ve 3B görünüm ölçülebilir bütçeye hiç giremez.

---

## 5. Bu turda gerçekten çalıştırılanlar

| Komut / ölçüm | Sonuç |
|---|---|
| `python -m kinecapture --self-test` | **exit 0** — 83 kare, playback, etiketleme, ham RGB-D, export doğrulaması geçti |
| `capture_diagnostic --backend mock --seconds 5` | finalized take, kaynak 60,0 FPS, kuyruk kaybı 0, `awaiting_processing` |
| `python -m kinecapture.processing <take>` | **complete**, 302 kare, 4,7 s, `issues: []` |
| `ReviewDataset(run_...)` | 0,11 s; 9 dizi, proxy 302 kare, canonical anchor çalışıyor |
| `load_take()` aynı ham kayıtta | 302 kare, **0 gövde**, spec yok, proxy yok |
| Timeline boyama ölçümü (4 senaryo + zoom) | 84–323 ms; cProfile ile darboğaz bulundu |
| Scrub ölçümü (3 dk ve 20 dk proxy) | 7,9–8,6 ms medyan |
| Soğuk açılış ölçümü | 959 ms |
| `arrays.npz` / `.npy` memmap karşılaştırması | 0,73 s·135 MB vs 7,5 ms·0,27 MB |
| `load_skeleton_stream` ölçümü | 5,95 s / 20 000 kare / 1 gövde |
| `DatasetIndex` tarama deseni ölçümü | 650 ms / 1000 kayıt |
| `QTableWidget` doldurma ölçümü | 36 ms / 1000 satır |
| `pytest tests/` tek süreçte | **tamamlanmadı** (~28 dk, ~289 s CPU, elle durduruldu) |
| `pytest` dosya dosya (39 dosyanın tamamı) | **1 dosya kırmızı** (`test_raw_capture_fields.py`, 5 test), diğer 38 dosya yeşil |

Dosya bazlı sonuçlar (hepsi `QT_QPA_PLATFORM=offscreen`, `KineSynth`;
süre saniye):

```
annotations             38  56 P   export_joint_evidence   19  14 P   packaging            12   6 P
auth_gui                 9  13 P   export_labels           38  25 P   processing_pipeline   5  12 P
capture                  3  30 P   features                 2  42 P   project_deletion      5  24 P
capture_architecture     3   8 P   gui                      6  25 P   project_deletion_gui  3   9 P
capture_subject_gui     21  31 P   gui_painting             5  43 P   raw_capture_fields    2  ** 5 FAILED **
continuous_activity     22  31 P   gui_viewports           13  79 P   recording_boundaries  2   3 P
domain                   2  47 P   identity                 5  19 P   review_flow          52  33 P
environment              3  10 P   joint_annotation_gui     9  51 P   rgbd_archive          6  21 P
export                  13  22 P   joint_evidence           9  27 P   shell_chrome_gui     13  16 P
export_features         19  28 P   label_dialog_class_...   2   2 P   storage               4  23 P
export_gui               8  32 P   launcher                 3   4 P   subject_lock          3  22 P
                                   live_validation          2   1 P   timeline_preview     19  16 P
                                   nav_logo                 2  13 P   user_state            2   5 P
                                   orphan_record_gui        4  12 P   zed_adapter           2  22 P
```

Toplam dosya bazlı süre ≈ 6 dk; aynı testler tek süreçte 28 dakikada bitmedi
(K4). **Değişen kaynak kodu yok**, gerçek
kullanıcı verisine dokunulmadı; bütün geçici çıktı
`%LOCALAPPDATA%\Temp\kcf1*` ve oturum scratchpad'i altında.

---

## 6. Onay bekleyen sorular

1. **Öncelik sırası** yukarıdaki gibi kabul mü? Özellikle "backend eklerini
   (madde 4) F5'ten önce yapmak" kararı promptun faz sırasını bir adım
   değiştiriyor.
2. **Backend'e eklenecekler** (promptun Bölüm 9 kuralı gereği bildiriyorum):
   `arrays.npz` yanına opsiyonel `.npy` memmap dizileri; `summary.npz` timeline
   özeti; `thumbs/` küçük görüntüler; `ReviewDataset`'e derinlik ve anchor
   indeks erişimi; proje kökünde yeniden üretilebilir bir **türetilmiş** özet
   indeksi. Hepsi toplamsaldır, ham veriye dokunmaz, mevcut dosya adlarını
   değiştirmez; `PROCESSING_SCHEMA_VERSION` 1.0.0 → **1.1.0** olur. Onaylıyor
   musunuz?
3. Eski `segments.json` kayıtları için **açık dönüştürme** yolu bu görev
   kapsamında mı, yoksa "eski kayıtlar eski ekranda kalsın" mı?
