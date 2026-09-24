# KineCapture Studio

Stereolabs ZED 2i ile hareket verisi toplama, inceleme, etiketleme ve makine
öğrenmesi için sürümlenmiş dataset üretme masaüstü uygulaması.

Windows · Python 3.11 · PySide6 · ZED SDK 5.4

---

## Durum

Uçtan uca dikey dilim çalışır durumda: **giriş → proje → katılımcı → kayıt →
oynatma → tekrar segmentasyonu → etiketleme → dataset sürümü.** Teknik çekim
oturumu kullanıcıdan gizlenir ve arka planda otomatik yönetilir. Akış hem
gerçek ZED 2i donanımıyla hem de donanımsız sentetik backend ile çalışır.

| Bileşen | Durum |
|---|---|
| SQLite kullanıcı kimliği, güvenli şifre doğrulama ve proje erişimi | Çalışıyor |
| Tek Sistem Sahibi + normal kullanıcı self-registration | Çalışıyor |
| Proje erişimine göre filtreleme ve otomatik operatör bağlama | Çalışıyor |
| Sentetik (mock) backend | Çalışıyor, deterministik, testlerin temeli |
| ZED 2i backend (RGB / derinlik / vücut takibi / SVO2) | Çalışıyor, gerçek donanımda doğrulandı |
| Kayıt, finalize, checksum, yarım kayıt kurtarma | Çalışıyor |
| Senkron oynatma + zaman çizelgesi | Çalışıyor |
| Hareket segmentasyonu (oluştur/böl/birleştir/dışla, undo/redo) | Çalışıyor |
| İki seviyeli etiketleme (hareket + zamansal hata aralığı) | Çalışıyor |
| Etiketleme sırasında hata **ve hareket** türü oluşturma | Çalışıyor |
| Doğru/hatalı kararının hata aralıklarından türetilmesi | Çalışıyor |
| Zaman çizelgesinde sürükleme sırasında kare önizlemesi | Çalışıyor |
| Yönetici-only kalıcı proje silme (disk alanı boşaltır) | Çalışıyor |
| Autosave + undo/redo | Çalışıyor |
| Dataset paneli + kalite bulguları | Çalışıyor |
| Sürümlü export (manifest / spec / mapping / fingerprint / doğrulama) | Çalışıyor |
| Seçilebilir iskelet özellikleri (kalite, tracker ham, koordinat, kemik, hız, açı, simetri, özet) | Çalışıyor |
| Export ekranında aranabilir özellik seçimi + presetler | Çalışıyor |
| Zorunlu ham RGB-D arşivi (ölçülen derinlik + SVO2) | Çalışıyor, gerçek donanımda doğrulandı |
| Görüntüye tıklayarak kişi seçimi ve kalıcı kişi kilidi | Çalışıyor, gerçek donanımda doğrulandı |
| Sürekli aktivite dataseti | **Yalnız okuma** — etiketleme arayüzü kaldırıldı, mevcut veri korunuyor |
| KineSynthV3 26-eklem eşleştirmesi | **Kısmi** — 23/26 eklem; 3 eklem eşleşmiyor ve NaN yazılıyor |
| Otomatik tekrar algılama, çok kameralı kayıt, çok uzmanlı consensus | Uygulanmadı |

### İki dataset üretim modu

Aynı kayıttan iki farklı dataset üretilebilir ve ikisi birbirinden bağımsızdır.

**1. Hareket örnekleri (varsayılan, eskiden beri).** Etiketli her tekrar ayrı
bir örnektir. Tekrarların dışındaki zaman datasete girmez.

**2. Sürekli aktivite (yalnız okuma).** Bir örnek = bir kaydın tamamı,
gerçek uzunluğunda. Her kare için "kişi ne yapıyordu" etiketi taşır.

> **Bu sürümde aktivite etiketleme arayüzü kaldırıldı.** İnceleme ekranı iki
> yazılabilir katmana indi: hareket ve hata. Aktivite şeridi, modu ve F3
> kısayolu yok.
>
> Daha önce girilmiş `activity_intervals` **silinmez, dönüştürülmez ve üzerine
> yazılmaz**: dosyada olduğu gibi durur, her kayıt sonrası korunur, ve
> export'ta hâlâ okunabilir. Export ekranındaki "Sürekli aktivite" seçeneği
> yalnızca projede aktivite etiketi taşıyan kayıt varsa açılır; olmayan bir
> projede seçilebilir olsaydı tamamı etiketsiz bir dataset üretirdi.

Export ekranında biri, diğeri veya (veri varsa) ikisi birden seçilebilir.
**Varsayılan yalnızca hareket örnekleridir.**

#### Aktivite sınıfları

| Sınıf | Kod | Anlam |
|---|---|---|
| `background` | 0 | Bekleme, nötr duruş, oturma |
| `transition` | 1 | Başlangıç pozisyonuna geçiş veya oradan çıkış |
| `target_exercise` | 2 | Tanınması istenen egzersiz (egzersiz kodu taşır) |
| `other_activity` | 3 | Yürüme, eğilme, kıyafet düzeltme gibi hedef dışı hareket |
| **etiketlenmemiş** | **-1** | **Hiç kimsenin bakmadığı zaman** |

**`unlabelled` bir sınıf DEĞİLDİR ve `background` sayılmaz.** Kimsenin
bakmadığı bir kareyi "spor yapılmıyor" saymak, modele etiketleyicinin dikkat
süresini öğretmek olur. Etiketlenmemiş zaman ayrı sayılır, zaman çizelgesinde
taralı çizilir, export'ta `activity_label_mask` ile ayrılır ve ancak açık
onayla arka plana çevrilebilir.

Aktivite durumları **karşılıklı dışlayandır**: iki durum aynı kareyi
paylaşamaz, çakışma hem GUI'de hem domain'de reddedilir. Bir `target_exercise`
aralığı bir hareket sample'ına **bağlanabilir**; bağlandığında sınırların tek
kaynağı hareketin kendisidir, ikisi bir daha ayrışamaz.

Hiç egzersiz içermeyen, tamamı `background`/`other_activity` etiketli bir
kayıt geçerli bir sürekli-aktivite örneğidir — negatif örnek olmadan
"egzersize başladı" kararı öğrenilemez.

### Etiket modeli

Etiketler **iki seviyelidir**:

1. **Hareket sample'ı** — kayıt içindeki bir tekrar. Yalnız **hareket türü**
   taşır. Bir kayıt birden çok hareket içerebilir; her biri ayrı bir export
   örneği olur.
2. **Hata aralığı** — seçili hareketin *içinde*, hatanın göründüğü zaman
   aralığı. Bir aralık tek bir hata sınıfı taşır. Aynı sınıf hareket boyunca
   tekrarlanabilir, farklı sınıflar çakışabilir (aynı anda iki hata),
   fakat hiçbir aralık ait olduğu hareketin dışına çıkamaz.

Bu, ileride eğitilecek modelin yalnızca "hatalı mı?" değil "hata hareketin
neresinde?" sorusunu da öğrenebilmesi içindir.

#### Doğru/hatalı kararı TÜRETİLİR

Kullanıcı bir harekete ayrıca "doğru" veya "hatalı" demez. Kural tektir:

- **Sınıflandırılmış hata aralığı yoksa** hareket **DOĞRU**'dur.
- **En az bir geçerli ve sınıflandırılmış hata aralığı varsa** **HATALI**'dır.
- **Son hata aralığı silinirse** hareket kendiliğinden yeniden DOĞRU olur.
- **Sınıfsız, sınırları geçersiz veya hareketin dışına taşan** bir hata aralığı
  hareketi doğru yapmaz; hareket **eksik** sayılır ve export'a girmez.

İki ayrı yer (insanın kararı ve zaman çizelgesindeki kanıt) aynı soruyu
yanıtladığı sürece birbiriyle çelişebilirdi, ve çelişen bir kayıtta hangi
yarısına inanılacağını söyleyen bir şey yoktu. Aralıklar gözlemdir; karar
onların özetiydi — artık doğrudan onlardan okunuyor.

`correctness` alanı dosyada yazılmaya devam eder, fakat **türetilmiş bir
önbellektir**: hiçbir düzenleme API'si onu aralıklardan bağımsız
ayarlayamaz ve kaydetmeden önce yeniden hesaplanır.

#### "Hiç hata yok" ile "kimse bakmadı" aynı şey değildir

İkisi de sıfır hata aralığı üretir, bu yüzden ayırmak için ek bir işaret
gerekir: hareket penceresinin **Kaydet**'i. Kaydetmek "bu hareketin sınıf
incelemesi bitti" demektir ve `reviewed_at` alanına yazılır. Sınıfı
kaydedilmemiş hareket, hata aralığı olmasa da **Etiketlenmedi** kalır.

**Hareket fazı kavramı kaldırılmıştır.** Eski kayıtlardaki faz değerleri
silinmez; `legacy` bloğunda saklanır fakat arayüzde ve yeni export
sözleşmesinde yer almaz.

#### Etkilenen eklem: node düzeyinde kanıt

Bir hata aralığı, hangi anatomik eklemlerle ilgili olduğunu da taşıyabilir.
Bu alan **bir eklem sınıflandırıcısı ürünü değildir**. Amacı tek şeydir:
ileride eğitilecek graph-temporal modele, hatanın iskeletin neresinde
göründüğüne dair **node-level evidence/relevance denetimi** vermek. Model
girdisinden hiçbir düğüm çıkarılmaz — `joints_xyz` bütün native topolojiyi
taşımaya devam eder; seçilen eklemler yalnız *denetim hedefi* ve *maske*
üretir.

Seçim, hata penceresindeki önden görünüşlü şema üzerinden yapılır. Şema
**sporcunun** sol/sağını gösterir: önden bakıldığı için sporcunun solu
ekranın sağında çizilir ve figürün üstündeki bant bunu yazıyla da söyler.
Durum yalnız renkle değil, seçili eklemin üzerindeki işaretle de belirtilir.

##### Topolojiden bağımsız rol sözlüğü

Depolanan değer eklem *indeksi* değil, **kanonik anatomik roldür**
(`left_knee`, `pelvis`, `right_shoulder`, …). Tek otorite
`kinecapture.features.roles` modülüdür; feature katmanı da aynı tabloyu
kullanır, yani açı tanımları ile eklem etiketleri aynı sözlüğü paylaşır.

Bunun sebebi karışık dataset'lerdir: aynı sürümde BODY_18 ve BODY_34 kayıtları
bir arada olabilir ve `19` numaralı düğüm ikisinde farklı yerdedir. Rol
kullanıldığında hedef uzayı tek kalır, native düğüme çeviri export
manifestindeki `role_to_native_node` tablosuyla yapılır.

Bir rolün karşılığı olmayan topolojide o rol **seçilemez**. `zed_body_18`
içinde pelvis yoktur, `mock_16` içinde topuk yoktur; pencere bu eklemleri
tıklanamaz gösterir ve repository katmanı yine de gelen böyle bir değeri
`role_not_in_skeleton` ile reddeder. Rol listesinde bulunmayan eklemler
export'tan **atılmaz**, yalnız hedef üretiminde kullanılmaz.

##### Boş olmanın dört ayrı anlamı

Eklem listesinin boş olması tek bir şey demek değildir, ve bunları tek bir
"boş" değerine indirmek eğitimde sessizce yanlış negatif üretirdi:

| `joint_status` | Anlamı | Node denetimi |
|---|---|---|
| `selected` | Bir veya daha fazla rol işaretlendi | **Pozitif kanıt** |
| `not_applicable` | İncelendi; bu hatanın belirli bir eklem hedefi yok | Maskelenir |
| `indeterminate` | İncelendi; görüntüden güvenilir belirlenemiyor | Maskelenir |
| `unreviewed` | Eklem yönünden hiç incelenmedi (eski veri dahil) | Maskelenir |

Maskelenmek **negatif etiket değildir**. `not_applicable` bir aralık, "bu
eklemler etkilenmedi" demez; "bu satır node kaybında kullanılmaz" der.

`selected` durumu boş rol listesiyle, boş olmayan rol listesi de başka bir
durumla saklanamaz: ikisi de `joint_status_without_roles` /
`roles_without_selected_status` ile reddedilir ve reddedilen düzenleme
aralığı hiç değiştirmez.

##### Etiket hazırlığı ile eklem kapsaması ayrı ölçülür

Eklem incelemesi yapılmamış bir kayıt **export'a girer** ve zamansal hata
sınıfı eğitimi bundan etkilenmez. Kapsama ayrı raporlanır:
`AnnotationRepository.joint_annotation_counts()` dört durumu sayar, zaman
çizelgesinin ipucu ile inceleme ekranının durum satırı seçili aralığın
durumunu yazıyla söyler. İkisini birleştirmek ya kullanılabilir veriyi
bloklardı ya da node denetimindeki boşluğu gizlerdi.

##### Eski dosyalarla uyum

Eski `affected_joints` alanı **kayıpsız korunur**. Değerlerin tamamı kanonik
role birebir çevrilebiliyorsa aralık `selected` olarak okunur; **bir tanesi
bile** çevrilemiyorsa hiçbiri çevrilmez, aralık `unreviewed` kalır ve ham
liste `legacy.affected_joints` içinde durur. Yarım bir göç, tamamlanmış gibi
görünürdü.

Bir dosyayı açmak onu **yeniden yazmaz**: eski kayıt açıldığında ne autosave
tetiklenir ne undo geçmişi oluşur, dosyanın baytları ve değişiklik zamanı
aynı kalır. Bu sürümün tanımadığı bir `joint_status` değeri de `unreviewed`
sayılır — bilinmeyen bir kelime, birinin verdiği karar gibi okunamaz.

---

## Kurulum

Bu proje bilgisayarda hâlihazırda bulunan **`KineSynth`** conda
environment'ında çalışır. Yeni environment oluşturulmaz.

```powershell
conda run -n KineSynth python -m pip install -e ".[dev]"
```

Bağımlılıklar (`KineSynth` içinde zaten mevcut): PySide6 6.10.1, NumPy 2.4.6,
PyYAML 6.0.3, opencv-python 4.12, pytest 9.0.1.

`pyzed` **bilinçli olarak pip bağımlılığı değildir**: ZED SDK ayrı kurulur ve
Python bağlaması SDK'nın `get_python_api.py` betiğiyle environment'a eklenir.
SDK yoksa uygulama yine açılır, sentetik backend ile tam olarak çalışır ve
tanılama ekranı eksiği açıkça bildirir.

## Çalıştırma

```powershell
.\scripts\run_app.ps1                 # GUI
.\scripts\run_app.ps1 -Backend zed    # ZED backend seçili açılır
.\scripts\diagnose.ps1                # ortam + SDK + kamera + iskelet tablosu
.\scripts\run_tests.ps1               # testler, dosya dosya (tek süreç: -SingleProcess)
```

Betikler `KineSynth` bulunamazsa başka bir environment'a düşmez; ne yapılması
gerektiğini yazıp durur.

Doğrudan CLI:

```powershell
conda run -n KineSynth python -m kinecapture --diagnose
conda run -n KineSynth python -m kinecapture --list-devices
conda run -n KineSynth python -m kinecapture --self-test
conda run -n KineSynth python -m kinecapture --self-check --report selfcheck.json
conda run -n KineSynth python -m kinecapture --backend mock
```

`--self-check` kurulumun açılabildiğini **konsolsuz ve pencere göstermeden**
denetler (paket, ayar, tema/yazı tipi/ikon kaynakları, Qt eklentisi, sandbox'ta
kurulan Studio penceresi, kullanıcı klasörleri, önizleme modelleri, ZED SDK) ve
sonucu JSON raporuna yazar; `pythonw.exe` ile de çalışır. `--expect-zed-sdk
5.4.1` ve `--require-preview-models` bu iki maddeyi zorunlu yapar.

### Windows kurucusu

Tek komutla (hiçbir şey indirmez; KineSynth'e dokunmaz, onu `C:\KCBuild\env`
altına klonlayıp çalışma zamanı paketlerine budar):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\build_installer.ps1 -NoOwnerSeed
```

Çıktı `dist\KineCapture-Setup-<sürüm>.exe` ve yanında içerik manifesti ile
tarama sonucu. Kurucu önce bilgisayarı denetler (ZED SDK birebir 5.4.1, NVIDIA
sürücüsü ≥ 580, CUDA/VC++ bileşenleri, disk, yol uzunluğu) ve uygun değilse
hiçbir şey değiştirmez; `/checkonly` yalnız denetler. Hazır sistem sahibi
hesabıyla gelen kurucu için önce kendi terminalinizde
`python scripts\release\make_owner_seed.py --title "<unvan>"` (parola iki kez
sorulur, yalnız özeti `dist\owner_seed.json`'a yazılır), sonra `-Fresh` ile
derleyin. Ayrıntı ve doğrulama:
[Faz B raporu](knowledge/reports/release-installer-phase-b-2026-09-23.md).

---

## Uygulama akışı

```text
Uygulamayı aç
    → Kullanıcı adı ve şifreyle giriş yap
    → Erişilebilir projeyi seç
    → Katılımcıyı seç veya ekle
    → Kayda Başla
    → Capture ekranı
```

İlk açılışta tek **Sistem Sahibi** hesabı oluşturulur. Sonraki kullanıcılar
giriş ekranından normal kullanıcı hesabı açabilir; yalnızca kendilerine
atanmış veya kendilerinin oluşturduğu projeleri görür. Sistem Sahibi kullanıcı
durumlarını, geçici parola sıfırlamayı ve proje atamalarını yönetir. Parola
saklanmaz; sürümlü `scrypt` türevi saklanır.

Sol gezinme çubuğunda sekiz çalışma alanı var (`Ctrl+1` … `Ctrl+8`,
`Ctrl+B` daraltır):

1. **Ana Sayfa** — sayımlar, yarım kayıtlar, etiket bekleyenler, sistem durumu.
2. **Projeler** — erişilebilir projeyi oluştur/aç, Kayıt Planı tanımla.
3. **Katılımcılar** — anonim katılımcı (`P0001`) seç/ekle ve Kayda Başla.
4. **Capture** — canlı RGB/derinlik ve 3B iskelet ekranın tamamını kullanır;
   ön kontrol, kayıt planı, kayıt bilgisi, kaydedilecek kişi ve ham arşiv
   ayrıntıları **Kayıt bilgileri** penceresindedir (`F4`). Kritik uyarılar
   (kayıt kaybı, bağlantı hatası, disk yetersizliği, belirsiz kişi) ana
   ekranda, düzeltme düğmelerinin yanında kalır.
5. **İnceleme ve Etiketleme** — senkron oynatma, iki katmanlı zaman çizelgesi,
   hareket ve hata etiketleri. Etiket formları kalıcı bir panelde değil,
   aralığa **çift tıklayınca** açılan küçük pencerelerdedir.
6. **Dataset** — bileşim, filtreler, kalite bulguları.
7. **Export** — sürümlü dataset yayını.
8. **Ayarlar ve Tanılama** — tercihler, yakalama profili, etiket şeması, tanı.

### Capture kısayolları

| Tuş | İşlem |
|---|---|
| `R` | Kaydı başlat / durdur |
| `Boşluk` | Önizlemeyi aç / kapat |
| `M` | Marker bırak |
| `Esc` | Kaydı durdur |
| `F4` | Kayıt bilgileri penceresi |

Metin alanına yazarken bu kısayollar tetiklenmez.

### Etiketleme akışı

1. Kaydı oynatın veya zaman çizelgesinde gezinin.
2. **Hareket modunda** (F1) HAREKET şeridinde sürükleyerek bir tekrar çizin —
   ya da `Hareket ekle` (`N`) ile oynatma konumunda oluşturun. Arka arkaya on
   tekrar çizerken araya pencere girmez.
3. Hareketi seçin, gerekirse sadece onu döngüde oynatıp sınırlarını düzeltin.
4. Hareket bandına **çift tıklayın** (veya `Enter`): açılan küçük pencerede
   hareket türünü arayın veya seçin. Pencere yalnızca bunu sorar; doğru/hatalı
   diye bir seçim yoktur. Kaydet, sınıf incelemesinin bittiğini kaydeder ve
   hata aralığı yoksa hareketi anında DOĞRU ve export'a hazır yapar.
5. Hatanın göründüğü yeri göstermek için `Hata ekle` (`E`) ile HATA şeridinde
   aralığı çizin, sonra o aralığa **çift tıklayıp** hata türünü seçin.
   Sınıflandırılan ilk aralıkla birlikte hareket HATALI olur.
6. Aynı harekete başka hata aralıkları ekleyin, sonra sonraki harekete geçin.
   `Sonraki eksik`, bu kayıtta etiketi tamamlanmamış bir sonraki harekete —
   kalmadıysa eksik bir sonraki kayda — atlar.

Aranan tür listede yoksa, adı yazıp Enter'a basmak **hem hareket hem hata**
için yeni türü projeye kalıcı olarak ekler ve seçili aralığa atar; ekrandan
çıkmanız gerekmez. İki tür de aynı yinelenen-ad kontrolünü kullanır: büyük/
küçük harf, fazladan boşluk ve Unicode biçim farkları mevcut türü seçer, yeni
tür yaratmaz.

**Yeni sınıf eklemek proje düzeyinde bir değişikliktir.** `label_schema.json`
dosyasına anında ve atomik yazılır, etiketleme undo yığınına **girmez**, ve
pencereyi **İptal** ile kapatsanız bile tanımlı kalır — iptal yalnızca "bu
aralığa atama" işlemini geri alır. Türü seçilmemiş bir aralık "tamamlandı"
sayılmaz: hem ekranda hem export kuralında eksik görünür.

### İnceleme kısayolları

| Tuş | İşlem |
|---|---|
| `Boşluk` | Oynat / duraklat |
| `,` / `.` | Bir kare geri / ileri |
| `F1` / `F2` | Hareket modu / hata modu |
| `N` | Konumda yeni hareket |
| `E` | Konumda yeni hata aralığı |
| `S` | Seçili hareketi böl |
| `X` | Dışla / geri al |
| `L` | Seçili aralığı döngüde oynat |
| `Enter` | Seçili aralığın etiket penceresini aç |
| `Delete` | Seçili aralığı sil |
| `Esc` | Süren sınır sürüklemesini iptal et |
| `F4` | Kayıt bilgileri penceresi |
| `Ctrl+1`/`2`/`3` | RGB / İskelet / RGB + İskelet |
| `Ctrl+Z`, `Ctrl+Y` | Geri al / yinele |
| `Ctrl+S` | Hemen kaydet |

Metin alanına yazarken bu kısayollar tetiklenmez.

### Ekranda yalnızca kaydedilen kişi çizilir

İnceleme ekranı, kayıt sırasında seçilmiş kişiyi çizer ve **başka hiç kimseyi
çizmez** — soluk da olsa. Otorite `subject_body()`'dir; o kişi bir karede
bulunamadıysa iskelet çizilmez ve panelde "Seçilen kişi bu karede bulunamadı"
yazar. Önceki karenin pozu ekranda **donmaz**, en iyi takip edilen gövde
yerine geçirilmez. Zaman çizelgesindeki takip kapsamı eğrisi de aynı kişiyi
anlatır, böylece grafik "veri var" derken görüntü boş kalamaz. Gövde/tracker
kimliği seçici kaldırıldı: seçilecek bir şey yok.

Kişi kilidi eklenmeden önce alınmış kayıtlarda kayıtlı bir cevap yoktur. Bu
durumda kayıtta **en çok görünen** gövde çizilir, bu bir tahmin olarak
işaretlenir (`Kilit yok · tahmin ID n`) ve kayıt açılırken uyarı verilir.
Uydurma bir kimlik yazılmaz; export aynı kaydı aynı kuralla okur.

### RGB üzerine iskelet hizası

2B eklem konumları **kameranın kendi görüntüsünün** pikselleridir. İnceleme
ekranında görünen resim ise küçültülmüş proxy videodur (`proxy_video_width`,
varsayılan 640). Bu iki uzayı aynı saymak, HD720 bir kayıtta her eklemi 2x,
960x540 bir kayıtta 1.5x sağa kaydırıyordu. Artık eklem uzayının çözünürlüğü
kaydın kamera bilgisinden okunur ve izdüşüm normalize koordinatlar üzerinden
yapılır; sonuç, resmin ekranda hangi boyutta çizildiğinden bağımsızdır.
Düzeltme bir piksel ofseti değil, ölçek hatasının kaynağının giderilmesidir.

2B eklem yoksa kaydın **doğrulanmış** kamera kalibrasyonu (fx/fy/cx/cy)
kullanılır. İkisi de yoksa bindirme **çizilmez** ve nedeni yazılır —
yaklaşık yerleştirilmiş bir iskelet, takip hatasından ayırt edilemez.

Bir karenin proxy görüntüsü eksikse eski kare tekrar gösterilmez: renkli kare
olmadığı söylenir. Aynı poz başka bir anın resmiyle eşleştirilirse ortaya
çıkan görüntü, tam olarak bir takip hatasına benzer.

---

### Sınır sürüklerken kare önizlemesi

Bir hareket veya hata aralığının kenarını sürüklerken — ve yeni bir aralığı ilk
kez çizerken — görüntüleyici **sürüklenen anı** gösterir, tıpkı bir video
düzenleyicide olduğu gibi. Üç görünüm modu da (RGB, İskelet, RGB + İskelet) aynı
geçici kareyi kullanır ve hata aralığı önizlemesi ana hareketin sınırlarına, son
hâlle birebir aynı kuralla kırpılır.

Fare bırakıldığında:

- kalıcı playhead, **sürükleme başlamadan önce bulunduğu kareye** geri döner —
  farenin bırakıldığı yere değil;
- oynatma kendiliğinden başlamaz;
- repository'ye **tek bir** düzenleme yazılır. Eskiden her fare hareketinde bir
  mutasyon, bir undo adımı ve bir autosave üretiliyordu, yani tek bir
  sürüklemeyi geri almak için Ctrl+Z'ye onlarca kez basmak gerekiyordu.

`Esc`, odak kaybı veya aralık eşiğini geçmeyen kısa tıklama sürüklemeyi iptal
eder: hiçbir şey yazılmaz ve playhead eski yerine döner. Kısa tıklama eski
scrub davranışını korur.

---

## Projeyi kalıcı olarak silme

Disk alanı geri kazanmak için **yalnız Sistem Sahibi** bir projeyi kalıcı
olarak silebilir. Bu, uygulamadaki tek yıkıcı işlemdir ve değişmezlik
kurallarının bilinçli, dar kapsamlı tek istisnasıdır.

**Silme gerçekten silmektir:** proje klasöründeki ham RGB-D arşivi, proxy
videolar, iskelet akışları, etiket sidecar'ları ve oluşturulmuş dataset
sürümleri fiziksel olarak kaldırılır. Geri dönüşüm kutusuna taşınmaz, gizli bir
çöp klasöründe bekletilmez.

### Yetki

Yetki kontrolü **düğmede değil, servistedir**. Normal kullanıcı düğmeyi görmez;
GUI'yi atlayıp servisi doğrudan çağırsa da `AuthorizationError` alır.
Bir kullanıcının proje **erişimini kaldırmak** ile projeyi **silmek** ayrı
işlemlerdir ve erişim kaldırma hiçbir dosyaya dokunmaz.

### Onay

Basit bir Evet/Hayır yeterli değildir. Onay penceresi proje adını, proje
kimliğini ve **tam, kısaltılmamış, kopyalanabilir** yolu gösterir; işlemin geri
alınamayacağını ve neyin silineceğini yazar. Son düğme, admin **proje adını
birebir yazana kadar** etkin olmaz. İptal, pencereyi kapatma ve yanlış metin
hiçbir dosyayı, DB kaydını veya aktif bağlamı değiştirmez.

İşlem başladıktan sonra ikinci tıklama ikinci bir silme başlatmaz ve
**İptal düğmesi sunulmaz**: özyinelemeli silmenin ortasında "iptal" yarım
silinmiş bir projeyi tarif ederdi.

### Yol güvenliği

Hedef yalnız DB kaydından alınır; kullanıcı metni, glob veya çözülmemiş göreli
yol asla özyinelemeli silmeye girmez. Silmeden hemen önce:

- yol `resolve()` ile çözülür ve kayıtla karşılaştırılır;
- klasördeki `project.json` içindeki `project_id` seçili kayıtla eşleşmelidir;
- sürücü kökü, kullanıcı ana klasörü, dataset kökü ve uygulama kaynak klasörü
  reddedilir;
- symlink/junction hedefleri reddedilir; proje **içindeki** bir bağlantı
  izlenmez, yalnız bağın kendisi silinir.

Bunlardan biri tutmazsa **hiçbir şey silinmez**.

### Yarıda kalırsa

Dosya sistemi ile SQLite tek bir transaction olamaz. Bu görmezden gelinmez:
proje önce `datasets/.deleting/<project_id>__<zaman>` altına **atomik olarak
taşınır** (aynı birim içinde `os.replace`), sonra DB temizlenir, en son
baytlar silinir. Klasörün içine bırakılan işaret dosyası hangi tarafın
tamamlandığını söyler.

- **Tam başarı:** klasör yok, DB kayıtları yok, aktif/son proje referansı yok,
  audit olayı var, `.deleting` klasörü kaldırılmış.
- **Onay öncesi / iptal / yetki hatası:** hiçbir şey değişmedi.
- **DB hatası:** proje eski yerine geri taşınır; hiçbir dosya silinmez.
- **Dosya silme hatası:** **başarı gösterilmez**; kalan yollar tek tek
  bildirilir ve bir sonraki açılışta kurtarma çalışır.

Uygulama silme sırasında kapanırsa, sonraki girişte `.deleting` altındaki
işaretler okunur: DB tarafı bitmişse silme tamamlanır, bitmemişse proje eski
yerine geri alınır. İşareti okunamayan klasöre **dokunulmaz** ve bildirilir —
belirsizlik her zaman veriyi korumaktan yana çözülür.

### Klasörü kaybolmuş proje kaydı

Kayıtlı klasör diskte yoksa proje listede kalır fakat silinemez: silinecek bir
şey yoktur. Bu durumda **ayrı** bir işlem devreye girer — *kaydı listeden
kaldır*. Farkı gizlenmez; pencere başlığı, uyarı metni ve buton yazısı
değişir, çünkü hiçbir dosya silinmez ve disk alanı boşalmaz. Yalnız
uygulamadaki eski kayıt ve erişim bağlantıları kaldırılır.

Güvenlik açısından ikisi aynı değildir ve aynı muameleyi görmez:

- Kaldırma **yalnız** ön kontrol `delete_target_missing` döndüğünde
  açılabilir. Manifest uyuşmazlığı, symlink, izin hatası gibi başka her guard
  başarısızlığı `not_an_orphan_record` ile reddedilir; "silinemiyor" hatası
  sessizce "kaydı at" işlemine dönüşemez.
- Kaldırma dosya sistemine **hiç dokunmaz**.
- Yine sistem sahibine özeldir ve yine proje adının birebir yazılmasını
  ister — bir projeyi uygulamadan çıkarmak kazara yapılacak bir şey değildir.
- Denetim kaydı ayrı bir olaydır: `project_deleted` değil
  `project_record_removed`, ve metadata'sında `files_deleted: false` bulunur.
  Kaydı okuyan biri dosyaların yok edilip edilmediğini ayırt edebilmelidir.

Klasör yalnızca taşındıysa doğru davranış onu geri getirmektir; pencere bunu
kayıt kaldırılmadan önce yazıyla söyler.

### Denetim izi

`audit_log.project_id`, `projects` tablosuna foreign key ile bağlıdır. Proje
satırı silinirken bu geçmiş **silinmez**: önce her olayın metadata'sına proje
kimliği ve adı kopyalanır, sonra işaretçi `NULL` yapılır. Kimin ne zaman neyi
sildiği, dosyalar gittikten sonra da kayıtlıdır.

## Ham RGB-D arşivi

Her gerçek kayıt, ileride yeniden işlenebilmesi için ham RGB ve **ölçülen**
derinliğiyle saklanır. Bu **zorunludur**: Ayarlar'dan kapatılamaz, ve arşivi
eksik kalan bir kayıt `FINALIZED` sayılmaz.

### SVO2 gerçekte ne saklıyor?

Bu makinede, bu SDK ile ölçülerek doğrulandı:

| Soru | Ölçülen cevap |
|---|---|
| SVO2 RGB'yi geri veriyor mu? | **Evet.** Yeniden açılıp herhangi bir konumdan okunabiliyor. |
| SVO2 derinliği saklıyor mu? | **Hayır.** Stereo görüntüleri saklar; derinlik okuma anında YENİDEN HESAPLANIR. |
| Yeniden hesaplanan derinlik ölçülene eşit mi? | **Hayır.** Aynı kaydın aynı konumlarında yer yer **14 metreye varan** fark, geçersiz piksel maskeleri bile farklı. |
| Varsayılan sıkıştırma kayıpsız mı? | **Hayır.** `H264` kayıplıdır. |

Ölçülen sıkıştırma maliyetleri (HD720/30, gerçek kamera):

| Mod | Boyut |
|---|---|
| `H264` (varsayılan, kayıplı) | ~96 MB/dk |
| `H264_LOSSLESS` | ~1.1 GB/dk |
| `LOSSLESS` | ~3.0 GB/dk |

Bu yüzden **ölçülen derinlik ayrıca arşivlenir.** Belgede hiçbir yerde SVO2
için "lossless" denmez; kullanılan mod `raw_capture_manifest.json` içine
yazılır.

### Derinlik nasıl saklanıyor?

Ölçülerek seçildi (gerçek ZED derinliği üzerinde, yeni bağımlılık kurmadan):

| Şema | Boyut | Kayıpsız |
|---|---|---|
| zlib float32 | 5153 MB/dk | evet |
| **byteshuffle + zlib-1 (varsayılan)** | **3534 MB/dk** | **evet** |
| temporal XOR + byteshuffle + zlib | 3286 MB/dk | evet |
| uint16 @ 0.25 mm (isteğe bağlı) | 1612 MB/dk | **hayır** (ölçülen hata 0.13 mm, menzil 16.4 m) |

Kayıpsız sıkıştırmanın zayıf kalması veriden kaynaklanıyor: tek bir karede
200 000 pikselin 196 010'u farklı değer taşıyor, ardışık değerler arasındaki
medyan fark 9 mikrometre. Ücretsiz kazanç yok, bu yüzden **varsayılan ölçümü
korumaktır** ve maliyet kayıttan önce gösterilir. Nicemlenmiş profil
seçilirse ölçek, geçersiz sentinel ve hassasiyet sürüm dosyasına yazılır ve
her yerde "kayıplı" olarak işaretlenir.

### Dosya düzeni

```text
take_.../
├── raw/
│   ├── capture.svo2                 # ZED'in kendi stereo kaydı (H264, kayıplı)
│   ├── raw_capture_manifest.json    # biçim, codec, provenance, senkron sözleşmesi
│   └── rgbd/
│       ├── depth_000000.kcd         # ölçülen derinlik, chunk'lı, bağımsız okunur
│       ├── color_000000.kcc         # yalnız native kayıt yoksa (ör. mock backend)
│       └── index.jsonl              # kare başına senkronizasyon indeksi
├── derived/  skeleton.jsonl · proxy.mp4
└── annotations/ · quality/ · checksums.json
```

Her chunk kendi başlığını taşır ve tek başına çözülür; elektrik kesintisinde
yalnız yarım kalan chunk kaybolur, kalan kayıt okunabilir. Her chunk ayrı
checksum'lanır.

### Zaman eşlemesi

`raw/rgbd/index.jsonl` her kare için şunları taşır:

| Alan | Anlam |
|---|---|
| `p` | **Kayıt içi konum** (0 tabanlı). Etiket sınırları ve `skeleton.jsonl` bunu kullanır. |
| `i` | **Kameranın kendi kare numarası**. Kare düşünce `p` ile ayrışır. |
| `host_ns` / `cam_ns` | Host ve kamera zaman damgaları |
| `color` / `depth` / `skel` / `native` | Hangi akışın o kareyi gerçekten aldığı |
| `subj` | Seçili kişinin otoritatif ilişkilendirmesi |

Akış konumu ile kamera kare numarası birbirinin yerine kullanılamaz. SVO
konumu ile canlı kare arasında 1:1 sıra **varsayılmaz**: ölçümde SVO2'nin kare
sayısı canlı kare sayısından bir fazla çıktı, bu yüzden eşleme zaman damgasıyla
doğrulanmalıdır.

### Kayıp, arıza ve kurtarma

- Ham kayıt başlatılamıyorsa **gerçek kayıt hiç başlamaz**.
- Preview kaybı, kayıt kuyruğu kaybı, RGB arşiv kaybı, derinlik arşiv kaybı ve
  backend kaybı **ayrı ayrı** sayılır.
- Renk veya derinlik karesi kaybedilirse take `PARTIAL` kalır; yazılan hiçbir
  dosya silinmez.
- Native kayıt düzgün durdurulamazsa bu yutulmaz; take `FINALIZED` olmaz.
- Finalize sırasında chunk'lar okunur, boyutlar ve checksum'lar alınır.
- Kayıttan önce tahmini GB/dakika ve diskin kaç dakikaya yettiği gösterilir;
  yetmiyorsa kayıt başlamaz. Çözünürlük, FPS veya derinlik **sessizce
  düşürülmez**.

### Ham veriyi geri okuma

```bash
conda run -n KineSynth python -m kinecapture.tools.extract_raw <take_dir> --verify
```

```bash
conda run -n KineSynth python -m kinecapture.tools.extract_raw <take_dir> --out <dir> --range 100 220
```

Doğrulama hiçbir şey yazmaz. Çıkarım, ham veriye dokunmadan yeni bir türetilmiş
paket ve onu açıklayan bir manifest üretir. Derinlik **her zaman** arşivden
okunur, SVO2'den değil.

## Kaydedilecek kişiyi seçmek

Canlı görüntüde kişinin üzerine tıklanır. Seçilen kişi çerçeveyle vurgulanır,
diğerleri soluk çizilir. Hit testing tracker'ın kendi 2B eklem noktalarını
kullanır; letterbox ve DPI ölçeği hesaba katılarak tıklama doğru kaynak
pikseline çevrilir. İki kişi üst üsteyse **rastgele seçim yapılmaz**, kullanıcı
uyarılır.

### Tracker kimliği ile mantıksal kişi ayrıdır

| Kavram | Nedir |
|---|---|
| `subject_id` | Kayda özel, seçim anında üretilen ve kayıt boyunca **değişmeyen** mantıksal kimlik |
| `tracker_body_id` | O karede eşlenen SDK kimliği; kişi kadrajdan çıkıp girince değişebilir |

Seçim anı, ilk tracker kimliği, kare, zaman damgası ve yöntem metadata'ya
yazılır. Her kare için seçili kişinin hangi gövdeyle eşlendiği — veya
bulunamadığı — kaydedilir.

### Kaybolma ve yeniden ilişkilendirme

```text
UNSELECTED → LOCKED → TEMPORARILY_LOST → REIDENTIFYING → LOCKED
                                     ↘ AMBIGUOUS (kullanıcı doğrulaması gerekir)
```

- Seçili kimlik görünürken doğrudan o kullanılır.
- Kısa kaybolmalarda kilit kaldırılmaz; kareler "kişi yok" olarak işaretlenir.
- **Başka bir kişiye asla sessizce geçilmez.** En yüksek güvenli gövdeyi
  otomatik seçmek yoktur.
- **Seçili kişiyle aynı karede görülmüş bir tracker kimliği bir daha seçili
  kişi olamaz.** İki gövde aynı anda görünüyorsa iki farklı kişidir; bu, benzer
  ölçülü bir antrenörün veriye karışmasını engelleyen en güçlü kanıttır.
- Otomatik yeniden eşleştirme yalnız konum sürekliliği, uzuv oranları ve boy
  kanıtı hem eşiği hem ikinci adaya göre farkı geçerse yapılır.
- Kanıt yetersizse veya iki aday yakınsa durum `AMBIGUOUS` kalır ve kullanıcıdan
  doğrulama istenir.
- Bütün kararlar ve **reddedilen** kararlar kare, zaman damgası, eski/yeni
  kimlik, yöntem, skor ve gerekçeyle audit kaydına yazılır.

**Verilen garanti** "kişi her koşulda tanınır" değildir — hiçbir gövde
takipçisi bunu veremez. Garanti şudur: **sistem belirsizken başka kişiye
geçmez; otomatik eşleştirme yalnız yeterli kanıtla yapılır; emin olunamayan
kareler boş kalır.**

### Gizlilik sınırı

Yüz tanıma yok. Görünüm gömülmesi yok. Kayıtlar arası kalıcı biyometrik kimlik
veritabanı yok. Kişi eşleştirmesi yalnız uzuv oranları ve boy kullanır ve
kapsamı **tek bir kayıtla** sınırlıdır.

### Ham tespitler korunur

`skeleton.jsonl` kadrajdaki **bütün** gövdeleri saklamaya devam eder. Bunun
yanında hangi gövdenin seçili kişi olduğu kare bazında otoritatif olarak
yazılır. Etiketleme ve export yalnız bu otoritatif ilişkilendirmeyi kullanır;
`primary_body()` fallback'i ground truth üretiminde kullanılmaz. Seçili kişinin
bulunmadığı karelerde koordinatlar NaN ve `subject_present_mask` False olur.

Kişi kilidinden **önce** alınmış kayıtlar için otomatik migration yapılmaz:
sürekli export bu kayıtlarda kaydın baskın tracker kimliğini kullanır ve
manifestte `legacy_active_body: true` diye işaretler.

## Disk yapısı

Kullanıcı ve proje erişim veritabanı datasetin dışında tutulur:

```text
%LOCALAPPDATA%/KineCapture/identity.sqlite3   # Windows, identity schema v1
```

SQLite yalnız hesap, parola türevi, aktiflik, proje sahipliği/ataması ve küçük
audit metadata'sını saklar. RGB, derinlik, SVO2, MP4 ve JSONL dosyaları SQLite'a
konmaz.

```text
dataset_root/
└── projects/<project_id>/
    ├── project.json
    ├── label_schema.json
    ├── participants/<participant_id>/          # P0001, P0002, ... (anonim)
    │   ├── participant.json
    │   └── sessions/<session_id>/            # arka planda otomatik yönetilir
    │       ├── session.json
    │       └── takes/<take_id>/
    │           ├── take.json                   # yakalama metadata + provenance
    │           ├── raw/capture.svo2            # ZED native kayıt (değişmez)
    │           ├── derived/skeleton.jsonl      # kare başına iskelet (append-safe)
    │           ├── derived/proxy.mp4           # inceleme için küçültülmüş kopya
    │           ├── annotations/segments.json   # insan kararları (sidecar, v2)
    │           ├── quality/quality.json        # ölçülen kalite metrikleri
    │           └── checksums.json
    └── releases/dataset_v001/ ...
```

### Veri bütünlüğü kararları

- **Ham kayıt değişmez.** Etiketleme `take.json` dosyasına dokunmaz.
- **Atomik yazım.** Geçici dosya + `os.replace`; yarım JSON bırakılmaz.
  Mevcut dosyanın üzerine sessizce yazılmaz.
- **Append-safe iskelet akışı.** Her kare sonrası flush edilir. Elektrik
  kesilse bile o ana kadarki kareler okunabilir; yarım kalan son satır
  tolere edilir ve `truncated` olarak bildirilir.
- **Ölçülen derinlik zorunlu saklanır.** SVO2 yeniden oynatımının kayıt anındaki
  derinliği bit düzeyinde üretmediği gerçek donanımda ölçüldü. Bu nedenle ZED
  rengi SVO2'de, ölçülen float32 derinlik ise chunk'lı RGB-D arşivinde tutulur.
- **Yarım kayıtlar kaybolmaz.** Finalize edilmemiş kayıt `PARTIAL` kalır,
  açılışta bulunur ve kurtarılabilir.
- **Uzun yol desteği.** Windows 260 karakter sınırı `\\?\` önekiyle aşılır
  (`kinecapture.core.paths`).
- **Kare sınırları tek sözleşme.** `start_frame` / `end_frame` her yerde
  `derived/skeleton.jsonl` kare listesindeki 0 tabanlı konumdur ve **her iki uç
  dahildir**. Arayüz, sidecar ve export aynı anlamı kullanır.
- **Eski etiketler bozulmaz.** v1 sidecar okunabilir; okuma sırasında dosya
  **yeniden yazılmaz**. Yerini yitiren alanlar (`movement_phase`, `severity`,
  `affected_joints`, eski durumlar) `legacy` bloğunda korunur. Belirsiz bir
  `uncertain` kararı kesin bir doğru/yanlış'a **çevrilmez**; etiketlenmemiş
  sayılır ve orijinali kaydedilir.

---

## Dataset sürümleri

Her sürüm (`dataset_v001`, `dataset_v002`, …) şunları içerir:

| Dosya | İçerik |
|---|---|
| `samples/*.npz` | Hareket başına `float32 [T, J, 3]` + güven + kare indeksi + kamera zaman damgası + hata aralıkları |
| `manifest.json` | Örnek listesi, ilişkiler, provenance, dizi sözleşmesi |
| `skeleton_spec.json` | Eklem adları, sırası, kenarlar, koordinat sistemi, birim |
| `feature_spec.json` | Seçilen özellikler, sürümleri, dizi sözleşmeleri, sütun adları, birim, eksik veri politikası, availability |
| `continuous/*.npz` | Sürekli aktivite örnekleri (yalnız o mod seçiliyse) |
| `activity_spec.json` | Aktivite sınıf kodları, kare bazlı hedef dizileri, maskeler, split gruplama kuralı |
| `label_mapping.json` | Sınıf kodları ve sabit indeksleri |
| `dataset_fingerprint.json` | Bileşen bazlı + birleşik parmak izi |
| `validation_report.json` | Doğrulama sonucu, hatalar, uyarılar |
| `excluded.json` | Dışlanan örnekler ve nedenleri |

**Ham koordinatlar yazılır.** Root centering, ölçek normalizasyonu,
interpolasyon ve augmentation uygulanmaz — bunlar eğitim katmanına aittir.
Görülemeyen eklem NaN kalır.

#### Etiket sözleşmesi

Her örnek (bir hareket sample'ı) şunları taşır:

| Alan | Anlam |
|---|---|
| `exercise` | Hareket türü kodu |
| `correctness` | `correct` veya `incorrect` — **ikili**, hata aralıklarından **türetilmiş** |
| `correctness_source` | Her zaman `derived_from_error_intervals` |
| `reviewed_at` | Hareket sınıfı incelemesinin tamamlandığı an |
| `error_intervals[]` | Zamansal hata aralıkları (0 veya daha fazla) |

Her hata aralığı hem **mutlak** (kayıt içi) hem **göreli** (dizi içi) konum
taşır, böylece tüketici tahmin yürütmez:

```jsonc
{
  "error_code": "diz-ice-cokuyor",
  "class_index": 0,             // label_mapping.error_types.code_to_index
  "start_position": 43,          // kayıt akışındaki mutlak konum
  "end_position": 55,
  "relative_start": 4,           // joints_xyz[4 : 12+1] tam olarak bu aralık
  "relative_end": 12,
  "num_frames": 9,
  "start_camera_frame": 46,      // kameranın kendi kare numarası
  "end_camera_frame": 58,
  "start_timestamp_ns": 1787...,
  "end_timestamp_ns": 1787...
}
```

`.npz` içinde ayrıca iki hazır hedef bulunur:

- `error_intervals` — `int32 [K, 3]` = `(class_index, relative_start, relative_end)`,
  her iki uç dahil.
- `error_multi_hot` — `uint8 [T, C]`; sütun sırası `label_mapping` ile aynıdır.
  Çakışan aralıklar aynı karede birden çok sütunu 1 yapar.

Doğrulama raporu yetim aralıkları, hareket dışına taşanları, bilinmeyen hata
kodlarını, ters/boş aralıkları, doğruluk-hata çelişkilerini ve manifest-dizi
uzunluğu uyuşmazlıklarını yakalar. Fingerprint hata sınıflarına ve aralık
sınırlarına duyarlıdır: bir aralığı eklemek, silmek, taşımak veya yeniden
sınıflandırmak sürüm parmak izini değiştirir.

##### Node kanıtı: eklem hedefleri ve maskeler

Her hata aralığı, etkilenen eklem bilgisini de taşır:

```jsonc
{
  "error_code": "diz-ice-cokuyor",
  "affected_roles": ["pelvis", "left_knee"],   // kanonik rol adları
  "joint_status": "selected",                   // dört durumdan biri
  "has_node_supervision": true
}
```

`.npz` içinde **her zaman** yazılan iki küçük dizi bunu kayıpsız taşır:

- `error_interval_joint_multi_hot` — `uint8 [K, R]`; sütun sırası
  `label_contract.joint_evidence.roles` ile aynıdır.
- `error_interval_joint_mask` — `uint8 [K]`; 1 yalnız `selected` aralıklarda.
  0 olan satır "hiçbir eklem etkilenmedi" **değil**, "bu satır node
  denetiminde kullanılmaz" demektir.
- `error_interval_joint_status` — `int8 [K]`; `joint_evidence.status_codes`
  eşlemesi (`selected`=0, `not_applicable`=1, `indeterminate`=2,
  `unreviewed`=3), yani dört durum maskede kaybolmaz.

`store_error_target_arrays` açıkken ek olarak yoğun hedefler yazılır:

- `error_joint_target` — `uint8 [T, C, J]`; `J` **native** düğüm sayısıdır,
  rol sayısı değil. Model kendi topolojisinde çalışır.
- `error_joint_label_mask` — `uint8 [T, C]`; node kaybı bu maskeyle
  çarpılmalıdır.

Yoğun diziler yazılmasa bile manifest içindeki `dense_target_recipe` onları
interval dizilerinden birebir yeniden üretmeye yeter:

> `error_joint_target[t, c, j] = 1` ancak ve ancak `class_index == c` olan,
> `t` karesini kapsayan ve `error_interval_joint_mask == 1` olan bir aralık,
> `role_to_native_node` üzerinden `j` düğümüne eşlenen bir rol taşıyorsa.

Manifest'in `label_contract.joint_evidence` bloğu rol listesini,
`role_to_index` eşlemesini, durum kodlarını, her durumun eğitimdeki anlamını,
sürümde geçen her iskelet biçimi için `role_to_native_node` tablosunu, eşleme
kaynağını ve `role_mapping_version` değerini yayınlar; tüketici hiçbir şeyi
tahmin etmez.

Doğrulama `unknown_joint_status`, `unknown_anatomical_role`,
`selected_without_roles`, `roles_without_selected_status` ve
`joint_mask_disagrees_with_status` sorunlarını raporlar. Fingerprint eklem
durumuna ve rol listesine duyarlıdır: bir aralığın eklemlerini değiştirmek
sürüm parmak izini değiştirir.

**Export'a ne girer?** Ekranda "hazır" görünen hareketler — ne eksiği ne
fazlası. Aynı kural (`evaluate_sample`) hem arayüzü hem exportu besler.
Dışlanan her şey nedeniyle birlikte `excluded.json` içine yazılır.

`participant_id`, `session_id` ve `take_id` her örnekte korunur; katılımcı
bazlı ayrım yapılabilsin ve rastgele split sızıntısı fark edilebilsin diye.

### Canonical veri ve seçilebilir özellikler

Bir sürümde iki tür dizi bulunur.

**Canonical (her zaman yazılır, kapatılamaz).** `joints_xyz`, `frame_indices`,
`camera_timestamps_ns`. Bunlar tracker'ın ürettiği ham veridir. Root centering,
ölçek normalizasyonu, interpolasyon, padding, resampling ve augmentation
uygulanmaz.

**Seçilebilir özellikler (varsa canonical'ın *yanına* yazılır).** Export
ekranındaki "Veri ve özellik seçimi" alanından açılan aranabilir listeden
seçilir. Kategoriler:

| Kategori | Örnek diziler |
|---|---|
| Kalite ve maskeler | `joint_confidences`, `joint_valid_mask`, `frame_valid_mask`, `delta_time_s`, `tracking_state_code` |
| Tracker ham çıktıları | `joint_orientations_xyzw`, `joint_positions_2d`, `joint_position_covariances_raw`, `local_joint_positions_xyz`, `root_orientation_xyzw`, `tracker_root_velocity_xyz` |
| Koordinat temsilleri | `root_centered_xyz`, `body_aligned_xyz`, `body_frame_rotation`, `body_scale`, `scale_normalized_xyz` |
| Kemik / geometri | `bone_vectors_xyz`, `bone_lengths`, `bone_unit_vectors_xyz`, `joint_centroid_proxy_xyz` |
| Hız ve ivme | `joint_displacement_xyz`, `joint_velocity_xyz`, `joint_speed`, `joint_acceleration_xyz`, `root_speed`, `root_path_length` |
| Açılar ve açısal hareket | `joint_angles_rad`, `joint_angles_deg`, `joint_angular_velocity_rad_s` |
| Simetri ve oran proxy'leri | `segment_distances`, `segment_ratios`, `bilateral_angle_difference_rad`, `bilateral_mirror_distance` |
| Klasik ML özetleri | `summary_features` (sabit uzunluklu vektör) |
| Deneysel | `joint_jerk_magnitude`, `quaternion_angular_speed_rad_s` |

Presetler: `Minimum canonical`, `KineSynth temel uyumluluk`,
`Kinematik araştırma`, `Klasik ML`, `Desteklenen tüm araştırma özellikleri`.
Preset yalnızca kutuları işaretler; sürüme yazılan şey her zaman çözülmüş
özellik kimlikleri listesidir.

**Varsayılan export değişmedi.** Hiçbir şey seçmezseniz sürüm, özellik katmanı
eklenmeden önce ürettiği dosyanın aynısıdır.

#### Kare farkı ile fiziksel hız aynı şey değildir

| Dizi | Nedir | Birim |
|---|---|---|
| `joint_displacement_xyz` | `x[t] - x[t-1]`. FPS değişince değişir. | length_unit |
| `joint_velocity_xyz` | Kamera zaman damgasına göre türev. | length_unit/saniye |

KineSynthV3'ün mevcut "velocity" kanalı **kare farkıdır**; `joint_velocity_xyz`
ile aynı kanal değildir. `KineSynth temel uyumluluk` preseti bu nedenle
`joint_displacement` içerir, fiziksel hızı içermez. Tracker'ın kendi bildirdiği
kök hızı da ayrı bir dizidir (`tracker_root_velocity_xyz`), koordinatlardan
türetilenden (`root_velocity_derived_xyz`) ayrılmıştır.

#### Türev ve eksik veri politikası

- Fiziksel türevler kamera zaman damgalarından hesaplanır. Bir adım ancak
  `0 < dt <= 2.5 / hedef_fps` ise kullanılır; takip boşluğunun üzerinden türev
  alınmaz.
- Birinci türev iç noktalarda merkezi fark, uçlarda tek yanlı farktır. İkinci
  türevin uçları NaN'dır; ekstrapolasyon yapılmaz.
- İlk hız/yer değiştirme karesi **sahte sıfırla doldurulmaz**.
- Hiçbir yerde filtre veya yumuşatma uygulanmaz.
- NaN sıfıra çevrilmez, önceki kareyle doldurulmaz. Her özellik mümkün olduğunda
  kendi `*_valid_mask` dizisini yazar ve doğrulama maske ile NaN düzenini
  karşılaştırır.
- İskelette bulunmayan bir eklem için ilgili sütun/kemik NaN kalır; komşu eklem
  yerine geçmez.

#### Eklem eşleştirmesi ile ilişkisi

Her özellik, eşleştirme altında ne olacağını kendisi beyan eder:

- `recompute` — geometrik özellikler hedef iskeletin koordinatlarından yeniden
  hesaplanır (açı, kemik, mesafe, hız, simetri).
- `index_remap` — anlamı eklem indeksine bağlı olan diziler taşınır
  (2B noktalar, eklem kovaryansları, güven değerleri).
- `native_only` — parent zincirine bağlı olanlar taşınmaz: local quaternionlar
  ve parent'a göre eklem konumları. Bir eşleştirme seçiliyken bunlar
  yazılmaz; Export ekranı bunu seçimden önce gösterir ve sürüm nedenini yazar.

#### Sürüm parmak izi

Fingerprint bileşenleri: `samples`, `export_config`, `skeleton_spec`,
`label_schema`, `features`. Örnek bileşeni, yazılan `.npz` dosyasının kendi
sağlama toplamını da içerir; yani **dizi içeriği değişirse parmak izi değişir**.
Özellik seçimini, bir özelliğin sürümünü veya algoritma parametresini
değiştirmek de parmak izini değiştirir.

#### Klinik doğrulama sınırı

Bu dizilerin hiçbiri klinik olarak doğrulanmış bir ölçüm değildir. Tüketici
sınıfı bir derinlik kamerasının iskelet tahmininden türetilmiş kinematik
büyüklüklerdir. `joint_centroid_proxy_xyz` bir kütle merkezi değildir;
doğrulanmış antropometrik model olmadığı için öyle adlandırılmamıştır. Zemin
yüksekliği ve ayak teması gibi büyüklükler, doğrulanmış bir dünya/zemin
kalibrasyonu gerektirdiği için hiç üretilmez.

### Sürekli aktivite dizi sözleşmesi

Sürekli örnek kaydın tamamıdır; `T` gerçek kayıt uzunluğudur. Interpolation,
padding, sabit uzunluğa resampling ve augmentation **uygulanmaz**.

| Dizi | Şekil / tip | Anlam |
|---|---|---|
| `joints_xyz` | `[T,J,3] float32` | **Seçili kişinin** ham koordinatları; kişi yoksa NaN |
| `frame_indices` / `camera_timestamps_ns` | `[T] int64` | Kamera kare numarası ve zaman damgası |
| `subject_present_mask` | `[T] bool` | Seçili kişi bulundu mu |
| `subject_source_tracking_id` | `[T] int64` | Eşlenen SDK kimliği; yoksa `-1` |
| `subject_association_confidence` | `[T] float32` | Eşleştirme güveni; kişi yoksa NaN |
| `activity_state_code` | `[T] int16` | 0/1/2/3 sınıf, `-1` **etiketlenmemiş** |
| `activity_label_mask` | `[T] bool` | Aktivite etiketi bulunan kareler |
| `exercise_active` | `[T] bool` | Hedef egzersizin yapıldığı kareler |
| `exercise_class_index` | `[T] int32` | `label_mapping` indeksi; yoksa `-1` |
| `exercise_class_valid_mask` | `[T] bool` | Sınıfın bilindiği kareler |
| `exercise_start_target` / `exercise_end_target` | `[T] uint8` | Aralığın ilk / son karesinde 1 |
| `correctness_code` | `[T] int8` | 0=correct, 1=incorrect, `-1` uygulanamaz |
| `error_label_mask` | `[T] bool` | Hata etiketinin **uygulanabilir** olduğu kareler |
| `error_multi_hot` | `[T,C] uint8` | Yalnız `error_label_mask` True iken yorumlanır |

Üç ayrım hiçbir zaman bulanıklaştırılmaz:

- **Etiketlenmemiş ≠ arka plan.** `-1` + `activity_label_mask=False`.
- **Kişi yok ≠ kişi hareketsiz.** `subject_present_mask=False` + NaN koordinat.
- **Hata etiketi yok ≠ hata yok.** `error_label_mask=False`, "bu kareye
  sorulmadı" demektir.

Tek karelik bir egzersizde `start` ve `end` aynı karede 1 olabilir.

Ham RGB-D **her örneğe kopyalanmaz**: manifest, kaydın kendi arşivine
checksum'lu bir referans taşır. Aynı kayıttan türetilen bütün pencereler aynı
`split_group_id`'yi taşır ve train/val/test arasında bölünmemelidir.

Fingerprint aktivite aralıklarına, egzersiz bağlantılarına, kişi ilişkilendirme
özetine, seçili dataset moduna, dizi içeriği checksum'una ve ham kaynak
checksum'una duyarlıdır.

### Eski: KineSynthV3 uyumluluğu

> Bu proje artık **modelden bağımsız** bir dataset üretir. KineSynthV3
> Transformer modeline uyum ne varsayılan hedeftir ne de önceliktir; aşağıdaki
> eşleştirme yalnız eski otomasyon için korunmaktadır. `kinesynth_compat`
> preset'i **Eski** olarak işaretlidir ve varsayılan seçim değildir.


ZED'in native `BODY_34` formatı KineSynthV3'ün 26 eklemli `rehab24_6_mocap`
yapısıyla **aynı değildir**. Sürümlü bir adapter tanımlıdır
(`zed_body_34__to__rehab24_6_mocap` v0.1.0-partial):

- 26 hedef eklemin **23'ü** doğrudan eşleşiyor.
- 3 eklem eşleşmiyor ve **NaN yazılıyor**: `Head_end`, `LeftToeBase_end`,
  `RightToeBase_end`. Bunlar mocap uç işaretçileridir ve ZED'de karşılığı
  yoktur; uydurulmak yerine boş bırakılır.
- Eşleştirmenin durumu, kapsamı ve eşleşmeyen eklemlerin gerekçesi manifeste
  yazılır ve Export ekranında gösterilir.

Varsayılan export **native** eklem sırasındadır.

---

## Mimari

```text
GUI (PySide6)          gui/pages/*, gui/widgets/*, gui/main_window.py
   │
Auth / Access          identity/ (SQLite schema, repository, scrypt, service)
   │  hesap + proje yetkisi; büyük çekim dosyası içermez
Authenticated AppState gui/state.py
   │
CaptureService         capture/service.py
   ├── acquisition thread ── backend.grab_frame()
   │        ├── preview slot (son kare kazanır → GUI QTimer okur)
   │        └── recording queue (sınırlı) ── writer thread ── TakeWriter
CameraBackend          camera/base.py → camera/mock.py, camera/zed.py
Depolama               dataset/workspace.py, recording/, playback/, annotations/
Export                 export/release.py, export/continuous.py
Features               features/ (registry, roller, açılar, türevler, özet)
Kişi kilidi            capture/subject_lock.py (Qt'siz, sürümlü, deterministik)
Ham arşiv              recording/rgbd_archive.py (chunk'lı, thread havuzlu)
Domain                 domain/ (Qt ve pyzed içermez)
```

- Kamera okuma ve disk yazımı GUI thread'inde **değildir**.
- Önizleme kuyruğu tek karelik: GUI geride kalırsa kare atlanır ve
  *önizleme kaybı* olarak sayılır.
- Kayıt kuyruğu sınırlıdır: taşarsa bu *veri kaybıdır*, ayrıca sayılır,
  ekranda kırmızı gösterilir ve kaydın kalite metriklerine yazılır.
- Bu iki sayı asla birbirine karıştırılmaz.

---

## Test

```powershell
.\scripts\run_tests.ps1
conda run -n KineSynth python -m pytest -k export
```

**561 test, tamamı geçiyor** (~177 s). Testler gerçek kamera gerektirmez ve
gerçek zaman beklemez; GUI testleri `QT_QPA_PLATFORM=offscreen` ile çalışır.

Kapsam: ortam ve opsiyonel `pyzed` importu, config doğrulama, domain
shape/dtype, ZED iskelet tabloları, eklem eşleştirme, mock determinizmi,
ilk kurulum ve tek-owner DB kısıtı, self-registration, parola hash/verify,
pasif kullanıcı, parola sıfırlama ve zorunlu değişim, proje sahipliği/ataması,
yetkisiz proje yolu, eşzamanlı katılımcı kodu tahsisi, otomatik çekim oturumu,
çok gövde ve takip kaybı senaryoları, state machine, capture servisi,
atomik yazım ve overwrite koruması, checksum, yarım kayıt kurtarma,
oynatma, hareket segmentasyonu, hata aralıkları (tek/çok/tekrarlı/çakışan),
aralığın hareket dışına çıkamaması, hareket sınırı değişince güvenli davranış,
etiketleme sırasında hata türü oluşturma ve tekrar adı kontrolü,
undo/redo, autosave, eski v1 annotation JSON'unun kayıpsız okunması,
dataset index, export manifest/mapping/fingerprint/doğrulama, iptal ve hata
atomikliği, ZED gövde dönüşümü (donanımsız stub ile), RGB/iskelet/bindirilmiş
görünüm modları, iki modlu zaman çizelgesi ve her sayfanın gerçekten
çizdirilmesi (paint testleri).

Özellik katmanı için ayrıca: düzensiz zaman damgasında fiziksel hızın kapalı
form doğruluğu, aynı kare farkının farklı FPS'te farklı hız vermesi, takip
boşluğunda türev maskesi, sabit ivmenin birebir geri elde edilmesi, bilinen
90°/180° açılar, sıfır uzunluklu vektörde NaN, `q`/`-q` quaternion işaret
değişiminin sahte açısal hız üretmemesi, kemik sırası, tam simetrik iskelette
sıfıra yakın simetri değeri, bilinçli asimetride sıfırdan farklı sonuç,
kameraya göre dönmenin asimetri üretmemesi, eksik bir eklemin yalnız bağımlı
sütunları geçersiz yapması, eski v1 JSONL kaydının kayıpsız okunması, yeni
opsiyonel alanların round-trip'i, yanlış şeklin reddedilmesi, eşleştirme
altında native-only alanların düşürülmesi, bütün örneklerde aynı dizi anahtarı
sözleşmesi, fingerprint'in özellik seçimine / sürümüne / dizi içeriğine
duyarlılığı, hiç üretilemeyen özelliğin doğrulamayı düşürmesi ve export
ekranının preset/bağımlılık/kullanılamaz durum davranışı.

Ham arşiv, kişi kilidi ve sürekli aktivite için ayrıca: derinliğin bit düzeyinde
kayıpsız round-trip'i (NaN ve sonsuz dâhil), nicemlenmiş codec'in beyan ettiği
hatayı aşmaması, yarım kalan chunk'ın tespiti ve yalnız o chunk'ın kaybı,
kuyruk taşmasının kayıp olarak sayılması, arşivi eksik take'in `FINALIZED`
olmaması, native kaydın durdurulamamasının yutulmaması, disk ön kontrolünün
kaydı engellemesi, checksum bozulmasının yakalanması, çıkarım aracının ham
veriye dokunmaması; letterbox'lı tıklamanın doğru piksele düşmesi, üst üste iki
kişide seçim yapılmaması, seçili kişi görünürken daha yüksek güvenli yabancıya
geçilmemesi, seçili kişi kaybolunca fallback yapılmaması, aynı kimlik dönünce
takibin sürmesi, yeni kimliğe yalnız kanıtla geçilmesi, aynı karede görülmüş
kimliğin diskalifiye olması, kimlik yeniden kullanımının işaretlenmesi, elle
doğrulamanın olay üretmesi, kişi olmayan karede koordinatın NaN kalması;
aktivite CRUD/undo/redo/round-trip, çakışan durumun reddi, etiketlenmemiş
zamanın arka plana dönüşmemesi, hareket-sample bağlantısının tek kaynak
kalması, kare bazlı hedeflerin aralık sınırlarıyla birebir uyuşması, hiç
egzersiz içermeyen kaydın geçerli negatif örnek olması, iki datasetin yan yana
yayımlanabilmesi, eski kayıtların legacy olarak işaretlenmesi ve türevlerin
kişi-yok boşluğunun üzerinden hesaplanmaması.

---

## Gizlilik

- **Yüz tanıma, görünüm gömülmesi veya kayıtlar arası biyometrik kimlik
  veritabanı yoktur.** Kişi eşleştirmesi yalnız uzuv oranı ve boy kullanır ve
  kapsamı tek bir kayıtla sınırlıdır.
- Katılımcılar varsayılan olarak anonim kod ile temsil edilir (`P0001`).
- Dosya adlarında ve loglarda kişisel bilgi bulunmaz.
- Onam yalnızca durum olarak saklanır; onam metni bu uygulamada tutulmaz.
- Veri silme yalnızca açık hedef ve tekrar onayla yapılır; sessiz/otomatik
  silme yoktur.

## Sorumluluk reddi

Bu bir **araştırma ve dataset üretim aracıdır**. Ölçümler ve türetilen
çıktılar klinik olarak doğrulanmış bir değerlendirme değildir ve öyle
sunulmamalıdır.


## Proje bilgisi nerede

Kod ve testler gerçek davranışın birincil kaynağıdır. Kararların, doğrulamaların
ve tarihin nerede tutulduğu için:

- [KineCapture Wiki](knowledge/index.md) — insan ana sayfası
- [MEMORY_INDEX](MEMORY_INDEX.md) — kısa AI başlangıç haritası
- [Sistem haritası](knowledge/architecture/system-map.md) — paket sorumlulukları
- [Veri hattı](knowledge/concepts/pipeline.md) — kayıt, işleme, etiketleme, export
- [Açık sorular](knowledge/open-questions.md) — bilinen açıklar ve riskler
