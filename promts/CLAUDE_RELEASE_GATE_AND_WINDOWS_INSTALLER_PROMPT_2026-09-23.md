---
type: task-prompt
status: ready
updated: 2026-09-23
tags:
  - release
  - export
  - stress-test
  - installer
  - identity
---

# Claude Code görevi — yayın kapısı (export + ölçek testleri) ve temiz Windows kurucusu

## Görev ve öncelik

Bu görev iki parçalıdır ve **sıralıdır**:

1. **Faz A — Yayın kapısı (release gate):** Uygulamayı paketlemeden önce dataset
   export'unun doğru olduğunu, uygulamanın büyük veri ve çok sınıf altında
   GUI/backend tarafında çökmediğini ve kodun paketlenmeye uygun olduğunu kanıtla.
2. **Faz B — Kurucu (installer):** Çalışan Python ortamını `conda-pack` ile taşıyan,
   ilk adımda ZED SDK/NVIDIA uyumluluğunu denetleyen, **hiçbir mevcut veri
   taşımayan** ve yalnız yeni sistem sahibi (admin) tohumunu içeren tek bir
   Windows `Setup.exe` üret.

**Faz A geçmeden Faz B'ye başlama.** Dataset doğru export edilemiyorsa kurucunun
anlamı yoktur. Faz A'da giderilemeyen bir export hatası bulursan dur, kanıtıyla
kullanıcıya bildir ve karar bekle.

Önce `MEMORY_INDEX.md`, ardından
[karar notu](../knowledge/decisions/windows-installer-release-2026-09-23.md),
[veri hattı](../knowledge/concepts/pipeline.md),
[kimlik ve erişim](../knowledge/concepts/identity-and-access.md),
[veri bütünlüğü](../knowledge/concepts/data-integrity.md) ve
[test ve ölçüm ortamı](../knowledge/protocols/test-and-measurement.md) notlarını oku.
Eski promptları topluca okuma. Bu belgedeki kullanıcı kararları eski kararlarla
çelişirse bu belge geçerlidir. Teknik yöntemi sen seç; aşağıdaki koşulları
değiştirme. Bir koşul uygulanamıyorsa varsayım yapma, kullanıcıya sor.

Bu belgenin hazırlanmış olması hiçbir şeyin uygulandığı veya test edildiği
anlamına gelmez.

## Değişmez kurallar

- `base`, `Kinesynth` veya `KineSynth` dahil **mevcut hiçbir Conda ortamına paket
  kurma veya kaldırma.** Yayın için yeni ortam gerekiyorsa `KineSynth`'ten
  klonla (ör. `conda create --name KineCaptureRelease --clone KineSynth`);
  `conda-pack` ve Inno Setup gibi derleme araçları ayrı bir araç ortamında veya
  sistem aracı olarak bulunsun. Sistem geneline bir şey kurmadan önce kullanıcıya
  sor.
- **Kullanıcının gerçek verisine dokunma.** Şu yollar yalnız okunabilir kabul
  edilir ve hiçbir test bunlara yazmaz:
  `%LOCALAPPDATA%\KineCapture\` (içinde `identity.sqlite3`),
  `~/KineCapture/datasets`, `~/KineCapture/logs` ve kullanıcının açtığı projeler.
  Bütün testler geçici dizinlerde üretilen veriyle çalışır. Gerçek bir kayıtla
  deneme gerekiyorsa önce **kopyasını** al ve kopya üzerinde çalış.
- `pyzed` yalnız `kinecapture/camera/zed.py` içinde gecikmeli import edilir; bu
  sınırı bozma. Doğrulanmamış `pyzed` API çağrısı yazma.
- Test edilmemiş bir özelliği çalışıyor diye belgeleme. Her iddianın yanında
  hangi koşuda, hangi komutla, hangi sonuçla doğrulandığı yazsın. Sentetik veri
  ile gerçek veri, canlı ölçüm ile offline yeniden üretim ayrı raporlanır.
- Başarısız veya aralıklı testleri atlayarak, işaretleyerek ya da eşiği
  gevşeterek "yeşil" gösterme. Bilinen aralıklı takılmalar
  (`test_processing_pipeline.py`, `test_identity.py` eşzamanlılık testi) ayrıca
  raporlanır.
- **Admin şifresinin düz metni hiçbir dosyaya, loga, commit'e, wiki notuna,
  ortam değişkenine, komut satırı argümanına veya sohbet çıktısına yazılmaz.**
  Kullanıcıdan şifreyi sohbette isteme. Ayrıntı: B3.

## Faz A — Yayın kapısı

### A1. Temel koşu

- Mevcut test takımının tamamını `scripts/run_tests.ps1` ile `KineSynth`
  ortamında çalıştır. Sonucu (geçen/başarısız/atlanan, süre) kaydet. Başarısız
  testleri sınıflandır: gerçek hata, ortam sorunu, aralıklı takılma.
- Faz A'daki yeni testler ve ölçümler mevcut test yapısına uysun; uzun süren
  ölçekli testler `slow` veya ayrı bir işaretle ayrılsın ama **koşulsun**.

### A2. Dataset export doğruluğu

Amaç: export edilen veri setinin, uygulamadaki etiket ve işlem durumunu
**eksiksiz, bozulmadan ve tekrarlanabilir** biçimde yansıttığını kanıtlamak.

- Uçtan uca sentetik zincir kur: mock backend ile kayıt → offline işleme
  (`run_<id>`) → etiketleme (hareket ve hata aralıkları, eklem rolleri) →
  kanonik yayın/export. `BODY_18`, `BODY_34`, `BODY_38` ve `rehab24_6_mocap`
  export hedefinin hepsi kapsansın.
- Export çıktısını **export kodunu yeniden kullanmayan bağımsız bir okuyucuyla**
  (test tarafı oracle) doğrula. En az şunlar kontrol edilsin:
  - örnek/segment sayısı, sınıf listesi ve sınıf→indeks eşlemesi;
  - her segmentin başlangıç/bitiş karesi ve zaman damgası;
  - hareket etiketi, hata etiketi, etkilenen eklem ve not alanları;
  - katılımcı ve proje eşleşmesi; bir katılımcının verisinin başka katılımcıya
    karışmaması;
  - eksik ölçümün NaN olarak korunması, tahmin edilmemesi;
  - manifest, şema sürümleri ve checksum'ların içerikle tutarlılığı;
  - sınıfsız ve reddedilmiş/hatalı kayıtların kurala uygun dışlanması.
- **Belirlenimcilik (determinism):** Aynı girdiyle iki kez export et; zaman
  damgası gibi beklenen alanlar dışında çıktılar bayt/hash düzeyinde aynı olmalı.
- **Kesinti güvenliği:** Export ortasında süreç sonlandırıldığında geçerli
  görünen yarım bir yayın kalmamalı (atomik yazım sözleşmesi).
- **Kenar durumları:** Türkçe karakterli ve boşluklu proje/sınıf/katılımcı
  adları; özel karakterli sınıf adları; tek kareli ve kayıt sonuna değen
  segmentler; çakışan aralıklar; boş sınıf; 259 karakteri aşan hedef yol
  (`LongPathsEnabled = 0` bu makinede).
- Gerçek veri: Bu makinede işlenmiş gerçek kayıt varsa, **kopyası** üzerinde
  kanonik export'u uçtan uca çalıştır ve aynı oracle ile doğrula. Yoksa bu açık
  (`Kanonik export paketi gerçek kayıtla uçtan uca doğrulanmadı`) açık kalır ve
  raporda öyle yazar.
- Bulunan her export hatası için önce hatayı yakalayan başarısız bir regresyon
  testi yaz, sonra düzelt. Şema değişiyorsa sürümü yükselt ve belgeyle.

### A3. Ölçek ve dayanıklılık testleri (layout testi değil)

Amaç: Veri büyüdüğünde GUI'nin donmadığını, backend'in bozulmadığını ve
belleğin kontrolsüz büyümediğini ölçmek. Yerleşim/görsel testleri bu görevin
kapsamı dışındadır.

Kullanıcının belirlediği eşikler:

- **≥ 30.000 etiketli örnek/segment** içeren bir veri seti;
- **≥ 30.000 kayıt / işlenmiş `run_<id>`** içeren bir veri seti (gerçek SVO
  gerekmez; `ReviewDataset`'in açabildiği şemaya uygun hafif sentetik run
  klasörleri üret);
- **≥ 100 sınıf** (hareket ve hata sınıfları); dayanıklılık payını görmek için
  bir kademe üstünü de (ör. 150–200) ölç;
- bunların birlikte olduğu birleşik senaryo.

Sentetik veri üreticisi tekrar kullanılabilir olsun (ör. `scripts/measure/`
altında), sabit tohumla (seed) çalışsın ve yalnız geçici dizine yazsın.

Her senaryoda şunları ölç ve raporla:

- **Backend:** veri seti indeksleme/açma süresi, `ReviewDataset` açılışı,
  istatistik ve özet hesapları, export süresi, tepe bellek (peak RSS), disk
  kullanımı; ölçekte de A2 oracle'ının export'u doğrulaması; karmaşıklığın
  doğrusal mı ikinci dereceden mi büyüdüğü (en az üç ölçek noktası, ör. 1k /
  10k / 30k).
- **GUI (gerçek `studio` arayüzü, `KineSynth` ortamında):** Projeler listesi,
  Veri Seti ekranı ve dört istatistik bloğu, Etiket özeti sekmesi, etiketleme
  editöründeki sınıf seçicileri (100+ sınıf), zaman çizelgesi (çok segmentli
  kayıt), iş kuyruğu tablosu (çok satır). Ölçülecekler: ekranın dolma süresi,
  **GUI thread'inin bloklanma süresi** (olay döngüsü gecikmesi), tepe bellek,
  istisna/çökme, ekran geçişlerinde bellek sızıntısı (aynı ekrana tekrar tekrar
  girip çıkma).
- Başlangıç kabul ölçütü (ölçüm sonrası kullanıcıyla netleştirilebilir):
  çökme veya yakalanmamış istisna yok; veri kaybı veya yanlış sayım yok; GUI
  thread'i tek seferde **> 250 ms** bloklanmıyor, uzun işler iş parçacığında
  veya ilerleme göstergesiyle yürüyor; tekrarlı ekran geçişlerinde bellek
  büyümesi sınırlı. Bu eşikleri aşan her yer bulgu olarak raporlanır; eşiği
  kendiliğinden gevşetme.
- Bir darboğaz bulursan (ör. tüm satırları tek seferde widget'a doldurmak,
  ana thread'de dosya taraması) düzelt, önce/sonra ölçümünü raporla ve
  ölçekli testi regresyon olarak bırak.

### A4. Paketlenebilirlik denetimi

Kod, `KineSynth` klasöründen değil, başka bir bilgisayardaki taşınmış bir
ortamdan ve farklı bir kurulum yolundan çalışacak. Şunları denetle ve gerekirse
düzelt:

- **Depo köküne bağlı yollar:** `core/config.py` içindeki `_project_root()`
  (`parents[3]`) ve `default_config_path()` depo düzenini varsayıyor. Paket
  editable olmayan biçimde kurulduğunda `configs/default.yaml` bulunamaz.
  Varsayılan yapılandırmayı paket verisi (`importlib.resources`) veya kurulum
  dizini üzerinden bulunur hale getir. Kodda başka depo-göreli yol, `__file__`
  varsayımı veya `C:\Users\gorke` gibi makineye özel yol kalmamalı.
- **Kurulum dizini salt okunurdur.** Uygulama kurulum dizinine yazmamalı; veri,
  log, önbellek ve kimlik veritabanı kullanıcı dizinlerine gitmeli
  (`%LOCALAPPDATA%\KineCapture`, `~/KineCapture/...`).
- **Konsolsuz çalışma:** `pythonw.exe` ile başlatıldığında `sys.stdout`/`stderr`
  `None` olabilir; buna yazan kod çökmemeli. Hatalar log dosyasına gitmeli.
- **Çocuk süreçler:** İş kuyruğu ve işleme alt süreçleri `sys.executable` ile
  ve konsolsuz modda da doğru başlamalı; yeni konsol penceresi açılmamalı.
- **Kaynaklar:** Qt eklentileri, fontlar, SVG ikonlar, tema dosyaları, logo ve
  önizleme modelleri kurulum sonrası bulunmalı.
- **ZED SDK yokken:** `pyzed` import edilemediğinde uygulama çökmemeli; kamera
  gerektirmeyen ekranlar açılmalı ve eksiklik anlaşılır biçimde söylenmeli.
- Paketin editable olmayan (wheel) kurulumunu klon ortamda yap ve test takımının
  ilgili kısmını o kurulumdan çalıştır.

### A5. Faz A teslimi ve kapı kararı

`knowledge/reports/` altına bir doğrulama raporu yaz: komutlar, sürümler,
sonuç tabloları, ölçek eğrileri, bulunan ve düzeltilen hatalar, açık kalanlar.
Kapı ancak şu durumda **geçti** sayılır: A2 export doğrulamaları yeşil, A3'te
çökme/veri hatası yok ve eşik aşımları ya düzeltilmiş ya da kullanıcı tarafından
kabul edilmiş, A4 maddeleri kapalı. Kapı durumunu kullanıcıya özetle; açık
madde varsa Faz B'ye geçmeden onay iste.

## Faz B — Temiz Windows kurucusu

### B1. Yayın ortamı

- `KineSynth` ortamını yeni bir ortama klonla; sürümler birebir aynı kalsın
  (Python 3.11.14, PySide6 6.10.1, numpy 2.4.6, OpenCV 4.12, pyzed 5.4).
  `kinecapture`'ı bu ortama **editable olmayan** wheel olarak kur
  (`conda-pack` editable/develop kurulumları paketlemez).
- Geliştirme bağımlılıklarının (pytest vb.) yayından çıkarılıp çıkarılamayacağını
  değerlendir; çıkarırsan ortamın yine çalıştığını doğrula.
- Ortamı `conda-pack` ile arşivle. Hedefte `conda-unpack` çalıştırıldıktan sonra
  ortamın başka bir yolda çalıştığını doğrula.

### B2. Sıfır veri garantisi

Kurucu **hiçbir mevcut kullanıcı verisini** içermez: kimlik veritabanı,
kullanıcı hesapları (mevcut admin dahil), projeler, katılımcılar, kayıtlar,
SVO/SVO2, run klasörleri, etiketler, export'lar, loglar, önbellekler,
kullanıcıya özel yapılandırma ve yollar. Ayrıca `.git`, `knowledge/`,
`promts/`, `.claude/`, `.agents/`, `.obsidian/`, `tests/` ve geliştirme
betikleri kurucuya girmez.

- Derleme sonunda kurucuya giren dosyaların bir **içerik manifesti** üret.
- Manifesti otomatik tara ve şu durumlarda derlemeyi **başarısız** say:
  `*.sqlite3`, `*.db`, `*.svo`, `*.svo2`, `run_*` klasörleri, log dosyaları,
  `identity`, kullanıcı adı veya `C:\Users\...` içeren yol/metin, düz metin
  parola şüphesi.
- Kurulumdan sonra uygulama **sıfır durumdan** açılmalı: boş proje listesi,
  yalnız B3'teki sistem sahibi hesabı.
- **Mevcut admin hesabı yalnız kurulum paketinden çıkarılır.** Bu bilgisayardaki
  `%LOCALAPPDATA%\KineCapture\identity.sqlite3` ve içindeki hesaplar olduğu gibi
  kalır; bu dosyayı açma, değiştirme, taşıma.

### B3. Sistem sahibi (admin) tohumu — yalnız hash

Kullanıcı kararı: Her kurulumda aynı sistem sahibi hesabı bulunacak.

- Kullanıcı adı: `gorkembektas`; ad: `Görkem`; soyad: `Bektaş`; rol: Sistem Sahibi
  (`UserRole.OWNER`). `title` alanı zorunludur; değerini kullanıcıya sor.
- Şifre **hiçbir yerde düz metin olarak bulunmaz.** Kurucuya yalnız mevcut
  `identity/passwords.py` ile üretilmiş `scrypt-v1` özeti girer: algoritma,
  parametreler, salt ve hash.
- Bunun için bir derleme betiği yaz (ör. `scripts/release/make_owner_seed.py`).
  Betik şifreyi `getpass` ile **iki kez** sorar, eşleşmeyi ve mevcut şifre
  kurallarını denetler, `hash_password` ile özet üretir ve yalnız özeti tohum
  dosyasına (ör. `owner_seed.json`) yazar. Şifre argüman, ortam değişkeni, dosya
  veya log ile alınmaz ya da yazılmaz.
- Bu betik etkileşimlidir; senin araç kabuğunda `getpass` çalışmayabilir.
  Betiği **kullanıcının kendi terminalinde** çalıştırmasını iste ve tam komutu
  ver. Kullanıcıdan şifreyi sohbete yazmasını isteme.
- Tohum dosyası yalnız derleme çıktısında (`dist/` veya `build/`, ikisi de
  `.gitignore`'da) bulunur; commit edilmez. Gerekirse `.gitignore`'a açık kural
  ekle.
- **Uygulama tarafı:** Kimlik veritabanı boşsa (`needs_initial_setup`) ve kurulum
  dizininde tohum dosyası varsa, ilk açılışta sistem sahibi hesabı bu hazır
  özetle oluşturulur. Düz şifre gerektirmeyen dar bir servis yolu ekle
  (ör. `create_initial_owner_from_digest`); denetim (audit) kaydı düşsün;
  mevcut `create_initial_owner` davranışı bozulmasın. Tohum varken "Sistem
  Sahibi oluştur" kurulum ekranı görünmez; tohum yoksa mevcut davranış sürer.
- Kimlik veritabanı `%LOCALAPPDATA%` altında kullanıcı başınadır; aynı
  bilgisayardaki başka bir Windows kullanıcısı da ilk açılışta aynı tohumla
  sistem sahibini alır. Bunu ikinci bir Windows kullanıcı hesabıyla veya eşdeğer
  izole bir `LOCALAPPDATA` ile test et.
- Hedefte **zaten dolu** bir kimlik veritabanı varsa (eski kurulum) ona
  dokunma; başka bir sistem sahibi varsa üzerine yazma, birleştirme veya silme
  yapma. Durumu logla ve kullanıcıya gösterilecek anlaşılır bir mesaj üret.
  Böyle bir geçiş gerekirse ayrı karar olarak kullanıcıya sor.
- Tohum dosyasındaki özet, kurulum dosyasını alan biri tarafından çevrimdışı
  kaba kuvvet denemesine açıktır. Bunu raporda sınır olarak yaz; özetten başka
  hiçbir gizli bilgiyi pakete koyma.
- Testler: tohumla ilk açılış, tohumsuz ilk açılış, dolu veritabanı, bozuk
  tohum dosyası, yanlış şifreyle giriş, doğru şifreyle giriş (testte geçici,
  test amaçlı bir şifreyle üretilmiş tohum kullan; kullanıcının şifresini
  kullanma). Kurucu çıktısında ve tüm repoda düz metin şifre olmadığını
  otomatik tara.

### B4. Kurulum öncesi uyumluluk denetimi (preflight)

Kurucu çalışınca **ilk iş** hedef bilgisayarı denetler. Her şey uygunsa kuruluma
geçer; değilse **hiçbir değişiklik yapmadan** durur ve eksikleri Türkçe, açık
bir listeyle gösterir (bulunan sürüm, gereken sürüm, ne yapılmalı).

Kullanıcının belirlediği uyumluluk kuralı:

- **ZED SDK: birebir 5.4.1.** Kurulum konumu, sürüm bilgisi ve uygulamanın
  ihtiyaç duyduğu SDK DLL'lerinin varlığı denetlenir. Sürümü nereden ve nasıl
  okuduğunu (kayıt defteri, ortam değişkeni, SDK başlık dosyası, SDK aracı vb.)
  bu makinede gerçekten doğrula; tahmin etme.
- **NVIDIA GPU mevcut** olmalı.
- **NVIDIA sürücüsü ≥ minimum:** Minimum sürüm, ZED SDK 5.4.1'in derlendiği
  CUDA sürümüne göre belirlenir. CUDA sürümünü kurulu SDK'dan, minimum sürücü
  sürümünü NVIDIA'nın resmi CUDA uyumluluk tablosundan al ve kaynağını raporla.
  Sürücünün birebir aynı olması **gerekmez**.
- SDK'nın ihtiyaç duyduğu CUDA çalışma zamanı bileşenleri erişilebilir olmalı.
- Windows 10/11 x64, yeterli disk alanı ve gerekiyorsa Visual C++
  Redistributable.

Uygulama yöntemi senin kararındır (Inno Setup Pascal betiği, küçük bir
denetim aracı veya ikisi birden). Şartlar:

- Denetim mantığı test edilebilir olsun; algılama fonksiyonlarını sahte
  değerlerle (SDK yok, SDK 5.4.0, sürücü eski, GPU yok, hepsi uygun) sınayan
  otomatik testler yaz.
- Sonuç bir log dosyasına da yazılsın; kurucunun yalnız denetim yapan bir modu
  olsun (ör. `/checkonly` veya eşdeğeri).
- Kurulum sonrası doğrulama: kurulu ortamda `pyzed` import edilir ve sürümü SDK
  ile eşleşir; uygulama konsolsuz ve başsız bir öz-denetim (self-check) komutuyla
  açılış yolunu doğrular. Böyle bir komut yoksa ekle.

### B5. Kurucu

- Araç: Inno Setup (veya gerekçeli eşdeğeri). Kurulu değilse kurmadan önce
  kullanıcıya sor.
- Kurucu: preflight → ortam arşivini açma → `conda-unpack` → kısayollar
  (`pythonw.exe -m kinecapture` veya eşdeğer başlatıcı, konsol penceresi yok) →
  kurulum sonrası doğrulama.
- Kurulum yolu: Boşluk ve Türkçe karakter içeren yolları (ör. `Program Files`,
  Türkçe karakterli Windows kullanıcı adı) gerçekten dene; güvenli çalışan
  varsayılanı seç ve gerekçesini yaz. Kurulum dizinine çalışma zamanında
  yazılmadığını doğrula.
- Kaldırıcı (uninstaller) yalnız program dosyalarını siler; veri setleri,
  kimlik veritabanı ve loglar kalır. Aynı sürümün yeniden kurulumu ve üstüne
  kurulum veriyi korur.
- Kurucu imzalı değilse Windows SmartScreen uyarısı çıkacağını raporda belirt;
  kod imzalama bu görevin kapsamı dışında.
- Derleme tek komutla yeniden üretilebilir olsun (ör.
  `scripts/release/build_installer.ps1`): klon ortam kontrolü → wheel → conda-pack
  → tohum dosyası varlığı → Inno Setup → içerik manifesti ve taramalar.
  Tohum dosyası yoksa derleme durur ve kullanıcıya B3 komutunu söyler.

### B6. Başka bilgisayara kurulabilirlik doğrulaması

- **Olumsuz yol:** ZED SDK ve NVIDIA sürücüsü bulunmayan temiz bir ortamda
  (ör. Windows Sandbox) kurucunun hiçbir şey değiştirmeden durduğunu ve doğru
  eksik listesini gösterdiğini doğrula.
- **Olumlu yol:** Bu bilgisayarda yeni bir Windows kullanıcı hesabıyla (boş
  `LOCALAPPDATA`) veya eşdeğer izolasyonla: kurulum, ilk açılışta yalnız
  `gorkembektas` hesabı, boş proje listesi, mock backend ile kayıt → işleme →
  etiketleme → export zinciri, gerçek ZED bağlıysa kamera bağlantısı, kaldırma
  ve yeniden kurulum.
- Gerçekten ayrı bir fiziksel bilgisayarda deneme senin yapabileceğin bir şey
  değildir. Kullanıcı için kısa bir **hedef makine kontrol listesi** hazırla ve
  bu madde kullanıcı deneyene kadar raporda **açık** kalsın.

## Teslim ve belgeleme

- `knowledge/reports/` altında Faz A ve Faz B doğrulama raporları (komutlar,
  sürümler, sonuçlar, ölçümler, sınırlar, açıklar).
- [Karar notunu](../knowledge/decisions/windows-installer-release-2026-09-23.md)
  uygulama sonucuyla güncelle; `MEMORY_INDEX.md` güncel durum ve sonraki adımı
  düzelt; gerekiyorsa `promts/index.md`.
- Wiki, rapor, commit mesajı ve loglarda yalnız kullanıcı adı (`gorkembektas`)
  geçer; **şifre ve şifre özeti** geçmez.
- Kullanıcıya son özet: kapı durumu, kurucu dosyasının yolu ve boyutu,
  preflight kuralları, yapılan ve yapılamayan doğrulamalar, hedef makine kontrol
  listesi.
