---
type: report
status: current
created: 2026-09-19
updated: 2026-09-19
tags:
  - studio
  - gui
  - validation
  - measurement
---

# Studio GUI iyileştirmesi — çalıştırılan doğrulamalar

> 20 Eylül ek notu: Bu rapordaki çalıştırılmış kontroller tarihsel kanıt olarak
> korunur. Bunlardan çıkarılan genel GUI kabul/kapsam kapanışı `superseded`:
> kullanıcı deneyimi açıkları yeniden üretildi. [Yeni denetim ve sınırlar](../audits/studio-gui-acceptance-audit-2026-09-20.md).

Yalnız **gerçekten çalıştırılan** kontroller ve ölçümler. Tasarım onayı ve
plan kararları burada kanıt sayılmaz; onlar
[plan dosyasında](../plans/studio-gui-refinement-implementation.md) ve
[tasarım notunda](../decisions/studio-gui-refinement-2026-09-19.md).

Kanıt düzeyi ayrımı: `verified` (bu ortamda çalıştırıldı) ·
`observed` (gözlendi, tekrarlanmadı) · `doğrulanmadı` (çalıştırılamadı).

## Ortam

| | |
|---|---|
| Python | 3.11.14 (`KineSynth`) |
| PySide6 | 6.10.1 |
| numpy | 2.4.6 |
| OpenCV | 4.12.0 |
| pyzed | 5.4 (SDK 5.4.1) |
| Qt platformu | ölçümlerde `QT_QPA_PLATFORM=windows` (gerçek pencere) |
| Tarih | 2026-09-19 |

## 1. Başlangıç ölçümü (değişiklik öncesi)

`verified`. Gerçek pencere, 1600×900, DPR 1.0, boş geçici proje.

| Ölçüm | Değer |
|---|---|
| `build_window` | 1304.5 ms |
| İlk `show()` + yerleşme | 741.8 ms |
| `minimumSize` | 1120 × 700 |
| Etiketleme'ye **ilk** geçiş | 1563.7 ms |
| Etiketleme'ye tekrar geçiş (×3) | 153.0 / 154.4 / 154.1 ms (150 ms'i ölçüm beklemesi) |
| Açılışta kurulan sayfa sayısı | 1 (`projects`) |

### 1.1 `LOAD-01` kök nedeni — `verified`

| | |
|---|---|
| `winId` (Etiketleme öncesi) | 330866 |
| `winId` (ilk geçişten sonra) | 396402 |
| Native pencere yeniden oluşturuldu | **Evet** |
| Tekrarlanan geçişlerde `winId` | 396402 (sabit) |
| Geçiş sırasında `isVisible()` örnekleri | 83 örneğin tamamı `True` |
| Pencere geometrisi | geçiş öncesi/sonrası aynı (160, 35, 1600, 900) |

**Yorum:** Belirti, ilk `QOpenGLWidget`'in (ReviewPage içindeki
`Skeleton3DView`) zaten gösterilmiş üst pencereye eklenmesiyle Qt'nin native
pencereyi yeniden oluşturmasıdır. `isVisible()` Python tarafında `True`
kalıyor; kaybolma pencere sunucusu seviyesinde olduğu için widget bayrağıyla
görülmüyor — bu yüzden ölçüt `winId` değişimidir.

**Sınır:** Kullanıcının "her geçişte" tarifi bu koşuda **tekrarlanmadı**;
ölçümde yalnız ilk geçişte oluşuyor. `observed` olarak ayrı tutuluyor.

### 1.2 `LOAD-02` kök nedeni — `verified`

Gerçek sürüm: `run_61ef0f7cf0fb42e3`, 1370 kare, 60 FPS, `zed_body_38`,
209 dosya / 2.70 GB. Okuma-yalnız; kullanıcı verisine yazılmadı.

| Adım | Süre |
|---|---|
| `ReviewSession.open` | **6793.6 ms** |
| — içinde `verify_checksum_manifest` | **6772.8 ms** |
| — `source_map.jsonl` ayrıştırma | 6.7 ms |
| `video` uygunluk (ilk decode açılışı) | 133.2 ms |
| `frame(0)` | 23.6 ms |
| `frame(mid)` seek | 4.2 ms |
| `joints_3d(0)` | 3.5 ms |
| `joints_3d_window(0, 300)` | 0.3 ms |
| `load_annotations` | 0.6 ms |
| GUI thread toplamı (`_after_open` yolu) | ≈ 165 ms |

**Yorum:** Yükleme süresinin %99,7'si checksum doğrulaması. Worker thread'de
çalışıyor, yani donma değil; asıl kusur **ilerleme bilgisi olmaması** ve
busy'nin `_attach`/`opened` öncesinde kapanması. Hash'lenen bayt / toplam bayt
bilindiği için gerçek yüzde ve ETA üretilebilir.

### 1.3 `NOTICE-01` kök nedeni — `verified`

| | |
|---|---|
| Toast katmanı geometrisi | (1184, 671, 400, 121) |
| Toast merkezinde `childAt` (sayfa değişimi **öncesi**) | `Toast` |
| Toast merkezinde `childAt` (sayfa değişimi **sonrası**) | `QWidget` (sayfa) |
| `stack` çocuk sırası | `ProjectsPage`, `ReviewPage`, `ToastLayer`, `LibraryPage` |

**Yorum:** `ToastLayer`, `QStackedWidget`'in kardeş çocuğudur.
`QStackedLayout::setCurrentIndex` yeni sayfayı `raise()` eder ve katmanın
üstüne çıkarır. `show_message` içindeki tek seferlik `raise_()` sonraki sayfa
geçişinde geçersiz kalır. Bu, "bildirimler tabloların arkasında kalıyor,
Kapat/Ayrıntılar tıklanamıyor" şikâyetinin doğrudan karşılığıdır.

### 1.4 ZED zemin tespiti API'si — `verified` (yalnız API varlığı)

`pyzed` 5.4 üstünde doğrulandı:

- `sl.Camera.find_floor_plane(py_plane, reset_tracking_floor_frame,
  floor_height_prior=nan, world_orientation_prior=None,
  floor_height_prior_tolerance=nan) -> ERROR_CODE` mevcut.
- `sl.Plane`: `get_plane_equation`, `get_normal`, `get_pose`, `get_center`,
  `get_bounds`, `get_extents`, `type` mevcut.
- İşleme hattı SVO replay'inde zaten `enable_positional_tracking` çağırıyor
  (`camera/zed.py:351`), yani düzlem tespitinin gerektirdiği koşul sağlanıyor.

**Sınır:** Gerçek SVO üzerinde `find_floor_plane` **çalıştırılmadı**.
`doğrulanmadı`.

## 2. Faz doğrulamaları

### 2.1 Kök nedenlerin kapanışı — `verified`

Üçü de **ölçülerek** kapandı; "bir `raise_` çağrısı var" gibi dolaylı kanıt
kullanılmadı.

| Belirti | Ölçüt | Önce | Sonra |
|---|---|---|---|
| `LOAD-01` native pencere yeniden oluşuyor | `winId` değişimi | 330866 → 396402 | **değişmiyor** |
| `LOAD-01` ilk Etiketleme geçişi | ms | 1563.7 | **1069** |
| `LOAD-02` açılışta ilerleme yok | gerçek bayt sayacı | yok | 210 okuma / 2 703 157 059 bayt |
| `LOAD-02` ETA doğruluğu | %50'de tahmin vs gerçek | — | 7.10 s / 7.19 s (**%1.5 hata**) |

`LOAD-02` satırları F7'de **2.70 GB**'lık bir sürümle ölçüldü. O sürüm bu
denetim sırasında diskte yoktu; §2.4'teki performans tablosu bu yüzden elde
bulunan **88 MB**'lık sürümle alındı. İki ölçüm farklı kayıtlardır ve
birbirinin yerine okunmamalıdır.
| `NOTICE-01` toast sayfa arkasında | merkezinde `childAt` | sayfa (`QWidget`) | **toast katmanı** |

`LOAD-01` düzeltmesi: `show()` öncesinde 1×1, `WA_DontShowOnScreen` bir
`QOpenGLWidget` (`kcGlPrimer`) kuruluyor. Üç yollu deney yapıldı: primer yok →
yeniden oluşuyor; gizli primer → oluşmuyor; görünür primer → oluşmuyor. Gizli
olan seçildi.

### 2.2 Bildirim katmanı, altı ekran × iki tema — `verified`

`QT_QPA_PLATFORM=windows`, gerçek pencere, sürüm açık, 3B çizimden sonra.
Her ekranda bir bildirim gösterilip kartın **kendi merkezinde** `childAt`
soruldu:

| Tema | Ekran | Katman görünür | Merkez isabeti toast içinde |
|---|---|---|---|
| dark | Yakalama · Etiketleme · Dışa Aktarım · Veri Seti | evet | **evet** (4/4) |
| light | Yakalama · Etiketleme · Dışa Aktarım · Veri Seti | evet | **evet** (4/4) |

Bu, `NOTICE-02`'nin sorduğu tam soru: bildirim tüm sayfalarda, tekrarlanan
geçişten ve 3B kompozisyondan sonra da **tıklanabilir** kalıyor.

### 2.3 Yerleşim kabulü — `verified`

`QT_QPA_PLATFORM=windows`, 251 font ailesi yüklü (offscreen'de 0).
Altı ekran × üç boyut × üç ölçek. Kırpılma ölçütü: sarmalanan etiketler için
`heightForWidth(genişlik)`, diğerleri için `sizeHint` (2 px pay).

| Ölçek | DPR | Kırpılan denetim | Yatay kayan panel |
|---|---|---|---|
| %100 | 1.0 | **0** | 3 × `QTableView`, 1–2 px |
| %125 | 1.25 | **0** | 3 × `QTableView`, 1–2 px |
| %150 | 1.5 | **0** | 5 × `QTableView`, 1 px |

Pencere `minimumSizeHint` 1129 × 672. Bu tablo §2.4b'deki iki düzeltmeden
**sonraki** durumdur; öncesinde Yakalama ekranı %150'de sığmıyordu.

1–2 pikselin kaynağı `ResizeToContents` + `stretchLastSection` yuvarlaması;
okunabilirliği etkilemiyor, kusur olarak sayılmadı ama ölçüm burada duruyor.

**1120×700'de Etiketleme ekranı** (en dar kabul boyutu):

| | |
|---|---|
| Görüntü · 3B · panel · timeline | dördü de görünür |
| Görüntü | 462 × 258 |
| 3B | 260 × 258 |
| Panel | 347 px |
| Timeline | 202 px |
| Araç çubuğu taşması | hayır — Gez/hareket/hata ve oynat görünür |
| Pencere `minimumSizeHint` | 1129 × 672 |

### 2.4 Performans — önce/sonra — `verified`

Gerçek pencere, 1600×900, gerçek sürüm (`run_9ef0826515344e72`, 1231 kare,
88 MB, `ux14` projesi, **okuma-yalnız**).

| Ölçüm | Önce | Sonra | Bütçe |
|---|---|---|---|
| `build_window` | 1304.5 ms | 1320.8 ms | — |
| İlk `show()` | 741.8 ms | 653.9 ms | — |
| Etiketleme'ye **ilk** geçiş | 1563.7 ms | **1069 ms** | — |
| Sürüm açma (88 MB) | — | 0.57 s | — |
| İlk kullanılabilir ekran | — | 0.64 s | — |
| 3B çizim (tam iskelet) medyan | — | **0.78 ms** | 8 ms |
| 3B çizim p95 / max | — | 1.06 / 1.27 ms | 8 ms |
| Kare arama (seek) | — | 9.71 ms | 16.7 ms (60 FPS) |
| Kamera preset yolculuğu | — | 1.50 s (×3) | 1.5 s hedef |
| Hareket azaltılmış geçiş | — | **0.00 s** (anında) | — |
| Eklem seçme testi | — | 0.161 ms | — |
| 8 sayfa döngüsü | — | 1.64 s | — |
| RSS (imzadan sonra → son) | — | 242 → 299 MB | — |

**Doğru yerde iş yükü** (`PERF-02`):

| Kontrol | Sonuç |
|---|---|
| Gizli sayfada oynatma timer'ı | **durmuş** |
| Gizli sayfada kamera timer'ı | **durmuş** |
| Kamera varışta timer | **duruyor** |
| 8 sayfa döngüsünde widget artışı | **0** |
| 8 sayfa döngüsünde RSS artışı | **−0.1 MB** |
| Döngüden sonra sürüm hâlâ açık | evet (yeniden açılmıyor) |
| Eklem seçme varsayılan | **kapalı** |
| Zemin tespiti arayüzde | yok — yalnız `processing/floor.py` |

**Ölçülemeyen:** GPU kullanımı. Tahmin edilmedi.

**Kanıt sınırı — 3B çizim sayıları.** Elde bulunan tek tam sürüm
`needs_subject_selection` ile işlenmiş; bütün eklemleri NaN. Ölçülen sahnede
gerçek iskelet yok. Bu yüzden iki ayrı sayı raporlanıyor: boş sahne
(medyan 0.59 ms) ve **sentetik koordinatlı tam iskelet** (34 eklem, 32 kemik;
medyan 0.78 ms). Widget, pencere, sürücü, shader ve kemik şeritleri gerçek;
yalnız koordinatlar üretilmiş. Gerçek eklem verisiyle çizim ölçümü
`doğrulanmadı`.

### 2.4b Gerçek platformun bulduğu iki hata — `verified`

Her ikisi de `offscreen`'de **yeşildi** ve yalnız `QT_QPA_PLATFORM=windows`
altında düştü. İkisi de gerçek kusurdu, test uyarlaması değil.

**(1) Ayrılmış genişlik yanlış fontta ölçülüyordu.** `_Metric._value`
genişlik tabanını `__init__` içinde `QFontMetrics(self._value.font())` ile
alıyordu. Tema stil sayfası uygulamaya widget'lar kurulduktan **sonra**
veriliyor, yani ölçüm varsayılan yüzden alınıyordu: `preview_loss` için taban
**24 px** çıkıyor, dört mono rakam **28 px** istiyordu. Sayaç dört haneye
çıktığında yanındaki okuma **4 px** kayıyordu — `CAP-02`'nin yasakladığı şeyin
ta kendisi. Offscreen bunu hiç göremez: font veritabanı yokken bütün glifler
aynı genişlikte, yani yanlış ölçüm ile doğrusu aynı sayıyı veriyor.

Düzeltme: taban `FontChange` / `StyleChange` / `ApplicationFontChange`
olaylarında **yeniden** ölçülüyor. Aynı tuzak geri sayım yuvasında da vardı
(`setFixedWidth`, yani kaydırmak yerine **kırpıyordu**); orada `showEvent`
de eklendi, çünkü sayfa düzeyindeki font olayı ayrıca cilalanan bir çocuğa
her zaman ulaşmıyor. `tests/test_studio_capture_row.py` içine sınıfın
tamamını koruyan iki test yazıldı.

**(2) Yakalama ekranı %150'de dizüstüne sığmıyordu.** `minimumSizeHint`
**1053 px**, 1366×768'in %150'sinde kullanılabilir alan **911 px**.
(1)'in düzeltilmesi doğru — ve daha geniş — tabanları verdiği için sınır
biraz daha zorlanmıştı. Satırda genişliğinden vazgeçebilecek tek şey kontrol
olmayan tek şeydi: klavye kısayolu hatırlatması (165 px). `ElidedLabel` +
`QSizePolicy.Ignored` yapıldı, tam metin tooltip'te duruyor. Sonuç:
**1053 → 892 px**, 911'in altında.

Bu iki düzeltmeden sonra 6 ekran × 3 boyut × %100/%150 turunda **kırpılan
denetim 0**.

### 2.5 Kabul koşusu — `verified`

Proje kuralı gereği **dosya dosya** (tek süreçte tam pytest bitmiyor).

| Koşu | Sonuç |
|---|---|
| `QT_QPA_PLATFORM=offscreen`, 84 dosya (ilk tur) | 82/83 — iki gerçek hata bulundu |
| `QT_QPA_PLATFORM=windows`, yerleşime duyarlı 18 dosya | **18/18 yeşil**, 1399 s |
| `QT_QPA_PLATFORM=offscreen`, 84 dosya (son tur) | **83/84**, 2146 s |

Son turdaki tek düşüş `test_processing_pipeline.py` içindeki
`test_cancelling_a_paused_job_does_not_wait_for_a_resume`. Bu, test ve ölçüm
notunda **bu çalışmalardan önce** kayıtlı olan aralıklı duraklat/sürdür
zamanlama yarışıdır. Protokolün istediği ayrım yapıldı: izole koşuda
**3/3 geçti**. Bu turdaki değişikliklerle ilgisi yok.

İlk offscreen turunda 1 dosya düştü: `test_processing_pipeline.py`
`job["schema_version"] == "1.1.0"` sabitine bağlıydı, F12 şemayı **1.2.0**'a
taşımıştı. Test sabite değil `PROCESSING_SCHEMA_VERSION` **sabitine** bağlandı
ve `floor_plane` bloğunun varlığı da doğrulandı — şema numarasını değiştiren
şey buydu.

**Bu turda yazılan yeni test dosyaları:**

| Dosya | Test | Neyi koruyor |
|---|---|---|
| `test_studio_visual_language.py` | 72 | token tek kaynak, `views/` içinde düz renk yok |
| `test_studio_auth_gui.py` | 23 | giriş ekranı, marka fontu, hata durumu |
| `test_studio_capture_row.py` | 20 | tek satır kontrol sırası, kayıt durumları |
| `test_studio_processing_layout.py` | 15 | kaynak/kuyruk bölünmesi, arama+filtre birlikte |
| `test_studio_library_layout.py` | 15 | kapak en-boy koruma, eksik boyut "0 B" değil |
| `test_studio_review_loading.py` | 17 | yükleme aşamaları, iptal, ETA |
| `test_studio_stage_layout.py` | 21 | üç bant geometrisi (aritmetik) |
| `test_studio_review_bands.py` | 18 | bantların bağlanması, araç kuralları |
| `test_studio_skeleton_view.py` | 41 | anatomik renk, seçim, kamera |
| `test_processing_floor.py` | 17 | zemin bloğu, üç durum ayrımı |
| `test_studio_label_panel.py` | **22** | ikon şeridi, tek tık, sınıf-eklem kalıcılığı |
| `test_studio_export_layout.py` | **10** | altı durum, bayatlama, dar okuma |
| `test_studio_dataset_actions.py` | **11** | engelleyici eylemleri sürümü taşıyor |
| `test_studio_workload.py` | **13** | timer'lar, mesh önbelleği, sızıntı |

`test_studio_label_panel.py` sonradan 4 döngülü oynatma testiyle **26**'ya,
`test_studio_capture_row.py` iki font-genişliği testiyle **22**'ye çıktı.

## 3. Kanıt sınırları

- **Canlı ZED kamerasıyla kayıt ölçümü** bu oturumda yapılmadı. Kayıt kaybı
  (`recording_loss` / `preview_loss`) önce/sonra karşılaştırması `doğrulanmadı`.
- **GPU kullanımı ölçülmedi**; tahminle doldurulmadı.
- **Gerçek eklem verisiyle 3B çizim** ölçülemedi; elde bulunan tek tam sürüm
  `needs_subject_selection`. Sentetik koordinatlı ölçüm ayrı etiketlendi.
- **Hareketli kamerayla çekilmiş SVO** yok; zemin bloğunun `camera_moved`
  dönüşüm yolu `doğrulanmadı`.
- **MSAA** sürücüde alınamıyor: `setSamples(4)` isteniyor, `samples: 0`
  veriliyor. Kenar yumuşatma `fwidth` tabanlı analitik yolla yapıldı.
- Kullanıcının gerçek projesine **yazılmadı**; yalnız okundu. Ölçüm
  koşumları kendi geçici kimlik veritabanını ve kendi veri kökünü kullandı,
  gerçek hesaba dokunmadı.
- `test_processing_pipeline.py` uzun geçici yolda proxy video yazamadığında
  kendini `skip` ediyor; bu bilinen platform sınırı, bu turda değişmedi.
- **Fare ile kamera sürükleme** (CAM-01/CAM-03) el ile denenmedi; kamera
  geometrisi presetler ve birim testlerle doğrulandı.
- Tam `pytest` tek süreçte hâlâ bitmiyor; kabul koşusu dosya dosya yapıldı.
  Neden bulunmadı, `open` kalıyor.
