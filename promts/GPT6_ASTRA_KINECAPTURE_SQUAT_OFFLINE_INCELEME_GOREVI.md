# GPT-6 Astra için KineCapture squat doğruluğu ve offline işleme inceleme görevi

> **Bu görevin izi:** [6T uygulama kaydı](../knowledge/archive/memory/6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · [squat/offline raporu](../knowledge/archive/reports/KINECAPTURE_SQUAT_OFFLINE_INCELEME_RAPORU_2026-09-10.md) · [Veri bütünlüğü ve kanıt](../knowledge/concepts/data-integrity.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


## Bu dosya nasıl kullanılmalı?

Yeni Codex görevini `C:\Users\gorke\Desktop\KineCapture` projesinde aç, model
olarak **GPT-6 Astra (`gpt-6-astra`)** seç ve bu mesajı gönder:

> `GPT6_ASTRA_KINECAPTURE_SQUAT_OFFLINE_INCELEME_GOREVI.md` dosyasının tamamını
> oku ve içindeki inceleme görevini uygula. Bu aşamada kodu değiştirme; önce
> mevcut uygulamayı, kodu, kayıtları, yan verileri ve logları salt okunur
> inceleyip kanıta dayalı alternatif planlar hazırla.

Uzun ve çok adımlı bir inceleme olduğu için yüksek veya xhigh reasoning uygundur.

---

## Astra'ya doğrudan görev

Sen, KineCapture'ın gerçek spor salonu kullanımına hazırlanması için teknik ve
ürün incelemesi yapan kıdemli bir görüntü işleme/masaüstü uygulama mühendisisin.
Çalışma dizinin:

`C:\Users\gorke\Desktop\KineCapture`

Bu görevde amaç kod yazmak değil; mevcut kanıtları yeniden denetlemek, eksik
incelemeleri yapmak ve kullanıcıya birkaç uygulanabilir çözüm planı sunmaktır.
Çalışmanı Türkçe yürüt ve sonuçları Türkçe yaz.

### Kullanıcının asıl hedefi

KineCapture, üniversitenin spor salonunda antrenörler tarafından gerçek
sporcularla, gerçek antrenman hızlarında veri toplamak için kullanılacak.
Bugünkü temel problem şudur:

- Gerçek hızdaki çekimde sistem yaklaşık 15 FPS'e düşebiliyor.
- Buna rağmen kaydedilen iskelet doğru olmayabiliyor; özellikle squatta bir veya
  iki bacak, dizden bükülmek yerine gövdeyle birlikte düz olarak aşağı iniyor.
- Gövde genellikle doğru görünüyor; belirgin sorun alt ekstremitede.
- Kullanıcı, bunun modelin squat örnekleriyle yeterince eğitilmemesinden
  kaynaklanabileceğini düşünüyor ama bu yalnızca bir hipotez.
- Kullanıcı, canlı çekimde yalnızca kameranın değişmez ham kaydını alıp iskelet,
  derinlik ve diğer türetilmiş verileri sonradan üretme modu öneriyor.
- Offline işleme daha ağır ve daha doğru modelleri kullanabilmeli, kaynak
  videonun bütün karelerini işlemeli ve düşük canlı FPS yüzünden veri
  kaybetmemeli.
- Kayıtta birden fazla kişi varsa hangi sporcunun işleneceği GUI'de güvenilir ve
  antrenörün kolay anlayacağı biçimde çözülmeli.
- Şu anda ZED kamera bağlı değil. Mevcut kayıtlar, loglar ve kodla ilerle;
  kamerayı bağlamayı bu analiz için ön koşul yapma. Planlar onaylandıktan sonra
  ZED ile yeni kontrollü testler yapılabilir.
- Kullanıcı, gerekirse daha sonra ZED'i bağlayıp Astra ile interaktif test
  yapmaya hazırdır. Astra monitörde görünür bir canlı kamera/iskelet penceresi
  açabilir; kullanıcı kamera karşısında squat yaparken birlikte kontrollü veri
  toplanabilir.
- Kullanıcı, offline önerisine ek olarak doğruluk veya performansı artırabilecek
  başka fikirler de bekliyor.

### Bu aşamanın sınırı

Bu turda kaynak kodu, şemaları, uygulama ayarlarını, identity DB'yi veya kullanıcı
verisini değiştirme. Ham kayıtları taşıma, yeniden adlandırma, silme ya da
üzerlerine çıktı yazma. İnceleme için geçici çıktı gerekirse benzersiz bir temp
klasörüne yaz ve bunun türetilmiş/geçici olduğunu açıkça belirt. Önce planları
sun; kullanıcı açıkça onaylamadan uygulamaya geçme.

---

## Zorunlu çalışma kuralları

1. Repository kökündeki `AGENTS.md` ve **`MEMORY.md` dosyasının tamamını** önce
   oku. Hafıza ile gerçek kod veya güncel disk durumu çelişirse gerçek durumu
   incele ve çelişkiyi görünür biçimde raporla.
2. Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
   oluşturma; paket kurma/güncelleme yapma.
3. Kullanıcı verisini ve değişmez ham kaydı koru. Salt okunur inceleme yap.
4. Çalışma ağacında kullanıcıya ait değişiklikler vardır. Bunları geri alma,
   düzeltme, formatlama veya üzerine yazma.
5. Uygulamayı açmak faydalıysa mevcut launcher ile açabilirsin, fakat kamera
   bağlı olmadığı için donanım bağlantısını zorlamamalısın.
6. Veri dosyalarını, logları, proje manifestlerini ve salt okunur SQLite proje
   kayıtlarını incelemek için kullanıcının parolasına ihtiyaç yoktur. GUI giriş
   ekranı gerçekten gerekli olursa kullanıcıdan parolayı sohbete yazmasını
   isteme; kullanıcının uygulamada kendisinin giriş yapmasını iste. Parolayı
   okuma, kaydetme veya loglama.
7. İnceleme sırasında görülebilecek sporcu görüntülerini yerel ve özel veri
   kabul et; kullanıcının açık izni olmadan dış servise yükleme veya paylaşma.
8. Resmî SDK davranışı ya da güncel bir model özelliği hakkında iddia kurarken
   güncel birincil kaynakları kontrol et ve bağlantı ver. Blog özeti veya forumu
   ana kanıt olarak kullanma.
9. Sonuç raporunda her önemli bulguyu şu sınıflardan biriyle işaretle:
   `Bugün doğrulandı`, `Önceki ölçüm`, `Güçlü çıkarım`, `Hipotez`, `Bilinmiyor`.
10. Bu analiz tamamlanınca, gerçekten yapılan incelemeyi, değişmeyen gerçek
    sürümleri, çalıştırılan kontrolleri ve yeniden doğrulanamayanları `MEMORY.md`
    içine ekle. Kod değiştirmediğini açıkça yaz.

---

## Kullanıcının önceki mesajları

### İlk sorun tanımı

> Capture uygulamasıyla alakalı iki önemli sorun var. Birincisi ve en önemlisi,
> squat hareketini kaydederken bacakların doğru tespit edilememesi. Squat
> sırasında bazen bir bacak bazen iki bacak dizlerden kıvrılması gerekirken düz
> bir şekilde gövdeyle birlikte aşağı iniyor. Sadece ayaklarda/bacaklarda sorun
> çıkıyor, gövdede sorun olmuyor. Landmark modelinin squat yapan insan
> görselleriyle eğitilmemiş olması ihtimali var ama başka bir sebep de olabilir.
> İkinci sorun, canlı çekimde hem iskelet çıkarmanın hem tespit yapmanın bilgisayara
> çok ağır gelmesi; hedef FPS yakalanamıyor. Kamerayı önce kaydedip iskeleti daha
> sonra çıkaran bir mod mantıklı olabilir. Böylece canlı yerine daha yüksek
> performanslı ve doğru modeller kullanılabilir. Önce kök nedeni ve offline
> yaklaşımın uygulanabilirliğini inceleyelim; şu anda kodu değiştirmeyelim.

### Yeni görev ve ürün beklentisi

> Bu konuşmaları, araştırmaları ve söylediklerimi GPT-6 Astra ile yeni bir
> sohbette kullanabileceğim bir Markdown dosyasına dönüştür. Astra uygulamayı
> açıp daha önce çekilmiş videolardan elde edilen datayı ve logları da inceleyerek
> ek bir inceleme yapsın. Veriyi incelemek için parolaya ihtiyaç olmaması gerekir;
> gerekirse hesabımı uygulamada ben açabilirim. Benim offline işleme önerime ek
> performansı artırabilecek fikirleri varsa söylesin ve birkaç çözüm planı
> hazırlasın. Gerçek sporcular gerçek hızda antrenman yaparken veri toplamak
> istiyoruz; şu anda yaklaşık 15 FPS ve yanlış veri kaydediyoruz. Planlarda GUI
> ve birden fazla kişi arasından işlenecek sporcunun seçimi gibi gerçek kullanım
> senaryoları mutlaka düşünülmeli. Uygulamayı üniversite spor salonundaki
> antrenörler kullanacağı için kullanım kolaylığı ve tasarım ayrıntıları önemli.
> ZED şu anda bağlı değil; önceki kayıtlarla inceleme yapılmalı. Planlardan sonra
> ZED ile test yapılabilir.

### Kullanıcının son açıklaması

> Son görülen veriler ayrı bir testti. Önceki, daha kötü sonuç veren kayıtları
> ben sildim. Gerekirse Astra ile ZED kamerayı bağlayıp interaktif test
> yapabilirim. Astra monitörümde iskeletimin çizildiği görünür bir pencere açar;
> ben karşısında squat yaparım ve test/analiz için birlikte veri toplarız.

---

## Önceki teknik incelemenin sonuçları

Bu bölüm önceki Codex incelemesinin aktarımıdır. Bunları başlangıç hipotezi ve
kanıt envanteri olarak kullan; mümkün olanları bağımsız doğrula. Özellikle eski
squat SVO dosyalarının bugünkü disk durumu aşağıdaki “Güncel disk gerçeği”
bölümünde açıklanmıştır.

### 1. İskeletin uygulama içinde bozulmadığına dair kanıt

- `src/kinecapture/camera/zed.py` içindeki
  `ZedCameraBackend._retrieve_bodies()` SDK'nın `body.keypoint`,
  `keypoint_2d` ve güven dizilerini eklem geometrisini değiştirmeden
  `BodyPose` içine geçiriyor.
- Uygulamada dizleri yeniden eşleyen, düzleştiren, önceki kareyle dolduran veya
  gizli biçimde yumuşatan bir dönüşüm bulunmadı.
- Hatalı squat karesinde SDK'nın kendi 2B diz noktası da hatalıydı. Dolayısıyla
  sorun yalnız 3B derinlik üretimi, kamera intrinsics'i, GUI bindirmesi veya
  eklem indeksinin uygulamada karışması değildi.
- Kaydedilmiş 3B noktaların kamera intrinsics'iyle yeniden izdüşümü ile SDK 2B
  noktaları arasındaki fark medyan `0.00 px`, p95 `0.01 px` ölçüldü.
- Hatalı sol diz ekleminin güveni yaklaşık `0.971` idi. Yalnız güven eşiğini
  yükseltmek bu yüksek güvenli yanlış pozu elemez.

### 2. En olası squat hata mekanizması

- Stereolabs'ın eğitim veri kümesi kamuya açık olmadığı için “squat verisiyle
  eğitilmedi” iddiası doğrulanamaz. Bunu gerçekmiş gibi sunma.
- Resmî açıklamaya göre önce görüntüden sinir ağıyla 2B keypoint tahmini
  yapılıyor; depth ve positional tracking ile 3B sonuç üretiliyor. Landmarklar
  ölçüm cihazıyla kalibre edilmiş anatomik eklem merkezleri değil, öğrenilmiş
  tahminlerdir.
- Tam önden çekimde squatın önemli diz fleksiyonu kamera derinlik ekseninde
  gerçekleşir. Kalça-diz-ayak bileği 2B görüntüde kısmen üst üste geldiğinde
  model yanlış, neredeyse düz bir bacak çözümüne kilitlenebilir.
- Body fitting, geçmiş ve kinematik kısıtlarla kayıp noktaları tamamladığı için
  yanlış çözümü zaman içinde sürdürebilir. Bu güçlü bir açıklamadır ama eğitim
  verisi bilinmediğinden mutlak kök neden iddiası değildir.
- Yerel SDK 5.4.1 için önceki introspection sonucu:
  `skeleton_smoothing=0.0`, `minimum_keypoints_threshold=0`,
  `allow_reduced_precision_inference=False`, `prediction_timeout_s=0.2`.
  Bu nedenle gözlenen örnek fazla smoothing veya reduced precision ile
  açıklanamamıştır.

### 3. Eski squat kayıtlarında yapılan offline A/B ölçümü

Kaynak SVO2 dosyalarına dokunulmadan `svo_real_time_mode=False`,
`HUMAN_BODY_ACCURATE`, `NEURAL_PLUS` ve body fitting açık olarak işlenmişti:

| Kayıt | Format | Sonuç | İşleme hızı |
|---|---|---|---|
| `take_20260902T075335_36a0` | BODY_34 | 4 dip squatın 3'ünde sol diz `178.8–179.0°`, yani yanlış düz | 176 grab / 174 gövdeli kare, 11.60 s, `15.17 FPS` |
| Aynı kayıt | BODY_38 | 4 tekrarın tamamında iki diz dipte yaklaşık `45–61°` | 176/176 gövdeli kare, 13.38 s, `13.16 FPS` |
| `take_20260902T075046_63e2` | BODY_34 | Dip medyanı sağ diz `178.4°`, yanlış düz | Önceden kaydedilmiş çıktı |
| Aynı kayıt | BODY_38 | Sol `59.6°`, sağ `57.2°`; 198/198 gövdeli kare | Offline replay |

Bu sonuç BODY_38'i squat için güçlü aday yapar. Fakat iki kayıt, tek sporcu ve
tek kamera düzeni genelleme için yeterli değildir. Daha fazla sporcu, kıyafet,
mesafe, ışık ve kamera açısıyla A/B gerekir. Ayrıca offline işleme, aynı BODY_34
modelinin semantik hatasını kendi başına düzeltmedi; yalnız bütün kaynak
karelerinin işlenmesini sağladı.

### 4. Canlı performans ölçümü

Sorun görülen eski profil:

- HD1080
- İstenen 25 FPS, kameranın bildirdiği gerçek kaynak 30 FPS
- `NEURAL_PLUS`
- `HUMAN_BODY_ACCURATE`
- `BODY_34`
- Body fitting açık
- Kayıpsız float32 canlı derinlik arşivi
- Native SVO H264 ve RGB proxy

Ölçülen HD1080 acquisition hızı `14.17–15.67 FPS`, maksimum kare boşluğu
`133–334 ms` idi. `take_20260902T113715_20ed` kaydında 610 kare / 42.99 s =
`14.17 FPS`; derinlik sıkıştırma kuyruğu 15 kare kaybettiği için take `PARTIAL`
kaldı.

Donanım bugün yeniden doğrulandı:

- NVIDIA GeForce RTX 2060, 6 GB VRAM
- Intel i7-10750H, 6 çekirdek / 12 thread
- 15.8 GB RAM
- NVIDIA driver 616.56
- `KineSynth`: Python 3.11.14
- ZED SDK 5.4.1

Mevcut canlı hat `camera.grab()` sonrasında renk, depth ve body tracking'i aynı
acquisition döngüsünde alıyor. Ayrı writer thread; skeleton JSONL, proxy ve
kayıpsız float32 depth chunk sıkıştırmasını yürütüyor. Böylece GPU'daki ağır
depth/body işleri ile CPU/diskteki ağır arşiv işi aynı anda gerçek zaman bütçesi
içinde yarışıyor.

Logdaki daha yeni fakat ham dosyası artık bulunmayan 3 Eylül kaydı:

- `take_20260903T124732_4a81`: 1078 kare / 45.9 s = `23.4 FPS`.
- Bugünkü kullanıcı tercihinde `HD720`, 30 FPS, `QUALITY` depth,
  `HUMAN_BODY_ACCURATE`, `BODY_38`, body fitting açık ve kayıpsız float32 depth
  arşivi görülüyor.
- Kullanıcı bunun önceki kötü squat testleriyle aynı deney olmadığını özellikle
  belirtti. Bu nedenle 23.4 FPS'i doğrudan “aynı senaryoda 15'ten 23.4'e
  iyileşme” kanıtı sayma. Yalnız daha yeni, farklı koşullardaki bir performans
  gözlemi olarak kullan. Take artık diskte olmadığı için profil, kalite, kayıp
  sayıları ve squat doğruluğu birlikte yeniden denetlenemiyor.

### 5. Offline işleme uygulanabilirliği

Resmî ZED dokümantasyonuna göre SVO/SVO2 dosyası açıldığında API canlı kamera
gibi davranır ve depth/body tracking gibi modüller playback üzerinde
çalıştırılabilir. Bu nedenle şu mimari teknik olarak mümkündür:

1. Canlıda yalnız değişmez stereo SVO2 kaydı ve gerekirse hafif bir RGB
   önizleme/kişi seçim ipucu üret.
2. Kayıt bittiğinde veya daha sonra, kaynak hızına yetişme zorunluluğu olmadan
   SVO'nun bütün karelerini sırayla işle.
3. BODY_38 veya daha ağır/alternatif model kullan.
4. Sonuçları ham kaydın üzerine değil, sürümlü ve provenance'lı bir `derived`
   çıktı olarak atomik yayımla.

Bu yaklaşım mantıklıdır; ancak mevcut uygulamada SVO input backend'i veya genel
bir post-processing job katmanı bulunmadı. Güvenli ürünleştirme için en az şu
öğeler gerekir:

- `awaiting_processing`, `processing`, `processed`, `failed` gibi açık işler;
- ilerleme, iptal, devam/yeniden dene ve crash recovery;
- kaynak SVO checksum'u, gerçek codec, SDK/model/parametre sürümü ve işleme
  provenance'ı;
- staging'e yazma ve yalnız tam/doğrulanmış sonuçta atomik publish;
- aynı ham kayıttan birden fazla iskelet sürümünü yan yana koruma;
- `reconstructed_offline` ayrımı; canlı ölçülmüş depth ile sonradan hesaplanan
  depth'i aynı gerçeklik sınıfı gibi göstermeme;
- annotation'ın hangi iskelet sürümüne bağlı olduğunun kaydı;
- offline kişi/track seçimi ve belirsizlik denetimi;
- uygulama kapanınca yarım işin güvenli kalması;
- disk tahmini, kuyruk sırası, başarısızlık mesajı ve tekrar çalıştırma.

Önceki tahmin: sınırlı proof-of-concept yaklaşık 2–4 iş günü; mevcut güvenlik,
GUI, şema, test ve recovery ilkeleriyle ürün entegrasyonu yaklaşık 1–2 hafta ve
orta-yüksek zorluk. Astra bunu kodu inceleyerek yeniden tahmin etsin; kesin
taahhüt gibi kullanmasın.

### 6. Kodda bulunan ilişkili sorunlar

- `src/kinecapture/camera/zed.py` içindeki
  `ZedCameraBackend.start_native_recording()` profilin
  `native_compression` seçimini kullanmak yerine hâlâ doğrudan
  `sl.SVO_COMPRESSION_MODE.H264` seçiyor. Manifest profil tercihini yazabildiği
  için beyan ile SDK'ya gerçekten verilen codec ayrışabilir.
- Aynı metodun docstring'inde H264 için “lossless-by-default” anlamına gelen
  tarihsel ifade vardır; H264 kayıplıdır.
- `configs/default.yaml` hâlâ SVO2'nin depth'i yeniden üretmesi nedeniyle ikinci
  depth arşivinin kazanç sağlamadığını söyler. Önceki gerçek donanım ölçümleri
  SVO replay depth'inin canlı ölçülmüş depth ile aynı olmadığını gösterdi.
- Kullanıcı arayüzü geçmişte HD1080 için desteklenmeyen 25 FPS gibi değerleri
  kabul edip kameranın gerçekte 30 FPS açmasını görünür biçimde engellemedi.

Bu maddeleri yeni mimari planında düzeltilecek ürün/provenance riskleri olarak
ele al, fakat bu analiz turunda düzeltme yapma.

---

## Güncel disk gerçeği — 2026-09-10

Bu bölüm özellikle önemlidir; eski hafızadaki yolların hepsi bugün geçerli
değildir.

### Kullanıcı tarafından silinmiş eski kötü squat ham kayıtları

Kullanıcı tercih dosyası:

`C:\Users\gorke\.kinecapture\user_state.yaml`

şu geçici dataset kökünü gösteriyor:

`C:\Users\gorke\AppData\Local\Temp\pytest-of-gorke\pytest-386\viewports0\datasets`

Fakat bu klasör bugün mevcut değil. Salt okunur identity DB sorgusunda iki proje
kaydı hâlâ bu artık bulunmayan geçici köke bağlı:

- `prj_20260902T072943_e359` — `KineSynth`
- `prj_20260903T124439_8b0e` — `Eklemtest`

2 Eylül squat take'leri ve 3 Eylül BODY_38 take'i bu geçici ağaçtaydı. Bugünkü
`C:\Users\gorke` taramasında bunların `.svo2` dosyaları bulunmadı. Bunların hâlâ
erişilebilir olduğunu varsayma ve eksikliği gizleme. Kullanıcı sonradan bu daha
kötü kayıtları kendisinin sildiğini ve 3 Eylül sonucunun ayrı bir test olduğunu
açıkladı; bu nedenle durumu istemsiz veri kaybı gibi sunma. Eski sonuçlar için
log, tanı PNG'leri ve önceki ölçüm notları kaldı. Ham klasörü geri getirme,
identity DB'den silme veya kullanıcı tercihlerini düzeltme işlemi bu ilk analiz
turunun kapsamı değildir.

### Hâlâ bulunan squat görsel kanıtları

Önceki tanıdan yedi PNG hâlâ burada:

`C:\Users\gorke\AppData\Local\Temp\kinecapture_squat_diag_20260902`

Özellikle:

- `take075335_p165.png`: görüntüde sporcunun iki dizi de squat dibinde bükülmüş.
- `take075335_overlay_p165.png`: BODY_34 çıktısında taraflardan biri neredeyse
  düz çizgi olarak gösteriliyor.
- `p150` ve `p171` görüntü/overlay çiftleri zaman komşuluğunu incelemek için var.

Bunlar görsel tanı kanıtıdır; ham SVO veya tam skeleton stream yerine geçmez.

### Hâlâ bulunan uygulama logu

`C:\Users\gorke\KineCapture\logs\kinecapture.log`

Dosya yaklaşık 544 KB; 20 Ağustos–3 Eylül aralığını içeriyor. Önemli satırlar:

- 2 Eylül kayıtlarının başlama/bitiş ve ölçülen FPS satırları;
- `take_20260902T075046_63e2` ve `take_20260902T075335_36a0` için yaklaşık
  15.3–15.4 FPS;
- `take_20260902T113715_20ed` için depth kuyruğunda 15 kayıp ve `PARTIAL`;
- 3 Eylül `take_20260903T124732_4a81` için 23.4 FPS.

Logları salt okunur incele. Log tek başına iskelet doğruluğunu kanıtlamaz fakat
performans zaman çizelgesini ve hata olaylarını doğrular.

### Hâlâ bulunan iki kalıcı SVO2 take

Kullanıcı profili altında bugün bulunan `.svo2` dosyaları yalnız şunlardır:

1. `C:\Users\gorke\KineCapture\datasets\projects\prj_20260821T111333_a60a\participants\P0001\sessions\ses_20260821T111428_c99a\takes\take_20260821T111845_4ed7`
   - BODY_34, HD720/30, `HUMAN_BODY_MEDIUM`, `NEURAL_LIGHT`
   - 230 kare, 7.67 s, 29.87 FPS, coverage 1.00
   - `raw/capture.svo2`, `derived/proxy.mp4`, `derived/skeleton.jsonl`,
     `quality/quality.json`, `take.json` mevcut
2. `C:\Users\gorke\KineCapture\datasets\projects\prj_20260820T164820_1e49\participants\P0001\sessions\ses_20260820T165034_c665\takes\take_20260820T165211_daeb`
   - BODY_34, HD720/30, `HUMAN_BODY_MEDIUM`, `NEURAL_LIGHT`
   - 668 kare, 22.27 s, 29.95 FPS, coverage 0.9177
   - aynı temel dosyalar mevcut

Bu iki take squat sorununun asıl örnekleri değildir. Yine de SVO playback,
offline işleme prototipi, frame/timestamp eşleme, codec okuma, bütün kareleri
işleme ve output şeması için güvenli salt okunur teknik örnek olabilir. Bunların
mevcut schema'sı uygulamanın bugünkü 0.10.0 şemasından eskidir; migration yazma.

### Güncel kullanıcı tercihi

Bugünkü `user_state.yaml`:

- backend `zed`
- HD720 / 30 FPS
- depth `QUALITY`
- `HUMAN_BODY_ACCURATE`
- `BODY_38`
- body fitting açık
- confidence 40
- native compression tercihi `H264`
- depth archive `float32_lossless`
- preview 30 FPS

Bu tercih yalnız bugünkü ayardır; eski take'lerin gerçek provenance'ı yerine
kullanılamaz.

---

## İncelenecek kod haritası

En az şu dosyaları gerçek davranış için oku:

- `src/kinecapture/camera/zed.py`
- `src/kinecapture/camera/base.py`
- `src/kinecapture/capture/service.py`
- `src/kinecapture/capture/subject_lock.py`
- `src/kinecapture/recording/take_writer.py`
- `src/kinecapture/recording/rgbd_archive.py`
- `src/kinecapture/playback/take_reader.py`
- `src/kinecapture/domain/project.py`
- `src/kinecapture/domain/models.py`
- `src/kinecapture/dataset/workspace.py`
- `src/kinecapture/gui/pages/capture.py`
- `src/kinecapture/gui/pages/review.py`
- `src/kinecapture/gui/pages/dataset.py`
- `src/kinecapture/gui/state.py`
- `src/kinecapture/core/config.py`
- `src/kinecapture/core/logging.py`
- `configs/default.yaml`
- ilgili capture, raw archive, subject lock, playback ve GUI testleri

Özellikle şunları çıkar:

- Canlı bir kare için GPU/CPU/disk adımlarının gerçek sırası ve thread sınırları.
- Hangi adımlar kayıt doğruluğu için zorunlu, hangileri yalnız önizleme/kolaylık.
- Body tracking kapalıyken SVO kaydının ve timestamp/index üretiminin nasıl
  sürdürülebileceği.
- Mevcut subject lock'ın body keypoint/ID'ye hangi noktalarda bağımlı olduğu.
- Raw-only take'in mevcut `Take`, `CaptureProfile`, state machine, manifest,
  checksum ve finalize sözleşmelerine etkisi.
- Offline skeleton sürümlerinin annotation/review/export ile nasıl
  ilişkilendirileceği.
- GUI'de yeni modun yerleşeceği doğal noktalar ve mevcut viewport kuralları.

Uygulamayı açarsan, kamera bağlı olmadığı için gerçek çekim başlatma. Var olan
kalıcı iki projeyi identity DB'ye kaydetme/içe aktarma gibi yazma işlemleri yapma.
Mevcut auth/dataset yolu nedeniyle GUI kayıtları göstermeyebilir; bunu veri yok
sonucu olarak yorumlama. Kod ve doğrudan dosya incelemesi ana yöntemdir.

---

## Yapılacak ek inceleme

### A. Squat hatasının kök neden sıralaması

Aşağıdaki ihtimalleri kanıt lehine/aleyhine değerlendir ve olasılık sırasına
koy:

- BODY_34 ile BODY_38 arasındaki model/topoloji farkı;
- tam önden görünümde sagittal hareketin gözlenebilirlik sorunu;
- self-occlusion, koyu kıyafet/zemin, ayakkabı ve düşük alt-vücut piksel alanı;
- 2B keypoint ağının yanlış tahmini;
- depth kalitesi veya depth mode;
- body fitting/prediction'ın yanlış pozu sürdürmesi;
- FPS düşüşü ve büyük zaman aralıklarının tracker sürekliliğine etkisi;
- yanlış eklem indeksi, 2B/3B projeksiyon, GUI overlay veya confidence ölçeği;
- H264 sıkıştırmanın olası etkisi;
- eğitim verisi dağılımı hipotezi.

Her biri için “hangi kanıt bunu doğrular veya çürütür?” sorusunu cevapla. Eğitim
verisi hakkında belgesiz kesin hüküm verme.

### B. Performans bütçesi

Canlı hattı şu sınıflara ayır:

- kamera grab/native SVO encoding;
- RGB retrieval ve preview kopyaları;
- depth compute/retrieval;
- body inference/fitting/tracking;
- skeleton serileştirme;
- proxy video;
- lossless float32 depth arşiv sıkıştırması;
- GUI repaint ve diğer kopyalar.

Mümkünse mevcut log/metadata/kodla hangisinin baskın olduğunu belirle. Kesin
timing yoksa ölçüm planı yaz; sayı uydurma. Resmî doküman, H264/H265'in NVENC ile
tam hız kayda düşük ek yük için tasarlandığını; NEURAL_PLUS'ın en ağır depth
seçeneği olduğunu söylüyor. Bu, doğrudan SVO capture-only modunun güçlü aday
olduğunu destekler, fakat yerel ölçümle doğrulanmalıdır.

### C. Mevcut kayıtlarla salt okunur deneyler

Squat ham SVO'ları bulunamazsa bunu blocker yapma. Hâlâ bulunan iki SVO üzerinde
şunların teknik fizibilitesini doğrulayabilirsin:

- `svo_real_time_mode=False` ile bütün kareleri sırayla işleme;
- SVO frame position, kamera timestamp ve output frame eşleme;
- BODY_34/BODY_38 veya FAST/MEDIUM/ACCURATE profil farkları;
- output'un ham take'e dokunmadan staging/temp alana yazılması;
- işlem yarıda kesilirse ham kaydın sağlam kalması;
- işlem hızının kaynak FPS'in altında olmasının veri kaybı anlamına gelmediği.

Bu eski videolar squat doğruluğunu kanıtlamaz. Deneyi yalnız mimari/performans
kanıtı olarak sınıflandır. Büyük türetilmiş dosyalar üretmeden önce disk alanını
hesapla; gereksiz tam depth arşivi üretme.

### D. Güncel resmî kaynak kontrolü

Başlangıç kaynakları:

- Body tracking overview:
  https://docs.stereolabs.com/docs/development/zed-sdk/modules/body-tracking
- Body Tracking API ve runtime parametreleri:
  https://www.stereolabs.com/docs/development/zed-sdk/modules/body-tracking/using-the-api
- Depth mode hız/doğruluk dengesi:
  https://docs.stereolabs.com/docs/development/zed-sdk/modules/depth-sensing/depth-modes
- Depth stabilization ve performans ayarı:
  https://docs.stereolabs.com/docs/development/zed-sdk/modules/depth-sensing/depth-settings
- Düşük çözünürlükte depth retrieval olanağı:
  https://docs.stereolabs.com/docs/development/zed-sdk/modules/depth-sensing/using-the-api
- SVO recording/playback ve NVENC:
  https://docs.stereolabs.com/docs/development/zed-sdk/modules/camera/recording

Bugünkü SDK sürümü 5.4.1 ile belge sürümü arasındaki farkları not et. Bir seçenek
yalnız daha yeni SDK'da varsa mevcut uygulama için hemen kullanılabilir gibi
sunma.

---

## İstenen çözüm planları

En az üç, tercihen dört uygulanabilir plan hazırla. Her plan yalnız algoritma
değil; veri sözleşmesi, güvenlik, GUI, çoklu kişi, performans, doğruluk, disk,
uygulama zorluğu ve test stratejisi içermeli.

### Plan 1 — Düşük riskli kısa vadeli iyileştirme

Mevcut canlı mimariyi tümden değiştirmeden ulaşılabilecek en güvenli iyileşmeyi
tanımla. Şunları değerlendir:

- desteklenen çözünürlük/FPS kombinasyonlarını GUI'de doğrulamak;
- BODY_38 kullanmak;
- HD720 ve daha hızlı depth modu;
- preview FPS'i acquisition FPS'ten ayırmak;
- yalnız önizleme için depth'i daha düşük çözünürlükte almak;
- depth stabilization, reduced precision, tracking modeli ve fitting için
  kontrollü A/B;
- kamerayı tam önden değil 30–45° oblik veya yandan yerleştirme protokolü;
- yüksek güvenli ama kinematik olarak imkânsız dizler için kalite uyarısı.

Amaç, mevcut sistemin ne kadar kurtarılabileceğini görmek; 30 FPS garantisi
verme.

### Plan 2 — Raw-only capture + tam offline BODY_38

Kullanıcının ana önerisini ürün seviyesinde tasarla:

- canlıda değişmez SVO2 + hafif RGB önizleme;
- depth/body tracking ve tam proxy üretimini offline'a taşıma seçenekleri;
- işlem kuyruğu, öncelik, gece işleme, pause/resume/cancel/retry;
- kaynak checksum'u ve actual codec provenance'ı;
- sürümlü derived skeleton/depth;
- atomik publish ve crash recovery;
- annotation başlamadan önce/sonra yeniden işleme kuralları;
- kalite kontrol ve “işlenmeye hazır / işleniyor / inceleme gerekli / tamam”
  durumları.

Bu planın hedefi capture'ın kaynak FPS'i kaçırmaması ve offline sürenin uzun
olmasının kabul edilebilir olmasıdır.

### Plan 3 — Hibrit canlı kişi seçimi + offline yüksek doğruluk

Raw-only modun gerçek spor salonu sorununu çöz:

- Çekimden önce antrenör RGB görüntüsünde sporcuyu tıklar.
- Canlı tam skeleton yerine düşük çözünürlüklü/düşük frekanslı hafif person
  detector + bounding-box tracker yalnız bir **seçim ipucu** üretir.
- Bu ipucu ground truth değildir; SVO ve timestamp ile audit edilir.
- Offline ilk geçiş bütün kişi track'lerini çıkarır ve canlı ipucunu adaylarla
  eşler.
- Eşleşme güçlü değilse sessizce başka kişiye geçmez; koçtan onay ister.

Bu plan, mevcut subject lock'ın eş-görünürlük ve audit fikirlerini yeniden
kullanabilir ama canlı ZED skeleton'a bağımlı olmak zorunda değildir. Yüz tanıma
ve kayıtlar arası biyometrik veritabanı önermeden çöz.

### Plan 4 — Doğruluk odaklı gelişmiş seçenek

Maliyet ve karmaşıklığı açıkça yazarak şu seçeneklerden en anlamlı olanı
tasarla:

- BODY_38 ana model + hata yakalandığında alternatif modelle yeniden işleme;
- 2B RGB pose modeli + stereo triangulation/depth fusion;
- iki kamera/çoklu görüş;
- squat özel kalite denetleyicisi ve model-agnostic tekrar işleme;
- ayrı güçlü işleme bilgisayarı veya kuyruklu iş istasyonu.

Canonical skeleton'ı sessizce kural tabanlı “düzeltme”. Şüpheli diz açısını
işaretle, alternatif sürüm üret veya kullanıcı incelemesi iste; ham/model
çıktısının üzerine açıklamasız sentetik değer yazma.

---

## Çoklu kişi için zorunlu GUI tasarımı

Planların her birinde aşağıdaki gerçek kullanım akışını somutlaştır:

1. Antrenör katılımcıyı seçer ve Capture ekranına gelir.
2. “Kayıt modu”nda anlaşılır seçenek görür:
   - `Hızlı kayıt · İskeleti sonra çıkar (önerilen)`
   - `Canlı iskelet · Daha yüksek sistem yükü`
3. Raw-only modda ana ekran teknik ayrıntıyla dolmaz. Büyük ve net olarak:
   seçilen katılımcı, kamera görüntüsü, disk/süre, kayıt durumu ve olası kişi
   belirsizliği görünür.
4. Birden fazla kişi varsa kayıt öncesi sporcuyu tıklama veya kayıt sonrasında
   seçme akışı vardır.
5. Offline ilk geçişten sonra GUI; her track için temsilî küçük görüntüler,
   görünme süresi, başlangıç/bitiş ve çakışma/belirsizlik bölgeleri gösterir.
6. Koç “İşlenecek sporcu”yu bir kez seçer; seçim timeline boyunca önizlenir.
7. Track kayboluyor, ID değişiyor veya iki aday benzerse ilgili zaman bölgesi
   sarı/kırmızı gösterilir ve onay gerekir. Sessiz fallback yoktur.
8. İş başlatılınca ilerleme, tahmini süre, kuyruk sırası, iptal ve daha sonra
   devam et seçenekleri vardır.
9. Tamamlanınca koç teknik model adları yerine `İskelet hazır`, `4 bölüm insan
   kontrolü istiyor`, `Kayıt eksiksiz işlendi` gibi sonuç odaklı dil görür.
10. Teknik ayrıntı, model sürümü, checksum ve parametreler açılır “Tanılama /
    Ayrıntılar” bölümündedir; ana akış antrenörü bunlarla yormaz.

Alternatif kişi seçme yaklaşımlarını karşılaştır:

- çekim öncesi hafif canlı tracker;
- tamamen offline contact sheet/track seçimi;
- ikisinin hibriti;
- tek-sporcu çekim alanı protokolü.

Her yaklaşım için yanlış kişi riski, GPU yükü, antrenör adımı ve gizlilik
etkisini yaz.

---

## Offline dışında özellikle değerlendirilecek performans fikirleri

Kullanıcının önerisini tekrarlamakla yetinme. En az aşağıdakileri değerlendir ve
hangilerini önerdiğini kanıtla:

- Native SVO kaydını inference/depth retrieval'dan tamamen ayırmak.
- Canlı RGB preview'ı düşük FPS veya düşük çözünürlükte sunmak; kaynak SVO
  hızını düşürmemek.
- Preview/proxy üretimini mümkünse sonradan yapmak.
- Canlı kayıpsız float32 depth sıkıştırmasını raw-only modda kaldırmak; çünkü
  canlı depth hiç ölçülmüyorsa kaybedilecek bir canlı measurement yoktur.
- H264, H264_LOSSLESS ve başka codec seçeneklerini kalite/boyut/NVENC açısından
  A/B test etmek; koddaki hardcode'u gelecekte düzeltmek.
- Her kamera çözünürlüğü için yalnız desteklenen FPS değerlerini sunmak.
- Kuyruk/backpressure ve disk yazımını ayrı ölçmek; toplam FPS yerine aşama
  timing'leri toplamak.
- Offline işte kaynak karelerin hepsini işlemek ve sonuçta frame/timestamp
  coverage doğrulamak.
- Offline'da tam precision, canlı seçim ipucunda gerekirse reduced precision
  veya FAST model kullanmak.
- BODY_38 ana çıktı; kinematik kalite kapısı başarısızsa alternatif model ya da
  farklı parametreyle yeniden işleme.
- Sol/sağ diz simetrisi, zamansal süreklilik, eklem hız sınırı ve squat fazı
  gibi kontrolleri **hata tespiti/QC** olarak kullanmak; canonical noktaları
  sessizce değiştirmemek.
- Kamera yüksekliği, mesafe, 30–45° oblik açı, tam beden/ayak görünürlüğü ve
  aydınlatma için antrenör odaklı kurulum rehberi.
- Ölçüm doğruluğu bilimsel olarak kritikse tek kamera iskeletini mutlak anatomik
  ground truth saymamak; çoklu görüş veya harici doğrulama maliyetini açıkça
  belirtmek.

---

## Planların karşılaştırma biçimi

Her plan için tek tabloda şu alanları ver:

- kısa açıklama;
- beklenen canlı capture FPS etkisi;
- beklenen squat doğruluğu etkisi;
- çoklu kişi çözümü;
- antrenör GUI akışı;
- depolama maliyeti;
- işlem süresi ve kuyruk davranışı;
- şema/provenance etkisi;
- kod değişikliği büyüklüğü;
- test zorluğu;
- ana risk ve geri dönüş yolu;
- tahmini iş yükü (aralık olarak, varsayımlarla);
- “hemen / sonra / araştırma” önceliği.

Ardından tek bir önerilen yol seç. Öneri mümkünse aşamalı olsun:

- Faz 0: veri yollarını güvenli kalıcı köke alma ve gözlemleme araçları;
- Faz 1: küçük, doğrulanabilir capture-only teknik spike;
- Faz 2: offline BODY_38 worker ve sürümlü derived output;
- Faz 3: coach-friendly çoklu kişi/iş kuyruğu GUI'si;
- Faz 4: gerçek ZED A/B ve saha pilotu;
- Faz 5: gerekirse alternatif model/çoklu görüş.

Her faz için “bitti” sayılma kriterleri ve geri alma/başarısızlık davranışı yaz.

---

## Gelecekteki ZED test planı

Kamera bugün bağlı olmasa da planlardan sonra uygulanacak kontrollü test matrisini
hazırla. En az şunları içersin:

- en az 5 sporcu; farklı boy, kıyafet ve vücut yapısı;
- normal antrenman hızında squat;
- tam ön, 30–45° oblik ve yan açı;
- BODY_34 ve BODY_38;
- HD720 ve gerekirse HD1080;
- uygun depth modları;
- live ve raw-only/offline karşılaştırması;
- tek kişi ve arka planda başka insanlar;
- seçili sporcunun kadrajdan çıkıp geri dönmesi;
- farklı SVO codec profilleri;
- kaynak kare sayısı, işlenen kare sayısı, timestamp gap, acquisition FPS,
  queue loss, tracking coverage, çoklu kişi doğruluğu;
- squat diplerinde manuel referans diz açısı/2B işaretleme veya daha güçlü bir
  referans yöntem;
- yüksek güvenli yanlış iskelet oranı;
- yanlış kişiye bağlanma oranı;
- antrenörün görevi tamamlama süresi ve hata sayısı.

Tek bir başarılı video yeterli kabul edilmemeli. Önceden başarı kriterlerini
tanımla; örneğin capture'da kaynak FPS'e yakın tam kare kapsamı, sıfır sessiz
kayıp, yanlış kişi seçiminin sıfır olması ve BODY_38 iyileşmesinin sporcular
arasında tekrarlanması.

### Kullanıcıyla interaktif ZED testi yapma yetkisi ve akışı

Mevcut dosya/log incelemesini tamamladıktan sonra karar için yeni donanım kanıtı
gerekiyorsa kullanıcı interaktif teste açıkça izin vermiştir. Şu sırayı izle:

1. Önce kullanıcıya hangi belirsizliği çözeceğini, kaç kısa klip alınacağını ve
   yaklaşık süreyi söyle. ZED'i bağlamasını ve fiziksel olarak hazır olduğunu
   onaylamasını iste.
2. Yeni veri almadan **önce** output kökünü doğrula. Bugünkü tercih hâlâ geçici
   ve artık bulunmayan `pytest-386` klasörüne işaret ediyor. Yeni kayıtları bu
   geçici köke yazma. Kullanıcıyla kalıcı bir test proje konumu seç; mevcut iki
   kalıcı projeyi değiştirme ve eski take'lerin üzerine yazma.
3. Uygulamayı veya güvenli tanı görüntüleyicisini kullanıcının monitöründe
   **görünür** aç. Kullanıcı canlı RGB ve çizilmiş iskeleti görebilmeli. Gizli
   pencerede fiziksel hareket testi yürütme.
4. GUI giriş isterse parola isteme veya ekrandan okumaya çalışma. Kullanıcı
   hesabını uygulamada kendisi açabilir; giriş tamamlanınca devam et.
5. Kamera bağlantısı, tam beden ve ayak görünürlüğü, ışık, mesafe, kamera
   yüksekliği ve disk alanı için kısa ön kontrol yap. Kayıt başlamadan önce net
   biçimde “hazır” sinyali ver; kullanıcı hazır olmadan otomatik kayıt başlatma.
6. İlk oturum kısa ve kontrollü olsun. Önerilen başlangıç:
   - sabit profil ve açıyla 8–10 squat;
   - mümkünse BODY_34 canlı referans klibi;
   - aynı koşullarda BODY_38 canlı referans klibi;
   - değişmez SVO üzerinden BODY_34/BODY_38 offline karşılaştırması;
   - ardından yalnız gerekliyse 30–45° oblik açı tekrarı.
7. A/B sırasında çözünürlük, gerçek kamera FPS'i, depth modu, body modeli,
   body formatı, fitting, confidence, codec ve kamera açısı gibi tek tek
   değişkenleri manifest/notta açık tut. Aynı anda birden fazla değişkeni
   değiştirip sonucu tek nedene bağlama.
8. Kayıt sürerken kullanıcıya anlaşılır canlı durum göster: gerçek acquisition
   FPS, kayıt kaybı, iskelet görünürlüğü ve seçilen kişi. Teknik ayrıntılar ayrı
   panelde olabilir.
9. Her klipten sonra dosyanın gerçekten var olduğunu, finalize/partial durumunu,
   kare ve timestamp kapsamını ve checksum'u doğrula. Yeni ham SVO'yu değişmez
   tut; offline çıktıyı ayrı staging/temp/derived alana yaz.
10. Test sırasında ağrı, dengesizlik, kamera/kablo güvenliği veya kullanıcıdan
    durma isteği olursa kaydı güvenli kapat. Bu bir klinik değerlendirme değildir.
11. Test bittiğinde pencereyi ve kamerayı güvenli kapat; hangi kliplerin
    alındığını, hangilerinin karşılaştırılabilir olduğunu ve sonuçların nereye
    yazıldığını kullanıcıya özetle.

İnteraktif test izni, kaynak kodunu değiştirme veya büyük mimariyi uygulama
izni değildir. Önce mevcut uygulamayla ölçüm yap; yeni özellik geliştirme için
ayrıca kullanıcı onayı al.

---

## Beklenen nihai çıktı

Kod değiştirmeden önce kullanıcıya şu yapıda bir rapor ver:

1. Kısa sonuç: en olası kök neden ve en mantıklı ürün yönü.
2. Bugünkü veri envanteri ve eksik/kaybolmuş kayıt gerçeği.
3. Uygulama + log + kalıcı take incelemesinde yeni buldukların.
4. Kök nedenlerin olasılık sırası ve kanıt tablosu.
5. Canlı performans darboğazının aşama aşama açıklaması.
6. En az üç planın karşılaştırma tablosu.
7. Önerilen aşamalı yol haritası.
8. Her faz için coach-friendly GUI akışı ve failure states.
9. Planlardan sonra uygulanacak ZED A/B test protokolü.
10. Bilinmeyenler ve kullanıcıdan daha sonra gerekebilecek bilgiler.

Sonuçta şunlara açık cevap ver:

- Hata gerçekten “model squat görmedi” diye açıklanabilir mi, yoksa elimizdeki
  kanıt neyi daha güçlü söylüyor?
- BODY_38 bulgusu ne kadar güvenilir ve ne kadar genellenebilir?
- Offline mod yalnız FPS'i mi çözer, yoksa doğruluk için hangi ek koşullar
  gerekir?
- Raw-only capture gerçek kaynak FPS'e ulaşmak için yeterli mi; başka hangi
  işler canlı hattan çıkarılmalı?
- Çoklu kişi problemi antrenörü yormadan nasıl çözülür?
- İlk uygulanması gereken en küçük, geri alınabilir ve ölçülebilir değişiklik
  nedir?

Raporu verdikten sonra dur ve kullanıcı onayını bekle. Henüz kod uygulama.

---

## Mevcut sürümler ve çalışma ağacı

Bugün gerçek koddan doğrulanan sürümler:

- uygulama/package: `0.10.0`
- project: `1.1.0`
- session: `2.0.0`
- take: `1.1.0`
- skeleton stream: `1.1.0`
- annotation: `2.2.0`
- release: `2.2.0`
- label: `2.0.0`
- feature spec: `1.0.0`
- raw archive: `1.0.0`
- identity SQLite: `1`

Bu görev dosyası hazırlanırken görülen kullanıcıya ait mevcut çalışma ağacı:

```text
 M MEMORY.md
 M src/kinecapture/gui/widgets/label_dialogs.py
 M tests/test_shell_chrome_gui.py
?? tests/test_label_dialog_class_creation.py
```

Bu değişiklikleri koru. Yeni inceleme sırasında farklı dirty dosyalar varsa
önce kullanıcı işi kabul et ve yalnız kendi açıkça oluşturduğun geçici/rapor
çıktılarını yönet.

## Bu görev dosyasını hazırlarken yapılan doğrulamalar

- `MEMORY.md` ve `AGENTS.md` tamamen okundu.
- Gerçek app/schema sürümleri kaynak koddan yeniden okundu.
- Kullanıcı tercih dosyası ve identity DB yalnız salt okunur incelendi.
- Kullanıcı profili altında `.svo`/`.svo2` envanteri çıkarıldı.
- İki kalıcı take'in `take.json`, `quality.json` ve dosya envanteri okundu.
- Uygulama logunda 2–3 Eylül performans ve kayıp olayları doğrulandı.
- Squat tanı PNG'leri bugün yeniden görsel olarak açıldı.
- ZED SDK, Python ve donanım bilgileri yeniden sorgulandı.
- Resmî Stereolabs body tracking, depth ve SVO belgeleri yeniden kontrol edildi.
- Uygulama kaynak kodu, kullanıcı ayarı, identity DB ve ham kayıtlar
  değiştirilmedi.
- Pytest, self-test ve canlı ZED testi çalıştırılmadı; bu bir inceleme/handoff
  hazırlama turudur.
