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
| Tekrar segmentasyonu (oluştur/böl/birleştir/dışla, undo/redo) | Çalışıyor |
| Etiketleme + autosave | Çalışıyor |
| Dataset paneli + kalite bulguları | Çalışıyor |
| Sürümlü export (manifest / spec / mapping / fingerprint / doğrulama) | Çalışıyor |
| KineSynthV3 26-eklem eşleştirmesi | **Kısmi** — 23/26 eklem; 3 eklem eşleşmiyor ve NaN yazılıyor |
| Otomatik tekrar algılama, çok kameralı kayıt, çok uzmanlı consensus | Uygulanmadı |

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
5. **İnceleme ve Etiketleme** — senkron oynatma, zaman çizelgesi, tekrarlar, etiketler.
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

### İnceleme kısayolları

| Tuş | İşlem |
|---|---|
| `Boşluk` | Oynat / duraklat |
| `,` / `.` | Bir kare geri / ileri |
| `N` | Konumda yeni tekrar |
| `S` | Seçili tekrarı böl |
| `X` | Dışla / geri al |
| `C` | Önceki tekrarın etiketini kopyala |
| `1`–`4` | Doğru / Hatalı / Kararsız / Etiketlenmedi |
| `Ctrl+Z`, `Ctrl+Y` | Geri al / yinele |
| `Ctrl+S` | Hemen kaydet |

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
    │           ├── annotations/segments.json   # insan kararları (sidecar)
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

---

## Dataset sürümleri

Her sürüm (`dataset_v001`, `dataset_v002`, …) şunları içerir:

| Dosya | İçerik |
|---|---|
| `samples/*.npz` | Tekrar başına `float32 [T, J, 3]` + güven + kare indeksi + kamera zaman damgası |
| `manifest.json` | Örnek listesi, ilişkiler, provenance, dizi sözleşmesi |
| `skeleton_spec.json` | Eklem adları, sırası, kenarlar, koordinat sistemi, birim |
| `label_mapping.json` | Sınıf kodları ve sabit indeksleri |
| `dataset_fingerprint.json` | Bileşen bazlı + birleşik parmak izi |
| `validation_report.json` | Doğrulama sonucu, hatalar, uyarılar |
| `excluded.json` | Dışlanan örnekler ve nedenleri |

**Ham koordinatlar yazılır.** Root centering, ölçek normalizasyonu,
interpolasyon ve augmentation uygulanmaz — bunlar eğitim katmanına aittir.
Görülemeyen eklem NaN kalır.

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

**223 test, tamamı geçiyor** (~29 s). Testler gerçek kamera gerektirmez ve
gerçek zaman beklemez; GUI testleri `QT_QPA_PLATFORM=offscreen` ile çalışır.

Kapsam: ortam ve opsiyonel `pyzed` importu, config doğrulama, domain
shape/dtype, ZED iskelet tabloları, eklem eşleştirme, mock determinizmi,
çok gövde ve takip kaybı senaryoları, state machine, capture servisi,
atomik yazım ve overwrite koruması, checksum, yarım kayıt kurtarma,
oynatma, segmentasyon, etiketleme, undo/redo, autosave, dataset index,
export manifest/fingerprint/doğrulama, iptal ve hata atomikliği,
ZED gövde dönüşümü (donanımsız stub ile), GUI kurulumu ve temalar,
ve her özel widget ile her sayfanın gerçekten çizdirilmesi (paint testleri).

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
