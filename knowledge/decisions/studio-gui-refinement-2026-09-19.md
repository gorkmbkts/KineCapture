---
type: design
status: decision
updated: 2026-09-19
approved: 2026-09-19
implementation_status: not_started_by_this_prompt
tags:
  - studio
  - gui
  - annotation
  - design
---

# Studio GUI ayrıntıları — onaylı tasarım

> 20 Eylül güncellemesi: Sağ panelde kaydırma ve hareket/hata editörünün
> konumu için [yeni karar](studio-gui-repair-2026-09-20.md) önceliklidir.
> Diğer tasarım gereksinimleri korunur; uygulamanın görsel kabulü yeniden açık.

## Kapsam ve kanıt düzeyi

- `decision`: Kullanıcı 19 Eylül 2026'da ilk tasarım değerlendirmesinin ardından
  “tamam hemfikiriz” diyerek aşağıdaki yaklaşımı onayladı ve Claude'un faz
  planı çıkarıp uygulaması için ayrıntılı promptun kaydedilmesini istedi.
  [Claude görev promptu](../../promts/CLAUDE_STUDIO_GUI_FINAL_REFINEMENT_PROMPT_2026-09-19.md)
  hazırlandı. Bu not karar bağlamıdır; uygulama veya test sonucu değildir.
- `superseded`: Önceki “öneriler onay bekliyor / prompt henüz yazılmadı”
  durumu aynı gün gelen kullanıcı onayıyla sona erdi.
- `decision`: Tek kapsamlı prompt, Claude'dan önce kodu incelemesini, kendi
  bağımlılık temelli faz planını çıkarmasını ve kontrollü uygulamasını isteyecek.
  Faz sırası bu görüşmede belirlenmeyecek.
- `decision`: Kullanıcının sonraki açıklamasıyla yürütme tercihi kesinleşti:
  Claude planı Obsidian'a kaydettikten sonra tüm fazları kullanıcı onayı veya
  “devam et” mesajı beklemeden uygulayacak. Rutin plan sunumu/faz sonu sohbet
  açıklaması yapılmayacak; sonuçlar ve devam noktaları her faz sonunda
  Obsidian'a kaydedilecek. Bütün fazların uygulama/doğrulaması sonunda tek
  nihai rapor verilecek. Kullanıcı eylemi gerektiren gerçek engeller ayrıca
  kısa biçimde bildirilebilir; bağımsız işler sürdürülür.
- `superseded`: Promptun ilk sürümündeki planı kullanıcıya açıklama ve her
  faz sonunda kullanıcıya ilerleme özeti verme talimatları kaldırıldı.
- `decision`: Simetri, hizalama ve küçük görsel ayrıntılar kapsamın parçasıdır;
  uygulama yöntemi değişebilir, kullanıcı talepleri sessizce atlanamaz.
- `decision`: Görsel iyileştirmeler kayıt, işleme ve etiketleme performansını
  kabul edilemez ölçüde bozmamalı. Kabul edilebilir ek maliyet ölçümle sınanacak.
- `observed`: Aşağıdaki sorunlar kullanıcı anlatımı ve verilen ekran
  görüntülerine dayanır; bu oturumda uygulama çalıştırılarak yeniden üretilmedi.
- `decision`: Aşağıdaki tasarım yaklaşımı kullanıcı tarafından onaylandı.
  Yaklaşık oranlar/font-renk başlangıçları uygulamada okunabilirliğe göre
  ayarlanabilir; koşullu seçenekler kendi koşullarıyla geçerlidir. Teknik
  kök nedenler ve performans fizibilitesi onayla doğrulanmış hale gelmez.
- [Fikir haritası ve gerekçeler](studio-gui-design-map-2026-09-19.md), bu
  kararların ilişkisini ve Claude'un incelemesi gereken bağımlılıkları gösterir;
  faz sırası içermez.

## Kullanıcının kesin talepleri

### Giriş

- Ayrı “Yıldız Teknik Üniversitesi” yazısı kaldırılacak, logo biraz büyütülecek.
- KineCapture Studio daha büyük, marka hissi veren bir yazı karakteriyle sunulacak.
- Kullanıcı adı ve parola yazıları alanların yanından kaldırılıp boş alanların
  içine yer tutucu olarak taşınacak; yazıldığında kaybolacak. Form simetrik olacak.
- Sayfanın genel sadeliği daha güçlü bir giriş tasarımıyla iyileştirilecek.

### Yakalama

- Bağlan, Yakalama başlığıyla aynı hizada sağ üstte; kayıt hedefi panelinin
  üzerinde olacak.
- Alt kontrol ve telemetri iki satırdan tek satıra inecek. Sıra:
  kayıt → süre → FPS → kayıt kaybı → önizleme kaybı → diskte kalan → işaret koy.
- Kazanılan dikey alan kamera görünümü ve sağ panel için kullanılacak.
- Kayıt eylemi mavi yerine kırmızı olacak.

### Verileri Hesapla

- İşlenmeyi bekleyenler ve işler üst üste geniş yatay kutular yerine yan yana
  iki dikey liste/panel olacak; çok sayıda öğeyle kullanılabilir kalacak.
- İlk istekte hafif ek içeriklere açıktı; üzerinde anlaşılan seçimler
  aşağıdaki onaylı tasarım yaklaşımında kayıtlıdır.

### İşlenen Videolar

- Liste ve seçili sürüm alanının boyutları içerikle orantılı olacak.
- Önizleme korunup geliştirilecek; katılımcı ve sürüm boyutu gibi anlamlı
  bilgiler değerlendirilecek. Yeni GUI içeriği kayıt/işleme yükünü artırmamalı.

### Etiketlemeye giriş

- Sürüm seçilmeden sayfaya geçerken pencerenin kısa süreli kaybolup geri gelmesi
  araştırılıp giderilecek; kesintisiz gezinme sağlanacak.
- Sürüm açılırken GUI donmayacak. Hazırlık boyunca yükleniyor görünümü;
  mümkünse ilerleme ve kalan süre olacak. Kullanılabilir editör hazırlık sonunda
  açılacak; RGB ve iskeletin geç gelmesiyle yarım hazır ekran gösterilmeyecek.

### Etiketleme yerleşimi

- Üstteki Etiketleme başlığı ve run kimliği/kare sayısı satırı kaldırılacak.
- RGB görünümü kaynağın gerçek en-boy oranını koruyacak; 16:9 doğrulanmış veri
  değil, kullanıcının tahmini. Gereksiz yan boşluklar kaldırılacak.
- İskelet görünümü kare olacak. RGB, iskelet ve sağ panel bitişik tek yüzey
  hissi verecek; ortak dış çerçeve kullanılabilir.
- Kazanılan yatay/dikey alan sağ paneli genişletmekte kullanılacak.
- Sayfa üç yatay banttan oluşacak: görüntüler ve sağ panel; tek kontrol satırı;
  timeline. Kontrol satırı oynatma, çizim ve diğer timeline araçlarını birleştirecek.
- Hareket çiz/hata çiz dahil uygun araçlar anlamlı ikonlarla sunulacak.
- Bir hareket/hata aralığı çizilince otomatik Gez aracına dönülecek;
  sonraki normal tıklama yanlışlıkla yeni aralık oluşturmamalı.

### İskelet, kamera ve zemin

- Kare eklem noktaları küre olarak görünecek; kenar çizgilerindeki basamaklı
  görüntü giderilecek. Sağ/sol ve kol/bacak grupları farklı renklerle ayrılacak;
  kullanıcının renk örnekleri kesin palet değildir.
- Normal sol sürükleme: ayakların ortasından geçen dikey eksen çevresinde yatay
  dönüş; Bullet Time gibi sporcu merkezde kalır, izleyici çevresinde dolaşır.
- Orta tuş/tekerlek basılı sürükleme: beden ortasındaki hedef çevresinde üstten
  veya alttan inceleme; sanal kamera hedefe bakmaya devam eder.
- Izgara ayakların altında ve başlangıçta sporcunun merkezinde olacak;
  hareket/zıplama boyunca bedeni izleyerek yükselmeyecek veya kaymayacak.
- ZED SDK zemin bulma desteği offline SVO işlemede değerlendirilecek. Etiketlemede
  ayrıntılı nokta bulutu yerine yalnız düşük maliyetli zemin düzlemi gösterilecek.
- Kare görüntü alanı için beden merkezli küresel inceleme düşüncesi değerlendirilecek.
- Ön, arka, sağ, sol, üst ve çapraz gibi mantıklı kamera presetleri olacak.
- Preset geçişi yaklaşık 1,5 saniyede yumuşak hızlanma/yavaşlama ile yapılacak.
  Büyük açı aynı sürede daha hızlı geçilecek; en kısa dönüş yönü seçilecek.

### Sağ panel

- Yatay yazılı sekmeler yerine panelin en sağında yukarıdan aşağıya kare
  ikonlar olacak. Sıra: kamera presetleri; etiketler; kişi bilgileri/seçimi.
- Kamera sekmesinde presetler ve incelemeyi kolaylaştıracak anlamlı araçlar olacak.
- Etiket ikonuna doğrudan basıldığında mevcut etiketlerin kullanışlı özeti açılacak.
- Timeline'daki hareket aralığına tek tıklama hareket düzenleyicisini, hata
  aralığına tek tıklama hata düzenleyicisini otomatik açacak.
- Etiket sekmesinin rengi bağlama göre değişecek: normal özet, hareket, hata
  birbirinden ayırt edilecek; mavi/kırmızı kullanıcı örneğidir.
- Hareket sınıfları kolay seçilen butonlar olarak gösterilecek. Altında
  “Hareket sınıfı ekle” yer tutuculu alan ve sağında Ekle olacak. Yeni sınıf
  hemen listeye eklenecek, geçerli aralığa seçilecek, panel açık kalacak.
  Export öncesi etiket değiştirme korunacak.
- Hata sınıfları da kolay seçilen butonlar ve benzer ekleme alanıyla sunulacak.
- Yeni hata sınıfı oluştururken ilgili eklemler zorunlu seçilecek. İsimlerden
  oluşan checkbox listesi yerine soldaki 3B iskelet üzerinde çift tıklamayla
  çoklu eklem seçimi; seçilen düğümde belirgin görsel değişim olacak.
- Eklem seçerken iskelet döndürülebilecek. Bu seçim modu sınıf oluşturma
  sırasında etkin olacak; sıradan etiketlemede yanlışlıkla eklem değişmeyecek.
- Eklem ilişkisi sınıfla saklanacak ve sonraki hata etiketlerinde tekrar
  sorulmadan kullanılacak.

### Veri Seti, Dışa Aktarım ve ortak dil

- Veri Seti ve Dışa Aktarım ekranlarındaki paneller içeriklerine uygun
  boyutlandırılacak.
- Uygulama genelinde düşünülmüş, tutarlı semantik renkler kullanılacak;
  timeline aralıklarının ağır/opak görünümü hafifletilecek.
- Üst bağlam çubuğundaki yeşil onay işaretleri kaldırılacak.
- Sağ alttaki bildirimlerin içerik arkasında kalıp okunamaz/kapatılamaz olması
  giderilecek; tüm sayfalarda katman ve tıklanabilirlik doğrulanacak.

## Onaylanan tasarım yaklaşımı

- Ortak ölçü ritmi, eşit kontrol yükseklikleri, dengeli boşluklar; koyu antrasit
  yüzeyler, sıcak beyaz ana metin, ikincil metinde yeterli kontrast. Renk tek
  başına durum bildirmeyecek; şekil/kısa metin de kullanılacak.
- Girişte yaklaşık %10–15 büyük logo, Space Grotesk ile daha güçlü marka yazısı,
  ortalanmış eşit genişlikte form ve ana buton, hafif statik ışık/iz deseni.
  Mevcut Lucide ailesi tutarlı biçimde genişletilebilir.
- Yakalama telemetrisi tek satır etiket/değer çiftleri; değişen sayıların
  hizayı oynatmaması. Kaydedilen kare sayısı süre üzerine ipucu/ayrıntı olabilir.
- Hesaplama ekranında yaklaşık %40 kaynak listesi / %60 iş kuyruğu; filtre,
  seçili kayıt özeti, gerçek aşama/ilerleme/kalan süre ve kuyruğa ait kısa sayımlar.
- Kütüphanede yaklaşık %55 kayıt/sürüm listesi / %45 önizleme ve düzenli metadata.
  Aynı kaydın sürümleri gruplanır. Statik, önceden üretilmiş küçük resimler ve
  önbelleğe alınmış dosya boyutları kullanılır; sürekli video oynatılmaz.
- Etiketlemede ortak üst bant yüksekliği; video genişliği gerçek oranından,
  iskelet genişliği aynı yükseklikten hesaplanır. Sağ panele okunabilir asgari
  genişlik ayrılır. Kazanılan alanın tamamı yalnız videoya verilmez. Küçük
  pencere/DPI uyarlaması, kırpma veya oran bozma ile çözülmez.
- Kamera hedefi gövde merkezinde; yatay dönüşün düşey ekseni ayakların zemin
  üzerindeki merkezinden geçer. Tekerlek yakınlaştırır, sağ sürükleme kadrajı
  kaydırır; yeniden merkezleme vardır. Yatay takip gerekirse seçenek olur,
  zemin dünya koordinatında sabit kalır. Kamera hareketi ölçüm dizilerini değiştirmez.
- Görünür bir küre kabuğu yerine bedeni saran görünmez küre kamera mesafesi ve
  kadraj için kullanılabilir. Gövde hedefi eksikse geçerli alternatif veya son
  geçerli hedef; ölçüm verisindeki NaN değerler doldurulmaz.
- Anatomik sağ kolda kehribar, sağ bacakta mercan; sol kolda turkuaz,
  sol bacakta indigo; gövde nötr. Kamera dönünce sağ/sol renkler değişmez.
  Küresel görünümün yöntemi ve kenar yumuşatma tekniği ölçümle seçilir.
- Kamera sekmesinde yön pusulası/küpü, merkezle/sığdır, zemin ve RGB iskelet
  kaplaması anahtarları, son bakışa dönme ve kişisel görünüm kaydetme düşünülebilir.
  Presetler sabit bir kayıt referansını kullanır; “ön” yönü kendiliğinden her
  karede yeniden yorumlanmaz. Elle sürükleme animasyonu anında keser; yeni preset
  geçişi o anki konumdan başlar. Hareket azaltma seçeneği desteklenir.
- Etiket özeti: hareket kartında sınıf, zaman/kare aralığı, süre, hata sayısı,
  hazır/eksik durumu; hata alt kayıtları ve ilgili aralığa atlama. Kırmızı hata,
  yeşil tamamlanmış ve hatasız, sarı eksik/inceleme gereken durumdur.
  İncelenmemiş veri sırf hata yazılmadığı için yeşil olmaz. Mevcut türetilmiş
  doğru/hatalı sözleşmesi korunur.
- Sınıf eklemede isim ve geçerli eklem seçimi tamamlanınca tek kaydetme/ekleme
  eylemi; yeni sınıf aktif aralığa atanır. Çift tıklama ile döndürme hareketi
  ayrılır, seçilen eklem vurgusu anatomik rengi kaybettirmez. Eksik eklem
  uydurulmaz; başka geçerli kare kullanılabilir.
- Proje içinde ortak sınıf kütüphanesi ve sınıfın eklem varsayılanları;
  varsayılandan aktarılan ilişki, aralığa özel insan gözlemi olarak sunulmaz.
  Sınıfın sonradan değişmesi eski etiketleri sessizce değiştirmez; gerekirse
  kontrollü toplu uygulama ve geri alma tasarlanır. İleri düzey istisna
  düzenlemesi, varsayılan hızlı akışı bozmayacak şekilde düşünülebilir.
- Tek araç satırı: oynatma/kare adımları; süre/kare; Gez/hareket/hata; yapışma
  ve zoom; undo/redo; sonraki eksik; kaydetme durumu. İsteğe bağlı seçili
  aralığı döngüde oynatma ve hız seçimi; ikincil eylemler dar alanda taşma menüsüne.
- Veri Seti: kompakt kapsam sayımları, içeriğe göre kolonlar ve seçili kayıt
  için sağ ayrıntı/düzeltmeye git alanı. Dışa Aktarım: solda doğrulama listesi,
  sağda paket seçenekleri, hedef, özet ve paket yazma; açık boş/yükleniyor/hata durumları.
- Bildirimler tek merkezi üst katmanda, sayfa değişimi/boyutlandırma/3B çizim
  sonrasında da okunur ve kapatılır; kalıcı engeller ilgili panelde de görünür.
- Ağır disk işlemleri, thumbnail/metadata/zemin üretimi offline veya arka planda;
  görünmeyen sayfalarda sürekli çizim yapılmaz. Görsel geliştirmeler önce/sonra
  ölçülür; canlı ölçüm, offline ve mock doğrulama ayrı belgelenir.

## Koddan doğrulanan sınırlar ve açık teşhisler

- `verified` (statik kod incelemesi): Sayfalar ilk ziyarette oluşturulup
  saklanıyor; ReviewPage oluşturulurken Skeleton3DView ekleniyor.
  Kaynak: `studio/views/shell.py:501`, `studio/views/pages/review.py:168`.
- `hypothesis`: Qt, görünür pencereye ilk QOpenGLWidget sonradan eklendiğinde
  native pencerenin yeniden oluşturulabileceğini belgeliyor. Bu ilk girişteki
  kaybolmayı açıklayabilir; kullanıcının “her seferinde” bildirimi ayrıca
  tekrarlanıp incelenmeli. Henüz kök neden doğrulanmadı.
- `verified` (statik): ReviewViewModel.open_version arka plan işi kullanıyor;
  başarı callback'i `_attach` ve `opened` öncesinde busy durumunu kapatıyor.
  ReviewPage._after_open video erişimi ve ilk 3B kadraj hazırlığını yapıyor.
  `open_version:191`, `_after_open:659`, `_loading_changed:701`.
  `open`: Gerçek donmanın hangi alt adımdan kaynaklandığı profillenmedi.
- `verified` (statik): Mevcut zemin grid'i varsayılan height=0 düzlemidir;
  burada SDK ile algılanmış zemine bağlanma yok. GL_POINTS ve tek renkli
  shader mevcut kare noktalarla tutarlıdır. İstenen 4x örnekleme ayarı zaten
  vardır; gerçek etkinliği ve çizgi yumuşatma ayrıca değerlendirilmelidir.
- `verified` (resmî belge): ZED düzlem tespiti kamera konum takibi ve OK
  durumunu gerektiriyor; floor plane ve dönüşüm desteği mevcut.
  `open`: Kurulu SDK/Python API, mevcut SVO verisi, referans uzayı ve hareketli
  kamera durumları bu projede denenmedi. SVO'da çalıştığı varsayılıp tamamlandı denemez.
- `hypothesis`: Plane normal/offset ve gerekli referans dönüşümü sürümlü türetilmiş
  çıktıda saklanabilir. İskelet ve plane aynı uzaya dönüştürülmeli, ham eklemler
  yerinde değiştirilmemeli. Kamera hareketliyse kareye uygun poz bilgisi gerekir.
  Tespit yoksa “zemin bulunamadı”; eski kayıtlar gerekirse açıkça işaretlenmiş
  görsel referansla açılır. Ayakların anlık minimum yüksekliği ölçülmüş zemin sayılmaz.
- `verified` (statik): ToastLayer sayfa stack'inin çocuğudur, yeni bildirimde
  raise_ çağrısı vardır. `open`: Sayfa geçişlerinde katman sırası ve olası
  kırpma sorunlarının gerçek kök nedeni bu oturumda test edilmedi.
- GUI kodu, veri şeması ve paketler değiştirilmedi; GUI/performance/canlı
  kamera testi çalıştırılmadı. Bu not uygulama veya performans kanıtı değildir.

## Kaynaklar

- Kullanıcının 19 Eylül 2026 tasarım görüşmesi; Codex oturumu
  `01a0b73e-0a13-7be0-a8ad-eb03e808cc4d`.
- Aynı oturumdaki sonraki kullanıcı mesajı: tasarım onayı ve ayrıntılı Claude
  promptunu, Obsidian fikir haritasıyla birlikte kaydetme talebi.
- Kullanıcının bu oturuma eklediği 11 ekran görüntüsü; özgün dosyalar
  `%LOCALAPPDATA%/Temp/codex-clipboard-*.png` konumlarında. Görseller veya
  katılımcı/kayıt verileri wiki'ye kopyalanmadı.
- [Konuşma kaynak sicili](../sources/conversation-registry.md).
- [Etiket ve feature sözleşmesi](../concepts/annotation-and-features.md).
- [Qt QOpenGLWidget davranışı](https://doc.qt.io/qt-6/qopenglwidget.html).
- [ZED plane detection](https://docs.stereolabs.com/docs/development/zed-sdk/modules/spatial-mapping/plane-detection).
- [Space Grotesk kaynak ve lisansı](https://github.com/floriankarsten/space-grotesk).
