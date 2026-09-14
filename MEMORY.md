---
document_type: project_memory
project_name: KineCapture Studio
status: backend_capture_processing_architecture_implemented_awaiting_live_zed_validation
last_updated: 2026-09-11
app_version: 0.11.0
---

# KineCapture Studio — Proje Hafızası

> **BU BİR ARŞİVDİR. BAŞTAN SONA OKUNMAZ.**
> Giriş noktası **`MEMORY_INDEX.md`**'dir (≤6 KB): güncel faz, sürüm tablosu,
> modül haritası, aşağıdaki bölümlerin dizini, bilinen açıklar, sonraki adım.
> Önce onu oku; buradan **yalnızca** görevinin dokunduğu bölümü, indeksin
> verdiği satır aralığıyla hedefli aç. Kısa kalıcı talimatlar `CLAUDE.md`
> (Claude) ve `AGENTS.md` (Codex) içindedir.

## 1. Bu belge nasıl kullanılmalı?

Bu dosya, ZED 2i tabanlı veri toplama ve etiketleme uygulamasının Claude ve
Codex tarafından paylaşılan kalıcı proje hafızasıdır. Bir arşivdir; oturum
başına tamamını okumak ciddi bağlam israfıdır ve bu kural **kaldırılmıştır**.

### Okuma

1. Her görevde önce `MEMORY_INDEX.md` okunur.
2. Bu dosyadan yalnız ilgili bölüm, hedefli olarak (grep veya satır aralığı)
   açılır. Görevin dokunmadığı bölüm açılmaz.
3. Ardından repository içindeki gerçek dosyalar incelenir.
4. Buradaki kararlarla kod arasında çelişki varsa bu belirtilmeli ve **gerçek
   kod** doğrulanmalıdır; kod hafızadan önceliklidir.
5. Kararlaştırılmamış ürün ayrıntıları kendiliğinden kesinleştirilmez.

### Yazma

6. Buraya **yalnızca kalıcı bir şey öğrenildiğinde** yazılır: mimari karar,
   gerçekten çalıştırılmış doğrulama sonucu, sürüm/şema değişikliği, kapanmış
   veya yeni açılmış bir bilinmeyen. Küçük düzeltme, biçimlendirme, yeniden
   adlandırma ve başarısız deneme yazılmaz.
7. "Her görev sonunda hafıza güncellenir" kuralı kaldırılmıştır; yerine
   "kalıcı bilgi üretildiğinde yazılır" geçmiştir.
8. Durum değiştiyse `MEMORY_INDEX.md` güncellenir — bu kısa dosyanın güncel
   kalması arşivin güncel kalmasından önemlidir.
9. Bu dosya sonsuza kadar büyümez: şişen bölümün eski ayrıntısı özetlenerek
   sıkıştırılır, aynı bilgi iki yere yazılmaz.

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
- 2026-08-26: `CODEX_AUTH_PROJECT_PARTICIPANT_REDESIGN_PROMPT.md` uygulandı:
  **tek Sistem Sahibi**, normal kullanıcı self-registration, SQLite kimlik ve
  proje erişimi, girişle otomatik operatör bağlama, sade Projeler/Katılımcılar
  akışı ve kullanıcıdan gizlenen otomatik çekim oturumu. Ayrıntı: bölüm 6E.
- 2026-08-28: `CLAUDE_CAPTURE_REVIEW_LABELING_UI_PROMPT.md` uygulandı.
  Capture'ın kalıcı sağ sütunu modeless bilgi penceresine taşındı, İnceleme
  ekranı yalnızca kayıtta seçilmiş kişiyi çizer hale getirildi, RGB bindirme
  hizası kök nedeninden (proxy/kamera piksel uzayı karışması) düzeltildi,
  etiketleme iki küçük diyaloga indirildi ve aktivite yazımı emekliye ayrıldı
  (veri korunarak). Ayrıntı: bölüm 6G.
- 2026-08-30: `CLAUDE_PROJECT_DELETE_LABELING_EXPORT_GUI_PROMPT.md` uygulandı.
  Doğru/hatalı kararı hata aralıklarından türetilir hale geldi (annotation
  2.1.0), yalnız Sistem Sahibinin kullanabildiği kalıcı proje silme eklendi,
  zaman çizelgesi sürüklemesine kare önizlemesi ve tek commit getirildi, export
  modelden bağımsız hale getirildi, Export/Ayarlar/Dataset/Projeler duyarlı
  yapıldı ve NavigationRail'e paketlenmiş YTÜ logosu eklendi. Ayrıntı: bölüm
  6I.

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

## 6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)

### Kesin ürün kararları

1. **Tek Sistem Sahibi vardır.** İlk kurulumdaki ilk hesap `owner` olur;
   SQLite partial unique index ikinci owner'ı DB düzeyinde de reddeder. Owner
   silinemez, pasifleştirilemez, role dönüştürülemez ve bütün projelere örtük
   erişir. İlk sürümde yalnız `owner | user` rolleri vardır.
2. **Self-registration yalnız normal kullanıcı üretir.** Giriş ekranındaki
   `Yeni Kullanıcı Oluştur` ad, soyad, isteğe bağlı unvan, kullanıcı adı,
   parola ve parola doğrulaması alır. Başarıda giriş formuna yalnız kullanıcı
   adı taşınır; parola taşınmaz veya tercihlere yazılmaz.
3. **Koç akışı** `giriş → proje → katılımcı → Kayda Başla → Capture`'dır.
   Operatör adı, teknik oturum formu ve tek plan varken plan seçimi sorulmaz.
4. **Protokol domain adı korundu, kullanıcı dili değişti.** Python'daki
   `CaptureProtocol` ve dosya alanları geriye uyumluluk için aynı; yeni bütün
   kullanıcı metinlerinde kavram **Kayıt Planı** olarak sunulur.
5. **Eski test datasetleri migrate edilmez ve SQLite'a otomatik kaydedilmez.**
   Owner isterse gelişmiş `Klasörden içe aktar` eylemiyle doğrulanmış bir
   projeyi kaydedebilir. Böylece eski klasör var diye yetkisiz proje açılmaz.

### SQLite kimlik ve erişim katmanı

Yeni `kinecapture/identity/` paketi katmanları:

```text
database.py    kısa ömürlü bağlantı, PRAGMA, idempotent schema/transaction
repository.py  yalnız parametreli SQL sorguları
passwords.py   sürümlü scrypt türetme ve sabit-zaman karşılaştırma
service.py     kimlik doğrulama, owner kuralları, yetki ve proje koordinasyonu
models.py      User / ProjectAccess değer nesneleri; parola alanı içermez
```

- Windows varsayılan DB konumu:
  `%LOCALAPPDATA%\KineCapture\identity.sqlite3`. Datasetin ve
  `~/.kinecapture/user_state.yaml` tercihlerinin dışında, kullanıcı tarafından
  proje sanılmayacak deterministik bir konumdur. `AppConfig.identity_db_path`
  testlerde geçici yol enjekte eder ve tercih dosyasına yazılmaz.
- **Identity schema v1**: `users`, `projects`, `project_access`, `audit_log`,
  `app_metadata`. Sürüm hem `PRAGMA user_version=1` hem metadata tablosunda.
  Kurulum tekrar çalıştırılabilir. `foreign_keys=ON`, `busy_timeout=5000`,
  açık `BEGIN`/`BEGIN IMMEDIATE` ve bağlantı kapanışı var.
- Journal mode bilinçli olarak **DELETE**: işlemler kısa/yerel; kalıcı WAL
  sidecar'ları olmadan DB'nin yedeklenmesi ve taşınması daha güvenli. Büyük
  bilimsel veri hiçbir zaman SQLite'a girmez.
- Kullanıcı adı NFKC + `casefold` ile normalize edilir ve DB'de case-insensitive
  benzersizdir. Görünen ad 3-64 ASCII harf/rakam/nokta/alt çizgi/kısa çizgiyle
  sınırlıdır. SQL'in tamamı parametrelidir.
- Parola en az 8 karakterdir. `hashlib.scrypt` (`scrypt-v1`, N=16384, r=8,
  p=1, 32-byte çıktı), 16-byte kriptografik rastgele salt ve parametre JSON'u
  ayrı alanlarda tutulur; `secrets.compare_digest` kullanılır. Açık parola,
  geçici parola ve hash loglanmaz. Tercihler yalnız `last_username` saklar.
- Başarısız giriş kullanıcı adı/parola ayrımını açıklamaz; pasif hesap özel
  fakat güvenli bir pasiflik mesajıyla reddedilir. Başarılı giriş
  `last_login_at` günceller. Admin reset'i `must_change_password=1` yapar ve
  zorunlu değişim tamamlanmadan çalışma alanı gösterilmez.

### Proje sahipliği ve yetki

- `projects` aynı `project_id`'nin doğrulanmış, normalize edilmiş tek klasör
  yolunu ve `owner_user_id`'yi tutar. Aynı kimliğin farklı klasöre bağlanması
  reddedilir.
- Normal kullanıcı yalnız sahibi olduğu veya `project_access` ile atanmış
  projeleri listeler. Owner bütün kayıtlı projeleri ayrı erişim satırı olmadan
  görür. Normal kullanıcının oluşturduğu proje otomatik onun mülkiyetine ve
  erişimine girer.
- Dosya sistemi proje oluşturma başarılı fakat DB kaydı başarısız olursa yalnız
  o çağrının yeni, doğrulanmış `dataset_root/projects/<project_id>` dizini
  telafi olarak kaldırılır. Erişim kaldırma hiçbir proje dosyasını silmez.
- `AppState.open_project`, proje/katılımcı listeleme-oluşturma,
  `prepare_capture`, kayıt öncesi doğrulama ve admin işlemleri servis katmanında
  aktif kullanıcı + erişim kontrolünü tekrar yapar. `last_project_path`
  doğrudan açılmaz; tek erişilebilir proje otomatik açılır, sıfır/çok projede
  Projeler sayfası gösterilir.

### Minimum katılımcı ve otomatik çekim oturumu

- Yeni `Participant`: `participant_id`, `code`, `created_at`,
  `created_by_user_id`, `schema_version`. Boy, kilo, dominant taraf ve serbest
  not yeni modelden ve Katılımcılar ekranından çıkarıldı.
- `participant_id == code` (`P0001`, `P0002`, ...). Kod proje içinde anonim,
  değişmez ve kompakt kalıcı kimliktir. Kompaktlık Windows'taki derin take
  yollarının üçüncü taraf araç sınırını aşmaması için önemlidir.
- Kod + proje sayacı, proje kökündeki exclusive allocation lock altında
  birlikte güncellenir. Ayrı `ProjectWorkspace` nesnelerinden eşzamanlı 12
  tahsis testi `P0001..P0012` sonucunu verdi.
- Katılımcılar sayfası arama, kod, kayıt sayısı, son kayıt zamanı,
  `Katılımcı Ekle`, `Kayda Başla` ve `Kayıtlarını Gör` içerir. Manuel oturum,
  onam, operatör ve biyometrik form yoktur.
- `Kayda Başla` erişimi yeniden doğrular; tek planı otomatik, plan yoksa
  serbest modu seçer, yalnız birden fazla planda kısa seçim ister. Aynı uygulama
  çalışmasında aynı kullanıcı/proje/katılımcı/plan için uygun açık otomatik
  session yeniden kullanılır.
- Proje/katılımcı değişimi, logout ve güvenli kapanış otomatik session'ı
  `ended_at` + neden ile kapatır. Önceki uygulama çalışmasından açık otomatik
  session yeni çekimde deterministik olarak orphan sayılıp kapatılır; sessizce
  aktif kabul edilmez.
- `Session.operator` okunabilir ad snapshot'ıdır; yeni
  `Session.operator_user_id` kalıcı kullanıcı bağlantısıdır. Aynı alan
  `Take.operator_user_id` içine de kopyalanır; kullanıcı adı değişse bile kayıt
  operatörü kaybolmaz.

### GUI

- `MainWindow` çalışma shell'ini `AuthPage` arkasında tutar; kimlik doğrulama
  bitmeden sayfalar ve last-project açma görünür/aktif değildir.
- İlk kurulum, normal login, parola göster/gizle, Enter ile login, alan bazlı
  self-registration, zorunlu parola değiştirme ve owner-only
  `Kullanıcılar ve Erişimler` dialogu eklendi.
- Admin dialogu ad/unvan/kullanıcı adı/durum/proje sayısı/son giriş gösterir;
  normal kullanıcı oluşturma, profil düzenleme, aktif/pasif, geçici parola ve
  proje atama/kaldırma sağlar. Fiziksel silme veya rol kontrolü yoktur; servis
  bu çağrıları ayrıca açıkça reddeder.
- Üst bağlam artık **Kullanıcı | Proje | Katılımcı | Kamera | Disk**;
  `Oturum` chip'i kaldırıldı. Kullanıcı menüsü Şifre Değiştir, Oturumu Kapat ve
  owner için Kullanıcıları Yönet eylemlerini içerir.
- Projeler normal kullanıcıda yalnız erişilebilir kayıtları gösterir; teknik
  klasör/root kontrolleri yalnız owner'da görünür. Kayıt Planı formu plan adı,
  satır başına sıralı hareket ve özetle başlar; hedef ayrıntıları varsayılan
  kapalı Gelişmiş hedefler altındadır.

### Sürümler ve doğrulama

- Uygulama/paket: **0.9.0**.
- `PROJECT_SCHEMA_VERSION`: **1.1.0**.
- `SESSION_SCHEMA_VERSION`: **2.0.0** (minimum participant +
  `operator_user_id`).
- `TAKE_SCHEMA_VERSION`: **1.1.0** (`operator_user_id`).
- Identity SQLite schema: **1**. Annotation/export/feature/raw schema sürümleri
  bu görevde değişmedi.
- Yeni bağımlılık kurulmadı; yalnız standart kütüphane `sqlite3`, `hashlib`,
  `secrets` kullanıldı.

Gerçekten çalıştırılan sonuçlar:

```text
.\scripts\run_tests.ps1
  KineSynth · Python 3.11.14 · 561 passed in 178.46 s

conda run -n KineSynth python -m kinecapture --self-test
  exit 0 · 72 kare · playback OK · ham RGB-D 72/72
  2 hareket + 1 hata aralığı + 1 sürekli örnek · export doğrulama geçti

GUI offscreen smoke/paint
  ilk kurulum, login, self-registration, owner dialogu, bütün çalışma
  sayfaları, minimum 1120x700 ve dark/light: geçti
```

**Bu görevde gerçek ZED kamera yeniden çalıştırılmadı.** Capture ana düzeni ve
donanım backend'i değiştirilmedi; mock hattı ve bütün donanımsız regresyonlar
geçti. Önceki 2026-08-24 donanım kanıtı geçerlidir fakat bu auth turunun yeni
bir donanım doğrulaması değildir.

Legacy test verisi için silme öncesi üç kesin KineCapture proje dizini
doğrulandı (`muhasebe`, `Full Test`, `Demo`). PowerShell `Remove-Item`
runtime güvenlik katmanı tarafından işlem başlamadan reddedildi; ardından üç
hedefin de hâlâ var olduğu doğrulandı. **Hiçbir eski klasör silinmedi.** Yeni
identity DB bunları otomatik kaydetmez/açmaz. Kalan kesin yollar:

```text
C:\Users\gorke\KineCapture\datasets\projects\prj_20260820T164820_1e49
C:\Users\gorke\KineCapture\datasets\projects\prj_20260821T111333_a60a
C:\Users\gorke\AppData\Local\Temp\shots4_iu_kvaue\datasets\projects\prj_20260824T135007_2cb6
```

## 6F. Capture ve İnceleme/Etiketleme sadeleştirme promptu (2026-08-27)

> **Tarihsel.** Bu bölüm görev öncesi durumu ve prompt hazırlığını anlatır.
> Uygulanmış sonuç için **bölüm 6G**'ye bakın; buradaki "bugün şöyle"
> ifadeleri artık geçerli değildir.

**Durum: yalnız uygulama promptu hazırlandı; bu bölümdeki GUI değişiklikleri
henüz uygulanmadı.** Claude'un uygulaması için
`CLAUDE_CAPTURE_REVIEW_LABELING_UI_PROMPT.md` repository köküne eklendi.

### Kullanıcının yeni ürün kararları

1. Capture ekranındaki Ön kontrol, Kayıt Planı, Kayıt bilgisi, Kaydedilecek
   kişi ve Ham RGB-D arşivi kartları kalıcı sağ sütunda yer kaplamayacak;
   görünür bir düğmeyle açılan ayrı bilgi penceresinde erişilecek. RGB/derinlik
   ile 3B iskelet görüntüleri ana yatay alanın çoğunu kullanacak. Kayıt kaybı,
   disk, bağlantı ve kişi belirsizliği gibi kritik durumların kompakt uyarıları
   ana ekranda kalacak.
2. İnceleme ekranında yalnız kayıt sırasında seçilen/ilişkilendirilen kişinin
   iskeleti gösterilecek. Subject lock bulunan kayıtta otoritatif kaynak
   `SkeletonFrame.subject_body()` olacak; kişi o karede yoksa başka gövdeye
   fallback yapılmayacak. Legacy kayıtta kimlik uydurulmayacak.
3. RGB + İskelet kayması sabit görsel ofsetle değil; aynı RGB/skeleton karesi,
   tracker 2B noktaları, gerçek kamera calibration'ı, görüntü çözünürlüğü ve
   letterbox dönüşümü doğrulanarak çözülecek. Güvenilir projeksiyon verisi yoksa
   yaklaşık bindirme göstermek yerine dürüstçe kullanılamaz denecek.
4. İnceleme/Etiketleme ekranında yalnız iki yazılabilir zamansal katman olacak:
   **Hareket** ve seçili hareketin içindeki **Hata**. `Hareket ekle` / `Hata
   ekle` timeline çizimini hazırlar; mevcut aralığa çift tıklama, sınıf seçme
   ve yeni sınıf oluşturmayı sağlayan küçük bir pencere açar. Hareket
   sözlüğüne ekleme de hata sözlüğü gibi etiketleme anında mümkün olacak ve
   proje `label_schema.json` dosyasına atomik kaydolacak.
5. İnceleme ekranındaki Aktivite modu/şeridi/kartı/F3 akışı emekliye ayrılacak;
   arka plan/geçiş/hedef egzersiz/diğer hareket authoring'i yapılmayacak. Bu
   karar 6D'deki sürekli aktivite GUI kararını ürün akışı açısından geçersiz
   kılar. Buna rağmen eski `activity_intervals`, eski release'ler ve ham kayıt
   silinmeyecek veya otomatik olarak başka etikete dönüştürülmeyecek; geriye
   dönük okuma/kayıpsız koruma sürdürülecek.

### Prompt hazırlanırken gerçek kodda doğrulananlar

- `CapturePage` iki görüntü kartını ayrı bir yatay splitter'da tutuyor; ana
  splitter kalıcı sağ panel için `[900, 460]` başlangıç boyutu ve `3:2` stretch
  kullanıyor. Yan panelin minimum genişliği 400 px.
- `ReviewPage` görüntü/yan panel için `[820, 540]` ve `3:2` splitter kullanıyor.
  `Gövde` seçicisi olsa da `_redraw()` bütün `frame.bodies` listesini
  `SceneView`'a geçiriyor; seçici yalnız `active_id` değerini değiştiriyor.
  Dolayısıyla seçilmeyen iskeletler gerçekten çiziliyor.
- `SkeletonFrame.subject_body()` otoritatif subject tracker kimliğini buluyor
  ve başka gövdeye fallback yapmıyor; mevcut Review çizimi bu metodu
  kullanmıyor.
- `VideoView` kayıtlı `joint_positions_2d` varsa gerçek görüntü pikselini
  kullanıyor; alan yoksa `_focal_ratio = 0.75` tahminine düşüyor.
  `LoadedTake.video_position_for()` pozisyonu özdeş varsayıp kısa proxy'de son
  kareye clamp ediyor. Prompt her iki dürüstlük/senkronizasyon riskini test
  edilerek kaldırmayı şart koşuyor.
- `LabelSchema` hem `add_exercise()` hem `add_error_type()` sağlıyor ve
  `ProjectWorkspace.save_label_schema()` mevcut atomik JSON yolunu kullanıyor.
  Review'daki yerinde picker/oluşturma akışı bugün yalnız hata türünde var.
- Aktivite UI'si `TimelineMode.ACTIVITY`, sağ Aktivite kartı, timeline lane'i ve
  F3 kısayoluyla gerçekten mevcut; ekran görüntüsündeki `Aktivite durumları`
  düğmesi bu akışa ait.

### Sürümler ve bu prompt hazırlama turunun doğrulaması

- Gerçek kod sürümleri değişmedi: uygulama/paket **0.7.0**; project **1.1.0**;
  session **2.0.0**; take **1.1.0**; skeleton stream **1.1.0**; annotation,
  label ve release **2.0.0**; raw archive **1.0.0**; feature spec **1.0.0**;
  identity SQLite schema **1**.
- Kaynak kod, veri şeması ve paket sürümü değiştirilmedi; yalnız Claude görev
  promptu ile bu hafıza bölümü eklendi.
- Görsel ek `codex-clipboard-0bdf70b7-f06a-4114-bada-b2363291820b.png`
  incelendi; geniş sağ kart, Hareket/Hata/Aktivite modları ve sürekli açık
  hareket sınıfı alanı kullanıcının tarif ettiği yer kaybını doğruluyor.
- Bu turda test paketi veya self-test çalıştırılmadı; uygulama kodu değişmedi.
  Yalnız metin/kod incelemesi yapıldı. ZED kamera çalıştırılmadı ve GUI
  davranışı uygulanmış olarak doğrulanmadı.

## 6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)

`CLAUDE_CAPTURE_REVIEW_LABELING_UI_PROMPT.md` uygulandı. Bölüm 6F o promptun
hazırlık analiziydi; burası uygulamanın kendisi.

### Capture ekranı

- Kalıcı sağ sütun kaldırıldı. **Ön kontrol, Kayıt Planı, Kayıt bilgisi,
  Kaydedilecek kişi ve Ham RGB-D arşivi** kartları aynen korundu, fakat artık
  tek örnekli, modeless `InfoWindow` içinde (`gui/widgets/info_window.py`).
  `Kayıt bilgileri` düğmesi ve `F4` açar/kapatır; pencere açıkken kayıt ve
  önizleme sürer.
- İki canlı görünüm (RGB/derinlik + 3B iskelet) splitter'ı ekranın tamamını
  kullanıyor (`setSizes([760, 640])`, eşit stretch).
- **Kritik uyarı şeridi ana ekranda kaldı**: `_build_alerts` + `_refresh_alerts`.
  Öncelik sırası — bağlantı yok → kamera hatası → kayıt kaybı → disk
  yetersizliği → kişi belirsiz → kişi geçici kayıp → kişi seçilmedi.
  `Kimliği yeniden doğrula` ve `Seçimi kaldır` düğmeleri bu şeridin içinde,
  yani sorunun yanında.
- Kişi durumu chip'i canlı RGB kartının başlığında; sayısal ayrıntılar
  (`Mantıksal kimlik`, `Eşlenen tracker ID`, kayıp süresi, yeniden eşleştirme,
  belirsiz kare) info penceresinde.
- `_disk_shortfall` alanı `_refresh_archive_card` tarafından doldurulur ve
  uyarı şeridini besler.

### İnceleme ekranı — yalnızca kaydedilen kişi

- `ReviewPage._redraw()` artık **tek gövde** çiziyor:
  `LoadedTake.review_body_at(position)` → kilit varsa `frame.subject_body()`,
  yoksa `None`. Başka gövde soluk bile çizilmiyor.
- **Gövde/tracker seçicisi kaldırıldı** (`_body_selector` yok).
- Kişi bulunamayan karede iskelet çizilmez, uyarı şeridinde
  `Seçilen kişi bu karede bulunamadı — iskelet çizilmiyor.` yazar, önceki
  karenin pozu **donmaz**.
- Zaman çizelgesindeki kapsam eğrisi `LoadedTake.subject_coverage_curve()`
  ile aynı gövdeden geliyor; eskiden `coverage_curve(None)` en iyi takip
  edilen gövdeyi çiziyordu ve katılımcının kaybolduğu aralıkta "tam kapsam"
  iddia ediyordu.
- **Eski (kilitsiz) kayıtlar:** `SkeletonStream.dominant_tracking_id` — kayıtta
  en çok görünen gövde. Bu bir tahmindir, öyle işaretlenir
  (`Kilit yok · tahmin ID n` + açılış bildirimi) ve `ReleaseBuilder`'ın aynı
  kayıtlara uyguladığı kuralla birebir aynıdır. Uydurma kimlik yazılmaz.

### Bindirme hizası — KÖK NEDEN, ofis ofseti değil

- **Sebep:** `joint_positions_2d` *kameranın* görüntüsünün pikselleri;
  inceleme ekranındaki resim ise küçültülmüş proxy video. `VideoView`
  gösterilen görüntünün genişliğine bölüyordu.
- **Ölçüm (gerçek kayıt):** kamera 960x540, proxy 640x360, 2B x aralığı
  402–557 → her eklem **1.5x** fazla sağda. HD720 + `proxy_video_width=640`
  ile çarpan **2.0x**.
- **Düzeltme:** `VideoView.set_joint_space(resolution, calibration=...)`.
  İzdüşüm normalize koordinatlar üzerinden yapılıyor, çizim boyutundan
  bağımsız. `LoadedTake.joint_pixel_space` (`camera_info.resolution`) ve
  `LoadedTake.camera_calibration` (`extra.left_camera_calibration`) besliyor.
- Tahmini `_focal_ratio = 0.75` izdüşümü **silindi**. 2B yoksa doğrulanmış
  kalibrasyonla pinhole izdüşüm; o da yoksa `can_overlay()` False döner,
  bindirme çizilmez ve nedeni ekrana yazılır.
- Canlı Capture etkilenmiyordu çünkü orada tam çözünürlüklü kare gösteriliyor;
  iki uzay çakışıyor. Hata yalnız İnceleme'de görünüyordu.
- `LoadedTake.video_position_for()` artık **clamp etmiyor**, `Optional[int]`
  döndürüyor. Renkli kare yoksa `SceneView.set_frame(..., rgb_missing_reason=)`
  ile resim temizlenir ve neden yazılır; başka bir anın resmi gösterilmez.

### Etiketleme arayüzü — iki katman, iki küçük pencere

- Kalıcı sağ panel, hareket listesi, hata listesi ve sürekli açık sınıf
  formları kaldırıldı. Zaman çizelgesi hem liste hem seçim yüzeyi.
- Kompakt, her zaman görünür eylem satırı: `Hareket ekle`, `Hata ekle`,
  `Etiketle`, sil/geri al/yinele/oynat-döngüle (ikon), ilerleme chip'i,
  `Sonraki eksik`, `Diğer…` menüsü (böl, birleştir, dışla, marker'lardan
  oluştur, yakınlaştır).
- **Çift tık** (veya `Enter`): hareket bandında `MovementLabelDialog`, hata
  bandında `ErrorLabelDialog` (`gui/widgets/label_dialogs.py`).
- Ortak `LabelClassPicker` (`gui/widgets/label_picker.py`, `LabelKind`
  parametreli) hem hareket hem hata sözlüğüne hizmet ediyor. Eski
  `gui/widgets/error_picker.py` **silindi** (kullanan kalmadı).
- Aralık **oluşturmak** pencere açmaz. Arka arkaya on tekrar çizerken on modal
  kabul edilemez; etiketleme ayrı ve açık bir eylem.
- `ReviewPage._run_dialog(dialog)` tek modal noktası — testler bu metodu
  değiştirerek gerçek diyalog widget'ını insansız sürüyor.

### Sınıf oluşturma, iptal ve hazır olma semantiği

- `LabelSchema.match_exercise/search_exercises/ensure_exercise` eklendi;
  `add_exercise` artık `add_error_type` ile **aynı** NFKC/casefold/boşluk
  yinelenen-ad kuralını kullanıyor. `ensure_exercise("Squat")` ve
  `ensure_exercise("  SQUAT ")` aynı `squat` seçeneğini döndürür.
- `AnnotationRepository.ensure_movement_class` / `assign_new_movement_class`
  eklendi; `ensure_error_class` ile aynı sözleşme.
- **Sınıf eklemek proje düzeyinde bir değişikliktir**: `label_schema.json`
  dosyasına anında ve atomik yazılır, etiketleme undo yığınına **girmez**, ve
  diyalog **İptal** ile kapatılsa bile tanımlı kalır. İptal yalnızca "bu
  aralığa atama"yı geri alır. Gerekçe: sınıf başka take'lerde kullanılıyor
  olabilir; bir pencerenin kapatılması onu tanımsız yapamaz.
- Yarım kalmış aralık **hazır sayılmaz**: türsüz hata aralığı hem
  `evaluate_sample()` hem ekran metninde eksik görünür; export aynı kuralı
  okur.

### Aktivite yazımının emekliye ayrılması

- `TimelineMode.ACTIVITY`, aktivite şeridi, aktivite kartı, F3 kısayolu,
  bütün aktivite CRUD handler'ları ve `TimelineWidget`'ın aktivite sinyalleri
  **kaldırıldı**. Gizli üçüncü şeride dönüştürülmedi: `list(TimelineMode)`
  artık tam olarak `[MOVEMENT, ERROR]`.
- **Veri korunuyor.** `domain/activity.py`, `AnnotationRepository`'nin aktivite
  okuma/yazma yolu ve `export/continuous.py` yerinde. Mevcut
  `activity_intervals` silinmiyor, dönüştürülmüyor, okuma sırasında migration
  yapılmıyor.
- `ProjectWorkspace.save_samples()` artık **tanımadığı üst düzey blokları**
  aynen koruyor (`_ANNOTATION_KNOWN_KEYS` dışındaki her şey). Böylece emekli
  bir özellik ya da daha yeni bir sürümün yazdığı blok, sonraki ilk kayıtla
  sessizce kaybolmuyor.
- **Export ekranı kararı:** `Sürekli aktivite` seçeneği silinmedi, *koşullu*
  hale getirildi. `_refresh_continuous_availability()` projede aktivite
  etiketi taşıyan kayıt sayar; sıfırsa seçenek pasifleşir ve nedeni yazar.
  Gerekçe: eski etiketli kayıtlardan hâlâ geçerli bir sürekli release
  üretilebilir, fakat aktivite etiketi olmayan bir projede seçenek yalnızca
  tamamı etiketsiz bir dataset üretebilirdi.

### Yerleşim — 1120x700 / 1366x768 / 1600x980, iki tema

- `gui/widgets/flow_layout.py`: `FlowLayout` + `flow_row()`. Yoğun satırlar
  (9 metrik kutusu, 10 eylem düğmesi) kırpılmak yerine alt satıra sarıyor.
- `_ASSUMED_MIN_WIDTH = 760`: Qt bir height-for-width satırının *minimum*
  yüksekliğini kendi minimum genişliğinde sorar; gerçek minimum (tek kontrol)
  bırakılırsa dokuz kutu dokuz satır iddia eder ve sayfa 700 px yüksekliğe
  hiç inemez. 1120 px pencerede içerik alanı 834 px, bu yüzden 760 gerçekçi
  ve ilk yerleşim geçişinde doğru.
- `common.ElidedLabel`: sayfa başlığı, açıklaması, uyarı ve konum satırları
  sarmak yerine kısaltıyor. Sarılan bir açıklama altı satır kaplayıp o yeri
  kamera görüntüsünden alıyordu.
- `Card(compact=True)` (İnceleme'nin iki kartı), `KeyValueList` anahtar
  sütunu sarıyor, `MetricTile` en fazla 135 px, video/iskelet görünümleri
  minimum 240x120, timeline şerit yükseklikleri 16 px kısaldı.
- Ölçülen minimumlar: **CapturePage 529 px, ReviewPage 596 px** yükseklik
  (1120x700 penceresinde sayfaya kalan alan 606 px); genişlikte
  **951 / 1101 (capture, tema başına) ve 938 (review)** — hepsi 1120'nin
  altında. Yatay kaydırma ve kırpma yok.

### Sürümler

- `APP_VERSION` ve paket sürümü **0.7.0 → 0.8.0**.
- **Hiçbir şema sürümü değişmedi** — veri sözleşmesi aynı: project 1.1.0,
  session 2.0.0, take 1.1.0, skeleton stream 1.1.0, annotation 2.0.0,
  label 2.0.0, release 2.0.0, feature spec 1.0.0, raw archive 1.0.0,
  identity SQLite schema 1.

### Bu turda GERÇEKTEN çalıştırılanlar

- `python -m pytest tests/` → **585 passed**, 196.75 s (uygulama sonrası tam
  tur; ara turlarda 25 kırmızı test yeni arayüze göre yeniden yazıldı).
- `.\scripts\run_tests.ps1 -Quiet` → "Testler gecti." (KineSynth, Python 3.11.14).
- `python -m kinecapture --self-test` → uçtan uca sentetik akış OK; export
  `dataset_v001`, 2 hareket örneği, 1 sürekli örnek, doğrulama geçti.
- İki ekran offscreen olarak **1120x700, 1366x768, 1600x980** boyutlarında ve
  **dark/light** temalarda gerçek `grab()` ile render edildi; `minimumSizeHint`
  değerleri ölçüldü, `FlowContainer` içindeki her kontrolün kutusunun içinde
  kaldığı test edildi.
- **Donanımda doğrulanmadı:** bu turda ZED 2i ile canlı kayıt alınmadı. Kişi
  kilidi, ham arşiv ve bindirme hizası mock backend ile ve daha önce (bölüm
  6D) alınmış gerçek kayıtların dosyalarıyla doğrulandı. Gerçek kamerada
  Capture uyarı şeridinin canlı kayıt kaybı senaryosu tetiklenmedi.

## 6H. Sonraki Claude GUI/veri görevi — prompt hazırlığı (2026-08-30)

> **Tarihsel.** Bu bölüm görev *öncesi* durumu ve onaylanan ürün
> kararlarını kaydeder. Başlığındaki "HENÜZ UYGULANMADI" artık geçerli
> değildir: prompt aynı gün uygulandı. Uygulanmış sonuç için **bölüm
> 6I**'ye bakın.

Kullanıcı son 0.8.0 arayüzünü yeniden değerlendirdi; mevcut kod, ilgili
testler ve geçici/izole GUI render'ları incelendikten sonra
CLAUDE_PROJECT_DELETE_LABELING_EXPORT_GUI_PROMPT.md oluşturuldu. Bu bölüm
uygulanmış özellikleri değil, onaylanan ürün kararlarını ve prompt hazırlama
denetimini kaydeder.

### Onaylanan ürün kararları

- **Proje silme kalıcıdır:** yalnız identity modelindeki tek System
  Owner/admin kullanabilir. Başarılı işlem proje klasörünü; ham kayıt, proxy,
  iskelet, annotation ve release'ler dahil fiziksel olarak kaldırmalı ve disk
  alanını boşaltmalıdır. Listeden kaldırma, soft delete, Recycle Bin veya
  kalıcı trash yeterli değildir. Normal user hem GUI hem servis katmanında
  engellenmelidir.
- Silme için proje adı/doğrulama metni isteyen güçlü bir onay, canonical path
  ve manifest kimliği kontrolü, geniş kök/symlink-junction koruması, aktif
  handle'ların kapanması, SQLite ilişki/audit düzeni ve kısmi hata/recovery
  politikası promptta zorunlu tutuldu. Gerçek kullanıcı projesi üzerinde
  destructive test yasaktır; yalnız disposable temp proje kullanılacaktır.
- **Correctness kullanıcı seçimi değildir:** hareket sınıfı kaydedilmiş ve
  sınıflandırılmış geçerli hata aralığı yoksa hareket otomatik Doğru ve
  export-ready; en az bir sınıflandırılmış hata aralığı varsa Hatalı; son hata
  aralığı silinirse yeniden Doğru olur. Sınıfsız/geçersiz hata aralığı
  hareketi unready bırakır.
- Mevcut 2.0.0 annotation'larda explicit Hatalı kararı olup hata aralığı
  bulunmaması sessizce Doğru'ya çevrilmeyecek; legacy çelişkisi görünür ve
  çözülene kadar export dışı olacaktır. Correctness otoritesi değiştiği için
  uygulayıcı gerçek schema/reader etkisini inceleyip uygun sürümleme ve
  idempotent migration kararı vermelidir.
- **Timeline trim preview** hem mevcut hareket/hata aralığının start/end
  kenarını düzenlerken hem de yeni hareket/hata aralığını ilk kez çizerken
  sürüklenen endpoint karesini gösterir. Drag başlangıcındaki playhead
  saklanır; release/cancel sonrasında oraya dönülür. MouseMove başına
  repository mutation/undo/autosave yapılmaz, final değişiklik tek işlem
  olarak commit edilir.
- Export artık KineSynthV3 Transformer uyumluluğunu varsayılan hedef veya
  öncelik saymayacaktır. Yeni model için modelden bağımsız, self-describing,
  provenance/mask/unit/shape/dtype/label mapping/error interval/derived
  correctness içeren canonical dataset önceliklidir. Legacy uyumluluk
  gerekirse ikincil ve açıkça işaretli kalabilir.
- Export ile Ayarlar ve Tanılama sabit yoğun yan yana sütunlar yerine
  1120x700, 1366x768 ve 1600x980'de erişilebilir responsive/scroll
  mimarisine geçirilecektir. Tüm sayfalar dolu fixture'larla genel geometri
  denetimine alınacaktır.
- files/Yıldız_Technical_University_Logo.png (RGBA, 398x405) açık
  NavigationRail'de Daralt düğmesinin hemen üstünde, oranı korunmuş ve
  ortalanmış gösterilecek; rail daralınca tamamen gizlenecek ve boşluk
  bırakmayacaktır. Görsel paket kaynağına dahil edilecek, cwd-relative
  development path'e bağlı kalmayacaktır.

### Prompt hazırlama sırasında doğrulanan mevcut durum

- ProjectsPage ve IdentityService'te proje silme akışı yoktur.
- Hareket dialogu, MovementSample, evaluate_sample, Dataset ve export
  explicit stored correctness'e bağlıdır; yalnız GUI düğmesi kaldırmak yeterli
  değildir.
- TimelineWidget resize/move sırasında bounds sinyallerini sürekli gönderiyor;
  preview/restore sinyali veya tek commit transaction'ı yoktur.
- ExportPage hâlâ KineSynthV3 uyumu metni taşır ve sabit iki sütun kullanır.
- SettingsPage iki yoğun bağımsız scroll sütununda yatay taşan kontrol
  grupları kullanır. İzole render'da 1120x700 ve 1366x768 boyutlarında
  yatay scroll, sıkışan alanlar ve görünür viewport dışına kayan alt kartlar
  doğrulandı.
- Logo dosyası mevcuttur fakat bu turda kaynak/paketleme dosyalarına
  eklenmedi.

### Bu prompt hazırlama turunda gerçekten çalıştırılanlar

- conda run -n KineSynth python -m pytest tests/test_gui_painting.py
  tests/test_gui.py tests/test_export_gui.py tests/test_review_flow.py -q
  → **132 test geçti**.
- Aynı dört dosya --collect-only ile doğrulandı → **132 test toplandı**.
- Uygulama normal launcher ile açıldı; gerçek kullanıcı hesabıyla giriş
  yapılmadı ve gerçek veri değiştirilmedi. Export, Settings ve Projects
  sayfaları geçici identity DB + geçici proje ile offscreen olarak 1120x700
  ve 1366x768'de render edildi.
- Full tests/ turu ve self-test bu prompt-only turda yeniden
  çalıştırılmadı. Proje silme, yeni correctness, timeline preview, responsive
  refactor ve logo **henüz uygulanmadı veya işlevsel olarak doğrulanmadı**.
- Kaynak kod ve gerçek app/schema sürümleri değişmedi: app 0.8.0; project
  1.1.0, session 2.0.0, take 1.1.0, skeleton stream 1.1.0, annotation 2.0.0,
  label 2.0.0, release 2.0.0, feature spec 1.0.0, raw archive 1.0.0,
  identity SQLite schema 1. Bu turda yalnız yeni Claude promptu ve bu MEMORY
  bölümü eklendi.

## 6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)

`CLAUDE_PROJECT_DELETE_LABELING_EXPORT_GUI_PROMPT.md` uygulandı.

### Doğru/hatalı kararı artık TÜRETİLİYOR — veri sözleşmesi değişikliği

**Kural:** sınıflandırılmış hata aralığı olan hareket HATALI, olmayan DOĞRU.
Kullanıcıya ayrıca sorulmaz. Son aralık silinince hareket yeniden DOĞRU olur.
Sınıfsız/geçersiz/dışarı taşan aralık hareketi doğru yapmaz — eksik bırakır.

- Tek kaynak: `MovementSample.derived_correctness`. Domain, repository,
  Dataset filtre/dağılımları, timeline bandı rengi, release manifesti ve
  continuous export **hepsi** bunu okur; hiçbiri kendi hesabını yapmaz.
- `MovementSample.correctness` alanı korunuyor fakat **türetilmiş önbellek**:
  `label_sample()` ve `apply_to_all()` artık `correctness` parametresi
  **kabul etmiyor**, `to_dict()` reviewed örneklerde türetilmiş değeri yazıyor.
  Divergence üretebilecek public API yok.
- **"Hata yok" ile "kimse bakmadı" ayrımı:** yeni `reviewed_at` alanı. Hareket
  penceresinin Kaydet'i onu damgalar (`mark_reviewed()`); damgasız hareket hata
  aralığı olmasa da `UNLABELLED` kalır. Bu, aralıkların tek başına söyleyemediği
  tek şeydir.
- `MovementLabelDialog`'dan Doğru/Hatalı düğmeleri, `KARAR` bölümü,
  `correctness` property'si, `_set_verdict` ve `1`/`2` kısayolları **kaldırıldı**
  (hem dialogdan hem ReviewPage'den). Kaydet, sınıf seçilmeden **etkin olmuyor**.
- Yeni readiness durumu: `SampleReadiness.LEGACY_CONFLICT`.

### Legacy annotation politikası

`is_review_complete` = `reviewed_at` var **veya** dosyadaki karar türetilmiş
değerle **aynı**. Böylece insan kararı ile kanıt uyuşuyorsa otomatik ve kayıpsız
geçiş olur; uyuşmuyorsa çelişki görünür kalır.

| Eski dosyadaki durum | Sonuç |
|---|---|
| CORRECT + aralık yok | READY (kanıt ve karar aynı) |
| INCORRECT + sınıflı aralık var | READY |
| **INCORRECT + sınıflı aralık yok** | **LEGACY_CONFLICT**, export dışı |
| **CORRECT + sınıflı aralık var** | **LEGACY_CONFLICT**, export dışı |
| UNLABELLED + exercise var | UNLABELLED (sınıf yalnız başına karar değil) |

- **Dosyayı açmak onu yeniden yazmaz.** Çözülmemiş legacy örnek kaydedilse bile
  eski kararı **verbatim** korur (`to_dict()` yalnız `reviewed_at` varsa
  türetilmiş değeri yazar). Sessiz veri kaybı yok.
- Çözüm iki deterministik yoldan biriyle: hareket penceresini yeniden kaydetmek
  (yeni kuralı bilinçli kabul), veya eksik hata aralığını ekleyip
  sınıflandırmak. İkisi de idempotent ve testli.

### Sürümler (gerçekten değişenler)

- `APP_VERSION` / paket: **0.8.0 → 0.9.0**
- `ANNOTATION_SCHEMA_VERSION`: **2.0.0 → 2.1.0** — `reviewed_at` ve
  `correctness_source` eklendi, `correctness`'in otoritesi değişti. Minor:
  2.0 reader 2.1 dosyada bildiği alanda geçerli bir ikili değer bulur; 2.1
  reader 2.0 dosyada kararı verbatim korur ve çelişkiyi gösterir.
- `RELEASE_SCHEMA_VERSION`: **2.0.0 → 2.1.0** — manifest `correctness_source`
  ve `reviewed_at` taşıyor. Toplamsal; hiçbir 2.0 alanı anlam değiştirmedi.
- **Değişmeyenler:** project 1.1.0, session 2.0.0, take 1.1.0, skeleton stream
  1.1.0, label 2.0.0, feature spec 1.0.0, raw archive 1.0.0, identity SQLite 1.

### Kalıcı proje silme (yalnız Sistem Sahibi)

Yeni `kinecapture/dataset/deletion.py` + `IdentityService` uzantıları.

- **Yetki servistedir:** `IdentityService.authorize_project_deletion()` owner
  şartını uygular. Normal kullanıcı düğmeyi görmez *ve* GUI'yi atlarsa
  `AuthorizationError` alır (test edildi).
- **Onay:** proje adı + kimlik + **tam, elide edilmemiş, kopyalanabilir yol**,
  ne silineceği ve geri alınamazlığı. Son düğme **proje adı birebir yazılana
  kadar** pasif. İptal/kapatma/yanlış metin = tam no-op. İş başladıktan sonra
  ikinci tıklama yeni iş üretmez ve **İptal düğmesi sunulmaz**.
- **GUI thread bloklanmaz:** `DeletionWorker(QThread)` ölçüm ve silmeyi
  yürütür; dialog ilerlemeyi gösterir. Worker'a servis değil düz bir callable
  verilir, böylece threading hiçbir şey silmeden test edilebilir.
- **Path guard'ları** (`inspect_target`, saf fonksiyon, yalnız DB kaydını alır):
  resolve + kayıtla karşılaştırma, `project.json` içindeki `project_id`
  eşleşmesi, sürücü kökü / home / dataset kökü / kaynak klasör reddi,
  symlink & Windows junction (reparse point) reddi. Proje **içindeki**
  bağlantı izlenmez, yalnız bağın kendisi kaldırılır (test edildi).
- **Sıra:** authorize → preflight → aktif bağlamı bırak (capture service ve
  video handle'ları; Windows açık handle'lı klasörü taşımaz) → `os.replace` ile
  `datasets/.deleting/<id>__<zaman>` tombstone → DB transaction → baytları sil.
- **DB hatası:** proje eski yerine geri taşınır, hiçbir dosya silinmez
  (`StorageError delete_db_failed`). **Dosya kalırsa:** başarı gösterilmez,
  kalan yollar raporlanır, `project_files_remaining` audit olayı yazılır.
- **Audit FK:** `audit_log.project_id → projects` bağı yüzünden geçmiş
  silinmiyor. Önce her olayın metadata'sına proje kimliği/adı kopyalanıyor,
  sonra işaretçi `NULL` yapılıyor; `project_deleted` olayı actor + yol ile
  ekleniyor.
- **Kurtarma:** girişte `.deleting` taranır. `database_cleared: true` ise silme
  tamamlanır; `false` ise proje eski yoluna geri alınır; işareti okunamayan
  klasöre **dokunulmaz** ve bildirilir. Belirsizlik veriyi korumaktan yana.
- **Kayıt sürerken silme reddedilir** (`recording_blocks_delete`); kayıt
  kullanıcının haberi olmadan durdurulmaz.
- Read-only dosyalar `onerror` içinde yazılabilir yapılıp yeniden deneniyor
  (Windows'un klasik yarıda kalan silme sebebi); uzun yollar `long_path()`.

### Timeline: video editörü tarzı kırpma önizlemesi

- Yeni sinyaller: `edit_started`, `preview_position_changed(int)`,
  `edit_finished`, `edit_cancelled`. `position_changed` kalıcı playhead için
  ayrıldı — ikisini aynı saymak playhead'in farenin bırakıldığı yerde
  kalmasının sebebiydi.
- Altı sürükleme türünde de önizleme var: hareket/hata × başlangıç/bitiş
  yeniden boyutlandırma ve yeni aralık çizme. Hata aralığı önizlemesi ana
  hareket sınırına **son hâlle aynı kuralla** kırpılır.
- `_Drag.tentative_start/end` ekranda çizilir (`_drawn_bounds`); repository
  **fare bırakılana kadar hiçbir şey duymaz**. Eskiden her `mouseMove` bir
  mutasyon + bir undo snapshot + bir autosave üretiyordu; tek sürüklemeyi geri
  almak onlarca Ctrl+Z demekti. Artık bir sürükleme = bir yazma.
- Bırakınca: tek commit, sonra `ReviewPage._edit_finished` playhead'i
  **sürükleme başlamadan önceki kareye** döndürür ve oynatmayı başlatmaz.
- `Esc`, odak kaybı ve eşik altı kısa tıklama iptal eder; kısa tıklama eski
  scrub davranışını korur. `ReviewPage._redraw(position)` artık isteğe bağlı
  konum alıyor: önizleme `self._position`'a dokunmuyor.

### Export: modelden bağımsız

- Export ekranındaki KineSynthV3 yönlendirmesi kaldırıldı; native/kanonik
  seçenek "önerilen" olarak sunuluyor. Yeni `canonical` preset varsayılan
  başlangıç; `kinesynth_compat` **`legacy=True`** ile korunuyor (silmek eski
  otomasyonu bozardı) ve adı "Eski: ..." ile başlıyor.
- Yeni "Çıktı sözleşmesi" kartı ne yazıldığını ve normalizasyon/sabit uzunluk/
  padding/split'in **yapılmadığını** açıkça söylüyor.
- Release doğrulaması artık *sınıflandırılmış* aralıkları sayıyor ve sınıfsız
  aralığı ayrı bir hata olarak bildiriyor; türetilmiş correctness ile aralık
  içeriği çelişemez.

### GUI: bilgi mimarisi ve viewport denetimi

- **Export**: 5 sekme (Kapsam / İskelet / Özellikler / Doğrulama / Sürümler),
  her biri kendi dikey scroll'u; **Sürüm oluştur** sekmelerin dışında sabit
  eylem çubuğunda, pasifse nedeni yanında yazıyor. Release tablosu
  `ResizeToContents` yerine `Interactive` + ilk sütun `Stretch`.
- **Ayarlar**: 6 sekme (Genel / Yakalama / Sentetik / Sınıflar / Tanılama /
  Konumlar); iki bağımsız scroll kolonu kaldırıldı. **Kaydet** sekmelerin
  dışında, yanında kirli/temiz durumu. Tanılama raporu monospace ve esnek
  yükseklikte. Sınıf listeleri splitter içinde, birbirini ezmiyor.
- **Dataset**: 8 filtre ve 12 metrik kutusu `flow_row` ile sarıyor; tablolar
  `Interactive` sütunlarla; sayfa dikey scroll'a alındı.
- **Projeler**: sabit 2:3 kolon yerine splitter; plan düğmeleri sarıyor.
- **Dashboard**: yatay scrollbar kapatıldı.
- Yeni ortak yardımcılar: `make_wrapped_label` (sarar, genişlik dayatmaz),
  `Card(compact=True)`, `ElidedLabel` kullanımı yaygınlaştı.
- **Ölçülen minimumlar (1120x700, dark/light):** dashboard 290x133,
  projects 861x245, participants 586x342, capture 1101x593, review 938x598,
  dataset 517x133, export 550x523, settings 551x447. Hepsi 1120'nin altında;
  `pages with problems: 0`.
- **Minimum pencere boyutu büyütülmedi**; kök neden layout/size-policy
  üzerinden çözüldü.

### NavigationRail'de YTÜ logosu

- Kaynak `files/Yıldız_Technical_University_Logo.png` **dokunulmadı**;
  bayt-bayt aynı kopya `src/kinecapture/gui/assets/` altına alındı ve
  `pyproject.toml` içinde `package-data` olarak bildirildi. `importlib.resources`
  ile okunuyor — cwd/repository yoluna bağlı değil. **Wheel içinde bulunduğu
  doğrulandı** (`kinecapture-0.9.0-py3-none-any.whl`).
- Rail açıkken Daralt düğmesinin hemen üstünde, yatayda ortalı, en-boy oranı
  ve şeffaflık korunarak `SmoothTransformation` ile ölçekleniyor
  (94x96 px; tavan 96 px, 700 px ekranda navigasyonu itmiyor).
- Daraltıldığında **tamamen gizleniyor** ve `height=0` — boşluk bırakmıyor.
  Her ölçekleme **orijinalden** yapılıyor, art arda collapse/expand görüntüyü
  bozmuyor ve yeni pixmap sızdırmıyor (8 tur test edildi).
- Logo yüklenemezse uygulama çalışmaya devam ediyor, yalnız warning düşüyor.

### QFont::setPointSize uyarısı — Qt kaynaklı, kanıtlandı

- Offscreen platformda **hiç görünmüyor**; `windows` platform eklentisinde
  uygulama açılışında 27 kez düşüyor: `Point size <= 0 (-1)`.
- **Minimal tekrar üretim, hiç kinecapture kodu olmadan:** px tabanlı bir
  stylesheet (`QWidget { font-size: 13px; }`) + `QToolButton` + `QMenu` →
  aynı uyarı 6 kez. `px` stylesheet fontu piksel boyutlu bırakıyor
  (`pointSize() == -1`) ve Qt'nin kendi menü ölçüm kodu bu değeri geri
  `setPointSize`'a veriyor.
- Uygulama kodu **hiçbir zaman** pozitif olmayan punto istemiyor:
  `monospace_font()` tema sabitleriyle çağrılıyor, timeline cetveli
  `max(7, ...)` ile sınırlı — ikisi de testle sabitlendi.
- Menüye açık punto vermeyi denedim: uyarı **6 → 9'a çıktı**. Yukarı akış
  davranışı; kozmetik; düzeltilmedi ve nedeni testte belgelendi.

### Gerçekten çalıştırılanlar

| Komut | Sonuç |
|---|---|
| `python -m pytest tests/` | **732 passed**, 241.70 s |
| `.\scripts\run_tests.ps1 -Quiet` | "Testler gecti." (KineSynth, Python 3.11.14) |
| `python -m kinecapture --self-test` | uçtan uca OK, export doğrulama geçti |
| `pip wheel . --no-deps` | `kinecapture-0.9.0-py3-none-any.whl`, logo içinde |
| GUI denetimi (8 sayfa × 3 boyut × 2 tema) | `pages with problems: 0` |
| Gerçek `windows` platform akış testi | hepsi OK (aşağıda) |

Yeni test dosyaları: `test_project_deletion.py` (19), `test_project_deletion_gui.py`
(9), `test_timeline_preview.py` (16), `test_nav_logo.py` (13),
`test_gui_viewports.py` (79). `test_annotations.py` türetilmiş karar ve legacy
migration testleriyle 56'ya çıktı.

`windows` platform eklentisiyle (offscreen değil) doğrulananlar: hareket
penceresinde verdict düğmesi yok ve Kaydet sınıfsız pasif; türetilmiş karar
`correct` + ready; trim preview sonrası playhead 28→28; silme dialogu boş/yanlış
metinde pasif, doğru metinde etkin, tam yol gösteriliyor; logo 94x96 açık,
collapsed height 0, geri geliyor; export/settings/dataset/capture çiziliyor.

### Donanımda doğrulanamayanlar

- **Bu turda ZED 2i ile canlı kayıt alınmadı.** Capture ekranı düzeni bu görevde
  değişmedi; mock backend ve önceki turların gerçek kayıt dosyaları kullanıldı.
- **Gerçek büyük proje silinmedi.** Silme yalnız `tmp_path` altında oluşturulan
  tek kullanımlık fixture'larda çalıştırıldı. Onlarca GB'lık gerçek bir ham
  arşivde silme süresi, açık handle davranışı ve gerçek disk kazancı
  ölçülmedi.
- **Paketlenmiş installer denenmedi.** Logo bir wheel içinde doğrulandı;
  PyInstaller/MSI gibi bir dağıtım biçimi üretilmedi.
- `test_participant_codes_are_unique_under_concurrent_allocation` tam suite
  yükünde ara sıra Windows `.lock` dosyası yarışından düşüyor; tek başına
  üst üste geçiyor. Bu görevden önce de vardı, bu görevde değişmedi.

## 6J. Etkilenen eklem kanıtı ve GUI iyileştirmeleri promptu (2026-08-31)

Bu tur bir uygulama geliştirme turu değildir. Gerçek kod ve iki kullanıcı ekran
görüntüsü salt okunur incelendi; Claude Code'un uygulayacağı görev
`CLAUDE_AFFECTED_JOINT_EVIDENCE_AND_GUI_POLISH_PROMPT.md` dosyasına yazıldı.
Uygulama/package ve veri şemaları değiştirilmedi: app `0.9.0`, annotation/release
`2.1.0`, label `2.0.0`, project `1.1.0`, session `2.0.0`, take/skeleton stream
`1.1.0`, feature spec/raw archive `1.0.0`, identity schema `1` olarak kaldı.

Prompt için alınan kalıcı ürün ve veri kararları:

- Hata intervalindeki eklem etiketi ayrı bir son kullanıcı “joint classifier”
  ürünü değildir. Gelecekteki temporal graph modelinde açık node
  evidence/relevance supervision ve gating hedefi sağlayacaktır. Model bütün
  native skeleton node'larını almaya devam eder; yalnız GUI'de seçilemeyen yüz,
  parmak ve yardımcı tracker node'ları özelliklerden atılmaz.
- Kalıcı değer native index değil, topolojiden bağımsız canonical anatomik
  roldür (`left_knee`, `right_shoulder`, `pelvis`, `spine_mid`, `chest`, `neck`
  gibi). BODY_18/BODY_34/BODY_38 eşlemesi tek otoritatif rol tablosundan ve
  düzenlenen take'in gerçek `SkeletonSpec` bilgisinden yapılacaktır.
- Hata dialogu gerçek topolojiyi sabit önden görünümde bağlam olarak gösterecek;
  semantik roller çoklu seçilebilecek ve sol/sağ “sporcunun solu/sağı” olarak
  açıklanacaktır. Exact Qt/görsel tasarım yöntemi Claude'a bırakılmıştır.
- Eklem annotation durumu `selected`, `not_applicable`, `indeterminate` ve
  geriye uyumluluk için `unreviewed` anlamlarını ayıracaktır. Joint etiketi
  eksikliği derived correctness'i veya temporal error eğitim kullanılabilirliğini
  değiştirmeyecek; yalnız node supervision loss'u maskelenecektir.
- Class, joint status, canonical role listesi ve note tek atomik repository
  işlemi/undo/autosave adımı olacaktır. Eski `legacy.affected_joints` kayıpsız
  korunacak; yalnız tek anlamlı ve idempotent değerler normalize edilebilecektir.
- Canonical export interval + class + time + role + native-node ilişkisini,
  mapping provenance'ını, targetı ve label maskesini deterministic ve validator
  tarafından denetlenebilir biçimde taşıyacak; yeni joint annotation release
  fingerprintini etkileyecektir. Exact array adları/şekilleri mevcut export
  mimarisini inceleyecek uygulayıcıya bırakılmış, semantik kayıp kabul
  edilmemiştir.
- Klasörü gerçekten bulunmayan stale proje için normal recursive silmeden ayrı,
  owner-only ve güçlü onaylı “yetim proje kaydını listeden kaldırma” yolu
  istenmiştir. Bu yol hiçbir filesystem hedefini silmeyecek; project/access
  identity kayıtlarını transaction içinde kaldırıp audit metadata'sını
  koruyacaktır. Manifest/ID/symlink/izin/IO güvenlik hataları missing-target gibi
  ele alınmayacaktır.
- Navigation rail'de YTÜ logosu ile `Daralt` kontrolü görsel olarak ortalanacak,
  aralarında ölçülü dikey boşluk olacak ve 700 px yükseklikte taşma olmayacaktır.
  Auth ekranı mevcut paketli YTÜ logosunu kullanarak işlevleri ve güvenliği
  değiştirmeden daha profesyonel/responsive hale gelecektir. Production launcher
  ana pencereyi varsayılan olarak gerçek maximized state'te açacaktır; constructor
  farklı viewport GUI testlerine uygun kalacaktır.

Bu prompt-hazırlama turunda uygulama kodu değiştirilmediği için pytest, self-test,
wheel veya donanım testi çalıştırılmadı. Yalnız prompt dosyasının oluşturulduğu,
UTF-8 içeriğinin okunabildiği ve çalışma ağacı diff'i statik olarak doğrulandı.
Prompt uygulanmadan yukarıdaki özelliklerin uygulamada var olduğu kabul
edilmemelidir.

## 6K. Etkilenen eklem kanıtı ve GUI cilası — UYGULANDI (2026-08-31)

`CLAUDE_AFFECTED_JOINT_EVIDENCE_AND_GUI_POLISH_PROMPT.md` uygulandı.

### Ürün kararı: bu bir eklem sınıflandırıcısı DEĞİLDİR

Hata aralığına eklenen eklem bilgisi **node-level evidence/relevance
denetimidir**: ileride eğitilecek graph-temporal modele hatanın iskeletin
neresinde göründüğünü söyler. Modelin girdisinden hiçbir düğüm çıkarılmaz —
`joints_xyz` bütün native topolojiyi taşımaya devam eder. Bu cümle export
manifestine (`label_contract.joint_evidence.purpose`) ve README'ye yazıldı ki
sözleşmeyi okuyan biri alanı yanlış amaçla kullanmasın.

### Topolojiden bağımsız rol sözlüğü — tek otorite

- Depolanan değer eklem indeksi değil **kanonik anatomik roldür**.
- Tek otorite `kinecapture.features.roles` (`ALL_ROLES`, 26 rol). **Taşınmadı,
  kopyalanmadı**: feature katmanı zaten onu kullanıyordu, ikinci bir tablo
  ikisinin sessizce ayrışmasına izin verirdi.
- Sebep karışık dataset: aynı sürümde BODY_18 ve BODY_34 bir arada olabilir ve
  `19` numaralı düğüm ikisinde farklı yerdedir. Rol ile hedef uzayı tek kalır.
- Bir rol o topolojide yoksa **seçilemez** ve repository katmanı yine de gelen
  böyle bir değeri `role_not_in_skeleton` ile reddeder. Doğrulanmış boşluklar:
  `zed_body_18` → pelvis yok; `mock_16` → topuk/el/burun/spine_mid yok.
- Rol listesinde bulunmayan eklemler export'tan **atılmaz**, yalnız hedef
  üretiminde kullanılmaz. `zed_body_38` için hedef dışı düğümler picker'da
  sayıyla anlatılır (uydurma koordinatta çizilmez).

### Boş olmanın dört ayrı anlamı (`JointAnnotationStatus`)

| Durum | Anlam | `supervises_nodes` | `is_reviewed` |
|---|---|---|---|
| `selected` | Bir/daha fazla rol işaretlendi | True | True |
| `not_applicable` | İncelendi; belirli eklem hedefi yok | False | True |
| `indeterminate` | İncelendi; güvenilir belirlenemiyor | False | True |
| `unreviewed` | Hiç incelenmedi (eski veri dahil) | False | False |

Maskelenmek **negatif etiket değildir**. Dördünü tek "boş" değere indirmek
eğitimde sessizce yanlış negatif üretirdi. `selected` boş rol listesiyle,
boş olmayan rol listesi başka bir durumla saklanamaz
(`joint_status_without_roles` / `roles_without_selected_status`).

### Tek atomik yazım ve tek undo adımı

`AnnotationRepository.update_error_interval(...)` sınıf + not + durum + rolleri
**tek** işlemde uygular. Önce `copy.deepcopy` üzerinde doğrular, sonra tek
`_snapshot()` / `_changed()` yapar. Ayrı setter'larla yazmak bir kullanıcı
kararını üç undo adımına bölüyor ve yarısı uygulanmış bir aralık bırakabiliyordu
(yeni sınıf + eski eklemler). Reddedilen düzenleme aralığı hiç değiştirmez.

### Eski dosyalarla uyum — kayıpsız, göç yok

- Eski `affected_joints` **hep korunur** (`legacy.affected_joints`).
- Göç **hep-ya-hiç**: değerlerin tamamı role çevrilebiliyorsa `selected`
  okunur; biri bile çevrilemiyorsa hiçbiri çevrilmez, aralık `unreviewed`
  kalır. Yarım göç tamamlanmış gibi görünürdü.
- Dosya açmak onu **yeniden yazmaz**: test dosyanın baytlarını ve
  `st_mtime_ns` değerini karşılaştırıyor.
- Tanınmayan `joint_status` değeri `unreviewed` sayılır — bilinmeyen bir
  kelime, birinin verdiği karar gibi okunamaz.

### Etiket hazırlığı ile eklem kapsaması AYRI ölçülür

Eklem incelemesi yapılmamış kayıt export'a girer; zamansal hata sınıfı eğitimi
etkilenmez. Kapsama ayrı raporlanır: `joint_annotation_counts()` dört durumu
sayar, timeline ipucu ve inceleme durum satırı seçili aralığın durumunu
**yazıyla** söyler. Birleştirmek ya kullanılabilir veriyi bloklardı ya da node
denetimindeki boşluğu gizlerdi.

### Eklem seçici (`gui/widgets/joint_picker.py`)

- **Sabit şematik önden görünüş**, veriye bağlı yerleşim değil: bir take'e göre
  hesaplanan yerleşim kayıttan kayda oynar ve aynı vücut parçasını farklı yere
  koyardı.
- Önden bakıldığı için **sporcunun solu ekranın sağında** çizilir. Figürün
  üstünde "◀ Sporcunun sağı / Sporcunun solu ▶" bandı bunu yazıyla da söyler.
  Testler merkezden simetriyi ve tıklama-rol eşleşmesini ayrıca doğruluyor.
- Durum yalnız renkle değil, seçili eklemin üzerindeki **işaretle** de belli
  edilir. Vuruş yarıçapı 17 px (trackpad ile kullanılabilir olsun diye).
- Roller `ALL_ROLES` sırasında saklanır: iki annotatör aynı eklemleri farklı
  sırayla tıklarsa dosya yine aynı olur.
- Klavye ile gezinme ve `accessibleName` var.

### Export sözleşmesi (release 2.2.0)

Her zaman yazılan, kayıpsız ve küçük interval dizileri:
`error_interval_joint_multi_hot uint8 [K,R]`,
`error_interval_joint_mask uint8 [K]`,
`error_interval_joint_status int8 [K]` (dört durum maskede kaybolmasın diye).
`store_error_target_arrays` açıkken ek olarak
`error_joint_target uint8 [T,C,J]` (J = **native** düğüm sayısı) ve
`error_joint_label_mask uint8 [T,C]`.

Manifest `label_contract.joint_evidence` bloğu rol listesini, `role_to_index`,
`status_codes`, her durumun eğitimdeki anlamını, sürümde geçen her iskelet
biçimi için `role_to_native_node` tablosunu, `role_mapping_source` ve
`role_mapping_version = "anatomical-roles-1.0.0"` değerini yayınlar. Yoğun
diziler yazılmasa bile `dense_target_recipe` onları interval dizilerinden
birebir yeniden üretmeye yeter (test bunu gerçekten yeniden üretip
karşılaştırıyor).

Doğrulama: `unknown_joint_status`, `unknown_anatomical_role`,
`selected_without_roles`, `roles_without_selected_status`,
`joint_mask_disagrees_with_status`. Fingerprint eklem durumuna ve rol
listesine duyarlı.

### Klasörü kaybolmuş proje kaydı (yetim kayıt)

`DeletionService.forget_orphan(actor, project_id)` **yalnız** ön kontrol
`delete_target_missing` döndüğünde çalışır; başka her guard başarısızlığı
(manifest uyuşmazlığı, symlink, izin) `not_an_orphan_record` ile reddedilir —
"silinemiyor" hatası sessizce "kaydı at" işlemine dönüşemez. Dosya sistemine
**hiç dokunmaz**. Yine owner'a özel, yine proje adı birebir yazılır. Denetim
olayı ayrıdır: `project_record_removed`, metadata'sında `files_deleted: false`.
`DeleteProjectDialog(orphan=True)` başlığı, uyarı metnini ve buton yazısını
değiştirir; klasör yalnızca taşındıysa geri getirilmesi gerektiğini söyler.

### GUI cilası

- Nav rail: `navToggle` rolü ile Daralt düğmesi ortalandı; logo ile düğme
  arasına 10 px sabit boşluk widget'ı kondu ve **logo ile birlikte** gizleniyor.
  Test bunu gizli widget geometrisinden değil `layout().minimumSize()`
  üzerinden ölçüyor (Qt gizli widget'ın son dikdörtgenini bırakır).
- Giriş ekranı: paketlenmiş logo (yeni kopya üretilmedi), 360–520 px ortalanmış
  kolon, `QScrollArea` (kısa ekranda buton aşağı taşmasın), placeholder'lar,
  açık `setTabOrder`, `accessibleName`, kaydırılabilir footer. Logo yüklenmezse
  giriş ekranı tamamen çalışır — dekorasyon taşıyıcı değildir.
- Üretim launcher'ı `window.showMaximized()` çağırır (ekran dikdörtgenine
  resize DEĞİL: task bar, çok monitör ve per-monitor DPI yanlış olurdu).
  Pencere yapıcısı normal boyutta açar, böylece viewport testleri hâlâ
  yeniden boyutlandırabilir.

### Sürümler (bu turda değişen gerçek sabitler)

app **0.10.0**, annotation **2.2.0**, release **2.2.0** (üçü de bu fazda
yükseltildi; eklemeler geriye dönük uyumlu olduğu için minor). Değişmeyenler:
project 1.1.0, session 2.0.0, take 1.1.0, skeleton stream 1.1.0, label 2.0.0,
feature spec 1.0.0, raw archive 1.0.0, identity SQLite schema 1.

### Bu turda bulunan/düzeltilen gerçek hatalar

- `JointAnnotationStatus.parse()` bir str-Enum üyesini `str(value)` ile
  okuyunca `"JointAnnotationStatus.SELECTED"` elde ediyor ve `unreviewed`'a
  düşüyordu → `isinstance(value, cls)` erken dönüşü eklendi.
- `release.py` `resolve_roles` fonksiyonunu import etmeden kullanıyordu
  (`NameError`, 18 teste yayılıyordu).
- Hata penceresi BODY_18'de minimum 862 px yüksekliğe çıkıyordu; 700 px
  ekrana sığmıyordu. Minimum pencere boyutunu büyütmek yerine picker minimumu
  ve yardımcı metin yükseklikleri kısıldı → 591 px. Kesilen topoloji notu
  tooltip ile tam metin olarak erişilebilir.

### Bu turda GERÇEKTEN çalıştırılanlar

(Ayrıntılı sayılar bölüm 9'da.)

## 6L. Yeni sınıfı dialogu yeniden açmadan kaydetme düzeltmesi (2026-08-31)

Hareket ve hata etiketleme pencerelerinde yeni bir sınıf adı yazıp `Yeni …
türü ekle` denildiğinde taslak sınıf doğru biçimde tutuluyor, fakat `Kaydet`
düğmesinin uygunluk durumu yeniden hesaplanmıyordu. Bu nedenle sınıf ancak
dialog kapatılıp yeniden açıldıktan sonra atanabiliyordu.

- `MovementLabelDialog._creation_requested()` pending sınıfı kaydettikten
  sonra save gate'i yeniden hesaplıyor.
- `ErrorLabelDialog._sync()` pending sınıfta erken çıkmıyor; sınıf ile eklem
  doğrulamasını birlikte hesaplıyor. Yeni sınıf geçerli olsa bile
  “işaretlenen eklemler” seçilip node seçilmemişse kayıt hâlâ doğru biçimde
  engelleniyor.
- Yeni sınıfın gerçek oluşturulması ve aynı hareket/hata intervaline atanması
  mevcut `ReviewPage` akışında kaldı. Böylece proje sözlüğünün atomik yazımı,
  duplicate-normalization, iptalde sınıfın proje düzeyinde kalması ve hata
  intervalinin class + joint + note tek-işlem güncellemesi değişmedi.
- `tests/test_label_dialog_class_creation.py`, iki gerçek dialogda başlangıçta
  pasif olan `Kaydet` düğmesinin yeni sınıf tıklamasından sonra aynı pencere
  içinde etkinleştiğini ve gerçek Save tıklamasının dialogu kabul ettiğini
  sabitliyor.

Gerçek kod sürümleri değişmedi: app/package `0.10.0`, annotation/release
`2.2.0`, label `2.0.0`; diğer schema sürümleri bölüm 6K ile aynıdır.

Gerçekten çalıştırılan doğrulamalar:

- `tests/test_label_dialog_class_creation.py -q` → **2 passed**.
- İki mevcut sınıf oluşturma/atama ve iki eklem-save doğrulama testi →
  **4 passed**.
- Yeni dialog testleri + `test_review_flow.py` ve `test_annotations.py`
  içindeki `class` odaklı kapsam → **22 passed**. Bu komut önceki dört testten
  bazılarını tekrar içerir; sayılar bağımsız toplam gibi toplanmamalıdır.
- `scripts/run_tests.ps1 -Quiet` başlatıldı ve yaklaşık `%57` ilerlemeye kadar
  hata görülmedi; aynı makinedeki başka yüksek kaynaklı Python sürecine
  müdahale etmemek için bu Codex test süreci kullanıcıya bildirildikten sonra
  elle durduruldu. **Tam paket tamamlanmış veya geçmiş sayılmamalıdır.**

Bu küçük GUI durum düzeltmesinde ZED donanımı, self-test ve paket/wheel testi
çalıştırılmadı; kamera, export, şema ve paket kaynağı değiştirilmedi.

## 6M. 30 günlük zorunlu staj raporu için kaynak denetimi ve anlatı planı (2026-09-01)

Bu tur uygulama geliştirmesi değildir. KineCapture ile KineSynthV3'te bugüne
kadar yapılan gerçek çalışmaların, her biri yaklaşık 500 kelimelik 30 iş günü
anlatısına nasıl dönüştürüleceği planlandı. Günler, kesin commit tarihlerini
taklit eden bir günlük olarak değil; gerçekten yapılmış işleri pedagojik ve
teknik bağımlılık sırasına koyan **tematik iş paketleri** olarak ele alınacak.
Kodda, sonuç artefaktlarında veya test kayıtlarında kanıtı olmayan teknik
başarı, ölçüm ya da özellik rapora eklenmeyecek.

Kaynak önceliği şu şekilde kararlaştırıldı: gerçek kod ve sürüm sabitleri →
sonuç/manifest/test artefaktları → Git geçmişi → proje hafızası ve README →
açıklayıcı yeniden çizilmiş şema. Git commit tarihi, tek başına bir çalışmanın
stajın tam olarak hangi gününde yapıldığının kanıtı sayılmayacak. Nihai raporda
KineSynthV3 ve KineCapture için dengeli iki ana bölüm, son günde de iki sistemin
uçtan uca ilişkisi kullanılacak.

Bu incelemede doğrulanan repository gerçekleri:

- KineCapture Git geçmişinde 2026-08-20–2026-08-31 aralığında 9 commit vardır;
  gerçek kod sürümü **0.10.0**'dır. Şemalar: project 1.1.0, session 2.0.0,
  take/skeleton stream 1.1.0, annotation/release 2.2.0, label 2.0.0, feature
  spec/raw archive 1.0.0 ve identity SQLite 1. Bu değerler
  `pyproject.toml` ile `src/kinecapture/__init__.py` üzerinden yeniden
  doğrulandı.
- KineSynthV3 Git geçmişinde 2026-07-16–2026-08-18 aralığında 21 commit vardır;
  gerçek paket sürümü **0.3.0**'dır. Güncel README, kod ve kayıtlı sonuçlar;
  conditioned encoder çalışmalarının yanında pseudo-evidence decoder, weak
  temporal evidence eğitimi ve masaüstü evidence timeline/prediction panelini
  içerir.
- KineSynthV3 `project_memory.md` içindeki “encoder-only, evidence decoder
  uygulanmadı” durumu güncel kodla çelişir; raporda bu eski durum son gerçek
  durum gibi kullanılmayacak. Eski hafıza tarihsel aşama olarak, güncel kod ve
  `colab/results/` artefaktları ise mevcut durum için kullanılacak.
- KineSynthV3 içinde rapora doğrudan alınabilecek 54 conditioned-hybrid analiz
  figürü ile model sonuç görselleri vardır. KineCapture repository'sinde ürün
  ekran görüntüsü arşivi yoktur; rapor üretiminde mock backend ve gerekirse
  güvenli gerçek kayıt kullanılarak yeni, PII içermeyen ekran görüntüleri
  alınmalıdır.

Bu turda test paketi, self-test, GUI veya ZED donanım doğrulaması
çalıştırılmadı; yalnız salt-okunur kod, Git geçmişi, dokümantasyon, mevcut
sonuç artefaktı ve görsel envanteri denetlendi. Kaynak kod, paket ve şema
sürümleri değiştirilmedi. Çalışma ağacında daha önceden bulunan kullanıcı
değişikliklerine dokunulmadı; bu bölüm yalnız kalıcı raporlama kararlarını
ekler.

## 6N. Zorunlu staj raporunun ilk 5 iş günü belgesi (2026-09-01)

30 günlük rapor planının ilk beş günü, düzenlenebilir Word belgesi olarak
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Staj_Raporu_Ilk_5_Gun.docx`
yolunda üretildi. Kapakta yalnız kullanıcı tarafından verilen kurum bilgileri
kullanıldı: Yıldız Teknik Üniversitesi, Elektrik-Elektronik Fakültesi,
Kontrol ve Otomasyon Mühendisliği Bölümü ve araştırma laboratuvarı. Ad,
öğrenci numarası, staj tarihleri veya laboratuvarın özel adı uydurulmadı.

Günler sırasıyla proje bütününün incelenmesi, REHAB24-6 veri yapısı,
anotasyon/tekrar sınırları, tekrar bazlı indeksleme ve değişken uzunluklu veri
erişimi, KineSynthV3 masaüstü inceleme uygulamasını kapsar. Metinler birinci
tekil şahısla yazıldı; sözcük sayıları gün 1-5 için **509, 502, 500, 502 ve
500**'dür. YTÜ logosuna ek olarak her gün için kaynak proje artefaktlarından
bir teknik görsel, şekil açıklaması, kaynak satırı ve alternatif metin
eklendi. Belge 12 sayfadır.

Doğrulama olarak belge LibreOffice ile PDF/sayfa PNG'lerine çevrildi ve 12
sayfanın tamamı görsel olarak incelendi; kırpılma, taşma veya okunamayan görsel
görülmedi. `images_audit.py` altı görselin tamamının inline olduğunu,
`a11y_audit.py` yüksek/orta/düşük önem düzeyinde bulgu olmadığını ve
`heading_audit.py` beş adet Heading 1 başlığı bulunduğunu doğruladı. Bu turda
KineCapture/KineSynth kaynak kodu, kullanıcı verisi veya şemalar değiştirilmedi;
uygulama testi, self-test, GUI testi ve ZED donanım testi çalıştırılmadı.
Gerçek sürümler değişmedi: KineCapture **0.10.0** (annotation/release 2.2.0
dahil önceki bölümdeki şemalar), KineSynthV3 **0.3.0**.

## 6O. İngilizce staj raporu, 6–15. iş günleri (2026-09-02)

Kullanıcının sonraki raporlar için kalıcı biçim tercihi güncellendi: rapor dili
**İngilizce**, her günün ana metni **300–400 kelime**, düzen ise kopyalamayı
kolaylaştıran sade metin + inline proje görseli olacaktır. Özel kapak, dekoratif
sayfa öğeleri, görsel hizalama çalışması veya yoğun masaüstü yayıncılık düzeni
yapılmayacak. Günler kesin commit tarihlerini taklit etmeyecek; 6M'de
kararlaştırıldığı gibi gerçek çalışmaları teknik bağımlılık sırasına yerleştiren
tematik iş paketleri olarak yazılacaktır.

6–15. günler için düzenlenebilir Word belgesi
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_06_15_EN.docx`
yolunda üretildi. Konular sırasıyla eğitim zamanı preprocessing ve zamansal
standardizasyon, subject-wise split/leakage önleme, 26 eklemli graph ve CTR-GCN,
temporal Transformer + hibrit mimari, exercise-conditioned correctness,
training/checkpoint/reproducibility, Small/Medium/Large kapasite deneyi, pooled
OOF değerlendirme, weak temporal evidence modeli ve masaüstü evidence explorer
entegrasyonudur. Gün 6–15 ana metin sözcük sayıları sırasıyla **381, 377, 389,
367, 382, 364, 371, 344, 341 ve 362**'dir.

Belgede yalnız güncel kod/README ve kayıtlı sonuç artefaktlarıyla doğrulanan
değerler kullanıldı. P1–P9 ana benchmarkı 1.049 örnek ve dokuz katlı LOSO'dur;
conditioned kapasite sonuçları correctness balanced accuracy için Small 0.6163,
Medium 0.6985, Large 0.7514; weak temporal evidence final run sonucu 0.7612 BA
ve 0.7620 macro-F1'dir. Suspected interval'ların frame-level ground truth veya
klinik hata sınırı olmadığı açıkça yazıldı; conditioning müdahalelerinde
bağlantının pratik etkisinin zayıf olduğu da abartılmadan raporlandı.

Nihai DOCX LibreOffice ile 13 sayfaya render edildi ve sayfaların tamamı görsel
olarak incelendi; kırpılma, taşma, bindirme, boş sayfa veya görselden ayrılmış
caption görülmedi. Son erişilebilirlik metadata eklemesinden önceki ve sonraki
13 sayfa PNG'lerinin SHA-256 karşılaştırması tamamen aynıdır. `images_audit.py`
10 görselin tamamının inline olduğunu, `heading_audit.py` 10 adet Heading 1
bulunduğunu, `a11y_audit.py` ise yüksek/orta/düşük önem düzeyinde bulgu
olmadığını doğruladı. Bu turda uygulama kaynak kodu, kullanıcı verisi, paket veya
şema değiştirilmedi; KineCapture **0.10.0** (project 1.1.0, session 2.0.0,
take/skeleton stream 1.1.0, annotation/release 2.2.0, label 2.0.0,
feature/raw archive 1.0.0, identity SQLite 1) ve KineSynthV3 **0.3.0** olarak
kaldı. Uygulama testi, self-test, GUI testi ve ZED donanım testi çalıştırılmadı;
yalnız belge sözcük sayımı, render, görsel, başlık ve erişilebilirlik denetimleri
çalıştırıldı.

## 6P. Squat bacak takibi ve ertelenmiş iskelet işleme tanısı (2026-09-02)

Bu tur bir uygulama geliştirme turu değildir. Kullanıcının squat sırasında bir
veya iki bacağın dizden bükülmeyip gövdeyle birlikte düz aşağı indiği gözlemi
gerçek kayıtlar, kaynak kod ve ZED SVO2 yeniden oynatması üzerinde salt-okunur
incelendi. Uygulama kaynak kodu ve kullanıcı kaydı değiştirilmedi.

### Kök neden hakkında doğrulananlar

- `ZedCameraBackend._retrieve_bodies()` SDK'nın `body.keypoint`,
  `keypoint_2d` ve güven dizilerini eklem sırasını/geometrisini değiştirmeden
  `BodyPose` içine geçiriyor. Uygulama tarafında dizleri düzelten, yeniden
  eşleyen, yumuşatan veya önceki kareyle dolduran gizli bir dönüşüm yok.
- `take_20260902T075335_36a0` kaydının proxy görüntüsünde dip squatta iki diz
  de bükülmüşken BODY_34 çıktısı sporcunun sol kalça-diz-ayak bileğini neredeyse
  aynı düşey çizgiye koydu. Hata yalnız 3B derinlik üretiminde oluşmadı: SDK'nın
  kendi 2B keypoint'i de bu bacağı düz kabul etti. Sol diz güveni hatalı karede
  yaklaşık `0.971` idi; dolayısıyla yalnız güven eşiği yükseltmek bu örneği
  elemez.
- Aynı kayıtta kaydedilen 3B noktaların kamera intrinsics'iyle yeniden
  izdüşümü ile SDK 2B noktaları arasındaki medyan fark `0.00 px`, p95
  `0.01 px` çıktı. RGB/iskelet uzayı veya uygulama çizimi kayması kök neden
  değildir; yanlış poz SDK çıktısının kendi içinde tutarlıdır.
- ZED eğitim dataseti kamuya açık olmadığı için “model squat görselleriyle
  eğitilmedi” iddiası doğrulanamaz. Gözlenen hata bu olasılıkla uyumludur,
  fakat daha somut açıklama BODY_34 pose hattının önden squat geometrisinde
  yanlış bir kinematik çözüme kilitlenmesidir. Önden görünümde diz fleksiyonu
  büyük ölçüde kamera derinlik ekseninde olur; 2B kalça-diz-ayak bileği neredeyse
  üst üste gelebilir. Body fitting'in geçmiş ve insan kinematik kısıtlarıyla
  eksik eklemleri tamamlaması yanlış düz-bacak çözümünü sürdürebilir.
- SDK 5.4.1 varsayılanları yerel `KineSynth` ortamında okundu:
  `skeleton_smoothing=0.0`, `minimum_keypoints_threshold=0`,
  `allow_reduced_precision_inference=False`, `prediction_timeout_s=0.2`.
  Yani hata fazla smoothing veya reduced precision kullanımından gelmiyor.

### Aynı SVO2 üzerinde offline karşılaştırma

Kaynak SVO2 dosyalarına dokunmadan `svo_real_time_mode=False`,
`HUMAN_BODY_ACCURATE`, `NEURAL_PLUS`, body fitting açık olacak şekilde bütün
kareler sırayla yeniden işlendi.

- `take_20260902T075335_36a0`, BODY_34: 176 kare grab, 174 gövdeli kare,
  11.60 s (`15.17 işleme FPS`). Dört dip squat grubunun üçünde sol diz
  `178.8-179.0 derece` ile düz kaldı; yalnız bir tekrar doğru büküldü. Bu,
  offline işlemenin kare kaybını çözse bile aynı BODY_34 model hatasını tek
  başına çözmediğini kanıtlıyor.
- Aynı SVO2, BODY_38: 176 grab ve 176 gövdeli kare, 13.38 s (`13.16 işleme
  FPS`). Dört tekrarın tamamında iki diz de dipte yaklaşık `45-61 derece`
  aralığında büküldü.
- Bağımsız ikinci sorunlu `take_20260902T075046_63e2` kaydında BODY_34 dip
  medyanı sağ diz için `178.4 derece` idi. BODY_38 offline çıktısında dip
  medyanları sol `59.6`, sağ `57.2 derece` oldu (198/198 gövdeli kare).

Bu iki kayıt BODY_38'i squat için güçlü bir çözüm adayı yapıyor; yine de nihai
ürün kararı daha fazla kişi, kıyafet, mesafe ve kamera açısıyla kontrollü A/B
doğrulama sonrasında alınmalıdır. BODY_38 aynı donanımda BODY_34'ten daha yavaş
çalıştığı için canlı modda performans sorununu büyütebilir; offline modla iyi
eşleşmesinin nedeni budur.

### Canlı performans tanısı

- Kullanıcı ayarı HD1080, istek 25 FPS, NEURAL_PLUS,
  HUMAN_BODY_ACCURATE, BODY_34 ve body fitting açık. Kamera bu desteklenmeyen
  kombinasyonda gerçekte `30.0 FPS` raporladı; take profile 25'i saklarken
  `CameraInfo` 30'u saklıyor. GUI 1-120 arası her sayıya izin verdiği için
  çözünürlüğe bağlı desteklenen ZED FPS değerleri doğrulanmıyor.
- İncelenen HD1080 take'lerde ölçülen acquisition `14.17-15.67 FPS`, maksimum
  kare boşluğu `133-334 ms` idi. En son kayıtta 610 kare / 42.99 s,
  `14.17 FPS`; 15 derinlik karesi arşivlenemediği için take `PARTIAL` kaldı.
- Donanım: RTX 2060 6 GB, i7-10750H (6C/12T), 16 GB RAM. Canlı her grab'da
  sırasıyla renk, NEURAL_PLUS derinlik ve Accurate body tracking çalışıyor;
  writer ayrıca kayıpsız float32 derinliği sıkıştırıyor. HD1080/30 kaynak bu
  makinede yaklaşık yarı hızda tüketilebiliyor.
- `backend_dropped_frames` SDK'nın bağlantı boyunca kümülatif sayacının take
  içindeki maksimumudur; take başlangıcındaki değeri çıkarmadığı için kesin
  take-başına kayıp değildir. Mevcut değerler kayıp olduğunu gösterir fakat
  doğrudan toplanmamalıdır.

### Ertelenmiş işleme uygulanabilirliği ve mimari kapsamı

Resmî ZED sözleşmesinde SVO açıldığında depth/body tracking dahil modüller canlı
kamera gibi kullanılabilir. Dolayısıyla yalnız stereo SVO2 + hafif RGB önizleme
kaydedip iskeleti sonra, her kareyi sırayla ve gerekirse BODY_38/daha ağır bir
modelle üretmek teknik olarak uygulanabilir ve bu donanım için anlamlıdır.

Ancak mevcut kodda SVO input backend'i veya post-processing job katmanı yoktur.
Ürünleştirme için en az şunlar gerekir: canlı-iskelet ile raw-only modunu ayrı
provenance olarak saklamak; `awaiting_processing/processing/processed/failed`
durumları; ilerleme/iptal/yeniden deneme; SVO checksum + SDK/model/parametre
manifesti; staging'e yazıp atomik yayınlanan sürümlü `derived` çıktısı; offline
kişi seçimi/subject association; annotation'ın bağlı olduğu iskelet sürümünü
değiştirmeme veya yeniden işlemeyi annotation sonrası engelleme; crash recovery
ve GUI/test kapsamı. Bu nedenle proof-of-concept orta, güvenli ürün entegrasyonu
orta-yüksek zorluktadır.

Raw-only modda canlı derinlik hiç üretilmediği için “kayıt anındaki ölçülmüş
derinliği koruma” şartı uygulanmaz; SVO'dan sonra hesaplanan derinlik açıkça
`reconstructed_offline` provenance taşımalıdır. Ham SVO değişmez kalır.

### Kod/hafıza ile çelişen yan bulgular

- `ZedCameraBackend.start_native_recording()` profilin
  `native_compression` seçimini kullanmıyor ve her zaman `H264` yazıyor; buna
  rağmen manifest profil değerini beyan ediyor. Ayrıca aynı metodun docstring'i
  H264 kayıplı olmasına rağmen hâlâ “lossless-by-default” diyor. Offline kalite
  profili eklenmeden önce gerçek compression seçimi uygulanmalı ve manifest
  SDK'ya verilen gerçek değeri yazmalıdır.
- `configs/default.yaml` içindeki eski yorum SVO2'nin derinliği yeniden
  ürettiği için ikinci derinlik kopyasının gereksiz olduğunu söylüyor; gerçek
  runtime ve bu hafızadaki ölçüm bunun tersidir. Dataclass varsayılanı nedeniyle
  uygulama gerçekte `float32_lossless` arşivliyor, fakat shipped yorum/legacy
  `store_depth_frames: false` yanıltıcıdır.
- Kullanıcının güncel proje ve yedi gerçek take'i
  `C:\Users\gorke\AppData\Local\Temp\pytest-of-gorke\pytest-386\viewports0\...`
  altında. Identity DB ve `~/.kinecapture/user_state.yaml` da bu geçici yolu
  gösteriyor. Bu tur taşımadı veya yeniden yazmadı; Windows/temp temizliği veri
  kaybı yaratabileceği için yeni geliştirmeden önce kontrollü, checksum'lu bir
  kalıcı konuma taşıma/yeniden bağlama planı gereklidir.

### Bu turda gerçekten çalıştırılanlar ve sürümler

- Kaynak inceleme, yedi take metadata/quality/JSONL analizi, gerçek proxy
  karelerinin ve geçici overlay'lerin görsel incelemesi, iki SVO2 üzerinde üç
  offline ZED geçişi (BODY_34 bir kez, BODY_38 iki kez), yerel SDK varsayılan
  parametre introspection'ı ve donanım sorgusu çalıştırıldı. Geçici PNG'ler
  `%LOCALAPPDATA%\Temp\kinecapture_squat_diag_20260902` altında; dataset ve
  repository kaynakları değildir.
- Pytest, self-test, wheel veya canlı kamera testi çalıştırılmadı. Yeni bir
  canlı BODY_38 take alınmadı; BODY_38 sonucu kayıtlı SVO2 replay kanıtıdır.
- Uygulama/package `0.10.0`; project `1.1.0`, session `2.0.0`, take/skeleton
  stream `1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature/raw
  archive `1.0.0`, identity SQLite `1`. Hiçbiri değiştirilmedi.

## 6Q. İngilizce staj defteri gün 16–25 (2026-09-06)

Kullanıcının staj defterinin sonraki on günü İngilizce ve iş odaklı olarak
hazırlandı. Çıktı:
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_16_25_EN.docx`.
Her gün 300–400 sözcük sınırındadır: gün 16–25 sırasıyla 331, 334, 326, 331,
333, 328, 319, 344, 335 ve 327 sözcük. Konular kamera backend sözleşmesi,
deterministik mock backend, ZED 2i adapteri ve BODY topolojileri, threaded
capture/yazıcı kuyrukları, kurtarılabilir skeleton ve RGB-D kayıtları, subject
lock, senkron playback, iki seviyeli interval annotation, anatomik joint
evidence ve feature/release export işidir. Metin deney raporu anlatımından
kaçınıp birinci tekil şahısla yapılan geliştirme, hata önleme ve doğrulama
işlerini anlatır.

Belgede 11 inline görsel vardır. Altısı gerçek kaynak koddan oluşturulan,
dosya ve satırları görünür code screenshot'larıdır; beşi gerçek PySide6
bileşenlerinin disposable mock proje/kamera verisiyle offscreen çalıştırılıp
`grab()` ile alınan Capture, Review, Timeline, JointRolePicker ve
FeatureSelectionDialog görüntüleridir. Görsel üretimi gerçek kullanıcı
kayıtlarına, identity DB'ye veya kullanıcı tercihine dokunmadı; geçici dataset
ve LOCALAPPDATA kullanıldı. Kullanıcının mevcut kirli
`label_dialogs.py`, `test_shell_chrome_gui.py` ve
`test_label_dialog_class_creation.py` değişiklikleri korunup değiştirilmedi.

Gerçekten çalıştırılan doğrulamalar:

- Mevcut `KineSynth` environment'ında
  `tests/test_capture.py`, `tests/test_subject_lock.py`,
  `tests/test_rgbd_archive.py`, `tests/test_timeline_preview.py`,
  `tests/test_joint_annotation_gui.py`, `tests/test_export.py` ve
  `tests/test_export_features.py`: toplanan 189 testin tamamı geçti.
- DOCX, standart renderer ile 14 sayfa PNG ve QA PDF'e çevrildi; her sayfa
  görsel olarak incelendi. Başlıktaki varsayılan mavi çizgi kaldırıldı.
- `a11y_audit.py`: high/medium/low 0; `images_audit.py`: 11/11 inline;
  `heading_audit.py`: 10 adet Heading 1.

Uygulama/package `0.10.0`; project `1.1.0`, session `2.0.0`, take/skeleton
stream `1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature/raw archive
`1.0.0`, identity SQLite `1` olarak kaldı. Bu turda uygulama kodu, package veya
şema değiştirilmedi. Canlı ZED donanım testi, self-test, wheel/package testi ve
tam test paketi çalıştırılmadı; staj belgesindeki donanım adapteri anlatımı
gerçek kod sözleşmesine ve önceki doğrulanmış proje hafızasına dayanır.

## 6R. Staj defteri gün 16–25 anlatım akışı revizyonu (2026-09-06)

Mevcut
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_16_25_EN.docx`
dosyası yerinde güncellendi. Teknik kapsam, görseller ve günlük başlıklar
korundu; birbirine mekanik biçimde bağlanan "I then implemented..." türü
geçişler kaldırıldı. Her gün, o güne özgü bir gözlem veya amaçla başlayan,
gerektiğinde önceki günün sonucuna doğal biçimde değinen ve farklı kapanış
ifadeleri kullanan bağımsız bir staj günlüğü kaydına dönüştürüldü.

Revizyon sonrasında gün 16–25 sözcük sayıları sırasıyla 308, 325, 321, 313,
323, 315, 303, 340, 322 ve 314'tür; her gün 300–400 sözcük sınırındadır.
Belge 14 sayfa ve 11 inline görsel olarak kaldı. Standart renderer ile tüm 14
sayfa yeniden üretildi ve görsel olarak incelendi; kesilme, taşma veya bozuk
karakter görülmedi. `a11y_audit.py`: high/medium/low 0;
`images_audit.py`: 11 inline görsel; `heading_audit.py`: 10 adet Heading 1.

Bu revizyonda uygulama kaynak kodu, package veya şema değiştirilmedi; pytest,
self-test, canlı donanım ve wheel/package testi yeniden çalıştırılmadı.
Uygulama/package `0.10.0`; project `1.1.0`, session `2.0.0`, take/skeleton
stream `1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature/raw archive
`1.0.0`, identity SQLite `1` olarak kaldı.

## 6S. GPT-6 Astra squat/offline inceleme handoff'u (2026-09-10)

Bu tur uygulama geliştirmesi değildir. Kullanıcının squat alt-ekstremite
takip hatası, yaklaşık 15 FPS canlı performans sorunu, sonradan iskelet
çıkarma önerisi, antrenör odaklı GUI ve çoklu kişi gereksinimi; yeni bir
GPT-6 Astra görevinde eksiksiz kullanılmak üzere
`GPT6_ASTRA_KINECAPTURE_SQUAT_OFFLINE_INCELEME_GOREVI.md` dosyasında bir araya
getirildi. Dosya, Astra'nın önce kodu/veriyi/logu salt okunur yeniden
denetlemesini, en az üç ürün planı hazırlamasını ve kullanıcı onayı olmadan kod
uygulamamasını ister.

Güncel disk incelemesi önceki 6P kaydına önemli bir düzeltme getirdi:

- `~/.kinecapture/user_state.yaml` ve identity DB hâlâ
  `C:\Users\gorke\AppData\Local\Temp\pytest-of-gorke\pytest-386\viewports0\datasets`
  kökünü ve `prj_20260902T072943_e359` / `prj_20260903T124439_8b0e`
  projelerini gösteriyor, fakat bu klasör artık yoktur.
- Kullanıcı bu eski, daha kötü sonuç veren test kayıtlarını **kendisinin
  sildiğini** açıkladı. Bu durum istemsiz veri kaybı gibi raporlanmamalıdır.
  3 Eylül'deki 23.4 FPS kaydı ayrı bir testtir ve eski 15 FPS squat deneyiyle
  kontrollü aynı-koşul karşılaştırması değildir.
- Eski squat SVO/skeleton akışları bugün bulunmuyor; yeniden üretilebilir kanıt
  değildir. Buna karşılık `C:\Users\gorke\KineCapture\logs\kinecapture.log`
  içindeki 2–3 Eylül olayları ve
  `%LOCALAPPDATA%\Temp\kinecapture_squat_diag_20260902` altındaki yedi görsel
  hâlâ vardır.
- Kullanıcı profili altında bulunan tek kalıcı iki `.svo2` take 20 ve 21
  Ağustos BODY_34/HD720/30/HUMAN_BODY_MEDIUM/NEURAL_LIGHT kayıtlarıdır. Bunlar
  squat doğruluğu kanıtı değil, SVO playback/offline işleme mimarisi için
  kullanılabilecek eski şemalı teknik örneklerdir.
- Güncel kullanıcı tercihi HD720/30, QUALITY, HUMAN_BODY_ACCURATE, BODY_38,
  fitting açık ve float32_lossless depth arşividir; bu tercih eski take
  provenance'ı yerine kullanılamaz.

Kullanıcı, planlardan sonra gerekirse ZED'i bağlayarak Astra ile interaktif
test yapmaya açıkça izin verdi. Astra monitörde görünür RGB + iskelet penceresi
açabilir ve kullanıcı karşısında squat yaparken kontrollü A/B veri toplayabilir.
Handoff şu sınırları koyar: test amacı ve süresi önce açıklanacak; kullanıcı
hazır olmadan kayıt başlamayacak; GUI parolası kullanıcı tarafından girilecek
ve model parolayı istemeyecek/okumayacak; mevcut stale pytest kökü yeni kayıt
için kullanılmayacak; önce kalıcı test konumu doğrulanacak; BODY_34/BODY_38,
kamera açısı ve diğer değişkenler kontrollü değiştirilecek; her ham SVO
değişmez kalacak ve her klip sonunda finalize/kare/timestamp/checksum
doğrulanacaktır. Bu test izni kaynak kodu değiştirme izni değildir.

Bu turda gerçekten yapılan salt-okunur doğrulamalar:

- `AGENTS.md` ve 2417 satırlık mevcut `MEMORY.md` tamamen okundu.
- App/schema sürümleri gerçek kaynak sabitlerinden doğrulandı.
- Kullanıcı tercihi, yalnız `projects` alanlarını okuyan SQLite read-only
  bağlantısı, iki kalıcı take'in `take.json`/`quality.json`/dosya envanteri,
  uygulama logu, kullanıcı profilindeki SVO envanteri ve tanı PNG'leri
  incelendi.
- Donanım yeniden sorgulandı: RTX 2060 6 GB, i7-10750H 6C/12T, 15.8 GB RAM,
  driver 616.56; `KineSynth` Python 3.11.14 ve ZED SDK 5.4.1.
- Güncel resmî Stereolabs body tracking, depth mode/settings/retrieval ve SVO
  recording/playback belgeleri kontrol edildi. Resmî OpenAI GPT-6 Astra model
  kılavuzu yeni görevin model seçimi ve çok adımlı çalışma biçimi için
  doğrulandı.

Pytest, self-test, uygulama GUI'si ve canlı ZED bu handoff hazırlama turunda
çalıştırılmadı. Uygulama kaynak kodu, kullanıcı ayarı, identity DB, ham kayıt
ve şemalar değiştirilmedi. Gerçek sürümler değişmedi: app/package `0.10.0`;
project `1.1.0`, session `2.0.0`, take/skeleton stream `1.1.0`,
annotation/release `2.2.0`, label `2.0.0`, feature/raw archive `1.0.0`,
identity SQLite `1`. Önceden var olan kirli `label_dialogs.py`,
`test_shell_chrome_gui.py` ve `test_label_dialog_class_creation.py`
değişiklikleri korunmuştur; bu tur yalnız yeni handoff Markdown'u ve bu hafıza
bölümünü eklemiştir.

## 6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)

Kullanıcı `GPT6_ASTRA_KINECAPTURE_SQUAT_OFFLINE_INCELEME_GOREVI.md` içindeki
incelemenin uygulanmasını istedi. AGENTS.md, bu MEMORY.md'nin tamamı ve görev
dosyası okundu; gerçek kod, log, kullanıcı tercihi, read-only identity proje
alanları, iki kalıcı eski take ve tanı görselleri yeniden incelendi. Bu tur
uygulama geliştirmesi değildir: kaynak/test kodu, configs, şemalar, kullanıcı
tercihi, identity DB ve eski ham/türetilmiş kayıtlar değiştirilmedi. Rapor:
[KINECAPTURE_SQUAT_OFFLINE_INCELEME_RAPORU_2026-09-10.md](C:/Users/gorke/Desktop/KineCapture/KINECAPTURE_SQUAT_OFFLINE_INCELEME_RAPORU_2026-09-10.md).

Başlangıç Git ağacı temizdi; HEAD `d3182f5`. 6S/görev dosyasındaki eski dirty
liste güncel değildi; ilgili kullanıcı değişiklikleri commit içinde korunmuştu.
Bu turun repository değişiklikleri yalnız bu hafıza ve yeni rapordur. Yalnız
mevcut `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe` kullanıldı; paket
kurulmadı/güncellenmedi, environment oluşturulmadı, yeni kamera kaydı alınmadı.

### Bugünkü kanıt ve geçmiş kanıt ayrımı

- Eski kötü squat SVO'ları kullanıcı tarafından silinmiş; bulunmayan
  `pytest-386` dataset kökü, stale kullanıcı tercihi ve iki identity proje
  kaydı aynı durumda. Bunlar düzeltilmedi/DB'den silinmedi; kalıcı projeler
  içe aktarılmadı. Kullanıcı profilinin erişilebilir bölümünde yalnız iki
  Ağustos SVO bulundu. `rg` taraması ilgisiz bir Windows CloudStore alt yolunda
  hata verdi; bütün disklerde kesin yokluk iddiası değil.
- 2 Eylül depth kuyruğunda 15 kayıp/PARTIAL/610 kare yaklaşık 14.2 FPS ve
  3 Eylül 1078 kare/45.9 s/23.4 FPS olayları logdan bugün doğrulandı. 3 Eylül
  ayrı testtir, kontrollü 15→23.4 FPS iyileşmesi sayılmaz.
- Önceki squat BODY_34/38 açıları, reprojection medyan 0.00/p95 0.01 px ve
  yanlış diz confidence yaklaşık 0.971 **önceki ölçüm** olarak kaldı. Bugün
  ham kaynakla tekrar hesaplanmadı. Yerel tanı PNG'leri görsel kanıt olarak
  incelendi; hiçbir sporcu görüntüsü dış servise yüklenmedi.
- BODY_38 güçlü aday; eğitimde squat olmadığı bilinmiyor. En güçlü açıklama
  önden görünüm/örtüşme ile SDK poz tahmini/fitting davranışı. Tek sporcu ve
  iki geçmiş klip genelleme kanıtı değil. Offline aynı modelin semantik
  hatasını kendiliğinden çözmez.

### Yeni ve öncelikli hata: SDK depth tampon sahipliği

**Bugün gerçek SDK ve değiştirilmemiş RgbdArchiveWriter ile yeniden üretildi.**
`camera/zed.py:533` içindeki
`np.ascontiguousarray(self._mat_depth.get_data(), dtype=np.float32)`, SDK'nin
varsayılan `deep_copy=False` dönüşü zaten contiguous float32 olduğu için
kopya oluşturmuyor. FramePacket ve `RgbdArchiveWriter.add_frame()` de kopya
sahipliğini sağlamıyor; writer `np.asarray` ile veriyi chunk dolana kadar
tutuyor. Sonraki retrieve_measure önceki kare belleğini değiştirebiliyor.

Üç SDK depth karesi, her birinin bağımsız referans kopyası alınarak mevcut
yazıcıya chunk_frames=3 ile verildi. Arşivden geri okunan 0/1/2 karelerinin
kendi özgün verisine eşitliği `[false, false, true]`; son kareye eşitliği
`[true, true, true]`; ilk/son array ortak bellek taşıyor. Dört tam BODY
geçişindeki iki karelik probes da retained_previous_changed=true verdi.
Bu test canlı GUI üzerinden tam oturum değildir; etkilenen geçmiş kare sayısı
bilinmiyor. Fakat gerçek buffer/yazıcı kusuru doğrulanmış durumda.

Bu bulgu, eski “lossless canlı depth birebir korunuyor” genel kabulünü
geçersiz kılan önemli sınırlamadır: sıkıştırmanın kayıpsızlığı doğru anın
ölçümünün saklandığını kanıtlamaz. Önceki canlı/SVO replay depth farkının
büyüklüğü, tampon alias etkisi dışlanmadan yalnız SDK farkı sayılamaz. SVO
depth'i yine reconstructed_offline olarak tutulmalı; geçmiş ham depth
üzerine düzeltme yazılmamalı. Bu hata SDK'nin kendi squat skeleton geometrisi
ile ayrı bir sorundur. Onay sonrası en küçük öneri: SDK sınırında owned
snapshot, yeniden kullanılan tamponla regresyon, RAM/kopyalama ölçümü.
**Bu turda düzeltme uygulanmadı.**

### Gerçek offline deneyler ve yeni frame-map bulgusu

Geçici kök:
`C:\Users\gorke\AppData\Local\Temp\kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d`.
Deney öncesi yaklaşık 207 GB alan vardı; tam depth arşivi üretilmedi. Yalnız
3 karelik tampon deneyi yaklaşık 6 MB yazdı. `audit.py`, `followup.py`, JSON
özetleri, partial stream'ler ve test XML'i burada; bunlar geçici/türetilmiş.
Önemli sayılar kalıcı rapora aktarıldı. Aynı betikler aynı dosya adlarını
kullandığından mevcut dizinde körlemesine yeniden çalıştırılmamalı.

İki RGB-only, dört BODY_34/38 sıralı geçişi ve 40 karede bir kooperatif iptal
yapıldı. Kaynak HD720/30; RGB retrieval 640×360; body geçişleri ACCURATE,
NEURAL_PLUS, fitting/tracking açık, confidence 40, reduced precision kapalı,
svo_real_time_mode=False. Eski canlı take profili MEDIUM/NEURAL_LIGHT olduğu
için yeni sonuçlar aynı canlı profilin karşılaştırması değildir.

| Kaynak | SDK kare bildirimi / okunan | RGB decoding FPS | BODY_34 FPS / gövdeli kare | BODY_38 FPS / gövdeli kare |
|---|---|---:|---|---|
| take_20260820T165211_daeb | 668 / 667 | 69.43 | 17.02 / 609 | 14.80 / 615 |
| take_20260821T111845_4ed7 | 230 / 229 | 65.07 | 17.19 / 226 | 13.79 / 229 |

- B'de BODY_38 tüm 229 karede iki kişi buldu; BODY_34 hiç iki kişi bulmadı.
  Proxy'de ana oturan kişi ve sağda kısmen görünen başka kişi var. Daha fazla
  kişi bulmak squat doğruluğu veya doğru katılımcı eşlemesi kanıtı değildir.
- Body geçişleri kaynak 30 FPS'in altında olmasına rağmen RGB geçişinin aynı
  okunabilir konumlarını sıralı, tekrarsız ve ek iç boşluksuz işledi. Bu, yavaş
  offline işlemenin ek kare atlaması gerektirmediğini doğrular.
- A'da 0..666, B'de 0..228 okunuyor; SDK'nin bildirdiği son 667/229 konumuna
  ayrıca seek de EOF dönüyor. Bütün tam geçişler declared count kontrolünü
  geçemediği için partial tutuldu; başarılı publish yolu denenmedi. SDK EOF
  sayımı/eskiden kayıt sınırı/dosya sorunu ayrımı bilinmiyor. Otomatik N−1
  istisnası konmamalı.
- Her iki take'te live[1:] timestamp'leri mikro saniyeye nicemlendiğinde SVO
  0..N−2 ile tam eşleşiyor. Eşleşmeyen **canlı ilk kare**, ilk SVO timestamp'inden
  A'da 66.744899 ms, B'de 66.757700 ms önce. Bu “canlı son kare eksik” değildir.
  Bildirilen son SVO'nun okunamamasıyla nedenselliği kanıtlanmadı. Yeni offline
  skeleton'ı eskisinin üzerine yazmak annotation konumlarını kaydırabilir.
- 40 karede kooperatif iptal kaynak hash'ini değiştirmedi; yalnız partial çıktı
  bıraktı. Süreç kill, elektrik kesintisi, resume ve tracker durum devamlılığı
  test edilmedi.
- Aşama süreleri raporda: grab medyan yaklaşık 48–50 ms; body retrieval ve
  Python dizi hazırlığı BODY_34 yaklaşık 7.5–8 ms, BODY_38 yaklaşık 15–20 ms.
  GPU kernel profiling değil; grab saf depth süresi sayılamaz. Açılış hariç;
  tam proxy/depth yazımı yok. RGB FPS canlı NVENC/capture benchmark değildir.

### Diğer doğrulanan sözleşme açıkları

- `start_native_recording` H264 hardcode'u ve manifestte tercih codec'inin
  yazılması sürüyor. Playback `get_recording_parameters()` H265 döndürdü ama
  bu yeni RecordingParameters varsayılanıyla aynı; eski SVO codec'i olarak
  doğrulanmadı. Requested/applied/readback bilinmiyor ayrımı önerildi.
- Backend frame_index başarılı grab başına yerel sayaç; manifestteki “kameranın
  kendi sayacı” açıklaması yanlış. missing_frame_indices=0 sensör kapsamını
  kanıtlamaz. Backend cumulative drop sayısı take içi delta sayılamaz.
- stop_recording native stop → sentinel → writer join sırasındayken acquisition
  `_writer` var oldukça enqueue edebiliyor; zaman aşımı sonrası finalize riski
  var. Gerçek eski indeks farkının nedeni olduğu yalnız hipotezdir.
- finalize, take.json'u checksums'tan önce yazıyor; dosya bazında atomicity bütün
  kapanış işlemini atomik yapmıyor. İki eski take'te raw/proxy/skeleton mevcut
  checksum'la eşleşiyor, take.json eşleşmiyor. İnceleme öncesi/sonrası dosyalar
  aynı. `_ask_verdict` sonrası mutable kalite/not kaydı muhtemel açıklama,
  geçmiş olay nedeni kanıtlanmadı. Ham checksum ve mutable metadata ayrılmalı.
- Raw-only ürün modu ve genel SVO job katmanı yok. Reader sabit skeleton/proxy
  yollarını ve skeleton kare sayısını kullanıyor; export hazır olma durumu
  offline/QC bilmez. CaptureMode guided/free anlamı korunmalı, processing ayrı
  boyut olmalı. Bilinmeyen JSON alanı eklemek model/reader'ı düzeltmez.
- SubjectLock body/keypoint bağımlı; aynı tracker ID dönüşünü güvenilir sayan
  hızlı yol yanlış kişi riski taşıyor. select_subject displayed packet yerine
  yeniden peek timestamp'i alıyor. Yeni hint gösterilen kareye bağlanmalı.
  Genel tracking_coverage seçili kişiyi ölçmez; subject_coverage paydasında
  ambiguous kareler yok. Bunlar ayrı ve bütün ilgili kareler üzerinden ölçülmeli.
- Preview timer zaten acquisition'dan ayrı; yalnız GUI FPS azaltmak her grab'deki
  full RGB/depth/body işini kaldırmaz. FramePacket RGB/depth aynı H×W ister;
  düşük çözünürlüklü preview ayrı sözleşme gerektirir.

### Çalıştırılan testler ve sınırlar

- `-B -m kinecapture.tools.verify_zed_topology`: SDK 5.4.1 ile BODY_18 18/19,
  BODY_34 34/35, BODY_38 38/37 eklem/bağlantı eşleşti.
- Seçili 6 test dosyası: `test_zed_adapter.py`, `test_capture.py`,
  `test_rgbd_archive.py`, `test_subject_lock.py`, `test_storage.py`,
  `test_capture_subject_gui.py`.
- İlk koşu uzun audit temp yolu altında 13 failure + 14 setup error verdi
  (WinError 3 uzun yol sorunları). Aynı kapsam yeni kısa
  `C:\Users\gorke\AppData\Local\Temp\kcA3213` basetemp ile,
  `-B -m pytest -o addopts='' -q --tb=short -p no:cacheprovider` üzerinden
  **143 passed in 23.73s**. JUnit `pytest_short_path.xml` deney kökünde.
- Eski hafızadaki uzun yol sorununu yalnız proxy ile sınırlayan kabul doğru
  değil; metadata taraması/depth dosya erişimi de bu uzun yolda etkilendi.
  Kısa yolda test geçmesi uzun yol düzeltmesi değildir.
- Testler offscreen GUI ve mock yolları kapsar; SDK buffer alias regresyonu
  içermedikleri için yeni arşiv hatasını çürütmez. Yeni test kodu yazılmadı.
- Tam suite, self-test, gerçek camera capture, codec/precision/FAST A/B,
  koç pilotu, crash/power-loss/resume, başarılı atomic publish yapılmadı.
- Deneyler ve testler sonunda kaynak/test/config/pyproject, gerçek user_state,
  identity DB ve iki take içindeki 154 dosyanın hash+mtime kontrolünde değişen
  dosya yok. Kontrol MEMORY/raporu ve bütün kullanıcı diskini kapsamaz.
- Rapor teslim kontrolünde 10 ana bölüm, yerel bağlantıların varlığı/satır
  sınırları ve tablo sütunları doğrulandı; JUnit XML'de 143 test, 0 hata,
  0 failure, 0 skipped görüldü. `git diff --check` geçti. Yalnız MEMORY.md
  değişikliği ve yeni rapor working tree'de kaldı.

### Öneri ve kalıcı sınır

Raporda dört plan, 13 alanlı karşılaştırma, Faz 0–5, coach GUI/failure states,
offline kişi kartları/hafif tracker/hibrit/tek kişi alanı karşılaştırması,
en az 5 sporcu için kontrollü ZED matrisi ve önerilen başarı kapıları var.
Öneri: önce depth sahiplik + gözlemleme, ardından Plan 2 raw-only + sürümlü
offline BODY_38; canlı kişi ipucu ancak pilotta koç yükü gerektirirse Plan 3.
Plan 4 referans doğruluk yetersizse araştırma. Planlar **onaylanmış uygulama
kararı değildir**. Kaynak FPS ve squat doğruluğu garanti edilmedi.

Önerilen yeni mimaride raw hash/ledger, derived version, source frame map,
subject association revision ve annotation/release bağı ayrı korunmalı.
Tespitsiz kare atlanmamalı; canonical skeleton kural tabanlı sessiz düzeltilmemeli.
Resume'da tracker state saklanamıyorsa baştan/history replay gerekeceği açık
olmalı; N'ye seek edip ID sürekliliği varsayılmamalı. Şema numarası atanmadı.

Gerçek sürümler değişmedi: app/package `0.10.0`; project `1.1.0`, session
`2.0.0`, take/skeleton stream `1.1.0`, annotation/release `2.2.0`, label
`2.0.0`, feature/raw archive `1.0.0`, identity SQLite `1`. Eski iki take
app `0.3.0`, take/skeleton `1.0.0`; migration yapılmadı. Yerel Python 3.11.14,
SDK 5.4.1, driver 616.56, RTX 2060 6 GB, i7-10750H, yaklaşık 15.84 GiB RAM
yeniden sorgulandı; kamera listesi boştu. Resmî Stereolabs belgeleri güncel
olarak kontrol edildi; belgedeki başka donanım FPS'i bu makineye taşınmadı.

Görev talimatı gereği rapor tesliminden sonra duruldu. Uygulama geliştirmesi
ayrı kullanıcı onayını bekler; bu tur onay için yeniden kamera bağlama şartı
konmadı ve gereksiz veri/yol düzeltmesi yapılmadı.

## 6U. İngilizce staj defteri gün 26–30 (2026-09-11)

Kullanıcının devam isteği üzerine staj defterinin son beş günü İngilizce olarak
hazırlandı ve
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_26_30_EN.docx`
yoluna kaydedildi. Önceki raporun sade Word düzeni şablon olarak korundu; yeni
belge 8 sayfa, 5 `Heading 1` gün başlığı ve 5 satır içi görsel içeriyor. Günlük
metin uzunlukları sırasıyla 368, 357, 332, 352 ve 351 kelime. Günlerin açılışları
ve anlatım akışı birbirinden farklı tutuldu; kronolojik bir laboratuvar özeti
yerine o gün yapılan mühendislik işine odaklanıldı.

Rapor kapsamı gerçek kod ve yerel kanıta dayanıyor: gün 26 kayıtlı squat
verisindeki BODY_34 düz-bacak hatasının BODY_38 ile karşılaştırılması; gün 27
değişmez SVO2 kaynağını merkeze alan raw-first kayıt profili; gün 28 kayıttan
bağımsız, bounded latest-frame önizleme çalışanı; gün 29 hash korumalı,
iptal/yeniden başlatma destekli ve atomik yayımlanan offline işleme; gün 30 ise
checksum doğrulamalı review sınırı ve canonical source anchor kullanımı. Yerel
Squat BODY_34 overlay karesiyle birlikte `CaptureProfile`, `LatestWorker`,
`process_take` ve `ReviewDataset` gerçek kod parçalarından dört okunabilir görsel
üretildi. Bu rapor turunda uygulama kaynak koduna veya şemalara değişiklik
yapılmadı; kullanıcının mevcut working-tree çalışması korundu.

Rapor hazırlanırken gerçek sürümler yeniden doğrulandı: app/package `0.11.0`,
project `1.1.0`, session `2.0.0`, take/skeleton stream `1.2.0`, raw archive
`1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature `1.0.0`, identity
SQLite `1`. Seçilmiş mimari ve işleme testleri önce varsayılan uzun Windows temp
yoluyla çalıştırıldı: 17 geçti, `Path.exists()` uzun türetilmiş yol sınırına
takıldığı için 1 test kaldı. Aynı kapsam kısa ve izole
`--basetemp C:\Users\gorke\AppData\Local\Temp\kc_report_2630` ile tekrarlandı;
18 test 5.50 saniyede geçti. Bu sonuç kısa çalışma yolundaki uygulama
davranışını doğruluyor, Windows uzun-yol hassasiyetini ortadan kaldırmıyor.

Belge kalite kontrolünde DOCX ZIP bütünlüğü geçti, beş başlık/beş görsel ve eski
gün 16–25 metninin bulunmadığı doğrulandı. Sekiz sayfanın tamamı render edilip
görsel olarak incelendi; kırpılma, üst üste binme, eksik görsel veya bozuk
karakter görülmedi. Erişilebilirlik denetimi high/medium/low için `0/0/0`, görsel
denetimi 5 inline şekil, heading denetimi 5 başlık verdi. Tam pytest paketi,
uygulama self-test'i, wheel/package testi ve bağlı canlı ZED testi bu rapor
turunda çalıştırılmadı.

## 6V. Capture → Verileri Hesapla → Etiketleme backend devamı (2026-09-11)

Bu bölüm, eski canlı zorunlu RGB-D ürün kararlarını yeni kayıtlar için geçersiz
kılar. Kullanıcının “Tüm yeni kayıtlarda minimum ham kayıt varsayılan olsun”
yanıtı ve `KINECAPTURE_BACKEND_YENI_MIMARI_DEVAM_PROMPTU.md` yönü uygulandı.
`3706cbe` içindeki ownership/boundary/lifecycle düzeltmeleri korundu. Bu tur
commit yapılmadı; yeni uygulama çalışma ağacındadır. Ayrıntılı teknik teslim:
`KINECAPTURE_BACKEND_MIMARI_UYGULAMA_RAPORU_2026-09-11.md`.

### Kalıcı kararlar ve gerçek uygulama

- Yeni CaptureProfile: HD720/60, H264_LOSSLESS, policy 2; final canlı body/depth,
  skeleton/proxy ve ayrı RGB/depth arşivi varsayılan kapalı. Kapalı ürünün SDK
  modülü, retrieval/kopya, writer/encoding/sıkıştırması gerçekten devreden çıkar.
  Kullanıcı dosyasını değiştirmeyen `for_new_capture` eski tercihleri bu yeni
  başlangıca taşır; tarihsel take/session `from_dict` legacy profili korur.
- ZED raw kaynak SVO2'dir. Mock, saklanan renk ve sentetik generator provenance'ı
  üzerinden replay edilir. Doğrudan legacy mock test akışı ayrıca korunur.
- Görüntüsüz FramePacket kaynak çözünürlüğünü taşır. RGB preview küçük ve
  seyrektir; tüm çözünürlükte RGB ancak seçilen ürün gerektirirse kopyalanır.
- `preview/LatestWorker` tek slot, bloklamayan offer, latest-frame-wins ile
  inference ve kullanıcı frame listener'larını acquisition thread'inden ayırır.
  `CpuPosePreview`, mevcut OpenCV DNN ile CPU'da hafif 2D kişi/pose gösterir.
  Bu çıktı metrik iskelet veya participant identity değildir. OpenCV Zoo commit
  `47534e27c9851bb1128ccc0102f1145e27f23f98`, Apache-2.0 lisans/NOTICE taşınır.
  İki ONNX model ~/.cache/kinecapture/models altında checksum doğrulamalı veri
  dosyasıdır. Yeni conda environment/paket kurulmadı veya yükseltilmedi.
- Operatör seçimi gösterilen görüntünün source timestamp/resolution, nokta ve
  bbox anchor'ıdır. Kayıt anında raw sidecar'a yazılır; capture lifecycle kilidi
  kapanış/checksum sırasında değiştirilmesini önler. Düzeltme/reprocess için
  yeni processing parametresi olarak anchor verilir, eski raw değiştirilmez.
- SDK dizileri owned/read-only snapshot; RGB-D writer mutable dış girdiyi de
  korur. Sonlu iskelet float32 değerleri JSON'da ondalık quantization olmadan
  geri gelir. Body/image timestamp ve is_new kontrolü eski sonuç kullanımını
  engeller. Malformed zorunlu SDK body alanları integrity issue üretir.
- Kayıt start/stop, grab+enqueue ile aynı sınırda; kontrol işlemi önceliklidir.
  Writer/codec işçisi bitmeden dosya kapatılmaz/finalize edilmez; timeout'ta
  kaynak sahipliği korunur. Dolu kuyruğa sentinel beklenmez. JSONL fsync hatası
  artık yutulmaz. Eksik/boş native SVO2, yazım hatası, queue/backend kaybı veya
  bildirilen bütünlük hatası başarılı take sayılmaz. Checksum final take.json
  commit'inden önce gelir; mutable curation dosyası checksum'a dahil değildir.
- Canlı frame_index **successful-grab ordinal**; fiziksel kamera sayacı veya
  SVO position değildir. Native ingested/encoded değerleri ham telemetridir,
  doğrulanmış sayım değildir. Timestamp gap/jitter, queue loss ve backend delta
  ayrı kaydedilir. `awaiting_processing` take export'a hazır sayılmaz.
- `processing/process_take`: gerçek sıralı SVO replay, svo_real_time_mode=False,
  varsayılan BODY_38/ACCURATE/NEURAL_PLUS/fitting/full precision. GUI/Qt bağımlılığı
  yok. Her deneme farklı .partial dizin; kaynak SHA/provenance + parametreler +
  calibration override SHA + SDK + job state/progress/hata tutulur. Complete
  ancak dosyalar kapanıp kapsam/QC/checksum geçtikten sonra atomik rename ile
  yayımlanır. Restart baştan replay eden yeni denemedir, tracker geçmişini
  atlayarak append etmez. Kaynak değişmişse restart reddedilir.
- Eşleme: tekil camera timestamp floor(ns/1000) eşitliği. Ne yakın komşu ne N−1
  kaydırma kabul edilir. Declared/decode sayısı ve source/capture unmatched,
  source ordinal/timestamp sürekliliği ayrıca denetlenir. Subject belirsiz/eksik
  ise maskeler/NaN korunur. Aynı tracker ID büyük konum/anatomi çelişkisini
  geçersiz kılamaz; belirsizlik onaysız otomatik kilitlenmez (association 1.1.0).
- `ReviewDataset`: checksum'lı complete processing sürümü, hazır proxy/arrays/
  skeleton/features. Yeni annotation sidecar source fingerprint + source
  position + camera timestamp inclusive sınırlarına bağlıdır. Eski segments.json
  anlamı otomatik değiştirilmez; production GUI yeni mimariye göre yeniden
  geliştirilmedi. `tools/capture_diagnostic.py` bağımsız görünür test viewer'ıdır.

### Sürümler

App/package **0.11.0**, take/skeleton stream **1.2.0**, raw archive **1.1.0**,
capture policy **2**, processing **1.0.0**, canonical annotation sidecar **1.0.0**,
subject association **1.1.0**. Project **1.1.0**, session **2.0.0**, eski
annotation/release **2.2.0**, label **2.0.0**, feature spec **1.0.0**, identity
SQLite **1** kaldı. Scientific environment hâlâ KineSynth / Python 3.11.14,
ZED SDK 5.4.1. Sürümleri ancak gerçekten kodda değişmiş oldukları için yazıyoruz.

### Çalıştırılan kontroller ve sınırları

Kanıt dizini `C:\Users\gorke\AppData\Local\Temp\kcb_8af98122`:

- Backend/özellik/export/config kapsamı ilk çalışmada 244 passed + 2 eski
  beklenti başarısız (246 toplam, backend10.xml). Bunlar eski BODY_34 default
  ve artık hatalı depth açıklaması beklentisiydi; yeni kararlar için düzeltildi.
  Takip kapsamı **63 passed / 11.87 s** (remaining13.xml).
- Capture/genel GUI **56 passed / 22.18 s** (gui12.xml).
- SDK BODY_18/34/38 → disk → playback eklem/timestamp bütünlüğü, config ve
  offline anchor dahil **38 passed / 5.24 s** (final14.xml).
- Preview/listener bloklanırken kayıt ilerlemesi, eksik SVO2, kayıt sınırları,
  orta-akış iptali dahil **23 passed / 7.18 s** (closure16.xml).
- Modül-fixture tercih izolasyonu ve user-state **6 passed / 3.96 s**
  (isolation15.xml). Önceki ara sonuçlar/başarısız denemeler raporda belirtilir;
  örtüşen test sayıları toplanmaz.
- `python -B -m kinecapture --self-test` exit 0: 66 kare, playback, etiketleme,
  RGB-D arşivi, iki hareket/bir sürekli örnek export doğrulaması geçti.
- Yeni Python sürecinde processing/review import: PySide6/pyzed yüklenmedi.
  `git diff --check` geçti. Tam pytest başladı fakat GUI uzun beklemelerinde
  kesildi; **tam paket geçti denemez**. Wheel/install ve tam GUI matrisi yok.
- Gerçek eski B SVO: yeni RGB/proxy processing yolu 230 declared / 229 decoded,
  bütün okunabilir kareler işlendi; beklenen count/unmatched gerekçeleriyle
  partial. Max timestamp gap 33.424 ms, std 0.05975 ms, büyük gap 0. Kaynak
  immutable kaldı (svo_pipeline/.run_9562dcb98445424a.partial).
- Sınırlı gerçek SDK üç-kare depth kontrolü: üç farklı hash, sonraki okumalar
  önceki depth'i değiştirmedi, owned/read-only (bounded_depth_preview.json).
  Aynı görüntülerde CPU hafif pose 1 kişi ve 153.9/99.3/99.3 ms. Canlı hız veya
  tüm kişileri bulma garantisi değildir.
- Üç gerçek BODY_38/full precision SVO karesi: her karede iki kişi/38 eklem,
  timestamp/is_new integrity sorunu yok (bounded_sdk_body38.json).
- İki saniyelik sentetik diagnostic finalized; ara örnek source 58.55 FPS,
  queue loss 0; preview 14 tamamlanan / 45 atlanan. Bu ZED benchmark'ı değildir.

### Testte kullanıcı tercih sızıntısı ve onarım

Başlangıç baseline'ı 15 kullanıcı dosyasında karşılaştırıldı. 14 dosya (ham eski
kayıtlar ve gerçek identity DB dahil) değişmemişti; `test_gui_viewports.py`
module-scope fixture'ı function-scope autouse izolasyonundan önce çalışıp gerçek
`~/.kinecapture/user_state.yaml` içine kcbtest07/viewports0 yolunu yazmıştı.
Bu çalışma sırasında yakalanan gerçek yan etkidir; gizlenmedi.

Bozuk sürüm kanıt dizinine yedeklendi. Aynı görevin önceki dosya okuma kaydından
özgün byte'lar çıkarıldı; ancak önceki SHA-256
`1df1e90ee374767b56a7e38174567e234baad218c80dd04db7c12ad647a1e2e0` ile birebir
eşleştikten sonra dosya ve baseline mtime geri yüklendi. Session-scope dış
izolasyon ve fixture başlamadan güvenli yol kontrolü eklendi. İlgili fixture
yeniden çalıştırılıp geçti. Kullanıcının zaten eski pytest-386 yolunu içeren
önceden bozulmuş dataset tercihine ayrıca ürün müdahalesi yapılmadı. Diagnostic
bu yüzden açık output yolu ister ve kullanıcının tercih dosyasını okumaz.

Son testlerden sonraki nihai kontrolde korunan 15 kullanıcı dosyasının tamamı
başlangıç SHA-256 ve mtime değerleriyle birebir eşleşti; değişen dosya 0.
Kanıt: `C:\Users\gorke\AppData\Local\Temp\kcb_8af98122\protected_data_final.json`.

### Devam noktası — donanım bekleniyor

Yeni canlı ZED kaydı henüz alınmadı. Gerçek 60 FPS, H264_LOSSLESS bilgi koruması,
native sayaç doğruluğu, preview açık/kapalı ve display açık/kapalı etkisi,
görüntüden kişi anchor seçimi, yeni düzgün kapanmış SVO'nun tam decoded/timestamp
kapsamı ve BODY_38 offline sonucu ölçülecek. Mevcut evidence bunları kanıtlamaz.
Kamera bağlanması istendiğinde burada durulur; kamera beklerken polling, yeni
pahalı test veya eski uzun SVO deneyi yapılmaz. Sonraki adım küçük bağımsız
diagnostic viewer ile kullanıcı eşliğinde kontrollü kısa kayıttır.

## 6W. Staj defteri zamanlama dili denetimi ve portal metinleri (2026-09-11)

Dört staj DOCX'i salt okunur olarak tarandı; ZIP bütünlükleri geçti ve toplam
30 gün başlığı doğrulandı. Çıktı
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\Internship_Report_Form_Texts_and_Timing_Audit.txt`
yoluna UTF-8 düz metin olarak yazıldı. Mevcut DOCX'ler değiştirilmedi.

Günlük ana metinlerinin büyük bölümü o güne ait çalışma kaydı gibi okunuyor.
Dokuz riskli/meta ifade konumuyla birlikte işaretlendi: ilk beş gün girişindeki
`taslak bölüm`; gün 8 ve 10'daki sonradan bilinen modeli anlatan `later`
ifadeleri; gün 16–25 ile 26–30 girişlerindeki `this section records...` ve
sonradan görsel üretimini açıklayan cümle; gün 25'te `last day of this section`
ve `ten-day period`; gün 30'da `I concluded the thirty-day report`. Her biri
için günlük dilini koruyan kısa alternatif verildi. `today`, `yesterday` ve
`the previous day` ifadeleri kronolojiyi desteklediği için sorun sayılmadı.
Ek tutarlılık riski: gün 1–5 Türkçe, gün 6–30 İngilizcedir.

Portal için kısa, resmî İngilizce `Table of Contents`, 129 sözcüklük `Abstract`,
kurumun tam adı/adresi/tarihçesi/faaliyet alanı/organizasyon yapısı ve 120
sözcüklük `Conclusion` hazırlandı. `Internship Activities, Job Descriptions and
Content` yalnız içindekiler girdisi olarak geçer; kullanıcı talebi gereği bu
bölüm için gövde metni yazılmadı, çünkü sistem günlük metin ve görsellerden
otomatik üretecek. YTÜ resmî sayfalarından Davutpaşa Kampüsü A Blok adresi,
üniversitenin 1911 kökeni, 1992 adı ve Kontrol ve Otomasyon Mühendisliği
Bölümünün 2009'da bağımsız bölüm oluşu kontrol edildi.

Bu turda uygulama kaynak/test/config dosyaları, kullanıcı kayıtları, şemalar ve
dört DOCX değiştirilmedi. Uygulama pytest'i, self-test, wheel, GUI render'ı veya
ZED donanım testi çalıştırılmadı; görev metin denetimi ve TXT üretimiydi. Gerçek
sürüm sabitleri yeniden okundu: app/package `0.11.0`, project `1.1.0`, session
`2.0.0`, take/skeleton stream `1.2.0`, raw archive `1.1.0`, annotation/release
`2.2.0`, label `2.0.0`, feature `1.0.0`, identity SQLite `1`. Kullanıcının
önceden var olan geniş backend/processing working-tree değişiklikleri korundu.

## 6X. Tek kişiyle operatör kontrollü ZED testi — devam ediyor (2026-09-13)

Kullanıcı ZED'i bağladı; testte yalnız kendisi var. Baş/ayak kadrajını görüp
kaydı kendi başlatıp durdurmak istiyor. Yeni bağımsız
`tools/live_validation.py` penceresi bu amaçla eklendi: kırpılmayan RGB,
isteğe bağlı hafif 2D iskelet, model tahmini olduğu belirtilen kadraj ipucu,
Başlat/R, Durdur/Esc, iptal edilebilir 8 saniye hazırlık, varsayılan 20 saniye
kayıt üst sınırı ve Testi bitir. Ağır start/stop/finalize ayrı kontrol işçisinde;
ham kayıt kullanıcı düğmesi olmadan başlamaz. Tek kişinin seçimi kullanıcının
açık talebine dayanır; görüntü timestamp'li anchor yalnız kayıt başladıktan
sonraki tek ve kadrajda görünen kişi karesine yazılır. Çok kişili doğrulama yok.

Sentetik kontrol ilk turda 8 geçti / 1 hata: UI Take.duration_s yerine gerçek
Take.metrics.duration_s okumalıydı. Düzeltildikten sonra canlı test penceresi
ve capture architecture kapsamı **9 passed / 2.65 s**; JUnit
`C:\Users\gorke\KineCapture\zed_20260913\ui_tests_retry.xml`.
Geri sayımı iptal etmek kayıt yaratmıyor; manuel stop ve aktif kayıtta pencere
bitirme iki ayrı finalized mock take üretiyor. Yeni environment/paket yok.
App/package 0.11.0; take/skeleton 1.2.0, raw 1.1.0, processing 1.0.0,
canonical annotation 1.0.0; diğer şemalar 6V ile aynı ve değiştirilmedi.

SDK 5.4.1 ZED 2i S/N 31844341 AVAILABLE; 1280×720, 60 FPS, gerçek depth NONE,
body kapalı bağlantı doğrulandı. Başlangıç boş disk yaklaşık 203 GB.
İlk set `C:\Users\gorke\KineCapture\zed_20260913` altında 60 ve 40 saniyelik
iki gerçek kayıt içeriyor. Kullanıcı görüntüleri beğenmediğini ve kullanım
kesintisi yaşandığını belirterek **yeni set istedi**. İlk set silinmedi;
asıl yeni değerlendirme `C:\Users\gorke\KineCapture\zed_20260913_b` altındadır.
Yeni pencerede kullanıcı kontrollü çekim devam ediyor; GPU offline işi pencere
Testi bitir ile kapatılmadan başlamayacak. İki ilk 20 saniyelik yeni kaydın
ikisi de front_pose seçimiyle kaydedilmiş; ikinci çekimin gerçek yönü soruldu.
Kaynaklar partial: native status false olayı var; tek başına başarı iddiası
yok. SVO yeniden okuma ve nihai rapor henüz tamamlanmadı. Bu bölüm geçici devam
noktasıdır; bitince gerçek ölçümler ve doğrulanamayanlar eklenmelidir.

## 6Y. PySide6 arayüz yeniden yapımı — F0 hafıza politikası + F1 tespiti (2026-09-13)

`CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md` F0 ve F1 yapıldı. Üretim
kodu **değiştirilmedi**. Ayrıntılı rapor:
`F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

**F0 — hafıza politikası.** `MEMORY_INDEX.md` (6138 bayt) eklendi; bu dosyanın
başına arşiv uyarısı kondu ve "her oturumda tamamını oku" kuralı kaldırıldı.
Giriş noktası artık indekstir; buradan yalnız ilgili bölüm hedefli okunur.

### F1 — ölçülen kalıcı gerçekler

Hepsi bu makinede, `KineSynth` / `QT_QPA_PLATFORM=offscreen` ile çalıştırıldı.

- **Üretim arayüzü yeni backend'i tanımıyor.** Yeni varsayılan profille alınan
  bir ham kayıt (`store_skeleton=False`, `store_proxy=False`,
  `processing_status=awaiting_processing`) mevcut `load_take()` yolundan
  açıldığında 302 kare, **0 gövde**, `spec=None`, proxy yok veriyor:
  `take_reader.py:677` bu durumda `raw/rgbd/index.jsonl` dosyasını iskelet
  akışı sanıyor. `ReviewPage` `derived/processing/run_*` dizinine hiç bakmıyor,
  `ReviewDataset` GUI'de hiç kullanılmıyor. **Yeni kayıtlar arayüzden
  etiketlenemiyor.**
- **Capture'da kişi seçimi ölü.** `select_subject_at_pixel` → `packet.bodies`;
  yeni profilde canlı body tracking kapalı olduğu için liste hep boş. Yeni
  mimarinin `set_subject_anchor` + `CpuPosePreview` yolu yalnız
  `tools/live_validation.py` ve `tools/capture_diagnostic.py` içinde; `gui/`
  altında tek referansı yok.
- **Offline hat CLI'dan uçtan uca çalışıyor:** mock raw-only take →
  `python -m kinecapture.processing` → `state=complete`, 302 kare, 4,7 s,
  `issues: []`; `ReviewDataset` 0,11 s'de açılıyor, 9 dizi + 302 karelik proxy
  + canonical anchor veriyor.
- **Zaman çizelgesi bütçenin ~18 katı üstünde.** `TimelineWidget` tam görünüm
  yeniden çizimi: 5 dk/30 FPS **323 ms**, 60 dk/60 FPS **292 ms**, 1000 kareye
  zoom **84 ms** (hedef ≤16 ms). Maliyet kare sayısından değil piksel sütunu
  başına Python/numpy çağrısından geliyor: cProfile'da `_paint_availability`,
  `_x_to_frame` ve `np.clip` (10 boyamada 38 550 çağrı) baskın. Statik katman
  pixmap önbelleği ve çok çözünürlüklü özet yok.
- **Etiketleme açılışı GUI thread'ini kilitliyor.** `load_skeleton_stream`
  senkron ve bütün kareleri Python nesnesine çeviriyor: 20 000 kare × 1 gövde
  (BODY_38) = **5,95 s / 28,5 MB**; × 2 gövde = **12,41 s / 51,4 MB**.
  Doğrusal tahminle 60 dk/60 FPS ≈ 64 s / 308 MB (tek gövde). *Tahmin gerçek
  60 dakikalık kayıtla doğrulanmadı; kare başına ölçüm gerçektir.*
- **Diziler bellek eşlemeli değil.** `savez_compressed` + tam RAM okuma:
  60 dk/60 FPS/BODY_38 için 0,73 s / **135 MB**; aynı veri `.npy` memmap ile
  600 karelik pencere 7,5 ms / 0,27 MB.
- **`DatasetIndex` her yenilemede klasör tarıyor** (önbellek isabet etse bile):
  1000 kayıt / 2000 json için `rglob`+`stat` **650 ms**, GUI thread'inde.
  `DatasetPage` `QTableWidget` + hücre başına item kullanıyor: 1000 satır ×
  9 sütun = 36 ms, 5000 satır = 183 ms.
- **Bütçeyi tutanlar (körlemesine "optimize" edilmemeli):** soğuk açılış
  **0,96 s** (hedef ≤3 s); proxy scrub **8,6 ms** medyan, p95 11,3 ms
  (hedef ≤50 ms); sıralı oynatmada kare okuma 0,7 ms. `ProxyVideoReader`
  seek'i darboğaz değildir.
- **Promptun öngördüğü backend eksiklerinin hepsi doğru çıktı:** `.npy` memmap
  yok, timeline özeti yok, thumbnail yok, `ReviewDataset`'te derinlik erişimi
  yok, iş kuyruğunda duraklatma/ETA yok, özet indeksi yok. Ek olarak
  `ReviewDataset.position_of_anchor` her çağrıda `source_map`'i doğrusal
  tarıyor.
- Mimari katman (`viewmodels/`, `services/`), `tokens.json`/QSS üretici,
  pencere durumu kalıcılığı ve altı yardımcı pencereden beşi yok; 3B görünüm
  hâlâ `QPainter` (`QOpenGLWidget` değil).

### Test durumu (2026-09-13)

- `python -m kinecapture --self-test` → **exit 0** (eski canlı-iskelet profili;
  raw-only → processing → review zincirini kapsayan self-test yok).
- 39 test dosyası tek tek çalıştırıldı, toplam ≈6 dk: **38 dosya yeşil**,
  `tests/test_raw_capture_fields.py` **5 test kırmızı** —
  `AttributeError: 'object' object has no attribute 'ERROR_CODE'`. Test
  yardımcısı `sl` yerine düz `object()` veriyor; 6V'de `_retrieve_bodies`
  içine eklenen `_check_retrieval` `sl.ERROR_CODE` okuyor. Uygulama hatası
  değil, stub eskimesi — ama adapter bütünlük kontrolü şu an korumasız.
- `pytest tests/` **tek süreçte** ~28 dakikada bitmedi; süreç bu sürede yalnız
  ~289 s CPU harcadı (bekliyordu), elle durduruldu. Aynı belirti 6V'de de
  kayıtlı. Neden bulunamadı. **"Tam paket geçiyor" denemez.**

Sürümler değişmedi: app 0.11.0; take/skeleton 1.2.0, raw 1.1.0, processing
1.0.0, canonical annotation 1.0.0, subject association 1.1.0, project 1.1.0,
session 2.0.0, eski annotation/release 2.2.0, label 2.0.0, feature 1.0.0,
identity SQLite 1.

**Onay bekleyen:** F1 önceliklendirmesi ve `PROCESSING_SCHEMA_VERSION`
1.0.0 → 1.1.0 gerektirecek toplamsal backend ekleri (memmap dizileri, timeline
özeti, thumbnail, derinlik/anchor erişimi, türetilmiş özet indeksi). Onaysız
F2'ye başlanmadı.

## 6Z. Studio arayüzü F2 — katman, token, kabuk (2026-09-13)

Plan dosyası: `FAZ_PLANI_PYSIDE6_STUDIO.md` (faz sırası, kapsam dışı, ilerleme
kaydı orada; burada yalnız kalıcı kararlar ve ölçümler).

### Kullanıcı kararı — geriye dönük uyumluluk aranmıyor

Bugüne kadar toplanan veri test amaçlıydı; **yeni arayüzde görünmesi
gerekmiyor**. Mevcut veri **silinmeyecek**, ileride test için duracak. Bu karar
göç kodunu, çift okuma yolunu ve `segments.json` dönüştürücüsünü kapsam dışına
çıkardı.

### Kalıcı mimari kararlar

1. **Yeni arayüz ayrı pakettir: `kinecapture/studio/`.** Eski `gui/` silinmedi,
   bozulmadı ve `python -m kinecapture --legacy-gui` ile açılıyor — raw-first
   politikasından önceki kayıtları açabilen tek arayüz odur. Varsayılan
   `python -m kinecapture` artık Studio'yu açar.
2. **Üç katman, fiziksel sınır.** `studio/services/` ve `studio/viewmodels/`
   (ve `studio/theme/`) Qt import etmez. `tests/test_studio_layers.py` bunu iki
   şekilde denetler: PySide6 import'unun `AssertionError` fırlattığı bir alt
   süreçte paketleri gerçekten kullanır, ayrıca AST ile import taraması yapar
   (grep değil — bu dosyaların docstring'leri kuralın kendisinden bahsediyor).
3. **ViewModel → View iletişimi saf Python.** `Observable` (yalnız gerçek
   değişimde bildirir), `Event` (değer tutmaz; geç abone eski hatayı almaz),
   `Subscriptions`. Qt sinyaline çevirme yalnız `views/qt_bridge.py` içinde.
4. **`tokens.json` tek gerçek kaynak.** Renk/ölçü/tipografi oradan;
   `studio.qss.tmpl` yalnız `@Token@` yer tutucuları içerir; üretici çözülmemiş
   token bırakırsa hata verir. Widget'ta literal renk yasak ve testle sabit.
   Token adları WinUI kaynak adı gibi (`KcSurfaceBase`, `KcStatusRecording`).
   Renk anlam taşır: kırmızı kayıt/hata, sarı uyarı, yeşil canlı/tamam, mavi
   seçim.
5. **QSS'te evrensel `QWidget` kuralı arka plan boyamaz.** Yalnız `QMainWindow`
   ve adlandırılmış yüzeyler boyar; aksi hâlde her düz konteyner kendi
   dikdörtgenini ebeveyninin üstüne damgalıyor ve panel içinde hayalet kutular
   çıkıyordu (gerçekten görüldü ve düzeltildi).
6. **İkon seti: Lucide 0.462.0, ISC.** 25 SVG + lisans metni paket verisi.
   `currentColor` çalışma anında token rengiyle değiştiriliyor (Qt SVG'de
   cascade yok), device pixel ratio'da render ediliyor. Ürün sözlüğü
   (`record`, `cpu`) ile dosya adı arasında bir eşleme tablosu var; set
   değiştirilirse yalnız o tablo değişir.
7. **Pencere durumu `core/jsonio` ile atomik yazılıyor** (`QSettings` değil);
   bozuk/okunamayan dosya varsayılana düşer ve açılışı engellemez.
8. **İki katmanlı hata dili veri olarak modellendi** (`services/messages.py`):
   görünen `headline`/`detail`, "Ayrıntılar" altında `code` + `technical`.
   `sys.excepthook` yakalanmamış istisnayı bu mesaja çevirir; arayüz ayakta
   kalır.

### Ölçülenler (gerçekten çalıştırıldı)

- Soğuk açılış, gerçek süreç, `windows` platformu, üç koşu: **1,29 / 1,34 /
  1,29 s** (hedef ≤3 s).
- Kabuk kurulumu + `show()` süreç içinde 806 ms.
- 1120×700, 1366×768, 1600×980 × koyu/açık: `minimumSizeHint` hepsinde sığıyor,
  kırpılma yok.
- Sayfalar tembel kuruluyor: açılışta 1 sayfa.
- Qt-bağımsızlık alt süreç testi geçiyor.

### Önemli ortam gerçeği — `offscreen` platformunda font yok

`QFontDatabase.families()` **offscreen** Qt platformunda **boş liste** döndürür.
Bütün metin tofu kutusu olarak çizilir ve gerçek metinden geniş ölçülür: aynı
kabuk offscreen'de 1514 px minimum genişlik iddia ederken `windows`
platformunda 1120'ye sığıyor. **Yerleşim/genişlik ölçümleri offscreen'de
yapılamaz.** Studio yerleşim testleri bu yüzden offscreen'de atlanıyor ve
`QT_QPA_PLATFORM=windows` ile çalıştırılıyor. Bu, eski turlardaki offscreen
ölçümlerinin de yeniden değerlendirilmesini gerektirebilir.

### Onarılan gerçek hata

`tests/test_raw_capture_fields.py` içindeki beş kırmızı test: yardımcı `sl`
yerine düz `object()` veriyordu, 6V'de eklenen `_check_retrieval` ise
`sl.ERROR_CODE.SUCCESS` okuyor. Stub gerçek SDK sözleşmesini taklit edecek
biçimde düzeltildi ve başarısız retrieval'ın `CameraError` fırlattığını sabitleyen
yeni bir test eklendi. Uygulama kodu değişmedi.

### Sürümler

Hiçbir veri şeması değişmedi. `studio.STUDIO_VERSION = 0.1.0` eklendi (arayüz
sürümü, veri sözleşmesi değil). app/package 0.11.0 ve diğer bütün şema
sürümleri 6V'deki gibi.

## 6AA. Studio F3 — backend toplamsal ekleri, processing 1.1.0 (2026-09-13)

Plan: `FAZ_PLANI_PYSIDE6_STUDIO.md`. F1'de ölçülen darboğazların **veri
tarafı** bu fazda kapatıldı; çizim tarafı F8'de.

### Kalıcı kararlar

1. **`PROCESSING_SCHEMA_VERSION` 1.0.0 → 1.1.0.** Bir sürüm artık şunları da
   taşır: `arrays/*.npy` + `arrays/index.json`, `summary/` piramidi,
   `thumbs/`. `job.json` `paused`, `paused_s`, `rate_fps`, `eta_s` kazandı.
2. **`arrays.npz` yeni sürümlerde yazılmıyor.** Sıkıştırılmış arşiv üyesi
   bellek eşlenemez; asıl mesele buydu. Yerine dizi başına sıkıştırılmamış
   `.npy`. **Eski sürümler okunmaya devam ediyor**: `ArrayStore` 1.0.0
   yerleşimine düşer ve `is_memmapped=False` diyerek pencere okumasının ucuz
   **olmadığını** söyler — çağıran tahmin etmez. Testle sabitlendi.
3. **Timeline özeti min/max piramididir**, ses editöründeki dalga formu gibi.
   Ortalama değil: bir saniyelik iyi veri içindeki tek kötü kare ortalamada
   kaybolurdu — oysa annotatörün aradığı tam olarak o karedir. Kapsam için
   `any`/`all`, QC bayrakları için bitwise-or. Ölçülmemiş bin NaN kalır;
   0.0 ile karıştırılmaz.
4. **Thumbnail'ler seek ile alınır, sırayla okunarak değil.** İlk sezgi
   yanlıştı ve ölçüldü: 302 karelik proxy'de sıralı 305 ms, seek 131 ms — ve
   seek maliyeti kayıt uzunluğundan bağımsız. Codec seyrek keyframe'liyse
   birkaç kare kayabilir; indeks **istenen** değil **inilen** konumu yazar.
5. **`DepthReader` chunk başlıklarını bir kez okuyup indeks kurar** ve son
   çözülen chunk'ı tutar. Bunun için `rgbd_archive.read_chunk_header` eklendi
   (toplamsal). Offline derinlik her yerde `reconstructed_offline`
   provenance'ı taşır; kayıt anındaki ölçüm değildir.
6. **Proje indeksi türetilmiştir, otorite değildir.** `cache/take_index.json`
   silinebilir/bozulabilir; sonraki yenilemede `take.json` ve `job.json`
   dosyalarından yeniden üretilir. **Yapısal değişikliği** algılar (kayıt veya
   sürüm eklendi/kalktı), çalışan bir işin ilerlemesini değil — onu isteyen
   ekran `job.json`'u doğrudan okur.
7. **Duraklatma iptal değildir.** Yeni canlı kayıt GPU'yu geri isterse iş kare
   sınırında durur, bütün akışlar açık kalır, kaldığı yerden devam eder.
   Duraklama süresi `paused_s` olarak ayrı tutulur ve hız penceresi sıfırlanır;
   beklenen süre boşta geçen zamanla kirletilmez. İptal duraklamayı yener.
8. **Yüzde uydurulmaz.** Kaynak kare sayısı bildirilmemişse `eta_s` ve oran
   `None` kalır; ilk `_RATE_WARMUP_FRAMES = 20` kare model ısınmasına gittiği
   için orana dahil edilmez.

### Ölçülenler (60 dk / 60 FPS / BODY_38 sentetik, gerçek kod yolları)

| Ölçüm | 1.0.0 | 1.1.0 |
|---|---|---|
| Dizi yazımı (135 MB ham) | 5,05 s → 122,1 MB | **0,13 s** → 135,0 MB |
| 600 karelik pencere okuma | 403,7 ms | **13,5 ms** (soğuk, store açılışı dahil) |
| 100 ardışık pencere | — | **14,5 ms** toplam (0,14 ms/pencere) |
| Timeline özeti üretimi | yok | 0,06 s · 4,8 MB · 11 seviye |
| Lane okuma (60 dk tam görünüm, 1600 px) | yok | ilk 7,9 ms, sonraki **0,007 ms** · 1688 bin |
| Thumbnail (302 kare, 13 adet) | yok | **131 ms** · 7,4 kB |
| `depth.at` rastgele / 40 ardışık | O(chunk) her kare | 24,6 ms / 110,7 ms (2,8 ms/kare) |
| `position_of_anchor` ×1000 | doğrusal tarama | **0,7 ms** |

Proje indeksi (1000 kayıt, aynı koşuda karşılaştırıldı):

| | süre |
|---|---|
| Eski desen (`rglob("*.json")` + stat, **her** yenileme) | 1247 ms |
| Yeni: ilk kurulum (hepsi okunur) | 3932 ms |
| Yeni: önbellekli yenileme (0 yeniden okuma) | **154 ms** |
| 100 kayıtta eski / yeni önbellekli | 126,7 ms / **15,8 ms** |

**Dürüstlük notu:** 154 ms bir UI karesi değildir. İndeks GUI thread'inde
çalıştırılmaz; F4/F7 onu worker thread'e alır. İndeksin kazandırdığı şey işin
*sık* çalıştırılabilecek kadar küçülmesidir, sıfırlanması değil. Ayrıca F1'de
aynı eski desen 650 ms ölçülmüştü; bu turda 1247 ms çıktı — makine/disk önbellek
değişkenliği. Karşılaştırma yalnız aynı koşu içinde geçerlidir.

Windows'ta tek bir `os.stat` yaklaşık **65 µs** sürüyor (Defender dahil); bu
yüzden tarama `Path.glob` yerine `os.scandir` ile yapılıyor — `DirEntry` dizin
listesinin zaten ürettiği stat'ı taşır, glob ise her girdiyi ikinci kez stat'lar.

### Uzun yol tuzağı — `long_path` her yol için ayrı karar verir

F3 testlerini yazarken gerçek bir tuzağa düşüldü ve kalıcı olarak not edilmeli:
`core.paths.long_path` yalnız **kendisine verilen yol** 227 karakteri
(`MAX_PATH 259 − margin 32`) aşarsa `\?\` önekini ekler. Bu yüzden
`derived/processing` dizini eşiğin **altında** kalıp önek almazken, iki seviye
içindeki `job.json` sınırı aşabilir. Sonuç: kısa ebeveynden yapılan
`Path(...).glob(".*.partial/job.json")` **hiçbir şey döndürmez ve hata da
vermez** — arama zaman aşımı gibi görünür.

Kural: derin bir dosyaya erişirken yol **kademeli kurulur** ve `long_path`
yaprakta uygulanır (`read_json(base / name / "job.json")` gibi); kısa bir
ebeveynden özyinelemeli glob edilmez. Uygulama kodu zaten böyle çalışıyor;
hata yalnız test tarafındaydı. Ayrıca pytest'in geçici dizin adı test adını
içerdiği için uzun test adları bu sınırı kolayca aşıyor.

İlgili ikinci gözlem: OpenCV `\?\` önekini kabul etmediği için uzun yolda
proxy video yazılamıyor ve `process_take` bunu `review_proxy_incomplete` ile
işaretleyip sürümü `partial` bırakıyor. Bu **mevcut** bir sözleşme kararıdır
(F3'te değiştirilmedi); ilgili test bu durumu açıkça skip ediyor. Kolaylık
amaçlı bir ürünün (proxy) bilimsel sonucu kullanılamaz yapması ileride ayrıca
tartışılmalı.

### Çalıştırılanlar

- `tests/test_processing_artifacts.py` **23 passed** (yeni).
- `tests/test_summary_index.py` **17 passed** (yeni).
- `tests/test_processing_pipeline.py` **18 passed** (6 yeni: 1.1.0 ürünleri,
  duraklat/devam, duraklamışken iptal, ilerleme alanları, 1.0.0 uyumluluğu).
- `tests/test_environment.py` **11 passed** (yeni: offline katman Qt/SDK'sız
  import ediliyor).
- Gerçek mock take üzerinde uçtan uca: `python -m kinecapture.processing` →
  complete, 302 kare, 13 önizleme, 2 özet seviyesi, 4,9 s.
- Aynı take'in **1.0.0 ile üretilmiş** sürümü yeni `ReviewDataset` ile açıldı:
  diziler, derinlik ve anchor round-trip çalışıyor; özet/thumbnail yok diye
  raporlanıyor.

## 6AB. Studio F4–F7 — ekranlar, ayrı süreç, kütüphane (2026-09-13)

Kullanıcı F4'ten F7'ye kadar onay beklemeden devam edilmesini istedi. Plan ve
ölçüm tabloları `FAZ_PLANI_PYSIDE6_STUDIO.md` bölüm 7'de; burada yalnız kalıcı
kararlar ve ölçümle bulunan gerçekler.

### Kalıcı mimari kararlar

1. **`TaskRunner` arayüzü** (`studio/viewmodels/tasks.py`): viewmodel yavaş işi
   bir arayüze veriyor, Qt'yi görmüyor. `QtTaskRunner` `QThreadPool` kullanıyor
   ve sonucu **kuyruklu sinyalle GUI thread'ine** taşıyor. Testler
   `InlineRunner` ile senkron çalışıyor; viewmodel davranışı işin ertelenip
   ertelenmediğine bağlı olamaz.
2. **Tek tablo modeli** (`studio/views/models.py`): `QAbstractTableModel` +
   arama proxy'si. Sütun, satır nesnesinden metne bir fonksiyondur; model
   take/katılımcı/proje bilmez.
3. **İşleme alt süreçte.** `python -m kinecapture.processing` import edilmiyor,
   `subprocess` ile başlatılıyor. Gerekçe sırayla: SDK orada açılıyor, hiçbir
   davranışı çizimi bloklayamaz, işletim sistemi onu duraklatıp
   sonlandırabilir. İlerleme **`job.json`'dan** okunuyor; ikinci bir kopya yok.
4. **Kütüphane satırı hiçbir şey açmıyor.** Sürüm açmak checksum doğrulaması
   demek; satırlar yalnız türetilmiş indeksten ve `job.json`'dan kuruluyor.
   Önizlemeler F3'te üretildi, ekran yalnız dosya okuyor.
5. **Giriş kapısı**: çalışma alanı kapının arkasında, giriş yapılmadan hiçbir
   sayfa kurulmuyor. Parola hiçbir yerde saklanmıyor, kullanıldığı anda
   alandan siliniyor.
6. **Ayarlar all-or-nothing**: bir alan geçersizse hiçbiri yazılmıyor, eski
   değer yürürlükte kalıyor, sorun kendi alanının altında söyleniyor.
7. **Kişi seçimi gösterilen kareye bağlanıyor**; iki kişi örtüşüyorsa seçim
   yapılmıyor. Yanlış kişi, tekrar sormaktan kötüdür.

### Ölçümle bulunan gerçekler

- **Python tablo modeli çizimde C++ `QTableWidget`'tan pahalı**: 1000 satırda
  tam viewport çizimi 21 ms / 15 ms. Karşılığında doldurma satır sayısından
  **bağımsız** (1000 ve 5000 satırda ~45 ms; eski desen 36 / 183 ms) ve hücre
  başına nesne üretilmiyor. Bu bir takas, kazanç değil.
- **`view.setSortingEnabled(True)` proxy'yi her veri sıfırlamasında yeniden
  sıralatıyor** ve sıralama her karşılaştırmada `data()` ile Python'a giriyor:
  1000 satır doldurma **224 ms**. Sıralama modelin içine alınınca
  (önbelleklenmiş anahtarlar üzerinde tek `list.sort`) **42 ms**. Aynı sebeple
  arama da satır başına birleştirilmiş metin önbelleğine alındı (5000 satırda
  308 → 74 ms).
- **PySide6 6.10'da `invalidateFilter` ve `invalidateRowsFilter` deprecated**;
  `invalidate()` kullanılmalı. Proje kendi DeprecationWarning'lerini hata
  sayıyor.
- **Mock backend varsayılan olarak hız sınırlaması yapmıyor** (`real_time`
  parametresi var ve Studio onu vermiyordu). Kaynak istenen 60 FPS yerine
  ~350 FPS üretip 120 karelik yazıcı kuyruğunu taşırıyor, 45–96 kare kaybına
  yol açıyordu. Take doğru biçimde `partial` kalıyordu — sistem doğru
  davranıyordu, ölçüm ortamı yanlıştı. `real_time=True` ile kayıp **sıfır**.
  Ders: GUI'nin kayıt hattına etkisi ancak **A/B** ile söylenebilir; tek
  ölçümle "GUI kayıp yaratıyor" denemez.
- **`psutil` 7.1.3 ortamda mevcut** ve iş duraklatma onu kullanıyor (Windows'ta
  `SIGSTOP` yok). Bağımlılık olarak eklenmedi; yoksa arayüz duraklatmanın
  desteklenmediğini söyleyip iptali öneriyor.
- **Ayarlarda `backend` düz metin saklanırsa** tercih dosyası yazılırken
  `'str' object has no attribute 'value'` ile sessizce başarısız oluyor. Tip
  dönüşümü zorunlu.

### Ölçülen bütçeler

| Ölçüm | Sonuç | Bütçe |
|---|---|---|
| Soğuk açılış (gerçek süreç) | 1,29–1,34 s | ≤3 s ✓ |
| GUI kare süresi, canlı kayıt sırasında | medyan 0,09 ms · p95 3,7 ms | ≤8 ms ✓ |
| GUI kare süresi, offline işleme sürerken | medyan 2,88 ms · p95 7,7 ms | ≤8 ms ✓ |
| Kayıt kaybı (mock, GUI açık/kapalı, 60 ve 200 FPS) | **0** | kayıp yok ✓ |
| Liste doldurma, 1000 / 5000 satır | 43 / 48 ms | takılma yok ✓ |
| Kütüphane kaydırma, 500 sürüm | medyan 20,6 ms | — |
| Kaydırırken thumbnail üretimi | **0 çağrı** | üretim yok ✓ |

Zaman çizelgesi bütçesi (≤16 ms) **F8'e aittir ve henüz ölçülmemiştir.**

### Sürümler

Hiçbir veri şeması değişmedi. `studio.STUDIO_VERSION` 0.1.0; app 0.11.0,
processing 1.1.0 (F3), diğerleri 6V'deki gibi.

## 7. Mimari sınırlar

```text
gui/            PySide6; kameraya ve diske dokunmaz
gui/state.py    authenticated AppState; user/proje/katılımcı/auto-session
identity/       SQLite schema + repository + scrypt + auth/access service
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
| Test paketi | `.\scripts\run_tests.ps1` | **561 passed**, 178.46 s (2026-08-26) |
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
- Üç doğrulanmış legacy test projesi runtime silme politikası nedeniyle diskte
  kaldı (kesin yollar bölüm 6E'de). Identity DB'ye otomatik kaydedilmezler;
  owner içe aktarmadıkça GUI'de görünmezler.
- Mevcut kullanıcı tercihindeki `dataset_root`, önceki donanım testinin geçici
  `shots4_iu_kvaue` klasörünü gösteriyor. Bu görev tercih dosyasını silmedi;
  owner Projeler → Veri klasörü ile kalıcı hedefi seçmelidir.
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

## 6AC. Studio F8 — Etiketleme, kanonik sidecar 1.1.0 (2026-09-14)

Etiketleme ekranı ve altındaki kanonik etiket katmanı. Bu fazın kuralı:
**yanlış etiket, eksik etiketten kötüdür** — eksik olan dışa aktarımı durdurur,
yanlış olan modeli sessizce zehirler. Aşağıdaki kararların çoğu bu yüzden
"reddet" yönünde.

### Kanonik şema 1.1.0 (`processing/annotations.py`)

Bir etiketin zamanı `Anchor(source_fingerprint, source_position,
camera_timestamp_ns)`. Çözüm **tam eşleşme veya ret**; en yakın kareye kaydırma
yok. Sınırlar kapsayıcı (`4..9` dokuzuncu kareyi içerir). `Correctness`
türetilir: incelenmemiş → `unreviewed`, sınıflı hata var → `incorrect`, yok →
`correct`. `Readiness` neyin eksik olduğunu söyler; **sınıfsız bir hata aralığı
bütün hareketi bloklar** (aralığı atmak, tekrarı "hatasız" diye etiketlemek
olurdu).

### Tek yazıcı (`studio/services/annotation_store.py`)

Bir kullanıcı kararı = bir geri alma adımı. Doğrulama **bütün belge** üzerinde
çalışır ve düzenleme bütün olarak reddedilir; reddedilen düzenleme geri alma
yığınından da düşer, yani hiçbir iz bırakmaz. `label_movement` sınıf +
`reviewed_at` damgasını tek adımda yazar; `label_error` sınıf + eklem + durum +
notu tek adımda yazar (ayrı yazılsa bir aralık yeni sınıfla eski eklemleri
taşıyabilirdi — tamamlanmış görünen yanlış etiket).

### GUI yazarken ortaya çıkan backend açıkları (hepsi kapatıldı)

1. **`FeatureContext.raw` işleme tarafında hiç doldurulmuyordu.** Bütün
   ham tracker alanları (2B eklemler, oryantasyonlar, kovaryanslar, kök) offline
   bir koşuda **her zaman NaN** çıkıyordu; özellik kendini "üretilemedi" diye
   raporluyordu, oysa veri paketin içindeydi. `jobs.py` artık seçili bedenlerden
   istifliyor. `tracker_joint_positions_2d` varsayılan özellik setine alındı:
   etiketleme ekranı iskeleti videonun üstüne çiziyor ve pikselleri 3B'den geri
   üretmek mümkün değil.
2. **Kaynak haritası 222 MB tutuyordu.** 216000 satır dict + tuple anahtarlı
   indeks. İki `int64` diziye indirildi; pozisyonlar kesin artansa ikili arama,
   değilse sözlüğe düşülüyor. Açılış maliyeti 222 MB → **4,8 MB**.
3. **Tekrarlanan kare kimliği sessizce çözülüyordu.** Bozuk bir kaynakta aynı
   `(pozisyon, zaman)` iki kez geçebilir; dict'te son satır kazanıyordu. Artık
   belirsizlik tespit edilip çözüm reddediliyor.
4. **Hata aralığı sessizce kırpılıyordu.** Hareketin tamamen dışına çizilen
   aralık sınır karesine sıfır uzunlukta yapıştırılıyordu — kullanıcının
   yapmadığı, göremediği bir etiket. Örtüşen kırpılır, örtüşmeyen reddedilir.
5. **`joint_status` sessizce yükseltiliyordu.** Eklem işaretlenince durum
   kendiliğinden `selected` oluyordu; bu, yapılmamış bir insan incelemesini
   kayda geçirmek demek. Çelişkili bileşim reddediliyor.
6. **Kütüphane var olmayan sürüm listeliyordu.** `process_take` önce
   `state: complete` yazıyor, sonra checksum'ları yazıp klasörü
   `.run_x.partial` → `run_x` olarak adlandırıyor. Arada okuyan herkes "hazır"
   diyen ama açılamayan bir sürüm görüyordu. Artık **"tamamlandı" = terfi
   etmiş**: `ProcessingRunSummary.is_complete` terfiyi de şart koşuyor, satır
   gerçek klasör adını taşıyor, işleme ekranı terfiye kadar "çalışıyor"
   gösteriyor.
7. **`ReviewDataset` açılışta bütün `skeleton.jsonl`'i ayrıştırıyordu.**
   Tembelleştirildi; etiketleme ekranı ona hiç dokunmuyor (dizilerden pencere
   okuyor).

### Zaman çizelgesi (`studio/views/timeline.py`)

Şeritler per-bin `fillRect` yerine numpy ile `uint8 [h,w,4]` kurulup tek
`drawImage` ile basılıyor. 600 aralıkla tam görünüm **12,13 ms** (F1 tabanı
292–323 ms). Statik katmanlar `QPixmap`'te önbellekli; oynatma çizgisi ve
sürükleme üstte çiziliyor → çizgi hareketi **0,11 ms**.

### Ölçümler (60 dk / 60 FPS / BODY_38)

Boşta kare 0,38 ms (bütçe 8) · tarama 0,64 ms (bütçe 50) · 600 karelik 3B
pencere 0,12 ms · **zirve RSS 139 MB** (bütçe 1,5 GB). Diziler memmap,
iskelet akışı hiç yüklenmiyor.

### Test ortamı tuzakları (yine)

- `pytest` geçici kökü altında take yolu yeterince uzun olunca **OpenCV proxy
  videoyu açamıyor** → koşu dürüstçe `partial` oluyor. `test_studio_processing`
  artık "tek şikâyeti proxy olan partial" durumunu bitmiş sayıyor ve nedeni
  yazıyor. Ekran görüntüsü/uçtan uca betikleri kısa bir kökte (`C:\kc8`)
  çalıştırıldı; orada koşu `complete` ve video gerçekten var.
- `test_processing_pipeline` içinde dört `assert`'te düz `Path.exists()`
  kullanılıyordu; uzun yolda sessizce `False` döndüğü için **olumsuz
  iddialar boşuna geçiyordu**. Hepsi `path_exists()`e çevrildi.
- Kişi çapası (`subject_anchors.json`) yoksa işleme hiçbir bedeni seçmez ve
  **bütün diziler NaN kalır**; ekran doğru şekilde "iskelet yok" der. Testlerin
  gerçek sayılara dokunması için çapa yazılmalı. Yakalama ekranının tıkla-seç
  akışı F10'da bağlanacak.

### Ekran

Video editörü düzeni; canlı kırpma önizlemesi (kenar sürüklenirken görüntü o
kareye gider, oynatma çizgisi yerinde kalır); 1–9 sayı tuşlarıyla sınıf atama;
"Sınıfsızların hepsine uygula" (sınıfı olanı değiştirmez); "Sonraki eksik".
Seçili hata aralığının eklemleri görüntüde kırmızı; düşük güvenli eklem içi
boş; **tracker'ın üretmediği eklem çizilmez**. Denetçi kaydırma alanında —
ekranın istediği en küçük pencere 880×923 → **880×672** (1366×768 sığıyor).
