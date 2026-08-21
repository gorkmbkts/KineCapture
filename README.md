# KineCapture Studio

Stereolabs ZED 2i ile hareket verisi toplama, inceleme, etiketleme ve makine
öğrenmesi için sürümlenmiş dataset üretme masaüstü uygulaması.

Windows · Python 3.11 · PySide6 · ZED SDK 5.4

---

## Durum

Uçtan uca dikey dilim çalışır durumda: **proje → katılımcı → oturum → kayıt →
oynatma → tekrar segmentasyonu → etiketleme → dataset sürümü.** Akış hem
gerçek ZED 2i donanımıyla hem de donanımsız sentetik backend ile çalışır.

| Bileşen | Durum |
|---|---|
| Sentetik (mock) backend | Çalışıyor, deterministik, testlerin temeli |
| ZED 2i backend (RGB / derinlik / vücut takibi / SVO2) | Çalışıyor, gerçek donanımda doğrulandı |
| Kayıt, finalize, checksum, yarım kayıt kurtarma | Çalışıyor |
| Senkron oynatma + zaman çizelgesi | Çalışıyor |
| Hareket segmentasyonu (oluştur/böl/birleştir/dışla, undo/redo) | Çalışıyor |
| İki seviyeli etiketleme (hareket + zamansal hata aralığı) | Çalışıyor |
| Etiketleme sırasında hata türü oluşturma | Çalışıyor |
| Autosave + undo/redo | Çalışıyor |
| Dataset paneli + kalite bulguları | Çalışıyor |
| Sürümlü export (manifest / spec / mapping / fingerprint / doğrulama) | Çalışıyor |
| KineSynthV3 26-eklem eşleştirmesi | **Kısmi** — 23/26 eklem; 3 eklem eşleşmiyor ve NaN yazılıyor |
| Otomatik tekrar algılama, çok kameralı kayıt, çok uzmanlı consensus | Uygulanmadı |

### Etiket modeli

Etiketler **iki seviyelidir**:

1. **Hareket sample'ı** — kayıt içindeki bir tekrar. Hareket türü ve **ikili**
   doğru/yanlış kararı taşır. Bir kayıt birden çok hareket içerebilir; her biri
   ayrı bir export örneği olur.
2. **Hata aralığı** — seçili hareketin *içinde*, hatanın göründüğü zaman
   aralığı. Bir aralık tek bir hata sınıfı taşır. Aynı sınıf hareket boyunca
   tekrarlanabilir, farklı sınıflar çakışabilir (aynı anda iki hata),
   fakat hiçbir aralık ait olduğu hareketin dışına çıkamaz.

Bu, ileride eğitilecek modelin yalnızca "hatalı mı?" değil "hata hareketin
neresinde?" sorusunu da öğrenebilmesi içindir.

**Hareket fazı kavramı kaldırılmıştır.** Eski kayıtlardaki faz değerleri
silinmez; `legacy` bloğunda saklanır fakat arayüzde ve yeni export
sözleşmesinde yer almaz.

---

## Kurulum

Bu proje bilgisayarda hâlihazırda bulunan **`KineSynth`** conda
environment'ında çalışır. Yeni environment oluşturulmaz.

```powershell
conda run -n KineSynth python -m pip install -e ".[dev]"
```

Bağımlılıklar (`KineSynth` içinde zaten mevcut): PySide6 6.10.1, NumPy 2.4.6,
PyYAML 6.0.3, opencv-python 4.12, pytest 9.0.1.

`pyzed` **bilinçli olarak pip bağımlılığı değildir**: ZED SDK ayrı kurulur ve
Python bağlaması SDK'nın `get_python_api.py` betiğiyle environment'a eklenir.
SDK yoksa uygulama yine açılır, sentetik backend ile tam olarak çalışır ve
tanılama ekranı eksiği açıkça bildirir.

## Çalıştırma

```powershell
.\scripts\run_app.ps1                 # GUI
.\scripts\run_app.ps1 -Backend zed    # ZED backend seçili açılır
.\scripts\diagnose.ps1                # ortam + SDK + kamera + iskelet tablosu
.\scripts\run_tests.ps1               # testler
```

Betikler `KineSynth` bulunamazsa başka bir environment'a düşmez; ne yapılması
gerektiğini yazıp durur.

Doğrudan CLI:

```powershell
conda run -n KineSynth python -m kinecapture --diagnose
conda run -n KineSynth python -m kinecapture --list-devices
conda run -n KineSynth python -m kinecapture --self-test
conda run -n KineSynth python -m kinecapture --backend mock
```

---

## Uygulama akışı

Sol gezinme çubuğunda sekiz çalışma alanı var (`Ctrl+1` … `Ctrl+8`,
`Ctrl+B` daraltır):

1. **Ana Sayfa** — sayımlar, yarım kayıtlar, etiket bekleyenler, sistem durumu.
2. **Projeler ve Protokoller** — proje oluştur/aç, çekim planı tanımla.
3. **Katılımcılar ve Oturumlar** — anonim katılımcı (`P0001`), oturum formu.
4. **Capture** — canlı RGB/derinlik, 3B iskelet, ön kontrol paneli, kayıt.
5. **İnceleme ve Etiketleme** — senkron oynatma, iki modlu zaman çizelgesi,
   hareket ve hata etiketleri.
6. **Dataset** — bileşim, filtreler, kalite bulguları.
7. **Export** — sürümlü dataset yayını.
8. **Ayarlar ve Tanılama** — tercihler, yakalama profili, etiket şeması, tanı.

### Capture kısayolları

| Tuş | İşlem |
|---|---|
| `R` | Kaydı başlat / durdur |
| `Boşluk` | Önizlemeyi aç / kapat |
| `M` | Marker bırak |
| `Esc` | Kaydı durdur |

Metin alanına yazarken bu kısayollar tetiklenmez.

### Etiketleme akışı

1. Kaydı oynatın veya zaman çizelgesinde gezinin.
2. **Hareket modunda** (F1) HAREKET şeridinde sürükleyerek bir tekrar çizin.
3. Hareketi seçin, gerekirse sadece onu döngüde oynatıp sınırlarını düzeltin.
4. Hareket türünü ve doğru/yanlış kararını verin (`1` / `2`).
5. Hareket yanlışsa **hata moduna** (F2 veya `E`) geçin, HATA şeridinde hatanın
   göründüğü aralığı çizin ve hata türünü seçin.
6. Aynı harekete başka hata aralıkları ekleyin, sonra sonraki harekete geçin.

Aranan hata türü yoksa, adı yazıp Enter'a basmak yeni türü projeye kalıcı
olarak ekler ve seçili aralığa atar; ekrandan çıkmanız gerekmez.

### İnceleme kısayolları

| Tuş | İşlem |
|---|---|
| `Boşluk` | Oynat / duraklat |
| `,` / `.` | Bir kare geri / ileri |
| `F1` / `F2` | Hareket modu / hata modu |
| `N` | Konumda yeni hareket |
| `E` | Konumda yeni hata aralığı |
| `S` | Seçili hareketi böl |
| `X` | Dışla / geri al |
| `C` | Önceki hareketin etiketini kopyala |
| `1` / `2` | Doğru / Hatalı |
| `Ctrl+F` | Hata türü aramasına odaklan |
| `Ctrl+1`/`2`/`3` | RGB / İskelet / RGB + İskelet |
| `Ctrl+Z`, `Ctrl+Y` | Geri al / yinele |
| `Ctrl+S` | Hemen kaydet |

Metin alanına yazarken bu kısayollar tetiklenmez.

---

## Disk yapısı

```text
dataset_root/
└── projects/<project_id>/
    ├── project.json
    ├── label_schema.json
    ├── participants/<participant_id>/          # P0001, P0002, ... (anonim)
    │   ├── participant.json
    │   └── sessions/<session_id>/
    │       ├── session.json
    │       └── takes/<take_id>/
    │           ├── take.json                   # yakalama metadata + provenance
    │           ├── raw/capture.svo2            # ZED native kayıt (değişmez)
    │           ├── derived/skeleton.jsonl      # kare başına iskelet (append-safe)
    │           ├── derived/proxy.mp4           # inceleme için küçültülmüş kopya
    │           ├── annotations/segments.json   # insan kararları (sidecar, v2)
    │           ├── quality/quality.json        # ölçülen kalite metrikleri
    │           └── checksums.json
    └── releases/dataset_v001/ ...
```

### Veri bütünlüğü kararları

- **Ham kayıt değişmez.** Etiketleme `take.json` dosyasına dokunmaz.
- **Atomik yazım.** Geçici dosya + `os.replace`; yarım JSON bırakılmaz.
  Mevcut dosyanın üzerine sessizce yazılmaz.
- **Append-safe iskelet akışı.** Her kare sonrası flush edilir. Elektrik
  kesilse bile o ana kadarki kareler okunabilir; yarım kalan son satır
  tolere edilir ve `truncated` olarak bildirilir.
- **Derinlik iki kez saklanmaz.** SVO2 derinliği yeniden üretebildiği için
  kare başına derinlik varsayılan olarak yazılmaz (`store_depth_frames`).
- **Yarım kayıtlar kaybolmaz.** Finalize edilmemiş kayıt `PARTIAL` kalır,
  açılışta bulunur ve kurtarılabilir.
- **Uzun yol desteği.** Windows 260 karakter sınırı `\\?\` önekiyle aşılır
  (`kinecapture.core.paths`).
- **Kare sınırları tek sözleşme.** `start_frame` / `end_frame` her yerde
  `derived/skeleton.jsonl` kare listesindeki 0 tabanlı konumdur ve **her iki uç
  dahildir**. Arayüz, sidecar ve export aynı anlamı kullanır.
- **Eski etiketler bozulmaz.** v1 sidecar okunabilir; okuma sırasında dosya
  **yeniden yazılmaz**. Yerini yitiren alanlar (`movement_phase`, `severity`,
  `affected_joints`, eski durumlar) `legacy` bloğunda korunur. Belirsiz bir
  `uncertain` kararı kesin bir doğru/yanlış'a **çevrilmez**; etiketlenmemiş
  sayılır ve orijinali kaydedilir.

---

## Dataset sürümleri

Her sürüm (`dataset_v001`, `dataset_v002`, …) şunları içerir:

| Dosya | İçerik |
|---|---|
| `samples/*.npz` | Hareket başına `float32 [T, J, 3]` + güven + kare indeksi + kamera zaman damgası + hata aralıkları |
| `manifest.json` | Örnek listesi, ilişkiler, provenance, dizi sözleşmesi |
| `skeleton_spec.json` | Eklem adları, sırası, kenarlar, koordinat sistemi, birim |
| `label_mapping.json` | Sınıf kodları ve sabit indeksleri |
| `dataset_fingerprint.json` | Bileşen bazlı + birleşik parmak izi |
| `validation_report.json` | Doğrulama sonucu, hatalar, uyarılar |
| `excluded.json` | Dışlanan örnekler ve nedenleri |

**Ham koordinatlar yazılır.** Root centering, ölçek normalizasyonu,
interpolasyon ve augmentation uygulanmaz — bunlar eğitim katmanına aittir.
Görülemeyen eklem NaN kalır.

#### Etiket sözleşmesi

Her örnek (bir hareket sample'ı) şunları taşır:

| Alan | Anlam |
|---|---|
| `exercise` | Hareket türü kodu |
| `correctness` | `correct` veya `incorrect` — **ikili** |
| `error_intervals[]` | Zamansal hata aralıkları (0 veya daha fazla) |

Her hata aralığı hem **mutlak** (kayıt içi) hem **göreli** (dizi içi) konum
taşır, böylece tüketici tahmin yürütmez:

```jsonc
{
  "error_code": "diz-ice-cokuyor",
  "class_index": 0,             // label_mapping.error_types.code_to_index
  "start_position": 43,          // kayıt akışındaki mutlak konum
  "end_position": 55,
  "relative_start": 4,           // joints_xyz[4 : 12+1] tam olarak bu aralık
  "relative_end": 12,
  "num_frames": 9,
  "start_camera_frame": 46,      // kameranın kendi kare numarası
  "end_camera_frame": 58,
  "start_timestamp_ns": 1787...,
  "end_timestamp_ns": 1787...
}
```

`.npz` içinde ayrıca iki hazır hedef bulunur:

- `error_intervals` — `int32 [K, 3]` = `(class_index, relative_start, relative_end)`,
  her iki uç dahil.
- `error_multi_hot` — `uint8 [T, C]`; sütun sırası `label_mapping` ile aynıdır.
  Çakışan aralıklar aynı karede birden çok sütunu 1 yapar.

Doğrulama raporu yetim aralıkları, hareket dışına taşanları, bilinmeyen hata
kodlarını, ters/boş aralıkları, doğruluk-hata çelişkilerini ve manifest-dizi
uzunluğu uyuşmazlıklarını yakalar. Fingerprint hata sınıflarına ve aralık
sınırlarına duyarlıdır: bir aralığı eklemek, silmek, taşımak veya yeniden
sınıflandırmak sürüm parmak izini değiştirir.

**Export'a ne girer?** Ekranda "hazır" görünen hareketler — ne eksiği ne
fazlası. Aynı kural (`evaluate_sample`) hem arayüzü hem exportu besler.
Dışlanan her şey nedeniyle birlikte `excluded.json` içine yazılır.

`participant_id`, `session_id` ve `take_id` her örnekte korunur; katılımcı
bazlı ayrım yapılabilsin ve rastgele split sızıntısı fark edilebilsin diye.

### KineSynthV3 uyumluluğu

ZED'in native `BODY_34` formatı KineSynthV3'ün 26 eklemli `rehab24_6_mocap`
yapısıyla **aynı değildir**. Sürümlü bir adapter tanımlıdır
(`zed_body_34__to__rehab24_6_mocap` v0.1.0-partial):

- 26 hedef eklemin **23'ü** doğrudan eşleşiyor.
- 3 eklem eşleşmiyor ve **NaN yazılıyor**: `Head_end`, `LeftToeBase_end`,
  `RightToeBase_end`. Bunlar mocap uç işaretçileridir ve ZED'de karşılığı
  yoktur; uydurulmak yerine boş bırakılır.
- Eşleştirmenin durumu, kapsamı ve eşleşmeyen eklemlerin gerekçesi manifeste
  yazılır ve Export ekranında gösterilir.

Varsayılan export **native** eklem sırasındadır.

---

## Mimari

```text
GUI (PySide6)          gui/pages/*, gui/widgets/*, gui/main_window.py
   │  yalnız okur; kamera veya diske dokunmaz
AppState               gui/state.py
   │
CaptureService         capture/service.py
   ├── acquisition thread ── backend.grab_frame()
   │        ├── preview slot (son kare kazanır → GUI QTimer okur)
   │        └── recording queue (sınırlı) ── writer thread ── TakeWriter
CameraBackend          camera/base.py → camera/mock.py, camera/zed.py
Depolama               dataset/workspace.py, recording/, playback/, annotations/
Export                 export/release.py
Domain                 domain/ (Qt ve pyzed içermez)
```

- Kamera okuma ve disk yazımı GUI thread'inde **değildir**.
- Önizleme kuyruğu tek karelik: GUI geride kalırsa kare atlanır ve
  *önizleme kaybı* olarak sayılır.
- Kayıt kuyruğu sınırlıdır: taşarsa bu *veri kaybıdır*, ayrıca sayılır,
  ekranda kırmızı gösterilir ve kaydın kalite metriklerine yazılır.
- Bu iki sayı asla birbirine karıştırılmaz.

---

## Test

```powershell
.\scripts\run_tests.ps1
conda run -n KineSynth python -m pytest -k export
```

**314 test, tamamı geçiyor** (~93 s). Testler gerçek kamera gerektirmez ve
gerçek zaman beklemez; GUI testleri `QT_QPA_PLATFORM=offscreen` ile çalışır.

Kapsam: ortam ve opsiyonel `pyzed` importu, config doğrulama, domain
shape/dtype, ZED iskelet tabloları, eklem eşleştirme, mock determinizmi,
çok gövde ve takip kaybı senaryoları, state machine, capture servisi,
atomik yazım ve overwrite koruması, checksum, yarım kayıt kurtarma,
oynatma, hareket segmentasyonu, hata aralıkları (tek/çok/tekrarlı/çakışan),
aralığın hareket dışına çıkamaması, hareket sınırı değişince güvenli davranış,
etiketleme sırasında hata türü oluşturma ve tekrar adı kontrolü,
undo/redo, autosave, eski v1 annotation JSON'unun kayıpsız okunması,
dataset index, export manifest/mapping/fingerprint/doğrulama, iptal ve hata
atomikliği, ZED gövde dönüşümü (donanımsız stub ile), RGB/iskelet/bindirilmiş
görünüm modları, iki modlu zaman çizelgesi ve her sayfanın gerçekten
çizdirilmesi (paint testleri).

---

## Gizlilik

- Katılımcılar varsayılan olarak anonim kod ile temsil edilir (`P0001`).
- Dosya adlarında ve loglarda kişisel bilgi bulunmaz.
- Onam yalnızca durum olarak saklanır; onam metni bu uygulamada tutulmaz.
- Veri silme yalnızca açık hedef ve tekrar onayla yapılır; sessiz/otomatik
  silme yoktur.

## Sorumluluk reddi

Bu bir **araştırma ve dataset üretim aracıdır**. Ölçümler ve türetilen
çıktılar klinik olarak doğrulanmış bir değerlendirme değildir ve öyle
sunulmamalıdır.
