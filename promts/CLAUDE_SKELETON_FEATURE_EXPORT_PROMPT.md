# Claude Code Görevi — Seçilebilir İskelet Özellikleri ve Zengin Dataset Exportu

> **Bu görevin izi:** [6C uygulama kaydı](../knowledge/archive/memory/6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · [Etiket ve feature sözleşmesi](../knowledge/concepts/annotation-and-features.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


KineCapture repository'sinde uçtan uca bir **seçilebilir iskelet özellikleri ve
zengin export sistemi** uygula.

Bu görevi yalnızca analiz veya plan olarak bırakma. Mevcut mimariye uygun
implementasyonu tamamla, testleri çalıştır, dokümantasyonu ve `MEMORY.md`
dosyasını güncelle. Kullanıcı verisini değiştirme veya eski release'leri yeniden
yazma.

## Başlangıç ve çalışma kuralları

1. Önce repository kökündeki `CLAUDE.md` ve `MEMORY.md` dosyalarının tamamını
   oku.
2. Ardından özellikle şu dosyaları incele:
   - `src/kinecapture/domain/models.py`
   - `src/kinecapture/camera/zed.py`
   - `src/kinecapture/camera/mock.py`
   - `src/kinecapture/recording/take_writer.py`
   - `src/kinecapture/playback/take_reader.py`
   - `src/kinecapture/export/release.py`
   - `src/kinecapture/gui/pages/export.py`
   - `src/kinecapture/visualization/skeleton_spec.py`
   - `src/kinecapture/visualization/mapping.py`
   - ilgili testler
3. Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
   veya gereksiz bağımlılık oluşturma.
4. Çalışma ağacı kirliyse kullanıcı değişikliklerini koru.
5. KineSynthV3 repository'si yalnızca uyumluluk referansıdır; bu görevde
   KineSynthV3 kodunu değiştirme.
6. Kod ve veri alanları İngilizce, kullanıcıya görünen GUI metinleri Türkçe
   olsun.
7. Yeni veya doğrulanmamış klinik iddia üretme. Hesaplanan çıktılar “kinematik
   özellik” veya gerekiyorsa “biyomekanik proxy” olarak adlandırılsın; klinik
   ölçüm olarak sunulmasın.

## Verilen liste üst sınır değildir — bağımsız araştırma ve muhakeme zorunluluğu

Bu prompttaki feature ve raw alan listesi minimum kapsam ve yönlendirmedir;
eksiksiz veya nihai bir katalog değildir. Yalnız burada adı geçen maddeleri
mekanik biçimde uygulayıp durma.

Repository'yi, yerel ZED SDK 5.4 sözleşmesini, KineSynthV3'ün gerçek
preprocessing/model girdilerini ve iskelet tabanlı ML yöntemlerinin ihtiyaçlarını
inceleyerek **burada açıkça yazılmamış fakat bilimsel veya mühendislik açısından
değerli başka veri/özellikler olup olmadığını kendin değerlendir**.

Yeni bir alan veya feature keşfedersen şu karar çerçevesini kullan:

- Ham kayıttan daha sonra güvenilir biçimde geri üretilemiyor mu? Öyleyse kayıt
  sırasında saklanmasına öncelik ver.
- Mevcut ham iskelet ve timestamp verisinden deterministik üretilebiliyor mu?
  Öyleyse ham akışı değiştirmek yerine sürümlü, seçilebilir export feature'ı
  olarak tasarla.
- Birden fazla ML yaklaşımında anlamlı olabilecek mi; yoksa yalnız tek bir
  modele özel preprocessing mi? Modele özelse canonical exporta gömme.
- Yeni bilgi taşıyor mu, yoksa mevcut bir array'in belirsiz adla tekrarı mı?
- Koordinat uzayı, birim, zaman hizası, validity maskesi ve eksik veri davranışı
  açıkça tanımlanabiliyor mu?
- Skeleton mapping sonrasında semantiği korunuyor mu?
- Dataset split'i görmeden hesaplanabiliyor mu; leakage riski var mı?
- Tracker gürültüsünü veya kamera bakışını gerçek biyomekanik fark gibi modele
  öğretme riski var mı?
- Test edilebilir ve yeniden üretilebilir mi?

Bu değerlendirme sonucunda yararlı ve güvenli bulduğun ek raw alanları,
feature'ları, kalite maskelerini, provenance metadata'sını, GUI kontrollerini ve
validation kurallarını **görev kapsamına kendin ekle**. Eklediğin her ilave için
son raporda şu dört şeyi yaz:

1. Neyi ekledin?
2. Hangi ML/analiz ihtiyacına hizmet ediyor?
3. Neden raw-capture alanı veya derived-export feature'ı olarak seçtin?
4. Birim, koordinat uzayı, eksik veri, mapping ve klinik yorum sınırları nedir?

Ancak bu yetki sınırsız kapsam genişletme anlamına gelmez. Yeni bağımlılık,
etiket ontolojisi, klinik eşik, kullanıcıdan istenen yeni ölçüm veya mevcut veri
modelini kökten değiştiren bir karar gerekiyorsa bunu sessizce kesinleştirme.
Önce güvenli ve geriye uyumlu çekirdeği tamamla; büyük ürün kararlarını ayrı ve
gerekçeli bir takip önerisi olarak raporla. Doğrulanmamış SDK alanı veya uydurma
biyomekanik metrik ekleme.

## Ürün hedefi

KineCapture yalnızca sabit bir `[T,J,3]` pozisyon dataseti üreten araç olarak
kalmamalı. Ham iskelet sinyalini koruyan, ancak export sırasında kullanıcının
farklı ML yöntemleri için istediği ek veri ve türetilmiş özellikleri seçebildiği
sürümlü bir özellik platformuna dönüşmeli.

Temel ilke:

- `joints_xyz`, kare indeksleri ve kamera zaman damgaları
  canonical/otoritatif veri olarak korunmalı.
- Root centering, body alignment, hız, ivme, kemik vektörü, açı ve simetri gibi
  çıktılar ham koordinatın yerine geçmemeli.
- Seçildiklerinde `.npz` içine ayrı ve açık isimli diziler olarak eklenmeli.
- Her türetilmiş özelliğin tanımı, sürümü, şekli, birimi, koordinat uzayı,
  zaman hizası, eksik veri politikası ve algoritma parametreleri release içinde
  bulunmalı.
- Aynı ham kayıt ve aynı feature seçenekleri her zaman aynı sonucu üretmeli.
- Interpolation, padding, temporal resampling, augmentation ve train-dataset
  referansından öğrenilen özellikler bu export katmanına eklenmemeli. Bunlar
  model eğitim katmanının sorumluluğudur.

## Önce mevcut durumu doğrula

Kodda görünen şu noktaları gerçek implementasyondan doğrula ve görevi bunlara
göre yap:

- KineCapture şu anda exportta fiziksel hız üretmiyor.
- `BodyPose` eklem quaternionlarını destekliyor; ZED adapter bunları alıyor ve
  JSONL içinde `quat` olarak saklayabiliyor, fakat export bunları kullanmıyor.
- `BodyPose.root_orientation` alanı var; ancak ZED adapter tarafından
  doldurulmuyor ve mevcut `to_record`/`from_record` round-trip'ında saklanmıyor.
- Yerel ZED SDK 5.4 `BodyData` nesnesinde en az şu alanlar bulunuyor olabilir:
  `velocity`, `position_covariance`, `keypoints_covariance`,
  `local_position_per_joint`, `local_orientation_per_joint`,
  `global_root_orientation`, `keypoint_2d`, `action_state`.
- Bu alanların isim ve şekillerini yerel kurulumdan ve resmi SDK sözleşmesinden
  doğrula. Şekli veya anlamı doğrulanmayan alanı tahmin ederek doldurma.

## 1. Geriye uyumlu ham iskelet zenginleştirmesi

Yeni kayıtların, sonradan koordinatlardan güvenilir biçimde geri
üretilemeyecek tracker çıktılarını kaybedilmeden saklayabilmesini sağla.

`BodyPose` ve JSONL sözleşmesini geriye uyumlu biçimde aşağıdaki isteğe bağlı
alanları taşıyabilecek şekilde genişlet:

- `joint_positions_2d`: `[J,2]`
- `joint_position_covariances`: `[J,6]`
- `local_joint_positions_xyz`: `[J,3]`
- `joint_orientations`: `[J,4]`, mevcut alan
- `root_position`: `[3]`, mevcut alan
- `root_orientation`: `[4]`
- `tracker_root_velocity_xyz`: `[3]`
- `root_position_covariance`: `[6]`
- `body_confidence`
- doğrulanabiliyorsa `action_state`

Kurallar:

- Alanlar optional olmalı.
- Eksik veya şekli yanlış alan uydurma değerle doldurulmamalı.
- Eksik sayısal değer NaN olarak temsil edilmeli; JSON'da mevcut politika ile
  `null` kullanılmalı.
- Eski v1 JSONL kayıtları hiçbir migration veya rewrite olmadan okunabilmeli.
- Yeni kayıt şeması sürümlenmeli.
- Yeni okuyucu hem eski hem yeni kayıtları kayıpsız okuyabilmeli.
- Quaternion sırası açıkça `xyzw` olarak belgelenmeli.
- Kovaryansın altı elemanının sırası resmi SDK'da doğrulanmadan
  yorumlanmamalı. Gerekirse ilk sürümde ham altı değer saklanıp sözleşmede
  “SDK native order” denmeli.
- `keypoint_2d` kaydedilecekse görüntü çözünürlüğü ve doğrulanmış kamera
  intrinsics/calibration metadata'sının take/header içinde bulunup
  bulunmadığını denetle. Güvenli biçimde alınabiliyorsa bir kez take
  provenance'a ekle; tahmin etme.
- BODY_18 gibi bazı formatlarda fitting çıktılarının bulunmaması normal kabul
  edilmeli.
- Mock backend'i test edilebilir ve deterministik tut. Gerçek ölçüm gibi
  gösterilmeyen sentetik örnek alanlar veya açık NaN'ler üret.

Mask, RGB crop veya büyük piksel segmentasyonları bu görevin kapsamına girmez.

## 2. Sürümlü feature registry kur

Özellik hesaplarını `export/release.py` içine dağılmış yardımcı fonksiyonlar
olarak yığma. Örneğin `kinecapture/features/` altında domain ve Qt'den
bağımsız bir katman oluştur.

İsimleri mevcut kod yapısına göre uyarlayabilirsin ancak aşağıdaki
sorumlulukları ayır:

- Feature tanımı/metadata modeli
- Feature registry
- İskelet ve anatomik rol çözümleme
- Zaman ve türev yardımcıları
- Kinematik hesaplar
- Açı tanımları
- Simetri tanımları
- Sabit uzunluklu summary feature üretimi
- Export entegrasyonu

Her feature tanımı en az şunları taşımalı:

- kararlı `feature_id`
- `version`
- Türkçe görüntüleme adı ve açıklaması
- kategori
- gerekli kaynak alanlar
- çıktı array anahtarları
- shape sözleşmesi
- dtype
- unit
- coordinate space/reference frame
- time alignment
- missing-value policy
- desteklenen iskelet formatları veya uygulanabilirlik fonksiyonu
- experimental/default durumu
- türetim parametreleri

Feature registry sıralı ve deterministik olmalı. Fingerprint veya GUI sırası
Python `set` sırasına bağlı olmamalı.

## 3. Uygulanacak feature aileleri

Aşağıdaki aileleri gerçekten uygula. Ortak primitiveları kur; her metriği
birbirinden kopuk özel kod olarak yazma.

### A. Canonical çekirdek

Bunlar mevcut dataset sözleşmesinin çekirdeği olarak kalmalı:

- `joints_xyz [T,J,3] float32`
- `frame_indices [T] int64`
- `camera_timestamps_ns [T] int64`

`joints_xyz` export ekranında seçili ve kilitli gösterilebilir. Bu görevde
angle-only gibi canonical iskeleti tamamen kaldıran yeni bir export modu
oluşturma.

### B. Kalite ve geçerlilik

Seçilebilir çıktılar:

- `joint_confidences [T,J]`
- `joint_valid_mask [T,J]`
- `frame_valid_mask [T]`
- `delta_time_s [T]`
- body/tracking confidence ve tracking-state dizileri
- raw kovaryanslar mevcutsa bunlar
- kovaryanstan türetilen uncertainty/std değerleri yalnız eleman sırası
  doğrulandıysa

Maskeler gerçek eksikliği göstermeli. NaN eklem sıfır veya önceki koordinatla
doldurulmamalı.

### C. Alternatif koordinat temsilleri

Seçilebilir ve canonical ham koordinattan ayrı:

- root-centered positions
- body-aligned/yaw-normalized positions
- body frame rotation/transform ve validity mask
- sequence-level body scale
- ölçeğe bölünmüş positions, açıkça ayrı bir feature olarak

Body frame:

- `SkeletonSpec.root_index` ve semantik kalça/omuz rollerini kullanmalı.
- Sol-sağ ekseni, dikey eksen ve forward eksen açıkça tanımlanmalı.
- Gerekli eklemler eksikse tahmin yürütülmemeli; o kare veya sequence
  geçersiz işaretlenmeli.
- Frame-by-frame ve sequence-level orientation aynı isim altında
  karıştırılmamalı.
- Ham `joints_xyz` hiçbir zaman değişmemeli.

### D. Kemik/geometri akışı

`SkeletonSpec.edges` sırasına hizalı olarak:

- `bone_vectors_xyz [T,B,3]`
- `bone_lengths [T,B]`
- `bone_unit_vectors_xyz [T,B,3]`
- ilgili validity maskeleri

`feature_spec.json` içinde her kemik için parent/child indeksleri ve adları
bulunsun.

Mapping sonrası hedef skeleton export ediliyorsa bu özellikler hedef skeleton
topolojisi üzerinde hesaplanmalı. Eksik hedef eklem bulunan kemik NaN kalmalı.

### E. Zamansal kinematik

Seçilebilir olarak:

- joint displacement/delta
- timestamp-aware joint velocity
- joint speed
- timestamp-aware joint acceleration
- root trajectory, root speed ve path length
- jerk yalnız “experimental” olarak ve varsayılan kapalı

Çok önemli semantik ayrım:

- Kare farkı `x[t] - x[t-1]` fiziksel hız değildir. Kullanılacaksa
  `joint_displacement` gibi açık bir ad taşımalı.
- Fiziksel velocity kamera timestamp'lerinden hesaplanmalı ve birimi
  `length_unit/second` olmalı.
- SDK'nın verdiği root velocity ile koordinatlardan türetilen root velocity
  farklı array ve provenance taşımalı.
- Eksik veya sırasız timestamp, `dt <= 0`, aşırı frame gap veya eksik eklem
  durumunda sonuç sıfır değil NaN olmalı ve validity mask false olmalı.
- Merkezi fark kullanılıyorsa sınır ve gap politikası açıkça belgelenmeli.
- Türev alınırken bir tracking boşluğunun üzerinden köprü kurulmasın.
- Filtre/smoothing uygulanırsa algoritma ve pencere parametresi feature
  tanımına ve fingerprint'e girsin. Sessiz smoothing yapma.

Mevcut KineSynthV3'te “velocity feature” ardışık normalize kare farkıdır. Yeni
fiziksel velocity'nin onunla aynı kanal olduğu iddia edilmemeli. Gerekirse
manifest notunda bu fark açıkça yazılsın.

### F. Eklem açıları ve açısal hareket

Versioned anatomik açı tanımları oluştur. En azından iskelet formatının gerekli
eklemleri bulunduğunda:

- sol/sağ dirsek flexion
- sol/sağ diz flexion
- sol/sağ kalça açısı
- sol/sağ ayak bileği açısı, yalnız uygun foot joint mevcutsa
- trunk lean/deviation relative to configured vertical axis
- pelvis ve shoulder line tilt/orientation gibi açıkça tanımlanmış gövde
  açıları

Her açı tanımı:

- semantic id
- görünen ad
- kullanılan joint rolleri/indeksleri
- matematik tanımı
- unit
- geçerli aralık
- applicable skeleton formats

Üç noktalı açı için sayısal olarak kararlı
`atan2(norm(cross(u,v)), dot(u,v))` yaklaşımı tercih et. Sıfıra yakın vektör
veya eksik nokta NaN üretmeli.

Çıktılar en az:

- `joint_angles_rad [T,A]`
- `joint_angle_valid_mask [T,A]`
- `joint_angular_velocity_rad_s [T,A]`

Açı adları ve sütun sırası `feature_spec.json` içinde bulunmalı. Derece yalnız
GUI gösterimi veya ayrıca açık isimli array olarak kullanılabilir; aynı
array'in birimi belirsiz bırakılmasın.

Raw quaternionlardan angular velocity üretilecekse:

- quaternion normu doğrulansın,
- `q` ve `-q` eşdeğerliği nedeniyle zaman boyunca işaret sürekliliği
  sağlansın,
- Euler açılarını doğrudan farklayarak wrap-around sıçraması üretilmesin,
- quaternion kaynaklı ve üç-nokta açı kaynaklı açısal hız birbirinden ayrı
  adlandırılsın.

### G. Bilateral simetri

SkeletonSpec üzerindeki semantic sol/sağ eşlemelerini sürümlü biçimde tanımla.

Seçilebilir özellikler:

- bilateral angle difference
- bilateral speed difference
- body-centered sagittal reflection sonrası paired-joint mirror distance
- sol/sağ hareket amplitude veya ROM farkı
- yeterli ve anlamlı veri varsa sequence-level phase-lag/cross-correlation
  özeti

Kurallar:

- Simetri kamera koordinatında doğrudan `left_xyz-right_xyz` olarak
  hesaplanmamalı; mümkünse body-centered/body-aligned uzay kullanılmalı.
- Signed ve absolute farklar birbirinden açık isimlerle ayrılmalı.
- Sonuçlar “asimetri teşhisi” olarak adlandırılmamalı.
- İlgili çift eksikse NaN ve mask üretilmeli.
- Pair adları ve sırası feature spec içinde bulunmalı.

### H. Seçilmiş mesafe ve oran proxy'leri

Tüm eklem çiftlerinin karesel kombinasyonunu üretme. Versioned, açıklanabilir
bir definition listesi kullan.

Uygun skeletonlarda örnek olarak:

- ankle/foot separation
- knee separation
- hip width
- shoulder width
- wrist separation
- knee-separation / hip-width ratio
- stance-width / hip-width ratio
- root–wrist ve root–ankle uzaklıkları
- trunk segment length ve limb-length temelli body-scale özetleri

Zemin yüksekliği veya foot contact gibi özellikler ancak doğrulanmış
world/floor calibration varsa üretilebilir. Kamera koordinatındaki `y=0`
değerini otomatik olarak zemin kabul etme.

“Center of mass” için doğrulanmış antropometrik model yoksa joint centroid'i
COM olarak adlandırma. Gerekirse `joint_centroid_proxy` gibi dürüst isim
kullan.

### I. Klasik ML için sabit uzunluklu özet vektörü

Derin modeller dışında Random Forest, SVM, XGBoost ve istatistiksel modellerin
kullanılabilmesi için seçilebilir, sabit uzunluklu bir
`summary_features [F] float32` çıktısı oluştur.

Feature isim ve sırası release seviyesinde tek bir sözleşmede saklanmalı.

Etiketlerden, participant kimliğinden veya train/test referanslarından bağımsız
özetler kullan:

- gerçek duration ve ölçülen FPS
- tracking/validity oranları
- body scale
- joint/angle ROM
- mean/std/median/IQR/min/max
- velocity/speed RMS ve peak
- path length
- angular velocity özetleri
- bilateral symmetry özetleri
- mevcutsa uncertainty özetleri

Bir örnekte hesaplanamayan eleman NaN kalmalı; farklı örneklerde vektör boyutu
değişmemeli.

Correct-reference template distance, sınıf ortalaması,
DTW-to-correct-template veya dataset genelinde fit edilen scaler gibi split
leakage yaratabilecek özellikleri export sırasında hesaplama.

## 4. Mapping ve feature semantiği

Joint mapping yalnız `joints_xyz` için tasarlanmış mevcut basit bir indeks
kopyası olarak kalmamalı; fakat her array'i de kör biçimde aynı indeksle taşıma.

Kurallar:

- Koordinat, confidence, mask, 2D point ve covariance gibi per-joint alanlar
  ancak semantik olarak güvenliyse mapping indeks vektörüyle taşınabilir.
- Local joint quaternionları hedef skeletonın parent zinciri farklıysa
  doğrudan remap edilmemeli.
- Feature tanımı mapping desteğini açıkça bildirmeli.
- Mapping sonrası geometrik feature'lar mümkün olduğunda hedef skeleton
  koordinatlarından yeniden hesaplanmalı.
- Native-only bir feature seçilen hedef formatla uyumsuzsa GUI bunu seçimden
  önce göstermeli.
- Kısmi mappingte gerekli joint eksikse yalnız ilgili feature sütunu/kemik NaN
  kalmalı; başka eklemler bozulmamalı.
- Eski 23/26 KineSynth mapping davranışı ve uyarıları korunmalı.

## 5. Export sözleşmesi

Mevcut `.npz` örnek yapısını genişlet. Tek bir belirsiz `[T,J,C]` tensoruna
bütün kanalları gizlice concat etme. Her feature ayrı, açık isimli array olarak
yazılsın.

Release'e `feature_spec.json` benzeri sürümlü bir belge ekle. Şunları içersin:

- seçilen feature ve presetler
- feature sürümleri
- tüm array sözleşmeleri
- sütun/angle/bone/pair/summary isimleri
- şekiller ve dtype'lar
- unit ve coordinate space
- timestamp/derivative politikası
- missing value ve validity-mask ilişkisi
- algoritma parametreleri
- feature availability istatistikleri
- mapping ve provenance
- clinical validation olmadığına dair açıklama

Manifestte:

- `array_contract` mevcut canonical raw sözleşmeyi korusun.
- Ayrı bir `feature_contract` bölümü oluşsun.
- Her sample için hangi feature'ların tamamen, kısmen veya hiç mevcut olmadığı
  raporlansın.
- Release genelinde seçilen array anahtarları bütün sample dosyalarında aynı
  olsun.
- Bir raw tracker özelliği eski kayıtta yoksa şekli belirlenebiliyorsa
  NaN/false ile tutarlı array üret ve availability oranını raporla.
- Seçilen bir özellik hiçbir örnekte üretilemiyorsa exportu sessizce başarılı
  sayma; kullanıcıya açık hata veya bloke edici doğrulama sonucu ver.
- Kısmi availability release validation warning'i oluştursun.
- Yeni release schema sürümlensin. Eski yayımlanmış release'ler değişmeden
  okunabilsin.

Dataset fingerprint:

- feature seçimi,
- feature sürümleri,
- parametreler,
- feature spec,
- mapping,
- label sözleşmesi,
- sample array içerikleri veya bunların checksumları

değiştiğinde değişmeli.

Yalnız feature seçeneğini manifestte hashlemek yeterli değil; gerçek yazılan
sample içeriği de fingerprint ile ilişkilendirilmeli. Export validation
sırasında sonradan eklenen checksumlar fingerprint dışında kalmamalı.

## 6. Export GUI

Export ekranına anlaşılır, ölçeklenebilir bir “Veri ve özellik seçimi” alanı
ekle. Çok sayıda checkbox'ı mevcut karta sıkıştırma; gerekirse aranabilir,
kaydırılabilir bir dialog veya tree kullan.

Kategoriler:

- Zorunlu canonical veri
- Kalite ve maskeler
- Tracker raw çıktıları
- Koordinat temsilleri
- Kemik/geometri
- Hız ve ivme
- Açılar ve açısal hareket
- Simetri ve oran proxy'leri
- Klasik ML özetleri
- Experimental

Her satırda:

- Türkçe ad
- kısa açıklama
- yaklaşık shape/unit
- destek durumu
- experimental işareti
- gerekiyorsa neden devre dışı olduğu

bulunsun.

Presetler ekle:

1. `Minimum canonical`
2. `KineSynth temel uyumluluk`
3. `Kinematik araştırma`
4. `Klasik ML`
5. `Desteklenen tüm araştırma özellikleri`

Preset yalnız checkbox seçimini değiştirsin; altta gerçek seçili feature ID'leri
ExportOptions'a yazılsın. “KineSynth temel uyumluluk” mevcut KineSynth
modelinin fiziksel velocity beklediği izlenimini vermesin.

GUI önizlemesinde:

- seçili feature sayısı
- oluşacak array anahtarları
- yaklaşık kanal/özet boyutu
- uygun olmayan kayıt/feature sayısı
- tahmini release boyutu, makul biçimde hesaplanabiliyorsa
- mapping kaynaklı kayıp ve eski kayıtlardaki raw alan eksikleri

gösterilsin.

Export worker thread ve cancellation davranışı korunmalı. Feature hesapları GUI
thread'inde yapılmamalı.

Son kullanılan feature seçiminin kullanıcı tercihine kaydedilmesi uygunsa
mevcut user-state altyapısını kullan; testlerin gerçek kullanıcı ayarına
yazmadığını koru.

## 7. Eksik veri politikası

Bu görev boyunca:

- NaN → sıfır dönüşümü yapma.
- Eksik joint üzerinden kemik çizme veya türev alma.
- Tracking gap üzerinden velocity/acceleration hesaplama.
- İlk velocity frame'ini “kişi duruyor” anlamına gelen sahte sıfırla doldurma.
- Bilinmeyen timestamp'i hedef FPS ile sessizce uydurma.
- Eksik toe/head-end joint üretme.
- Klinik isim taşıyan bir metriği yalnız geometrik benzerliğe dayanarak sunma.

Her feature mümkünse kendi validity maskesini üretmeli. Maskeyle NaN düzeni
validation'da karşılaştırılmalı.

## 8. Etiket modelinin sınırı ve geleceğe hazırlık

Mevcut iki seviyeli etiket modelini bu görevde bozma:

- hareket sample'ı
- correctness
- zamansal hata aralıkları

Eski tek `movement_phase`, `severity` ve `affected_joints` alanlarını sessizce
geri getirme.

Ancak uzun vadeli evidence decoder için ham feature'ların tek başına yeterli
olmadığını dokümante et. Aşağıdakiler gelecekte ayrı, uzman tanımlı bir
annotation genişletmesi olarak değerlidir:

- hata aralığı başına affected joints/body regions
- project-defined severity rubric
- annotator confidence
- tek enum yerine zamansal phase intervals veya phase boundaries

Bunlar ontology/rubric kararı olmadan bu görevde zorunlu etiket veya readiness
koşulu yapılmamalı. Feature/export mimarisi ileride bu hedef arraylerinin
eklenmesini engellememeli.

## 9. Testler

Donanım gerektirmeyen deterministik testler ekle.

En az şu durumları kapsa:

- Eski v1 BodyPose/JSONL kaydını yeni kodla okuma
- Yeni tüm optional raw alanların round-trip'ı
- `root_orientation` alanının artık kaybolmaması
- ZED adapter stub'ında doğrulanmış yeni alanların shape/dtype dönüşümü
- Yanlış şeklin uydurulmak yerine reddedilmesi veya unavailable olması
- Sabit hızlı sentetik hareket + düzensiz timestamp → doğru fiziksel velocity
- Aynı per-frame displacement fakat farklı FPS → aynı displacement, farklı
  doğru velocity
- Frame gap çevresinde derivative mask/NaN
- Sabit ivmeli hareket
- Bilinen 90° ve 180° joint angle
- Sıfır uzunluklu vektörde angle NaN
- `q`/`-q` quaternion dizisinin sahte angular-velocity sıçraması üretmemesi
- Bone vector/length sırası
- Tam simetrik sentetik skeleton'da sıfıra yakın symmetry feature
- Bilinçli asimetride non-zero sonuç
- Eksik bir joint'in yalnız bağımlı açı/kemik/summary elemanlarını geçersiz
  yapması
- Native ve mapped skeleton feature hizası
- Local orientation'ın güvenli olmayan mappingte devre dışı kalması
- Seçili feature'ların bütün `.npz` dosyalarında aynı anahtar sözleşmesine
  sahip olması
- Feature seçimi veya feature version değişince fingerprint değişmesi
- Sample array içeriği değişince fingerprint değişmesi
- Export validation'ın shape, dtype, units metadata, mask ve NaN tutarlılığını
  kontrol etmesi
- Cancellation/failure durumunda staging'in silinmesi ve release
  yayımlanmaması
- GUI preset, checkbox dependency, unavailable state ve gerçek painting
  testleri
- Default export seçeneklerinin mevcut davranışı bozmaması
- Eski kayıtların default ve zengin feature exportuyla çalışması
- Claude'un kendi değerlendirmesiyle eklediği her ilave feature/raw alan için
  en az bir pozitif ve bir eksik/geçersiz veri testi

Önce ilgili testleri, sonra tam paketi çalıştır:

```powershell
.\scripts\run_tests.ps1
conda run -n KineSynth python -m kinecapture --self-test
```

Mümkünse gerçek kamera açmadan SDK adapter alanlarını introspection/stub ile
doğrula. Gerçek ZED donanım smoke testi yaparsan tam komutu ve gerçek sonucu
yaz; yapmadıysan yapılmış gibi gösterme.

## 10. Dokümantasyon ve tamamlanma ölçütü

README'ye şu konuları ekle:

- canonical raw ile optional derived feature ayrımı
- GUI'den feature seçimi
- her array'in anlamı
- displacement ve physical velocity farkı
- missing-data/mask politikası
- feature spec ve fingerprint
- KineSynth mevcut model uyumluluğu
- klinik doğrulama sınırı
- bu promptta bulunmayıp Claude'un kendi araştırmasıyla eklediği alanlar ve
  gerekçeleri

`MEMORY.md` içinde:

- yeni schema sürümleri
- feature registry mimarisi
- raw ZED alanları
- matematik ve eksik veri kararları
- mapping davranışı
- test komutları ve gerçek sonuçları
- yapılmayan donanım doğrulamaları
- gelecekteki annotation önerileri
- bağımsız inceleme sonucunda eklenen veya bilinçli olarak eklenmeyen yeni
  feature fikirleri ve nedenleri

kaydedilsin.

Görev ancak şu koşullarda tamamlanmış sayılır:

1. Eski kayıtlar okunuyor.
2. Default export mevcut canonical davranışı koruyor.
3. GUI'den seçilen feature'lar gerçekten `.npz` içine giriyor.
4. Manifest ve feature spec yazılan dizileri eksiksiz açıklıyor.
5. Fiziksel velocity timestamp tabanlı ve gap-safe.
6. Açı, kemik ve simetri özellikleri skeleton spec'e bağlı ve sürümlü.
7. Eksik veri uydurulmuyor.
8. Fingerprint gerçek feature içeriğine duyarlı.
9. Export atomik ve iptal edilebilir.
10. Tam test paketi ve self-test çalıştırılmış; gerçek sonuçlar raporlanmış.
11. `MEMORY.md` güncellenmiş.
12. Prompt listesinin ötesinde yararlı veri/feature olup olmadığı bağımsız
    olarak araştırılmış; eklenenler ve reddedilenler gerekçelendirilmiş.

Son yanıtında kısa fakat somut olarak şunları raporla:

- değiştirilen ana dosyalar
- eklenen feature aileleri ve array anahtarları
- promptta açıkça bulunmayıp kendi araştırmanla eklediğin maddeler
- değerlendirdiğin fakat eklemediğin önemli fikirler ve nedenleri
- schema/migration kararı
- GUI'deki seçim deneyimi
- mapping ve eksik veri davranışı
- çalıştırılan testlerin gerçek sonuçları
- gerçek ZED testi yapılıp yapılmadığı
- bilinçli olarak sonraya bırakılan maddeler
