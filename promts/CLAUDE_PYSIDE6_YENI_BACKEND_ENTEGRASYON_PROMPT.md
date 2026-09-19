# Claude Code görevi — KineCapture Studio arayüzünün PySide6 ile yeniden yapımı

> **Bu görevin izi:** [faz planı](../knowledge/archive/reports/FAZ_PLANI_PYSIDE6_STUDIO.md) · [F1 durum tespiti](../knowledge/archive/reports/F1_MEVCUT_DURUM_TESPITI_2026-09-13.md) · [Studio F0–F15](../knowledge/milestones/studio-f0-f15.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


## 0. Bu görevin niteliği

Bu bir yama veya uyumluluk düzeltmesi **değildir**. Uygulamanın arayüzü,
yeni backend mimarisine göre **son ürün kalitesinde yeniden yapılacaktır.**

Hedef: PySide6 sürümü o kadar iyi olsun ki, C# + WinUI 3 geçişi bir zorunluluk
değil, ölçülmüş bir tercih hâline gelsin. Geçiş kararı bu sürümün gerçek
performans değerlerine bakılarak verilecektir.

Bu yüzden:

- Görsel incelik, tutarlılık ve cila **isteniyor**.
- Performans ve dayanıklılık (robustness) **birinci sınıf gereksinimdir**.
- Eksik ekranlar ve eksik yetenekler bu görevde **tamamlanacaktır**.
- Backend tarafında arayüzün ihtiyaç duyduğu bir şey eksikse, o eksik de bu
  görev kapsamında **kapatılacaktır** (kurallar Bölüm 9'da).

Önceki sürümde etiketleme ekranı bilgisayarı ciddi biçimde zorluyordu. Bu, bu
görevin en önemli çözülmesi gereken problemidir ve bir "sonra bakarız" maddesi
değildir.

---

## 1. Proje bağlamı

Bu repo (`KineCapture Studio`, Python paketi `kinecapture`) ZED 2i kamerasıyla
işaretleyicisiz hareket yakalama yapan bir Windows masaüstü uygulamasıdır.
Kullanıcıları: sahada çalışan **antrenörler** ve projeyi geliştiren
**araştırmacı**.

Son iki haftada backend mimarisi kökten değişti. Değişiklikler başka bir ajanla
yapıldı ve `KINECAPTURE_BACKEND_MIMARI_UYGULAMA_RAPORU_2026-09-11.md` dosyasında
belgelendi. **Bu raporu tamamen oku.** Ayrıca inceleme raporu
`KINECAPTURE_SQUAT_OFFLINE_INCELEME_RAPORU_2026-09-10.md` arka planı verir;
onu indeksinden hedefli oku.

### Yeni ürün akışı

```
Capture (yalnız ham kayıt)  →  Verileri Hesapla (offline)  →  İşlenen Videolar  →  Etiketleme
```

### Backend'de değişenler — özet

Aşağıdaki özet raporun yerine geçmez, yönü verir.

- Canlı yakalama artık **minimum ham kayıt** yapar: HD720/60, H264_LOSSLESS
  SVO2. Canlı SDK body tracking, canlı depth retrieval/arşivleme, tam
  çözünürlük RGB kopyası, canlı skeleton dosyası ve proxy video **kapalıdır**.
- Canlı önizleme hafiftir: hedef 15 FPS, 640 px RGB; üzerine CPU'da çalışan
  hafif bir **2B pose** (OpenCV DNN / MediaPipe modelleri) binmektedir. Bu
  çıktı 2B'dir, metrik ZED iskeleti veya katılımcı kimliği değildir.
- Operatörün kişi seçimi (`subject anchor`) **gösterilen kareye** bağlanır:
  kamera timestamp'i, backend frame ordinal'i, kaynak çözünürlüğü, tıklama
  noktası, bbox.
- Offline işleme `kinecapture.processing` altında, GUI'den bağımsız çalışır.
  Varsayılan BODY_38 / HUMAN_BODY_ACCURATE / NEURAL_PLUS / fitting açık.
  Her deneme `derived/processing/.run_<id>.partial` altında başlar, `job.json`
  içinde durum/ilerleme/hata tutar, başarıda atomik rename ile `run_<id>`
  olarak yayımlanır.
- `ReviewDataset`, SDK veya Qt import etmeden tamamlanmış bir sürümü
  checksum'larıyla açar; iskelet, video ve dizilere erişim verir.
- Yeni etiketler canonical sidecar'a yazılır:
  `annotations/processing/run_<id>.json` — kaynak fingerprint + SVO pozisyonu +
  kamera timestamp sınırları, inclusive aralıklar. Eski `segments.json`
  otomatik taşınmaz.
- Take işlenmeyi beklerken `awaiting_processing`, manifest eşlemesi
  `pending_offline_timestamp_reconciliation` durumundadır.
- Sürümler: app **0.11.0**, capture policy **2**, take **1.2.0**, skeleton
  stream **1.2.0**, raw archive **1.1.0**, processing **1.0.0**, canonical
  annotation sidecar **1.0.0**, subject association **1.1.0**.

---

## 2. Mimari kural — WinUI geçişini ucuzlatan tek karar

Arayüzü **üç katmanlı** yaz ve bu ayrımı hiçbir yerde bozma:

```
  Views (PySide6 widget'ları)     ← yalnız çizim ve olay yönlendirme
        ↕
  ViewModels (saf Python)         ← durum, komut, biçimlendirme; Qt import ETMEZ
        ↕
  Services (saf Python)           ← backend'e tek giriş noktası; Qt import ETMEZ
```

**Neden:** WinUI 3'e geçilirse yalnız en üst katman yeniden yazılır; ViewModel
ve Service katmanları kavramsal olarak birebir taşınır. Bu ayrım yapılmazsa
geçiş sıfırdan yazım demektir.

**Kural:** `viewmodels/` ve `services/` altındaki hiçbir modül `PySide6`,
`QtCore`, `QtWidgets` veya `QtGui` import etmez. Bunu doğrulayan bir test yaz:
bu paketler Qt kurulu olmayan bir alt süreçte import edilebilmeli.

ViewModel → View iletişimi için ince bir sinyal adaptörü kullan (ViewModel saf
Python callback listesi yayınlar; adaptör bunları Qt sinyaline çevirir).

---

## 3. Görsel dil ve tema

### Karakter

Koyu, nötr, yoğun, sessiz. Referans karakter **DaVinci Resolve**: katmanlı gri
yüzeyler (arka plan en koyu, paneller bir ton açık, kontroller bir ton daha
açık), 1 piksel ayırıcılar, neredeyse yuvarlatma yok, küçük ve sıkı tipografi.

**Renk anlam taşır, süs değildir.** Kırmızı yalnız kayıt ve hata; sarı yalnız
uyarı ve belirsizlik; yeşil yalnız canlı/tamam; mavi yalnız seçim. Başka yerde
renk kullanma.

Sayısal alanlar (FPS, süre, kare sayısı, açı, gecikme) **eşit genişlikli
(monospace)** yazı kullanır; değer değişirken düzen zıplamaz.

**Kaçınılacaklar:** büyük kartlar, geniş boşluk, gradyan, gölge, cam/bulanıklık,
gereksiz animasyon, pazarlama tipografisi, jenerik "AI dashboard" görüntüsü.

Viewport'lar süslenmez: köşe yuvarlatma, gölge, çerçeve efekti yok; en fazla
1 piksel kenarlık. Bilimsel görüntüde piksel doğruluğu estetiğin önündedir.

### Token sistemi — tek gerçek kaynak

Bütün renk, boşluk, yarıçap, tipografi değerlerini **tek bir `tokens.json`**
dosyasında topla. Bir üretici (generator) bu dosyadan QSS üretsin. Sayfa veya
widget içinde asla literal renk/ölçü yazma.

Token adlarını WinUI kaynak adı gibi seç (`KcSurfaceBase`, `KcAccentPrimary`,
`KcStatusRecording`, `KcSpacingM`, `KcRadiusControl`, `KcMono` …). Böylece
WinUI'ye geçilirse aynı dosyadan `ResourceDictionary` üretilir.

Koyu tema birincildir. Açık tema aynı token setinden ikinci bir değer kümesi
olarak tanımlansın; ilk sürümde eksiksiz olması şart değil ama yapı hazır olsun.

### Erişilebilirlik

- Renk tek başına bilgi taşımaz: her durum göstergesi **renk + ikon + metin**.
- Tüm eylemler klavyeden erişilebilir; odak görünür.
- Yüksek DPI (125/150/200%) ölçeklemede kırpılma olmaz.
- İkonlar için serbest lisanslı tek bir set kullan (Lucide / Phosphor /
  Fluent System Icons), tek çizgi kalınlığında, SVG olarak.

---

## 4. Kullanıcı modeli — katmanlı yüzey

**Varsayılan arayüz antrenör içindir ve sadedir. Derinlik istendiğinde açılan
ikinci bir katmandadır. Hiçbir zaman zorunlu, hiçbir zaman gizli değildir.**

Teknik bilgi (model adı, checksum, engine, SDK parametreleri, süreler, dosya
yolları) ana ekranda durmaz; "Ayrıntılar" ve yardımcı pencerelerde yaşar.

Bu sürümde **rol tabanlı kısıtlama yoktur**. Tüm kullanıcılar log ve tanılama
dahil her şeye erişir. Tek istisna hesap ve proje yönetiminin mevcut davranışı.

---

## 5. Performans — ölçülebilir hedefler

Bu bölüm görevin en kritik parçasıdır. Önceki sürümde etiketleme ekranı
bilgisayarı zorluyordu; bu tekrarlanmayacak.

### Bütçeler (kabul kapıları)

Referans donanım: RTX 2060 6 GB, i7-10750H, ~16 GB RAM.

| Ölçüm | Hedef |
|---|---|
| Etiketleme ekranında UI kare süresi (boşta) | ≤ 8 ms |
| Timeline yeniden çizimi (60 dk oturum, tam görünüm) | ≤ 16 ms |
| Scrub sırasında kare gösterimi gecikmesi | ≤ 50 ms |
| Zoom/pan etkileşiminde düşen kare | yok (60 Hz korunur) |
| 60 dk oturum açıldığında bellek artışı | ≤ 1,5 GB |
| Uygulama soğuk açılış | ≤ 3 s |
| Proje/take listesi 1000 kayıtla kaydırma | takılma yok |
| Canlı yakalamada GUI'nin kayıt hattına etkisi | ölçülebilir kayıp yok |

Bu sayılar **ölçülecek ve raporlanacaktır.** "Hızlı hissettiriyor" kabul
edilmez.

### Zorunlu teknikler

- **Timeline kendi çizimini yapar.** Widget yığını değil, tek bir
  `QWidget.paintEvent` (veya `QGraphicsView` yerine doğrudan `QPainter`).
  Yalnız **görünür zaman aralığı** çizilir. Uzun oturumlar için önceden
  hesaplanmış **çok çözünürlüklü özet** (ses dalga formundaki gibi min/max
  decimation) kullanılır; her zoom seviyesi kendi özetinden çizer.
- **Statik katmanlar pixmap'e önbelleklenir.** Şerit arka planları, ızgara,
  zaman cetveli değişmedikçe yeniden çizilmez; yalnız playhead ve seçim üstte
  çizilir.
- **Video oynatma proxy üzerinden yapılır**, ham SVO'dan değil. Kare dönüşümü
  (BGR→RGB, ölçekleme) her karede yeniden alokasyon yapmaz; önceden ayrılmış
  tampon kullanılır. Mümkünse `QImage` sarmalaması kopyasız olsun.
- **3B iskelet `QOpenGLWidget` üzerinde çizilir.** Matplotlib veya yazılımsal
  çizim kullanma. Köşe verisi VBO'ya yüklenir; her karede tüm sahne yeniden
  kurulmaz.
- **Diziler bellek eşlemeli (memory-mapped) okunur.** `.npz` tamamını RAM'e
  açmak yasak. Backend `.npz` veriyorsa Bölüm 9'daki kuralla `.npy` memmap
  seçeneği eklenir.
- **Listeler sanallaştırılır.** Satır başına widget üretme; `QAbstractItemModel`
  + `QTableView`/`QListView` kullan.
- **Metrikler saniyede 2–4 kez güncellenir**, kare başına değil.
- **Disk ve hesaplama GUI thread'inde yapılmaz.** `QThreadPool` veya ayrı
  süreç. Offline işleme zaten ayrı süreçtir.
- **Tembel yükleme.** Bir take açıldığında yalnız görünür aralığın verisi
  okunur; tamamı değil.

### Profil kapısı

Her fazın sonunda `cProfile` veya `py-spy` ile bir ölçüm al ve sonucu raporla.
Bütçe aşılıyorsa faz tamamlanmış sayılmaz.

---

## 6. Ekran ekran kapsam

Aşağıdaki ekranların **hepsi** bu görevin kapsamındadır.

### 6.1 Uygulama kabuğu

- Altta ana gezinme şeridi, iş akışı sırasıyla:
  **Projeler · Yakalama · Verileri Hesapla · İşlenen Videolar · Etiketleme ·
  Veri Seti · Dışa Aktarım · Ayarlar**
- Üstte ince bağlam şeridi: aktif proje / katılımcı / oturum, kamera durumu,
  veri klasörünün geçerliliği, disk durumu.
- Sağda isteğe bağlı açılan inceleme paneli (inspector); kapalıyken yer
  kaplamaz.
- Pencere durumu (boyut, panel genişlikleri, açık sekme) kalıcı olarak saklanır.

### 6.2 Projeler ve Katılımcılar

- Liste odaklı, sanallaştırılmış. Arama ve filtre.
- Proje / katılımcı / oturum hiyerarşisi net.
- Yeni oturum başlatma buradan.
- Silme ve arşivleme mevcut yıkıcı-işlem kurallarına uyar.

### 6.3 Yakalama (Capture)

- Büyük RGB önizleme; hafif 2B pose kaplaması üzerine çizilir.
- Bu görüntünün **tanılama amaçlı** olduğu, metrik iskelet olmadığı kısa bir
  metinle belirtilir.
- Kayıt modu seçimi: `Hızlı kayıt · İskeleti sonra çıkar` (varsayılan) ve
  `Canlı iskelet · Daha yüksek sistem yükü`. İkincisi ek maliyet olarak
  işaretlenir.
- **Kişi seçimi:** operatör önizlemede tıkladığında anchor, gösterilen karenin
  kamera timestamp'i + frame ordinal + kaynak çözünürlüğü + tıklama noktası +
  bbox ile kaydedilir. Yeniden bir kare okuyup onu kullanma.
- Taşıma çubuğu: kayıt düğmesi, süre, dosya boyutu, kalan disk, diskten kalan
  yaklaşık kayıt süresi.
- Kayıt durumu eş zamanlı olarak birden fazla yerde bildirilir (düğme, görüntü
  kenarında ince kırmızı çerçeve, pencere başlığı).
- Metrikler: gerçek yakalama FPS'i, timestamp jitter, kayıt kuyruğu doluluğu,
  SDK sayaçları, disk yazma hızı. **Önizleme kaybı ile kayıt kaybı ayrı
  gösterilir.**
- Kayıt bitişi: *"Ham kayıt kaydedildi · İskelet bekliyor"* + `Şimdi işle` /
  `Kuyruğa ekle`. Gövde bulunamadı diye kayıt başarısız gösterilmez.

### 6.4 Verileri Hesapla (yeni ekran)

- Bekleyen / işlenen / tamamlanmış / başarısız işler.
- İşleme ayrı süreç olarak başlar; GUI asla bloklanmaz.
- İlerleme `job.json`'dan okunur. Toplam bilinmiyorsa yüzde uydurulmaz;
  *"İşlenen 412 / doğrulanmış 900 kare"* biçiminde gösterilir.
- Tahmini süre, model ısınmasından sonra ölçülen gerçek hızdan üretilir.
- Eylemler: başlat, duraklat, iptal, yeniden dene (`--restart`).
  **"İptal" ham kaydı silmez** — arayüzde açıkça yazar.
- Yeni canlı kayıt başladığında çalışan iş güvenli sınırda duraklar:
  *"Kayıttan sonra devam edecek."*
- Kapsam uyuşmazlığı (`source_frame_count_mismatch`,
  `capture_frames_unmatched`) açıkça bildirilir; "eksiksiz" denmez.
- İşleme parametreleri (BODY formatı, model seviyesi, depth modu, fitting)
  görünür ve değiştirilebilir; varsayılanlar backend'den gelir.

### 6.5 İşlenen Videolar (yeni ekran)

Şu an hiç yok; yeni akışın eksik halkası.

- Tamamlanmış `run_<id>` sürümlerinin kütüphanesi.
- Her satır: katılımcı, tarih, süre, kaynak kapsamı, kişi sayısı, seçili sporcu
  durumu, QC işaretleri, kullanılan model/parametre özeti.
- Küçük önizleme görüntüleri (thumbnail) — arka planda üretilir ve
  önbelleklenir; liste kaydırırken üretim yapılmaz.
- Aynı take'in birden fazla sürümü yan yana karşılaştırılabilir.
- Buradan doğrudan etiketlemeye geçilir.
- Filtreler: işlenmiş / kontrol bekliyor / başarısız / kişi seçilmemiş.

### 6.6 Etiketleme (Review) — en kritik ekran

- Üstte senkron görünümler, altta çok şeritli zaman çizelgesi.
- **Görünümler:** proxy video, 2B iskelet kaplaması, ve **3B iskelet görünümü**.
- **3B görünüm, offline hesaplanan derinlik ve iskelet verisiyle yeniden
  çizilir.** Bu şu an eksik ve bu görevde tamamlanacaktır. Döndürme, yakınlaşma,
  kaydırma; kamera açısı kalıcı; sıfırlama kısayolu.
- Video, 2B kaplama, 3B iskelet ve timeline **her zaman aynı karededir.**
  Senkronizasyon kare indeksi üzerinden değil, kaynak timestamp'i üzerinden
  kurulur.
- **Timeline şeritleri:** video · iskelet güvenilirliği · QC işaretleri ·
  belirsiz kişi aralıkları · kullanıcı anotasyonları · olay işaretleri.
  Şerit başlıkları solda sabit, içerik yatay kayar.
- Etkileşim: sürükleyerek gezinme, yatay zoom (Ctrl+tekerlek), pan (orta tuş),
  kare kare ilerleme (`,` / `.`), aralık seçip etiketleme, snap
  (kare / saniye / anotasyon sınırı).
- Zoom sırasında playhead çapa olarak sabit kalır.
- **Sürüm bağı:** hangi `run_<id>` açık olduğu görünür; sürüm değiştirilebilir.
  Yeni sonuç geldiğinde *"mevcut etiketler önceki sonuca bağlı"* uyarısı çıkar;
  otomatik taşıma yapılmaz.
- Etiketler canonical sidecar'a yazılır.
- Eski `segments.json` verisi olan take açıldığında kullanıcı bilgilendirilir;
  açık bir işlemle dönüştürülebilir, sessizce değil.
- **Sporcu seçimi ve belirsiz aralık onayı** bu ekranda yaşar: aday kişiler için
  başlangıç/orta/son görüntü kartları, görünme süresi, kopma sayısı. Başlıklar
  "Kişi 1", "Kişi 2"; teknik takip kimliği küçük ayrıntı. Yalnız belirsiz
  aralıklar sorulur: *"Aynı sporcu" / "Diğer kişi" / "Bu bölümde sporcu yok"*.
  Sistem sessizce en yakın kişiye düşmez.

### 6.7 Veri Seti

- Tüm kayıtların toplu görünümü; filtreleme, kalite ve kapsam işaretleri.
- Toplu işlemler (toplu işleme kuyruğuna alma, toplu etiket kontrolü).
- Kapsamı doğrulanmamış take'ler açıkça ayrışır.

### 6.8 Dışa Aktarım

- Format seçimi, hedef klasör, ilerleme, iptal.
- Kişi onayı eksik veya kapsamı doğrulanmamış veri sessizce dışa aktarılmaz;
  kullanıcı açıkça onaylar veya engellenir.
- Dışa aktarılan her paket hangi `run_<id>` ve hangi anotasyon revizyonundan
  geldiğini taşır.

### 6.9 Ayarlar

Yeni backend'e göre **baştan gözden geçirilecek.** En az şu gruplar:

- **Kayıt:** çözünürlük/FPS, codec, ham ürün seçimi (her ürünün maliyeti
  yazılı), disk hedefi ve alan uyarı eşiği
- **Önizleme:** hedef FPS, çözünürlük, 2B pose açık/kapalı
- **İşleme:** varsayılan BODY formatı, model seviyesi, depth modu, fitting,
  precision, eşzamanlı iş sayısı, gece işleme
- **Veri:** veri kökü, geçerlilik durumu, taşıma/doğrulama araçları
- **Görünüm:** tema, yoğunluk, dil
- **Gelişmiş:** log seviyesi, tanılama, model önbellek klasörü

Her ayarın yanında ne işe yaradığı bir cümleyle yazılı olsun. Ayarlar diske
atomik yazılsın; geçersiz değer uygulamayı kilitlemesin.

### 6.10 Yardımcı pencereler (ayrılabilir)

Ana akışı engellemeyen, ikinci monitöre taşınabilen modeless pencereler:

| Pencere | İçerik |
|---|---|
| Log Konsolu | Canlı akış, seviye filtresi, arama, dosyaya kaydet |
| Tanılama | Kare zamanlaması, kuyruklar, aşama süreleri, RAM/VRAM, GPU, disk |
| Cihaz Bilgisi | ZED seri no, firmware, SDK sürümü, gerçek FPS, kalibrasyon |
| Kaynak Denetimi | Ledger sayısı, SDK bildirimi, çözülen kare, timestamp boşlukları, checksum |
| Köken (Provenance) | Bu sürümü üreten model, parametreler, kod revizyonu, çıktı hash'leri |
| Ham Parametreler | Aktif ZED yapılandırması; requested / applied ayrı |

---

## 7. Hata ve durum dili

İki katmanlı: **görünen katman** ne olduğunu ve ne yapılacağını sade Türkçe,
teknik terimsiz söyler ve tek birincil eylem sunar; **"Ayrıntılar"** hata kodu,
teknik açıklama ve ilgili log satırlarını açar.

| Durum | Söylenecek | Söylenmeyecek |
|---|---|---|
| Veri klasörü geçersiz | "Yeni kayıt için veri klasörü seçin" | Take'leri kayıp saymak, DB'yi otomatik temizlemek |
| Disk yetersiz | İhtiyacı önceden göster, alternatif sun | İş ortasında durup "tamamlandı" demek |
| Model ilk açılışı | "İşlem hazırlanıyor" | Açılış süresini klip tahminiyle karıştırmak |
| Kişi bulunamadı | "Bu bölümde kişi bulunamadı" | Tespitsiz kareyi düşen kare saymak |
| Kimlik değişti | "02:13–02:16 arasında sporcuyu doğrulayın" | Sessizce en yakın kişiye geçmek |
| Kapsam uyuşmuyor | "Kaynak kapsamı doğrulanamadı" | "Eksiksiz" demek |
| İşlem yarım kaldı | "İşlem yarım kaldı; ham kayıt güvende" | Yarım sonucu tamamlanmış göstermek |

---

## 8. Dayanıklılık (robustness)

- Uygulama **hiçbir koşulda kullanıcı verisini bozmaz.** Mevcut atomik yazım ve
  değişmez ham varlık kuralları korunur.
- Beklenmeyen istisna arayüzü çökertmez: yakalanır, kullanıcıya anlaşılır
  şekilde bildirilir, loglanır, uygulama kullanılabilir kalır.
- Uygulama kapanırken çalışan işler güvenli sonlandırılır; yarım çıktı
  yayımlanmaz.
- Uygulama çöküp yeniden açıldığında: yarım işler `failed`/`partial` görünür,
  ham kayıtlar sağlam, etiketler kayıpsız.
- Backend süreci ölürse arayüz bunu fark eder ve yeniden başlatma sunar.
- Kamera bağlantısı koparsa kayıt güvenli kapatılır, kullanıcı bilgilendirilir.
- Uzun dosya yolu sorunu (WinError 3) yüzeye çıkmadan ele alınır.
- Otomatik kurtarma testleri yaz: çöküş simülasyonu, disk dolu, süreç
  sonlandırma.

---

## 9. Backend'de eksik kapatma — kurallar

Arayüzün ihtiyaç duyduğu bir şey backend'de yoksa **eklenebilir**, ancak:

1. Önce eksiği **bana bildir** ve ne ekleyeceğini bir paragrafla anlat. Küçük
   ve açık eksikler için onay beklemeden devam edebilirsin; mimari etkisi olan
   bir değişiklik için onay bekle.
2. **Mevcut sözleşmeleri bozma.** Var olan dosya biçimleri, durum adları ve
   modül sınırları korunur.
3. **Şema değişikliği sürüm artışı gerektirir** ve `MEMORY.md`'ye yazılır.
4. Backend **Qt import etmez** ve GUI'den bağımsız kalır. `process_take` ve
   `ReviewDataset`'in bağımsızlığı korunmalı; bunu doğrulayan mevcut test
   çalışmaya devam etmeli.
5. Ham veri değişmezliği ve atomik yayın ilkeleri asla gevşetilmez.
6. Doğrulanmamış `pyzed` çağrısı yazma.

### Beklenen muhtemel eksikler

Bunlar tahmindir; gerçeğini kodu okuyarak tespit et:

- Dizilerin **bellek eşlemeli** okunabilmesi (`.npz` yerine `.npy` seçeneği)
- Timeline için **önceden hesaplanmış çok çözünürlüklü özet** üretimi
- **Thumbnail üretimi** (işlenen videolar ekranı için)
- 3B görünüm için **offline derinlikten yeniden çizim** verisinin hazır sunumu
- İş kuyruğunun **ilerleme ve tahmini süre** alanları
- Eski `segments.json` → canonical sidecar **açık dönüştürme** yolu
- Take/sürüm listesini ucuz okuyan bir **özet indeksi** (her klasörü taramadan)

---

## 10. Fazlar

Her faz kendi commit'ini alır, çalıştırılır, ölçülür ve raporlanır.
Bir faz tamamlanmadan sonrakine geçilmez.

| Faz | İçerik | Bitti sayılma ölçütü |
|---|---|---|
| **F0** | Hafıza politikası + `MEMORY_INDEX.md` (Bölüm 11) | İndeks üretildi, özeti bana verildi |
| **F1** | Mevcut durum tespiti: ne kırık, ne eksik, nerede yavaş | Önceliklendirilmiş liste + **onay bekle** |
| **F2** | İskelet: katman ayrımı, token sistemi, QSS üretici, kabuk, gezinme, tema | Uygulama açılıyor, tema tutarlı, Qt-bağımsızlık testi geçiyor |
| **F3** | Projeler / Katılımcılar / Ayarlar | Sanallaştırılmış listeler, ayarlar atomik, 1000 kayıtla takılma yok |
| **F4** | Yakalama | Mock ile tam kayıt turu; anchor doğru kaydediliyor; metrikler ayrı |
| **F5** | Verileri Hesapla | İşleme ayrı süreçte, ilerleme gerçek, iptal/restart çalışıyor |
| **F6** | İşlenen Videolar | Kütüphane, thumbnail önbelleği, sürüm karşılaştırma |
| **F7** | Etiketleme — timeline ve senkronizasyon | **Performans bütçeleri ölçülüp raporlandı** |
| **F8** | Etiketleme — 3B iskelet görünümü (offline derinlikle) | OpenGL çizim, senkron, kamera kontrolü |
| **F9** | Sporcu seçimi ve belirsiz aralık onayı | Sessiz fallback yok, onay revizyonu yazılıyor |
| **F10** | Veri Seti + Dışa Aktarım | Sürüm ve onay bağı korunuyor |
| **F11** | Yardımcı pencereler | Altısı da çalışıyor, ana akışı engellemiyor |
| **F12** | Dayanıklılık: çöküş/kurtarma testleri, hata dili geçişi | Kurtarma senaryoları geçiyor |
| **F13** | Cila: klavye, DPI, erişilebilirlik, boş/hata/yükleniyor durumları | Kontrol listesi tamam |
| **F14** | Uçtan uca deneme + final performans raporu | Tam tur çalıştı, bütçe tablosu dolduruldu |

Gerçek ZED ile doğrulama bu görevin kapsamı **değildir** (kullanıcı kamerayı
bağladığında ayrıca yapılacak), ama arayüz kamera bağlıyken çalışacak biçimde
yazılmalıdır.

---

## 11. F0 — Hafıza politikası (ilk iş)

`MEMORY.md` 180 KB'ye ulaştı ve "her görevde tamamını oku" kuralı her oturumda
ciddi bağlam israfına yol açıyordu. Bu kural kaldırıldı.

1. Repo kökündeki **`CLAUDE.md` ve `AGENTS.md` güncellendi.** Onları oku; yeni
   politika oradadır.
2. **`MEMORY_INDEX.md` oluştur** (≤6 KB): güncel faz ve tek cümlelik durum;
   sürüm tablosu; `src/kinecapture/` modül haritası (alt paket başına bir
   satır); `MEMORY.md` bölüm dizini (başlık + neyi kapsadığı, tek satır);
   bilinen açıklar; anlaşılan sonraki adım.
3. `MEMORY.md`'nin en üstüne kısa bir kullanım notu ekle: bu bir arşivdir,
   baştan sona okunmaz, giriş noktası `MEMORY_INDEX.md`.
4. `MEMORY.md` içinde hâlâ "her görevde tamamını oku" veya "her görev sonunda
   güncelle" diyen ifadeleri yeni politikayla değiştir.
5. Bu iş için `MEMORY.md`'yi bir kez baştan sona taraman gerekecek —
   **bu tek seferliktir.**

---

## 12. Çalışma kuralları

- **Faz başına bir commit.** Tek commit'te birden fazla ekran değiştirme.
- **Her fazda derle, çalıştır, ekran görüntüsü al, gördüğünü raporla.**
  "Şimdilik çalışmıyor ama sonra düzelir" kabul değil.
- **Ölçmediğin performansı iddia etme.** Bütçe tablosundaki her satır gerçek
  ölçümle doldurulur.
- Yalnız `KineSynth` conda environment'ı kullanılır.
- Mock backend bozulmaz; testler onun üzerinden yürür.
- Test edilmemiş özellik tamamlanmış sayılmaz; ne çalıştırdığını ve ne
  gözlemlediğini söyle.
- Kullanıcı verisi silinmez, üzerine yazılmaz; ham kayıt değişmezdir.
- Token dışında literal renk/ölçü yazma.
- `viewmodels/` ve `services/` Qt import etmez.
- Faz bittiğinde `MEMORY.md`'ye yalnız kalıcı olanı yaz, `MEMORY_INDEX.md`'yi
  güncelle.

## 13. Başlangıç

**F0'ı yap, sonra F1'i yap, sonra dur.** F1'in çıktısını (ne kırık, ne eksik,
nerede yavaş — önceliklendirilmiş liste) bana ver ve onay bekle. Onaysız F2'ye
başlama.
