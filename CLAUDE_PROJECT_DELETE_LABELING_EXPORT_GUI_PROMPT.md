# Claude Code Görevi — Güvenli Proje Silme, Türetilmiş Etiketler ve Duyarlı GUI

KineCapture Studio 0.8.0 uygulamasında aşağıdaki ürün kararlarını gerçek koda
uygula. Bu görevi yalnız analiz, öneri, tasarım veya plan olarak bırakma:
uygulamayı değiştir, gerekli veri sözleşmesi ve migration kararlarını ver,
regresyon testlerini ekle, bütün uygun testleri çalıştır, arayüzü gerçekçi dolu
durumlarla çizdirerek doğrula ve görev sonunda MEMORY.md dosyasını yalnız
gerçek sonuçlarla güncelle.

Bu prompttaki kararlar, daha eski promptlarda, belgelerde veya mevcut kodda
bulunan çelişkili davranışlardan üstündür. Özellikle
CLAUDE_CAPTURE_REVIEW_LABELING_UI_PROMPT.md içindeki hareket dialogunda
Doğru/Hatalı kararının kullanıcıdan istenmesi artık geçerli değildir.

## 1. Başlangıç ve değişmez çalışma kuralları

1. Önce repository kökündeki CLAUDE.md ve MEMORY.md dosyalarının tamamını oku.
   Ardından gerçek kodu, testleri ve mevcut çalışma ağacını incele. MEMORY ile
   kod çelişirse gerçek davranışı doğrula, çelişkiyi görünür kıl ve görev
   sonunda MEMORY.md içine kaydet.
2. Yalnız mevcut KineSynth conda environment'ını kullan. Yeni environment
   oluşturma; bilimsel ortamın paketlerini gereksiz yere kurma, kaldırma veya
   yükseltme.
3. Çalışma ağacındaki kullanıcı değişikliklerini koru. İlgisiz dosyaları geri
   alma, silme veya üzerlerine yazma. files klasöründeki logo bu görev için
   kullanıcı tarafından verilmiş bir girdidir.
4. Ham kayıt değişmezliğini, annotation sidecar ayrımını, atomik JSON yazımını,
   yarım kayıt kurtarmayı, Windows uzun yol desteğini, mock backend'i, sentetik
   veri işaretini, güvenli kapanışı ve preview-loss/capture-loss ayrımını koru.
5. Proje silme bölümü bu değişmezlik kuralının bilinçli ve dar kapsamlı tek
   istisnasıdır: yalnız yönetici açıkça onayladığında hedef proje ve onun tüm
   verileri kalıcı olarak silinecektir. Bu yetkiyi başka işlemlere genişletme.
6. GUI thread'ini kamera, video, disk taraması, klasör boyutu hesabı, büyük
   klasör silme veya ağır hesapla bloklama. Uzun işlemler için mevcut Qt
   worker/thread yaklaşımıyla uyumlu güvenli bir yaşam döngüsü kullan.
7. Kod, alan ve tanımlayıcılar İngilizce; kullanıcıya görünen yeni metinler
   Türkçe olsun. Mevcut tema, vektör ikon ve erişilebilirlik yaklaşımını koru;
   emoji ekleme ve yalnız renkle durum anlatma.
8. Sabit piksel ofsetleriyle, yalnız tek çözünürlükte çalışan yerleşim
   hileleriyle veya minimum pencere boyutunu büyüterek GUI kusurlarını gizleme.
   Kök nedeni layout, scroll, size policy ve veri sözleşmeleri üzerinden çöz.
9. Şema veya veri anlamı değişiyorsa doğru sürümleme ve geriye uyumluluk
   uygula. Yalnız GUI değişikliği için gereksiz şema artışı yapma; fakat
   correctness alanının otoritesi değiştiği halde şemayı değişmemiş gibi
   göstermeme.

## 2. Kodda doğrulanmış mevcut başlangıç durumu

Değişiklikten önce aşağıdaki noktaları gerçek kodda yeniden doğrula. Bunlar bu
prompt hazırlanırken yapılan denetimin sonuçlarıdır, kör varsayımlar değildir:

- Uygulama sürümü 0.8.0'dır.
- Project schema 1.1.0, session 2.0.0, take 1.1.0, skeleton stream 1.1.0,
  annotation 2.0.0, label 2.0.0, release 2.0.0, feature spec 1.0.0, raw archive
  1.0.0 ve identity SQLite schema 1'dir.
- src/kinecapture/gui/pages/projects.py proje oluşturma, içe aktarma ve açma
  işlevlerini sunuyor; proje silme eylemi yok.
- IdentityService ve identity repository proje kaydetme, oluşturma, listeleme
  ve erişim yönetimi yapıyor; proje verisiyle birlikte güvenli silme servisi
  yok.
- SQLite projects, project_access ve audit_log tabloları birbirine foreign key
  ile bağlı. audit_log.project_id nullable olsa da mevcut ilişkiler doğrudan
  projects satırı silmeyi güvenli bir kullanıcı akışı haline getirmiyor.
- Hareket dialogu src/kinecapture/gui/widgets/label_dialogs.py içinde hareket
  sınıfıyla birlikte açık bir Correctness seçimi bekliyor.
- MovementSample correctness değerini kalıcı tutuyor; evaluate_sample,
  annotation repository, Dataset ekranı ve export kodu bu saklanan değeri
  otoritatif kabul ediyor.
- TimelineWidget hareket ve hata aralıklarının sınırlarını mouse hareket
  ettikçe repository'ye yazan sample_bounds_changed ve
  interval_bounds_changed sinyallerini gönderiyor. Sürüklenen sınır karesini
  görüntülemek için ayrı bir geçici preview sözleşmesi ve bırakınca eski
  playhead'e dönüş yok.
- ExportPage sabit yatay seçenek/sürüm sütunlarına sahip ve kullanıcıya hâlâ
  KineSynthV3 uyumu yönlendirmesi gösteriyor.
- SettingsPage iki yoğun, bağımsız scroll sütunu ve içlerinde dar genişlikte
  yeniden akmayan yatay FieldRow grupları kullanıyor.
- NavigationRail açıkken 208 px, daraltıldığında 56 px genişlikte; marka
  başlığı ve navigasyon ile en alttaki Daralt düğmesi arasında logo için boş
  alan var.
- files/Yıldız_Technical_University_Logo.png mevcut, RGBA, şeffaf arka planlı
  ve yaklaşık 398x405 px. Dosya henüz paketlenmiş uygulama kaynağı değildir.
- Bu prompt hazırlanırken seçili GUI/Export/Review testlerinden 132 tanesi
  geçiyordu. Ancak mevcut bütün-sayfa paint testi yalnız pixmap üretildiğini
  kontrol ediyor; child widget taşması, erişilemeyen kontroller ve istemsiz
  yatay scroll gibi geometri kusurlarını yakalamıyor.

En az aşağıdaki dosyaları ve ilişkili testleri incele:

- src/kinecapture/gui/pages/projects.py
- src/kinecapture/gui/pages/review.py
- src/kinecapture/gui/widgets/timeline.py
- src/kinecapture/gui/widgets/label_dialogs.py
- src/kinecapture/gui/pages/export.py
- src/kinecapture/gui/pages/settings.py
- src/kinecapture/gui/pages/dataset.py
- src/kinecapture/gui/main_window.py
- src/kinecapture/gui/widgets/common.py
- src/kinecapture/gui/theme.py
- src/kinecapture/gui/state.py
- src/kinecapture/identity/database.py
- src/kinecapture/identity/repository.py
- src/kinecapture/identity/service.py
- src/kinecapture/annotations/repository.py
- src/kinecapture/domain/project.py
- src/kinecapture/domain/labels.py
- src/kinecapture/domain/enums.py
- src/kinecapture/dataset/workspace.py
- src/kinecapture/export/release.py
- src/kinecapture/export/continuous.py
- src/kinecapture/features/registry.py
- tests/test_gui.py
- tests/test_gui_painting.py
- tests/test_review_flow.py
- tests/test_export_gui.py
- ilgili identity, workspace, annotation, release ve GUI testleri

## 3. Projeler — yalnız yöneticinin kalıcı ve güvenli silmesi

Kullanıcı disk alanı kazanmak istiyor. Silme, listeden kaldırma veya soft
delete değildir: başarılı olduğunda proje kök klasörü içindeki ham kayıtlar,
proxy'ler, iskelet akışları, annotation sidecar'ları, release'ler ve diğer tüm
proje dosyaları fiziksel olarak kaldırılmış olmalı. Geri dönüşüm kutusuna
taşımak veya gizli bir çöp klasöründe süresiz tutmak başarı sayılmaz.

### 3.1 Yetki sınırı

1. Proje silme yetkisi yalnız identity modelindeki tek System Owner/admin
   rolüne aittir. Normal user rolü:
   - silme düğmesini görmemeli veya kullanamamalı;
   - GUI'yi atlayıp servis metodunu çağırsa bile authorization hatası almalı.
2. Yetkiyi yalnız ProjectsPage içinde kontrol etme. Asıl güvenlik sınırı
   IdentityService/AppState veya uygun domain servisinde enforced edilmeli.
3. Admin olmayan kullanıcının proje erişimini kaldırma ile projenin tamamını
   silmeyi aynı işlem veya aynı metin olarak sunma.

### 3.2 Kullanıcı akışı ve onay

1. Proje listesindeki seçili proje için açıkça destructive biçimde görünen
   Projeyi sil eylemi ekle. Yanlış projeyi silmeyi zorlaştır.
2. İlk onay penceresinde en az şunları göster:
   - proje adı ve proje kimliği;
   - tam ve elide edilmeden kopyalanabilir proje yolu;
   - bu işlemin ham kayıtlar ve export sürümleri dahil kalıcı olduğu;
   - geri alınamayacağı ve disk alanı açacağı;
   - proje aktifse kapatılacağı.
3. Basit Evet/Hayır tek başına yeterli değildir. Admin, proje adını veya
   açıkça belirtilen doğrulama metnini doğru yazmadan son Sil düğmesi
   etkinleşmesin.
4. İptal, pencereyi kapatma ve yanlış doğrulama metni hiçbir dosyayı, DB
   kaydını veya aktif bağlamı değiştirmesin.
5. Silme başladıktan sonra çift tıklama/tekrar basma ikinci bir silme işi
   oluşturmasın. İlerleme durumu görünür olsun. Geri alınamaz fiziksel silme
   aşamasında yanıltıcı bir İptal düğmesi sunma.
6. Büyük proje klasörlerinde UI donmamalı. Ön boyut hesabı yapılıyorsa o da
   arka planda çalışmalı ve erişilemeyen dosyalarda sahte kesin değer
   göstermemeli.
7. Başarı mesajı, proje adıyla birlikte gerçekten boşalan yaklaşık alanı
   mümkünse göstersin. Bu değer hesaplanamadıysa bunu açıkça belirt.

### 3.3 Dosya sistemi güvenliği

1. GUI'den doğrudan shutil.rmtree çağırma. Tek bir test edilebilir silme
   koordinatörü/service oluştur.
2. Hedef yolu yalnız seçili DB kaydından al. Kullanıcı metni, glob, ortam
   değişkeni veya çözülmemiş relative path ile recursive delete yapma.
3. Silmeden hemen önce:
   - canonical/resolved yol ile kayıtlı yolu karşılaştır;
   - klasördeki project manifest kimliğinin seçilen project_id ile aynı
     olduğunu doğrula;
   - hedefin mevcut bir proje klasörü olduğunu doğrula;
   - drive root, home, dataset root'un kendisi, repository root veya bunların
     benzeri geniş bir kök hedefse işlemi reddet;
   - symlink, junction/reparse point ve beklenmeyen path traversal durumlarını
     güvenli biçimde reddet veya açıkça güvenli politika uygula;
   - hedef değişmiş, taşınmış veya kimliği uyuşmuyorsa hiçbir şey silme.
4. Proje içindeki symlink/junction üzerinden proje dışındaki veriyi takip edip
   silme.
5. Silme sırasında kullanılan geçici/tombstone klasör kalıcı başarı sonunda
   kalmamalı; kullanıcı disk alanı kazanmalıdır.
6. Windows'ta açık video/dosya handle'larını, salt-okunur dosyaları, uzun
   yolları ve kısmi filesystem hatalarını ele al. Hata halinde başarı
   göstermeme; kalan yolu ve güvenli çözüm önerisini bildir.

### 3.4 Aktif bağlam, DB ve hata toparlama

1. Kayıt devam ederken proje silmeyi kesin biçimde engelle. Admin önce kaydı
   normal akışla durdurmalı/finalize etmelidir.
2. Silinen proje aktifse capture service, review reader, proxy/video handle,
   otomatik session ve workspace referanslarını güvenli sırayla kapat; sonra
   state'i proje seçilmemiş duruma getir ve ilgili Qt sinyallerini yayınla.
3. project_access satırlarını ve projects satırını kontrollü transaction ile
   kaldır. audit_log foreign key ilişkisini bilinçli çöz:
   - eski denetim geçmişini foreign key yüzünden silmeye çalışma;
   - gerekirse eski project_id referanslarını null yaparken olay metadata'sında
     minimum proje kimliği/adı ve silme sonucunu koru;
   - başarılı veya başarısız silme denemesini actor olarak admin ile logla.
4. Minimum güvenlik audit kaydı dışında silinen proje uygulamanın proje
   listesinde, erişim tablosunda, recent/last-project tercihinde veya aktif
   state'inde kalmamalı.
5. Filesystem ve SQLite tek atomik transaction olamaz. Bunu görmezden gelme.
   Doğrulanmış bir staging/tombstone + DB transaction + recovery tasarımı veya
   eşdeğer güvenli bir koordinasyon uygula. Aşağıdaki son durumlar garanti
   edilmeli:
   - tam başarı: klasör yok, proje/access DB kayıtları yok, aktif/recent
     referans yok, minimal audit olayı var;
   - onay öncesi/iptal: hiçbir şey değişmedi;
   - preflight/authorization hatası: hiçbir şey değişmedi;
   - ara aşama hatası: sahte başarı yok, mümkün olan yerde eski tutarlı durum
     geri getirildi; fiziksel kısmi silme olduysa tam olarak raporlandı ve
     uygulama başlangıcında güvenli recovery/cleanup yolu var.
6. Uygulama silme sırasında kapanır veya çökerse sonraki açılışta belirsiz
   proje/tombstone durumunu algılayan deterministik recovery politikası olsun.
7. Silme tamamlandıktan sonra ProjectsPage, ContextBar, Dashboard, Dataset,
   Review ve Export eski projeyi kullanmaya devam etmemeli.

## 4. İnceleme — Doğru/Hatalı kararı hata aralıklarından türetilecek

Yeni otoritatif ürün kuralı şudur:

- Hareket sınıfı kullanıcı tarafından kaydedilmiş ve sınıflandırılmış hiçbir
  hata aralığı yoksa hareket Doğru ve exporta hazırdır.
- En az bir geçerli ve sınıflandırılmış hata aralığı varsa hareket Hatalıdır.
- Son geçerli hata aralığı silinirse hareket otomatik olarak yeniden Doğru
  olur.
- Sınıfsız, sınırları geçersiz veya ana hareket dışındaki bir hata aralığı
  hareketi Doğru yapmaz; hareket eksik/unready sayılır ve exporta girmez.
- Kullanıcı hareket için ayrıca Doğru veya Hatalı seçmez.

Bu kuralı yalnız dialogdan iki düğme kaldırarak uygulama. Domain, repository,
readiness, Dataset, export, istatistikler ve görünen bütün özetlerde tek
otoritatif hesaplama kullan.

### 4.1 Hareket mini penceresi

1. MovementLabelDialog içindeki Doğru/Hatalı düğmelerini, KARAR bölümünü,
   ilgili zorunluluk metinlerini ve correctness seçimi API'sini kaldır.
2. Dialogun ana işi:
   - mevcut hareket sınıflarını aramak/göstermek;
   - seçili sınıfı atamak;
   - yeni hareket sınıfını aynı pencerede eklemek;
   - isteğe bağlı notu düzenlemek;
   - gerekirse gelişmiş ikincil eylemleri sade biçimde sunmak
   olmalıdır.
3. Screenshot'taki gibi geniş boş liste ve gereksiz yüksek dialog bırakma.
   İçeriğe ve ekrana göre duyarlı, klavyeyle kullanılabilir, dark/light temada
   dengeli mini pencere oluştur.
4. Kaydet yalnız geçerli bir hareket sınıfı seçildiğinde mümkün olsun. Bu
   kaydetme olayı hareketin sınıf incelemesinin tamamlandığı anlamına gelir.
5. Hareket sınıfını kaydetmek ve hata aralığı bulunmaması hareketi anında
   Doğru/hazır yapmalı. Kullanıcıdan ikinci bir onay isteme.
6. Eski 1/2 doğru-hatalı klavye kısayollarını, _set_verdict yollarını,
   tooltip'leri ve kullanıcı mesajlarını kaldır. Kısayol yardımını da güncelle.

### 4.2 Tek correctness kaynağı

1. derived_correctness benzeri tek bir domain fonksiyonu/property'si tanımla:
   geçerli sınıflandırılmış error interval varlığı Hatalı, yokluğu Doğru
   sonucunu üretir. Aynı mantığı farklı sayfalarda kopyalama.
2. Hareket henüz sınıf dialogundan kaydedilmediyse veya sınıfsızsa sonuç
   Etiketlenmedi/unready olarak kalmalı. Gerekirse açık bir reviewed/label
   completion alanı veya eşdeğer dayanıklı sözleşme tasarla.
3. Error interval ekleme, sınıf atama, sınıf değiştirme, sınır değiştirme,
   silme, undo/redo, split/merge ve autosave sonrasında türetilmiş sonuç anında
   tutarlı güncellensin.
4. Stored correctness alanı geriye uyumluluk için serialize edilmeye devam
   ederse salt türetilmiş/cache alanı olsun; hiçbir public edit API bu değeri
   hata aralıklarından bağımsız ayarlayamasın. Kaydetmeden önce yeniden
   hesaplanmalı ve divergence mümkün olmamalı.
5. Dataset filtreleri, dağılımlar, hareket listesi, readiness mesajları,
   release manifesti ve export hedefleri aynı türetilmiş sonucu kullanmalı.
6. Exportta binary correctness alanı yararlıysa koru; fakat manifest/contract
   bunun error intervals'dan türetildiğini açıkça belirtsin.

### 4.3 Legacy annotation güvenliği ve sürümleme

Mevcut annotation 2.0.0 dosyalarında explicit correctness bulunabilir. Yeni
kuralı uygularken geçmiş kullanıcı kararlarını sessizce yok etme:

1. Eski dosyayı yalnız açmak onu yeniden yazmamalı.
2. Eski Hatalı kararı var fakat geçerli/sınıflandırılmış error interval yoksa
   bunu sessizce Doğru'ya çevirmek yerine legacy çelişkisi olarak göster.
   Hareket exporta hazır sayılmasın; kullanıcıdan eksik hata aralığını ekleyip
   sınıflandırması veya hareket dialogunu yeni kurala göre yeniden kaydedip
   bilinçli biçimde doğru kabul etmesi istenebilir.
3. Eski Etiketlenmedi hareket yalnız exercise alanı bulunduğu için sessizce
   Doğru/hazır yapılmamalı. Yeni hareket dialogunda sınıfın kaydedilmesi,
   incelemenin tamamlandığını açıkça belirlemeli.
4. Eski Doğru + hata aralığı ve diğer çelişkileri kayıpsız yükle, görünür
   migration/readiness mesajı üret ve kullanıcının işlemiyle deterministik
   biçimde yeni kurala geçir.
5. Migration uyguluyorsan idempotent, test edilebilir ve atomik olsun. Raw
   recording, eski release veya kaynak sidecar'ı sessizce toplu yeniden yazma.
6. Correctness otoritesinin değişmesi bir veri sözleşmesi değişikliğidir.
   Annotation, label mapping, release ve app sürümlerinin hangisinin neden
   artması gerektiğini semver ve gerçek reader compatibility'sine göre karar
   ver. Gerçekten değişen sürümleri test ve MEMORY.md içinde açıkça yaz.

## 5. Timeline — video editörü tarzı geçici kırpma önizlemesi

Hareket ve hata aralıklarında hem mevcut aralığın başlangıç/bitiş kenarını
sürüklerken hem de yeni aralığı ilk kez çizerken görüntüleyici sürüklenen anı
göstermelidir. Mouse bırakıldığında kalıcı timeline playhead'i, sürükleme
başlamadan önce bulunduğu kareye dönmelidir.

### 5.1 Etkileşim sözleşmesi

1. Aşağıdaki drag türlerinde geçici kare önizlemesi uygula:
   - movement resize-start;
   - movement resize-end;
   - error resize-start;
   - error resize-end;
   - yeni movement aralığı create;
   - yeni error aralığı create.
2. Drag başladığında:
   - mevcut playhead/frame pozisyonunu sakla;
   - oynatma çalışıyorsa duraklat;
   - drag oturumunu tek bir edit transaction olarak başlat.
3. Mouse hareket ettikçe:
   - resize-start için geçerli başlangıç karesini;
   - resize-end için geçerli bitiş karesini;
   - create için hareket eden endpoint karesini
     RGB, İskelet ve RGB + İskelet görüntüleyicinin aktif modunda göster;
   - parent movement sınırı ve take sınırı clamp kurallarını önizlemede de
     uygula;
   - timeline'da kullanıcıya sürüklenen kare numarası ve zamanı görünür olsun.
4. Bu geçici gösterim normal position_changed/seek akışını kalıcı playhead
   değişikliği gibi kullanmamalı. preview_position_changed, edit_started,
   edit_finished/cancelled veya eşdeğer açık bir sinyal sözleşmesi tasarla.
5. Mouse bırakıldığında:
   - geçerli yeni sınırı repository'ye yalnız bir mantıksal edit olarak
     commit et;
   - aralık oluşturma ise aralığı bir kez oluştur;
   - görüntüleyiciyi ve timeline imlecini drag öncesinde saklanan kareye geri
     getir;
   - otomatik oynatmaya başlamayıp güvenli biçimde paused durumda bırak.
6. Escape, focus loss veya geçersiz drag iptalinde tentative sınırları
   tamamen at, repository/undo/autosave'i değiştirme ve eski playhead'e dön.
7. Mouse hareketinin her pikselinde repository mutation, ayrı undo snapshot
   veya disk autosave üretme. Timeline tentative/ghost bounds'u kendi edit
   oturumunda gösterebilir; kalıcı mutation release'te bir kez olmalı.
8. Whole-range move davranışı bu istek kapsamında trim preview olarak yeniden
   tanımlanmak zorunda değildir. Mevcut taşıma özelliğini bozma; fakat onun da
   tek undo/commit ve güvenli sınır kurallarına uyduğunu doğrula.
9. Aralık oluşturma eşiğini geçmeyen sıradan kısa click mevcut scrub/seek
   davranışını koruyabilir. Gerçek create drag ile click'i test ederek ayır.
10. RGB proxy karesi eksikse başka kareyi yanlış eşleşmiş gibi gösterme;
    mevcut dürüst eksik-frame davranışını koru. Skeleton-only preview yine
    çalışmalı.

### 5.2 İnceleme sayfasıyla entegrasyon

1. ReviewPage geçici preview karelerini normal playback state'ini veya seçili
   annotation'ı değiştirmeden çizebilmeli.
2. Üç görünüm modu aynı geçici frame pozisyonunu kullanmalı.
3. Drag sırasında playback timer yarışmamalı ve görüntüyü başka kareye
   sıçratmamalı.
4. Release sonrası dönüş, drag başladığı anda oynatma konumu ne ise tam olarak
   oraya olmalı; aralığın eski/yeni başlangıcına gitmemeli.
5. Autosave, undo/redo ve readiness yalnız final commit'ten sonra bir kez
   güncellensin.

## 6. Export — KineSynthV3 yerine modelden bağımsız, doğru etiketli dataset

Bu projeyle oluşturulacak dataset daha sonra geliştirilecek yeni bir model için
kullanılacaktır. Önceki KineSynthV3 Transformer modeline uyumluluk artık ürünün
önceliği veya varsayılan export hedefi değildir.

1. Export ekranındaki KineSynthV3 uyumu yönlendirmesini ve onu varsayılan
   hedef gibi gösteren metinleri kaldır.
2. Canonical/model-agnostic export varsayılan olsun. Ana amaç:
   - örnek ve frame kimliklerinin izlenebilirliği;
   - kayıt/take/participant/project provenance;
   - orijinal frame index ve camera timestamp;
   - subject body ve skeleton specification;
   - eklem koordinatları, confidence/presence mask ve unit/coordinate metadata;
   - hareket sınıfı ve class mapping;
   - hata aralıkları, hata sınıfı mapping ve gerekiyorsa frame-level targets;
   - error interval'lardan türetilmiş correctness;
   - veri eksikliği maskeleri;
   - feature tanımı, shape, dtype ve unit;
   - schema/app sürümleri, seçenekler, fingerprint ve checksum;
   - validation sonucu ve exporta alınmama nedenleri
     gibi alanları açık ve kendi kendini açıklayan biçimde taşımaktır.
3. Core dataset exportuna model-spesifik normalizasyon, sabit sequence length,
   padding, interpolation, augmentation, train/test split dayatması veya
   Transformer tensör reshape'i ekleme. Bunlar gelecekteki eğitim pipeline'ının
   görevidir.
4. Mevcut zengin feature registry ve araştırma feature'larını sırf KineSynthV3
   önceliği kaldırıldı diye silme. Kullanıcı seçebilsin; fakat canonical ham
   sözleşme ve doğru etiketler ön planda olsun.
5. kinesynth_compat preset'i eski otomasyon/test uyumluluğu için güvenle
   tutulabiliyorsa Gelişmiş/Legacy altında açıkça isteğe bağlı bırak. Ana
   arayüz, açıklama ve varsayılan seçim onu önermesin. Kaldırmak kontratı
   bozuyorsa deprecation kararını belgele.
6. İnceleme ekranından emekliye ayrılmış activity authoring'i normal yeni
   dataset yolu olarak yeniden öne çıkarma. Eski activity_intervals verisini
   silme; legacy continuous export gerekiyorsa ikincil ve açıkça Eski veri
   olarak tut.
7. Yeni correctness kuralıyla release validation ve label mapping'in
   çelişemediğini test et. Bir movement sample exporta girdiyse hareket sınıfı
   tamamlanmış ve bütün error interval'ları geçerli/sınıflandırılmış olmalı.

## 7. Export GUI'sini duyarlı ve erişilebilir hale getir

Mevcut sabit iki sütunlu layout, 1120x700'de seçenekleri sıkıştırıyor ve
tablolar yatay scroll üretiyor. Ekranı mevcut tasarım dili içinde yeniden
düzenle.

1. En az şu bilgi mimarisini açık bölümler, iç sekmeler veya duyarlı splitter
   ile kur:
   - Dataset kapsamı ve readiness kuralları;
   - İskelet/koordinat hedefi;
   - Feature seçimi;
   - Doğrulama ve export önizlemesi;
   - Oluşturulmuş release'ler ve ayrıntıları.
2. 1120x700'de sabit yan yana kalmak zorunda olmayan responsive bir düzen
   kullan. Gerekirse içerik dikeyleşsin veya sekmelere ayrılsın.
3. Sayfanın tamamı ya da mantıksal pane'ler kontrollü dikey scroll kullansın.
   Nested yatay scrollbar'ları ve erişilemeyen alt kartları ortadan kaldır.
4. Ana Export/Release oluştur eylemi içerik uzasa bile kolay bulunur ve
   erişilebilir kalsın. Disabled ise nedeni yakınında açıkça yazsın.
5. Release tablosunda ResizeToContents yüzünden kontrolsüz minimum genişlik
   oluşmasını engelle; önemli sütunlar okunur, ayrıntılar seçili kayıt
   panelinde erişilebilir olsun.
6. Empty, bir release, çok release, uzun Türkçe metin, uzun path ve zengin
   feature seçimi durumlarını test et.

## 8. Ayarlar ve Tanılama GUI'sini yeniden düzenle

Mevcut iki bağımsız scroll sütununu daha geniş ekran varmış gibi zorlamayı
bırak. Kullanıcının ayar, etiket şeması ve tanılama görevlerini birbirinden
ayırt edebildiği bir yapı kur.

1. İç kategoriler/sekmeler veya eşdeğer net navigasyon kullan:
   - Genel;
   - Capture profili;
   - Sentetik/mock backend;
   - Hareket ve hata sınıfları;
   - Tanılama;
   - Dosya konumları.
2. Her kategoride tercihen tek dikey scroll yüzeyi olsun. Bir ana sayfada iki
   uzun bağımsız scroll kolonunu yan yana sıkıştırma.
3. Formları label + control grid düzenine geçir. Üç FieldRow'u tek HBox'a
   zorlayan satırlar dar genişlikte alt satıra akmalı veya dikeyleşmeli.
4. Uzun teknik uyarıları kontrolleri ezmeyecek kompakt bilgi banner'ı,
   açıklama alanı veya yardım dialogunda göster.
5. Tanılama raporunu tam genişlikli, monospaced ve esnek yükseklikte sun.
   Yenile/kopyala gibi eylemler metin alanını kapatmamalı.
6. Hareket ve hata sınıfı listeleri uzun olduğunda kaydırılabilir, aranabilir
   ve birbirini yatayda ezmeyen bir düzen kullansın.
7. Kaydedilmemiş değişiklik/dirty durumu, başarı ve validation mesajı açık
   olsun. Kaydet düğmesi içerik aşağı uzadığında kaybolmasın.
8. Dosya yolları uzun olduğunda metni kesip bilgiyi kaybetme; elide + tooltip
   ve kopyalama gibi uygun davranış sun.

## 9. NavigationRail'e Yıldız Teknik Üniversitesi logosu

Kaynak görsel files/Yıldız_Technical_University_Logo.png dosyasındadır.

1. Logo, sol NavigationRail açıkken en alttaki Daralt düğmesinin hemen üstünde
   ve yatayda ortalanmış olarak gösterilsin.
2. Orijinal en-boy oranı ve şeffaflık korunsun. Smooth transformation kullan;
   700 px yüksek ekranda navigasyon maddelerini veya Daralt düğmesini
   itmeyecek makul maksimum boyut seç.
3. NavigationRail daraltıldığında logo küçültülmüş ikon haline gelmesin;
   tamamen gizlensin ve layout'ta boşluk bırakmasın.
4. Rail yeniden açıldığında doğru boyutta yeniden görünsün. Tekrar tekrar
   collapse/expand görüntüyü bozmasın veya yeni pixmap üretip sızıntı yapmasın.
5. Logo yalnız repository-relative development path'ten yüklenmemeli.
   Görseli src/kinecapture/gui altında uygun bir package resource/assets
   konumuna al veya kopyala, package-data/build yapılandırmasına ekle ve kurulu
   uygulama ile testlerde güvenilir bir resource loader kullan.
6. Kaynak logo dosyasını gereksiz dönüştürme veya kalitesini düşürme. Paketleme
   için kopya gerekiyorsa kaynak ile ilişkisini açık tut.
7. Logo yüklenemezse uygulama çökmemeli; navigation kullanılabilir kalmalı ve
   tanı koyulabilir bir warning üretilmeli.
8. Dark/light temada, 100/125/150% ölçekleme ve açık/dar rail durumunda test et.

## 10. Genel GUI denetimi ve küçük kusurlar

Yalnız kullanıcının tek tek saydığı sayfaları düzeltip bırakma. Bütün
uygulamayı aynı viewport matrisiyle denetle:

- giriş/ilk kurulum dialogları;
- Ana Sayfa;
- Projeler;
- Katılımcılar;
- Capture ve modeless bilgi penceresi;
- İnceleme ve Etiketleme ile iki label dialogu;
- Dataset;
- Export ve feature dialogu;
- Ayarlar ve Tanılama;
- ContextBar, NavigationRail, banner/status alanı ve ortak dialoglar.

Denetim ilkeleri:

1. 1120x700, 1366x768 ve 1600x980 boyutlarında dark/light temayı gerçekten
   show, processEvents ve grab ile çizdir.
2. Yalnız empty state kullanma. Uzun proje/katılımcı adları, uzun path'ler,
   çok satırlı uyarılar, dolu tablolar, çok sayıda sınıf, label bekleyen
   örnekler ve release'lerle gerçekçi fixture oluştur.
3. Aşağıdakileri tespit edip düzelt:
   - kardeş widget'ların istenmeyen üst üste binmesi;
   - child widget'ın görünür parent/viewport dışına taşması;
   - erişilemeyen düğme veya form alanı;
   - gereksiz yatay scroll;
   - kesilen Türkçe metin ve tooltip olmadan elide edilen önemli bilgi;
   - aşırı büyük boş alanlar;
   - sabit HBox yüzünden sıkışan ContextBar/filtre/eylem satırları;
   - modal dialogun ekran dışına taşması;
   - odak sırası ve klavye kullanım hataları;
   - disabled kontrolün nedeninin anlaşılamaması;
   - dark/light temada düşük kontrast;
   - yüksek DPI'da ikon veya metin taşması.
4. Bilinçli overlay'leri, combo popup'larını veya scroll viewport'larını yanlış
   pozitif sayan kaba bir tüm-widget kesişme testi yazma. Kritik container ve
   kontrol grupları için anlamlı geometri/visibility assertion'ları kur.
5. Uygulama başlatılırken görülen QFont::setPointSize <= 0 warning'lerinin
   kaynağını araştır. Uygulama kodundan geliyorsa düzelt ve warning-free
   startup testi ekle; Qt/platform kaynaklıysa kanıtla ve raporla.
6. Mevcut 1120x700 minimumunu büyütmeyi çözüm olarak kullanma. Daha küçük
   viewport desteği mevcut ürün kararıdır.

## 11. Test ve kabul ölçütleri

Testler gerçek kullanıcı verisine veya gerçek identity DB'ye asla dokunmasın.
TemporaryDirectory/tmp_path ve enjekte edilmiş identity_db_path kullan.

### 11.1 Kalıcı proje silme

- Normal user butonu görmez ve servis çağrısı authorization hatası verir.
- Owner/admin butonu görür.
- Cancel, dialog close ve yanlış doğrulama metni tam no-op'tur.
- Doğru doğrulama sonrası geçici proje klasörü ve içindeki raw, annotation,
  proxy, release ve nested dosyalar fiziksel olarak yoktur.
- Projects ve project_access DB satırları yoktur; proje listede, recent state
  veya active state'te görünmez.
- Minimal audit olayı admin actor ve sonuç bilgisiyle kalır.
- Aktif ama kayıt yapılmayan proje güvenli kapanıp silinir.
- Kayıt devam ederken silme reddedilir ve hiçbir veri değişmez.
- Manifest project_id/path uyuşmazlığı, root hedef, symlink/junction ve
  yetkisiz path durumlarında hiçbir şey silinmez.
- Permission/open-handle/DB failure enjeksiyonunda sahte başarı yoktur;
  recovery politikası ve kalan durum test edilir.
- Büyük klasör silme yolu GUI event loop'unu bloklamaz.
- Testler yalnız disposable temp projelerini siler.

### 11.2 Türetilmiş correctness

- Yeni movement class kaydedilip hata yoksa Doğru ve ready olur.
- İlk sınıflandırılmış hata aralığı eklenince Hatalı olur.
- Birden çok hata aralığı varken Hatalı kalır.
- Son hata aralığı silinince Doğru olur.
- Sınıfsız error interval hareketi unready yapar; Doğru veya exportable yapmaz.
- Error sınıfı sonradan atanır/silinir/değişirse sonuç anında güncellenir.
- Undo/redo, split, merge, autosave ve reload sonrası sonuç değişmez.
- Movement dialogunda verdict düğmeleri ve ilgili kısayollar yoktur.
- Dataset dağılımı/filtreleri, Review özeti ve release export aynı derived
  değeri gösterir.
- Legacy explicit correctness çelişkileri sessiz veri kaybı olmadan yüklenir,
  görünür olur ve belirlenen migration akışıyla çözülür.
- Exported correctness ile error target/interval içeriği çelişemez.

### 11.3 Timeline preview

- Altı drag türünün tamamında sürüklenen endpoint karesi preview edilir.
- Preview RGB, Skeleton ve Overlay modunda aynı konuma gider.
- Parent movement/take clamp'i preview ve final bounds'ta aynıdır.
- Release sonrası eski playhead tam olarak geri gelir.
- Escape/focus-cancel bounds'u ve playhead'i geri getirir.
- Bir drag yalnız bir repository mutation, undo snapshot ve autosave üretir.
- Create drag yeni aralığı bir kez oluşturur ve eski playhead'e döner.
- Kısa click mevcut scrub davranışını korur.
- Drag sırasında playback timer preview karesini ezmez.
- RGB eksik frame ve skeleton-only take durumları dürüst biçimde çalışır.

### 11.4 Export ve responsive GUI

- Varsayılan export ve görünen açıklamalar model-agnostic'tir; KineSynthV3
  temel hedef olarak sunulmaz.
- Canonical export, hareket/hata mapping'leri, derived correctness, frame/time
  provenance, masks, skeleton spec, units, shape/dtype ve validation
  metadata'sını taşır.
- Eski activity verisi okunabilir kalır fakat yeni ana akışı kalabalıklaştırmaz.
- Export ve Settings sayfalarında belirtilen üç viewport ve iki temada kritik
  kontroller görünür/erişilebilir, istenmeyen overlap ve yatay scroll yoktur.
- Dolu tablo, uzun metin/path, çok sınıf ve çok release fixture'ları çizilir.
- NavigationRail açıkken logo doğru konumdadır; collapsed durumda görünmez ve
  boşluk bırakmaz.
- Paketlenmiş/resource çözümlemesinde logo bulunur; development cwd'sine bağlı
  değildir.
- Bütün sayfaların gerçek paint yolları ve kritik dialoglar iki temada geçer.

## 12. Tam doğrulama

1. Önce ilgili hedef testleri çalıştır.
2. Ardından yalnız KineSynth environment'ında:

   - scripts/run_tests.ps1
   - conda run -n KineSynth python -m kinecapture --self-test

   komutlarını çalıştır.
3. Mümkünse uygulamayı normal launcher ile aç, disposable/test admin ve
   disposable bir proje kullanarak:
   - proje silme onayı;
   - movement/error create ve resize preview;
   - movement dialogu;
   - Export;
   - Settings/Diagnostics;
   - logo collapse/expand
     akışlarını etkileşimli doğrula.
4. Gerçek kullanıcı projesini silme veya değiştirme. Silme testleri sadece
   açıkça oluşturulmuş geçici fixture üzerinde yapılmalıdır.
5. GUI ekran görüntülerini veya geometri test kanıtlarını görev raporunda
   özetle. Offscreen paint'i gerçek kamera/donanım testi gibi sunma.
6. Çalıştırmadığın testi geçti diye yazma. Warning veya failure varsa
   nedenini incele; yeşil sonuç için assertion gevşetme.

## 13. MEMORY.md ve tamamlanma raporu

Son kullanıcı yanıtından önce MEMORY.md içine yalnız gerçekten doğrulanan
bilgilerle yeni bir bölüm ekle:

1. Admin-only permanent project deletion sözleşmesi, confirmation yöntemi,
   path guard'ları, DB/audit sırası ve failure recovery davranışı.
2. Yeni derived correctness kuralı, legacy migration politikası ve
   readiness/export etkisi.
3. Timeline create/resize preview sinyalleri, tek commit ve playhead restore
   davranışı.
4. Model-agnostic export sözleşmesi ve KineSynthV3/legacy preset kararı.
5. Export, Settings, genel GUI ve logo yerleşim kararları.
6. Değişen ve değişmeyen gerçek app/schema sürümleri.
7. Gerçekten çalıştırılan her test komutu, pass/fail sayısı ve süre.
8. Donanımda, gerçek büyük projede veya paketlenmiş installer'da
   doğrulanamayan noktalar.

Final raporunda değişen dosyaları, kullanıcı açısından yeni akışları, veri
güvenliği kararlarını, sürüm/migration kararlarını, test sonuçlarını ve
doğrulanamayanları kısa ama somut biçimde yaz.

## Bitti sayılmayacak sonuçlar

- Yalnız plan veya mockup sunmak.
- GUI'ye Sil düğmesi ekleyip servis seviyesinde authorization yapmamak.
- Projeyi yalnız listeden kaldırmak, Recycle Bin'e taşımak veya gizli trash
  klasöründe bırakarak disk alanını boşaltmamak.
- Kullanıcı metni veya doğrulanmamış path ile recursive delete yapmak.
- Kısmi filesystem/DB hatasında başarı mesajı göstermek.
- Doğru/Hatalı düğmelerini gizleyip stored correctness'i otoritatif bırakmak.
- Legacy Hatalı kararı + hata aralığı yok durumunu sessizce Doğru yapmak.
- Timeline drag sırasında normal seek yapıp mouse release sonrasında eski
  playhead'i geri getirmemek.
- Her mouseMove'da repository mutation/autosave/undo kaydı üretmek.
- Yalnız mevcut sınır düzenlemesine preview ekleyip yeni range create
  sürüklemesini dışarıda bırakmak.
- KineSynthV3 metnini kaldırıp export sözleşmesini hâlâ model-spesifik bırakmak.
- Layout kusurlarını minimum pencere boyutunu büyüterek veya yalnız bir ekran
  görüntüsüne göre sabit piksel ayarıyla gizlemek.
- Logoyu yalnız files klasöründen cwd-relative yükleyip paketlemeyi unutmamak.
- Yalnız pixmap null değil testiyle overlap ve erişilebilirliği doğrulanmış
  saymak.
- Gerçek kullanıcı verisi üzerinde destructive test yapmak.
