---
document_type: project_memory
project_name: KineCapture Studio
status: vertical_slice_working
last_updated: 2026-08-20
app_version: 0.3.0
---

# KineCapture Studio — Proje Hafızası

## 1. Bu belge nasıl kullanılmalı?

Bu dosya, ZED 2i tabanlı veri toplama ve etiketleme uygulamasının kalıcı proje
hafızasıdır. Yeni bir kodlama oturumu başladığında model:

1. Önce bu dosyanın tamamını okumalıdır.
2. Ardından repository içindeki gerçek dosyaları incelemelidir.
3. Buradaki kararlarla kod arasında çelişki varsa bunu belirtmeli ve gerçek
   kodu doğrulamalıdır.
4. Önemli mimari kararları, tamamlanan aşamaları ve doğrulama sonuçlarını bu
   dosyaya eklemelidir.
5. Kararlaştırılmamış ürün ayrıntılarını kendiliğinden kesinleştirmemelidir.

Kısa kalıcı talimatlar `CLAUDE.md` içindedir.

## 2. Mevcut aşama

**Uçtan uca dikey dilim çalışıyor.** PROMPT.md bölüm 5'teki 15 adımlık akışın
tamamı hem sentetik hem gerçek ZED 2i donanımıyla yürütülebiliyor.

Önceki scaffold aşaması (2026-08-20, aynı gün) bu sürümle büyük ölçüde
değiştirildi. Aşağıdaki "değişen kararlar" bölümü farkları kaydeder.

## 3. Ortam — DOĞRULANMIŞ

```text
Conda environment : KineSynth          (küçük harfli 'Kinesynth' de yol olarak çalışır)
Interpreter       : C:\Users\gorke\anaconda3\envs\KineSynth\python.exe
Python            : 3.11.14 (Anaconda, MSC v.1929, 64-bit)
Platform          : Windows 11 Pro 10.0.26200
```

`conda env list` ile doğrulandı; kanonik ad **`KineSynth`**'tir.
`sys.executable` ile interpreter kanıtlandı.

### Bağımlılıklar

Environment'ta **zaten mevcut** olan ve kullanılan sürümler:

| Paket | Sürüm |
|---|---|
| PySide6 / Addons / Essentials / shiboken6 | 6.10.1 |
| numpy | 2.4.6 |
| PyYAML | 6.0.3 |
| opencv-python | 4.12.0.88 |
| pytest | 9.0.1 |
| pyzed | 5.4 |

**Bu görevde hiçbir paket kurulmadı veya yükseltilmedi.** Yalnızca
`kinecapture` paketi editable modda kuruldu:

```powershell
conda run -n KineSynth python -m pip install -e ".[dev]" --no-deps
```

`--no-deps` bilinçliydi: bütün runtime bağımlılıkları zaten mevcuttu ve
KineSynthV3'ün çalışan sürümlerini (torch 2.5.1, numpy 2.4.6 vb.)
bozmamak gerekiyordu.

`pyproject.toml` bağımlılıkları: PySide6>=6.5, numpy>=1.24, PyYAML>=6.0,
opencv-python>=4.8. Dev extra: pytest>=7.4. `pytest-qt` **kaldırıldı** —
kurulu değildi ve GUI testleri onsuz yazıldı.

## 4. ZED SDK ve donanım — DOĞRULANMIŞ

```text
ZED SDK        : 5.4.1
pyzed          : 5.4  (sl.cp311-win_amd64.pyd, KineSynth site-packages içinde)
SDK yolu       : C:\Program Files (x86)\ZED SDK
Kamera         : ZED 2i, S/N 31844341, firmware 1523, state AVAILABLE
CUDA (virtual) : 13.3
```

`pyzed` import ediliyor, kamera açılıyor, RGB + derinlik + vücut takibi +
SVO2 kaydı çalışıyor. **Blocker yok.**

### Ölçülen davranış

- **İlk açılış çok yavaştır**: SDK sinir ağı modellerini optimize eder.
  Ölçüldü: ilk `camera.open()` 157 s, ilk `enable_body_tracking()` 70 s.
  Bu tek seferliktir; sonraki açılışlar **2.6–4.3 s** ve body tracking
  **0.2 s**. GUI bunu bir uyarı mesajıyla bildiriyor.
- RGB `retrieve_image(VIEW.LEFT)` → `(720, 1280, 4)` uint8 **BGRA**.
  Adapter `[:, :, :3][:, :, ::-1]` ile contiguous RGB'ye çeviriyor.
- Derinlik `retrieve_measure(MEASURE.DEPTH)` → `(720, 1280)` float32,
  ölçümsüz pikseller non-finite (~%32 sahnede).
- `keypoint_confidence` **0..100** ölçeğindedir; domain sözleşmesi 0..1
  olduğu için adapter 100'e bölüyor.
- `bodies.body_format` BODY_34 için `1` döner.
- SVO2 (H264) 60 kare / HD720 ≈ 3.3 MB. Yeniden açılıp `set_svo_position`
  ile aranabiliyor.
- `get_recording_status()` sayaçları (`number_frames_ingested/encoded`) bu
  SDK sürümünde 0 dönüyor olsa da dosya büyüyor; **bu sayaçlara
  güvenilmiyor**, uygulama kendi sayaçlarını tutuyor.

### ZED iskelet tabloları — yerel SDK'dan okundu

`sl.BODY_18/34/38_PARTS` value sırasıyla ve `sl.BODY_*_BONES` enumere edilerek
`visualization/skeleton_spec.py` içine yazıldı. **Ezberden yazılmadı.**

BODY_34 doğrulanan sıra (ilk/son birkaçı):
`0 pelvis, 1 naval_spine, 2 chest_spine, 3 neck, 4 left_clavicle,
5 left_shoulder, … 24 right_ankle, 25 right_foot, 26 head, 27 nose,
28 left_eye, 29 left_ear, 30 right_eye, 31 right_ear, 32 left_heel,
33 right_heel`

Regresyon koruması: `python -m kinecapture.tools.verify_zed_topology`
canlı SDK ile bu tabloları karşılaştırır. `scripts/diagnose.ps1` bunu her
tanıda çalıştırır. **Son sonuç: BODY_18/34/38 üçü de birebir uyuşuyor.**

## 5. Gerçekten çalışan özellikler

Aşağıdakiler çalıştırılarak doğrulanmıştır (bkz. bölüm 9).

- Paket ZED SDK olmadan import edilebiliyor; `pyzed` hiçbir zaman modül
  seviyesinde import edilmiyor (alt süreçte `sys.modules` kontrolüyle test).
- `--diagnose`, `--list-devices`, `--self-test` CLI komutları.
- Deterministik sentetik backend: aynı seed → byte düzeyinde aynı RGB ve aynı
  eklem dizileri; farklı seed → farklı görüntü. Çok gövde, takip kaybı ve
  düşük güven senaryoları scriptli.
- Gerçek ZED backend: RGB, derinlik, BODY_34 vücut takibi, SVO2 native kayıt,
  cihaz enumerasyonu, temiz kapanış, kopma tespiti.
- Threaded capture: acquisition thread + writer thread; GUI yalnız okuyor.
  Önizleme kaybı ve kayıt kaybı **ayrı** sayılıyor.
- Kayıt: `skeleton.jsonl` (append-safe), `proxy.mp4`, `capture.svo2`,
  `quality.json`, `checksums.json`, atomik `take.json`.
- Yarım kayıt tespiti ve kurtarma; kapanış sırasında güvenli finalize.
- Senkron oynatma (QTimer), hız kontrolü, kare adımlama, döngü aralığı.
- Katmanlı zaman çizelgesi: veri kapsamı, takip güveni, marker'lar,
  tekrarlar; sürükleyerek oluşturma/taşıma/yeniden boyutlandırma, zoom/pan.
- Tekrar CRUD: oluştur, böl, birleştir, dışla/geri al, sil; undo/redo;
  marker'lardan sınır önerisi; çakışma doğrulaması.
- Etiketleme: egzersiz, doğruluk, hata türleri, etkilenen eklemler, faz,
  kanıt aralığı veri modeli, şiddet, güven, not, durum; autosave; öncekini
  kopyala; tümüne uygula; sonraki etiketsize geç.
- Dataset paneli: sayımlar, filtreler, dağılımlar, kalite bulguları.
- Sürümlü export: `[T,J,3] float32` + manifest + skeleton spec + label
  mapping + fingerprint + validation report + excluded; staging → atomik
  yayın; iptal ve hata durumunda hiçbir şey yayımlanmaz.
- Modern GUI: 8 çalışma alanı, daraltılabilir navigasyon, koyu **ve** açık
  tema, 43 vektör ikon (emoji yok), inline form doğrulama, hata bandı,
  klavye kısayolları, kalabalık yan panellerde kaydırma.
  Bütün sayfalar gerçekten çizdirilerek doğrulandı (ekran görüntüsü alındı).

## 6. Bu görevde alınan kalıcı teknik kararlar

1. **Environment `KineSynth`.** Önceki scaffold `KineCaptureStudio` adlı yeni
   bir environment öngörüyordu; PROMPT bunu iptal etti. `setup_env.ps1`
   silindi, üç betik `scripts/_common.ps1` üzerinden yalnız `KineSynth`
   arıyor ve bulamazsa **başka ortama düşmeden** duruyor.
2. **Python 3.10 pini kaldırıldı.** Gerçek ortam 3.11.14 ve `pyzed` 5.4 bu
   sürüm için derlenmiş (`cp311`). `environment.yml` silindi; environment
   artık bu proje tarafından yönetilmiyor.
3. **ZED backend gerçekten yazıldı.** Her SDK çağrısı yazılmadan önce bu
   makinede çalıştırıldı. Önceki scaffold'un "not_implemented" stub'ı gitti.
4. **Ham kayıt = SVO2, oynatma = proxy MP4, poz = JSONL.** Üçlü bölüm
   bilinçli: SVO2 değişmez ham kayıt ve derinliği yeniden üretebilir; proxy
   yalnızca hızlı tarama içindir; JSONL append-safe ve poz için
   otoritatiftir. Derinlik kareleri ikinci kez saklanmıyor.
5. **İskelet akışı JSONL.** Chunked binary yerine seçildi: kare başına flush
   ile kurtarılabilir, yarım son satır tolere edilebilir, dış araçlarla
   okunabilir. HD720/34 eklem ≈ 100 byte/kare — 5 dakikalık kayıt ~1 MB.
6. **Tekrar aralıkları AKIŞ KONUMUDUR, kamera kare numarası değil.**
   `RepetitionSegment.start_frame/end_frame` = `skeleton.jsonl` kare
   listesindeki 0-tabanlı indeks. Kamera kimliği kaybolmuyor: segmentte
   timestamp, exportta `frame_indices` ve `camera_timestamps_ns` dizileri ve
   manifestte `start_camera_frame`/`end_camera_frame` var. Bu ayrım
   geliştirme sırasında gerçek bir hata olarak yakalandı (kare düşünce
   ikisi ayrışıyor).
7. **Windows uzun yol desteği.** Dizin yapısı derin olduğu için 260 karakter
   sınırı gerçekten aşılabiliyor (testlerde aşıldı). `core/paths.py`
   `\\?\` öneki ekliyor; jsonio, workspace, take_writer, take_reader,
   fingerprint ve export bunu kullanıyor. OpenCV bu öneki kabul etmediği
   için proxy video "kullanılamıyor" olarak işaretlenip nedeni yazılıyor —
   veri kaybı değil, özellik kaybı.
8. **3B görünüm QPainter ile.** pyqtgraph kurulu değil; PyOpenGL/VTK entegre
   etmek risk. Birkaç düzine eklemli çubuk figür için açık perspektif
   projeksiyonu yeterli, bağımlılıksız, DPI ölçeklemesinde tutarlı ve
   test edilebilir. Orbit/zoom/pan + 4 hazır görünüm var.
9. **Zaman çizelgesi elle yazıldı.** Katmanlı, sürüklenebilir, zoom'lanabilir
   bir tekrar editörü sunan hazır bir Qt bileşeni yok.
10. **İkonlar SVG path + QPainter.** Tema rengine göre boyanıyor, DPI'ya göre
    render ediliyor, repository'de binary asset yok. Emoji kullanılmadı.
11. **Etiket ontolojisi veridir.** `label_schema.json` proje başına.
    Varsayılan şema **boş** egzersiz ve **boş** hata türü listesiyle gelir;
    hareket fazları yapısal olduğu için varsayılanı var. Kod içinde uydurma
    hata sınıfı yok.
12. **26-eklem eşleştirmesi kısmi ve öyle raporlanıyor.**
    `zed_body_34__to__rehab24_6_mocap` v0.1.0-partial: 23/26 eklem eşleşiyor.
    `Head_end`, `LeftToeBase_end`, `RightToeBase_end` mocap uç işaretçileridir
    ve ZED'de karşılığı yoktur → **NaN yazılıyor**, gerekçeleriyle birlikte
    manifeste giriyor ve Export ekranında uyarı olarak gösteriliyor.
    Kaynak: KineSynthV3 `colab/dataset/processed/kinesynth_rehab24_v1/
    skeleton_spec.json` ile yerel SDK BODY_34 sırası karşılaştırıldı.
13. **Export normalize etmiyor.** Root centering, ölçekleme, interpolasyon,
    augmentation yok; manifest bunu `normalisation: none` olarak yazıyor.
14. **Önizleme kaybı ≠ kayıt kaybı.** İki ayrı sayaç, iki ayrı gösterge.
    Önizleme "son kare kazanır" tek yuvalı; kayıt kuyruğu 120 karelik ve
    taşması veri kaybı olarak kırmızı gösteriliyor.
15. **Kod ve arayüz dili.** Kod, tanımlayıcılar, docstring'ler ve schema
    alanları İngilizce; kullanıcıya görünen bütün metinler ve hata mesajları
    Türkçe. `MEMORY.md` ve `CLAUDE.md` Türkçe.
16. **`--self-test`.** GUI'siz uçtan uca akış, geçici klasöre yazıp siler.
    Hem CLI hem test paketi kullanıyor.

### Önceki scaffold'dan değişen kararlar (geçersiz kalanlar)

| Eski karar | Yeni durum | Neden |
|---|---|---|
| `KineCaptureStudio` environment oluştur | `KineSynth` kullan | PROMPT bölüm 2 |
| Python 3.10 pinle | 3.11.14 kullan | gerçek ortam; pyzed cp311 |
| ZED backend yazma (`not_implemented`) | Tam yazıldı | SDK ve kamera doğrulandı |
| `SessionWriter.write_frame` → `NotImplementedError` | `TakeWriter` çalışıyor | format kararlaştırıldı |
| Yalnız `mock_16` iskelet kayıtlı | + BODY_18/34/38 | yerel SDK'dan okundu |
| Tek düz `RecordingSession` modeli | Project→…→Repetition hiyerarşisi | PROMPT bölüm 4.1 |

## 7. Mimari sınırlar

```text
gui/            PySide6; kameraya ve diske dokunmaz
gui/state.py    tek AppState; açık proje/katılımcı/oturum burada
capture/        CaptureService: acquisition thread + writer thread
camera/         base (sözleşme) · mock · zed  ← pyzed yalnız burada, gecikmeli
recording/      TakeWriter, ProxyVideoWriter, kalite akümülatörü
playback/       skeleton stream okuma, proxy video okuma, kurtarma
annotations/    AnnotationRepository (undo/redo, autosave)
dataset/        ProjectWorkspace (disk), DatasetIndex (sorgu/özet/QA)
export/         ReleaseBuilder (staging → atomik yayın)
domain/         enums, models, project, labels  ← Qt ve pyzed içermez
visualization/  skeleton_spec (veri), mapping (sürümlü adapter)
core/           errors, ids, jsonio, paths, config, logging, diagnostics,
                state_machine, fingerprint
tools/          verify_zed_topology
```

Durum makinesi: `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING →
REVIEWING`, `ERROR` her yerden erişilebilir ve kurtarma `DISCONNECTED`
üzerinden döner. Geçersiz geçişler `InvalidStateTransition` fırlatır.

## 8. Test komutları

```powershell
.\scripts\run_tests.ps1
.\scripts\run_tests.ps1 -Filter export
conda run -n KineSynth python -m pytest
conda run -n KineSynth python -m kinecapture --self-test
conda run -n KineSynth python -m kinecapture --diagnose
conda run -n KineSynth python -m kinecapture --list-devices
conda run -n KineSynth python -m kinecapture.tools.verify_zed_topology
```

GUI testleri `QT_QPA_PLATFORM=offscreen` ile çalışır (betik bunu ayarlar).

## 9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar

Hepsi kullanıcının Windows makinesinde, `KineSynth` environment içinde
çalıştırıldı.

| Doğrulama | Komut | Sonuç |
|---|---|---|
| Interpreter | `conda run -n KineSynth python -c "import sys; print(sys.executable)"` | `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`, Python 3.11.14 |
| Test paketi | `python -m pytest` | **223 passed**, 0 warning, 28.9 s |
| ZED'siz import | alt süreçte `sys.modules` kontrolü | `pyzed` hiç yüklenmedi |
| Self test | `python -m kinecapture --self-test` | exit 0; proje→export tamamı OK |
| Cihaz listesi | `python -m kinecapture --list-devices` | ZED SDK 5.4.1, ZED 2i S/N 31844341 AVAILABLE |
| İskelet tablosu | `python -m kinecapture.tools.verify_zed_topology` | BODY_18/34/38 üçü de SDK ile birebir uyuşuyor |
| GUI dumanı (offscreen) | 8 sayfa gezinme + tema değişimi | Hepsi kuruldu, gezinildi, iki tema da uygulandı |

### Donanım dumanı — GERÇEK ZED 2i

Gerçek kamerayla, uygulamanın kendi hattı üzerinden (`ZedCameraBackend` →
`CaptureService` → `TakeWriter` → `load_take` → `AnnotationRepository`):

İki kez çalıştırıldı. **İkinci çalıştırmada kameranın önünde bir kişi vardı**,
böylece gövde takibi ve gerçek veriyle export de doğrulandı.

**Çalıştırma 1 — kamera önünde kimse yok:**

```text
connect                4.3 s (model optimizasyonu daha önce yapılmıştı)
KAYIT                  121 kare / 4.03 s / ölçülen 29.8 FPS (hedef 30)
VERİ KAYBI             YOK — dropped=0, missing=0
tracking_coverage      0.00, bodies=0
skeleton.jsonl         12,312 B (yalnız header + boş kare kayıtları)
export                 DOĞRU BİÇİMDE REDDETTİ: no_body_in_interval
```

Boş sürüm yayımlanmaması beklenen ve istenen davranıştır.

**Çalıştırma 2 — kamera önünde bir kişi var (TAM DOĞRULAMA):**

```text
connect                3.7 s
model/serial/firmware  ZED 2i / 31844341 / 1523      sdk 5.4.1
çözünürlük/fps         1280x720 @ 30                 coord right_handed_y_up, unit meter
body format            zed_body_34                   depth=True, body_tracking=True
capabilities           color+depth+body+native_recording+multi_body+enumeration
önizleme karesi        rgb (720,1280,3) uint8, depth (720,1280), camera_ts alındı
KAYIT                  122 kare / 4.03 s / ölçülen 30.0 FPS (hedef 30)
VERİ KAYBI             YOK — dropped=0, missing=0, zaman boşluğu 0
GÖVDE TAKİBİ           tracking_coverage=0.45, mean_joint_conf=0.736,
                       distinct_body_ids=1, tracking id=(0,)
dosyalar               capture.svo2 7,215,771 B · skeleton.jsonl 123,593 B
                       · proxy.mp4 476,068 B
oynatma                122 kare, 4.03 s, proxy seek OK, 2 marker, spec=zed_body_34
etiketleme             1 tekrar oluşturuldu ve etiketlendi
EXPORT (native)        dataset_v001 · 1 örnek · doğrulama GEÇTİ
                       dizi (118, 34, 3) float32, %45 finite,
                       skeleton=zed_body_34, origin=real, camera=ZED 2i
EXPORT (rehab24)       dataset_v002 · dizi (118, 26, 3) · status=partial
                       mapped=23/26
                       tamamı NaN olan eklem indeksleri = [5, 20, 25]
```

Son satır kritik: REHAB24-6 sırasında indeks **5 = `Head_end`**,
**20 = `LeftToeBase_end`**, **25 = `RightToeBase_end`**. Yani eşleştirme
gerçek BODY_34 verisi üzerinde tam olarak beyan ettiği gibi davrandı —
23 eklemi doldurdu, yalnızca ve tam olarak beyan edilen 3 eklemi NaN
bıraktı, başka hiçbir eklemi bozmadı.

`mean_joint_conf=0.736` değeri, SDK'nın 0..100 ölçeğinin 0..1'e doğru
çevrildiğini de kanıtlıyor (ham değer ~73.6 olurdu).

### Ek olarak: donanımsız gövde dönüşümü testleri

`tests/test_zed_adapter.py` (17 test) `ZedCameraBackend._retrieve_bodies`
dönüşümünü SDK'nınkine benzer stub nesnelerle donanımsız test ediyor: güven
ölçeği 0..100→0..1, yanlış eklem sayısında **yeniden şekillendirmeden
düşürme**, tracking-state eşlemesi, eksik eklemin non-finite kalması,
orientation kontrolü ve sidecar round-trip'i. Bunlar canlı kamera
gerektirmeden regresyonu yakalar.

### Geliştirme sırasında bulunup düzeltilen gerçek hatalar

1. **Windows 260 karakter yol sınırı**: derin dizin yapısı + uzun kimlikler
   `FileNotFoundError` üretiyordu. `core/paths.py` ile `\\?\` öneki eklendi,
   geçici dosya öneki kısaltıldı.
2. **Tekrar aralığı anlamı çelişkiliydi**: GUI konum, export kamera kare
   numarası varsayıyordu; kare düşünce ayrışıyorlardı. Konum standardı
   seçildi ve manifest ikisini birden yazacak biçimde genişletildi.
3. **Sentetik backend seed'i görüntüyü etkilemiyordu**: farklı seed aynı
   kareyi üretiyordu. Arka plana seed'e bağlı ton ve grain eklendi.
4. **İlk gövde seçimi "kimlik değişimi" sayılıyordu**: `None → 1` geçişi
   metadata'ya sahte bir değişim yazıyordu.
5. **Boş export nedeni gizliydi**: yalnız "örnek bulunamadı" diyordu; artık
   dışlanma nedenlerini ve hedefe uygun çözümü yazıyor.
6. **Derinlik renklendirmesinde NaN cast uyarısı**: ramp yalnız ölçülen
   piksellere uygulanacak biçimde düzeltildi.
7. **GUI çizim çökmesi (segfault)**: `QPainter.drawPolygon` timeline'da üç
   ayrı `QPointF` argümanıyla çağrılıyordu. PySide6 bunu Qt'nin
   `(const QPointF *, int)` aşırı yüklemesine bağlıyor, ikinci nokta "adet"
   olarak yorumlanıyor ve dizinin çok ötesi okunuyor → **access violation**.
   İnceleme sayfasına her geçişte uygulamayı çökürtüyordu. `QPolygonF` ile
   düzeltildi.
   **Neden kaçtı:** hiçbir test widget'ları gerçekten çizdirmiyordu; kurma ve
   veri verme paint kodunu hiç çalıştırmıyor. `tests/test_gui_painting.py`
   (31 test) eklendi: her özel widget `grab()` ile gerçekten çizdiriliyor
   (boş, tek kare, tamamı NaN, en yakın/uzak zoom, çoklu gövde, her tema).
   Düzeltme geri alınarak testin gerçekten yakaladığı doğrulandı.
8. **Capture ve İnceleme yan panelleri taşıyordu**: sağ sütundaki kartlar
   980 px yükseklikte sıkışıp metinleri üst üste biniyor, form alanları
   kırpılıyordu. Her iki panel kaydırılabilir hale getirildi.
9. **Testler gerçek kullanıcı ayarlarını bozuyordu**: GUI testleri tema ve
   proje değiştirdiğinde `AppState.save_preferences()` gerçek
   `~/.kinecapture/user_state.yaml` dosyasına yazıyor, pytest'in geçici
   klasörü kullanıcının dataset kökü olarak kaydediliyordu. conftest'te
   autouse bir fixture ile `USER_STATE_PATH` izole edildi ve
   `tests/test_user_state.py` bunu koruyan 5 test eklendi. Kirlenen dosya
   silindi.

## 10. Bilinen sorunlar, riskler ve sınırlar

- ZED SDK'nın **ilk** model optimizasyonu dakikalar sürer. GUI uyarı veriyor
  fakat bu sırada bağlan düğmesi bloklanıyor — iptal edilebilir bir arka plan
  işine dönüştürülmesi iyi olur.
- Proxy video Windows uzun yol sınırında devre dışı kalıyor (OpenCV `\\?\`
  kabul etmiyor). İskelet verisi etkilenmiyor.
- `get_recording_status()` sayaçları bu SDK sürümünde güvenilmez; uygulama
  kendi sayaçlarını kullanıyor.
- Eş zamanlı iki uygulama örneği aynı projeyi açarsa kilitleme yok.
- Dataset index metadata dosyalarını her yenilemede tarıyor; çok büyük
  datasetlerde kalıcı bir index/cache gerekebilir.
- `kinecapture.exe` script'i PATH'te değil (pip uyarısı); `python -m
  kinecapture` kullanılıyor.

## 11. Henüz uygulanmayanlar

- Otomatik tekrar algılama (veri modeli `model_suggestion` kaynağıyla hazır).
- Yapay zekâ ile hata sınıflandırma / ön etiket.
- Çok uzmanlı consensus ve reviewer yorumları.
- Çok kameralı kayıt, bulut senkronizasyonu, gelişmiş yetkilendirme.
- Yüz bulanıklaştırma / skeleton-only privacy export.
- Kanıt aralığı (`EvidenceInterval`) için tam GUI — veri modeli ve
  serileştirme hazır, ekran yalnız metin alanları sunuyor.
- Zaman çizelgesinde hareket fazı ve reviewer yorum katmanları.
- Paketleme / dağıtım (installer).

## 12. Sonraki önerilen adım

1. **Daha uzun ve kontrollü çekim yapın** (2–3 dakika, tam görüş alanında).
   4 saniyelik dumanda `tracking_coverage` 0.45 çıktı; kişinin çerçeveye
   girip çıkmasından kaynaklanıyor olabilir. Gerçek çekim mesafesi ve
   kamera yüksekliği için kapsamın ne olduğunu ölçüp bu dosyaya yazın.
2. Proje etiket şemasına gerçek egzersiz listesini ve hata ontolojisini
   girin (Ayarlar → Etiket şeması). Kod içinde uydurulmuş sınıf yok.
3. ZED ilk-açılış optimizasyonunu iptal edilebilir arka plan işine taşıyın.
4. Kanıt aralığı (evidence interval) için zaman çizelgesi katmanı ekleyin.
5. Otomatik tekrar algılamayı `SegmentSource.MODEL_SUGGESTION` olarak
   ekleyin; insan onayı olmadan ground truth sayılmamalı (altyapı hazır).
