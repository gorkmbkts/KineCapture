# Claude Code Görevi — Sürekli Aktivite Dataseti, Zorunlu RGB-D Arşivi ve Kalıcı Kişi Kilidi

> **Bu görevin izi:** [6D uygulama kaydı](../knowledge/archive/memory/6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · [RGB-D ve depth](../knowledge/concepts/rgbd-and-depth.md) · [Kişi seçimi ve subject lock](../knowledge/concepts/subject-selection.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


KineCapture repository'sinde uçtan uca üç bağlantılı yetenek uygula:

1. Mevcut hareket-tekrarı dataset üretimini bozmadan, gelecekte kameranın
   karşısındaki kişinin **istediği anda egzersize başladığını ve bitirdiğini**
   algılayacak modeller için isteğe bağlı sürekli-aktivite etiketleme ve export
   altyapısı kur.
2. Her gerçek kaydın RGB görüntüsünü ve derinlik bilgisini, gelecekte farklı
   datasetler üretmek üzere yeniden işlenebilecek **değişmez ve doğrulanabilir
   ham kaynak** olarak zorunlu biçimde sakla.
3. Capture ekranında kullanıcıya, kayda başlamadan önce canlı görüntüde kişinin
   üzerine tıklayarak kaydedilecek kişiyi seçme imkânı ver. Başka insanlar
   kadraja girse, seçilen kişi geçici olarak kaybolsa veya tracker kimliği
   değişse bile başka bir kişinin iskeletine sessizce geçme.

Bu görevi yalnız analiz veya plan olarak bırakma. Mevcut mimariye uygun
implementasyonu tamamla, testleri çalıştır, dokümantasyonu ve `MEMORY.md`
dosyasını güncelle. Kullanıcı verisini, eski take'leri veya yayımlanmış
release'leri yeniden yazma.

## 1. Başlangıç ve çalışma kuralları

1. Önce repository kökündeki `CLAUDE.md` ve `MEMORY.md` dosyalarının tamamını
   oku.
2. Ardından en az şu dosyaları ve ilgili testleri incele:
   - `src/kinecapture/domain/models.py`
   - `src/kinecapture/domain/project.py`
   - `src/kinecapture/camera/base.py`
   - `src/kinecapture/camera/zed.py`
   - `src/kinecapture/camera/mock.py`
   - `src/kinecapture/capture/service.py`
   - `src/kinecapture/recording/take_writer.py`
   - `src/kinecapture/playback/take_reader.py`
   - `src/kinecapture/dataset/workspace.py`
   - `src/kinecapture/annotations/repository.py`
   - `src/kinecapture/export/release.py`
   - `src/kinecapture/gui/pages/capture.py`
   - `src/kinecapture/gui/pages/review.py`
   - `src/kinecapture/gui/pages/export.py`
   - `src/kinecapture/gui/pages/settings.py`
   - `src/kinecapture/gui/widgets/video_view.py`
   - `src/kinecapture/gui/widgets/timeline.py`
3. Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
   oluşturma ve gereksiz bağımlılık kurma.
4. Çalışma ağacı kirliyse kullanıcı değişikliklerini koru.
5. Kod ve veri alanları İngilizce, kullanıcıya görünen GUI metinleri Türkçe
   olsun.
6. `pyzed` yine yalnız `camera/zed.py` içinde ve gecikmeli import edilsin.
7. GUI thread'ini kamera, RGB-D sıkıştırma, disk yazımı veya kimlik eşleştirme
   hesabıyla bloklama.
8. Ham kayıt değişmezliği, atomik metadata yazımı, yarım kayıt kurtarma,
   sentetik veri işareti, Windows uzun yol desteği ve preview-loss / capture-loss
   ayrımı korunmalı.
9. KineSynthV3 bu görevde değiştirilmesin. Yalnız gelecekteki model
   sözleşmesini anlamak için referans olarak incelenebilir.

## 2. Liste üst sınır değildir — bağımsız inceleme zorunluluğu

Bu prompt minimum gereksinimleri tarif eder; eksiksiz bir teknik tasarım
değildir. Repository'yi, yerel ZED SDK 5.4 sözleşmesini ve mümkünse resmi
Stereolabs belgelerini inceleyerek daha güvenli, yeniden üretilebilir veya ML
açısından daha değerli alanlar/olaylar/testler bulunuyorsa kapsam içinde kendin
ekle.

Özellikle şu konularda varsayım yapma; kod ve SDK üzerinden doğrula:

- SVO2 tam olarak hangi görüntüleri saklıyor, hangi veriler sonradan yeniden
  hesaplanıyor ve kullanılan H264 sıkıştırmasının gerçek niteliği nedir?
- Canlı SVO kaydı ile `FramePacket.frame_index`, kamera timestamp'i ve yeniden
  oynatmadaki SVO pozisyonu nasıl güvenilir biçimde eşlenebilir?
- ZED `BodyData.id`, varsa `unique_object_id` veya ilgili re-identification
  özellikleri hangi süre ve koşullarda kararlıdır?
- Seçilen kişi kadrajdan çıkıp tekrar girdiğinde SDK aynı ID'yi garanti ediyor
  mu? Etmiyorsa hangi kanıtlarla yeniden ilişkilendirme yapılabilir?
- `store_depth_frames` mevcut kodda gerçekten veri yazıyor mu, yoksa yalnız
  ayar/GUI alanı mı?

Yeni bulduğun her önemli eklemeyi son raporda şu şekilde açıkla:

1. Neyi ekledin?
2. Hangi veri kaybını veya model ihtiyacını çözüyor?
3. Hangi varsayımı doğruladın?
4. Hangi durumda hâlâ garanti verilemiyor?

Yüz tanıma, kalıcı biyometrik kimlik veritabanı, bulut servisi veya yeni büyük
bir ML modeli bu görev için sessizce eklenmemeli. Kişi eşleştirmesi take içinde
ve seçilen katılımcıyı takip etmek amacıyla sınırlı kalsın. Güvenli bir sonuç
çıkarılamıyorsa sistem belirsizliği göstermeli; yanlış kişiyi seçmek için tahmin
yürütmemeli.

## 3. Mevcut durumu önce doğrula

Kod incelemesinde görünen şu noktaları gerçek implementasyondan doğrula ve
gerekirse düzelt:

- `raw/capture.svo2` bugün ZED'in native kaydı olarak yazılıyor ve gelecekte
  RGB/derinlik üretiminin ana kaynağı olarak belgeleniyor.
- Native kayıt yalnız `store_native_recording=True` ve backend destekliyorsa
  başlıyor; ayar kapalıysa take ham kaynak olmadan devam edebiliyor.
- `CaptureProfile.store_depth_frames` ve Ayarlar ekranındaki “Derinlik
  karelerini ayrıca sakla” kontrolü bulunuyor; fakat `TakeWriter.write_frame`
  içinde derinlik stream'i yazılmıyor gibi görünüyor. Çalışmayan bir kontrolü
  arayüzde bırakma.
- `derived/proxy.mp4` küçültülmüş ve kayıplı bir inceleme kopyasıdır; ham RGB
  kaynağı gibi kabul edilemez.
- `skeleton.jsonl` şu anda karedeki bütün gövdeleri ve varsa `active_id`
  değerini saklıyor.
- Capture ekranında ID dropdown'u var, fakat canlı görüntü üzerinde kişinin
  üzerine tıklayarak seçim yok.
- `FramePacket.primary_body(preferred_id)` seçilen ID bulunamazsa başka bir
  gövdeye düşüyor. Bu davranış genel önizleme için kullanışlı olabilir fakat
  **kilitli katılımcı kaydı ve exportu için kabul edilemez**.
- Mevcut export her etiketli `MovementSample`ı ayrı örnek yapıyor; hareketlerin
  dışındaki bekleme, geçiş ve normal hareket kareleri model datasına girmiyor.

Bu maddelerden biri artık doğru değilse gerçek durumu raporla ve aynı ürün
hedefini sağlayan çözümü uygula.

## 4. Geriye uyumluluk ve ürün modları

Mevcut iş akışı aynen kullanılabilmeli:

- Kullanıcı kısa take kaydeder.
- İnceleme ekranında hareket sample'ları oluşturur.
- Hareket türü, correct/incorrect ve hata aralıklarını etiketler.
- Mevcut movement-sample release formatını üretir.

Yeni özellikler isteğe bağlı bir çalışma biçimi eklemeli; eski davranışı
silmemeli. Uygun isimleri kod mimarisine göre seçebilirsin, ancak ürün düzeyinde
en az şu iki amaç ayrılmalı:

1. **Hareket tekrarları — mevcut yöntem:** Etiketli hareket sample'ları ayrı
   dataset örnekleridir.
2. **Sürekli aktivite oturumu — yeni yöntem:** Take'in tamamı korunur; spor
   dışı zamanlar, geçişler, egzersiz başlangıçları ve bitişleri zaman üzerinde
   etiketlenebilir.

Export ekranında kullanıcı şunlardan birini seçebilmeli:

- Yalnız mevcut hareket-sample dataseti
- Yalnız sürekli-aktivite dataseti
- Her ikisi, birbirinden açıkça ayrılmış sözleşmelerle

Varsayılan seçim eski release davranışını korusun. Eski take ve annotation
dosyaları migration veya otomatik rewrite olmadan açılabilsin. Yeni alanı
olmayan eski kayıtlarda gerçek eksiklik açıkça raporlansın.

## 5. Zorunlu, değişmez ve yeniden işlenebilir RGB-D ham arşivi

### 5.1 Değişmez ürün garantisi

Yeni gerçek kamera kayıtlarında aşağıdaki garanti sağlanmadan take
`FINALIZED`/başarılı sayılmamalı:

- Kayıt süresindeki RGB görüntüleri gelecekte yeniden okunabilir.
- Kayıt süresindeki metrik derinlik bilgisi gelecekte yeniden okunabilir veya
  kayıt anındaki ham stereo veriden belgelenmiş ayarlarla yeniden üretilebilir.
- RGB, derinlik, iskelet ve annotation zamanları birbirine eşlenebilir.
- Ham kaynağın dosyası, biçimi, codec/sıkıştırması, SDK sürümü, kamera seri
  numarası, çözünürlük, FPS, depth mode, coordinate system, length unit,
  calibration/intrinsics ve checksum bilgileri kayıtta bulunur.
- Ham veri annotation veya export sırasında değiştirilmez.

Bu garanti Ayarlar ekranında kullanıcı tarafından yanlışlıkla kapatılamasın.
`store_native_recording` gibi bir seçenek gerçek ZED kaydında ham arşivi
devre dışı bırakabiliyorsa kaldır, kilitli/zorunlu göster veya yalnız açık bir
test-geliştirme profiline sınırla. Kullanıcıya “Ham RGB-D arşivi: zorunlu”
durumunu ve tahmini disk kullanımını göster.

### 5.2 SVO2 ve ayrı RGB-D stream kararı

ZED için `capture.svo2` mümkünse otoritatif ham sensör arşivi olarak korunsun.
Fakat şu ayrımları dürüstçe yap:

- SVO2 içinde fiziksel olarak saklanan stereo/görüntü verisi ile yeniden
  oynatma sırasında SDK'nın tekrar hesapladığı depth map aynı şey değildir.
- H264 kullanılıyorsa dokümantasyonda “lossless” denmemeli; gerçek compression
  mode açıkça yazılmalı.
- Gelecekte başka depth mode veya SDK sürümüyle yeniden hesaplama yapılmasının
  kayıt anındaki `depth_frame` ile bit düzeyinde aynı sonucu garanti edip
  etmediği varsayılmamalı.

Kullanıcının depth verisinin de saklanması yönündeki talebini gerçekten karşıla:

- Kayıt sırasında kullanılan `FramePacket.depth_frame` akışını NaN/non-finite
  semantiğini, çözünürlüğünü, float dtype'ını, metre birimini ve kamera
  timestamp'ini koruyacak şekilde kalıcılaştır.
- Full-resolution depth için append-safe veya küçük/chunk'lı, yarım kayıtta
  kurtarılabilir ve checksum alınabilir bir düzen kur. Tek dev `.npz`yi kayıt
  bitene kadar RAM'de biriktirme.
- Format/sıkıştırma seçimini ölçerek yap. Yeni bağımlılık kurmadan mevcut
  NumPy/OpenCV/standart kütüphaneyle güvenli çözüm bulunabiliyorsa onu tercih
  et. Quantization uygulanacaksa sessizce float veriyi 8-bit görüntüye çevirme;
  ölçek, invalid mask ve hassasiyet sözleşmede bulunmalı. Varsayılan olarak
  ölçülen float32 metriği kayıpsız korumaya öncelik ver.
- RGB'nin SVO2 içinde güvenilir biçimde yeniden okunabildiğini gerçek SDK ile
  doğrula. Bu doğrulanamıyorsa veya backend native replay sağlamıyorsa RGB'yi
  de taşınabilir, chunk'lı ve açık bir raw stream olarak sakla.
- Mock backend native SVO2 sağlamadığı için test edilebilir taşınabilir RGB-D
  raw archive yolu üretmeli; sentetik olduğu her metadata seviyesinde yazmalı.
- Bir backend depth sağlamıyorsa gerçek üretim kaydında bunu sessizce kabul
  etme. Ön kontrolde kayıt engeli ve çözüm göster. Yalnız açık sentetik/test
  senaryoları capability eksikliğini dürüst metadata ile kullanabilir.

Depolama maliyeti yüksekse bunu veriyi atarak çözme. Kayıttan önce tahmini
GB/dakika ve mevcut diskle tahmini süreyi göster; güvenli eşik altındaysa kaydı
başlatma veya açık uyarı/engelleme politikası uygula. Çözünürlük, FPS veya
depth'i sessizce düşürme.

### 5.3 Senkronizasyon ve provenance

Ham RGB-D'nin ileride yeniden işlenebilmesi için yalnız dosyanın varlığı yeterli
değildir. En az şu eşleme kaydedilsin:

- recording-local sıra numarası
- kamera frame/index bilgisi
- host timestamp
- camera timestamp
- mümkünse doğrulanmış SVO frame position veya replay timestamp
- RGB mevcut/yazıldı durumu
- depth mevcut/yazıldı durumu
- skeleton frame mevcut/yazıldı durumu
- capture/drop/gap durumu

Dosya veya field adlarını mevcut mimariye göre seç; fakat `skeleton.jsonl`
akış konumu ile kamera kare numarasını yeniden birbirine karıştırma.
Senkronizasyon sözleşmesi take metadata'sında ve README'de açıklansın.

SVO replay ile canlı akışta 1:1 sıra varsayma. Bunu timestamp/frame bilgisiyle
doğrula. Gerekirse sürümlü `raw_capture_manifest.json` veya eşdeğer bir
metadata/index dosyası oluştur.

### 5.4 Kayıt başarısı, arıza ve kurtarma

- Native/raw RGB-D kaydı başlatılamıyorsa gerçek kayıt başlamasın.
- Yazım sırasında RGB veya depth kaybı olursa bu yalnız log/not olmasın;
  ayrı sayaç, kalite durumu ve take state üzerinde açık etkisi olsun.
- Preview drop, skeleton queue drop, RGB raw drop, depth raw drop ve backend
  drop ayrı sayılmalı.
- Raw writer hatasında eldeki dosyaları silme. Take `PARTIAL` veya `FAILED`
  kalsın ve kurtarma ekranında neden görülsün.
- Finalize sırasında gerekli raw dosyaların varlığı ve makul boyutu
  doğrulansın, checksum alınsın.
- ZED donanımı erişilebiliyorsa finalize sonrası SVO2 yeniden açma ve en az
  başlangıç/orta/son konumlardan RGB + depth retrieve smoke testi yap. Her
  kayıtta pahalıysa hızlı doğrulama ile ayrı derin doğrulama aracını ayır;
  fakat başarı iddiasının hangi seviyede olduğunu metadata'ya yaz.
- Native kayıt durdurma hatası yutulup take başarılı gösterilmesin.
- `get_recording_status()` sayaçlarının bu makinede daha önce güvenilmez
  olduğu bilgisini koru; tek başarı kanıtı olarak kullanma.

İleride ham take'ten RGB/depth/skeleton çıkarabilmek için GUI'den veya CLI'dan
çalıştırılabilen, ham veriyi değiştirmeden yeni bir derived cache/dışa aktarım
oluşturan bir extraction/replay yolu ekle. En azından belirli frame/timestamp
aralığını okuyabilsin ve veri sözleşmesini açıklayan manifest yazsın.

## 6. Capture ekranında görüntü üzerine tıklayarak kişi seçimi

### 6.1 Kullanıcı deneyimi

Canlı RGB veya RGB+iskelet görünümünde:

- Her algılanan kişinin iskeleti ve kısa takip etiketi görülsün.
- Kullanıcı kayda başlamadan önce doğrudan kişinin iskeletine/gövdesine
  tıklayarak onu seçebilsin.
- Seçilen kişi belirgin vurgu, çerçeve/halo ve “Kaydedilecek kişi” etiketiyle
  gösterilsin; diğer kişiler soluk gösterilsin.
- Dropdown mevcutsa erişilebilirlik ve test amacıyla korunabilir, fakat görüntü
  üzerinde tıklama birinci sınıf akış olsun.
- Letterbox, DPI scale ve farklı görüntü boyutlarında tıklama koordinatı doğru
  kaynak görüntü pikseline çevrilsin.
- Hit testing için mevcutsa tracker'ın gerçek `joint_positions_2d` verisini
  kullan. Yoksa doğrulanmış projection/bounding yaklaşımı uygula ve bunun
  yaklaşık olduğunu belirt. Birbirine çok yakın iki kişi varsa rastgele seçim
  yapma; kullanıcıya adayları ayırt ettir.
- Manuel kişi-kilitli modda kişi seçilmeden kayıt düğmesi aktif olmasın veya
  kayıt başlatma açık, anlaşılır bir engel versin.
- Tek kişi varken “bu kişiyi seç” kolay eylemi bulunabilir; fakat seçimin
  gerçekten yapıldığı ekranda açıkça görünmeli.

`VideoView.clicked` yalnız parametresiz sinyal olarak kalıp hangi kişiye
tıklandığını GUI page içinde tahmin ettirmesin. Widget gerektiği kadar gerçek
tıklama konumu/aday body bilgisini kontrollü biçimde üst katmana aktarabilsin;
domain kararını yine GUI widget içine gömme.

### 6.2 SDK tracking ID ile mantıksal katılımcı kimliğini ayır

ZED'in kısa ömürlü `tracking_id` değeri, kaydın mantıksal “seçilen kişi”
kimliği değildir. Take içinde kararlı bir mantıksal kimlik oluştur, örneğin:

```text
selected_subject_id = take-local stable UUID/code
current_tracker_body_id = o karede eşlenen SDK ID veya null
```

İsimleri mimariye göre uyarlayabilirsin. Temel koşullar:

- Seçim anı, ilk tracker ID, kaynak frame/timestamp, seçim yöntemi ve seçim
  durumu metadata'ya yazılsın.
- Her frame, seçilen mantıksal kişinin hangi tracker gövdesiyle eşlendiğini
  veya o karede bulunamadığını kaydedebilsin.
- Seçilen kişi görünmüyorsa `null`/missing + mask yazılsın. Başka kişinin
  iskeleti seçili kişinin yerine geçmesin.
- Tracker aynı kişiye yeni bir ID verirse mantıksal subject ID değişmesin;
  yalnız source tracker ID association olayı yazılsın.
- Bütün association/re-identification/manual-confirmation olayları frame,
  timestamp, eski/yeni tracker ID, yöntem, skor/güven ve neden ile audit trail'e
  girsin.
- Kayıt sırasında sıradan bir tıklama kişiyi değiştirmesin. Gerekirse ayrı
  “Kimliği yeniden doğrula/değiştir” eylemi, açık onay ve olay kaydı kullan.
  Geçmiş ham dosyaları geriye dönük yeniden yazma.

### 6.3 Kişi kaybolması ve yeniden ilişkilendirme

En az şu durum makinesine denk bir davranış kur:

```text
UNSELECTED -> LOCKED -> TEMPORARILY_LOST -> REIDENTIFYING -> LOCKED
                                      \-> AMBIGUOUS / NEEDS_CONFIRMATION
```

Davranış:

- Seçilen tracker ID görünürken doğrudan onu kullan.
- Seçilen kişi kısa süre kaybolunca kimlik kilidini kaldırma; `LOST` göster ve
  kaydı sürdür.
- Kadrajdaki başka bir kişiyi “en iyi confidence” olduğu için otomatik seçme.
- Aynı SDK ID geri döndüğünde bunun gerçekten aynı track olduğuna dair SDK
  davranışını doğrula. ID reuse riski varsa yalnız sayıya güvenme.
- ID değişmişse yeniden ilişkilendirme take-local, sürümlü ve test edilebilir
  kanıtlara dayanmalı. Uygun kanıtlar arasında kısa boşlukta 3B konum/hız
  sürekliliği, 2B konum, depth, vücut/kemik oranları ve yüz tanımaya gitmeden
  kıyafet/gövde crop'ından elde edilen basit appearance descriptor olabilir.
- Uzun kaybolmada son konumu tek başına kullanma. Antrenör seçilen kişinin
  yerine geçmiş olabilir.
- Otomatik eşleştirme için minimum skor ve ikinci en iyi adaya göre yeterli
  margin şartı olsun. Eşikler/weights sürümlü ve metadata'ya yazılsın.
- Kanıt yetersiz veya iki aday yakınsa `AMBIGUOUS` kal; yanlış kişiye geçme.
  GUI kullanıcının aynı kişiyi yeniden tıklayarak doğrulamasına izin versin.
- Appearance descriptor kullanılırsa yüz biyometrisi üretme, take dışı kalıcı
  kişi tanıma veritabanı kurma ve descriptor'ın kapsamını/provenance'ını açıkla.
- Seçilen kişi yeniden bulunamazsa kayıt yine korunabilir; ilgili kareler
  subject-absent olur ve kalite raporu bunu gösterir.

“Kişi kadrajdan çıktıktan sonra her koşulda otomatik ve kesin tanınır” şeklinde
gerçek dışı garanti verme. Ürün garantisi şudur: **sistem belirsizken başka
kişiye sessizce geçmez; otomatik eşleştirme yalnız yeterli kanıtla yapılır.**

### 6.4 Ham detections ile seçilen subject track'i ayır

Gelecekte yeniden işleme ve hata analizi için mevcut bütün-body detection
bilgilerini kaybetme:

- `skeleton.jsonl` içindeki bütün algılanan body kayıtları geriye uyumluluk ve
  audit için korunabilir.
- Bunun yanında hangi body'nin seçilen mantıksal subject'e ait olduğu kare
  bazında açık ve otoritatif olmalı.
- Etiketleme ve yeni export, kişi-kilitli take'te yalnız bu otoritatif subject
  association'ını kullanmalı.
- Seçili subject bulunamadığında koordinatlar NaN ve presence/valid mask false
  olmalı; `primary_body()` fallback'i dataset ground truth üretiminde
  kullanılmamalı.
- Eski take'lerde yalnız `active_id` varsa legacy davranış açıkça belirtilsin.
  Otomatik migration veya kesin kişi kimliği uydurma.

Kişi seçim kapsamı ve kalite metrikleri ekle:

- selected-subject coverage
- selected-subject lost frame/duration
- re-identification sayısı
- ambiguous frame/duration
- manual confirmation sayısı
- unexpected tracker-ID reuse/switch bulguları
- çoklu kişi bulunan süre

## 7. Sürekli aktivite ve spor-dışı hareket etiketleme

### 7.1 Etiket ontolojisi

Mevcut `MovementSample` + correctness + `ErrorInterval` modelini kaldırma.
Bunun üzerine take zaman çizelgesine isteğe bağlı, karşılıklı dışlayan bir
aktivite-durum katmanı ekle:

```text
background
transition
target_exercise
other_activity
```

Çok önemli: `unlabelled` bir eğitim sınıfı değildir. Kullanıcının henüz
etiketlemediği kareler background kabul edilmemeli.

Anlamlar:

- `background`: bekleme, nötr duruş, oturma gibi açıkça spor olmayan zaman
- `transition`: egzersize hazırlanma, başlangıç pozisyonuna geçme veya çıkma
- `target_exercise`: tanınması istenen egzersizin yapıldığı zaman
- `other_activity`: yürüme, eğilip eşya alma, kıyafet düzeltme, ayakkabı
  bağlama veya hedef dışı başka hareket

`target_exercise` aralığı exercise code taşımalı ve mümkünse mevcut
`MovementSample` ile tek kaynaklı/linkli olmalı. Aynı sınırların iki bağımsız
nesnede sessizce farklılaşmasına izin verme. Mevcut sample modelini genişletmek
veya sürümlü take-level activity sidecar kullanmak arasında repository'ye en
uygun olanı seç; fakat kaynak otoritesi açık olsun.

`other_activity` için ilk sürümde genel sınıf yeterlidir. Projenin label
schema'sına kullanıcı tanımlı alt tür eklemek temiz ve geriye uyumluysa ekle;
kod içinde günlük hareket sınıfları uydurup zorunlu hale getirme.

### 7.2 Zaman çizelgesi ve annotation UX

İnceleme ekranında mevcut HAREKET ve HATA modlarını bozmayacak üçüncü bir
AKTİVİTE modu veya eşdeğer anlaşılır akış oluştur:

- Kullanıcı sürükleyerek activity interval oluşturabilsin.
- Durumu `background`, `transition`, `target_exercise`, `other_activity`
  olarak değiştirebilsin.
- `target_exercise` için proje label schema'sındaki egzersizi seçebilsin.
- Aralıklar seçilen subject'in timeline'ına bağlı olsun.
- Karşılıklı dışlayan state aralıkları çakışmasın; çakışma GUI ve domain
  katmanında doğrulansın.
- Unlabelled boşluklar görünür ve farklı çizilsin.
- “Etiketlenmemiş boşlukları background olarak işaretle” kolaylığı ancak açık
  kullanıcı onayıyla çalışsın; sessiz otomatik tamamlama yapma.
- Uzun take'te tamamlanmış etiket kapsamı ve unlabelled süre gösterilsin.
- Hiç egzersiz içermeyen, tamamı açıkça background/other olarak etiketlenmiş
  take geçerli bir sürekli-aktivite eğitim örneği olabilsin.
- Seçili subject'in görünmediği kareler activity etiketi taşısa bile ayrıca
  subject presence maskesiyle ayrılabilsin. “Kişi yok” ile “kişi duruyor” aynı
  şey değildir.

Mevcut inclusive frame-position sözleşmesini koru: interval sınırları
`skeleton.jsonl` frame-list pozisyonlarıdır; kamera frame numarası değildir.
Timestamp ve kamera index bilgileri ayrıca saklansın.

### 7.3 Annotation şeması ve readiness

- Annotation şemasını yalnız ekleme yönünde sürümle.
- Eski `segments.json` okuması dosyayı değiştirmesin.
- Yeni continuous export readiness'i mevcut movement-sample readiness'inden
  ayrı değerlendir. Bir take hareket-sample exportuna hazır olmayıp continuous
  exporta hazır olabilir veya tersi olabilir.
- Continuous exportta etiketlenmemiş kareler ya açık maskeyle korunmalı ya da
  kullanıcı “tam kapsam gerekli” seçtiyse release'i bloke etmeli.
- Geçersiz/çakışan/bilinmeyen activity interval release'te sessizce atılmasın;
  validation error veya gerekçeli exclusion üretmeli.
- Activity interval düzenlemeleri undo/redo ve autosave'e katılsın.
- Annotation ham `take.json`, SVO2 veya RGB-D stream'ini değiştirmesin.

## 8. Sürekli-aktivite dataset export sözleşmesi

Sürekli modda varsayılan örnek bir take'in tamamı olsun; gerçek `T` uzunluğu
korunsun. Export katmanında sessiz interpolation, fixed-length resampling,
padding veya augmentation yapma. Bunlar eğitim loader'ının sorumluluğudur.

Her continuous sample en az şunları içersin; isimleri mevcut sözleşmeye uyumlu
hale getirebilirsin:

```text
joints_xyz                         float32 [T,J,3]
frame_indices                      int64   [T]
camera_timestamps_ns               int64   [T]
subject_present_mask               bool    [T]
subject_source_tracking_id         int64   [T]      # yoksa sentinel + mask
subject_association_confidence     float32 [T]
activity_state_code                int16   [T]
activity_label_mask                bool    [T]
exercise_active                    bool    [T]
exercise_class_index               int32   [T]
exercise_class_valid_mask          bool    [T]
exercise_start_target              uint8   [T]
exercise_end_target                uint8   [T]
```

Bu listeyi gerçek ihtiyaçlara göre iyileştir. Başlangıç/bitiş target'larının
inclusive interval sözleşmesinden nasıl üretildiğini açıkça tanımla. Bir
egzersiz bir karelikse start ve end aynı karede 1 olabilir. Unlabelled kare ile
background code birbirinden maskeyle ayrılmalı; `-1` gibi sentinel kullanılırsa
spec'te yazılmalı.

Mevcut selected skeleton feature registry continuous sample üzerinde de
çalışabilsin. Hız/ivme bir subject-lost boşluğu üzerinden türetilmesin.

Hata etiketleri full-take timeline'a taşınıyorsa:

- `error_multi_hot [T,C]` yalnız ilgili target exercise sample sınırlarında
  anlamlı olsun.
- `error_label_mask [T]` veya eşdeğer maske ile background/unlabelled karelerde
  “hata yok” ile “hata etiketi uygulanamaz” ayrımı yapılsın.
- Correctness yalnız target exercise interval/sample için geçerli olsun.

Manifest/label mapping/activity spec içinde:

- state code sırası ve sürümü
- exercise mapping
- interval listesi ve frame/timestamp sınırları
- subject selection/re-identification provenance özeti
- raw RGB-D source path/reference ve checksum
- annotation coverage
- selected-subject coverage
- array contract, dtype, unit, missing policy
- source take ID ve dataset split group IDs

bulunsun.

Raw RGB-D dosyalarını her küçük ML `.npz` örneğine kopyalama. Otoritatif ham
take arşivinde bir kez koru; release manifeste checksum'lı kaynak referansı
yaz. Kullanıcı taşınabilir, bağımsız RGB-D release isterse extraction/export
seçeneği açıkça dosyaları kopyalasın veya türetsin ve boyutu önceden göstersin.

Dataset fingerprint şunlara duyarlı olsun:

- activity interval sınırları ve sınıfları
- exercise linkleri
- subject association timeline'ı
- seçili continuous/movement export modu
- array içerik checksumları
- raw RGB-D kaynak checksum/provenance
- feature seçimleri ve mevcut feature sürümleri

Farklı katılımcı/session/take grupları train/validation/test arasında
sızdırılmamalı. Aynı continuous take'ten ileride üretilen pencereler farklı
splitlere dağıtılamasın.

## 9. Dataset ve Capture ekranındaki bilgiler

Capture ekranında en az şunlar görünür olsun:

- kayıt amacı/modu
- ham RGB-D arşivinin zorunlu ve hazır olup olmadığı
- tahmini ham veri boyutu ve disk süresi
- seçilen kişi ve mantıksal subject kimliği
- kilit durumu: seçilmedi / kilitli / kayıp / yeniden aranıyor / belirsiz
- o an eşlenen tracker ID
- subject-lost süresi
- kadrajdaki kişi sayısı
- ayrı RGB/depth/skeleton drop göstergeleri

Dataset ekranına continuous veri için yararlı özetler ekle:

- toplam açıkça etiketlenmiş background/transition/target/other süreleri
- unlabelled süre
- egzersiz başlangıç/bitiş sayısı
- hiç egzersiz içermeyen negatif take sayısı
- seçili subject coverage ve ambiguous/lost süreleri
- ham RGB-D bütünlük durumu

Bu metrikleri movement-sample sayılarıyla karıştırma. Örneğin “hazır hareket
sayısı” ile “continuous exporta hazır take sayısı” ayrı olsun.

## 10. Mimari ve performans sınırları

- Qt, pyzed ve domain hesaplarını birbirine karıştırma.
- Kişi association/re-identification mantığı Qt widget içinde olmasın; Qt'siz,
  sürümlü ve deterministik test edilebilir bir servis/domain katmanı kur.
- `primary_body()` fallback davranışını global olarak değiştirmek eski yerleri
  bozacaksa yeni, açık `selected_body_strict()`/association API'si kullan.
- RGB-D yazımı iskelet JSONL yazımını ve GUI'yi bloke etmesin; ancak ayrı
  kuyruklar veri kaybını gizlemesin.
- Kuyruklar bounded olsun. Overflow meydana gelirse hangi stream'in karesinin
  kaybolduğu ayrı kaydedilsin ve take başarılı görünmesin.
- Full-resolution RGB/depth karelerini gereksiz kopyalamaktan kaçın; fakat
  performans uğruna otoritatif veriyi sessizce atma veya çözünürlüğü düşürme.
- Uzun take'leri RAM'e toplama. Streaming/chunking kullan.
- Yarım chunk ve elektrik kesintisi kurtarma davranışı test edilsin.
- Metadata atomik yazılsın; büyük frame payloadları için atomik olmayan fakat
  append-safe/chunk-finalization sözleşmesi açıkça belgelensin.
- Raw/derived/annotation/release sınırları korunmalı.

## 11. Testler

Donanım gerektirmeyen deterministik testleri genişlet. En az şu durumları
kapsa.

### RGB-D arşivi

- `store_depth_frames` kontrolünün gerçekten veri üretmesi veya kaldırılıp
  zorunlu politikaya dönüşmesi
- Native recording destekleyen backend'te raw kayıt başlamazsa take'in
  başlamaması
- Raw writer ortada hata verirse take'in `FINALIZED` olmaması ve dosyaların
  korunması
- RGB/depth/frame/timestamp senkron indeks round-trip
- Depth NaN/Inf, dtype, shape ve metre biriminin round-trip'ı
- Chunk sınırları, son kısa chunk ve yarım chunk kurtarma
- RGB/depth/skeleton drop sayaçlarının birbirine karışmaması
- Checksum değişince bütünlük doğrulamasının hata vermesi
- Mock backend ile tam RGB-D archive → replay testi
- Eski take'in yeni raw manifest olmadan okunması ve eksikliğin dürüstçe
  raporlanması
- Disk alanı yetersiz ön kontrolü

### Kişi seçimi ve kimlik kilidi

- Letterbox'lı VideoView'da tıklama doğru kişiyi seçer
- İki iskelet üst üste yakınsa belirsizlik rastgele çözülmez
- Seçilen ID görünürken başka kişi daha yüksek confidence alsa da seçim değişmez
- Seçilen kişi kaybolduğunda başka body'ye fallback yapılmaz
- Seçilen kişi aynı ID ile geri geldiğinde track devam eder
- Aynı kişi güçlü kanıtla yeni tracker ID aldığında mantıksal subject ID
  değişmeden association event oluşur
- Yeni ID için iki benzer aday varsa otomatik geçiş olmaz; `AMBIGUOUS` kalır
- Antrenör kadraja girdikten sonra katılımcı çıkarsa antrenörün iskeleti
  seçili subject datasına yazılmaz
- Tracker ID reuse senaryosu yalnız ID eşit diye kabul edilmez
- Manuel yeniden doğrulama audit event üretir
- `skeleton.jsonl` bütün bodies'i korurken selected-subject export yalnız doğru
  association'ı kullanır
- Subject-lost kareleri NaN/mask üretir ve türev boşluk üzerinden hesaplanmaz
- GUI gerçek paint + mouse event testi iki tema ve en az 1366x768'de çalışır

### Sürekli aktivite annotation/export

- Eski v2 annotation sidecar yeni kodla rewrite olmadan açılır
- Activity interval CRUD + undo/redo + round-trip
- Çakışan karşılıklı dışlayan state interval reddedilir
- Unlabelled boşluk background'a dönüşmez
- Kullanıcı onaylı “boşlukları background yap” yalnız hedef boşlukları doldurur
- Tamamı background olan ve hiç hareket sample'ı olmayan take continuous
  exportta geçerlidir
- Aynı take mevcut movement exportta eski kurallarla davranmaya devam eder
- Target exercise interval ile MovementSample linki sınır değişiminde tek kaynak
  olarak tutarlı kalır
- Continuous `.npz` bütün frame-level target/mask şekillerini doğru yazar
- Başlangıç/bitiş hedefleri interval sınırlarıyla birebir uyuşur
- Subject absent ile background birbirine karışmaz
- Activity annotation veya subject association değişince fingerprint değişir
- Aynı take'ten türetilen kayıtlar split group kimliğini korur
- Feature registry continuous take'te tracking gap üzerinden türev almaz
- GUI export seçenekleri varsayılan olarak mevcut movement exportunu korur

### Tam regresyon

- Mevcut feature export, annotation, GUI painting, storage ve self-test
  testleri bozulmamalı.
- Testler gerçek kullanıcı preferences dosyasına yazmamalı.
- Donanım olmadan `pyzed` import edilmemeli.

Önce ilgili testleri, sonra tam paketi çalıştır:

```powershell
.\scripts\run_tests.ps1
conda run -n KineSynth python -m kinecapture --self-test
```

## 12. Gerçek ZED 2i doğrulaması

Bu görev capture hattını ve SVO/RGB-D sözleşmesini değiştirdiği için yalnız
stub testleri yeterli değildir. Kamera erişilebiliyorsa kullanıcı verisini
silmeden kısa, kontrollü bir donanım smoke testi yap:

1. Bir kişi seçiliyken kayıt başlat.
2. İkinci kişi kısa süre kadraja girsin; seçimin değişmediğini doğrula.
3. Seçilen kişi kısa süre kadrajdan çıkıp geri girsin; aynı ID veya güvenli
   re-association davranışını kaydet.
4. RGB, depth, skeleton ve timestamp sayımlarını raporla.
5. SVO2'yi yeniden açıp başlangıç/orta/son konumdan RGB ve depth okuyabildiğini
   doğrula.
6. Saklanan exact depth stream'i yeniden okuyup canlı frame sözleşmesiyle
   shape/dtype/unit/invalid-mask açısından karşılaştır.
7. Take checksum ve raw manifest doğrulamasını çalıştır.

Gerçek test sırasında otomatik re-identification kesin biçimde tetiklenmediyse
tetiklenmiş gibi raporlama. Donanım veya ikinci kişi bulunamadıysa hangi kısımın
yalnız deterministik stub/mock ile doğrulandığını açıkça yaz.

## 13. Dokümantasyon

README'yi güncelle:

- iki dataset üretim modu
- continuous activity sınıfları ve `unlabelled != background` ayrımı
- full-take variable-length continuous sample yapısı
- movement-sample exportunun geriye uyumlu kaldığı
- zorunlu RGB-D raw archive ve gerçek dosya düzeni
- SVO2'nin sakladığı kaynak ile yeniden hesaplanan depth ayrımı
- exact depth sidecar/chunk formatı
- RGB/depth/skeleton zaman eşlemesi
- disk kullanımı ve failure/recovery davranışı
- görüntü üzerine tıklayarak kişi seçimi
- tracker ID ile mantıksal subject ID ayrımı
- lost/re-identifying/ambiguous davranışı
- başka kişiye sessiz fallback yapılmadığı
- privacy sınırı: yüz tanıma veya take'ler arası biyometrik veritabanı yok
- continuous export array sözleşmesi ve maskeler

`MEMORY.md` içine şunları gerçek sonuçlarla yaz:

- yeni schema sürümleri
- raw RGB-D dosya düzeni ve neden seçildiği
- codec/compression ve SVO replay konusunda doğrulanan gerçekler
- exact depth saklama kararı
- sync/index sözleşmesi
- subject-lock state machine ve association algoritması sürümü
- GUI seçimi ve belirsizlik davranışı
- activity annotation modeli ve readiness kuralları
- continuous export arrayleri
- geriye uyumluluk kararları
- test komutları ve gerçek sonuçlar
- gerçek donanımda doğrulanan ve doğrulanamayan maddeler
- promptta bulunmayıp bağımsız inceleme sonucunda eklenen iyileştirmeler
- bilinçli olarak sonraya bırakılan büyük ürün kararları

## 14. Tamamlanma ölçütü

Görev ancak şu koşulların tamamı sağlanırsa tamamlanmış sayılır:

1. Mevcut movement-sample kayıt, etiketleme ve export akışı çalışmaya devam
   ediyor; default export geriye uyumlu.
2. Sürekli aktivite modu isteğe bağlı olarak kullanılabiliyor.
3. Background, transition, target exercise ve other activity aralıkları gerçek
   timeline üzerinde etiketlenebiliyor; unlabelled kareler background sayılmıyor.
4. Hiç egzersiz içermeyen açıkça etiketlenmiş negatif take export edilebiliyor.
5. Continuous release full-take değişken uzunluğu ve frame-level mask/targetları
   doğru yazıyor.
6. Her yeni gerçek take yeniden işlenebilir RGB ve metric depth ham kaynağı
   olmadan başarılı sayılmıyor.
7. Exact canlı depth stream kalıcı, chunk'lı/kurtarılabilir ve zaman eşlemeli
   olarak saklanıyor.
8. SVO2 codec ve replay davranışı varsayım değil gerçek SDK ile doğrulanmış ve
   dürüstçe belgelenmiş.
9. Capture ekranında kişi doğrudan görüntü üzerine tıklanarak seçilebiliyor.
10. Tracker ID ile kararlı mantıksal selected subject kimliği ayrılmış.
11. Seçilen kişi kaybolduğunda başka kişiye sessiz fallback yapılmıyor.
12. Yeniden ilişkilendirme yalnız yeterli kanıtla yapılıyor; belirsiz durumda
    GUI doğrulama istiyor ve yanlış iskelet ground truth'a girmiyor.
13. Ham all-body detections korunurken annotation/export otoritatif selected
    subject association'ını kullanıyor.
14. RGB, depth, skeleton ve subject-association veri kayıpları ayrı ölçülüyor.
15. Raw failure take'i `FINALIZED` göstermiyor; kısmi dosyalar kurtarılabiliyor.
16. Schema, fingerprint, checksum, manifest ve validation yeni alanlara duyarlı.
17. Mock backend ve donanımsız testler bütün kritik durumları kapsıyor.
18. Tam test paketi ve self-test çalıştırılmış; gerçek sonuç raporlanmış.
19. Mümkün olan ZED donanım smoke testi yapılmış; yapılmayan bölüm açıkça
    belirtilmiş.
20. README ve `MEMORY.md` gerçek implementasyonla uyumlu güncellenmiş.
21. Claude prompt listesinin ötesinde gerekli veri/olay/kalite alanlarını
    kendisi değerlendirmiş; eklediklerini ve reddettiklerini gerekçelendirmiş.

Son yanıtında kısa fakat somut olarak şunları raporla:

- değiştirilen ana dosyalar
- eski akışın nasıl korunduğu
- yeni continuous annotation ve export sözleşmesi
- gerçek raw RGB-D dosya düzeni ve disk maliyeti
- SVO2/replay konusunda doğrulanan gerçekler
- kişi seçimi ve yeniden ilişkilendirme algoritması
- başka kişiye geçmeyi önleyen mekanizma
- schema/migration/fingerprint kararları
- GUI deneyimi
- çalıştırılan testlerin gerçek sonuçları
- gerçek ZED doğrulamasının gerçek sonucu
- kendi incelemenle eklediğin maddeler
- bilinçli olarak sonraya bıraktığın noktalar
