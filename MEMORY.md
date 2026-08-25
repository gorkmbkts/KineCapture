---
document_type: project_memory
project_name: KineCapture Studio
status: rgbd_archive_subject_lock_continuous_working
last_updated: 2026-08-24
app_version: 0.6.0
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

**Uçtan uca dikey dilim + iki seviyeli etiketleme çalışıyor.**

- 2026-08-20: PROMPT.md bölüm 5'teki 15 adımlık akış tamamlandı; hem sentetik
  hem gerçek ZED 2i donanımıyla doğrulandı.
- 2026-08-21: `CLAUDE_ANNOTATION_REDESIGN_PROMPT.md` uygulandı. Etiket modeli
  **iki seviyeye** çıkarıldı (hareket sample'ı + zamansal hata aralığı),
  hareket fazı kaldırıldı, doğru/yanlış ikili hale getirildi, İnceleme ekranı
  ve export sözleşmesi yeniden yazıldı. Ayrıntı: bölüm 6B.
- 2026-08-23: `CLAUDE_SKELETON_FEATURE_EXPORT_PROMPT.md` uygulandı. Ham kayıt
  geriye uyumlu biçimde zenginleştirildi, `kinecapture/features/` altında
  **sürümlü seçilebilir özellik katmanı** kuruldu, export ve Export ekranı bu
  katmanı taşıyacak şekilde genişletildi. Ayrıntı: bölüm 6C.
- 2026-08-24: `CLAUDE_CONTINUOUS_ACTIVITY_RGBD_SUBJECT_LOCK_PROMPT.md`
  uygulandı: **zorunlu ham RGB-D arşivi**, **görüntüye tıklayarak kişi seçimi
  ve kalıcı kişi kilidi**, **sürekli aktivite etiketleme ve dataseti**.
  Ayrıntı: bölüm 6D.
- 2026-08-24: `CLAUDE_CONTINUOUS_ACTIVITY_RGBD_SUBJECT_LOCK_PROMPT.md`
  hazırlandı, **henüz uygulanmadı**. Prompt; mevcut hareket-sample akışını
  koruyarak isteğe bağlı sürekli aktivite/background etiketleme ve exportu,
  zorunlu yeniden işlenebilir RGB-D ham arşivini ve Capture ekranında tıklamayla
  seçilen kişiye kalıcı kimlik kilidini birlikte tarif ediyor. Uygulama kodu ve
  schema sürümleri bu maddeyle değişmiş sayılmaz.

Önceki scaffold aşaması bu sürümle büyük ölçüde değiştirildi. "Değişen
kararlar" bölümleri farkları kaydeder.

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
- Hareket sample'ı CRUD: oluştur, böl, birleştir, dışla/geri al, sil;
  undo/redo; marker'lardan sınır önerisi; çakışma doğrulaması.
- **İki seviyeli etiketleme**: hareket türü + ikili doğru/yanlış (seviye 1),
  hareketin içinde hata sınıfına bağlı zamansal aralıklar (seviye 2). Tek/çok,
  aynı sınıftan tekrarlı ve çakışan aralıklar; aralık ana hareketin dışına
  çıkamaz; ana sınır daralınca kırpma/kaldırma raporlanır ve geri alınabilir.
- **Etiketleme sırasında hata sınıfı oluşturma**: aranabilir seçici, Enter ile
  oluştur-veya-yeniden-kullan, büyük/küçük harf ve boşluk farkına dayanıklı
  tekrar kontrolü, projeye atomik kalıcı yazım.
- Autosave; öncekini kopyala; tümüne uygula; sonraki eksik kayda geç.
- Dataset paneli: sayımlar, filtreler, dağılımlar, kalite bulguları.
- Sürümlü export: `[T,J,3] float32` + manifest + skeleton spec + label
  mapping + feature spec + fingerprint + validation report + excluded;
  staging → atomik yayın; iptal ve hata durumunda hiçbir şey yayımlanmaz.
- **Seçilebilir iskelet özellikleri**: kalite maskeleri, tracker ham çıktıları,
  alternatif koordinat temsilleri, kemik geometrisi, zaman damgası tabanlı
  kinematik, anatomik açılar, bilateral simetri, mesafe/oran proxy'leri ve
  klasik ML için sabit uzunluklu özet vektörü. Export ekranında aranabilir
  seçim + 5 preset.
- Modern GUI: 8 çalışma alanı, daraltılabilir navigasyon, koyu **ve** açık
  tema, 43 vektör ikon (emoji yok), inline form doğrulama, hata bandı,
  klavye kısayolları, kalabalık yan panellerde kaydırma.
- **Tek görüntü alanı**: RGB / İskelet / RGB+İskelet modları; kalıcı iki panel
  yok. Proxy video yoksa iskelet modu çalışmaya devam eder.
- **İki modlu zaman çizelgesi**: HAREKET ve HATA şeritleri; hata modunda seçili
  hareketin dışı maskelenir, çakışan aralıklar ayrı satırlara yığılır, her
  aralık sınıf adıyla birlikte çizilir (yalnız renge bağımlı değil).
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
6. **Etiket aralıkları AKIŞ KONUMUDUR, kamera kare numarası değil.**
   `MovementSample` ve `ErrorInterval` içindeki `start_frame`/`end_frame` =
   `skeleton.jsonl` kare listesindeki 0-tabanlı indeks, **her iki uç dahil**. Kamera kimliği kaybolmuyor: segmentte
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
   ve iç içe iki seviyeli bir aralık editörü sunan hazır bir Qt bileşeni yok.
10. **İkonlar SVG path + QPainter.** Tema rengine göre boyanıyor, DPI'ya göre
    render ediliyor, repository'de binary asset yok. Emoji kullanılmadı.
11. **Etiket ontolojisi veridir.** `label_schema.json` proje başına.
    Varsayılan şema **boş** egzersiz ve **boş** hata türü listesiyle gelir;
    kod içinde uydurma hata sınıfı yok. Kullanıcı hata türlerini etiketleme
    sırasında ekler ve şemaya atomik yazılır (bkz. bölüm 6B).
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

## 6B. İki seviyeli etiketleme redesign'ı (2026-08-21)

### Ürün kararları

1. **Bir hata aralığı = tek hata sınıfı.** Aynı anda görülen farklı sınıflar
   *çakışan aralıklarla* ifade edilir. Böylece her aralık temiz bir
   `(sınıf, başlangıç, bitiş)` üçlüsü olur ve zamansal hedef belirsizleşmez.
   Aynı sınıf bir hareket içinde tekrar edebilir.
2. **Doğru/yanlış ikili.** `Correctness` artık `correct | incorrect |
   unlabelled`. `unlabelled` bir hareket sınıfı değil, "henüz karar verilmedi"
   çalışma durumudur ve asla export edilmez. Eski `uncertain`/`unknown`
   **kesin karara çevrilmez**; `unlabelled` olur ve orijinal değer `legacy`
   içinde saklanır.
3. **`AnnotationStatus` kaldırıldı.** Draft/reviewed/approved yerine
   **türetilmiş** `SampleReadiness` var: `evaluate_sample()` tek kuraldır ve
   hem ekranın "hazır" tanımını hem exportun "uygun" tanımını besler. İkisi
   ayrışamaz. `SegmentStatus.EXCLUDED` kullanıcının açık "datasetten çıkar"
   eylemi olarak korundu.
4. **Tutarlılık kuralları**: doğru + hata aralığı = `contradiction`;
   hatalı + aralık yok = `needs_error_interval` (çalışılabilir, hazır değil);
   ters/boş/dışarı taşan/bilinmeyen sınıflı aralık = `invalid_interval`.
   Hiçbiri export edilmez.
5. **Hareket fazı kaldırıldı** (UI, yeni model, yeni export). Eski değerler
   `legacy.movement_phase` içinde korunur. `severity`, `affected_joints`,
   `annotator_confidence` da aynı şekilde saklanır — kullanılmıyor fakat
   silinmiyor.
6. **Kare sınırı sözleşmesi tek ve belgeli**: konumlar `skeleton.jsonl` kare
   listesindeki 0 tabanlı indekstir ve **her iki uç dahildir**. Arayüz, sidecar
   ve export aynı anlamı kullanır. Export ayrıca göreli konumları
   (`relative_start/end`), kamera kare numaralarını ve zaman damgalarını yazar.
7. **Undo kapsamı**: undo bu kaydın etiketlerini geri alır, **proje çapındaki
   hata sınıfı sözlüğünü değil**. Sınıf oluşturma bir *proje* düzenlemesidir;
   picker "listeye ekler" ve bir aralık fikri değişti diye liste küçülmez.
   Bu davranış hem docstring'de hem arayüz ipucunda yazılı.
8. **Birleştirme kayıp yaratmaz**: farklı etiketli iki hareket birleşirse
   kaybeden etiket `legacy.merged_from` içine yazılır ve kullanıcıya bildirilir.
   Bölme, sınırı aşan hata aralığını ikiye böler; hiçbiri düşmez.
9. **Ana sınır daralması**: kesişen aralıklar kırpılır, tamamen dışarıda kalan
   kaldırılır; ikisi de rapor edilir (`BoundsChangeReport`) ve Ctrl+Z ile geri
   alınabilir.
10. **İskelet-only mod 3B metrik görünüm kaldı** (döndürme + merkezleme).
    Gerekçe: bindirilmiş mod zaten "kamera ile hizalı mı" sorusunu yanıtlıyor;
    derinlik hatası kameranın kendi bakışından görünmez. Sabit projeksiyon
    eklemek yeni bilgi vermezdi.

### Şema ve uyumluluk

- `ANNOTATION_SCHEMA_VERSION` 1.0.0 → **2.0.0**, `LABEL_SCHEMA_VERSION` → 2.0.0.
- Sidecar dosya adı **değişmedi** (`annotations/segments.json`), böylece mevcut
  kayıtlar bulunmaya devam ediyor. v2 `samples` anahtarını yazar; okuma hem
  `samples` hem eski `segments` anahtarını kabul eder.
- **Okuma dosyayı yeniden yazmaz.** v1 belge yalnızca kullanıcı bir düzenlemeyi
  kaydettiğinde v2'ye dönüşür. Projeyi açmak eski etiketi bozamaz.
- `RepetitionSegment` adı `MovementSample`'a taşındı; eski ad alias olarak
  duruyor. `load_segments`/`save_segments` de alias.
- Eski `EvidenceInterval` değerlendirildi ve **yerini `ErrorInterval` aldı**:
  aynı fikir, fakat tek sınıf + kaynak + zaman damgası taşıyor ve ana hareketin
  içinde olması garanti ediliyor. Eski `evidence_intervals` kayıpsız okunuyor.
- Hareket seviyesindeki eski `error_types` listesi zamansız olduğu için
  aralığa **çevrilmiyor**; `legacy.unlocalised_error_types` olarak saklanıyor.
  Sınır uydurmak, veriyi kaybetmekten daha kötü olurdu.

### Export sözleşmesi

- Her hareket sample'ı bir örnek; zaman boyutu hareketin sınırlarından gelir.
- Manifest örneği: `exercise`, ikili `correctness`, `error_intervals[]`
  (sınıf + mutlak + göreli + kamera karesi + zaman damgası), `error_classes`,
  `has_error_localisation`.
- `.npz` içinde ayrıca: `error_intervals` `int32 [K,3]`
  `(class_index, relative_start, relative_end)` ve `error_multi_hot`
  `uint8 [T,C]` (sütun sırası `label_mapping` ile aynı; çakışma aynı karede
  birden çok sütunu 1 yapar). İkisi birlikte yazılıyor: liste otoriter ve
  okunabilir, dizi doğrudan eğitilebilir.
- `label_mapping.error_types.code_to_index` sıralı koddan üretilir → sürümler
  arası kararlı.
- Doğrulama: yetim aralık, dizi dışına taşma, bilinmeyen kod, ters/boş aralık,
  doğruluk-hata çelişkisi, manifest-dizi uzunluk uyuşmazlığı, göreli-mutlak
  tutarsızlığı.
- Fingerprint hata sınıfı ve aralık sınırlarına duyarlı (test edildi).
- **Dışlanan her şey nedeniyle yazılır**: hazır olmayan hareket, kullanıcı
  tarafından dışlanan hareket, filtrelenen kayıt. "Hareketim neden yok?"
  sorusunun cevabı `excluded.json` içinde.
- Geçersiz bir aralık, sample'ın **tamamını** dışlar. Yalnız o aralığı atmak
  modele "burada hata yok" demek olurdu; bu yanlış etiketlemedir.

### Bu turda bulunan gerçek hatalar

1. **v2 round-trip kaybı**: ikinci okumada üst düzey `status` (sample'ın
   active/excluded durumu) eski *annotation review status* sanılıp `legacy`'ye
   yazılıyordu. Yalnız v1 belgede toplanacak şekilde düzeltildi.
2. **Sessiz dışlama**: hazır olmayan hareketler `excluded.json`'a hiç
   yazılmadan eleniyordu. `_partition_samples` + `_rejected_takes` eklendi.
3. **`projects.py` eski sayaç anahtarını okuyordu** (`repetitions`), sayfa her
   açılışta `KeyError` veriyordu.
4. **Zaman çizelgesi şerit başlığı çakışması**: frame 0'da başlayan bir aralık
   "HAREKET" yazısının üstüne biniyordu. Sol gutter (`_GUTTER = 58`) eklendi.
5. 1366x768'de yan panel taşıyordu; aktif modun kartı öne alınıyor, pasif modun
   kartı özet satırına daraltılıyor, transport zaman çizelgesi kartına taşındı.

## 6C. Seçilebilir iskelet özellikleri (2026-08-23)

### Ürün kararları

1. **Canonical veri dokunulmazdır.** `joints_xyz`, `frame_indices`,
   `camera_timestamps_ns` her sürümde yazılır, kapatılamaz ve hiçbir özellik
   onların yerine geçmez. Türetilen her şey ayrı, açık isimli dizi olarak
   *yanına* yazılır. Tek bir belirsiz `[T,J,C]` tensoruna concat yok.
2. **Varsayılan export değişmedi.** Hiçbir özellik seçilmezse üretilen sürüm,
   özellik katmanı yokken üretilenle birebir aynıdır (test edildi).
3. **Kare farkı ile fiziksel hız ayrı kanallardır.**
   `joint_displacement_xyz` = `x[t]-x[t-1]` (FPS'e bağlı), `joint_velocity_xyz`
   = kamera zaman damgasına göre türev (`length_unit/saniye`). KineSynthV3'ün
   mevcut "velocity" kanalı birincisidir; `KineSynth temel uyumluluk` preseti
   bu nedenle fiziksel hızı içermez. Tracker'ın kendi kök hızı
   (`tracker_root_velocity_xyz`) ile türetilen kök hızı
   (`root_velocity_derived_xyz`) de ayrı dizilerdir.
4. **Türev politikası tek yerde**: adım ancak `0 < dt <= 2.5/hedef_fps` ise
   kullanılır; boşluk üzerinden türev alınmaz. Birinci türev iç noktalarda
   merkezi fark, uçlarda tek yanlı; ikinci türevin uçları NaN. Filtre yok.
   İlk hız karesi sahte sıfırla doldurulmaz.
5. **Eksik veri uydurulmaz.** NaN sıfıra çevrilmez, önceki kareyle
   doldurulmaz. Her özellik mümkünse kendi `*_valid_mask` dizisini yazar ve
   doğrulama maske ile NaN düzenini karşılaştırır.
6. **Rol tabloları** (`features/roles.py`) açı/mesafe/simetri tanımlarını
   iskelet biçiminden ayırır. `zed_body_18`'de pelvis yok, `zed_body_38`'de tek
   bir kafa eklemi yok, `mock_16`'da ayak yok — bunlar doldurulmaz, ilgili
   sütun NaN kalır. Rol tabloları sürüm dosyasına yazılır.
7. **Açı, mesafe ve oran tanımları sürümlüdür** (`ANGLE_SET_VERSION` vb.) ve
   sütun sırasını sabitler. 11 açı, 14 mesafe, 3 oran, 10 bilateral çift.
   Üç noktalı açı `atan2(|u x v|, u.v)` ile hesaplanır (0 ve pi civarında
   arccos'tan daha kararlı); sıfıra yakın vektörde NaN.
8. **Simetri gövde uzayında ölçülür.** Kamera koordinatında `sol - sağ` almak,
   kişinin kameraya göre dönmesini asimetri gibi gösterirdi. Sagittal düzlem,
   pelvisten kurulan gövde çerçevesinin `x = 0` düzlemidir. Sonuçlar
   "asimetri teşhisi" olarak adlandırılmaz.
9. **Gövde çerçevesinin ön ekseni sekans başına bir kez** belirlenir (varsa
   boyun→burun/kafa referansıyla, yoksa yalnız sağ el kuralıyla ve bunu
   `forward_source` alanında yazarak). Kare başına karar verilseydi tracker
   gürültüsünde işaret değiştirebilirdi.
10. **Quaternion sırası `xyzw`**, yerel SDK üzerinde doğrulandı: `sl.Rotation`
    ile Y ekseninde +90 derece döndürülünce `[0, 0.7071, 0, 0.7071]` geliyor.
    Quaternion kaynaklı açısal hız `2*arccos(|<qa,qb>|)/dt` ile hesaplanır;
    mutlak iç çarpım `q`/`-q` çift örtüsünü doğrudan çözer, Euler açıları
    hiçbir yerde farklanmaz.
11. **Sabit uzunluklu özet vektörü (307 eleman)** rol/açı/mesafe listelerinden
    üretilir, iskelet biçiminden bağımsızdır; hesaplanamayan eleman NaN kalır,
    uzunluk değişmez. Template mesafesi, sınıf ortalaması, DTW ve dataset
    scaler'ı **bilinçli olarak yoktur** — split leakage yaratırlar.
12. **Klinik iddia yok.** Çıktılar "kinematik özellik" veya proxy olarak
    adlandırılır. `joint_centroid_proxy_xyz` bir kütle merkezi DEĞİLDİR ve öyle
    adlandırılmamıştır. Zemin yüksekliği / ayak teması doğrulanmış world-floor
    kalibrasyonu gerektirdiği için hiç üretilmez.

### Ham kayıt zenginleştirmesi

`BodyPose` şu opsiyonel alanları kazandı; hepsi opsiyonel, eksikse `None`:
`joint_positions_2d [J,2]`, `joint_position_covariances [J,6]`,
`local_joint_positions_xyz [J,3]`, `root_orientation [4]`,
`tracker_root_velocity_xyz [3]`, `root_position_covariance [6]`,
`action_state` (`idle`/`moving`/`unknown`).

- `SKELETON_STREAM_SCHEMA_VERSION` 1.0.0 → **1.1.0** (yalnız ekleme).
  v1 JSONL **migration olmadan** okunur; alanı olmayan kayıtta özellik
  "yok" olarak raporlanır, uydurulmaz.
- Yanlış şekil **reddedilir** (`ValidationError`), asla yeniden şekillendirilmez.
  ZED adapter tarafında ise yanlış/boş şekil `None` olur ve kayıt sürer;
  `BODY_18` gibi biçimlerde fitting çıktılarının olmaması normaldir.
- `root_orientation` daha önce modelde vardı fakat `to_record`/`from_record`
  içinde kayboluyordu — düzeltildi (regresyon testi var).
- **Kovaryansın altı elemanının sırası doğrulanmadı**, bu yüzden ham
  saklanıyor ve "SDK native order" deniyor. Bundan std/belirsizlik
  TÜRETİLMİYOR; prompt'un izin verdiği koşul (sıra doğrulanmışsa) sağlanmadı.
- `keypoint_2d` piksel olduğu için anlamsız kalmasın diye **sol kamera iç
  parametreleri** bağlantı sırasında bir kez okunup take provenance'ına
  yazılıyor (`camera_info.extra.left_camera_calibration`): fx, fy, cx, cy,
  görüntü boyutu, distortion, model. Gerçek kamerada doğrulandı.
- Mock backend yalnız kendi modelinden dürüstçe türetebildiklerini üretir
  (2B projeksiyon, parent'a göre konum, analitik kök hızı, action state);
  quaternion ve kovaryanslar NaN'dır — "ölçülmedi" demek için.

### Feature registry mimarisi

```text
features/base.py         FeatureDefinition, ArrayContract, MappingSupport, SourceField
features/roles.py        anatomik rol -> eklem indeksi (5 iskelet biçimi)
features/definitions.py  sürümlü açı / mesafe / oran listeleri (sütun sırası)
features/temporal.py     dt, boşluk güvenli merkezi/ikinci fark, yol uzunluğu
features/geometry.py     üç noktalı açı, gövde çerçevesi, kemikler, gövde ölçeği
features/compute.py      özellik başına bir fonksiyon + FeatureContext
features/summary.py      sabit uzunluklu özet vektörü ve eleman adları
features/registry.py     sıralı katalog, uygulanabilirlik, presetler, boyut tahmini
features/spec.py         feature_spec.json belgesi
```

Registry bir **tuple**'dır, set değil: fingerprint ve GUI sırası Python set
sırasına bağlı olamaz. 31 özellik, 64 dizi anahtarı. Bağımlılıklar
(`depends_on`) geçişli olarak çözülür; kullanıcı özet vektörünü seçince açılar
otomatik gelir.

### Eklem eşleştirmesi altında davranış

Her özellik `mapping_support` beyan eder:
- `recompute` — geometrik olanlar hedef iskeletin koordinatlarından yeniden
  hesaplanır (test: aynı hareketin diz açısı native ve mapped exportta birebir
  aynı çıkıyor).
- `index_remap` — 2B noktalar, eklem kovaryansları, güven değerleri.
- `native_only` — local quaternionlar ve parent'a göre konumlar. Eşleştirme
  seçiliyken **yazılmaz** (dizi NaN, availability "absent", neden manifestte);
  GUI bunu seçimden önce gri satır ve gerekçeyle gösterir.
- Kısmi eşleştirmede yalnız ilgili kemik/sütun NaN kalır (test: 23/26
  eşleşmede yalnız `Head_end`, `*ToeBase_end` bağlantılı kemikler geçersiz).

### Export sözleşmesi eklemeleri

- `feature_spec.json`: seçilen özellikler ve sürümleri, bütün dizi
  sözleşmeleri, açı/mesafe/kemik/çift/özet sütun adları, birimler, koordinat
  uzayları, zaman hizası, eksik veri politikası, türev politikası, algoritma
  parametreleri, rol tabloları, örnek başına availability istatistiği,
  mapping ve klinik doğrulama uyarısı.
- Manifestte `array_contract` korundu, yanına `feature_contract` eklendi.
- Örnek girdisinde `features` (full/partial/absent), `feature_availability_ratio`,
  `feature_notes`, `array_keys` ve `checksum` var.
- Seçili bir özellik **hiçbir örnekte** üretilemezse `feature_never_available`
  doğrulama hatası verilir ve sürüm "geçti" sayılmaz. Kısmi availability
  uyarıdır.
- `RELEASE_SCHEMA_VERSION` 1.0.0 → **2.0.0**. Eski sürümler değiştirilmez.

### Fingerprint düzeltmesi (gerçek hata)

Örnek sağlama toplamları `_validate()` içinde, yani fingerprint hesaplandıktan
**sonra** ekleniyordu; dolayısıyla fingerprint yazılan dizilerin içeriğine
duyarlı değildi. Artık `.npz` yazılır yazılmaz hash alınıyor, fingerprint
anahtarına giriyor ve doğrulama sırasında yeniden hesaplanıp karşılaştırılıyor.
Fingerprint bileşenleri: `samples`, `export_config`, `skeleton_spec`,
`label_schema`, **`features`**.

### GUI

Export ekranına "Veri ve özellik seçimi" kartı ve aranabilir bir dialog
eklendi: kategori ağacı, satır başına Türkçe ad + şekil/birim + destek durumu
+ deneysel işareti + devre dışıysa gerekçe, 5 preset, arama, seçim özeti.
Önizleme seçili özellik/dizi sayısını, üretilemeyecek özellik sayısını,
filtrelenen kayıt sayısını ve sıkıştırma öncesi tahmini boyutu gösterir.
Son seçim kullanıcı tercihlerine (`export_feature_ids`) yazılır; testler
izole edilmiş `USER_STATE_PATH` kullandığı için gerçek ayar dosyasına
dokunulmaz. Özellik hesapları export worker thread'inde çalışır.

### Kendi araştırmamla EKLEDİKLERİM (promptta yoktu)

1. **Sol kamera iç parametreleri take provenance'ında.** 2B eklem noktaları
   piksel; görüntü boyutu ve intrinsics olmadan yeniden kullanılamaz.
   Kayıttan sonra güvenilir biçimde geri üretilemediği için raw-capture
   alanı yapıldı. Birim piksel, uzay sol kamera görüntüsü.
2. **`body_state` ailesi** (`body_present_mask`, `body_confidence`,
   `tracking_state_code`, `action_state_code`). Takip boşluğu ile "kişi
   duruyor" ayrımı ancak böyle yapılabilir; maskesiz bir NaN neden NaN
   olduğunu söylemez. Kod tablosu spec'te.
3. **`frame_timing` / `delta_time_s`.** Gerçek örnekleme düzensizliğini
   modele göstermenin tek yolu; hedef FPS'ten üretilemez.
4. **`joint_centroid_proxy_xyz`.** COM istenirdi fakat antropometrik model
   yok; dürüst isimle ve "COM değildir" açıklamasıyla eklendi.
5. **`segment_ratios`.** Ham mesafeler kişi boyuna bağlı; kişinin kendi kalça
   genişliğine oranlamak kişiler arası karşılaştırmayı mümkün kılar ve
   dataset genelinden bir şey öğrenmez (leakage yok).
6. **`body_frame_rotation` + `body_frame_valid_mask` ayrı diziler.** Kare
   başına yönelim ile sekans düzeyi ölçek aynı isim altında karışmasın diye.
7. **`root_path_length`** ve **`bone_unit_vectors_xyz`.** İkisi de ucuz,
   yönden bağımsız ve birden çok yaklaşımda anlamlı.
8. **Yazma anında checksum → fingerprint.** Yukarıdaki hata.

### Değerlendirilip EKLENMEYENLER (gerekçeleriyle)

1. **Kovaryanstan türetilen std / belirsizlik elipsoidi.** Altı elemanın sırası
   yerel SDK'dan doğrulanamadı; yanlış sıra sessizce yanlış belirsizlik üretir.
   Ham altı değer saklanıyor, yorum yapılmıyor.
2. **Zemin yüksekliği, ayak teması, adım uzunluğu.** Doğrulanmış world/floor
   kalibrasyonu yok; kamera koordinatındaki `y=0` zemin değildir.
3. **Center of mass, eklem torku, ters dinamik.** Antropometrik model ve
   kuvvet ölçümü gerektirir; uydurma olurdu.
4. **Frekans alanı özellikleri (FFT, spektral güç).** Örnekleme düzensiz ve
   sekanslar kısa; anlamlı bir pencere seçimi ürün kararı gerektirir.
5. **Smoothing / Savitzky-Golay türevleri.** Sessiz yumuşatma yapılmaması
   kuralına aykırı; ileride ayrı ve sürümlü bir özellik olarak eklenebilir.
6. **DTW-to-correct-template, sınıf ortalamasına uzaklık, dataset scaler.**
   Split leakage. Eğitim katmanına ait.
7. **Mask / RGB crop / segmentasyon.** Prompt kapsam dışı bıraktı; boyut ve
   gizlilik açısından da ayrı bir karar.
8. **`bounding_box`, `head_bounding_box`, `dimensions`, `unique_object_id`.**
   SDK'da var fakat iskelet tabanlı ML için yeni bilgi taşımıyor; koordinatlardan
   yaklaşık üretilebilir.

### Bu turda bulunan gerçek hatalar

1. **Fingerprint dizi içeriğine duyarsızdı** (yukarıda).
2. **`root_orientation` diske yazılmıyordu**; model alanı vardı, serileştirme
   yoktu.
3. **Export ekranı ilk açılışta `joint_confidences`'ı düşürüyordu**: kayıtlı
   tercih yokken seçim boş kalıyor, `store_confidences` False oluyordu.
   Tercih yoksa `DEFAULT_FEATURE_IDS` ile açılıyor.
4. **`_build_into` içinde `name` gölgelendi**: opsiyonel alan sayacının döngü
   değişkeni sürüm adının üzerine yazıyordu (self-test sürüm adını
   `tracker_root_velocity_xyz` diye bastı).
5. **Türev maskesinin rankı belirsizdi**: `[T,3]` bir dizi "üç skaler seri" mi
   "bir 3-vektör serisi" mi olduğu tahmin ediliyordu. `vector` parametresi
   zorunlu hale getirildi.

## 6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)

### ÖLÇÜLEREK DOĞRULANAN GERÇEKLER (varsayım değil)

Bu turun en önemli çıktısı bir kod değil, bir ölçüm:

1. **SVO2 replay, ölçülen derinliği geri vermiyor.** Taze bir `capture.svo2`
   yeniden açılıp aynı konumlardan `MEASURE.DEPTH` okunduğunda, kayıt anındaki
   derinlikle **aynı değil**: yer yer 7-14 metre fark, geçersiz piksel maskesi
   bile farklı. Gerçek kayıtta iki kez doğrulandı (3 sn'lik probe ve 20 sn'lik
   canlı kayıt). Derinlik okuma anında yeniden hesaplanır ve depth mode, SDK
   sürümü ve GPU'ya bağlıdır. **Ölçülen derinlik ayrıca arşivlenmezse kalıcı
   olarak kaybolur.**
2. **SVO2 RGB'yi geri veriyor.** Her probe edilen konumdan `(720,1280,4)` RGB
   okundu. Bu yüzden ZED'de renk ikinci kez arşivlenmiyor.
3. **`H264` KAYIPLIDIR.** Ölçülen boyutlar (HD720/30): `H264` 96 MB/dk,
   `H264_LOSSLESS` 1116 MB/dk, `LOSSLESS` 2954 MB/dk. Önceki kod ve docstring
   SVO2'yi "lossless-by-default" diye tanımlıyordu; bu **yanlıştı** ve
   düzeltildi.
4. **Kamera zaman damgası SVO2'ye mikrosaniye çözünürlüğünde yazılıyor**:
   yeniden oynatmada son üç hane sıfırlanmış geliyor (ölçülen fark 300 ns).
5. **SVO kare sayısı canlı kare sayısına eşit olmayabilir**: 601 canlı kareye
   karşı `get_svo_number_of_frames()` 602 döndürdü. 1:1 sıra varsayılmıyor;
   eşleme zaman damgasıyla doğrulanabilsin diye indeks her karede hem konumu
   hem kamera kare numarasını hem zaman damgasını yazıyor.
6. **`get_recording_status()` sayaçları hâlâ güvenilmez**: `ingested=0`,
   `encoded=0` döndürüyor. Tek başarı kanıtı olarak kullanılmıyor.
7. **`store_depth_frames` ölü bir ayardı.** Profilde ve Ayarlar ekranında
   vardı, `TakeWriter` hiç okumuyordu; tooltip'i "SVO2 derinliği yeniden
   üretebildiği için kapalı" diyordu ki bu da yanlıştı. Kaldırıldı, yerine
   zorunlu arşiv politikası ve codec seçimi geldi.

### Derinlik saklama kararı (ölçülerek)

Gerçek ZED derinliği üzerinde, yeni bağımlılık kurmadan:

| şema | MB/dk | kayıpsız |
|---|---|---|
| zlib float32 | 5153 | evet |
| **byteshuffle + zlib-1 (varsayılan)** | **3534** | **evet** |
| temporal XOR + byteshuffle + zlib-1 | 3286 | evet |
| uint16 @1/4000 m + byteshuffle | 1612 | hayır (max hata 0.126 mm) |

Kayıpsızın zayıf sıkışması veriden: bir karede 200 000 pikselin 196 010'u
farklı değer, medyan komşu fark 9 mikrometre. Kodlama hızı ölçüldü: tek
thread 14.6 fps, 3 thread 38.1 fps → chunk sıkıştırma **3 worker thread**'de
çalışıyor (zlib GIL'i bırakıyor).

Varsayılan **kayıpsız float32**. Nicemlenmiş profil isteğe bağlı ve her yerde
"kayıplı" işaretli; ölçek, geçersiz sentinel, adım ve menzil chunk başlığında.

### Ham arşiv mimarisi

```text
raw/capture.svo2                  ZED stereo görüntüleri (H264, kayıplı)
raw/raw_capture_manifest.json     biçim, codec, provenance, senkron sözleşmesi
raw/rgbd/depth_%06d.kcd           ölçülen derinlik, chunk'lı, bağımsız çözülür
raw/rgbd/color_%06d.kcc           yalnız native kayıt yoksa (mock backend)
raw/rgbd/index.jsonl              kare başına senkron indeksi
```

- Chunk = 15 kare (30 fps'te yarım saniye). Her chunk kendi JSON başlığını ve
  payload uzunluğunu taşır; yarım kalan chunk **okurken tespit edilir** ve
  yalnız o chunk kaybolur.
- Her chunk ayrı checksum'lanıyor (`checksum_targets` genişletildi).
- Kuyruk **bounded**; taşarsa kare kaybı sayılır ve gizlenmez.
- `TakeQualityMetrics` beş ayrı sayaç taşıyor: preview, kayıt kuyruğu, renk
  arşivi, derinlik arşivi, backend.
- **Ham arşivi eksik take `FINALIZED` olmaz**, `PARTIAL` kalır ve hiçbir dosya
  silinmez.
- Native kayıt durdurulamazsa hata yutulmuyor; `note_raw_failure` ile take'e
  taşınıyor ve finalize'ı düşürüyor.
- Kayıttan önce disk ön kontrolü: GB/dakika ve kaç dakikaya yettiği gösteriliyor,
  yetmiyorsa `insufficient_disk_space`. Çözünürlük/FPS **sessizce düşürülmüyor**.
- `python -m kinecapture.tools.extract_raw <take> --verify | --out <dir>`
  doğrulama ve çıkarım yapıyor, ham veriye dokunmuyor.

`RAW_ARCHIVE_SCHEMA_VERSION = 1.0.0` eklendi, `APP_VERSION` 0.6.0.

### Kişi kilidi (`capture/subject_lock.py`, algoritma sürümü 1.0.0)

Qt'siz, deterministik, tamamen test edilebilir.

- `subject_id`: kayda özel, seçimde üretilir, **hiç değişmez**.
- `tracker_body_id`: o karede eşlenen SDK kimliği veya yok.
- Durum makinesi: `UNSELECTED → LOCKED → TEMPORARILY_LOST → REIDENTIFYING →
  LOCKED`, çıkmaz olarak `AMBIGUOUS`.
- **En güçlü kanıt eş-görünürlük**: seçili kişiyle aynı karede görülmüş bir
  tracker kimliği tanım gereği başka bir kişidir ve bir daha seçili kişi
  olamaz. Bu, prompt'ta yazmıyordu; ilk sürümde benzer ölçülü ikinci kişiye
  geçiş yaşandığı için eklendi ve gerçek donanımda çalıştığı doğrulandı.
- Diğer kanıtlar: konum sürekliliği (2 sn'den kısa boşlukta, makul yürüme
  hızıyla), uzuv oranları, boy. Ağırlıklar 0.4/0.4/0.2, eksik kanıt lehte
  sayılmaz (coverage ile iskonto edilir).
- Otomatik geçiş yalnız `skor >= 0.62` **ve** ikinci adaya fark `>= 0.15` ise.
  0.5 sn'lik grace, 20 sn sonra tamamen vazgeçip kullanıcıya soruyor.
- Bütün kararlar **ve reddedilen kararlar** audit'e yazılıyor: kare, zaman
  damgası, eski/yeni kimlik, yöntem, skor, fark, gerekçe, adaylar.
- **Gizlilik sınırı**: yüz tanıma yok, görünüm gömülmesi yok, kayıtlar arası
  biyometrik veritabanı yok. İmza yalnız uzuv oranı + boy, kapsamı tek kayıt.
- `VideoView.clicked` artık `(float, float)` görüntü pikseli taşıyor; letterbox
  ve DPI hesaba katılıyor. Hit testing tracker'ın kendi `joint_positions_2d`
  verisini kullanıyor (kesin), yoksa aday üretilmiyor. İki kişi 25 pikselden
  yakınsa seçim yapılmıyor. Tıklama **görüntülenen** karede çözülüyor
  (`packet=self._last_packet`), sonradan gelen karede değil.
- Kayıt sırasında sıradan tıklama kişiyi değiştirmiyor; ayrı "Kimliği yeniden
  doğrula" eylemi var ve olay üretiyor.
- `skeleton.jsonl` bütün gövdeleri saklamaya devam ediyor; yanına kare başına
  `subject` bloğu yazılıyor. `SkeletonFrame.subject_body()` **fallback
  yapmıyor**; `body()` (görüntüleme yardımcısı) yapıyor ve docstring'i bunu
  söylüyor.

### Sürekli aktivite (`domain/activity.py`, `export/continuous.py`)

- Dört karşılıklı dışlayan durum: `background`(0), `transition`(1),
  `target_exercise`(2), `other_activity`(3). **Etiketlenmemiş = -1 ve bir sınıf
  değil.**
- Çakışma domain'de reddediliyor; yeni aralık boş alana kırpılıyor, tamamen
  doluysa hata.
- `target_exercise` bir `MovementSample`'a bağlanabiliyor; bağlıyken **sınırın
  tek kaynağı hareket**. Bağlı aralığın sınırı doğrudan düzenlenemiyor, hareket
  taşınınca birlikte taşınıyor. Bağlama, komşuyla çakışacaksa reddediliyor.
- "Boşlukları arka plan yap" **açık onay** istiyor (`confirmed=True`), GUI'de
  ayrıca ne iddia edildiğini anlatan bir onay kutusu var.
- `evaluate_continuous` tek kural; hem İnceleme ekranı hem exporter kullanıyor.
  Hareket-sample hazırlığından **bağımsız**.
- Annotation şeması yalnız ekleme yönünde genişledi: sidecar'a
  `activity_intervals` anahtarı eklendi, dosya adı ve `samples` değişmedi.
  Anahtarı olmayan eski dosya boş strip olarak okunuyor ve **okurken yeniden
  yazılmıyor**. `save_samples(activity_intervals=None)` diskte olanı koruyor,
  yani aktivite katmanını bilmeyen bir çağıran onu silemiyor.
- Undo/redo iki katmanı **birlikte** anlık görüntülüyor (`_State`).

### Sürekli export sözleşmesi

Bir örnek = bir kayıt, gerçek `T`. `continuous/` dizini + `activity_spec.json`.
Diziler: `joints_xyz`, `frame_indices`, `camera_timestamps_ns`,
`subject_present_mask`, `subject_source_tracking_id`,
`subject_association_confidence`, `activity_state_code`, `activity_label_mask`,
`exercise_active`, `exercise_class_index`, `exercise_class_valid_mask`,
`exercise_start_target`, `exercise_end_target`, `correctness_code`,
`error_label_mask`, `error_multi_hot` + seçilen feature dizileri.

Üç ayrım hiç bulanıklaşmıyor ve doğrulamada kontrol ediliyor:
etiketlenmemiş ≠ arka plan, kişi yok ≠ kişi hareketsiz, hata etiketi yok ≠
hata yok.

- Ham RGB-D **kopyalanmıyor**; manifest checksum'lu referans taşıyor.
- `split_group_id = take_id`; aynı kayıttan türetilen pencereler bölünemez.
- Fingerprint'e `dataset_modes` ve `activity_contract` sürümü girdi; sürekli
  örneğin anahtarı aktivite aralıklarını, kişi özetini, ham kaynak
  checksum'larını ve dosya checksum'unu içeriyor.
- Varsayılan export **değişmedi**: yalnız hareket örnekleri.
- Sürekli mod seçiliyken `select_rows` "hazır hareket" şartını kaldırıyor —
  aksi hâlde hiç egzersiz içermeyen negatif kayıtlar hiç görünmezdi.
- Kişi kilidinden önce alınmış kayıtlar `legacy_active_body: true` diye
  işaretleniyor ve doğrulama uyarısı üretiyor; otomatik migration yok.

### Bu turda bulunan gerçek hatalar

1. **`store_depth_frames` ölü ayardı** ve tooltip'i yanlış bir iddia taşıyordu.
2. **SVO2 "lossless" diye belgeleniyordu**; gerçekte H264 (kayıplı).
3. **`stop_native_recording` hatası yutuluyordu**; take başarılı görünebiliyordu.
4. **`link_activity_to_sample` sessizce çakışma yaratabiliyordu**: hareketin
   sınırlarını benimserken komşuyu kontrol etmiyordu, sonuç etiketli görünen
   fakat export edilemeyen bir kayıttı.
5. **Sürekli export, hazır hareket örneği olmayan kayıtları hiç görmüyordu**
   (`exportable_rows` filtresi) — tam da sürekli datasetin ihtiyaç duyduğu
   negatif örnekler eleniyordu.
6. **Kişi kilidi olmayan eski kayıtlar tamamen NaN sürekli örnek üretiyordu**;
   şimdi dürüst legacy yolu var ve manifestte işaretleniyor.
7. **Türev, kişinin görülmediği karede değer üretiyordu**: merkezi fark yalnız
   iki komşunun sonlu olmasını arıyordu. Artık farkı alınan karenin kendisi de
   sonlu olmalı.
8. **Tıklama sonraki karede çözülüyordu**; artık kullanıcının gördüğü karede.

### Bilinçli olarak sonraya bırakılanlar

- SVO2 özel veri kanalı (`ingest_data_into_svo`) ile subject association'ı
  SVO'nun içine yazmak. Mümkün görünüyor fakat ikinci bir doğruluk kaynağı
  yaratır; şimdilik indeks + sidecar tek kaynak.
- Görünüm tabanlı re-identification (kıyafet crop deskriptörü). Gizlilik
  sınırını genişletir; eş-görünürlük + oran kanıtı gerçek testte yeterli oldu.
- Çok kişili eşzamanlı kayıt (birden fazla subject lock).
- `other_activity` için kullanıcı tanımlı alt türler (ontoloji kararı).
- Hata aralığı başına etkilenen eklem / şiddet rubriği / annotator confidence
  ve zamansal faz aralıkları — hâlâ ayrı bir uzman ontoloji kararı gerektiriyor;
  mimari eklenmelerini engellemiyor.
- Sürekli örnekten pencere üretimi ve dengeleme: eğitim katmanının işi.

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
export/         ReleaseBuilder (staging → atomik yayın) + continuous.py
features/       sürümlü seçilebilir özellik katmanı ← Qt ve pyzed içermez
capture/subject_lock.py   kişi kilidi durum makinesi ← Qt ve pyzed içermez
recording/rgbd_archive.py chunk'lı ham RGB-D arşivi, worker havuzu
domain/         enums, models, project, labels, activity  ← Qt ve pyzed içermez
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
| Test paketi | `python -m pytest` | **528 passed**, 0 warning, 160.1 s (2026-08-24) |
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

### Redesign doğrulaması (2026-08-21, donanımsız)

Yeniden tasarım sonrası gerçekten çalıştırıldı:

```text
python -m pytest                    314 passed, 92.9 s
python -m kinecapture --self-test   exit 0
  hareket/hata etiketleme   : OK (2 hareket, 1 zamansal hata aralığı)
  dataset index             : OK (1 kayıt, 2 hazır hareket, 1 hata aralığı)
  export                    : OK (dataset_v001, 2 örnek, 1 hata aralığı,
                                  doğrulama=geçti)
```

Ayrıca elle doğrulandı: v1 sidecar → v2 kayıpsız okuma (eski `segment_id`
korunuyor, `uncertain` → `unlabelled` + `legacy`, `evidence_intervals` →
gerçek `ErrorInterval`, dosya okuma sırasında **değişmiyor**), v2 round-trip
kararlı, çakışan iki sınıfın 5 ortak karesi `error_multi_hot` içinde iki sütun
olarak görünüyor, fingerprint aralık ekle/taşı/sınıf değiştir/sil işlemlerinin
dördünde de değişiyor, sayfalar 1600x980 **ve** 1366x768'de taşmadan
çiziliyor.

**Redesign donanımda test edilmedi.** Etiketleme ve export kamera
gerektirmiyor; bu turda 2026-08-20'deki gerçek ZED 2i kaydı yeniden
alınmadı. Kayıt hattı (`camera/`, `capture/`) bu turda değişmedi.

### Ham arşiv / kişi kilidi / sürekli aktivite doğrulaması (2026-08-24)

```text
python -m pytest                    528 passed, 160.1 s, 0 warning
python -m kinecapture --self-test   exit 0
  aktivite etiketleme       : OK (3 aralık, kapsam %97, 2 kare etiketsiz)
  ham RGB-D arşivi          : OK (65 derinlik, 65 renk karesi, float32_byteshuffle_zlib)
  export                    : OK (2 hareket örneği, 1 sürekli örnek, doğrulama=geçti)
```

**GERÇEK ZED 2i ile doğrulandı** (kullanıcı kadraja girdi, görüntüde kendi
üzerine tıkladı, 20 sn kayıt aldı; kadrajda zaman zaman birden fazla kişi
vardı):

```text
connect              3.8 s · ZED 2i S/N 31844341 · SDK 5.4.1
ham arşiv tahmini    3.63 GB/dk, boş alan 56 dakikaya yetiyor
KAYIT                601 kare / 20.00 s / 30.0 FPS · durum=finalized
AKIŞ KAYIPLARI       kayıt kuyruğu=0  renk=0  derinlik=0
ARŞİVLENEN           601 derinlik karesi (renk SVO2'de, ikinci kopya yok)

KİŞİ KİLİDİ          kilitli=601  kayıp=0  belirsiz=0  yeniden eşleştirme=0
kapsam               %100.0
ÇOKLU KİŞİ KARESİ    554   (kadrajda başka insanlar vardı)
görülen tracker ID   [1, 2, 3]
DİSKALİFİYE ID       [2, 3]   <- eş-görünürlük kuralı gerçek veride çalıştı
olaylar              yalnız 1 tane: subject_selected

HAM ARŞİV            601 derinlik karesi · chunk sorunu=0 · checksum uyuşmazlığı=0
SVO2                 var · sıkıştırma=H264 · lossless=False
BOYUTLAR             SVO2 34.2 MB · derinlik 1202.0 MB (20 saniye için)
SENKRON İNDEKS       601 satır
  ilk: p=0   i=3603 cam_ns=1787578786176571501 subj=locked
  son: p=600 i=4203 cam_ns=1787578806177876501 subj=locked
     ^ konum 0'dan, kamera kare numarası 3603'ten başlıyor: ikisi AYNI ŞEY DEĞİL

SVO2 YENİDEN OKUMA
  pos   0: RGB (720,1280,4) okundu · saklanan derinlikle aynı mı: HAYIR (max fark 13.22 m, maske farklı)
  pos 301: RGB okundu · aynı mı: HAYIR (max fark 14.36 m, maske farklı)
  pos 599: RGB okundu · aynı mı: HAYIR (max fark  6.85 m, maske farklı)
  SVO2 kare sayısı 602, canlı kare 601  <- 1:1 sıra varsayılamaz

ETİKETLEME           1 hareket + 1 hata aralığı · aktivite kapsamı %100 · sürekli: ready
EXPORT               1 hareket örneği + 1 sürekli örnek · doğrulama GEÇTİ
  sürekli örnek      T=601 · 24 dizi · etiketsiz kare=0
  sınıf dağılımı     {background: 200, target_exercise: 201, other_activity: 200}
  kişi kapsamı       %100 · otoritatif ilişkilendirme=True
  subject_present    601/601
```

Bu çıktının en kritik iki satırı: **554 karede birden fazla kişi vardı ve kilit
hiç kaymadı**, ve **SVO2'den yeniden okunan derinlik saklanan derinlikle aynı
değil**. İkincisi bu turdaki bütün depolama maliyetinin gerekçesidir.

**Donanımda doğrulanamayan:** otomatik yeniden ilişkilendirme (`reassociated`)
bu kayıtta **tetiklenmedi** — seçili kişi hiç kaybolmadı, tracker kimliği hiç
değişmedi. O yol yalnız deterministik stub testleriyle doğrulandı
(`tests/test_subject_lock.py`): yeni kimlikle dönüş, iki benzer aday,
uzun kaybolma, kimlik yeniden kullanımı, antrenör senaryosu.

### Özellik katmanı doğrulaması (2026-08-23)

```text
python -m pytest                    438 passed, 121.9 s
python -m kinecapture --self-test   exit 0, export doğrulama=geçti
```

**GERÇEK ZED 2i ile doğrulandı** (kullanıcı kameranın önünde, canlı önizleme
penceresiyle kadraj kontrol edilerek):

```text
connect                3.8 s
model/serial/sdk       ZED 2i / 31844341 / 5.4.1
sol kamera intrinsics  fx=949.9 fy=949.9 cx=635.8 cy=350.7  1280x720  PINHOLE
KAYIT                  362 kare / 12.07 s / 29.9 FPS
VERİ KAYBI             YOK — dropped=0, missing=0, max_gap=66.6 ms
GÖVDE TAKİBİ           coverage=1.00, mean_joint_conf=0.888, distinct_ids=1

OPSİYONEL TRACKER ALANLARI (hepsi %100 sonlu, 362 kare x 34 eklem):
  joint_orientations          (362,34,4)  aralık [-0.763, 1]
  joint_positions_2d          (362,34,2)  aralık [34.5, 1311] piksel
  joint_position_covariances  (362,34,6)  aralık [-0.084, 0.120]
  local_joint_positions_xyz   (362,34,3)  aralık [-0.417, 0.264]
  root_position               (362,3)
  root_orientation            (362,4)
  tracker_root_velocity_xyz   (362,3)     aralık [-0.436, 0.439] m/s
  root_position_covariance    (362,6)
  action_state_code           idle=310, moving=52   (tracker gerçekten ikisini de veriyor)
  tracking_state_code         ok=362

EXPORT                 dataset_v001 · 2 örnek · doğrulama GEÇTİ
                       61 dizi / örnek, örnek şekli (120, 34, 3) float32
ÖLÇÜLEN DEĞERLER       joint_speed mean=0.381 max=3.867 m/s
                       sağ diz açısı 130.0°..180.0°, sol diz 172.1°..180.0°
                       gövde eğimi 0.2°..7.5°, body_scale 1.289 m
                       summary vector 307/307 eleman sonlu
                       quaternion normları mean=1.0000 (4080 örnek)
```

Son satır kritik: quaternion normlarının tam 1.0000 çıkması, `xyzw` okumasının
ve birim quaternion varsayımının gerçek veride doğrulandığını gösteriyor.
`joint_positions_2d` aralığının 1280 pikseli birkaç piksel aşması, kadrajın
kenarındaki eklemler için beklenen davranıştır.

`frame_timing`, `joint_displacement` ve `joint_acceleration` "kısmi"
raporlanıyor — tasarım gereği: ilk karede dt/yer değiştirme, ilk ve son karede
ivme NaN'dır.

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
- Çok kişili eşzamanlı kayıt (birden fazla subject lock).
- Görünüm tabanlı re-identification (gizlilik sınırını genişletir).
- SVO2 özel veri kanalına (`ingest_data_into_svo`) subject association yazmak.
- `other_activity` için kullanıcı tanımlı alt türler.
- Zaman çizelgesinde reviewer yorum katmanı.
- Hata sınıflarının hiyerarşisi/gruplanması (şu an düz liste).
- Bir hata aralığını başka bir harekete taşıma (şu an sil + yeniden çiz).
- Kovaryanstan türetilen belirsizlik (eleman sırası doğrulanmadı).
- Zemin/dünya kalibrasyonu ve ona bağlı özellikler (ayak teması, adım).
- Sürümlü ve açıkça işaretlenmiş smoothing/filtre özellikleri.
- Hata aralığı başına etkilenen eklem / body region, şiddet rubriği,
  annotator confidence ve zamansal faz aralıkları. Bunlar ayrı bir ontoloji
  kararı gerektirir; feature/export mimarisi ileride bu hedef dizilerinin
  eklenmesini engellemiyor (yeni FeatureDefinition + yeni array key yeter).
- Paketleme / dağıtım (installer).

## 12. Sonraki önerilen adım

1. **Daha uzun ve kontrollü çekim yapın** (2–3 dakika, tam görüş alanında).
   4 saniyelik dumanda `tracking_coverage` 0.45 çıktı; kişinin çerçeveye
   girip çıkmasından kaynaklanıyor olabilir. Gerçek çekim mesafesi ve
   kamera yüksekliği için kapsamın ne olduğunu ölçüp bu dosyaya yazın.
2. Proje etiket şemasına gerçek egzersiz listesini ve hata ontolojisini
   girin (Ayarlar → Etiket şeması). Kod içinde uydurulmuş sınıf yok.
3. ZED ilk-açılış optimizasyonunu iptal edilebilir arka plan işine taşıyın.
4. Birkaç gerçek kaydı iki seviyeli modelle baştan sona etiketleyip
   export alın; hata sınıfı listesi ancak gerçek kullanımla oturur.
5. Otomatik tekrar algılamayı `SegmentSource.MODEL_SUGGESTION` olarak
   ekleyin; insan onayı olmadan ground truth sayılmamalı (altyapı hazır).
6. Zamansal hedefi (`error_multi_hot`) tüketen ilk eğitim betiğini yazıp
   sözleşmenin gerçekten kullanışlı olduğunu doğrulayın.
7. `Klasik ML` presetiyle bir sürüm alıp `summary_features` üzerinde bir
   Random Forest baseline'ı çalıştırın; 307 elemanın hangilerinin gerçekten
   ayırt edici olduğunu ölçün ve işe yaramayanları bir sonraki summary
   sürümünde ayıklayın.
8. Kovaryans eleman sırasını Stereolabs dokümantasyonundan veya bilinen bir
   duruşla deneysel olarak doğrulayın; doğrulanırsa `joint_position_std`
   türetilmiş özelliği eklenebilir.
9. **Disk planlaması yapın.** Kayıpsız derinlik 3.5 GB/dakika. 20 dakikalık bir
   oturum ~70 GB. Uzun protokoller için ya ayrı bir disk ya da nicemlenmiş
   derinlik profili gerekiyor; ikisi de bilinçli bir karar olmalı, kayıt
   sırasında sürpriz olmamalı.
10. **Otomatik yeniden ilişkilendirmeyi gerçek donanımda tetikleyin**: seçili
   kişi kadrajdan tamamen çıkıp geri girsin, kadrajda başka biri varken de
   deneyin. Şu ana kadar yalnız stub testleriyle doğrulandı.
11. Birkaç gerçek oturumu AKTİVİTE modunda baştan sona etiketleyip sürekli
   dataset alın; sınıf dengesi ve `unlabelled` oranı ancak gerçek kullanımla
   görülür.
