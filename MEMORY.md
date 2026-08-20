---
document_type: project_memory
project_name: KineCapture Studio
status: scaffold_completed
language: tr
last_updated: 2026-08-20
---

# KineCapture Studio — Proje Hafızası

## 1. Bu belge nasıl kullanılmalı?

Bu dosya, ZED 2i tabanlı yeni veri toplama ve etiketleme uygulamasının kalıcı proje hafızasıdır.

Yeni bir Codex, Claude Code veya benzeri kodlama oturumu başladığında model:

1. Önce bu dosyanın tamamını okumalıdır.
2. Ardından repository içindeki gerçek dosyaları incelemelidir.
3. Buradaki kararlarla kod arasında çelişki varsa bunu belirtmeli ve gerçek kodu doğrulamalıdır.
4. Önemli mimari kararları, tamamlanan aşamaları ve doğrulama sonuçlarını bu dosyaya eklemelidir.
5. Kararlaştırılmamış ürün ayrıntılarını kendiliğinden kesinleştirmemelidir.

`KineCapture Studio` şimdilik geçici çalışma adıdır. Uygulama adı daha sonra değiştirilebilir.

## 2. Yeni projenin amacı

Bu proje, Windows üzerinde Python ile çalışan gelişmiş bir masaüstü uygulaması olacaktır.

Ana donanım:

- Stereolabs ZED 2i kamera
- İlk aşamada tek kamera
- Gelecekte mimari izin verirse ek kamera veya başka veri kaynakları

Uygulamanın uzun vadeli amaçları:

- ZED 2i kameraya bağlanmak
- Canlı RGB görüntüsünü göstermek
- Gerekirse canlı depth görünümü sunmak
- ZED body tracking çıktısını almak
- Algılanan insanları ve 3B iskeletlerini canlı göstermek
- Kayıt oturumlarını başlatmak, durdurmak ve güvenli biçimde saklamak
- Kaydedilen oturumları sonradan oynatmak
- Frame veya zaman aralığı tabanlı etiketleme yapmak
- Katılımcı, egzersiz, doğruluk ve hareket hatası metadata’sı tutmak
- Makine öğrenmesi için tekrar üretilebilir dataset exportları hazırlamak
- KineSynthV3 eğitim hattıyla ileride veri alışverişi yapabilmek

Bu ilk aşamada tam ürün geliştirilmeyecektir. Öncelik, gelecekte büyütülebilecek güvenli bir proje iskeleti oluşturmaktır.

## 3. Eski KineSynthV3 projesinden aktarılan bağlam

Yeni uygulama KineSynthV3 repository’sinden tamamen ayrı bir klasörde geliştirilecektir.

Yeni proje:

- KineSynthV3 kodunu doğrudan import etmemelidir.
- Eski repository’nin bilgisayarda bulunduğunu varsaymamalıdır.
- Eski dataset veya model dosyalarına sabit yollarla bağlanmamalıdır.
- Uyumluluğu doğrudan kod bağımlılığıyla değil, açık ve sürümlenmiş veri formatlarıyla sağlamalıdır.

KineSynthV3’ün mevcut araştırma amacı, 3B iskelet zaman serilerinden egzersiz sınıfı ve doğru/hatalı hareket tahmini yapmaktır. Uzun vadeli amaç; hata türü, etkilenen eklem, zaman aralığı, hareket fazı, şiddet, güven ve geri bildirim içeren kanıt paketleri üretmektir.

Mevcut KineSynthV3 dataset sözleşmesi:

- Her tekrar değişken uzunluklu `float32 [T, J, 3]` dizisidir.
- Mevcut REHAB24-6 verisinde `J = 26` eklemdir.
- Ham koordinatlar export sırasında normalize edilmez.
- Root centering, ölçekleme, interpolasyon ve augmentation yalnızca eğitim katmanında uygulanır.
- Dataset exportunda manifest, label mapping, skeleton specification, fingerprint ve doğrulama raporu bulunur.
- Katılımcı bazlı veri ayrımı zorunludur. Rastgele sample split veri sızıntısı oluşturabilir.
- Sonuçlar araştırma amaçlı proof-of-concept’tir; klinik doğrulama olarak sunulmamalıdır.

ZED’in native body formatı KineSynthV3’teki 26 eklemli yapıyla aynı kabul edilmemelidir. Yeni uygulama ZED’in native joint sırasını ve skeleton formatını kaybetmeden saklamalıdır. KineSynthV3 uyumluluğu daha sonra ayrı, açıkça test edilmiş bir mapping/export adapter ile sağlanmalıdır.

## 4. Yeniden kullanılacak tasarım ilkeleri

Eski projeden aşağıdaki ilkeler korunmalıdır:

- GUI için PySide6 tercih edilir.
- Kamera okuma, kayıt, dönüştürme ve export işlemleri Qt ana iş parçacığını bloklamamalıdır.
- Canlı yakalama ile GUI arasında açık bir worker/service sınırı bulunmalıdır.
- Playback, bloklayan döngüler yerine timer ve sinyallerle yönetilmelidir.
- Ham veri ile yalnızca gösterim amacıyla dönüştürülmüş veri ayrılmalıdır.
- Root centering veya eksen dönüşümü yalnızca görüntüleme için yapılıyorsa ham kayda yazılmamalıdır.
- Etiketler ve manuel düzeltmeler ham kaydı değiştirmeyen sidecar dosyalarda tutulmalıdır.
- Büyük kayıtlar tamamen RAM’e alınmamalıdır.
- Veri yazımı mümkün olduğunca atomik ve kesinti sonrası kurtarılabilir olmalıdır.
- Her kayıt ve export sürümlenmiş bir schema ile tanımlanmalıdır.
- Hatalar kullanıcıya anlaşılır şekilde, teknik ayrıntılar ise log dosyasında gösterilmelidir.
- Gerçek kamera olmadan geliştirme ve test yapılabilmesi için mock/synthetic backend bulunmalıdır.
- Testler gerçek dataset veya bağlı ZED kamera gerektirmemelidir.

## 5. Temel mimari sınırlar

Uygulama en az aşağıdaki katmanlara ayrılmalıdır:

- `camera`: Kamera backend arayüzü, mock backend ve ZED backend
- `domain`: Kamera, frame, body, skeleton, session ve annotation veri modelleri
- `services`: Kamera yaşam döngüsü ve canlı yakalama koordinasyonu
- `recording`: Kayıt oturumu ve güvenli disk yazımı
- `annotations`: Etiketlerin saklanması ve güncellenmesi
- `visualization`: Skeleton topolojisi ve görüntüleme dönüşümleri
- `gui`: PySide6 pencereleri ve widget’ları
- `core`: Ayarlar, loglama, durum makinesi ve ortam tanılama
- `tests`: Donanımdan bağımsız birim testleri

GUI doğrudan `pyzed` çağrısı yapmamalıdır. ZED SDK’ya ait bütün çağrılar kamera backend katmanında kalmalıdır.

## 6. Kamera ve canlı yakalama kuralları

`pyzed` zorunlu standart Python bağımlılığı gibi ele alınmamalıdır. ZED SDK ayrı kurulur ve Python binding’i SDK ortamından sağlanabilir.

Bu nedenle:

- `pyzed` modül seviyesinde zorunlu olarak import edilmemelidir.
- Import işlemi ZED backend içinde gecikmeli yapılmalıdır.
- SDK bulunamadığında uygulama açılabilmeli ve açıklayıcı tanı sunmalıdır.
- SDK sürümü, Python uyumluluğu ve donanım durumu yerel ortamda doğrulanmadan SDK çağrıları uydurulmamalıdır.
- Ağır SDK veya CUDA kurulumu kullanıcı onayı olmadan yapılmamalıdır.
- Mock backend varsayılan geliştirme yolu olmalıdır.

Kamera yaşam döngüsü açık bir durum makinesiyle yönetilmelidir. Başlangıç durumları:

```text
DISCONNECTED
READY
PREVIEWING
RECORDING
STOPPING
ERROR
```

Geçersiz durum geçişleri sessizce kabul edilmemelidir.

Canlı yakalama sırasında GUI’nin geride kalması halinde sınırsız frame kuyruğu oluşturulmamalıdır. Gecikme, dropped-frame sayısı ve gerçek FPS gözlemlenebilir olmalıdır.

## 7. Başlangıç veri sözleşmesi

Bir canlı frame paketi kavramsal olarak aşağıdaki bilgileri taşımalıdır:

```text
FramePacket
- frame_index
- host_timestamp_ns
- camera_timestamp_ns
- color_frame
- depth_frame veya depth bilgisine referans
- detected_bodies
- capture_status
- dropped_frame_count
```

Her algılanan kişi için:

```text
BodyPose
- tracking_id
- tracking_state
- body_format
- joint_positions_xyz: [J, 3]
- joint_confidences: [J]
- joint_orientations: isteğe bağlı
- root_position
- root_orientation: isteğe bağlı
```

Kesin alanlar SDK prototipi yapıldıktan sonra sürümlenerek netleştirilecektir.

Her kayıt oturumunda en az şu metadata düşünülmelidir:

- Session ve recording kimliği
- Katılımcı kimliği veya anonim kod
- Başlangıç/bitiş zamanı
- Kamera modeli ve seri numarası
- ZED SDK sürümü
- Uygulama sürümü
- Çözünürlük ve hedef FPS
- Depth ve body tracking ayarları
- Koordinat sistemi ve uzunluk birimi
- Skeleton/body formatı ve joint sırası
- Düşen veya eksik frame istatistikleri
- Kullanıcı notları
- Schema sürümü

Koordinat sistemi ve birim açıkça kaydedilmelidir. Görüntüleme için yapılan eksen değişimleri kaynak koordinatlarla karıştırılmamalıdır.

## 8. Kayıt ve etiketleme yaklaşımı

Ham kayıt, türetilmiş skeleton verisi ve etiketler ayrı tutulmalıdır.

Önerilen kavramsal yapı:

```text
session/
├── session.json
├── raw/
├── derived/
├── annotations/
└── checksums veya manifest
```

ZED’in native kayıt biçimi, skeleton frame kayıtları ve export formatı gerçek SDK prototipinden sonra kesinleştirilecektir. Format kararı verilmeden büyük üretim kaydı yapılmamalıdır.

Annotation kayıtları ileride şu alanları destekleyebilmelidir:

- `annotation_id`
- `recording_id`
- Başlangıç/bitiş frame’i
- Başlangıç/bitiş timestamp’i
- Katılımcı
- Egzersiz
- Doğru/hatalı/kararsız değerlendirme
- Hata türleri
- Etkilenen eklemler veya vücut bölgeleri
- Hareket fazı
- Şiddet
- Güven
- Serbest metin notu
- Annotation durumu: draft/approved/rejected
- Oluşturma ve güncelleme zamanı
- Label schema sürümü

Henüz tanımlanmamış hata sınıfları model tarafından uydurulmamalıdır. Alanlar label ontology belirlenene kadar isteğe bağlı kalabilir.

## 9. GUI için uzun vadeli hedefler

Ana pencere ileride şu alanları destekleyebilir:

- Kamera ve SDK durum paneli
- Bağlan/ayır kontrolleri
- Preview ve recording kontrolleri
- Canlı RGB görünümü
- Canlı depth görünümü
- Canlı 3B skeleton görünümü
- Algılanan kişiler ve aktif tracking ID seçimi
- FPS, gecikme ve dropped-frame göstergeleri
- Session metadata formu
- Kayıt listesi
- Playback ve frame stepping
- Annotation timeline
- Etiket düzenleme paneli
- Dataset doğrulama ve export ekranı
- Log ve hata durumu

Bu hedeflerin hepsi ilk scaffold aşamasında uygulanmayacaktır.

## 10. Mühendislik kuralları

- Python kodu type hint kullanmalıdır.
- Kaynak kod `src/` düzeninde paketlenmelidir.
- Platform hedefi Windows’tur.
- Dosya yolları `pathlib.Path` ile yönetilmelidir.
- Kullanıcıya ait kayıtlar otomatik olarak silinmemeli veya üzerine yazılmamalıdır.
- Kayıt yarıda kalırsa mevcut veri mümkün olduğunca korunmalıdır.
- Uygulama kapanırken kamera ve worker kaynakları kontrollü kapatılmalıdır.
- Loglarda gereksiz kişisel veri bulunmamalıdır.
- Test edilebilirlik için SDK nesneleri arayüzlerin arkasında tutulmalıdır.
- Donanım bulunmadığında unit testler ve mock GUI çalışmaya devam etmelidir.
- Büyük değişikliklerde önce plan, sonra uygulama, ardından test yapılmalıdır.
- Çalışmayan veya doğrulanmamış özellik tamamlanmış gibi belgelenmemelidir.

## 11. Henüz açık olan kararlar

Aşağıdaki konular daha sonra kullanıcıyla netleştirilecektir:

- Kesin uygulama adı
- Hedef Python ve ZED SDK sürümü
- RGB/depth çözünürlüğü ve FPS
- ZED body tracking modeli ve body formatı
- Tek veya çok kişi takibi
- SVO/SVO2 ve türetilmiş veri saklama politikası
- Dataset klasör şeması
- Annotation ontology
- Egzersiz listesi
- Manuel tekrar segmentasyonu
- Otomatik tekrar algılama
- KineSynthV3 joint mapping yöntemi
- Depth frame’lerinin tamamının saklanıp saklanmayacağı
- Uygulamanın paketlenme ve dağıtım biçimi
- Gizlilik, açık rıza ve veri saklama politikaları

Bu kararlar verilene kadar mimari genişletilebilir tutulmalı, fakat gereksiz soyutlama yapılmamalıdır.

## 12. Aşama kaydı

### 12.1 Scaffold aşaması — 2026-08-20

**Durum:** Başlangıç iskeleti tamamlandı. Uygulama mock backend ile çalışıyor,
gerçek ZED entegrasyonu **yapılmadı**.

#### Gerçekten çalışan özellikler

Aşağıdakiler çalıştırılarak doğrulanmıştır (bkz. 12.5):

- Paket ZED SDK olmadan import edilebiliyor; `pyzed` hiçbir zaman modül
  seviyesinde import edilmiyor (alt süreçte `sys.modules` kontrolüyle test
  edildi).
- `python -m kinecapture --diagnose` GUI açmadan ortam raporu üretiyor
  (OS, Python, PySide6, NumPy, PyYAML, pyzed, ZED backend, mock backend).
- Deterministik mock kamera backend'i: aynı seed → byte düzeyinde aynı RGB
  frame ve aynı joint dizileri; `grab_frame()` hiç uyumuyor.
- PySide6 ana penceresi: backend seçimi (Mock/ZED), bağlan/ayır, preview
  başlat/durdur, canlı RGB, canlı 2B skeleton, capture state, frame index,
  ölçülen/hedef FPS, dropped-frame sayacı, durum çubuğu.
- Capture service: sınırlı (bounded) frame tamponu, gerçek drop sayımı,
  idempotent stop/disconnect/shutdown, Qt ana thread'inde bloklayan döngü yok
  (QTimer poll ediyor).
- Test edilmiş capture state machine; geçersiz geçişler
  `InvalidStateTransition` üretiyor.
- Recording/annotation sınırları: sürümlenmiş schema, atomik JSON yazımı,
  mevcut kaydın üzerine yazmayı reddetme, sidecar annotation dosyası.

#### Bu görevde alınan kalıcı teknik kararlar

1. **Ürün adı tek noktada**: `APP_NAME`, `PACKAGE_NAME`, `APP_VERSION` ve schema
   sürümleri `src/kinecapture/__init__.py` içinde. `configs/default.yaml`
   içindeki `app_name` bunu ezebiliyor.
2. **ZED backend bilinçli olarak uygulanmadı.** `camera/zed.py` içinde tek bir
   capture/body-tracking çağrısı yok. Gerekçe: yerel SDK sürümü, Python
   binding'i ve body formatı doğrulanmadı; ezberden yazılan `pyzed.sl` çağrıları
   "bitmiş gibi görünüp" ilk gerçek donanım temasında kırılırdı.
   `is_available()` makine tarafından okunabilir iki kod döndürüyor:
   `pyzed_missing` ve `not_implemented`. `connect/start_preview/grab_frame`
   `CameraUnavailableError` fırlatıyor.
3. **Python 3.10 pinlendi** (`environment.yml`). Bu bir VARSAYIMDIR: ZED SDK 4.x
   Python binding'inin CPython 3.8–3.11 desteklediği bilgisine dayanıyor,
   yerel SDK ile doğrulanmadı. Gerçek makinede doğrulanmalı.
4. **Conda env yalnızca pip'e köprü**: `environment.yml` sadece `python=3.10` ve
   `pip` içeriyor; PySide6/NumPy/PyYAML/pytest editable install üzerinden pip ile
   geliyor. Böylece Windows ve diğer ortamlar aynı sürümleri çözüyor.
5. **Env sahiplik işareti**: `setup_env.ps1`, oluşturduğu environment prefix'ine
   `.kinecapture_project` marker dosyası yazıyor. Aynı adda ama marker'ı olmayan
   bir environment bulursa **durup hata veriyor** (`-AdoptExisting` ile açıkça
   izin verilmedikçe). Var olan hiçbir environment sessizce değiştirilmiyor.
6. **Skeleton topolojisi veri, kod değil**: GUI joint sayısını sabitlemiyor;
   `SkeletonSpec` üzerinden geliyor. Şu an yalnızca 16 eklemli `mock_16` kayıtlı.
   ZED BODY_18/34/38 sıraları **kasıtlı olarak yazılmadı** — doğrulanmış yerel
   SDK'dan okunmalı.
7. **Görüntüleme dönüşümü ham veriye dokunmuyor**: `SkeletonView` içindeki eksen
   çevirme/ölçekleme yalnızca çizim içindir.
8. **`SessionWriter.write_frame()` `NotImplementedError` fırlatıyor.** Sessizce
   hiçbir şey yapmıyor; kayıt formatı ZED prototipinden sonra kararlaştırılacak.
   GUI'deki recording düğmeleri görünür fakat devre dışı.
9. **Atomik yazım**: aynı dizinde geçici dosya + `os.replace`. Yarım kalan JSON
   bırakmıyor.
10. **Kod ve README dili İngilizce**, proje hafızası (`MEMORY.md`) Türkçe kaldı.
    Gerekçe: kod içi terminoloji ve docstring'ler İngilizce standarda uygun;
    hafıza dosyası mevcut diliyle tutarlı tutuldu.
11. **Ek test dosyaları**: PROMPT'taki 4 test dosyasına ek olarak
    `test_capture_service.py` ve `test_recording_and_annotations.py` eklendi
    (bounded queue, idempotency, üzerine yazma koruması gibi güvenlik
    davranışlarını doğrulamak için).

#### Eklenen dosyalar ve bileşenler

```text
README.md, pyproject.toml, environment.yml, .gitignore, .editorconfig
configs/default.yaml
scripts/setup_env.ps1, run_app.ps1, run_tests.ps1
src/kinecapture/__init__.py        -> APP_NAME, sürümler, schema sürümleri
src/kinecapture/__main__.py, app.py-> CLI: --backend, --diagnose, --config, --log-level
src/kinecapture/core/              -> config.py, logging.py, diagnostics.py, state_machine.py
src/kinecapture/domain/            -> enums.py, models.py
src/kinecapture/camera/            -> base.py, mock.py, zed.py (stub)
src/kinecapture/services/          -> capture_service.py
src/kinecapture/recording/         -> session_writer.py
src/kinecapture/annotations/       -> store.py
src/kinecapture/visualization/     -> skeleton_spec.py
src/kinecapture/gui/               -> main_window.py, widgets/{camera_view,session_panel,skeleton_view}.py
tests/                             -> 6 dosya, 63 test
```

#### Conda environment ve bağımlılıklar

- Hedeflenen environment adı: **`KineCaptureStudio`** (`environment.yml`,
  README ve üç PowerShell betiğinde aynı ad kullanılıyor).
- Pinlenen Python: **3.10** (varsayım, bkz. karar 3).
- Runtime bağımlılıkları: PySide6 >= 6.5, NumPy >= 1.24, PyYAML >= 6.0.
- Dev extra: pytest >= 7.4, pytest-qt >= 4.2.
- `pyzed` bilinçli olarak pip bağımlılığı **değil**; ZED SDK ayrı kurulur ve
  `get_python_api.py` proje environment'ı içinde çalıştırılır.

#### 12.5 Çalıştırılan doğrulamalar ve gerçek sonuçlar

Doğrulamalar bu oturumda **izole bir Linux sandbox** içinde yapıldı; kullanıcının
Windows makinesinde çalıştırılamadı (aşağıdaki "Bilinen sınırlar"a bakınız).

| Doğrulama | Komut | Sonuç |
|---|---|---|
| Test paketi | `python -m pytest` | **63 passed**, 0.37 s |
| Tanı komutu | `python -m kinecapture --diagnose` | exit 0; PySide6 6.11.2 / NumPy 2.4.6 / PyYAML 6.0.3 OK, `pyzed` MISS (`pyzed_missing`), mock backend OK |
| GUI dumanı (offscreen) | `QT_QPA_PLATFORM=offscreen python gui_smoke.py` | Pencere kuruldu, mock bağlandı, preview timer ~1 s'de **29 frame** teslim etti (hedef 30 FPS), recording düğmeleri disabled, temiz kapanış |
| ZED'siz import | alt süreçte `import kinecapture...` + `sys.modules` kontrolü | `pyzed` hiç yüklenmedi |
| PowerShell sözdizimi | PowerShell 7.4.6 `Parser::ParseFile` | 3 betik de hatasız |
| `run_app.ps1 -Diagnose` | `conda run` taklit eden stub ile | tanı çıktısı doğru üretildi |
| `run_tests.ps1` (+ `-k <expr>`) | aynı stub ile | 63 passed / filtreli çalıştırma çalıştı |
| `setup_env.ps1` sahiplik koruması | marker'sız sahte `KineCaptureStudio` env | betik environment'ı değiştirmeyi **reddetti** ve yönlendirici hata verdi |

Geliştirme sırasında bulunup düzeltilen gerçek hata: Qt `QComboBox`,
`BackendKind` item data'sını düz `str` olarak geri veriyordu ve
`default_backend_factory` "Unknown backend kind: mock" hatası veriyordu.
Fabrika artık `BackendKind(kind)` ile normalize ediyor; regresyon testi eklendi.

#### Bilinen sınırlar ve eksikler

- **Conda environment gerçekten oluşturulmadı.** Sandbox'ta
  `conda.anaconda.org` erişilemediği için `conda env create` çalıştırılamadı.
  Doğrulamalar aynı bağımlılıkların pip ile kurulduğu izole bir venv içinde
  (Python 3.11.15, Linux) yapıldı. Windows'ta `python=3.10` çözümü ve betiklerin
  gerçek `conda` ile davranışı **doğrulanmamıştır**.
- Betikler Windows PowerShell 5.1'de değil, Linux PowerShell 7.4.6'da denendi.
- ZED SDK, `pyzed` ve gerçek kamera hiç test edilmedi.
- Uygulanmayanlar: ZED backend, gerçek kayıt (SVO/depth/skeleton stream),
  depth görünümü, playback ve frame stepping, annotation timeline UI, dataset
  doğrulama/export, KineSynthV3 joint mapping, çoklu kişi yönetimi,
  ZED skeleton topolojileri, paketleme/dağıtım.

#### Sonraki önerilen adım

1. Windows makinesinde `scripts\setup_env.ps1` çalıştırılıp `KineCaptureStudio`
   environment'ı gerçekten oluşturulmalı; `run_tests.ps1` ve
   `run_app.ps1 -Diagnose` sonuçları buraya yazılmalı.
2. Ardından **gerçek ZED SDK ortam tanılaması ve tek-frame prototipi**: SDK
   sürümü ve desteklediği Python sürümü doğrulanmalı, `pyzed` proje
   environment'ına kurulmalı, kamera bir kez açılıp tek bir frame ve tek bir
   body alınmalı; gerçek joint sayısı, joint sırası, koordinat sistemi ve uzunluk
   birimi bu dosyaya kaydedilmeli. `ZedCameraBackend` ancak bundan sonra
   yazılmalı, kayıt formatı ancak bundan sonra kararlaştırılmalıdır.
