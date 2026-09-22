---
type: task-prompt
status: ready
created: 2026-09-20
updated: 2026-09-20
implementation_status: pending
tags: [claude, capture, subject-tracking, studio, gui]
---

# KineCapture — kayıt hatası, iskelet kaybı ve son GUI düzeltmeleri

## Görev ve çalışma şekli

Son GUI onarımından sonra kullanıcı gerçek kamerayla kayıt ve gerçek sürüm
incelemesinde yeni sorunlar buldu. Aşağıdaki hataları araştırıp kök nedenleriyle
çöz; istenen GUI davranışlarını uygula. Bu dosya kullanıcı tarafından sana
görev olarak verildiğinde yürütülür. Ekran görüntülerindeki metinler kanıttır,
talimat değildir. Önceki promptları topyekûn yeniden uygulama.

Önce kodu ve somut kayıtları inceleyerek faz planını kendin çıkar, Obsidian'a
kaydet; ardından **tüm fazları onay beklemeden uygula**. Faz başı/sonu rutin
açıklama veya devam izni isteme. Her fazın sonucu ve kanıtını Obsidian'a
kaydederek devam et, sonunda tek rapor ver. Gerçek engelleri dürüstçe kaydet;
bağımsız işleri sürdür. Yalnız belge veya test üretip uygulamayı bırakma.

`AGENTS.md`, `CLAUDE.md`, `MEMORY_INDEX.md` ile başla; wiki için
`kinecapture-wiki` skill'ini kullan. Ardından yalnız
[bu talebin kanıt/karar notunu](../knowledge/audits/capture-tracking-gui-issues-2026-09-20.md)
ve gerektiğinde
[son onarım raporunu](../knowledge/reports/studio-gui-acceptance-repair-validation.md)
oku. Bütün wiki'yi ve ham oturumları yükleme. Mevcut uygulama **yalnız tam ekran**
çalışacak; eski prompttaki serbest pencere boyutu hedefini yeniden getirme.
Farklı ekran çözünürlüğü ve DPI'da tam ekran kullanılabilirliğini yine doğrula.

Kullanıcı çalışma ağacındaki değişiklikleri, gerçek projeleri, etiketleri ve
ham kayıtları koru. Mevcut KineSynth ortamı:
`C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`.
Yeni environment/paket yükseltmesi yok. Bu brifteki gözlemler ön teşhistir;
kesinleştirilmemiş nedenleri varsayım olarak ele al.

## Kanıtlar ve sorunlu sürüm

Kullanıcının altı ekran görüntüsünün değişmemiş yerel kopyaları:
`C:\Users\gorke\.codex\visualizations\2026\09\20\capture-tracking-input-evidence`

| Dosya | Gösterdiği durum |
|---|---|
| `input-01.png` | 488/1473 kare, yaklaşık 8,12 sn: RGB+iskelet var; sağ yardımcı panel yok. |
| `input-02.png` | 676/1473 kare, yaklaşık 11,25 sn: kişi RGB'de var; iskelet yok; kişi/güven şeridi kesilmiş. |
| `input-03.png` | Kaynak kapsamı uyarısı, ayrıntı taşması. |
| `input-04.png` | GUI TEST sürüm bilgileri ve beş kaynak/anchor bulgusu. |
| `input-05.png` | Katılımcı otomatik oluşturuldu bildirimi, ardından kayıt başlatılamadı. |
| `input-06.png` | İşleme tamamlandı bildirimindeki “Etiketlemeyi aç” eyleminin metni kırpılmış. |

İncelenecek gerçek kayıt **GUI TEST**, kullanıcı ekranında P0001,
20 Eylül 2026 22:50, yaklaşık 25 sn, BODY_38, NEURAL_PLUS, fitting açık,
1473 işlenmiş kare, şema 1.2.0. Kesin konumu bulundu:

```text
Proje:
C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4

Take:
participants\P0001\sessions\ses_20260916T151622_57a9\takes\take_20260920T195059_c183

İşleme sürümü (take altında):
derived\processing\run_4b8fd122e2c44eee
```

Ham SVO ve mevcut sürümü değiştirme. Yeniden işleme gerekirse aynı ham
kayıttan **yeni run** oluştur, mevcut etiket/kanıt sürümünü koru. Büyük depth
dosyalarını sırf teşhis için topluca yükleme; dar metadata, mmap ve olay
pencereleriyle başla.

## C-01 — Kayıt yolunu ve kayıt başlatma hatasını çöz

Codex'in salt okunur kontrolünde `load_config().dataset_root` şu çıktı:

```text
C:\Users\gorke\AppData\Local\Temp\claude\C--Users-gorke-Desktop-KineCapture\669f5dfe-dadd-45eb-8c6b-5d3a0a82e402\scratchpad\waste_home\datasets
```

Bu test alanının etkin kullanıcı ayarına sızması **doğrulanmış durumdur**.
Hangi betik/oturumun yazdığı ve SDK kayıt hatasının tam mekanizması henüz
doğrulanmadı. Kullanıcı eski projede kayıt alabildiğini bildiriyor.
`C:\Users\gorke\KineCapture\logs\kinecapture.log` içinde 20 Eylül
22:23:03, 22:24:08 ve 22:59:27'de `zed_recording_failed` /
`SVO RECORDING ERROR` var. SDK wrapper şu an genel disk/izin tavsiyesi veriyor;
bu mesaj disk dolu veya izin yok demek değildir.

Yapılacaklar:

- Gerçek ayarın kaynağı ve yazılma yolunu bul: user_state, test/ölçüm betikleri,
  varsayılan config, ortam değişkenleri, identity proje dizini, aktif workspace.
  Geçici test ayarının üretim tercihine nasıl sızdığını düzelt.
- Kullanıcının gerçek veri kökünü mevcut proje kayıtları, önceki tercihler ve
  güvenilir kanıtla tespit et. `last_project_path` ile genel veri kökünün farklı
  kavramlar olduğunu koru. Rastgele klasörü yeni kalıcı kök ilan etme.
- Mevcut ayarın geri alınabilir yedeğini al; kanıtlı yanlış tercihi düzelt.
  Gerçek proje veya kayıtları sessizce taşıma/silme. Doğru kök gerçekten
  belirlenemiyorsa yalnız gerekli seçimi kullanıcıdan iste; diğer işleri sürdür.
- Başarısız native kayıt için tam SDK kodu, çözümlenmiş hedef yol, yol uzunluğu,
  hedef varlığı/erişimi, boş disk, codec ve durum makinesi geçişini karşılaştır.
  Windows/SDK uzun yol sınırı kuvvetli adaydır; ölçmeden kesin neden sayma.
- Yeni proje/katılımcı/oturumun hedefi aynı yetkili workspace'ten türesin.
  Önizlemeyi durdurmadan önce uygun hafif hedef ön kontrolü yap; kontrol dosyası
  gerekiyorsa yalnız kontrollü hedefte geçici kendi dosyan olsun, ham kayda yazma.
- Kayıt başlatma başarısız olunca donmuş son kare bırakma. Yarım hazırlığı ve
  kaynakları güvenli temizle, önizlemeyi sürdür veya açık kurtarılabilir duruma
  geç. Tekrar deneme/yeniden bağlanma çalışsın; hayalet aktif kayıt oluşmasın.
- Hata ayrıntısında neden ve gerçek hedef bulunsun; kullanıcıya nedene uygun
  kısa çözüm göster. Her SDK hatasına yalnız “disk/izin” demeyi bırak.
- Testlerin kullanıcı ayarı/identity/veri kökünü değiştirmediğini öncesi-sonrası
  hash veya eşdeğer kontrolle doğrula. UI kabul betikleri de bu izolasyona dahil.

Kabul: yeni projede ve mevcut projede doğru hedef; başarısız başlangıçta
arayüz/önizleme kurtarılabilir; tekrar deneme; kontrollü uzun/erişilemez yol
senaryosu; testlerden sonra gerçek ayarlar değişmemiş. Donanımlı kayıt
denenmediyse mock başarısını canlı başarı diye raporlama.

## C-02 — 10,6 saniye sonrası iskelet kaybını gerçek kayıtta araştır

Salt okunur ön bulgular:

- `job.json`: `state=partial`, `published=true`, `frames_processed=1473`.
- Coverage: capture 1475, SVO başlığında 1474, okunan kaynak 1473, eşleşen
  1473, eşleşmeyen 2. Beş issue: `capture_frames_unmatched`,
  `capture_timestamp_duplicated`, `source_frame_count_mismatch`,
  `source_timestamp_gap`, `subject_anchor_before_recording`.
- `arrays/subject_present.npy`: 1473 karede yalnız 622 true; son true indeks
  623. **Sıfır tabanlı indeks 624'ten itibaren** kalan eklem dizisinde hiçbir
  sonlu değer yok. Başlangıca göre 10,600615 saniye.
- `features.json` subject association: locked 622, lost 4, ambiguous 847;
  yeniden ilişkilendirme 0. Olaylarda `same_id_evidence_conflict`,
  `frame_index=626`. Bu olay indeksini dizi indeksiyle körlemesine eşitleme;
  capture/source/processed eşlemesini `source_map.jsonl` üzerinden çöz.
- Son işlenmiş timestamp ve source-position dizilerinde geriye gidiş sayısı
  0. Bu, bütün eşleme hattının doğru olduğunu tek başına kanıtlamaz.
- `subject_status=associated` fakat son association state `ambiguous`;
  kaydın bir kez seçilmiş olması bütün karelerin güvenli eşlendiği anlamına gelmez.

Şunları birbirinden ayır: SDK hiç iskelet bulmadı mı, başka tracker ID üretti
mi, uygulama bulunan adayı güvenlik kuralıyla reddetti mi, yoksa kaynak/proxy
eşlemesi mi yanlış? Sadece renderer'ı değiştirerek boş veriyi görünür yapma.

Öncelikle 9–12 saniye çevresini ve ardından sonuna kadar adayı incele:
tracker ID, aday sayısı, güven, tracking state, konum/ölçü değişimi, timestamp,
anchor ve subject-lock kararı. Aynı kimlikte kanıt çatışması ne tetikledi,
tek geçici aykırılık kalıcı ambiguous kilidine mi dönüştü, yeniden kazanım
koşulları neden çalışmadı? Görselde ayna yansıması mevcut; yansıma/ikinci aday
etkisini de araştır fakat gerçek neden olduğunu varsayma.

Ham capture sırası, SVO sırası, duplicate timestamp tie-break, successful-grab
ordinal, source map, proxy kareleri ve eklem dizileri arasındaki birebir
ilişkiyi doğrula. Aynı timestamp'e sahip farklı kareleri tekleştirme; yalnız
zaman damgasına göre yeniden sıralayarak kaynak düzenini bozma.

Düzeltme aynı kişinin güvenli devamını/yeniden kazanımını sağlamalı. Subject
lock'u tamamen kapatmak, ilk görülen bedene atlamak, farklı kişileri birleştirmek,
NaN doldurmak veya son pozu kopyalamak kabul edilmez. Otomatik çözüm gerçekten
belirsizse doğru kareye yeniden kişi anchor'ı koyma ve aynı ham veriden yeni
sürüm üretme yolu sun. Gerçek beden ile aynadaki/adayı ayıran kanıtı raporla.

Kabul: sorunlu gerçek take'te önce/sonra seçilmiş kişi kapsaması, çatışma
olayları ve 8,12 / 10,6 civarı / 11,25 saniye / son bölüm RGB-iskelet
eşzamanlı görüntüler. Sayısal olarak aralıklar ve eksik kare sayıları.
Ham veride gerçek algılama yoksa bunu dürüstçe ayır; görünürde düzelmiş
sonuç üretme. ID değişimi, kısa kayıp, aynı ID çatışması, iki kişi/yansıma,
duplicate timestamp için anlamlı regresyonlar ekle.

## C-03 — Kaynak kapsamı ile kişi kapsamını ayrı anlat

Şu an `studio/services/library.py::VersionRow.coverage_verified` yalnız
`not self.issues` döndürüyor; bu yüzden bilgi niteliğindeki anchor bulgusu
bile aynı genel “kaynak kapsamı doğrulanamadı” uyarısına katılabiliyor.
`library.py` viewmodel etiketleme açarken bu karara göre uyarı çıkarıyor.

Kaynak kare bütünlüğü/eşleşmesi, zaman kalitesi, kişi ilişkilendirme kapsamı,
proxy kullanılabilirliği ve bilgilendirme notlarını ayrı değerlendir.
Gerekirse issue şiddeti/kategorisi açık bir sözleşme olsun; yalnız uyarıyı
gizleyerek veya tüm issue'ları zararsız sayarak çözme. Bu kayıtta 2 eşleşmeyen
kare gerçekten var, ayrıca çok daha büyük kişi kaybı var.

Kullanıcı mesajında somut sayı ve etkisi bulunsun: örneğin kaynak 1473/1475
eşleşti, kişi 622/1473 karede güvenle izlendi. İşleme bitti ile veri eksiksiz
ayrı durumlar. “Yeniden işle” ancak neyi düzeltebileceği belirtilerek sunulsun;
hamda olmayan kareyi geri getireceğini vaat etme. Mevcut export veri
doğruluğu kapılarını koru, yeni sınıflandırmayla yanlış yeşil hazır verme.

## C-04 — İskelet sağındaki yardımcı paneli geri getir

Kullanıcının gerçek ekranında RGB ve iskelet var, fakat sağdaki kamera/özet/
kişi paneli ve ikonları yok. Kodda panel hâlâ oluşturuluyor;
`ReviewPage.set_inspector_visible` → `side_tabs.setVisible` ve shell'in
inspector aç/kapat zinciri ilk inceleme noktası. Görünürlük tercihi, yaşam
döngüsü, ilk yükleme, yeniden açma ve geometriyi birlikte araştır.

Bu panel etiketlemenin kalıcı parçasıdır. Varsayılan görünür olsun; genel
isteğe bağlı inspector düğmesi veya başka sayfanın tercihi bunu sessizce
gizlemesin. Kaydedilmiş gizli durumdan güvenli göçü de ele al. Üstte RGB,
kare iskelet ve panel bitişik/hizalı dursun; boş şeritler panelin yerini almasın.
Önceki alt hareket/hata editörünü bozma. Sağ panelde scroll tekrar getirme.

Presetleri sadeleştir: ana görünümde **Ön, Sağ, Sol, Üst, 45°** yeterli;
arka/kayıt yönü gibi seyrek açı gerekiyorsa ikincil mini menü. Merkezle/
sığdır/reset anlaşılır ve kompakt kalsın. Önceki anatomik yön ve yumuşak
en kısa yol animasyonu düzeltmelerini koru. Etiket özeti ve kişi sekmesi
içeriklerini de geri getir; yalnız kamera butonlarını göstererek kapatma.

Kabul: ilk açılış, sürüm yükleme, sekme değişimi ve uygulama yeniden açılışında
gerçek görünür panel; bütün ikonlar/temel eylemler erişilebilir; kaydırma yok.

## C-05 — Başlangıç, proje ve katılımcı kapıları

Her yeni uygulama açılışında, gerekiyorsa oturum açıldıktan sonra, **Projeler**
sekmesi gösterilsin. Son kullanılan sekmeyi geri yükleme. Proje otomatik
açılıp kullanıcının bu oturumda proje seçmesi şartını atlatmasın; eski son
proje tercihi yalnız öneri olabilir.

- Kullanıcı proje seçmeden diğer ana sayfa sekmelerini kullanamasın.
- Proje seçildikten sonra katılımcı seçmeden işleme, işlenen videolar,
  etiketleme, veri seti, dışa aktarım ve ayarlar kullanılabilir; yalnız
  yakalama için ayrıca **proje katılımcısı** seçili olmalı.
- Katılımcı seçmeden Yakalama'ya gitmeyi denerse kısa tek uyarı:
  “Kayıt için önce bir katılımcı seçin.” Ardından Projeler'e yönlendir ve
  katılımcı seçimini kolayca erişilebilir bırak.
- Yeni kayıt başlatırken otomatik katılımcı oluşturma davranışını bu akışta
  kaldır. Katılımcı seçimi/oluşturma açık kullanıcı eylemi olsun.
- Proje katılımcısı ile kamera görüntüsünde seçilen beden aynı kavram değildir;
  ikisini ayrı doğrula. Proje değişince eski projenin katılımcısı taşınmasın.
- Kapıyı yalnız düğme disable ederek uygulama: klavye, menü, bildirim eylemi,
  programatik navigasyon ve kayıt başlatma komutları da tutarlı denetlensin.
  Proje seçimi ve oturum kapatma gibi kurtarma yolları erişilebilir kalsın.

## C-06 — Yakalama görünümünü sabitle, görüntü alanını verimli kullan

Sağdaki çekim paneli kadraj uyarısı değiştikçe yeniden boyutlanıp içerikleri
yerinden oynatmayacak. Hedef/katılımcı, kişi seçimi, kayıt modu, çekim araçları
ve durum için kararlı bölmeler ayır. Durum bölgesinin yüksekliğini öngörülen
kısa mesajlara göre baştan ayır; içerik değişsin, altındaki denetimler zıplamasın.
Uzun açıklamalar ayrıntı mini penceresine gitsin. Kayıt sırasında panelin bir
anda scroll gerektirmesi veya kontrol kırpması kabul edilmez.

RGB container'ı kaynağın gerçek oranına göre düzenle. Görüntüyü büyütüp
kırparak veya esneterek siyah alanı gizleme. Önerilen alan kullanımı: ana RGB
görünümünün oranlı genişliğini hesapla, artan yatay alanı sağ panelde daha
okunur sabit bilgi ve gerektiğinde iki sütun çekim denetimlerine ayır.
Sağ panelin okunur üst genişlik sınırı olsun; çok geniş gereksiz kutu üretme.
Mevcut içerikle yer kazan, yeni pahalı analiz/grafik ekleme. En/boy oranı,
katılımcıya tıklama koordinatları ve overlay eşlemesi beraber doğru kalmalı.

Canlı RGB üzerinde “kadrajda kimse yok”, “kişiye tıklayın” gibi büyük merkez
metinlerini kaldır. Kişi seçimi gerektiğinde **tek popup/toast** kalsın;
aynı uyarı hem RGB'nin üzerinde hem popup olarak tekrarlanmasın. Frame başına
bildirim üretme; durum geçişine göre deduplicate et. Kamera bağlantısızken
boş görüntü placeholder'ı ve kritik kayıt durumu gibi farklı amaçlı göstergeleri
bu talebin dışında tut; kullanılabilirliği azaltma.

Kabul: kimse yok → kişi var → kişi seçildi → kadraj dar/tamam → kayıt →
kayıt hatası/durdurma geçişlerinde sabit kontrol geometrisi, scroll yok,
görüntüyü örten yönlendirme metni yok; tek anlamlı kişi seçimi bildirimi.

## C-07 — Bildirim kartları ve buton kırpılması

Özellikle `input-06.png` içindeki “Etiketlemeyi aç” butonu ve
`input-03.png` ayrıntı metni taşması yeniden üretilecek. Türkçe metin,
font ölçüsü, padding, ikon, DPI ve çok eylemli kart için gerçek boyut hesabı
yap. Butonların yazı alanına göre minimum genişliği olsun; sığmayan eylemleri
ikinci satıra veya uygun ikincil menüye yerleştir. Harf kesme, fontu aşırı
küçültme, butonları üst üste bindirme yok. Ayrıntılar gerekiyorsa ayrı
pencerede tam okunabilsin; karttan kesilmiş teknik metin sarkmasın.

Birincil eylem, Ayrıntılar ve Kapat erişilebilir kalsın. Yığılmış bildirimler
alt gezinmeyi kapatmasın; mevcut doğru layer davranışını koru. Kısa/uzun
mesaj, 0/1/çok eylem ve tam ekran farklı DPI'da screenshot + gerçek tıklama
ile doğrula. İşlem tamamlandı bildiriminin hedef sürümü doğru açtığını da dene.

## Doğrulama, Obsidian ve teslim

Plan: `knowledge/plans/capture-tracking-gui-repair-implementation.md`.
Rapor: `knowledge/reports/capture-tracking-gui-repair-validation.md`.
Her C-01…C-07 için belirti → kök neden → düzeltme → gerçekten çalıştırılan
kontrol → kanıt/screenshot → kalan sınır tablosu tut. Mevcut notları silme;
çelişkili tamamlanma iddiasını gerekçesiyle superseded yap. Kaynak sicilini
sonda bir kez güncelle.

UI kabulünü Python/Qt üzerinden gerçek Windows fontları ve GL ile tam ekranda
yapabilirsin; kullanıcı masaüstünü uzun fare turlarıyla meşgul etme. Gerçek
giriş olaylarıyla doğrula, yalnız private metoda çağrı yapıp etkileşimi
doğrulandı sayma. Screenshot'ları açıp incele. Gerçek kişi görüntülerini ham
veriyle birlikte wiki'ye gömme; yerel kanıt bağlantısı kullan.

SDK kayıt ve gerçek take yeniden işleme kontrollerini sentetik testlerden
ayrı raporla. Yanlış kişiye geçmeme, NaN, atomik yazım, ham veri değişmezliği,
undo/autosave ve export doğruluğu korunsun. Sonuç alınamayan gerçek kayıt
kusurunu yalnız GUI iyileştirmesiyle kapatma. Nihai raporda hem düzeltilen
işler hem gerçek verinin kurtarılabilen/kurtarılamayan kısmı açık olsun.
