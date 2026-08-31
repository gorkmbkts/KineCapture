# Claude Code Görevi — Hata Aralığında Etkilenen Eklem Kanıtı ve GUI İyileştirmeleri

KineCapture Studio'nun güncel sürümünde aşağıdaki ana özelliği ve küçük GUI
düzeltmelerini gerçek koda uygula. Bu görevi yalnız analiz, öneri, prototip veya
plan olarak bırakma: veri sözleşmesini, arayüzü, repository işlemlerini, export
çıktısını, geriye uyumluluğu ve testleri birlikte tamamla. Görev sonunda
`MEMORY.md` dosyasını yalnız gerçekten uygulanan ve doğrulanan sonuçlarla
güncelle.

Ana özellik, temporal olarak etiketlenmiş bir hata aralığına o hatadan etkilenen
bir veya birden fazla anatomik eklemin bağlanmasıdır. Bu etiketin amacı kullanıcıya
ayrı bir “eklem sınıflandırıcısı” sunmak değildir. Etiket, gelecekteki temporal
graph modelinde hatayla ilişkili düğümlerin açık denetim sinyali olarak
kullanılabilmeli; modelin hangi node'lardaki hareket örüntülerinden yararlanması
gerektiğini öğrenmesini desteklemelidir. Bu nedenle yalnız GUI'de eklem adını
kaydetmek yeterli değildir: aralık, hata sınıfı, anatomik rol ve native skeleton
node ilişkisi exportta kayıpsız ve doğrudan eğitilebilir biçimde korunmalıdır.

Bu prompttaki ürün ve veri anlamı kararları eski promptlarla veya mevcut kodun
eksik davranışıyla çelişirse bu prompt üstündür. Bununla birlikte mevcut güvenlik,
ham veri değişmezliği ve geriye uyumluluk ilkelerini bozma.

## 1. Başlangıç ve değişmez çalışma kuralları

1. Önce repository kökündeki `CLAUDE.md` ve `MEMORY.md` dosyalarının tamamını
   oku. Ardından gerçek kodu, testleri, sürümleri ve çalışma ağacını incele.
   Hafıza ile kod çelişirse gerçek davranışı doğrula, çelişkiyi görünür kıl ve
   görev sonunda hafızaya gerçek sonucu yaz.
2. Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
   oluşturma; bilimsel ortamın paketlerini gereksiz yere kurma, kaldırma veya
   yükseltme.
3. Kullanıcının ve başka araçların çalışma ağacındaki değişikliklerini koru.
   İlgisiz dosyaları geri alma, silme veya üzerlerine yazma. Görev kapsamındaki
   dosyaları değiştirirken mevcut değişikliklerle dikkatli biçimde birleş.
4. Ham kaydı değiştirme. Annotation sidecar ayrımını, atomik yazımı, undo/redo
   ve autosave davranışını, yarım kayıt kurtarmayı, güvenli kapanışı, mock
   backend'i, Windows uzun yol desteğini ve mevcut veri kaybı önlemlerini koru.
5. Kod ve kalıcı alan adları İngilizce; kullanıcıya görünen yeni metinler doğal
   Türkçe olsun. Emoji kullanma. Durumu yalnız renkle anlatma; yazı, şekil,
   erişilebilir ad ve focus durumu da sağla.
6. Sabit ekran koordinatları, yalnız tek çözünürlükte çalışan piksel hileleri
   veya minimum pencere boyutunu büyütme yoluyla GUI kusurlarını gizleme.
   Mevcut responsive layout, scroll ve size-policy yaklaşımıyla uyumlu çöz.
7. Yeni veri anlamı şema değişikliği gerektiriyorsa doğru semver/sürüm artışını,
   migration/normalization davranışını ve geriye uyumluluğu uygula. Sürümleri
   yalnız belgede değil gerçek sabitlerde, manifestlerde ve testlerde tutarlı
   değiştir.
8. Tasarım ve Qt bileşimi konusunda aşağıdaki davranış sınırları içinde karar
   vermekte özgürsün. Mevcut mimariyi inceleyip en sade, bakımı kolay ve
   test edilebilir çözümü seç; sırf bu promptta örnek verildi diye gereksiz bir
   sınıf, dosya veya veri kopyası oluşturma.

## 2. Kodda doğrulanmış başlangıç durumu

Değişiklikten önce aşağıdaki bulguları gerçek kodda yeniden doğrula. Bunlar bu
prompt hazırlanırken mevcut repository üzerinde görülmüştür:

- Uygulama/package sürümü `0.9.0`; annotation schema `2.1.0`, release schema
  `2.1.0`, label schema `2.0.0`, project schema `1.1.0`, session schema `2.0.0`,
  take schema `1.1.0`, skeleton stream schema `1.1.0`, feature spec `1.0.0`, raw
  archive `1.0.0` ve identity SQLite schema `1` durumundadır.
- `ErrorInterval` şu anda hata sınıfı, frame/timestamp sınırları, note, source ve
  audit zamanlarını taşır; güncel, tipli bir etkilenen-eklem alanı yoktur.
  Eski dosyalardaki `affected_joints` değeri güncel alan sayılmayıp `legacy`
  altında kayıpsız tutulmaktadır.
- Hata düzenleme dialogu hata sınıfı ile notu düzenler ve aralık oynatma/silme
  eylemleri sunar; skeleton üzerinde eklem seçimi yoktur.
- Review sayfası dialog sonucu için sınıfı ve notu ayrı repository çağrılarıyla
  kaydeder. Bu, yeni eklem alanları eklenirse tek kullanıcı eyleminin birden
  fazla snapshot/autosave adımına bölünme riski yaratır.
- Her açılmış take kendi `LoadedTake.spec` / `SkeletonSpec` bilgisini taşır.
  BODY_18, BODY_34, BODY_38 ve mock topolojileri gerçek kaydın metadata'sından
  çözülebilir. Eklem seçici, uygulamanın o anki capture ayarını değil düzenlenen
  take'in gerçek spec'ini kullanmalıdır.
- `features/roles.py` içinde pelvis, spine/chest/neck/head ile sağ/sol omuz,
  dirsek, el bileği, el, kalça, diz, ayak bileği, ayak ve topuk gibi semantik
  anatomik rollerin farklı skeleton topolojilerine eşlemesi zaten vardır.
  Yeni özellik aynı anlamın ikinci ve çelişebilen bir kopyasını üretmemelidir.
- Canonical export temporal hata aralıklarını ve frame düzeyindeki hata
  multi-hot hedeflerini üretir; interval-eklem ilişkisi ve bunun label maskesi
  henüz yoktur.
- Güvenli proje silme servisi gerçek proje klasörünün doğrulanmasını ister.
  Kayıtlı klasör artık diskte yoksa `delete_target_missing` / “Proje klasörü
  bulunamadı; silinecek bir şey yok.” sonucu verir. Projects sayfası bu durumda
  listede kalan identity kaydını temizleyemediği için kullanıcı projeyi GUI'den
  kaldıramaz.
- `IdentityService.forget_project(...)`, proje identity/access kayıtlarını audit
  izini koruyarak kaldırabilecek düşük seviyeli davranışa sahiptir; fakat eksik
  klasör için güvenli, açık ve owner-only bir GUI akışı değildir.
- Navigation rail açıkken Yıldız Teknik Üniversitesi logosu altta görünür;
  `Daralt` kontrolünün görünür içeriği logoya göre sola kaymış ve logo ile
  kontrol arasında yeterli dikey boşluk yoktur.
- Paketlenmiş logo kaynağı
  `src/kinecapture/gui/assets/yildiz_technical_university_logo.png` altında
  mevcuttur ve mevcut asset loader üzerinden kullanılabilir. Aynı logonun yeni
  bir kopyasını veya çalışma dizinine bağlı dosya yolu oluşturma.
- `AuthPage` işlevsel giriş/ilk kurulum/kayıt/şifre akışlarına sahiptir fakat
  açılış görünümü temel seviyededir ve YTÜ logosunu göstermez.
- Production GUI launcher `MainWindow` oluşturup normal `show()` çağırır;
  pencere constructor'ı başlangıç boyutu verir. Uygulama varsayılan olarak
  işletim sistemi seviyesinde maximized açılmaz.

İlgili kodla sınırlı kalmamak şartıyla en az şu alanları incele:

- `src/kinecapture/domain/project.py`
- `src/kinecapture/annotations/repository.py`
- `src/kinecapture/gui/widgets/label_dialogs.py`
- `src/kinecapture/gui/pages/review.py`
- `src/kinecapture/playback/take_reader.py`
- `src/kinecapture/visualization/skeleton_spec.py`
- `src/kinecapture/features/roles.py`
- canonical export/release/validator/fingerprint kodu ve testleri
- `src/kinecapture/dataset/deletion.py`
- `src/kinecapture/identity/service.py` ve identity repository/audit kodu
- `src/kinecapture/gui/pages/projects.py`
- `src/kinecapture/gui/main_window.py`
- `src/kinecapture/gui/auth.py`
- `src/kinecapture/app.py`
- ilgili tüm unit, integration, GUI paint/geometry ve packaging testleri

## 3. Ana özellik: hata aralığında etkilenen anatomik eklemleri etiketleme

### 3.1. Ürün anlamı ve model hedefi

Bir hata intervali aşağıdaki bilgileri tek bir ilişkili annotation olarak
taşıyabilmelidir:

- temporal başlangıç ve bitiş,
- hata sınıfı,
- etkilenen sıfırdan fazla canonical anatomik rol,
- eklem annotation durumunun neden boş olduğunu ayıran açık durum,
- isteğe bağlı not ve mevcut provenance/audit alanları.

Etkilenen eklem etiketi gelecekte aşağıdaki gibi bir graph-temporal modelde
node-level evidence/relevance supervision olarak kullanılacaktır:

- model girdisi native skeleton düğümlerini koruyan `[T, J, F]` benzeri bir
  tensördür,
- graph encoder düğüm boyutunu hemen yok etmeyip `[T, J, D]` benzeri bir
  temsil üretir,
- temporal hata tahmini `[T, C]` ile birlikte açık node evidence/relevance
  çıktısı `[T, C, J]` veya eşdeğer bir rol-uzayı temsili üretilebilir,
- etiketlenen node relevance/gating bilgisi hata başlığını gerçekten
  besleyebilir; yalnız görselleştirilen ama loss veya karar yoluna bağlanmayan
  dekoratif attention olmamalıdır,
- seçilmeyen diğer skeleton düğümleri model girdisinden atılmaz. Model bütün
  native topolojiyi görmeye ve komşu/kinematik bağlamdan yararlanmaya devam eder.

Bu görevde KineCapture içine eğitim modeli veya inference ağı ekleme. Ancak
annotation ve export sözleşmesi yukarıdaki modeli sonradan ek bilgi tahmini
yapmadan eğitebilecek kadar açık olmalıdır. Rastgele Transformer attention
ağırlıklarını doğrudan ground truth kabul etme; açık node evidence/relevance
hedefi ve maskesi üret.

Örnek anlam:

- hata sınıfı: `knee_valgus`
- interval: frame 120–168, sınırlar inclusive
- seçilen anatomik rol: `left_knee`
- take topolojisi: BODY_34

Export, frame 120–168 boyunca ilgili hata sınıfı ile `left_knee` rolünün BODY_34
native node eşlemesini birlikte ifade edebilmelidir. Böylece loader gerekirse
`Y_joint[t, c, j] = 1` ve buna karşılık gelen supervision maskesini deterministik
biçimde kurabilir. Frame, hata sınıfı veya node eşlemesinden biri kaybolmamalıdır.

### 3.2. Topolojiden bağımsız anatomik roller

Kalıcı annotation içine numeric joint index, yalnız BODY_34'e özgü tracker adı
veya `left_big_toe` gibi model-topolojisine bağımlı bir değer yazma. Kullanıcı
seçimini `left_knee`, `right_shoulder`, `pelvis`, `spine_mid`, `chest`, `neck`
gibi kararlı canonical anatomik rollerle sakla.

Kurallar:

1. BODY_18/BODY_34/BODY_38 arasında mümkün olduğunca aynı rol sözlüğü kullan.
   Capture formatı değişse de annotation hedeflerinin anlamı değişmesin.
2. Role-to-native-node eşlemesini tek otoritatif kaynaktan üret. Mevcut
   `features/roles.py` bilgisini uygun, bağımlılık açısından nötr bir yere
   taşımak/refactor etmek gerekirse yap; fakat GUI, export ve feature katmanında
   birbirinden kopuk üç eşleme tablosu oluşturma.
3. “Omurga/gövde” gibi hangi node'u ifade ettiği belirsiz birleşik kalıcı roller
   kullanma. Pelvis, spine_mid, chest ve neck gibi anlamı açık roller tercih et.
   Bir rol gerçekten birden fazla native node'a karşılık geliyorsa bunu spec'te
   açık ve deterministik bir group mapping olarak tanımla.
4. Native topolojinin yüz, parmak, göz, kulak veya yardımcı tracker noktaları
   skeleton bağlamında görünmeye devam edebilir, fakat ilk sürümde her native
   noktayı kullanıcıya seçilebilir hedef yapmak zorunlu değildir. Seçilebilir
   hedefler semantik ve antrenörün anlayabileceği anatomik roller olmalıdır.
5. Full model exporttaki bütün native node'ları almaya devam etsin. GUI'de bir
   tracker noktasının seçilememesi `joints_xyz` veya eşdeğer özelliklerden o
   node'un silinmesi anlamına gelmez.
6. Sol/sağ anlamı sporcunun anatomik sol/sağıdır. Önden görünümün aynalama
   etkisi nedeniyle GUI bunu “Sporcunun solu” ve “Sporcunun sağı” olarak açıkça
   belirtmeli; izleyicinin sol/sağıyla karıştırılmamalıdır.

### 3.3. Boş değer anlamı ve geriye uyumluluk

Boş listeyi tek başına kullanma; “henüz etiketlenmedi”, “belirli bir eklem yok”
ve “görüntüden belirlenemiyor” aynı şey değildir. En az şu anlamları kalıcı ve
export edilebilir biçimde ayır:

- `selected`: bir veya daha fazla canonical rol seçildi,
- `not_applicable`: bu hata için belirli bir eklem hedefi yok,
- `indeterminate`: görüntüden güvenilir biçimde belirlenemiyor,
- `unreviewed`: eski veri veya henüz eklem yönünden incelenmemiş interval.

Alan adlarının exact biçimini mevcut schema stiliyle uyumlu seçebilirsin; fakat
bu dört anlam kaybolmamalıdır. Yeni veya yeniden düzenlenen bir hata aralığı
kaydedilirken hata sınıfına ek olarak ya en az bir rol seçilmeli ya da kullanıcı
iki açık istisna durumundan birini seçmelidir. Eski interval açıldığı için
kullanıcı veri kaybetmeye veya migration kararı vermeye zorlanmamalıdır.

Önemli correctness kararı: eklem annotation'ının eksik olması hareketin
doğru/hatalı türetmesini değiştirmez. Sınıflandırılmış bir hata intervali,
eklemi `unreviewed` olsa bile hareketi hatalı yapmaya devam eder. Böyle eski
örnekler temporal hata sınıfı eğitiminde kullanılabilir; yalnız node evidence
loss'u maskelenir. Eksik joint etiketi nedeniyle tüm take'i veya tüm hata
intervalini genel eğitimden atma.

Eski dosyalar rewrite gerektirmeden açılmalıdır. `legacy.affected_joints` içeriği
kayıpsız kalmalıdır. Yalnız eşleme gerçekten tek anlamlı, doğrulanabilir ve
idempotent ise canonical alana otomatik normalize/migrate et; belirsiz değerleri
tahmin etme. Belirsiz legacy veri korunmalı ve yeni alan `unreviewed` kalmalıdır.

### 3.4. Antrenör odaklı hata dialogu

Hata intervali oluşturulduğunda veya düzenlendiğinde açılan mevcut mini pencereyi
şu ürün deneyimine genişlet:

- Hata sınıfı, temporal aralık, not ve eklem seçimi aynı görev bağlamında olsun.
- Düzenlenen take'in kendi BODY_18/BODY_34/BODY_38 topolojisinin tamamını sabit,
  anlaşılır bir önden görünümle göster. Mock spec'i testlerde destekle.
- Tam skeleton görsel bağlam olarak görünürken yalnız kararlı canonical anatomik
  hedefler yeterince büyük ve kolay tıklanabilir olsun. Yardımcı tracker noktaları
  daha geri planda ve seçilemez gösterilebilir.
- Birden fazla eklem seçilebilsin. Aynı node'a tekrar tıklama seçimi kaldırabilsin.
- Seçilen roller skeleton üzerinde belirginleşsin ve ayrıca okunabilir adlarla
  listelensin/chip benzeri kaldırılabilir bir özet sunsun. Çözüm yalnız renge
  dayanmasın.
- Hover/focus durumu, klavye erişimi, açıklayıcı accessible name ve yeterli hit
  area sağla. Küçük node çizimine tam isabet zorunluluğu antrenör için uygun
  değildir.
- Sporcunun sağ/sol tarafını görünür biçimde anlat. Ön görünümde izleyici
  perspektifi yüzünden yanlış taraf seçimini azalt.
- `Belirli eklem yok` ve `Görüntüden belirlenemiyor` seçeneklerini node
  seçiminden ayrı, anlaşılır ve birbirini dışlayan durumlar olarak sun.
- Validation hatasını dialog kapanmadan, kullanıcının ne yapması gerektiğini
  açıkça söyleyerek göster.
- Kaydedilmiş bir interval yeniden açıldığında sınıf, not, durum ve çoklu eklem
  seçimi eksiksiz geri yüklensin.
- Mevcut “Aralığı oynat” eylemini antrenör seçim yaparken aralığı tekrar izlemek
  için kullanılabilir hale getir. Oynatma istemeden dialogu kaydedip kapatmamalı
  veya yarım seçimi commit etmemelidir. Uygun Qt tasarımını mevcut review/player
  mimarisine göre sen belirle.

Önerilen görsel yön tam karşıdan görünen sade bir anatomik skeleton seçicidir;
ancak exact çizim teknolojisini, widget kompozisyonunu, dialog kolonlarını,
ölçüleri ve mikro etkileşimi mevcut uygulama tasarımına göre sen seç. Canlı,
döndürülebilir 3D viewport'u küçük bir alana sıkıştırmak zorunda değilsin. Sonuç
antrenörün birkaç saniyede anlayıp güvenle kullanabileceği kadar yalın olmalıdır.

Dialog ve review akışı en az 1120x700, 1366x768 ve 1600x980 viewportlarda;
dark/light temada; uzun Türkçe metinlerde; BODY_18/BODY_34/BODY_38 için clipping,
örtüşme veya erişilemez kontrol oluşturmadan çalışmalıdır. Gerekirse scroll veya
responsive yeniden akış kullan; minimum ana pencere boyutunu büyütme.

### 3.5. Tek atomik annotation işlemi

Hata sınıfı, eklem annotation durumu, seçilen roller ve not, kullanıcının tek
“Kaydet” eylemi olarak repository'ye yazılmalıdır. Ayrı ayrı snapshot/autosave
üreten çağrılarla kısmi commit bırakma. Domain validation ve repository
mutasyonu tek mantıksal işlem, tek undo adımı ve tek change/autosave bildirimi
oluştursun. Sınır değişikliklerinin mevcut önizleme/commit davranışını bozma.

Silme, undo/redo, autosave, reload, recovery ve sidecar round-trip testlerinde
yeni alanların tamamını doğrula. Invalid role, mevcut skeleton spec'inde
eşlenemeyen role, durum/rol çelişkisi ve yinelenen roller için deterministik
validation/normalization davranışı tanımla.

### 3.6. Dataset ve timeline görünürlüğü

Timeline'a yeni ve sürekli yer kaplayan bir lane ekleme. Mevcut hata aralığının
temporal görünümünü koru. Seçili intervalin tooltip/özet/status alanında etkilenen
eklemler ve annotation durumu kısa biçimde gösterilebilir.

Dataset/readiness görünümünde joint annotation kapsamı denetlenebilir olmalıdır:

- seçilmiş eklem bulunan hata intervali sayısı,
- `not_applicable` / `indeterminate` sayıları,
- `unreviewed` veya node supervision için eksik interval sayısı,
- mümkünse eksik eklem etiketi filtresi/iş listesi.

Bu metrikleri genel temporal hata etiketi hazırlığıyla karıştırma. Örneğin joint
etiketi eksik bir take temporal error training için hazır olabilir, fakat node
evidence supervision kapsamı eksik görünmelidir.

### 3.7. Canonical export ve doğrudan eğitilebilir sözleşme

Canonical manifest ve array exportunda aşağıdaki semantik bilgileri kayıpsız
taşı:

1. Her error intervalinin canonical role listesi ve joint annotation durumu.
2. Export edilen take'in skeleton formatı ile role-to-native-node mapping'i;
   mapping sürümü/provenance bilgisi ve deterministik sıralama.
3. Overlap eden farklı hata sınıfları ve aynı sınıftaki interval örnekleri
   birbirinden kopmadan class-time-role ilişkisini korusun.
4. Çoklu eklem seçimi kaybolmasın.
5. `unreviewed` ve `indeterminate/not_applicable` değerleri loss maskesinde
   doğru anlama gelsin; bilmediğimiz node'ları negatif ground truth yapma.
6. Canonical loader'ın doğrudan kullanabileceği target ile supervision maskesi
   üret veya manifestten bunları deterministik ve dokümante edilmiş biçimde
   oluşturmasını sağla.

Mevcut export mimarisine göre exact minimal şekli sen seç. Örneğin interval
uzayında `error_interval_joint_multi_hot [K,R]` ve
`error_interval_joint_label_mask [K]`, ya da frame/class/native-node uzayında
`error_joint_target [T,C,J]` ile `error_joint_label_mask [T,C]` benzeri yapılar
uygun olabilir. Bunlar isim ve şekil dayatması değil, gerekli semantiğin
örnekleridir. Seçtiğin sözleşme self-describing, deterministic, validate
edilebilir, verimli ve downstream eğitim kodunda tahmine ihtiyaç bırakmayacak
kadar açık olsun.

Canonical validator şu hataları yakalasın: bilinmeyen canonical rol, eksik veya
çelişkili status, mapping dışında node, boyut/dtype uyuşmazlığı, interval ile
dense hedef uyuşmazlığı, geçersiz label maskesi ve manifest/array fingerprint
uyuşmazlığı. Yeni annotation alanı release fingerprintini etkilesin; eklem
etiketi değiştiğinde eski release yanlış biçimde cache hit almamalıdır.

## 4. Yetim proje kaydını güvenle listeden kaldırma

Ekran görüntüsündeki sorun: Projects sayfasında proje listeleniyor, ancak kayıtlı
proje klasörü artık bulunamadığı için `Projeyi sil` işlemi “Proje klasörü
bulunamadı; silinecek bir şey yok.” uyarısıyla bitiyor. Kullanıcı bu projeyi
uygulamadan kaldıramadığı için kayıt GUI'de kalıyor.

Mevcut normal proje silme güvenliğini gevşetme. Bunun yerine yalnız doğrulanmış
eksik klasör için ayrı anlam taşıyan bir “yetim proje kaydını kaldırma” akışı
oluştur:

1. Bu eylem yalnız system owner tarafından kullanılabilsin; normal kullanıcıya
   proje silme veya identity kaydı kaldırma yetkisi verme.
2. Yalnız kaydedilmiş canonical hedefin gerçekten bulunmadığı doğrulanan
   `delete_target_missing` benzeri durumda kullanılabilsin. Hedef mevcut fakat
   manifest okunamıyor, proje ID'si uyuşmuyor, hedef symlink/junction, izin/IO
   hatası var veya güvenlik doğrulaması başarısızsa bunu “yetim kayıt” sayıp
   identity kaydını otomatik kaldırma.
3. Kullanıcıya proje adı, proje kimliği ve kayıtlı tam yol gösterilen güçlü bir
   onay sun. Klasör bulunamadığı için hiçbir dosyanın/disk verisinin
   silinmeyeceğini, yalnız uygulamadaki eski kayıt ve erişim bağlantılarının
   kaldırılacağını açıkça söyle. Mevcut güçlü onay yaklaşımıyla uyumlu olarak
   proje adını yazdır veya eşdeğer güvenli doğrulama kullan.
4. Onaydan sonra stale `projects` ve `project_access` kayıtlarını transaction
   içinde temizle; audit izini kaybetme. Normal fiziksel silmeden ayırt edilebilen
   audit olayı/metadata kullan. Audit kaydı proje adı, ID, eski yol, actor ve
   “disk hedefi bulunamadı” nedenini sonradan denetlenebilir biçimde korusun.
5. Active/last/recent project referansları bu project ID'yi tutuyorsa güvenli
   biçimde temizle. Projects listesi ve özet paneli anında yenilensin; kaldırılan
   kayıt uygulama yeniden başlatıldığında geri gelmesin.
6. Bu akışta recursive filesystem delete çağırma; çünkü doğrulanmış bir klasör
   yoktur. Başka bir benzer isimli klasörü arayıp silmeye çalışma.

Bunun aynı `Projeyi sil` butonunun missing-target durumunda güvenli bir ikinci
diyaloğa dönüşmesi mi, yoksa açıkça `Listeden kaldır` adını taşıyan ayrı bir
eylem mi olacağına mevcut kullanıcı akışını inceleyerek karar verebilirsin.
Ancak kullanıcı için “dosyaları kalıcı silme” ile “bulunamayan projenin eski
kaydını listeden kaldırma” farkı tamamen açık olmalıdır.

Testlerde yalnız temporary klasörler ve temporary identity DB kullan. Gerçek
kullanıcı projesine veya repository dışındaki verilere dokunma. En az şu
durumları test et:

- klasörü sonradan silinmiş kayıt owner onayıyla listeden kaldırılır,
- project/access kayıtları gider, audit izi ve kimlik metadata'sı korunur,
- GUI listesi ve seçili proje durumu yenilenir,
- owner olmayan kullanıcı yapamaz,
- iptal hiçbir şeyi değiştirmez,
- permission/IO, manifest uyuşmazlığı, symlink/junction ve mevcut güvenlik
  guard'ları yetim-kayıt yoluna düşmez,
- mevcut normal proje klasörü silme akışı ve testleri aynen güvenli çalışır.

## 5. Navigation rail: logo ve `Daralt` kontrolü

Yıldız Teknik Üniversitesi logosunun altındaki `Daralt` kontrolünü görsel olarak
düzelt:

- Expanded navigation durumunda kontrolün ikon + `Daralt` metninden oluşan
  görünür kompozisyonu logoya ve rail'e göre yatayda ortalanmış görünsün. Yalnız
  button rect'inin ortada olması yeterli değildir; kullanıcıya görünen içerik
  sola yığılmamalıdır.
- Logoyu bir miktar yukarı al ve logo ile kontrol arasında bilinçli, küçük ama
  net bir dikey boşluk bırak. İkisi üst üste, birbirine değiyor veya rastgele
  büyük boşlukla kopmuş görünmesin.
- Expanded/collapsed geçişi, logo görünürlüğü, ikon keskinliği ve mevcut navigation
  davranışı bozulmasın. Collapsed durumda gereksiz boş logo alanı kalmasın.
- 700 px yükseklikte son navigation öğeleri, logo ve toggle erişilebilir kalsın;
  overlap veya clipping olmasın. Dark/light temada ve yüksek DPI'da doğrula.

Exact margin, spacing, alignment ve widget bileşimini tasarım gözüne ve mevcut
style sistemine göre belirle. Sabit bir piksel değeri dayatmıyorum; amaç ekrandaki
asimetrik görüntüyü düzeltmek ve kurumsal bloğu dengeli göstermektir.

Görsel referans hazırlanırken görülen ekran görüntüsü:
`C:\Users\gorke\AppData\Local\Temp\codex-clipboard-b69a4436-612c-489d-b1f0-64e3bcbae912.png`.
Dosya erişilemiyorsa yukarıdaki davranış açıklaması otoritatiftir.

## 6. Açılış/giriş ekranının görsel iyileştirilmesi

Auth açılış ekranında paketlenmiş Yıldız Teknik Üniversitesi logosunu kullan ve
ekranı daha özenli, modern ve kurumsal görünecek şekilde yeniden düzenle.

Davranış sınırları:

1. Logo mevcut package asset loader üzerinden gelsin; CWD veya geliştirici
   makinesine özel absolute path'e bağlı olmasın. Aspect ratio ve transparanlığı
   korunsun, bozulmasın ve gereğinden büyük kullanılmasın. Asset yüklenemezse
   ekran çökmemeli.
2. İlk kurulum, normal login, kullanıcı kayıt akışı ve zorunlu şifre değiştirme
   davranışları aynı polished auth shell içinde tutarlı görünsün.
3. Bilgi hiyerarşisini, spacing'i, kart/zemin ilişkisini, başlık ve yardımcı
   metinleri, input focus/hover/error durumlarını ve ana eylemi iyileştir. Exact
   estetik yaklaşım, renk kullanımı ve layout kompozisyonunda özgürsün; mevcut
   KineCapture temasına ve kurumsal kimliğe uyumlu, sade ve profesyonel olsun.
4. Güvenlik veya yetkilendirme davranışını değiştirme. Yeni auth alanları,
   farklı parola kuralları veya gereksiz bir onboarding akışı icat etme.
5. Klavye tab sırası, Enter ile giriş, parola göster/gizle, hata metinleri,
   accessible name'ler ve dark/light tema korunup iyileştirilsin.
6. 1120x700 minimum viewport, 1366x768 ve maximized büyük ekranlarda dengeli
   görünmeli; küçük yükseklikte buton veya validation metni erişilemez kalmamalı.

Tasarımı özgürce iyileştirebilirsin, ancak sonuç yalnız logonun mevcut karta
eklenmesi kadar yüzeysel kalmamalı ve işlevsel auth ekranından bambaşka bir
dashboard/landing page'e de dönüşmemelidir.

## 7. Uygulamayı varsayılan olarak maximized açma

Production başlangıç akışında ana pencere ilk gösterildiğinde işletim sisteminin
gerçek maximized window durumuyla açılsın. Ekran boyutunu okuyup pencereyi sahte
biçimde o ölçülere `resize` etme. Normal Qt maximized davranışını veya platforma
uygun eşdeğerini kullan.

Bu karar production launcher için varsayılandır. `MainWindow` constructor'ını
offscreen/GUI testlerinde kontrol edilemez hale getirme; testlerin pencereyi
istenen viewportlara resize edip paint/geometry doğrulaması yapabilmesi sürsün.
Windows görev çubuğu, çoklu monitör ve OS work-area davranışına müdahale etme.
Maximize desteklenmeyen bir test/platform durumunda uygulama yine kullanılabilir
bir minimum boyutta açılabilmelidir.

## 8. Test ve görsel doğrulama beklentileri

Yalnız yeni happy-path unit testleriyle yetinme. Mevcut test stilini kullanarak
en az şu kapsamı ekle veya genişlet:

### Domain/repository/geriye uyumluluk

- multi-joint seçimin JSON round-trip'i,
- dört joint annotation durumunun validation ve normalization'ı,
- class + status + role listesi + note'un tek snapshot/undo/autosave işlemi,
- eski annotation dosyasının rewrite olmadan açılması,
- belirsiz `legacy.affected_joints` değerinin kayıpsız korunması,
- joint etiketi eksik olsa da derived correctness'in hata intervalinden aynı
  biçimde türemesi,
- undo/redo, silme, reload ve recovery davranışı.

### GUI

- BODY_18, BODY_34, BODY_38 ve mock spec ile skeleton seçicinin doğru role
  bağlanması,
- bir/çok node seçme, seçimi kaldırma, explicit boş durumlar ve edit reload,
- sporcunun sağ/sol eşleşmesinin doğru olması,
- save validation; oynatma isteğinin istemeden save/close üretmemesi,
- dialog ve auth ekranının 1120x700, 1366x768, 1600x980 boyutlarında dark/light
  paint + geometry doğrulaması,
- navigation logo/toggle merkezleme ve boşluğunun expanded/collapsed durumda
  clipping/overlap oluşturmaması,
- production başlangıcının maximized state istemesi; test pencerelerinin yine
  resize edilebilir olması,
- keyboard/focus/accessibility açısından kritik kontroller.

GUI testleri yalnız “pixmap oluştu” kontrolüyle bitmesin. Child geometry,
clipping, overlap, görünürlük, erişilebilir kontrol ve makul görsel merkezleme
assert'leri ekle. Mümkünse gerçekçi uzun Türkçe etiketler ve dolu veriyle render
al; tasarım kusuru görülürse düzeltip tekrar render et.

### Export/model-readiness

- interval/class/role association round-trip'i,
- overlap eden interval ve çoklu eklem,
- topolojiye göre deterministik role-to-native-node mapping,
- `unreviewed` için maskelenmiş node supervision; bunu yanlış negatif saymama,
- `not_applicable` ve `indeterminate` anlamının belgelenmiş/validate edilen
  karşılığı,
- target/mask shape, dtype, inclusive sınırlar ve padding davranışı,
- export determinism ve release fingerprint sensitivity,
- validator'ın bozuk mapping/role/mask/array/manifest durumlarını reddetmesi,
- downstream loader'ın ilave tahmin yapmadan node evidence target oluşturması.

### Yetim proje kaydı

4. bölümdeki owner-only, audit, cancellation ve security guard testlerinin
tamamı; ayrıca mevcut fiziksel proje silme testlerinin regresyonsuz geçmesi.

İlgili hızlı testleri geliştirirken çalıştır; sonunda uygun bütün test paketini
mevcut `KineSynth` environment'ında çalıştır. Uygulamanın mevcut self-test'i,
packaging/resource testi ve Windows'a özgü guard/plugin testleri varsa bunları da
çalıştır. Çalıştırmadığın veya ortam yüzünden doğrulayamadığın hiçbir testi
geçmiş gibi yazma.

## 9. Dokümantasyon, sürümleme ve tamamlanma raporu

1. Yeni joint annotation alanını, canonical rol sözlüğünü, dört durumun
   anlamını, topology mapping sözleşmesini, export target/mask semantiğini,
   inclusive interval sınırlarını ve geriye uyumluluğu ilgili schema/export
   dokümantasyonunda açıkla.
2. Bunun bir “joint classifier ürünü” olmadığını; gelecekteki temporal error
   modeline node evidence/relevance supervision sağladığını belirt. Modelin tüm
   native node girdilerini koruduğunu belgeye yaz.
3. Yetim proje kaydı kaldırma ile gerçek proje klasörü silme arasındaki güvenlik
   farkını kullanıcı/teknik dokümantasyonda gereken yerde açıkla.
4. Package asset'in wheel/sdist içine girdiğini test et. Yeni logo kopyası
   üretme.
5. Schema/package sürümlerini değiştirmen gerekiyorsa bütün otoritatif kaynakları
   tutarlı güncelle ve eski örneklerle geriye uyumluluk testini ekle.
6. Görev sonunda `MEMORY.md` içine yalnız kalıcı kararları, gerçek schema/app
   sürümlerini, gerçekten çalıştırılan test komutlarını ve sonuçlarını,
   çalıştırılmayan/doğrulanamayanları yaz.
7. Son raporda şu ayrımı açıkça ver:
   - uygulanan ana veri/GUI davranışı,
   - exportun node-level model supervision için sunduğu sözleşme,
   - yetim proje kaydı güvenlik davranışı,
   - auth/navigation/maximized GUI sonuçları,
   - değişen sürümler,
   - çalıştırılan testler ve sayıları,
   - halen bilinçli olarak kapsam dışında bırakılanlar.

## 10. Tamamlanma kabul kriterleri

Görev ancak aşağıdakilerin tamamı gerçek kod ve testlerle sağlandığında
tamamlanmış sayılır:

- Antrenör bir hata aralığında hata sınıfını ve birden fazla etkilenen anatomik
  rolü kolayca seçebilir; explicit `not_applicable` ve `indeterminate` durumları
  vardır.
- Dialog düzenlenen take'in gerçek skeleton spec'ini önden gösterir; sporcunun
  sağ/solu açıktır; BODY_18/BODY_34/BODY_38 annotation semantiği aynı canonical
  rol uzayında kalır.
- Class, status, roles ve note tek atomik repository işlemi olarak kaydolur;
  undo/autosave/round-trip güvenlidir.
- Eski interval `unreviewed` olarak kullanılmaya devam eder; legacy veri kaybolmaz
  ve joint annotation eksiği derived correctness'i veya temporal error etiketini
  bozmaz.
- Canonical export interval + class + time + role + native node ilişkisini,
  supervision targetını ve maskesini deterministik ve validate edilebilir
  biçimde taşır. Bu veri gelecekte ayrı bir joint classifier zorunluluğu olmadan
  node evidence/relevance denetimi sağlayabilir.
- Klasörü bulunamayan yetim proje yalnız owner'ın açık onayıyla uygulama
  listesinden kaldırılabilir; hiçbir filesystem hedefi silinmez, audit korunur ve
  güvenli silme guard'ları gevşemez.
- Navigation rail'deki logo ve `Daralt` kontrolü dengeli, ortalı ve aralıklı
  görünür; collapsed/expanded davranış bozulmaz.
- Auth açılış ekranı paketlenmiş YTÜ logosunu kullanır ve bütün mevcut auth
  işlevlerini koruyarak daha profesyonel, responsive ve erişilebilir görünür.
- Production uygulaması varsayılan olarak gerçek maximized window state'inde
  açılır; GUI testleri farklı viewportlarda çalışmaya devam eder.
- İlgili ve tam test paketleri gerçekten çalıştırılmış, başarısızlıklar giderilmiş
  ve `MEMORY.md` gerçek sonuçlarla güncellenmiştir.

Güvenlik veya veri anlamı kararlarında belirsizlik çıkarsa sessiz varsayım yapma;
mevcut kodu ve testleri inceleyerek en dar, denetlenebilir davranışı seç ve
seçimini dokümante et. Görsel tasarımın exact yönteminde özgürsün, fakat bu
prompttaki ürün anlamlarını veya kabul kriterlerini daha kolay bir alternatifle
değiştirme.
