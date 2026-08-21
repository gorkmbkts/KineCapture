# KineCapture Studio — Etiketleme ve İnceleme Akışını Yeniden Tasarlama Görevi

Bu görev KineCapture Studio'nun veri etiketleme yaklaşımını, zaman çizelgesini,
dataset export sözleşmesini ve İnceleme ve Etiketleme ekranını birlikte yeniden
tasarlamayı amaçlıyor. İstenen sonuç yalnızca görsel bir arayüz değişikliği
değil; gelecekte eğitilecek modeller için açık, tutarlı ve makine tarafından
doğrudan kullanılabilir bir etiket veri modeli oluşturulmasıdır.

Göreve başlamadan önce `CLAUDE.md` ve `MEMORY.md` dosyalarının tamamını oku,
mevcut kodu ve testleri incele. Buradaki isteklerle eski belgeler çelişirse bu
dosyadaki ürün gereksinimlerini esas al; kod/veri uyumluluğu açısından aldığın
kararları görev sonunda açıkla. Mevcut çalışma ağacında kullanıcıya ait
değişiklikler olabilir; ilgisiz değişiklikleri geri alma veya üzerlerine yazma.

## Ürün hedefi

Bir ZED kaydı birden fazla hareket tekrarı içerebilir. Kullanıcı önce kayıttaki
her hareket tekrarının başlangıç ve bitişini belirleyecek. Her hareket tekrarı
ayrı bir sample olacak ve kendi hareket türü ile doğru/yanlış etiketi bulunacak.

Yanlış yapılan bir hareketin içinde hata bütün hareket boyunca bulunmak zorunda
değildir. Kullanıcı seçili hareket sample'ının içinde ikinci bir zaman aralığı
seçerek o aralıkta hangi hata türünün görüldüğünü etiketleyecek. Böylece ileride
geliştirilecek model hem hata sınıfını hem de hatanın hareketin hangi bölümünde
başlayıp bittiğini öğrenebilecek ve tahmin sırasında zamansal yerelleştirme
yapabilecek.

İstenen temel etiketler şunlardır:

1. Hareket türü.
2. Hareket doğru mu, yanlış mı?
3. Yanlış veya hatalı bölüm varsa, seçili hareketin hangi başlangıç-bitiş
   aralığında hangi hata türü bulunuyor?

Hareket fazı kavramı artık kullanılmayacak. Hazırlık, iniş, dip, kalkış,
konsantrik, eksantrik, toparlanma vb. faz etiketlerini arayüzden, yeni veri
modelinden ve yeni export sözleşmesinden çıkar. Eski veriyi okurken uygulamanın
çökmemesi ve kullanıcı verisinin kaybolmaması için gereken geriye dönük
uyumluluğu koru; ancak yeni kullanıcı deneyiminde faz etiketleme bulunmasın.

## İstenen etiket hiyerarşisi

Etiketlerin iki seviyeli olduğu kullanıcıya ve veri tüketicisine açıkça belli
olmalı:

- **Hareket sample'ı:** Kayıt içindeki ana başlangıç-bitiş aralığıdır. Hareket
  türü ve doğru/yanlış kararı bu seviyeye aittir. Bir kayıt birden fazla hareket
  sample'ı içerebilir.
- **Hata aralığı:** Yalnızca seçili hareket sample'ının içinde bulunan alt
  başlangıç-bitiş aralığıdır. En az bir hata sınıfına bağlıdır ve gelecekteki
  modelin zamansal hata hedefini oluşturur.

Bir hareket sample'ında sıfır, bir veya birden fazla hata aralığı bulunabilsin.
Aynı hata sınıfı hareketin farklı zamanlarında tekrar edebilsin. Farklı hata
sınıfları aynı anda görülebileceği için gerektiğinde hata aralıklarının
çakışabilmesine izin ver; çakışmaları arayüzde anlaşılır biçimde göster. Hata
aralıkları kendi ana hareket sample'larının dışına taşamasın. Ana sample sınırı
sonradan daraltıldığında alt aralıkların ne olacağı sessiz ve veri kaybettiren
bir davranış olmasın; kullanıcıya anlaşılır bir düzeltme/uyarı akışı sun.

Tamamlanmış bir etiket için doğru/yanlış kararı ikili ve açık olmalıdır.
Henüz etiketlenmemiş/taslak olma hali sistemsel bir çalışma durumu olarak
korunabilir, fakat kullanıcıya üçüncü bir hareket sınıfı gibi sunulmamalıdır.
Mevcut `uncertain`, annotation status ve segment status kavramlarını incele;
ürün hedefini gereksiz durum seçenekleriyle karmaşıklaştırmadan, eski veriyi de
bozmayan tutarlı bir sonuç üret. Export'a hangi kayıtların gireceği ile ekranda
"etiketlendi" sayılan kayıtların tanımı aynı olmalı.

Tutarlılık açısından şu durumları ele al:

- Doğru işaretlenen bir hareket sample'ında hata aralığı bulunması çelişkidir.
- Yanlış olarak tamamlanan bir hareket sample'ında normalde en az bir hata
  aralığı ve hata sınıfı beklenir.
- Henüz lokalize edilmemiş bir yanlış hareket üzerinde çalışmaya izin verilebilir,
  fakat bunun tamamlanmış/exporta hazır etiket olmadığı açıkça gösterilmelidir.
- Geçersiz, ana sample dışında kalan, boş veya ters aralıklar kaydedilmemeli ya
  da export edilmemelidir.

Bu kuralların kullanıcıyı veri kaybına sürüklemeyen, anlaşılır doğrulamalarla
uygulanmasını istiyorum. Tam teknik durum modelini sen belirleyebilirsin.

## Zaman çizelgesi deneyimi

Aynı zaman çizelgesi iki farklı amaçla kullanılacak:

1. Kayıt içindeki hareket sample'larını oluşturmak ve sınırlarını düzenlemek.
2. Seçili hareket sample'ının içindeki hata aralıklarını oluşturmak ve
   sınırlarını düzenlemek.

Bu iki işlem birbirine karışmamalı. Kullanıcı hangi düzenleme modunda olduğunu,
hangi hareket sample'ının seçili olduğunu ve çizdiği aralığın hareket mi yoksa
hata mı olduğunu her an görebilmeli. Bunun için uygun mod, katman, lane, renk,
seçim veya odak yaklaşımını sen tasarla.

Beklenen kullanıcı akışı kabaca şöyledir:

- Kullanıcı kaydı oynatır veya zaman çizelgesinde gezinir.
- Bir ana hareket aralığı çizer ve bu aralık ayrı bir sample olur.
- Sample'ı seçer; gerekirse yalnız o aralığı döngüde oynatır ve sınırlarını
  hassas biçimde düzeltir.
- Hareket türünü ve doğru/yanlış kararını verir.
- Hareket yanlışsa "hata aralığı ekle" akışına geçer, sample içindeki başlangıç
  ve bitişi zaman çizelgesinden seçer, ardından hata sınıfını atar.
- Eklenmiş hata aralıklarını renkleri ve sınıf adlarıyla zaman çizelgesinde
  görür; seçebilir, oynatabilir, taşıyabilir, yeniden boyutlandırabilir veya
  silebilir.
- Aynı sample'a başka hata aralıkları ekleyebilir ve ardından sonraki harekete
  geçebilir.

Kare sınırlarının kapsayıcı mı dışlayıcı mı olduğu bütün katmanlarda tek ve
belgelenmiş bir sözleşmeye sahip olsun. Arayüz, sidecar JSON ve export aynı
anlamı kullansın. Kayıttaki mutlak pozisyon ile sample içindeki göreli konum
karıştırılmasın.

Mevcut marker'lardan sample oluşturma, bölme, birleştirme, dışlama, silme,
undo/redo, autosave, yakınlaştırma, kaydırma ve döngüde oynatma davranışlarını
yeni hiyerarşiye göre değerlendir. Yararlı olanları koru; kullanıcıya belirsiz
veya veri kaybettiren kenar durumları düzelt. Örneğin birleştirilen iki hareketin
birbirinden farklı etiketleri varsa bunlardan birini sessizce kaybetme.

## Hata sınıflarını etiketleme sırasında yönetme

Hata türü seçimi serbest metinle virgül ayırmaya dayanmamalı. Kullanıcıya proje
içinde daha önce tanımlanmış hata sınıflarını etiketleme anında kolayca gösteren,
aranabilir ve hızlı bir seçim deneyimi sun.

Aranan hata sınıfı sistemde yoksa kullanıcı İnceleme ve Etiketleme ekranından
ayrılmadan "Yeni hata türü ekle" diyebilmeli. Yeni sınıf:

- Boş olmayan anlaşılır bir görünen ada ve kalıcı/stabil bir koda sahip olmalı.
- Büyük-küçük harf, boşluk veya benzer yazım nedeniyle yanlışlıkla çoğaltılmamalı.
- Projenin etiket şemasına atomik ve kalıcı biçimde kaydedilmeli.
- Kaydedildiği anda mevcut hata aralığına atanabilmeli.
- Aynı projedeki diğer hareketlerde, kayıtlarda ve uygulama yeniden açıldığında
  seçim listesinde görünmeli.
- Export sınıf eşlemesine istikrarlı biçimde yansımalı.

Bir sınıf hâlihazırda etiketlerde kullanılıyorsa onu silme veya yeniden
adlandırma gibi işlemler veri bütünlüğünü bozmamalı. Bu görev için kapsamı
gereksiz yere büyütmek zorunda değilsin; ancak yıkıcı ve sessiz bir davranış
bırakma. Yeni hata sınıfı oluşturma işlemi autosave, undo/redo ve hata durumları
ile tutarlı çalışsın. Undo işleminin proje çapındaki sınıf sözlüğünü mü yoksa
yalnız aralık atamasını mı geri alacağı kullanıcı açısından şaşırtıcı olmasın.

Hareket türleri mevcut proje şemasından seçilmeye devam edebilir. Capture
sırasında kayda atanmış güvenilir bir hareket türü varsa, kullanıcıya hız
kazandıracak bir ön seçim olarak değerlendir; fakat kullanıcı kararını sessizce
ground truth kabul etme ve bir sample'ın açık etiketi olmadan exporta hazır
sayılmasına yol açma.

## İnceleme görüntüsünün birleştirilmesi

İnceleme ve Etiketleme ekranındaki yan yana duran RGB ve 3B iskelet alanlarını
tek bir ana görüntü alanında birleştir. Kullanıcı görünür ve kolay erişilen
butonlarla şu modlar arasında geçebilsin:

- **RGB:** Yalnız kamera görüntüsü.
- **İskelet:** Yalnız iskelet görünümü.
- **RGB + İskelet:** Aynı karede senkron RGB görüntüsü üzerine iskelet bindirmesi.

Kalıcı iki ayrı görüntü paneli olmasın. Tek alan, zaman çizelgesiyle aynı kare
konumunu göstermeye devam etsin. Birlikte modunda kamera görüntüsü üzerindeki
iskelet projeksiyonu doğru ölçek ve hizayla çizilsin. İskelet-only modunda
mevcut metrik 3B görünümün yararlı döndürme/merkezleme özelliklerini korumanın mı,
yoksa tutarlı bir kamera projeksiyonu göstermenin mi daha iyi olduğuna mevcut
kod ve kullanılabilir veriye bakarak karar verebilirsin. Kullanıcı açısından
üç modun anlamı açık, geçişi hızlı ve oynatma sırasında güvenli olsun.

Proxy video yoksa iskelet görünümü çalışmaya devam etsin ve RGB gerektiren
modlarda anlaşılır bir boş durum gösterilsin. Eksik gövde takibi, birden fazla
gövde ve gövde kimliği seçimi gibi mevcut durumları bozma. Görüntü modu yalnızca
görselleştirmeyi değiştirsin; ham koordinatları veya export verisini değiştirmesin.

## Veri saklama ve geriye dönük uyumluluk

Ham kayıtların değişmezliği devam etmelidir. Etiketleme hiçbir koşulda SVO2,
proxy video, `skeleton.jsonl` veya capture provenance içeriğini değiştirmesin.
İnsan kararları sidecar annotation verisinde kalmaya devam etsin ve mevcut
atomik yazım ilkeleri korunsun.

Projede hâlihazırda kullanılmayan bir `EvidenceInterval` veri modeli bulunduğunu
göreceksin. Bunun yeni ihtiyacın iyi bir temeli olup olmadığını değerlendir;
yeniden kullanmak, geliştirmek veya daha uygun bir modelle değiştirmek senin
teknik kararın. Önemli olan disk sözleşmesinin açık, sürümlenmiş, doğrulanabilir
ve kayıpsız olmasıdır.

Eski `segments.json` dosyaları şunları içerebilir:

- Hareket seviyesinde `error_types`, `affected_joints`, `movement_phase`,
  `severity` veya eski `evidence_intervals` alanları.
- `draft/reviewed/approved/excluded`, `uncertain/unknown` gibi eski durumlar.
- Manuel, operator marker veya model suggestion kaynak bilgisi.

Eski veriyi silme veya sessizce yanlış anlama. Uygulama eski dosyaları güvenli
şekilde açabilmeli. Gerekirse şema sürümünü yükselt ve açık bir migration ya da
uyumluluk katmanı oluştur. Migration belirsiz bir eski etiketi kesin yeni
ground truth'a çevirmesin. Kullanıcının mevcut sidecar dosyasını ilk okumada
habersizce ve geri alınamaz biçimde yeniden yazma.

## Export ve gelecekteki model eğitimi

Export'ta her ana hareket sample'ı yine ayrı bir örnek olmalı. İskelet dizisinin
zaman boyutu ana sample'ın sınırlarından gelmeli. Örneğin etiket metadata'sı
hareket türü, ikili doğruluk kararı ve sıfır veya daha fazla zamansal hata
aralığını açıkça taşımalı.

Hata aralıkları model eğitimi için belirsiz olmayacak şekilde temsil edilmeli:

- Hangi hata sınıfına ait olduğu.
- Kayıt içindeki mutlak başlangıç ve bitiş konumu.
- Export edilen sample içindeki göreli başlangıç ve bitiş konumu.
- Mümkün ve yararlıysa karşılık gelen kamera kare numaraları ve zaman damgaları.
- Kullanılan sınırların anlamı ve diziyle birebir ilişkisi.

Manifestte interval listesi taşımak, sample yanında ek hedef dizileri üretmek
veya ikisini birlikte yapmak konusunda gelecekteki temporal localization
eğitimini ve mevcut proje yapısını değerlendirerek karar ver. Çözümün tüketici
tarafından tahmin yürütmeden kullanılabilir olması önemlidir. `label_mapping`
hata sınıfları için stabil sınıf listesi ve açık kod-indeks eşlemesi sağlamalı.

Export doğrulaması en azından yetim hata aralıklarını, sample dışına taşan
sınırları, bilinmeyen hata kodlarını, ters/boş aralıkları, doğruluk-hata
çelişkilerini ve manifest-dizi uzunluğu uyumsuzluklarını yakalasın. Dışlanmış
veya tamamlanmamış etiketlerin varsayılan export davranışı açık ve UI'daki
"hazır" tanımıyla aynı olsun.

Dataset fingerprint hesabı yalnız hareket türü ve doğru/yanlış etiketine değil,
hata sınıflarına ve hata aralığı sınırlarına da duyarlı olmalı. Bir hata aralığı
eklemek, silmek, yeniden sınıflandırmak veya sınırını değiştirmek release
parmak izini değiştirmeli. Release manifest, mapping ve validation raporu yeni
etiket sözleşmesini eksiksiz belgelemeli.

## Arayüz kullanılabilirliği ve son görsel iyileştirme

Öncelikle veri modeli, saklama, düzenleme davranışları, export ve testleri doğru
hale getir. Fonksiyonel etiketleme akışı güvenilir olduktan sonra GUI'yi son bir
ayrı geçişte iyileştir. Yalnızca renk veya boşluk düzenlemekle yetinme; gerçek
etiketleme oturumunu hızlı ve hatasız kılan bir deneyim hedefle.

Son arayüzde özellikle şunlara dikkat et:

- İlk kez kullanan biri hareket aralığı ile hata aralığı arasındaki farkı
  açıklama okumadan anlayabilsin.
- Seçili hareket, doğru/yanlış durumu, etiketin tamamlanma/hazır olma hali ve
  varsa eksik adım görünür olsun.
- Hata sınıfı seçme ve yeni sınıf ekleme işlemi az tıklamayla yapılabilsin.
- Birden fazla ve çakışan hata aralığı okunabilir kalsın; yalnız renge bağımlı
  olunmasın, sınıf adı/metin/ikon gibi ek ayrımlar kullanılsın.
- Aralık seçimi kare hassasiyetinde düzeltilebilsin; oynatma, scrub, zoom,
  loop ve düzenleme birbirini engellemesin.
- Otomatik kayıt durumu ve doğrulama sorunları kullanıcıya açıkça gösterilsin.
- Klavye kısayolları metin yazarken yanlışlıkla tetiklenmesin.
- Ekran 1366x768 gibi makul bir çalışma çözünürlüğünde kullanılabilir olsun;
  önemli eylemler görünmez veya aşırı kaydırma gerektiren yerlerde kalmasın.
- Boş kayıt, proxy videosuz kayıt, etiketsiz sample, doğru sample, yanlış ama
  henüz lokalize edilmemiş sample ve birden çok hatalı sample için iyi boş/
  durum görünümleri olsun.
- Türkçe metinler kısa, tutarlı ve araştırmacının anlayacağı dilde olsun.

Mevcut tema ve ortak widget sistemini değerlendir, fakat kötü bir mevcut düzeni
yalnız uyumluluk uğruna korumak zorunda değilsin. Teknik widget hiyerarşisi,
sınıf yapısı ve etkileşim ayrıntılarında kendi kararlarını al.

## Beklenen davranış ve test kapsamı

Uygulamayı yalnız görünüş olarak değil uçtan uca çalışır halde teslim et. En az
şu senaryoları otomatik testlerle güvence altına al:

- Bir kayıtta birden fazla hareket sample'ı oluşturma, düzenleme ve kalıcı
  saklama.
- Her sample'a hareket türü ve doğru/yanlış etiketi verme.
- Sample içine tek, birden fazla, aynı sınıftan tekrarlanan ve çakışan hata
  aralıkları ekleme.
- Hata aralığının ana sample dışına çıkamaması ve ana sample sınırı değişince
  güvenli davranış.
- Etiketleme ekranından yeni hata sınıfı oluşturma, projeye kaydetme ve yeniden
  açıldığında listede görme.
- Benzer/tekrarlanan sınıf adlarının kontrollü ele alınması.
- Hata aralığı ekleme, taşıma, yeniden boyutlandırma, sınıf değiştirme, silme,
  undo/redo ve autosave.
- Doğru/yanlış ile hata aralığı tutarlılık kuralları.
- Eski annotation JSON'unu veri kaybetmeden okuyabilme ve yeni formatın
  serialize/deserialize round-trip'i.
- Export edilen ana sample dizisi ile hata aralıklarının göreli/mutlak
  sınırlarının birebir eşleşmesi.
- Hata sınıfı mapping'i, export validation ve fingerprint değişimi.
- RGB, iskelet ve RGB + iskelet görüntü modlarının aynı oynatma konumunu
  göstermesi ve proxy video yokken güvenli çalışması.
- Timeline katmanlarının ve temel GUI akışının offscreen Qt testlerinde
  çalışması.
- Mevcut mock backend, capture, playback, storage, dataset ve export
  testlerinin gerilememesi.

Mevcut `KineSynth` environment'ını ve proje betiklerini kullan. Donanım
gerektirmeyen bütün testleri gerçekten çalıştır. ZED donanım testi yapılamıyorsa
bunu açıkça belirt; donanım yokluğunu yazılımın geri kalanını doğrulamamak için
gerekçe olarak kullanma. Mümkünse mock kayıtla baştan sona manuel bir smoke test
de yap.

## Tamamlanma ölçütü

Görev ancak aşağıdakilerin tamamı sağlandığında bitmiş sayılır:

- Bir kayıt içinden birden fazla bağımsız hareket sample'ı çıkarılabiliyor.
- Her hareket sample'ı hareket türü ve doğru/yanlış etiketi taşıyor.
- Seçili sample'ın içinde hata sınıfına bağlı zamansal alt aralıklar rahatça
  oluşturulup düzenlenebiliyor.
- Yeni hata sınıfı etiketleme sırasında ekleniyor, projeye kalıcı kaydoluyor ve
  sonraki etiketlerde öneriliyor.
- Hareket fazı yeni etiketleme deneyiminden ve yeni export sözleşmesinden
  kaldırılmış durumda.
- RGB, iskelet ve bindirilmiş görünüm tek görüntü alanında seçilebiliyor.
- Sidecar veri sözleşmesi, export, mapping, fingerprint, validation, dataset
  özetleri ve filtreler yeni modele göre tutarlı.
- Eski veriler ve ham kayıtlar korunuyor.
- Uçtan uca testler geçiyor ve GUI kullanılabilirlik geçişi fonksiyonel işlerden
  sonra tamamlanmış oluyor.
- `README.md` ve `MEMORY.md` gerçek son davranışı yansıtacak şekilde
  güncelleniyor.

Görev sonunda kısa ama somut bir teslim raporu ver: değişen kullanıcı akışını,
veri sözleşmesini, migration/uyumluluk kararını, export formatını, çalıştırılan
testleri, varsa donanımda doğrulanamayan noktaları ve bilinçli olarak kapsam
dışında bıraktığın işleri açıkla. Küçük teknik kararlarda onay beklemek yerine
makul varsayımlar yap; ancak kullanıcı verisini riske atan veya ürün anlamını
değiştiren belirsiz bir karar varsa bunu görünür biçimde ele al.
