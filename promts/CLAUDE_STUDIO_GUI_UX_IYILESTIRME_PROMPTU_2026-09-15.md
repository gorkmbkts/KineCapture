# Claude Code görevi: KineCapture Studio kullanım deneyimini tamamla

> **Bu görevin izi:** [6AF uygulama kaydı](../knowledge/archive/memory/6af-6af-17-eylul-gercek-zed-kaydindan-etiketlemeye-giden-zincir.md) · [6AG uygulama kaydı](../knowledge/archive/memory/6ag-6ag-18-eylul-canli-zed-turu-ve-veri-kalitesi-olcumleri.md) · [Canlı ZED doğrulaması](../knowledge/experiments/2026-09-18-live-zed.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


## Amaç ve çalışma sınırı

Mevcut `src/kinecapture/studio/` PySide6 arayüzünü, mevcut backend ile bağlantısı güvenilir, DaVinci Resolve benzeri düzenli bir çalışma alanına dönüştür. WinUI geçişi veya uygulamayı baştan yazmak bu görevin kapsamında değil. Yalnız renkleri değiştirmek yeterli değil: aşağıdaki iş akışı hatalarını düzelt, sonra bilgi hiyerarşisi, panel yerleşimi ve etkileşim ayrıntılarını tamamla.

**Kullanıcının ana kullanım biçimi büyütülmüş pencere (maximize).** Birincil kabul testi gerçek Windows masaüstünde, mevcut monitörde ekranı kaplayan pencereyle yapılacak. 15 Eylül incelemesinde pencere görüntüsü **1920 × 1032 fiziksel piksel** idi; başlık çubuğu ve normal Windows pencere davranışı korunuyordu. Bunu kenarlıksız kiosk/tam ekran moduyla karıştırma. Ekran ölçeğini değiştirmeden mevcut DPI değerini ölç ve test raporuna yaz. Dar pencere desteği ikincil dayanıklılık kontrolüdür; ana tasarımı küçük pencereye sıkıştırma hedefiyle kurma.

Önce `AGENTS.md`, `MEMORY_INDEX.md`, bu dosya ve ilgili kaynak kodu oku. `MEMORY.md` arşivinin tamamını okuma. `FAZ_PLANI_PYSIDE6_STUDIO.md` bölüm 7 geçmiş çalışmaları anlatır; geçmişte “tamamlandı” denmesi bu rapordaki canlı UI bulgularını geçersiz kılmaz. İncelenen commit `b1b75ea`, uygulama 0.11.0. Başlangıç commit'i değişmişse bulguların hâlâ geçerli olduğunu kontrol et.

Yalnız mevcut `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe` ortamını kullan. Kullanıcı kayıtlarını, ham kaynakları, hesaplanmış sürümleri ve gerçek kullanıcı tercihlerini koru. Test için ayrı kimlik/veri/tercih yolları kullan. Gerçek kamerayı kendiliğinden kayda alma. Donanım testi gerekiyorsa kullanıcıya kadrajı ve başlat/durdur denetimlerini ver; ikinci bir kişinin mevcut olduğunu varsayma.

## Denetimin dayanağı — ne gerçekten denendi?

Bu belge bir masaüstü kullanım denetiminden üretildi; ürün kodu bu denetimde değiştirilmedi. 14 Eylül'de yaklaşık 1366 × 768 istemci alanında, 15 Eylül'de büyütülmüş 1920 × 1032 pencere görüntüsünde mevcut Studio ekranları kullanıldı. Test kimliği normal uygulama servisi üzerinden hazırlandı; giriş/parola ekranının elle kullanılabilirliği değerlendirilmedi. Kayıt ve işleme için **sentetik kamera** kullanıldı. Buradaki sonuçlar ZED performans ölçümü veya gerçek insan üzerindeki iskelet doğruluğu sonucu değildir.

Korunan test alanı: `C:\Users\gorke\KineCapture\ux14`. Aynı proje ve dosyalarla kesintiden sonra devam edildi. Tekrar kayıt almadan mevcut sonuçlar yeniden açıldı.

- Proje: `prj_20260914T201214_ec91`, adı `UX Denetimi 14 Eylül`.
- İlk kayıt: `take_20260914T201308_f645`, P0001, 1231 kare, yaklaşık 41 saniye. GUI'den başlatıldı/durduruldu ve GUI'den hesaplandı.
- İlk işlenmiş sürüm: `run_9ef0826515344e72`. GUI'den İşlenen Videolar → Etiketle ile açıldı.
- İkinci deneme: `take_20260914T201926_4303`. P0002 satırı seçildikten ve Yakalama'da “Canlı iskelet” işaretlendikten sonra başlatıldı. Dosya P0001 altında ve `capture_profile.enable_body_tracking=false`, `store_skeleton=false` olarak oluştu. Sonraki uygulama kapanışında 1808 kareyle finalize edildi; log açıkça “uygulama kapatıldı / kayıt yarıda kaldı” diyor. Bunu temiz kullanıcı durdurması diye raporlama.
- Etiketleme ekranındaki sürükleme, çizelge görünmezken 0–0 aralığında bir hareket oluşturdu; bu test etiketi aynı sentetik projede duruyor. Gerçek etiket değildir.
- Veri Seti ekranı incelendi; eksik satıra çift tıklama düzeltme ekranına götürmedi. Dışa Aktarım kontrolü, eksik kişili/etiketli sürümü doğru biçimde dışarıda bıraktı. Başarılı paket üretimi bu denetimde doğrulanmadı.
- Tanılama → Yenile denendi; sonuç “henüz çalıştırılmadı” kaldı. Logdaki gerçek hata: `collect_diagnostics() takes 0 positional arguments but 1 was given`.
- 15 Eylül'de yeniden açılışta proje listesi boş kaldı. GUI'den boş `UX Liste Yenileme Kontrolü` projesi oluşturulunca önceki proje yeniden listelendi; eski proje seçilip aynı kayıt açıldı. Bu yalnız inceleme sırasında kullanılan geçici çıkış yoludur, ürün çözümü değildir.
- Büyütülmüş pencerede sekiz ana ekranın yerleşimi gözlemlendi; etiketleme ve genel denetçi paneli açık/kapalı kontrol edildi. Ayarlar ekranında koyu → açık → koyu tema geçişi denendi. Açık temada form zemini koyu kaldı ve koyu yazılar okunamaz hale geldi; bekleyip yeniden görüntü alındığında da sorun devam etti. İki temanın bütün sayfaları ve bütün DPI değerleri test edilmiş değildir.

Kanıt dosyaları: test alanındaki `logs/kinecapture.log`, proje altındaki `take.json`, processing job/manifest ve annotation sidecar dosyaları. Ham dosyaları “testi geçiriyor” hale getirmek için değiştirme. Bu dosyadaki gözlemlerle tasarım önerilerini ayrı değerlendir. Kimlik doğrulama, başarılı son paket, gerçek ZED, çok kişili eşleştirme ve bütün DPI kombinasyonları bu denetimde tamamlandı diye gösterilmemeli.

## P0 — görünüşten önce düzeltilecek iş akışı ve veri doğruluğu

### 1. Etiketleme açılışını gerçekten tamamlanan veri yüklemesine bağla

**Gözlem:** Video başlığında 1231 kare ve ilk görüntü var; çizelge “Zaman çizelgesi boş” diyor. “Hareket çiz” seçilip yatay sürükleme yapılınca beklenen aralık yerine 0–0 hareketi oluşuyor. Aynı sorun büyütülmüş pencerede yeniden görüldü.

**Kod izi:** `studio/views/pages/review.py:page_activated` içinde `open_version()` ardından `QTimer.singleShot(0, self._after_open)` çağrılıyor. Gerçek `QtTaskRunner` yüklemeyi asenkron yapıyor. `_after_open` veri gelmeden dönüyor; sonradan `_attach` frame bilgisini yayımlasa da çizelge/iskelet/kişi panelinin tüm hazırlığı yeniden tetiklenmiyor. `tests/test_studio_review_gui.py` doğrudan `_after_open()` çağırarak bu gerçek açılış yolunu atlıyor.

**İstenen:** Açılma tamamlandı olayını, sürüm kimliğiyle birlikte yayımla ve bütün ekran hazırlığını buna bağla. Gecikmiş eski açılış sonucunun yeni sürümü ezmesini önle. Yüklenirken görünür durum, hata olduğunda yeniden deneme göster. Çizelge geçerli kare aralığı almadan çizme/düzenleme araçlarını etkinleştirme. Veri olmayan 3B panel “hazır” izlenimi vermesin.

**Kabul:** Gerçek QtTaskRunner ile kütüphaneden çift tıklayarak açılan sürümde cetvel, playhead, izler ve aralıklar görünür. Aynı hareket sürüklemesi ekranda seçilen zaman aralığını oluşturur. Yavaş yükleme, A sürümü yüklenirken B'yi açma, sayfadan ayrılma ve yeniden açma test edilir. Test içinde özel `_after_open` çağrısı veya sabit uyku ile hatayı gizleme.

### 2. Kayıt hedefini seçili katılımcı ve oturuma bağla

**Gözlem ve dosya kanıtı:** P0002 seçiliyken başlatılan ikinci kayıt P0001'e yazıldı. Yakalama ekranı hangi katılımcı/oturuma yazacağını göstermiyor. Katılımcı seçimi sonrası satır vurgusu da kaybolabiliyor.

**Kod izi:** `studio/viewmodels/capture.py:_current_session` içindeki `participant = participants[0]`; Projeler VM'nin `selected_participant` değeri ortak oturum bağlamına taşınmıyor. `ProjectsViewModel.select_participant → _refill` model yenilemesi seçimi etkiliyor.

**İstenen:** Proje/katılımcı/oturum için tek doğruluk kaynağı kur. Kayıt öncesi hedefi görünür ve değiştirilebilir yap; seçim yoksa ilk kişiyi sessizce seçme. Yeni oturumu mevcut mimariye uygun otomatik oluşturabilirsin, fakat hedefi açıkça göster. Katılımcı kodunu kamera üzerindeki kişi seçimiyle karıştırma: ilki veri sahibidir, ikincisi görüntüdeki hedef kişidir. Kayıt sırasında hedef değişimini engelle veya sonraki kayıt için bekleyen değişiklik olarak açıkça bildir.

**Kabul:** İki sentetik katılımcı oluştur; P0002 seç → kayıt al → durdur. UI bağlamı, take metadata ve dosya konumu P0002 olmalı; P0001'e yeni kayıt eklenmemeli. Liste sıralama/arama/yenileme seçimi bozmasın.

### 3. Kayıt modu düğmeleri gerçek etkin ayarı temsil etsin

**Gözlem:** “Canlı iskelet” işaretli deneme ham kayıt profiliyle yazıldı.

**Kod izi:** `CaptureViewModel.set_mode` yalnız `self.mode.set(key)` yapıyor. `CaptureService.profile()` doğrudan `config.capture` döndürüyor; backend bağlantısı ve kayıt başlangıcına mod aktarımı yok.

**İstenen:** Varsayılan minimum ham kayıt kararını koru. Canlı iskelet seçildiğinde doğrulanmış profil geçişini servis üzerinden uygula. Kamera yeniden bağlantı gerektiriyorsa durumu göster; başarılı uygulamadan önce “etkin” deme. Kayıt sürerken mod değiştirme; gerçek etkin profil ile sonraki kayıt için seçilen profili ayır. Desteklenmeyen modu açık gerekçeyle pasifleştir.

**Kabul:** Mock ile iki modun UI seçimi, backend'e verilen profil ve kaydedilen metadata tutarlı olmalı. ZED üzerinde etkinleşme ayrıca doğrulanmadan gerçek donanım desteği tamamlandı sayılmamalı. Ham kayıt varsayılanı ve ham kaynak bütünlüğü korunmalı.

### 4. Aktif kaydı tüm çalışma alanında görünür ve durdurulabilir tut

**Gözlem:** İkinci kayıt sürerken “Verileri Hesapla” sayfasına geçildiğinde başlıkta KAYIT göstergesi kayboldu, global durdurma yoktu. Henüz açık kayıt 0 kare/0 saniyeyle “işlenmeyi bekleyenler” tablosuna girdi. Bu kayıt o durumda işlenmeye başlatılmadı; işlemenin gerçekten kabul edilip edilmediği ayrıca test edilmeli.

**Kod izi:** Yakalama sayfası ayrılınca metrik zamanlayıcısı duruyor ve shell yeni sayfa başlığı yazıyor. `ProcessingViewModel._refill` yalnız legacy/complete-run koşullarını kontrol ediyor. Shell kayıt sırasında başka sayfaya geçişe izin veriyor.

**İstenen:** Shell seviyesinde kalıcı kayıt göstergesi, süre, hedef katılımcı ve “Kaydı durdur” denetimi ekle. Açık/finalize edilmeyen kayıtları işlemeye uygun listeden ayır; backend guard da uygula. Yakalama ekranında eski “Ham kayıt kaydedildi” mesajını yeni aktif kayıtla birlikte başarı bildirimi gibi bırakma. Durumlar: hazırlanıyor, kaydediliyor, dosyalar kapatılıyor, tamamlandı/kısmi/hata. Kapanış sürerken neden beklendiği ve gerçek sonuç görünür olsun; GUI thread'inde uzun SDK/flush işi çalıştırma. Kullanıcı verisini koruyan mevcut atomik kapanış mantığını sürdür. Bildirim veya durum mesajı geldiğinde sayfanın üstüne yeni bir satır/container sokup video, 3B görünüm veya timeline'ı aşağı itme; görsel davranış aşağıdaki tasarım brifindeki bildirim kurallarına uysun.

**Kabul:** Kayıt sırasında sekiz sayfada da durum doğru görünür; global durdurma bir kez çalışır; ikinci tıklama çift finalize başlatmaz. Aktif kayıt işleme/export için uygun sayılmaz. İşlem sırasında pencere hareket ettirilebilir. Bağlanma/SDK hazırlama ve kapanışta yavaşlık için kontrollü test yapılır.

## P1 — çalışma alanı, yönlendirme ve güvenilir geri bildirim

### 5. Yeniden açılış ve listelerin güncelliği

Test hesabıyla yeniden açılışta mevcut proje görünmedi; “Yenile” de getirmedi. Kaynakta Projeler sayfası oturum açılmadan etkinleşip `_loaded=True` olabiliyor; `_signed_in` sonrası `page_activated` yeniden yüklemiyor. `_force_refresh` yalnız açık proje indeksini yeniliyor. Bu kod yolunu normal giriş olay sırasıyla da doğrula; test hazırlığına özgü olduğunu varsayarak kapatma.

Oturum açılınca erişilebilir projeleri yükle; boş, yükleniyor, erişilemiyor ve gerçekten proje yok durumlarını ayır. Yenile düğmesi başlığının vaat ettiği kapsamı yenilesin. Kayıt/işleme bittiğinde ilgili özetleri olayla geçersiz kıl ve görünür ekranı güncelle. Her sayfa değişiminde pahalı tam tarama yapma. Proje değişiminde eski review/run/iş bağlamının sızmasını önle.

Kabul: yeni proje oluşturmaya gerek kalmadan yeniden açılışta eski proje görünür. Kayıt ve işleme sonrası Projeler sayfasında sayaçlar güncel olur; seçim korunur.

### 6. Tek, bağlama duyarlı ayrıntı paneli ve yeniden boyutlandırılabilir çalışma alanı

**Hem küçük hem büyütülmüş pencerede görüldü:** Sağ üst panel düğmesi, seçili hareket varken bile “Seçili öğenin ayrıntıları burada görünür.” yazan ikinci bir panel açıyor. Etiketlemenin kendi Etiket/Sporcu paneli ayrıca yer kaplıyor. `studio/views/shell.py:_build_inspector` içeriği sabit.

Tek denetçi yaklaşımı uygula: seçili proje/kayıt/sürüm/hareket/hata bağlamına göre gerçek içerik göster; review içindeki panelle aynı anda iki rakip denetçi açma. Video, isteğe bağlı 3B, medya listesi ve zaman çizelgesi arasında ayarlanabilir splitter kullan. Panel ölçülerini ve görünürlüğünü çalışma alanına göre hatırla; “Yerleşimi sıfırla” ekle. Veri olmayan paneli geniş boş alan olarak varsayılan açık bırakma; sebebi ve sonraki işlemi göster.

Ana hedef: büyütülmüş pencerede video ve zaman çizelgesi baskın; seçili nesne denetçisi okunabilir; gereksiz boş paneller çalışma alanını küçültmüyor. Dar pencerede açıklama kesilmesi ikincil bir doğrulanmış sorun; bunu bütün kontrol metinlerini küçülterek çözme.

### 7. Kişi seçilmemiş kayıttan çıkış yolu

Yakalama “seçim sonradan yapılabilir” diyor; kişi seçmeden hesaplanan sürüm kütüphanede “kişi seçilmedi”, Sporcu panelinde “Bu sürümde izlenen hiçbir kişi yok”, export'ta eklem dizileri boş olarak görünüyor. Panelin “Tracker bu kayıtta hiç kararsız kalmadı” mesajı bu durumda yanıltıcı rahatlık veriyor. Bu denetimde sentetik görüntü kullanıldı; gerçek insan algılama başarısı sınanmadı.

Kişi anchor'ı, işlenmiş kişi adayını seçme ve belirsiz kimlik aralığını onaylama adımlarını ayrı anlat. İşlenmemiş kaynakta hedef kişi seçimi gerekiyorsa uygun kaynak önizlemesi ve güvenilir frame-anchor yolunu kur. Kişisiz tamamlanmış sürüm için “Kişiyi seç ve yeni sürüm hesapla” gibi gerçek bir kurtarma akışı sağla. Sonradan seçim mevcut boş joint dizilerini sihirli biçimde doldurmaz; yeni sürüm üret ve eski sürümü koru. Ham kaynak veya finalize edilmiş checksums altındaki dosyaları değiştiren kestirme çözüm üretme; yeni seçim için mevcut kanonik, türetilmiş ve sürümlü sözleşmeyi kullan/uygun biçimde genişlet.

### 8. Ekranlar birbirine gerçek iş bağlamıyla bağlansın

Kayıt sonu bildirimi yalnız “Verileri Hesapla ekranını kullanın” diyor. Hesaplama sonu kütüphanede sonucu bulmayı kullanıcıya bırakıyor. Veri Seti satırına çift tıklama ve export dışlama gerekçesi kullanıcıyı düzeltmeye götürmüyor.

Kayıt sonrası “Bu kaydı hesapla”; işleme sonrası “Sonucu incele”; eksik sporcu/etiket/hata için ilgili sürüm ve aralığa giden “Düzelt” eylemleri ekle. Kayıt → işleme → inceleme/etiketleme → veri seti → dışa aktarım adımlarında hangi aşamada olunduğu, neyin eksik olduğu, sonraki eylem açık olsun. Kullanıcıya yeni bir sekme seçtirip aynı kaydı yeniden aratma. Dönüşte filtre, seçim ve playhead korunsun.

### 9. İşleme kuyruğu ve sürüm üretimi

“Seçileni işle” doğrudan başlatıyor; uygulanacak model/derinlik/proxy/depolama ayarlarının özeti o ekranda yok. Ayarlar başka sayfada mevcut, bu özelliklerin backend'de hiç olmadığı iddia edilmiyor. Tamamlanmış bir kaydı farklı ayarla yeniden hesaplamanın belirgin bir kütüphane eylemi yok.

İşlenecek kaydın kimliğini ve etkin profil özetini göster; ayrıntıları açılabilir tut. “Yeni sürüm hesapla” yolu ekle. Seçim gerektiren eylemleri doğru etkinleştir; bir kaydı iki kez başlatma ve kuyruk/çalışıyor/tamamlandı durumlarını açıkça ayır. Satır bazlı ilerleme ve iptal gerekçesi erişilebilir olsun. Sayfadan ayrılınca işler görünmez hale gelmesin; shell iş göstergesi olsun. Kayıt ve hesaplamanın kaynak paylaşımı mevcut backend kurallarına uysun.

### 10. Tanılama gerçek sonucu göstersin

`studio/views/shell.py:_diagnostics` yanlış imzayla `collect_diagnostics(config)` çağırıyor; fonksiyon keyword-only `dataset_root`, `backend` alıyor. Hata yakalanıp `None` dönünce araç “henüz çalıştırılmadı” diyor.

Doğru servis çağrısını kur; gerekiyorsa arka planda çalıştır. “Başlatılmadı / çalışıyor / tamamlandı / başarısız” ayrımını ve hatanın yeniden denemesini göster. Başarısız sonucu boş sonuç olarak sunma. Diğer yardımcı araçlarda da seçili sürümün gerçekten ekrandaki kayıt olduğundan emin ol; eski review bağlamını tercih eden `_selected_run` yolunu kontrol et.

## P1 — modern görünümü oluşturan somut tasarım işleri

### Görsel tasarım brifi — beklenen görüntü ve his

Bu bölüm bir uygulama tekniği tarifi değildir. Kullanılacak Qt sınıfı, layout türü veya çizim yöntemi konusunda özgürsün. Burada tarif edilen şey son ürünün görünüşü, kullanıcıya verdiği his ve görsel davranışıdır. Önce iş akışı doğruluğunu koru, ardından bütün ekranları aynı tasarım sisteminin parçaları gibi yeniden ele al. Mevcut kutulara rastgele radius ve gölge eklemek bu hedefi karşılamaz.

#### Genel sanat yönü

KineCapture, veri toplama ve ayrıntılı hareket inceleme için kullanılan ciddi bir masaüstü stüdyosu gibi görünmeli. DaVinci Resolve'dan beklenen şıklık; siyah arka plan, çok sayıda panel veya renkli düğme kopyalamak değildir. Beklenen his şudur:

- Ekran açıldığında ilk bakışta video/iskelet/timeline gibi asıl çalışma içeriği öne çıkar; uygulama çerçevesi ve yardımcı kontroller geri planda kalır.
- Koyu temada kömür, grafit ve nötr gri yüzeyler arasında sakin bir derinlik vardır. Her bölüm kalın çerçeveli ayrı bir kutu gibi bağırmaz. Yakın işler aynı yüzeyde gruplanır; ayrı bağlamlar ton farkı, boşluk ve ince ayraçlarla anlaşılır.
- Yüzeyler tamamen düz ve tek renk bir duvar gibi görünmez; ana sahne, araç çubukları, denetçi ve alt zaman çizelgesi arasında ölçülü ton farkı bulunur. Gölge varsa hafif ve işlevseldir. Parlayan, oyuncak hissi veren, ağır gradientli veya neon bir görünüm istemiyorum.
- Geometri aşırı sert ve köşeli olmamalı. Mevcut arayüz neredeyse her kontrolü kalın kenarlı dikdörtgen bir kutuya dönüştürüyor. Paneller ve etkileşimli kontrollerde ölçülü yumuşak köşeler, yeterli iç boşluk ve daha sakin sınırlar kullan. Her elemanı bağımsız kart haline getirip mobil uygulama görünümü de oluşturma.
- Yoğunluk profesyonel masaüstü yazılımına uygun olsun: ekran ferah görünürken aynı anda gerekli bilgiye ulaşılabilsin. Büyük boş alanlarla bilgi saklanmasın; minik yazı ve sıkışık düğmelerle de “profesyonel” görünmeye çalışılmasın.
- Vurgu rengi az ve amaçlı kullanılsın. Seçim, aktif araç, ana eylem, kayıt ve kritik hata birbirinden ayrılmalı. Her checkbox'ın veya her başlığın aynı parlak mavi blok olması görsel önceliği yok ediyor.
- İkonlar aynı aileden, aynı optik ağırlıkta ve anlaşılır olsun. Metinsiz ikonlar yalnız alışılmış anlamı güçlü olduğunda kullanılsın. Oynat, kare ilerlet, başa/sona git, panel aç/kapat ve kayıt durumları bir bakışta ayrılabilsin.
- Tipografi üç açık düzey kursun: ekran/iş adı, seçili içeriğin esas bilgisi ve ikincil teknik ayrıntı. Teknik kimlikler ile şema/model ayrıntıları okunabilir fakat baskın olmayan monospace veya yardımcı metin olarak gösterilebilir.

Amaç Resolve'un birebir taklidi veya telifli varlıklarının kopyası değildir. Resolve'daki olgunluk, içerik merkezli hiyerarşi, koyu yüzeylerin kontrollü katmanlanması, zaman çizelgesinin güçlü görsel dili ve yoğun işlerde sakin kalan arayüz örnek alınmalı. Sonuç KineCapture'a ait bir görsel kimlik taşımalı.

#### Sabit ve sakin bir çalışma alanı

Bir bildirim geldiğinde mevcut arayüz sayfanın içine yeni bir container ekliyor. Bu container video görüntüleme alanını, 3B görünümü veya timeline'ı sıkıştırıyor; bütün splitter oranları ve kullanıcının gözünün alıştığı yerleşim bir anda değişiyor. Bilgi mesajı yüzünden görüntünün boyutu değişmemeli, timeline aşağı kaymamalı ve kullanıcının imleci altındaki kontrol yer değiştirmemeli.

Bildirimlerin beklenen görsel davranışı:

- Kısa başarı, bilgi ve uyarılar çalışma alanının üzerinde, içerik ölçülerini değiştirmeyen kompakt bir toast/banner katmanı olarak görünür. Video veya timeline'ın önünü gereksiz kapatmaz; güvenli bir köşede ya da üst araç çubuğunun hemen altında yüzer.
- Mesajın türü ikon, başlık, kısa metin ve ölçülü renk vurgusuyla anlaşılır. Büyük, tam genişlikte renkli bloklar kullanılmaz.
- Geçici bilgi mesajı bir süre sonra sakin biçimde kaybolur; kullanıcı isterse kapatabilir. Kaybolması gereken mesaj kalıcı panel yüksekliği tüketmez.
- Kullanıcı eylemi gerektiren hata veya veri kaybı riski kendiliğinden yok olmaz. Kısa bir ana açıklama, ayrıntı ve net eylem içerir; yine de sayfanın iskeletini iterek değiştirmez.
- Aynı olay tekrarlandığında üst üste çok sayıda kutu birikmez. Benzer bildirimler gruplanır veya mevcut mesaj güncellenir.
- Aktif kayıt, işlem ilerlemesi ve kaydedilmemiş etiket gibi sürekli durumlar geçici toast değildir. Bunlar sabit durum çubuğu/başlık alanında, yerleşimi önceden ayrılmış ve değişmeyen bir bölgede gösterilir.
- Bildirim açılırken/kapanırken hareket kısa ve ölçülüdür; animasyon odak çalmaz. Bildirim üzerinde fare varken okunmadan kaybolmaz.

Bildirim açık ve kapalı durumdaki ana video/timeline dikdörtgenlerinin ekran koordinatları ve boyutları aynı kalmalıdır. Bu, görsel kabul testinde ekran görüntüsü veya geometri ölçümüyle doğrulansın.

#### Tema bütünlüğü ve yüzeylerin tek sahibi

Bazı box/container yüzeyleri KineCapture temasından değil Windows'un yerel renklerinden geliyor. Koyu temada bu her zaman fark edilmese de açık temaya geçildiğinde uygulamanın içinde farklı tonlarda koyu adalar, beyaz native input şeritleri ve okunamaz yazılar oluşuyor. Tema değişimi yalnız üst kabuğun rengini değiştiren bir anahtar gibi görünmemeli.

Beklenen görüntü:

- Aynı temada ana pencere, sayfa zemini, tablo, liste, header, scroll alanı, viewport, açılır menü, tooltip, modal, yardımcı pencere, input, spin control, checkbox ve boş durumlar aynı renk ailesinden gelir.
- Koyu temada hiçbir kontrol yanlışlıkla parlak Windows beyazına dönmez. Açık temada hiçbir panel eski koyu temasını koruyup siyah bir ada oluşturmaz.
- Açık tema saf beyaz bir web formu gibi göz almamalı; sıcak veya nötr açık gri yüzeyler ve yeterli kontrastla profesyonel masaüstü görünümünü korumalı.
- Giriş alanları arka plandan ayırt edilir fakat sayfa boyunca uzanan parlak beyaz barlar gibi görünmez. Etkin, hover, focus, disabled ve hata durumları iki temada da aynı hiyerarşiyi taşır.
- 3B viewport ve video sahnesinin doğal olarak koyu kalması gerekiyorsa bu bilinçli bir medya yüzeyi olarak çerçevelenir. Yanındaki formun yanlış temada kalmış görünümüyle karıştırılmaz.
- Tema değişimi anında tamamlanır. Önceden oluşturulmuş sayfa, sonradan açılan sayfa, popup ve yardımcı pencere arasında eski temadan parça kalmaz.
- Renk kontrastı yalnız normal metinde değil; ikincil metin, pasif düğme, timeline etiketi, ince ayraç, focus halkası ve durum rozetlerinde de okunabilir olmalıdır.

Koyu → açık → koyu geçişini Ayarlar, Projeler, Yakalama, İşlenen Videolar, Etiketleme ve en az bir yardımcı pencere açıkken gözle kontrol et. Her ekran için aynı görsel sistem korunmalı. Windows sistem temasından gelen rastlantısal renk, ürün tasarımının parçası kabul edilmemeli.

#### Etiketleme ve timeline'ın görsel dili

Timeline, uygulamanın esas üretim alanlarından biridir; boş bir panelin üzerine renkli dikdörtgenler bırakılmış gibi görünmemeli. Kullanıcı bir hareket veya hata aralığının seçilebilir, taşınabilir ve uçlarından trimlenebilir olduğunu kullanım kılavuzu okumadan anlayabilmeli.

Aralık kutularının beklenen görünüş ve davranışı:

- Her hareket/hata aralığının başlangıç ve bitiş ucunda trim yapılabildiğini anlatan görünür tutamaçlar bulunur. Bunlar küçük dikey grip çizgileri, kontrastlı uç kapakları veya aynı anlamı açıkça veren başka bir işaret olabilir.
- Normal durumda tutamaç belli fakat sakin görünür; üzerine gelince daha belirginleşir. İmleç uca yaklaşınca trim imlecine dönüşür. Mouse1 basılı sürüklemede ilgili uç aktif görünür ve canlı önizleme hangi sınırın değiştiğini açıkça gösterir.
- Kutunun gövdesine gelmek ile ucuna gelmek görsel olarak farklıdır. Kullanıcı gövdeden seçim/taşıma, uçtan trim davranışını karıştırmamalı.
- Seçili aralık, hover aralık ve pasif aralık birbirinden net ayrılır. Seçim yalnız çok ince bir renk değişimine bağlı kalmaz; kenarlık, parlaklık veya tutamaç vurgusu da kullanılır.
- Çok kısa aralıkta iki trim tutamacı üst üste gelip kullanılamaz hale gelmez. Yakınlaştırma düzeyine göre minimum etkileşim alanı korunur ve hangi uca dokunulduğu anlaşılır.
- Trim sırasında başlangıç/bitiş kare veya timecode değeri yakınında küçük bir bilgi etiketi görünür; kullanıcı sınırı körlemesine sürüklemez. Snap gerçekleştiğinde kısa ve ölçülü bir görsel geri bildirim olur.

Renk sistemi sınıf bilgisini öğretmeli:

- Aynı hareket sınıfına ait bütün hareket aralıkları aynı temel renkte görünür. Örneğin tüm squat tekrarları aynı aileyi taşır; farklı hareket sınıfı başka bir renge geçer.
- Aynı hata sınıfına ait hata aralıkları kendi içinde aynı renkte görünür. Hareket rengi ile hata rengi birbirine karışmamalı; hata aralıkları ayrı track, desen, alt şerit, kenarlık veya ton davranışıyla “hareket”ten farklı bir veri türü olduğunu belli etmeli.
- Renk ataması proje ve yeniden açılış boyunca kararlı olmalı. Aynı sınıf her ekrana girişte başka renk almamalı.
- Palet, koyu ve açık temada video editörü hissine uygun, doygunluğu kontrollü ve birden fazla yan yana aralıkta ayırt edilebilir olmalı. Neon gökkuşağı görünümü oluşturma.
- Renk tek anlam taşıyıcısı değildir. Sınıf adı/kısa kodu, track konumu ve seçili durum işaretleri renk görme farklılıklarında da ayrım sağlar.
- Aralık içinde yeterli alan varsa sınıf adı gösterilir; alan daralınca metin zarifçe kısalır ve tooltip/denetçi tam adı verir. Yazı kutunun sınırları dışına taşmaz.

Timeline'ın bütünü zaman cetveli, playhead, track başlıkları, zoom düzeyi ve aktif araçla tek bir kompozisyon gibi görünmeli. Hareket ve hata track'leri sabit başlıklarla ayrılmalı; playhead bütün track'ler boyunca devam etmeli. Seçili video karesi, timecode ve playhead aynı konumu anlatmalı. Dalga biçimi olmayan boş alanlar “bitmemiş UI” izlenimi vermesin; ölçülü grid/cetvel ve track zemini çalışma alanını tarif etsin. Yakınlaştırıldığında daha ayrıntılı tick ve etiket, uzaklaştırıldığında daha sade bir cetvel görünmeli.

#### Ekranlara özgü kompozisyon beklentisi

- **Projeler:** Bir elektronik tablo gibi üç eşit boş kutu görünümü yerine proje → katılımcı → oturum ilişkisi açık bir master-detail akışı vermeli. Seçili proje ve katılımcı kuvvetli fakat sakin bir vurgu almalı. Adlar için alan ayrılmalı; tarih ve sayaçlar görsel ağırlığı ele geçirmemeli.
- **Yakalama:** Kamera görüntüsü sahnenin merkezidir. Kayıt modu, hedef katılımcı, görüntüde seçili kişi ve kayıt kontrolleri sahneyi çevreleyen tek bir operatör konsolu gibi görünmeli. Kayıt düğmesi ve süre uzaktan seçilebilir; açıklamalar görüntünün altında uzun bir hukuk metni gibi uzanmamalı.
- **Verileri Hesapla:** Bekleyen kayıtlar ile çalışan/tamamlanan işler görsel olarak ayrılır. Boş alanlar devasa iki tablo kutusu hissi vermemeli. Aktif işin ilerlemesi, modeli ve kalan süresi ilk bakışta bulunmalı; ikincil ayrıntı gerektiğinde açılmalı.
- **İşlenen Videolar:** Medya kütüphanesi hissi vermeli. Liste ile seçili sürüm önizlemesi dengeli; seçili öğe, model, kalite, sürüm ve etiket durumu anlaşılır bir hiyerarşi kurmalı. Sağ panel boşken ekranın büyük bir bölümünü amaçsızca tüketmemeli.
- **Etiketleme:** Video ve isteğe bağlı 3B sahne üstte, timeline altta, bağlama duyarlı denetçi sağda dengeli bir editör kompozisyonu oluşturmalı. Kullanıcı splitter'ları değiştirebilmeli; varsayılan oran 1920 × 1032 büyütülmüş kullanımda timeline'ı okunabilir, videoyu değerlendirmeye yeterli bırakmalı.
- **Veri Seti ve Dışa Aktarım:** Kalite/uygunluk durumu sıradan metin yığını değil, sakin rozetler ve neden–eylem ilişkisiyle taranabilir olmalı. Hazır, eksik ve dışarıda durumları aynı görsel ağırlıkta görünmemeli.
- **Ayarlar:** Tam genişliği kaplayan uzun beyaz/koyu input şeritleri yerine okunabilir bir ayar sayfası olmalı. Bölüm adı, seçenek, açıklama, maliyet ve etkinleşme zamanı aynı satır ailesinde düzenli görünmeli. Form “Windows kontrol galerisi” değil KineCapture'ın parçası gibi hissettirmeli.

#### Hareket, geri bildirim ve incelik

Arayüz statik bir kutular duvarı olmamalı; etkileşime verdiği küçük tepkiler kalite hissini oluşturmalı. Hover ile tıklanabilir alan anlaşılır, basılan düğme tepki verir, seçilen panel sakin biçimde vurgulanır, splitter tutamaçları bulunabilir olur. Geçişler hızlıdır ve işi yavaşlatmaz. Uzun fade, yaylanan animasyon, parallax veya dekoratif hareket istemiyorum.

Odak halkaları klavye kullanımında görünür, fare kullanımında gereksiz parlamaz. Disabled kontrol silikleşir fakat yazısı okunamaz hale gelmez. Boş durumlarda yalnız “boş” yazısı göstermek yerine bir sonraki makul eylem kısa biçimde belirtilir. Hata durumunda kırmızı tüm paneli boyamaz; problemin yeri ve ağırlığı anlaşılır.

Bu görsel revizyon sonunda kullanıcı uygulamayı ilk kez açtığında “geliştirici kontrollerinin yan yana dizildiği bir PySide ekranı” değil, uzun süre kullanılmak üzere tasarlanmış bütünlüklü bir hareket yakalama ve etiketleme stüdyosu görmelidir.

#### Görsel teslim ve değerlendirme

Kodlamaya başlamadan önce mevcut ekranlardan çıkardığın görsel sorunları kısa bir tasarım özetiyle grupla ve önerilen sistemin küçük bir stil panosu hazırla: koyu/açık yüzey hiyerarşisi, tipografi düzeyleri, vurgu/durum renkleri, köşe dili, kontrol durumları ve timeline sınıf paleti. Bu pano uygulama içi debug ekranı olmak zorunda değildir; tasarım kararlarını tutarlı uygulamak için teslim kanıtıdır.

Son teslimde en az şu büyütülmüş pencere görüntülerini ver: Projeler dolu durum, Yakalama bağlı ve kayıt halinde, İşleme aktif iş, Kütüphane seçili sürüm, Etiketleme dolu timeline (normal/hover/seçili/trim halinde), global bildirim görünürken Etiketleme, açık tema Ayarlar ve açık tema Etiketleme. Bildirim öncesi/sonrası çalışma alanının sıkışmadığını yan yana göster. Aynı sınıftan en az iki hareket ve aynı hata sınıfından iki hata aralığının kararlı renklerini göster.

Görsel kabul yalnız ekran görüntüsünün güzel bulunmasına dayanmasın: tema yüzeylerinde rastlantısal Windows rengi kalmadığını, metin kontrastını, focus durumunu, hit area'ları, bildirim sırasında geometri kararlılığını ve trim tutamaçlarının mouse davranışını test et. Buna rağmen son değerlendirme teknik testlerin ötesinde görsel bütünlük incelemesi içermeli; bütün ekranlar yan yana konduğunda aynı ürün ailesine ait görünmelidir.

### 11. Geniş ekran sütunları ve bilgi hiyerarşisi

1920 × 1032 pencerede bile proje adı yaklaşık 100 pikselde kesilirken “Oluşturuldu” sütunu yüzlerce piksel alıyor. Kütüphanede kısa durum/etiket alanları genişliyor, asıl kimlik/tarih alanları dar kalıyor. Boş alan eklemenin tek başına modernlik sağlamadığını dikkate al.

Ad/başlık gibi değişken uzunluklu sütunları esnet; tarih, sayaç ve durum için içerik temelli sınırlar tanımla. İlk görünümde kullanıcı sütunları elle düzeltmek zorunda kalmasın. Boyutları sonradan kişiselleştirebilsin. Satırda insanın tanıyacağı katılımcı + yerel tarih/saat + kayıt sırası/başlığı göster; uzun `take_...`/`run_...` kimlikleri ayrıntı ve kopyalama için bulunsun. Saat gösteriminde UTC/yerel tutarlılığı sağla: önceki 23:13 yerel kaydı tabloda 20:13 görünüyordu; `started_at[:16]` ile saat dilimini kaybetme.

### 12. Kontroller, tipografi ve görsel dil

Oynat ve bir kare ileri düğmeleri aynı `▶` karakteriyle gösteriliyor; küçük boyutta işlevleri ayırt etmek zor. Seçili kutular dolu renk blokları gibi; açılır liste okları ve spin denetimleri zayıf görünüyor. Yeni proje diyaloglarında Türkçe arayüz içinde `OK/Cancel` var ve ad alanı çok dar. Bazı pasif düğmeler etkin düğmeye çok yakın görünüyor.

Mevcut theme token sistemini kullanarak tutarlı vektör ikonlar, belirgin onay/radyo işaretleri, combo okları ve açık hover/focus/pressed/disabled durumları oluştur. Oynat, kare ileri, sona git birbirinden ayırt edilsin. Araç ipucu ve erişilebilir isim ekle; yalnız renkle anlam verme. Türkçe eylem isimleri kullan: örneğin “Proje oluştur / Vazgeç”. Ana bilgi, yardımcı bilgi ve teknik ayrıntıyı farklı hiyerarşide sun. Ana ekrandaki şema sürümü, ham enum adı ve nanosaniye gibi ayrıntıları uygun açılır ayrıntılara taşı; gerçek model seçimi gibi kullanıcının karar verdiği teknik bilgiyi saklama.

**Doğrulanmış tema hatası:** Ayarlar açıkken sağ üst tema düğmesiyle açık temaya geçildiğinde kabuk açık, form zemini koyu kaldı; koyu etiketler koyu zeminde kayboldu. `StudioWindow.apply_theme`, sayfa token güncellemesi, iç widget/scroll viewport paletleri ve önceden oluşturulmuş kontrolleri birlikte incele. Koyu temadan açık temaya geçişte bütün yüzeyler ve yazılar tutarlı güncellensin. Sonradan açılan ekranlar ve yardımcı pencereler de doğru temayı alsın. Sorunu yalnız başlangıç temasını sabitleyerek gizleme.

### 13. Etiketleme ergonomisi

Önce P0 açılışını çöz; sonra gerçek çalışan çizelgede şu davranışları tamamla/doğrula: zaman cetveli, playhead, hareket/hata/kalite izleri, seçili aralık vurgusu, sürükle-trim önizlemesi, anlamlı yakınlaştırma ve “Tüm kaydı göster”. Mevcut özellikleri yeniden yazmadan eksik bağlantıları tamamla.

Hareket/hata listesi ile çizelge karşılıklı seçilsin. Sınıf atama, başlangıç/bitiş, eklem durumu ve eksik alanlar görünür olsun. UI kare numarasını 1 tabanlı gösterirken formun 0 tabanlı değerleriyle kullanıcıyı şaşırtma; kaynak anchor/array indeksini değiştirmeden sunum dönüşümünü tek yerde tanımla. Kaydediliyor/kaydedildi/kaydedilemedi durumları ayrışsın. Undo/redo, sayfa değişimi ve kapanışta kayıt hatası etiketi sessizce kaybettirmesin; `ReviewViewModel.close` içindeki flush hatası sonrası store'u bırakma davranışını ayrıca test et.

Tekrarlı iş için görünür klavye kısayolu yardımı, yavaş oynatma ve hassas zaman/kareye gitme ekle. Metin alanında yazarken kısayollar etiketi değiştirmesin. “Sonraki eksik” doğru aralığa ve eksik alana gitsin. Tam ekran ana düzeninde gerekirse video/3B/timeline ağırlıkları kullanıcı tarafından değiştirilsin; gizli paneller render maliyeti üretmesin. Aralık kutularının trim tutamaçları, hover/aktif uç durumu ve sınıfa bağlı kararlı renk sistemi yukarıdaki görsel tasarım brifine uysun; bunlar isteğe bağlı süs değil, etkileşimin anlaşılabilirliği için kabul şartıdır.

### 14. Tek başına çekim ergonomisi

Kayıt ekranındaki preview + başlat/durdur temeli korunmalı. Kullanıcı tek başına kadraja girip çekim yapıyor: seçilebilir geri sayım, görünür geri sayımı iptal etme, klavye ile başlat/durdur, isteğe bağlı süre sonunda durdurma ve uzaktan okunur kayıt/süre göstergesi ekle. Önizlemeyi büyütme, yatay aynalama ve kadraj kılavuzu sun; bunlar ham kaydı dönüştürmesin. Aynalama/letterbox varsa kişi tıklamasını doğru kaynak koordinatına dönüştür ve test et.

Baş/ayak görünürlüğü gibi kadraj önerileri ancak gerçekten mevcut algılama verisine dayanıyorsa gösterilsin; güvenilir veri yoksa “kontrol edilemiyor” denilsin. Hafif 2B kaplamayı metrik/klinik ölçüm veya gerçek backend iskeleti gibi sunma. Bu maddeler tasarım gereksinimidir; gerçek ZED'de başarısı bu denetimde ölçülmedi.

### 15. Veri Seti, dışa aktarım ve ayarlar

Veri Seti ve Dışa Aktarım gerçek ekranlardır; yeniden yer tutucu üretme. Doğru çalışan uygunluk kontrollerini koru. Dışarıda kalan sürümler için okunur gerekçe ve ilgili düzeltmeye geçiş ver. Yazılacak kapsam, sürümler, hedef klasör ve çıktı seçenekleri yazmadan önce görünür olsun; oluşan paket için konumu açma/kopyalama ve sonuç özeti sağla. UI'da “hazır” görünmesi kanonik export doğrulamasını atlamasın.

Ayarları kayıt/önizleme/işleme/görünüm başlıklarında gezilebilir hale getir; uzun tek sütun formunda arama veya bölüm navigasyonu ekle. Kontroller bütün ekran genişliğini anlamsız biçimde kaplamasın. Değişikliğin “hemen / sonraki kayıt / yeniden bağlantı sonrası” etkisini göster. Kaydedilmiş tercih ile bağlı kameranın etkin profilini ayır; kaydedildi denilen fakat etkin olmayan ayarı saklama.

## Uygulama sırası ve teslim ölçütleri

1. P0 sorunlarına önce tekrarlanabilir regresyon testleri ekle ve düzelt. Yeni GUI görünümüne geçmeden veri sahibinin/modun/açık kaydın doğru olduğundan emin ol.
2. Proje açılışı, liste güncelliği ve sayfalar arası bağlamı tamamla.
3. Görsel tasarım brifini kısa bir stil panosu ve ana ekran kompozisyonlarıyla somutlaştır; büyütülmüş pencere için tek denetçi, sabit bildirim katmanı, panel düzeni, tema bütünlüğü, timeline görsel dili, sütun politikası ve kontrol görsellerini uygula.
4. Kişi seçimi → yeni processing sürümü → etiketleme → dışa aktarım yolunu tamamla.
5. Tek başına çekim ergonomisini ekle; mock doğrulamasını ve gerçek kamera doğrulamasını ayrı raporla.

Mevcut mimari sınırları koru: view → viewmodel → servis → backend. Görünümden SDK, JSON veya array işleme çağrısı yapma. Kanonik anchor, subject review, annotation, processing ve release sürümlerini incele; uydurma SDK metodu veya eklem verisi ekleme. Eksik veri NaN/eksik kalır. Ham kayıt değişmez, türetilmiş sürümler atomik oluşur. GUI'yi düzgün göstermek için bütün iskelet dizilerini RAM'e yükleme; memmap, özet piramidi, thumbnail, sınırlı önbellek ve gizli ekran zamanlayıcı politikalarını koru.

Performansı önce aynı makinede ölç, değişiklikten sonra aynı veri ve boyutlarda karşılaştır: açılış, kütüphane kaydırma, scrub gecikmesi, timeline trim, 3B çizim, idle CPU/RSS, kayıt FPS ve ayrı önizleme/kayıt kayıp sayaçları. Geçmiş rapordaki sentetik sayıları yeni ölçüm gibi kopyalama. Uzun işi GUI thread'inden çıkarmak adına her frame'i sınırsız kuyruğa koyma. Asenkron işlemlerde iptal, hata, sayfa/proje değişimi ve kapanış sonuçlarını test et.

Zorunlu kabul turu gerçek `QT_QPA_PLATFORM=windows` ve gerçek QtTaskRunner ile, **büyütülmüş pencerede** yapılmalı. `offscreen` geometri/font testi yeterli değildir. Proje → P0002 → ham kayıt → durdur → işleme → kişi/etiket düzeltme → veri seti → başarılı paket turunu, kamuya açık GUI eylemleriyle tamamla. Ayrıca kişi seçilmemiş, işleme başarısız, eksik proxy, yazma başarısız, kayıt sürerken başka sayfa, uygulamayı yeniden açma ve iki farklı sürüm arasında hızlı geçiş senaryolarını çalıştır. Test kolaylığı için özel view metodunu elle çağırıp gerçek açılış sırasını atlama.

Ana monitörde maximize, denetçi açık/kapalı, 3B açık/kapalı ve iki temada yerleşim kontrolü yap. Sonra desteklenecek diğer DPI/pencere boyutlarını raporla; denenmeyeni geçmiş sayma. Kullanıcı verisine dokunmadan ekran görüntülü önce/sonra kanıtı üret. Testlerde ortaya çıkan sorunları yalnız test beklentisini gevşeterek kapatma.

Teslim: çalışan kod, ilgili testler, büyütülmüş pencere görüntüleri, hangi bulgunun nasıl kapandığı, gerçekten çalıştırılan test ve ölçümler, kalan sınırlar. Her maddeye “uygulandı + test edildi / uygulandı ama doğrulanmadı / açık” durumu ver. Ürün akışının tamamlandığını görmeden yalnız birim testleri geçti diye “bitti” deme. `MEMORY_INDEX.md` içindeki Veri Seti/Dışa Aktarım yer tutucu bilgisini ve güncel açıkları düzelt; kalıcı yeni sonuçları hafıza politikasına uygun kaydet.
