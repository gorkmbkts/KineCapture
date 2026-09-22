---
type: task-prompt
status: ready
updated: 2026-09-21
tags:
  - studio
  - gui
  - user-revision
---

# Claude Code görevi — 21 Eylül kullanıcı geri bildirimleriyle GUI düzenlemesi

## Görev ve öncelik

KineCapture Studio'nun son Claude/Codex güncellemelerinden sonra kullanıcı arayüzü hâlâ kabul edilmedi. Bu görev, aşağıdaki son kullanıcı geri bildirimlerini uygulamak içindir. Önceki tamamlanmamış görevleri, devir planlarını ve test koşularını kendiliğinden sürdürme. Eski açıkları silme veya tamamlandı sayma; bu görev dışında bırak. Yalnız buradaki davranışların gerektirdiği bağımlılıklara dokun.

Önce `MEMORY_INDEX.md`, ardından bu görevle ilgili [21 Eylül karar notunu](../knowledge/decisions/studio-gui-user-revision-2026-09-21.md) oku. Eski promptları topluca okuma. Aynı konuda eski kararlarla çelişki varsa bu belgedeki yeni kullanıcı kararları geçerlidir. Teknik yöntemi sen seç; aşağıdaki görünüm, davranış ve koruma koşullarını değiştirme.

Bu belge uygulanmak üzere kullanıcı tarafından görevlendirildiğinde kod görevidir. Belgenin hazırlanmış veya wiki'ye eklenmiş olması uygulamanın tamamlandığı anlamına gelmez. Kaynak ekran görüntüleri kullanıcı gözlemidir; bu turda uygulama davranışının yeniden test edildiği iddia edilmemiştir.

## 1. Tek hedef pencere ve içerik koruma sözleşmesi

- Uygulama **maksimize pencere / maximized windowed** olarak çalışacak. Buradaki “tam ekran”, kenarlıksız özel fullscreen modu anlamına gelmiyor. Windows başlık çubuğundaki pencere küçültme/büyütme kontrollerini kaldır; kapatma işlevi kalsın. Uygulama normal küçük pencere boyutuna dönmesin.
- Hedef kullanıcının mevcut ekranı ve mevcut Windows ölçek ayarıdır. Başlangıçta gerçek kullanılabilir pencere alanını kaydet; kırpılmış kaynak görsellerden çalışma çözünürlüğü veya DPI tahmin etme. Sabit boyutlar kullanabilirsin; çok boyutlu responsive tasarım hedefi yok.
- Farklı DPI, ölçek, ekran çözünürlüğü ve pencere boyutu matrisleri çalıştırma. Buna harcanacak emeği gerçek hedef görünümün ekran görüntülerini inceleyip düzeltmeye ayır.
- **Kullanıcının kaldır dediği içerikler kaldırılacak; söylemediği içerikler ve işlevler korunacak.** Sığdırmak için panel, container, düğme veya seçenek silme; boş görünse bile işlev taşıyan alanı keyfî kaldırma. Mevcut işlevleri önce kısa bir envantere al, teslimde kaybolmadıklarını kontrol et.
- Genel cila: tutarlı iç boşluklar, hizalar, düğme yükseklikleri, okunabilir alanlar ve dengeli boşluk kullanımı. İçeriği kenara yapıştırmak, yazıyı aşırı küçültmek, metni üst üste bindirmek ve büyük anlamsız boşluklar bırakmak çözüm değildir.
- Kaydırma istisnası yalnız aşağıda tarif edilen **Etiket özeti** sekmesidir. Başka panelde yeni kaydırma ile yerleşim kusuru gizleme. Mevcut zaman çizelgesinin gezinme/zoom işlevlerini bu kuralla karıştırıp kaldırma.

## 2. Projeler

- Sağ üstteki **Yenile** düğmesini yalnız metin gibi görünen durumdan çıkar; Katılımcı ekle, Projeyi sil ve Yeni proje ile aynı görsel düğme ailesine kat. Tehlikeli eylem ve birincil eylem renklerini aynileştirmek gerekmiyor; yükseklik, yüzey, kenarlık ve boşluk dili tutarlı olsun.
- Proje/katılımcı arama alanını genişlet. Alanın ne aradığı ilk bakışta anlaşılmalı, açıklayıcı yer tutucu metin okunmalı ve yazılan sorgu gereksiz yere dar alana sıkışmamalı.

## 3. Yakalama

### Sabit önizleme alanı

Kamera bağlı değilken görünen siyah önizleme alanı ile bağlantıdan sonra RGB görüntüsünü taşıyan alanın **konumu ve dış boyutları aynı** olacak. Bağlan, bağlantıyı kes ve yeniden bağlan durumları komşu paneli veya alt satırı zıplatmayacak. Siyah alan küçük başlayıp ilk kareyle genişlemeyecek. Görüntünün en/boy oranını bozma; dış alanın sabitliği ile görüntünün bu alana yerleştirilmesini birlikte çöz.

### Bildirimler ve Araçlar

- Sağ container'daki değişken kamera/kadraj/sistem durumu içeriklerini kaldır: Durum bölümü, “kadraj tamam”, “kamera bağlı değil”, “etkin”, kare bildirimi/kayıp uyarıları ve aynı amaca hizmet eden açıklama/bantlar burada görünmeyecek.
- RGB önizlemenin üzerindeki büyük “kadraj tamam”, “ayaklar kadraj dışında”, “kadrajda 2 kişi” gibi başlıkları, uyarı kutularını ve geçmiş süre özetlerini tamamen kaldır.
- Kişi seçimi sonrası kişinin etrafındaki **seçim çerçevesi kalsın**, içindeki “seçilen kişi” metni kalksın. Kişiye tıklayarak seçim, çerçeve ve istenen diğer önizleme işlevleri korunacak.
- Kullanıcının bu sekmede istediği tek bildirim: görüntüde kişiyi seçmeden **Kayda başla** denendiğinde çıkan uyarı popup'ı. Bu durumda kayıt başlamayacak; uyarıdan sonra kişi seçip yeniden denemek mümkün olacak.
- Kaldırılan kamera/sistem durum bilgileri sağ alttaki **Araçlar** düğmesiyle açılan menü/panelden erişilebilir olacak. Bilgiyi yalnız görünümden taşı; hata tespitini, kayıt korumalarını veya tanı bilgisini iptal etme. Yeni toast, badge veya önizleme yazısı ile eski bildirimleri başka ad altında geri getirme.
- Sağ container'ın tamamını kaldırma. Kayıt hedefi, kişi seçimi kontrolleri, kayıt modu, geri sayım, süre sonunda dur, aynalama ve kadraj kılavuzu gibi bu görevde kaldırılması istenmeyen kontroller kalacak. Kontrol ile değişken durum mesajı arasındaki farkı gözet.

### Alt kontrol satırı

Bağlan / Bağlantıyı kes düğmesini üstten alıp kayıt düğmesinin yanına taşı. Soldan sağa sıra:

**Kayda başla → Bağlan / Bağlantıyı kes → Süre → FPS → mevcut diğer metrik ve eylemler.**

Kamera bağlandığında bağlantı düğmesi yeşil olacak ve bağlantıyı kes eylemini açıkça ifade edecek; bağlantı kesildiğinde normal görünüme dönecek. Bağlantıyı ayrıca “etkin” mesajıyla anlatma. Mevcut süre, FPS, kayıt kaybı, önizleme kaybı, diskte kalan ve işaret koy kontrollerini koru. Bildirim temizliği bu sabit metrikleri silme gerekçesi değil.

## 4. Verileri Hesapla

- İşlenmeyi bekleyen kayıtlar ve İş kuyruğu ana container'larının üst ve alt sınırları aynı hizada, dikey uzunlukları eşit olacak. Genişliklerinin farklı olması kabul edilir. Alt eylemler ve açıklamalar bu hizalamayı bozmadan okunacak.
- Kullanıcı, iş kuyruğunun altındaki **Duraklat, Devam et, İptal, Yeniden dene** kontrollerinin çalışmadığını bildiriyor. Kaynak görselde kuyruk boş; yalnız görsele bakarak backend arızası sonucu çıkarma. İlgili iş durumlarını oluşturarak gerçek etkileşimi incele.
- Uygun iş ve durum seçiliyken eylem gerçekten iş kuyruğuna etki etsin; sadece renk/metin değiştirmesin. Uygun iş yoksa devre dışı görünümü ve nedeni anlaşılır olsun.
- Öncelik bu eylemleri çalışır hâle getirmektir. Gerçekten desteklenemeyen bir eylem varsa kullanıcı o düğmenin kaldırılmasına izin veriyor; ancak nedenini ve hangi düğmenin kaldırıldığını raporla. Bu istisna container'ı veya diğer çalışan eylemleri kaldırma izni değildir.
- Duraklatma/sürdürme işin ilerlemesine, iptal türetilen işin güvenli kapanmasına, yeniden deneme başarısız işin yeniden çalışmasına yansısın. İptal ham kaydı silmesin; kullanıcı kayıtları test verisi olarak değiştirilmesin.

## 5. İşlenen Videolar ve diğer ekranlar

İşlenen Videolar için bu aşamada işlev değişikliği istenmiyor; yalnız genel yerleşim, boşluk, boyut ve hizalama cilası yap. Veri Seti, Dışa Aktarım ve Ayarlar için yeni işlev veya yeniden tasarım kapsamı üretme. Genel görsel düzeltmeler bu ekranlardaki mevcut içerikleri korumalı.

## 6. Etiketleme — iskeletin sağındaki sekmeli panel

Panel korunacak. Üç sekmenin içerikleri ayrı kalacak; sığdırmak için birini ortadan kaldırma.

### Sekme ikonları

Sağdaki dikey navigasyon şeridi ikonlar için gereğinden geniş. Şeridi yatayda daralt; ikonlar merkezde, seçili durum belirgin ve tıklama alanları rahat olsun. İkonlar arasında kullanılmayan geniş koridor bırakma; şeridi inceltirken tıklanabilirliği bozma.

### A. Bakış / kamera presetleri

- Pusula benzeri yön göstergesini kaldır. Kamera açıları/presetler ve diğer işlevler kalsın.
- Preset düğmelerini panel kenarlarına yapışan büyük bloklar olarak sunma. Dış kenarlarda görünür iç boşluk, düğmeler arasında tutarlı aralık ve kendi içinde dengeli boyutlar olsun.
- Bakış presetleri bir grup, Merkezle / Sığdır / Önceki gibi görünüm eylemleri ikinci grup olarak rahat ayırt edilsin. Gruplar arasında bağıran kutular yerine ölçülü boşluk ve başlık hiyerarşisi kullanabilirsin.
- Zemin, RGB iskelet kaplaması ve Gelişmiş gibi mevcut seçenekleri koru. “Ön” yönünün referansını açıklayan yararlı içerik pusulayla birlikte yanlışlıkla silinmesin.
- Varsayılan sekme olan bu alan açıldığında dengeli ve tamamlanmış görünmeli. Kaydırma olmayacak.

### B. Etiket özeti — tek kaydırma istisnası

- Etiket sayısı artınca satırları daraltıp birbirine bastırma. Okunabilir satır yüksekliği ve düzenli boşluklar sabit kalsın; sınıf, durum, aralık/süre bilgisi birbirini ezmesin.
- **Yalnız bu sekmenin liste içeriği dikey kaydırılabilir.** Fare tekerleği ve uygun normal gezinme etkileşimi çalışacak; görünür scrollbar veya slider olmayacak.
- Listenin en altındaki etikete erişilebilsin, seçilen etiket ile zaman çizelgesi arasındaki mevcut bağ korunsun. Kaydırma, preset ve sporcu sekmelerine bulaşmasın; bütün sağ paneli kaydırma.

### C. Sporcu / kişi sekmesi

Durum bilgisi, seçili sporcu, kişi seçimi ve belirsiz aralık eylemleri korunacak. Düğmeler panelin kenarına bitişik dev yüzeyler olmayacak; tutarlı iç boşluklarla, işlev hiyerarşisi anlaşılır şekilde yerleşecek. Pasif eylemler anlaşılır görünecek. Bu sekmede kaydırma olmayacak. Bu görev yeni kişi takip algoritması tasarlama görevi değil.

## 7. Etiketleme — hareket/hata düzenleme bandı

### İlk açılış ve kipler

Sayfa ilk açıldığında editör boş/gizli kalmayacak: **varsayılan olarak hareket etiketleme içeriği görünecek**. Hareket seçilmemişse seçime bağlı eylemler anlamlı şekilde pasif olabilir; kullanıcıya hareket sınıfları ve çalışma alanı görünmeli. Hata aralığına tıklanınca hata düzenlemeye geçecek; hareket seçimi veya Harekete dön ile hareket düzenlemeye dönecek. Kipler arasında bandın yüksekliği ve zaman çizelgesinin konumu gereksiz değişmesin.

### İstenen tasarım sonucu

Bu alan kısa ve geniş bir editör bandı. Onu dört sert dikey bölüme ayırıp dar mini kartlara dönüştürme. Öncelik sınıf seçimi; aralık ve eylem kontrolleri bunu destekleyen, aynı yatay akışa oturan öğeler olsun.

**Codex tasarım önerisi:** Solda kompakt “yeni sınıf + Ekle” alanı, devamında sık kullanılan sınıfların hızlı seçim düğmeleri, daha sağda okunur başlangıç/bitiş ve bağlama ait eylemler. Gerekirse iki düzenli yatay hat kullan; üst üste yığılmış kutucuklar ve büyük boş sütunlar oluşturma. Bu bir widget/algoritma tarifi değil, görsel öncelik ve kullanım önerisidir. İçerik kaybetmeden daha iyi bir çözüm bulabilirsin; zorunlu konum, taşma ve kullanım koşulları aşağıdadır.

### Her iki kipte sınıflar

- Yeni sınıf ekleme alanı bandın **en solunda** yer alacak; özellikle yeni hata sınıfı metin kutusu ortada kalmayacak. Hareket ve hata kipleri aynı kullanım mantığını paylaşsın.
- Mevcut sınıflar tek hareketle seçilebilen düğme/chip benzeri kontrollerle sunulsun. Seçili sınıf açıkça ayırt edilsin.
- Sınıf listesi bandın boyunu uzatmayacak, kontrol alanlarının üzerine taşmayacak, yatay scrollbar doğurmayacak. Görünür hızlı seçim kapasitesini hedef ekrana ve uzun sınıf adlarına göre belirle; keyfî olarak daha çok düğme sığdırmak için metni ezme.
- Kapasite aşıldığında görünür sınıfların sonunda tam **Diğer sınıflar** adlı düğme bulunsun. Açılan seçicide geri kalan bütün sınıflara erişilsin. Arama/sayfalama gibi çözümler seçebilirsin; panel kaydırma yasağına yeni istisna ekleme.
- Sıralama **en son kullanılan sınıf ilk sırada** olacak. İkinci sıradaki sınıf kullanıldığında birinci sıraya gelsin. Diğer sınıflar seçicisinden seçilen sınıf, seçici kapandığında ilk hızlı seçim düğmesi olarak görünsün; eski sıralamanın kalan kısmı tutarlı biçimde ilerlesin.
- Hareket sınıfları ile hata sınıfları birbirine karışmasın. Yalnız hover/focus almak veya seçiciyi açıp vazgeçmek “kullanıldı” sayılmasın. Liste yeniden sıralanırken tıklanan sınıf başka bir sınıfa dönüşmesin.
- Uzun adlar kontrollü kısaltılabilir; tam ad erişilebilir olsun. Başlangıç/bitiş gibi sayısal değerler ise kısaltılmayacak.

### Hareket kipi

Mevcut hareket sınıfı seçme/ekleme, hareket aralığı, hazır/durum bilgisi, veri setinin dışında tut, hata aralığı ekle, sınıfsızlara uygula ve silme işlevlerini koru. Bunları eşit genişlikte dört sütuna dağıtma. Sınıf seçimi, aralık düzenleme ve ikincil eylemlerin önemi görsel olarak anlaşılır olsun. Zaman çizelgesi ve oynatma araç çubuğundaki mevcut işlevleri kaybetme.

### Hata kipi

Yeni hata sınıfı alanı en solda, hızlı sınıf seçimleri hemen ilişkili konumda olsun. Başlangıç/bitiş, bağlı hareket bilgisi, ilgili eklem özeti, **tek bir Eklemleri düzenle** düğmesi, Harekete dön, Not ve silme korunacak. Tek düğme için geniş ve büyük ölçüde boş bir “İlgili eklemler” sütunu ayırma; eylemi bandın akışında mantıklı bir yere yerleştir. Eklem seçimi ve not işlevlerini tasarım bahanesiyle kaldırma.

### Sayısal alanlar ve taşma

Başlangıç ve bitiş değerleri, sayı değiştirme okları yüzünden kırpılmayacak. Ekran görüntülerindeki 428/454/695 gibi kısa değerlerde dahi görülen sıkışma giderilmeli. Kayıtların desteklenen kare aralığındaki uzun değerleri de bütünüyle okunmalı; sayı ile oklar üst üste gelmemeli. Değer değişikliği mevcut aralık kurallarını, kaydetmeyi ve geri almayı bozmasın.

## 8. Doğrulama ve kabul

Uygulamayı gerçek Windows masaüstü ortamında hedef **maksimize pencere ve mevcut ölçek** ile aç. Ekran görüntüsü al, gerçekten incele, kusur varsa düzelt ve ilgili durumu yeniden kontrol et. Sadece widget ölçüsü, test sayısı veya offscreen görüntüyle görsel kabul ilan etme. Testten vazgeçilmiyor; farklı DPI matrisi yerine istenen davranışlar ve gerçek görünüm doğrulanıyor.

| Kontrol | Kabul ölçütü |
|---|---|
| Pencere | Maksimize açılış; küçültme/büyütme kontrolleri yok; kapatma korunmuş |
| Projeler | Yenile tutarlı düğme; arama alanının amacı okunuyor |
| Yakalama geometrisi | Bağlantı öncesi/sonrası/kesilince önizleme dış sınırı ve komşu alanlar aynı |
| Yakalama içerikleri | Eski durum bantları ve RGB bildirimleri yok; Araçlar'dan tanı bilgisine erişiliyor |
| Kişi seçimi | Seçim çerçevesi yazısız; seçim yokken kayıt uyarısı ve kayıt engeli çalışıyor |
| Kayıt satırı | Kayda başla → bağlantı → süre → FPS → kalanlar; bağlı düğme yeşil |
| İşleme yerleşimi | İki ana container'ın üst ve alt sınırları eşit |
| İş kuyruğu | Boş/çalışan/duraklamış/başarısız durumlarda ilgili eylem gerçekten doğrulanmış |
| Sağ panel | İnce ikon şeridi; iç boşlukları dengeli preset/sporcu içerikleri; pusula yok |
| Etiket özeti | Çok sayıda etikette okunur satırlar; son etikete çubuksuz kaydırmayla erişim |
| Editör ilk açılış | Hareket içeriği görünür; hata seçimi ve geri dönüş çalışıyor |
| Sınıf kapasitesi | Sıfır, az, sınırdaki ve çok sınıf; uzun adlarda taşma yok; Diğer sınıflar erişilebilir |
| Son kullanılan | İkinci sıradan ve Diğer sınıflar içinden seçim sonrası ilk sıra doğru |
| Sayılar | Hareket/hata başlangıç ve bitiş değerleri tümüyle okunur ve düzenlenebilir |
| Koruma | Söylenmeyen içerikler, kaydetme, geri alma, seçim ve veri bütünlüğü korunmuş |

Boş kuyrukta birkaç düğmeye basmak iş kuyruğu doğrulaması değildir. Kontrol edilebilir test işleriyle durum geçişlerini doğrula. Sentetik/mock kontrolü ile gerçek kamera testi ayrı raporlanmalı. Donanım veya başka somut engel varsa ilgili kabul maddesini açık bırak; test edilmediğini söyle. Kullanıcının gerçek kaydını değiştirme veya üstüne yazma.

Yalnız mevcut `KineSynth` ortamını kullan: `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`. Yeni environment oluşturma, bilimsel paketleri gereksiz değiştirme. Mock backend, atomik yazım/kapanış, NaN ve değişmez ham veri sözleşmeleri korunacak. Mevcut çalışma ağacındaki başka değişiklikleri geri alma.

## 9. Teslim ve wiki

- İstenen maddelere karşılık ne değiştiğini, hangi içeriklerin kaldırılıp hangilerinin taşındığını kısa ve açık raporla.
- Son hedef görünümü gösteren ekran görüntülerini ilgili kabul maddelerine bağla. Kişisel görüntüler/ham kayıtları wiki'ye kopyalamadan yerel kanıt konumlarını kullan.
- Gerçekten çalıştırılan testleri, GUI etkileşim kontrollerini ve çalıştırılamayanları ayır. Kullanıcı kabulünü test geçişiyle eşitleme.
- Wiki'de bu görevin kararlarını ve gerçek doğrulama sonuçlarını güncelle. Eski açıkları kendiliğinden tekrar görev yapma veya tamamlandı sayma.
- Teslimde önceki onarımın devamını anlatmak yerine bu belgenin kabul tablosunu esas al. Açık kalan madde varsa görünür bırak.

## Kaynak görseller

13 kullanıcı ekran görüntüsü ve ek metnin özgün konumları, kimlikleri ve SHA-256 değerleri [kaynak notunda](../knowledge/sources/gui-user-feedback-2026-09-21.md). Görseller arızaların referansıdır; kopyalanacak hedef tasarım değildir. İşlevsel şikâyetleri ayrıca yeniden üret.

| Görsel zamanı | İlgili alan |
|---|---|
| 18:34:00 | Projeler / Yenile düğmesi |
| 18:37:05 | Kamera öncesi önizleme ve sağ container |
| 18:41:25 | Kamera sonrası önizleme, durum bantları ve alt satır |
| 18:41:29 | RGB üzerindeki kişi/kadraj bildirimi |
| 18:57:37 | İşleme container hizaları ve kuyruk eylemleri |
| 19:01:28 | Etiketleme genel görünümü |
| 19:04:18 | Preset paneli ve pusula |
| 19:13:22 | Etiket özeti listesi |
| 19:15:27 | Sporcu sekmesi |
| 19:16:27 | Hareket editörü |
| 19:20:15 | Hata editörü |
| 19:23:28 | Hata editörü ve araç çubuğu |
| 19:25:03 | Başlangıç/bitiş sayı alanları |
