# Claude Code Görevi — Capture ve İnceleme/Etiketleme Deneyimini Sadeleştirme

> **Bu görevin izi:** [6G uygulama kaydı](../knowledge/archive/memory/6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · [Veri hattı](../knowledge/concepts/pipeline.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


KineCapture Studio'da Capture ile İnceleme ve Etiketleme ekranlarını aşağıdaki
ürün kararlarına göre yeniden düzenle. Bu görevi yalnız analiz, öneri veya plan
olarak bırakma: gerçek kodu değiştir, regresyon testlerini ekle, uygun bütün
testleri çalıştır, ekranları gerçekten çizdirerek doğrula ve görev sonunda
`MEMORY.md` dosyasını gerçek sonuçlarla güncelle.

Bu promptta tarif edilen yeni ürün kararları, eski belgelerdeki veya mevcut
arayüzdeki çelişkili davranışlardan üstündür. Bununla birlikte kullanıcı
verisini, değişmez ham kaydı veya eski annotation sidecar'larını silmek ya da
sessizce yeniden yorumlamak yasaktır.

## 1. Başlangıç ve değişmez çalışma kuralları

1. Önce repository kökündeki `CLAUDE.md` ve `MEMORY.md` dosyalarının tamamını
   oku. Ardından gerçek kodu ve testleri incele. Hafıza ile kod çelişiyorsa
   gerçek davranışı doğrula, çelişkiyi görünür kıl ve yeni kararı görev sonunda
   `MEMORY.md` içine kaydet.
2. En az şu dosyaları ve bunlarla ilişkili testleri incele:
   - `src/kinecapture/gui/pages/capture.py`
   - `src/kinecapture/gui/pages/review.py`
   - `src/kinecapture/gui/widgets/scene_view.py`
   - `src/kinecapture/gui/widgets/video_view.py`
   - `src/kinecapture/gui/widgets/skeleton_view.py`
   - `src/kinecapture/gui/widgets/timeline.py`
   - `src/kinecapture/gui/widgets/error_picker.py`
   - `src/kinecapture/playback/take_reader.py`
   - `src/kinecapture/recording/take_writer.py`
   - `src/kinecapture/domain/models.py`
   - `src/kinecapture/domain/project.py`
   - `src/kinecapture/domain/labels.py`
   - `src/kinecapture/domain/activity.py`
   - `src/kinecapture/annotations/repository.py`
   - `src/kinecapture/dataset/workspace.py`
   - `src/kinecapture/export/continuous.py`
   - `src/kinecapture/export/release.py`
   - `tests/test_capture_subject_gui.py`
   - `tests/test_review_flow.py`
   - `tests/test_gui_painting.py`
   - ilgili diğer GUI, annotation, playback ve export testleri
3. Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
   oluşturma; bilimsel ortamın paketlerini gereksiz yere kurma, kaldırma veya
   yükseltme.
4. Çalışma ağacı kirliyse kullanıcıya ait değişiklikleri koru. İlgisiz
   değişiklikleri geri alma veya üzerlerine yazma.
5. Ham kayıt değişmezliğini, annotation sidecar ayrımını, atomik JSON yazımını,
   yarım kayıt kurtarmayı, Windows uzun yol desteğini, sentetik veri işaretini,
   mock backend'i, güvenli kapanışı ve preview-loss/capture-loss ayrımını koru.
6. GUI thread'ini kamera, disk veya ağır hesapla bloklama. `pyzed` yine yalnız
   `camera/zed.py` içinde gecikmeli import edilsin.
7. Kod, tanımlayıcılar ve veri alanları İngilizce; kullanıcıya görünen bütün
   yeni metinler Türkçe olsun. Mevcut tema, vektör ikon ve erişilebilirlik
   yaklaşımını koru; emoji ekleme.
8. Sorunu sihirli piksel ofsetleri, sabit ekrana göre konum ayarı veya yalnız
   bir ekran görüntüsünde iyi görünen CSS/Qt hilesiyle maskeleme. Kök nedeni
   veri, koordinat sistemi, senkronizasyon ve layout sözleşmeleri üzerinden
   çöz.

## 2. Kodda doğrulanmış mevcut durum

Değişikliğe başlamadan bunları yeniden doğrula; bu liste kod incelemesinden
çıkan başlangıç noktasıdır, değişmez varsayım değildir:

- `CapturePage`, iki ana görüntü kartını (`Canlı görüntü` ve `3B iskelet`)
  yatay gösteriyor; fakat `_build_side_panel()` içindeki Ön kontrol, Kayıt
  Planı, Kayıt bilgisi, Kaydedilecek kişi ve Ham RGB-D arşivi kartları ikinci
  bir kalıcı sütun olarak ekranın yaklaşık `2/5` genişliğini alıyor.
- `ReviewPage` tek bir `SceneView` içinde RGB / İskelet / RGB + İskelet
  modlarına sahip olsa da sağdaki geniş ve kaydırılabilir sütun sürekli açık.
  Hareket, Hata ve Aktivite kartlarının ayrıntılı formları burada bulunuyor.
- İnceleme oynatımında `_redraw()` bugün `frame.bodies` içindeki bütün
  iskeletleri `SceneView`'a veriyor. `Gövde` seçicisi yalnız `active_id`
  belirliyor; diğer gövdeler yine çiziliyor. Bu nedenle kullanıcı, kayıt
  sırasında kilitlenmiş kişi dışında iskeletler görebiliyor.
- `SkeletonFrame.subject_body()` kayıt sırasında seçilmiş kişiyi otoritatif
  biçimde döndürüyor ve kişi o karede yoksa başka gövdeye fallback yapmıyor.
  Bu doğru güvenlik sınırı İnceleme ekranında şu an kullanılmıyor.
- `VideoView`, `joint_positions_2d` varsa tracker'ın gerçek kamera pikselini
  kullanıyor. Bu alan yoksa `_focal_ratio = 0.75` ile yaklaşık 3B projeksiyona
  düşüyor. Bu tahmin gerçek kamera intrinsics'i değildir ve kayık bindirmeye
  yol açabilir.
- `LoadedTake.video_position_for()` iskelet pozisyonu ile proxy video
  pozisyonunu özdeş varsayıyor ve kısa videoda son kareye clamp ediyor. Bu,
  gerçekten eşlenmeyen bir RGB karesini başka iskelet karesiyle göstermemeli.
- Proje etiket sözlüğü `label_schema.json` içindedir. `LabelSchema` hem hareket
  hem hata sınıfı ekleyebilir; hata sınıfı için etiketleme sırasında oluşturma
  akışı zaten vardır, fakat hareket sınıfı için eşdeğer sade mini pencere akışı
  yoktur.
- Aktivite modu 2026-08-24'te bilinçli olarak eklenmiş eski bir ürün
  özelliğidir. Aşağıdaki yeni karar, İnceleme ve Etiketleme ürün akışı için bu
  eski kararı geçersiz kılar. Eski aktivite verisinin var olması onu silme
  yetkisi vermez.

Mevcut başlangıç sürümlerini de koddan doğrula. Bu prompt hazırlanırken gerçek
değerler `APP_VERSION = 0.7.0`, annotation/label/release şemaları `2.0.0`,
skeleton stream `1.1.0`, raw archive `1.0.0`, project `1.1.0`, session `2.0.0`
ve take `1.1.0` idi. Gerçek veri sözleşmesi değişmiyorsa sırf GUI değişti diye
şema sürümü yükseltme; sözleşme değişiyorsa doğru sürümleme ve geriye uyumluluk
uygula.

## 3. Capture ekranı — görüntülere geniş alan, bilgiler isteğe bağlı

Capture ekranındaki RGB/derinlik görüntüsü ile 3B iskelet görüntüsü ana çalışma
alanıdır. İkisi yatayda mümkün olduğunca geniş ve yeniden boyutlandırılabilir
olmalı. Sağdaki bilgi kartları sürekli açık bir sütun olarak yer kaplamamalı.

İstenen davranış:

1. Kalıcı sağ bilgi sütununu kaldır. Ön kontrol, Kayıt Planı, Kayıt bilgisi,
   Kaydedilecek kişi ve Ham RGB-D arşivi bilgileri kaybolmasın; header veya
   görüntü alanına yakın, açıkça görünen tek bir `Bilgiler` / `Kayıt bilgileri`
   düğmesiyle açılan ayrı bir pencere ya da dialog içinde erişilebilir olsun.
2. Açılan pencere:
   - aynı gerçek widget durumlarını göstermeli, eski kartların çalışan
     eylemlerini korumalı;
   - Capture devam ederken güncellenen sağlık, kişi kilidi, disk ve arşiv
     durumlarını canlı göstermeli;
   - bir kez açıldığında yanlışlıkla ikinci kopyasının üretilmesini önlemeli;
   - ana pencere kapanırken güvenli biçimde kapanmalı;
   - 1120x700 ve 1366x768 gibi küçük ekranlarda taşmamalı, gerekirse kendi
     içinde kaydırılmalı;
   - modal olmak kişi seçimi veya canlı takibi gereksiz yere engelliyorsa
     modeless/toggle pencere olarak tasarlanmalı. En uygun Qt yaşam döngüsünü
     gerçek kullanım akışına göre seç ve test et.
3. Ana Capture ekranında iki görüntü kartı artık neredeyse bütün yatay alanı
   kullanmalı. Splitter oranları, minimum boyutlar ve stretch factor'lar hem
   16:9 hem daha dar pencerelerde anlamlı olsun.
4. Kullanıcı görüntüye tıklayarak kaydedilecek kişiyi seçmeye devam edebilmeli.
   Bilgi penceresine taşımak bu akışı, `Kimliği yeniden doğrula` ve `Seçimi
   kaldır` eylemlerini bozmamalı.
5. Kayıt düğmeleri, marker, süre ve kritik kalite göstergeleri ana ekranda
   erişilebilir kalmalı. Özellikle kayıt kaybı, bağlantı hatası, yetersiz disk
   veya belirsiz kişi gibi hemen müdahale gerektiren durumları yalnız kapalı
   pencerenin içine gömme; ana ekranda kompakt bir uyarı/özet göster.
6. Bilgi kartlarını silip işlevleri erişilemez hale getirmek kabul edilmez;
   istenen şey sürekli kapladıkları alanı geri kazanmaktır.

## 4. İnceleme — yalnız kayıt sırasında seçilen kişinin iskeleti

İnceleme ve Etiketleme ekranında amaç birden fazla tracker gövdesini
karşılaştırmak değildir. Kullanıcı yalnız kayıt sırasında veri setine alınmak
üzere seçilmiş kişiyi görmelidir.

1. Subject lock bulunan yeni kayıtlarda her kare için yalnız
   `frame.subject_body()` sonucunu çiz:
   - sonuç varsa `SceneView`'a yalnız o tek gövdeyi ver;
   - sonuç yoksa boş iskelet durumu göster;
   - başka bir gövdeyi `best available`, en yüksek güven veya önceki tracker ID
     diye sessizce ödünç alma;
   - RGB + İskelet ve yalnız İskelet modları aynı kişi seçimi politikasını
     kullanmalı.
2. `Gövde`/tracker-ID seçicisini normal İnceleme arayüzünden kaldır. Seçilmemiş
   diğer gövdeleri düşük opaklıkla da olsa çizme. Bu ekranda bir karede
   çizilebilecek gövde sayısı en fazla birdir.
3. Subject lock öncesindeki eski kayıtlar için kimlik uydurma. `active_id`
   yalnız gerçekten kaydedilmiş ve o karede mevcutsa kontrollü bir legacy
   görüntüleme kaynağı olarak değerlendirilebilir; rastgele `body()` fallback'i
   ile kişiler arasında geçiş yapılamaz. Otoritatif kişi bilgisi yoksa bunu
   açık bir legacy uyarısıyla göster ve güvenilir iskelet yokken hiç iskelet
   göstermemeyi yanlış kişiyi göstermekten üstün tut. Eski ham/pose verisini
   değiştirme.
4. Zaman çizelgesindeki takip kapsamı, durum metinleri ve kalite bilgileri de
   mümkünse aynı seçilmiş kişi kaynağını kullansın; ekranda tek kişi gösterip
   kapsamı başka bir gövdeden hesaplama.
5. Kişi geçici kaybolduğunda son pozu dondurma veya başka gövdeye atlama.
   Eksik kare eksik olarak görünmeli ve veri tarafında NaN/presence-mask
   sözleşmesi korunmalı.

## 5. RGB + İskelet bindirmesindeki kaymayı kök nedeninden çöz

Bindirme düzeltmesi yalnız bir görsel ofset değildir. Aynı fiziksel kareyi,
aynı kamera piksel uzayını ve aynı seçilmiş kişiyi kullandığını kanıtla.

1. Şu olası hata kaynaklarını gerçek kod ve kayıt sözleşmesi üzerinden ayrı
   ayrı incele:
   - proxy RGB karesi ile skeleton stream pozisyonunun/timestamp'inin eşleşmesi;
   - `position`, kamera `frame_index` ve `camera_timestamp_ns` kavramlarının
     karıştırılması;
   - proxy video kısa, eksik veya aranamazken son RGB karesine clamp edilmesi;
   - tracker'ın `joint_positions_2d` piksel koordinatları ile proxy görüntünün
     gerçek çözünürlüğü, ölçeklenmesi, crop/resize işlemi ve letterbox dönüşümü;
   - ZED koordinat sistemi ve metre cinsinden 3B eklemlerin kamera intrinsics'i
     ile projeksiyonu;
   - bütün gövdelerin çizilmesinin yanlış kişiye ait bindirmeyi kayma gibi
     göstermesi.
2. `joint_positions_2d` mevcutsa bunu o gövdenin otoritatif 2B bindirme kaynağı
   olarak kullan. Şekil, joint sayısı, sonlu değerler ve kaynak görüntü
   çözünürlüğünü doğrula. Qt widget koordinatına dönüşüm letterbox ve DPI'dan
   bağımsız doğru çalışmalı.
3. 2B eklemi olmayan legacy kayıtta sabit `_focal_ratio`, elle ayarlanmış x/y
   ofseti veya tahmini principal point ile “yaklaşık doğru” görüntü üretme.
   Kayıtta güvenilir sol kamera calibration/intrinsics ve gerekli koordinat
   sözleşmesi gerçekten varsa pinhole projeksiyonu onlarla uygula. Gerekli veri
   yoksa bindirmenin güvenilir olmadığını açıkça göster ve yanlış iskeleti
   çizme; yalnız İskelet modu çalışmaya devam etsin.
4. Bir skeleton pozisyonuna karşılık gelen proxy RGB karesi yoksa başka kareyi
   tekrar gösterme. Görüntüyü “bu kare için RGB yok” olarak işaretle veya
   doğrulanmış timestamp/indeks eşlemesini kullan. Kullanıcı kayık ama dolu bir
   görüntüdense dürüst eksik durumu görmeli.
5. Canlı Capture bindirmesini de regresyona uğratma. Aynı `VideoView`
   kullanılıyorsa canlı paketlerin 2B eklem bilgisi ve görüntü çözünürlüğüyle
   çalışmaya devam ettiğini test et.
6. Çözümden sonra gerçek ZED kaydında doğrulama yapılabiliyorsa aynı karede
   belirgin eklemler (baş, omuzlar, kalça, dizler, ayaklar) üzerinde görsel
   kontrol yap. Donanım veya uygun gerçek kayıt yoksa bunu yapılmış sayma;
   sentetik/geometrik testin neyi kanıtladığını ve gerçek donanımda neyin
   doğrulanmadığını ayrı yaz.

## 6. İnceleme ve Etiketleme arayüzü — iki aralık, sade eylemler, mini pencereler

Bu ekranın yazılabilir etiket modeli kullanıcı açısından yalnız iki zamansal
katmandan oluşacak:

1. **Hareket sınıfı aralığı**: bir hareket örneğinin başlangıç ve bitişi;
   hareket sınıfı bu aralığa aittir.
2. **Hata sınıfı aralığı**: seçili hareketin içindeki hatalı bölümün başlangıç
   ve bitişi; bir hata sınıfı bu aralığa aittir.

Kalıcı geniş sağ paneli ve sınıf seçmek için sürekli açık formları kaldır.
Görüntü ve timeline ana çalışma alanı olsun. Gerekli ana eylemler kompakt ve
her zaman görünür olabilir:

- `Hareket ekle`
- `Hata ekle`
- gerektiği ölçüde `Sil`, `Geri al`, `Yinele`, `Oynat/Döngüle` ve bilgi
  düğmeleri

Eski gelişmiş CRUD yetenekleri (böl, birleştir, dışla, marker'lardan oluştur,
öncekini kopyala vb.) işlevsel olarak korunacaksa ana alanı yeniden kalabalık
etme; bağlam menüsü, üç nokta menüsü, klavye kısayolu veya aralık mini
penceresinde uygun biçimde grupla. Kullanıcı verisini sessizce kaybettiren bir
özellik kaldırma.

### 6.1 Aralık oluşturma akışı

1. `Hareket ekle` düğmesi timeline'ı hareket aralığı çizme moduna hazırlar.
   Kullanıcı ilgili şeritte sürükleyerek kapsayıcı başlangıç-bitiş aralığını
   belirler. Oluşan aralık seçilir ve görünür biçimde “sınıf bekliyor” durumu
   taşıyabilir.
2. `Hata ekle` düğmesi için önce bir hareket seçili olmalı. Kullanıcı yalnız o
   hareketin içinde hata aralığı çizebilmeli; hareket dışı alan maskeli veya
   pasif olmalı. Ana hareket dışına taşma domain katmanında da reddedilmeli.
3. Düğmelerin hazırladığı mod, imleç/şerit açıklaması ve seçili ana hareket
   her an anlaşılır olmalı. Hareket ve hata çizimi birbirine karışmamalı.
4. Aralık sınırları `skeleton.jsonl` listesindeki 0 tabanlı akış pozisyonudur
   ve iki uç da dahildir. UI, sidecar ve export bu sözleşmede kalmalı.

### 6.2 Çift tıklamayla açılan mini etiket pencereleri

1. Timeline'daki mevcut bir **hareket aralığına çift tıklanınca** küçük,
   odaklı bir Hareket Etiketi penceresi açılsın. Mevcut çift tıklama yalnız
   zoom yapıyorsa bu davranışı değiştir; zoom ayrı bir eylem olarak kalabilir.
2. Timeline'daki mevcut bir **hata aralığına çift tıklanınca** küçük, odaklı
   bir Hata Etiketi penceresi açılsın.
3. Pencereler ekrana göre boyutlu, klavyeyle kullanılabilir ve dark/light
   temada düzgün olmalı. `Kaydet`, `İptal` ve uygun doğrulama mesajları açık
   olsun. Aynı aralık için gereksiz dialog kopyaları açılmasın.
4. Hareket penceresi en az şunları sunsun:
   - projede daha önce tanımlanmış hareket sınıflarının aranabilir/görülebilir
     listesi;
   - mevcut aralığın seçili sınıfı;
   - listede olmayan yeni hareket sınıfını o anda oluşturma;
   - mevcut iki seviyeli annotation sözleşmesinin gerektirdiği doğru/hatalı
     kararı. Bu alan kaldırılmıyorsa sağ panelde değil bu pencerede yer alsın;
   - gerekiyorsa not, dışlama ve gelişmiş eylemler sade/ikincil bölümde.
5. Hata penceresi en az şunları sunsun:
   - projede daha önce tanımlanmış hata sınıflarının aranabilir/görülebilir
     listesi;
   - mevcut aralığın tek hata sınıfı;
   - listede olmayan yeni hata sınıfını o anda oluşturma;
   - aralığı oynatma ve gerektiğinde silme gibi ilgili küçük eylemler.
6. Yeni sınıf ekleme hem hareket hem hata için proje düzeyindeki
   `label_schema.json` dosyasına mevcut atomik `ProjectWorkspace` yoluyla
   kaydolmalı. Kod içine örnek sınıf yazma. NFKC/casefold/boşluk normalizasyonu
   ve mevcut duplicate kurallarını iki sınıf türünde de tutarlı uygula.
7. Yeni sınıf oluşturmak proje sözlüğü düzenlemesidir: annotation undo aralığı
   veya sınıf atamasını geri alabilir, fakat ortak sınıfı sözlükten sessizce
   silmemeli. Bu mevcut hata sınıfı kararına hareket sınıflarında da uyumlu
   olsun.
8. İptal edilen dialogun aralık ve yeni sınıf üzerindeki etkisini açık ve
   test edilebilir biçimde tanımla. Yarım bırakılan aralık sessizce “hazır”
   sayılmamalı; kullanıcıya eksik etiket durumu görünmeli.

## 7. Aktivite etiketleme akışını kaldır

İnceleme ve Etiketleme ekranında `Aktivite durumları`, `Aktivite` kartı,
AKTİVİTE şeridi ve arka plan/geçiş/hedef egzersiz/diğer hareket sınıflandırması
artık bulunmamalı. Kullanıcı bu ekranda yalnız hareket ve hata aralıklarını
yazar.

1. En az şu kullanıcı yollarını kaldır veya devre dışı bırak:
   - `TimelineMode.ACTIVITY` ile açılan düzenleme modu;
   - `Aktivite durumları` sekmesi/düğmesi;
   - Aktivite kartı, listesi, durum düğmeleri, egzersize bağlama,
     hareketlerden oluşturma ve boşlukları arka plan yapma eylemleri;
   - F3 aktivite kısayolu;
   - timeline'da yeni aktivite aralığı çizme, seçme, taşıma ve çift tıklama;
   - İnceleme ekranındaki aktivite kapsamı/hazırlık metinleri.
2. Aktivite kavramını Hareket olarak yeniden adlandırıp aynı üçüncü katmanı
   saklama. Gerçekten yalnız iki authoring lane'i kalmalı: Hareket ve Hata.
3. Eski take'lerin `activity_intervals` verisini silme, üzerine yazma veya
   hareket aralıklarına otomatik dönüştürme. Annotation dosyasını kaydederken
   bilinmeyen/retired bloklar kayıpsız korunmalı. Gerekirse aktivite domain ve
   continuous export kodu yalnız geriye dönük okuma/uyumluluk için kalabilir;
   fakat İnceleme ekranından yeni aktivite etiketi üretilememeli.
4. Export ekranında veya başka kullanıcıya açık akışlarda “yeni aktivite
   dataseti üret” seçeneği hâlâ normal ürün özelliği gibi görünüyorsa yeni ürün
   kararıyla tutarlılığını incele. Bu görevde güvenle kaldırılabiliyorsa kullanıcı
   yolunu emekliye ayır; eski release'leri veya eski sidecar'ları değiştirme.
   Kapsam dışı bırakmak zorundaysan nedenini ve kalan görünür yolu raporla.
5. Aktivite verisini fiziksel olarak silmek, eski release'leri yeniden yazmak
   veya okuma sırasında migration yapmak bu görevde yasaktır.

## 8. Sağ panel yerine önerilen bilgi mimarisi

Kesin piksel tasarımını mevcut bileşen diliyle sen çöz; fakat sonuç şu ilkeleri
sağlamalı:

- Görüntü ve timeline genişliğin çoğunu kullanır.
- Üstte veya timeline yakınında hangi aralık türünün eklendiği ve hangi
  hareketin seçili olduğu kompakt biçimde görünür.
- Sınıf sözlükleri ve ayrıntılı formlar yalnız gerektiğinde açılan mini
  pencerelerdedir.
- Kayıt seçimi, autosave durumu ve temel oynatma kontrolleri kolay erişilir
  kalır.
- Kayıt teknik bilgileri gerekiyorsa Capture'daki yaklaşıma benzer ayrı bir
  `Kayıt bilgileri` penceresine taşınabilir.
- Geniş boş listeler, sürekli açık açıklamalar ve aynı işi yapan tekrar eden
  düğmeler ana çalışma alanını daraltmaz.
- 1120x700, 1366x768 ve 1600x980 ölçülerinde; dark/light temada kırpılma,
  üst üste binme ve gereksiz yatay scroll olmaz.

## 9. Test ve kabul ölçütleri

En az aşağıdaki regresyonları otomatikleştir. Sadece widget'ı kurmak yetmez;
özel çizim yollarını `show()`/event processing/`grab()` ile gerçekten çalıştır.

### Capture

- Ana Capture layout'unda kalıcı sağ sütun yoktur; iki görüntü alanı genişler.
- Bilgi düğmesi tek pencere açar, tekrar basma/focus davranışı tutarlıdır ve
  bütün eski bilgi/eylemler erişilebilir kalır.
- Bilgi penceresi açık ve kapalıyken canlı frame, subject lock ve capture
  kontrolleri çalışır.
- Küçük ekran, iki tema ve yüksek DPI'ya duyarlı layout dumanı geçer.

### Seçilmiş kişi

- Aynı karede üç body olsa bile subject lock birini işaretlediğinde RGB+
  İskelet ve İskelet modlarına yalnız o body verilir.
- Seçilmiş kişi kayıpken başka body görünmez ve yanlış kişiye fallback olmaz.
- Tracker ID yeniden ilişkilendirilse bile karedeki `subject.tracker_id`
  izlenir; sabit eski ID'ye yapışılmaz.
- Legacy kaydın kontrollü davranışı test edilir; otoritatif bilgi yokken
  rastgele kişi çizilmez.

### Bindirme

- Bilinen çözünürlükte sentetik 2B eklemler, letterbox uygulanmış farklı widget
  boyutlarında beklenen görüntü pikseline düşer.
- Yalnız seçilmiş body'nin 2B eklemleri çizilir.
- 2B alanı olmayan kayıtta doğrulanmış intrinsics yolu matematiksel olarak
  test edilir; calibration yoksa yaklaşık/fake overlay gösterilmediği test
  edilir.
- Proxy ile skeleton kare sayısı uyuşmadığında son RGB karesi başka skeleton
  pozisyonuna clamp edilmez.
- Mevcut RGB-only ve skeleton-only modları bozulmaz.

### Etiketleme akışı

- `Hareket ekle` ve `Hata ekle` doğru lane'i hazırlar; hata hareket dışına
  çizilemez.
- Hareket aralığına çift tıklama hareket dialogunu, hata aralığına çift tıklama
  hata dialogunu açar.
- Her dialog mevcut sınıfları gösterir, mevcut seçimi yükler ve seçimi
  kaydeder.
- Hem yeni hareket hem yeni hata sınıfı dialog içinden eklenir, normalize
  duplicate oluşturulmaz ve proje yeniden açıldığında sınıf kalır.
- İptal/kaydet, incomplete readiness, undo/redo ve autosave semantiği test
  edilir.
- Bir hata aralığı tek sınıf taşır; bir hareket içinde birden çok/çakışan hata
  aralığı mevcut sözleşmeye göre çalışır.
- Hareket doğru işaretliyken hata aralığı çelişkisi ve hatalı işaretliyken hata
  aralığı eksikliği mevcut readiness/export kurallarıyla tutarlı kalır.
- Aktivite düğmesi, şeridi, kartı ve F3 yolu artık yoktur.
- Eski `activity_intervals` içeren sidecar açılıp hareket etiketi düzenlenip
  kaydedildiğinde eski aktivite bloğu byte eşit olmak zorunda olmasa bile
  semantik olarak kayıpsız korunur.

### Genel doğrulama

1. Önce ilgili hedef testleri çalıştır.
2. Ardından `KineSynth` içinde tam paketi çalıştır:

   ```powershell
   .\scripts\run_tests.ps1
   conda run -n KineSynth python -m kinecapture --self-test
   ```

3. En az Capture ve İnceleme sayfalarını 1120x700, 1366x768 ve 1600x980'de,
   dark/light temada gerçekten çizdir. Mümkünse önce/sonra ekran görüntülerini
   karşılaştır.
4. Gerçek ZED 2i veya kullanıcının sorunu gösteren gerçek take erişilebilirse
   bindirmeyi onunla da doğrula. Kamera çalıştırılmadıysa veya gerçek take
   bulunmadıysa açıkça “donanımda doğrulanmadı” yaz; mock/offscreen testi gerçek
   kamera kanıtı gibi sunma.
5. Çalıştırmadığın testi geçti diye raporlama. Hata veya warning varsa nedenini
   incele; sırf yeşil sonuç için testi gevşetme.

## 10. Tamamlanma raporu ve `MEMORY.md`

Görev sonunda:

1. Değişen dosyaları ve kullanıcı açısından yeni Capture/İnceleme akışını kısa
   ve açık biçimde özetle.
2. Çoklu iskeletin gerçek nedenini ve yalnız seçili kişinin nasıl garanti
   edildiğini açıkla.
3. RGB + İskelet kaymasının bulduğun gerçek kök nedenini yaz; hangi veri
   kaynağının projeksiyon ve senkronizasyon için otoritatif olduğunu belirt.
4. Aktivite verisinin emeklilik/geriye uyumluluk politikasını açıkla; eski
   verinin silinmediğini doğrula.
5. Sınıf ekleme, dialog iptali, readiness, undo ve schema sürüm kararlarını
   yaz.
6. Gerçek `APP_VERSION` ile bütün gerçek schema/contract sürümlerini listele;
   değişenleri ve değişmeyenleri ayır.
7. Gerçekten çalıştırılan her test komutunu, pass/fail sayısını ve süreyi
   kaydet. Donanımda veya gerçek kayıtta doğrulanamayanları ayrıca belirt.
8. Bu kalıcı kararları ve kanıtları son kullanıcı yanıtından önce `MEMORY.md`
   içine ekle. `MEMORY.md` güncellenmeden görev tamamlanmış sayılmaz.

## Bitti sayılmayacak sonuçlar

- Yalnız tasarım/plan sunmak, kodu uygulamamak.
- Sağ panelleri gizleyip bilgileri erişilemez bırakmak.
- İncelemede seçili kişiyi vurgulayıp diğer iskeletleri çizmeye devam etmek.
- Kişi kaybolunca başka bedene, “en iyi” bedene veya son poza fallback yapmak.
- Bindirmeyi sabit odak oranı, elle x/y kaydırma ya da tek çözünürlüğe göre
  ayarlamak.
- Proxy video eksikken başka kareyi tekrar gösterip iskeletle eşleşmiş gibi
  sunmak.
- Hareket sınıfı eklemeyi yalnız Ayarlar ekranına bırakmak.
- Aktivite sekmesini yalnız yeniden adlandırmak veya gizli bir üçüncü
  authoring lane olarak bırakmak.
- Eski `activity_intervals`, ham kayıt, take metadata veya release'leri silmek
  ya da yeniden yazmak.
- Yalnız offscreen widget construction testiyle görsel ve etkileşimli akışı
  doğrulanmış saymak.

