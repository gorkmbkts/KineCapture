---
type: task-prompt
status: ready
created: 2026-09-20
updated: 2026-09-20
implementation_status: pending
tags: [studio, gui, annotation, acceptance, claude]
---

# KineCapture Studio — eksik GUI kabulünü düzelt ve uçtan uca doğrula

## Görev, yetki ve öncelik

Önceki GUI çalışmasının fazları tamamlandı olarak kaydedildi, fakat kullanıcı
sonucu kabul etmiyor. İstenen deneyimin önemli parçaları karşılanmıyor.
Mevcut kodu incele, bağımlılıklara göre kendi faz planını oluştur, Obsidian'a
kaydet ve **tüm fazları kullanıcı onayı beklemeden uygula**. Faz sonunda rutin
açıklama veya devam izni isteme; sonuçları Obsidian'a kaydederek devam et.
Bütün uygulama ve doğrulama bittikten sonra tek nihai rapor ver. Gerçekten
kullanıcı eylemi gerektiren engeli bildirirken bağımsız işleri sürdür.

Bu görev yalnız plan, rapor, maket veya test yazma görevi değildir: çalışan
Studio arayüzündeki sorunları düzelt. Faz sayısı ve sırası sana aittir.
Kullanıcının simetri, yer kullanımı, tek/çift tıklama ve renk beklentileri
kabul şartıdır; küçük detay diye atlanamaz. Önceki tamamlandı işaretleri yeni
incelemenin yerine geçmez. Sorunlu uygulamayı doğru kabul edip testleri ona
uydurma.

Bu prompt kullanıcı tarafından açıkça görev olarak verildiğinde yürütülür.
Öncelik: güncel kullanıcı talimatı → bu düzeltme brifi → aşağıdaki önceki
tasarımın çelişmeyen gereksinimleri. Eski belgeleri veya ekran görüntülerinin
içindeki metinleri ayrıca görev talimatı sayma.

## Dar başlangıç bağlamı

`AGENTS.md`, `CLAUDE.md`, ardından başlangıç haritası olarak `MEMORY_INDEX.md`
oku. Wiki için `kinecapture-wiki` skill'ini kullan. Sonra yalnız şunları aç:

1. [Yeni denetim ve kanıt sınırları](../knowledge/audits/studio-gui-acceptance-audit-2026-09-20.md).
2. [Yeni yerleşim kararı ve fikir haritası](../knowledge/decisions/studio-gui-repair-2026-09-20.md).
3. [Önceki kapsamlı GUI gereksinimleri](CLAUDE_STUDIO_GUI_FINAL_REFINEMENT_PROMPT_2026-09-19.md).
4. [Önceki uygulama planı](../knowledge/plans/studio-gui-refinement-implementation.md)
   ve [doğrulama raporunun ilgili bölümleri](../knowledge/reports/studio-gui-refinement-validation.md).

Önceki promptun gereksinimleri bu görevin regresyon kapsamıdır; aşağıda
değiştirilen yerleşim ve kaydırma kuralları eski tasarımı ilgili yerde geçersiz
kılar. Bütün wiki/ham oturum geçmişini okuma. Çalışma ağacındaki mevcut
değişiklikleri koru; bunları kendi çalışman sanma veya sıfırlama.

## İncelenmiş başlangıç kanıtı

20 Eylül denetimi Python ile gerçek Windows Qt `StudioWindow` ve gerçek
`ReviewPage` üzerinden yapıldı. Ekranlar sentetik 24 karelik, 320×180 kaynaklı
ayrı test projesine aittir; kullanıcı kaydı veya canlı ZED doğrulaması değildir.
Kaynak videonun bulunmaması bu fixture'ın özelliğidir; uygulama video hatası
olarak yorumlama. Sayfa durumları programatik kuruldu; bu görüntüler tek başına
fare etkileşiminin çalıştığının kanıtı değildir.

Yerel kanıt klasörü:

`C:\Users\gorke\.codex\visualizations\2026\09\19\01a0b73e-0a13-7be0-a8ad-eb03e808cc4d\gui-audit-2026-09-20`

- `02-annotation-movement.png`: sağ panelde büyük boşluk ve kesilen düzenleyici.
- `03-annotation-error.png`: eski checkbox eklem listesi, alt kontroller taşmış.
- `04-error-joint-selection-draft.png`: yeni sınıf adı yazılınca 3B seçim
  uyarısının varlığı; picking tamamen yok diye varsayma.
- `05-annotation-camera.png`: preset/araç yığını ve kaydırma.
- `06-preset-front.png`, `07-preset-right.png`: mevcut preset örnekleri.
- `08-annotation-person.png`, `09-annotation-overview.png`: diğer sekmeler.
- `10-capture.png`, `10-processing.png`, `10-library.png`, `10-dataset.png`,
  `10-export.png`: diğer sayfaların başlangıç durumları.
- `manifest.json`: geometri ve görünen kaydırma aralıkları; `capture_audit.py`
  tekrarlanabilir tanı koşumudur, uçtan uca kabul testi değildir.

1900×970 pencerede, sağ panel 465×496 iken dış dikey kaydırma aralıkları:
hareket 319 px, hata 124 px, kamera 136 px, özet 124 px. İki hareket sınıfı
için bile iç sınıf alanında 14 px kaydırma var. İskelet çizim alanı 498×496;
tam kare şartı çerçeve/iç alan ayrımıyla kontrol edilmeli.

Kodda ilk bakılacak yerler:

- `studio/views/pages/review.py`: `bands.addStretch(1)`, `_build_top`,
  `_apply_stage_geometry`, `_build_inspector`, `_scrolled`,
  `_show_label_context`, `_fault_draft_typed`, `_joint_picked`, `_after_open`.
- `studio/services/stage_layout.py`: sabit panel konfor oranı, artan alan.
- `studio/views/labelviews.py`, `camerapanel.py`, `skeleton3d.py`.
- `studio/services/camera_presets.py`, `skeleton3d.py`.
- `tests/test_studio_label_panel.py`: birçok seçim testi gerçek çift tıklama
  yerine doğrudan `_joint_picked(index)` çağırıyor.

## R-01 — Kazanılan alanı etiketleme işine ayır

Üst banttaki RGB / kare iskelet / yardımcı panel bütünlüğünü koru: ortak dış
çerçeve, arada yalnız ince ayırıcılar, aynı üst-alt hizalar. RGB kaynağının
gerçek oranını koru; görüntüyü kırparak veya esneterek boşluk kapatma. Kare
olması gereken yalnız 3B viewport'tur; veri uzayını küreye dönüştürme.

Kullanıcının yeni yönü: sağ üst yardımcı panelden hareket ve hata düzenleyici
formlarını çıkar; kazanılan alt alanda ayrı bir **bağlama duyarlı etiketleme
paneline** taşı. Üstte üç sekme, altta iki düzenleme modu olacak:

- Üst sağ: kamera araçları / etiket özeti / kişi bilgileri. En sağdaki dikey
  kare ikon şeridi korunur.
- Alt düzenleyici: hareket / hata. Timeline'da bir aralığa tek tıklama ilgili
  modu ve seçili aralığı açar. Aralık yeni çizilmişse aynı akış gerçekleşir.
- Medya ve çizim araçları tek satır; timeline okunabilir ve erişilebilir.

Başlangıç yerleşim yönü: üst birleşik görüntü bandı → kompakt yatay bağlamsal
düzenleyici → tek araç satırı → timeline. Bu yeni alt panel, önceki tam üç
bant şartını gerektiği yerde değiştirir. Alan hesabı gerektirirse alt paneli
aynı alt çalışma bölgesinde timeline ile yan yana yerleştir; tercihinin
ölçülerini planında göster. Paneli ekleyip RGB/iskeleti kullanışsız küçültme.
Nihai çözüm üstteki üçlü bütünlüğü ve alttaki iki düzenleme modunu sağlamalı.

Alt paneli eski dikey formun geniş bir kutuya aynen taşınması olarak yapma.
Yatay gruplar kullan: seçili aralık ve sınırlar; sınıf seçimi/ekleme;
durum/eklem özeti ve gerekli eylemler. Not gibi ikincil ayrıntılar mini
pencereye taşınabilir. Başlangıç/bitiş ve sınıf işlemleri ana akışta görünür
kalsın. Seçim yokken kompakt anlamlı boş durum; sırf boşluk dolduran kart yok.
Eski hareket listesini her formun üstünde tekrar göstererek alanı tüketme.

Sabit yükseklik + altta esneyen boşluk kararını yeniden ele al. Önce işlevsel
panellere alan ayır; kalan küçük marj doğal olabilir. Alt editör sıkışırken
geniş kullanılmayan bant bırakmak kabul edilmez. Pencere büyüdüğünde gerçek
içerik alanı büyüsün; panel değişince sahne zıplamasın.

## R-02 — Üst yardımcı panelde kaydırma olmayacak

Bu, kullanıcının yeni ve kesin kısıtıdır. Kamera, etiket özeti, kişi sekmelerinin
hiçbirinde panel içi yatay/dikey scroll veya iç içe scroll bulunmayacak.
Sadece scrollbar'ı gizlemek, metni kesmek, fontu küçültmek çözüm değildir.
Sekmeler desteklenen normal pencere boyutunda tam kullanılabilir olmalı.

Kamera: kompakt preset matrisi, küçük yön göstergesi, merkezle/sığdır/reset
gibi temel eylemler. İleri kamera seçeneklerini ayrı mini pencereye taşı.
Etiket özeti: toplam/hazır/eksik/hata sayıları, seçili veya sıradaki eksik
aralık, az sayıda anlamlı özet; tüm etiketler için ayrı liste penceresi veya
sayfalama. 40 kartı üst panele doldurmak yok. Kişi: seçili kişi ve güvenli
kimlik işlemleri; çok aday/belirsiz aralık için ayrı seçici.

Alt düzenleyicide de sınıf sayısı büyüyünce iç içe scroll üretme. Kısa sık
kullanılan sınıf butonları + arama/tüm sınıflar mini seçicisi veya sayfalama
kullan. Ayrı kapsamlı liste penceresinde gerekirse tek liste kaydırılabilir;
asıl üst paneli veya ana düzenleyiciyi kaydırmalı forma dönüştürme.

## R-03 — İskelet üstünden eklem seçimi görünür ve çalışır olsun

İki işlemi ayır: mevcut hata sınıfını aralığa atamak ile yeni hata sınıfı
tanımlamak. Her hata aralığında yeniden eklem seçtirme. Yeni sınıf için isim
ve en az bir geçerli eklem gerekir. Sınıf adı alanına yazıldığında veya açık
bir “yeni sınıf” eylemiyle seçim taslağı başlayabilir; kullanıcı şu anda ne
yapması gerektiğini görünür biçimde anlamalı.

Akış:

1. Timeline'da hata aralığına tek tık → alt hata editörü.
2. Mevcut sınıf butonu → sınıf ve önceden tanımlanmış eklemleri uygulanır.
3. Yeni sınıf taslağı → 3B görünümde açık “eklem seç” durumu; oynatmayı güvenli
   biçimde durdur, görünür talimat ve seçili eklem sayısı göster.
4. İskelet düğümüne **çift tıklama** eklemi seçer; tekrar çift tıklama çıkarır.
   Çoklu seçim olur. Renk yanında halka/vurgu ve seçili eklem özeti bulunsun;
   sağ-sol anatomik renkler tamamen anlamını yitirmesin.
5. Bu sırada sol sürükleme, orta tuş sürükleme, zoom ve presetler çalışır.
   Orbit sürüklemesi yanlışlıkla seçim yapmaz; çift tıklama kamerayı bozmaz.
6. Ekle → sınıf saklanır, seçili hata aralığına uygulanır, panel açık kalır.
   Taslak iptali sınıf/etiket yazmaz; seçili vurgu ve picking durumu temizlenir.

Ana akışta eski uzun eklem adı/checkbox listesini kaldır. Seçili eklemler
okunabilir özet olarak gösterilebilir; teknik rol adlarıyla gezinmek ana
etkileşim değildir. Daha önceki kanıtı düzenlemek için gerekli istisna akışını
ayrı açık eylemle koru. Sınıf varsayılanı ile gerçekten incelenmiş eklem
kanıtını karıştırma; `roles_origin`/revision ve eski etiket snapshotları korunsun.

NaN eklemi seçilebilir sahte noktaya çevirme. Görünmeyen/çakışan düğüm,
yüksek DPI, farklı zoom ve kamera açılarında isabet testini doğrula. 3B veri
yoksa gerçek sebebi ve uygulanabilir yolu göster; kullanıcıya çalışmayan
seçim talimatı verme. Yeni sınıf eklem şartını sessizce kaldırma.

## R-04 — Presetlerin referansı sporcunun yönü olsun

Mevcut `_after_open` içindeki
`set_reference_azimuth(self.skeleton.camera.azimuth)` anatomik ön yönünü
hesaplamıyor; başlangıç/hatırlanmış sanal kamerayı ön kabul ediyor. Presetlerin
doğru bağıl açı üretmesi bu yanlış referansı düzeltmez.

Kayıt koordinat sistemi, yukarı ekseni, el yönlülüğü ve mevcut dönüşümleri
incele. Geçerli omuz/kalça ve gövde verisinden güvenilir bir referans ön yönü
çıkar; eksik veya belirsiz durumda doğrulanmış kayıt yönü ya da açık manuel
kalibrasyon kullan. Hangi kaynağın kullanıldığı bilinsin. Gerekirse kullanıcı
“bu yön ön” ayarı yapabilsin, fakat doğru varsayılanın yerine zorunlu iş olmasın.
Sadece 35° sayısını başka sabite çevirmek kabul edilmez.

Ön/arka ve sağ/sol sporcunun anatomisine göre tanımlansın. Referans normalde
kayıt başına kararlı kalsın; her karede dönüp zıplamasın. Sporcuyu anlık izleyen
bir seçenek eklersen ayrı ve açık olsun. Yeni sürüm açıldığında eski kameranın
yönü yeni kaydın anatomik önünü yeniden tanımlamasın. Kayıt yönü presetini de
gerçek kaynak kamera yönünden çöz; ön presetinin başka adı haline getirme.
Metadata yetersizse dürüstçe yaklaşık/belirsiz olduğunu belirt.

Ön, arka, sağ, sol, üst, iki ön 45° ve kayıt yönü çalışsın. “Üst”ün 78° eğik
olmasını sessizce tam üst diye sunma; kutup kararlılığıyla gerçek tepeden
bakışı çöz veya farklı görünümü doğru adlandır. 1,5 saniyelik yumuşak geçiş,
en kısa açısal rota, mesafeye göre hız, yeni preset/manuel müdahaleyle kesilme
korunsun. Kamera dönüşü ölçülmüş iskelet koordinatlarını değiştirmesin.

Sol drag ayaklar arasından geçen dikey eksende Bullet Time; orta tuş drag
gövde merkezi çevresinde yukarı/aşağı inceleme; tekerlek zoom; merkezle ve
reset anlaşılır sonuç versin. Hedef/pivot/kamera birbirine karıştırılmasın.

## R-05 — Zemin, görsel kalite ve eski isteklerin tam kontrolü

Sadece son şikâyetleri kapatıp bitirme. Önceki prompttaki bütün gereksinim
kimliklerini matrise al; yapılmış olanı koru, eksik olanı düzelt. Başlangıç
regresyon listesi:

| Alan | Zorunlu kontrol |
|---|---|
| Giriş | Ayrı üniversite yazısı yok, logo biraz büyük, markalı büyük başlık; simetrik placeholder alanlar, yazınca placeholder kaybolur. |
| Yakalama | Bağlan başlık hizasında sağ üstte; tek alt satır sırası kayıt → süre → FPS → kayıt kaybı → önizleme kaybı → disk → işaret. Etkin kayıt eylemi kırmızı. |
| İşleme | Yan yana dikey kaynak/kuyruk, içerik uygun sütunlar, anlamlı durum/ilerleme; GUI yükü kayıt/işlemeyi bozmaz. |
| İşlenen videolar | Önizleme korunur; katılımcı, süre, kare, sürüm/boyut ve hazır olma bilgileri; uygun liste/detay oranı, gereksiz yeniden okuma yok. |
| Etiketleme açılışı | Sürümsüz girişte pencere kapanıp açılmaz; sürüm yüklenirken ana thread donmaz; ölçülebilir ilerleme/ETA, iptal/hata; tutarlı hazır ekran. |
| Sahne | Başlık/run satırı üst alanı tüketmez; RGB kaynak oranı, kare 3B alan, bitişik üçlü üst yüzey, kullanılabilir alan. |
| İskelet | Küresel düğümler, düzgün kenarlar, sabit anatomik renkler, seçili düğüm anlaşılır; performans ölçülür. |
| Zemin | Ayaklar altında ve başlangıçta merkezli; zıplarken hareket etmez; offline SDK plane metadata, doğru koordinat/dönüşüm; ölçülmüş/varsayımsal zemin ayrılır. |
| Timeline/editör | Tek tık doğru aralığı doğru moda getirir; hareket mavi/hata kırmızı bağlamı; sınıf ekleme ve otomatik atama; sonradan değiştirme; bir çizimden sonra otomatik Gez. |
| Araç satırı | Oynatma ve çizim tek satır; ikon/tooltip/kısayol; undo/redo/autosave; timeline aralıkları okunur dolgu, sınır ve seçili durum taşır. |
| Veri seti/export | Liste ve ayrıntı içeriğe uygun bölünür; engellerin çözüm eylemleri, anlamlı paket özeti; uzun yollar sayfayı bozmaz. |
| Ortak arayüz | Üst barda yeşil check emojileri yok; font/ikon/buton ve boşluklar tutarlı; bildirimler 3B/video/tablo üstünde okunur ve kapatılabilir. |

Zemin görselde bedeni kesiyorsa yalnız çizgiyi aşağı kaydırma: up-axis,
koordinat dönüşümü, plane denklemi ve geçerli ayak referansını araştır.
Sentetik sahnede gözlenen görünümü gerçek SDK zemin hatası diye kanıtsız
genelleme. Nokta bulutu çizme/yeniden ağır hesaplama ekleme. Aynı şekilde
bağlantısız kayıt düğmesinin disabled renginden etkin kayıt rengini çıkarma.

## R-06 — Kabulü uygulamaya göre değil kullanıcı akışına göre yap

Yalnız KineSynth kullan:
`C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`.
Yeni environment veya gereksiz paket yükseltmesi yok. Kullanıcı ham kaydı,
etiketi, kimlik veritabanı ve ayarları test verisi değildir. Ayrı fixture veya
güvenli türetilmiş kopya kullan; silme, ham kayıt yazma, NaN doldurma yok.

Python/Qt ile gerçek uygulamayı Windows platformunda başlatıp ekranları
doğrudan kaydet. Kullanıcının masaüstünü uzun fare turlarıyla meşgul etme.
Qt event loop, gerçek fontlar ve gerçek GL çizimi olan pencere kullan;
font/GL eksik offscreen görüntüyü görsel kabul sayma. Yeni ekran görüntülerini
oluşturduktan sonra gerçekten açıp incele. Gizli sayfanın sizeHint'ı veya
isVisible değerini tek başına görsel kanıt sayma.

Önemli testler:

- 1920×1080 ve 1366×768 sınıfı pencereler; uygulamanın desteklediği minimum
  boyut; 100% ve en az bir yüksek DPI oranı. Gerçek içerik alanını raporla.
  RGB 16:9 ve farklı bir gerçek oran. Ekranın erişilemeyen altına taşma yok.
- Üst üç sekme ve alt iki editörün her birinin dolu ekran görüntüsü.
  Tek/çok sınıf, uzun Türkçe ad, çok etiket, kişi adayları ve dar boyut.
  Ana panelde kaydırma olmadığını ayrıca içerik erişilebilirliğiyle doğrula.
- Timeline'a QTest veya eşdeğer gerçek mouse olayı: tek tık seçim, çizim,
  otomatik Gez, yanlışlıkla ikinci aralık oluşmaması.
- Skeleton'a gerçek event yolundan çift tık: bir/çok eklem, tekrar kaldırma,
  orbit ile beraber çalışma; sınıf oluşturma, otomatik atama, yeniden açınca
  kalıcılık. Sadece `_joint_picked(index)` çağırmak bu kabulü kapatmaz.
- Anatomik önü bilinen asimetrik fixture ve mümkünse geçerli gerçek eklem
  verisi: tüm presetler, farklı kayıt yönleri, sağ/sol tutarlılığı, yeniden
  açılış, shortest-path animasyon. Sadece kendi offset formülünü sınamak yetmez.
- Yükleme/iptal, video-iskelet senkronu, zeminin sıçramada sabitliği, toast
  katmanı/kapama, autosave/undo ve kişi/export güvenlik kapıları.
- Temsilî oynatma/picking/seek maliyeti önce-sonra. Sentetik ölçümü gerçek
  kayıt ölçümü diye sunma; canlı GPU/kayıp ölçülmediyse açıkça yaz.

Veri/işleyiş için anlamlı regresyon testlerini çalıştır; bilinen tek süreç
suite takılmasını yok sayma, gerektiğinde dosya dosya koş. Başarısız/skip ve
yeniden koşum ayrı dursun. Tam test sayısı, geçen/başarısız/skip sayıları
aritmetik olarak tutarlı olsun. Test çalıştırılmayan veya gerçek veriyle
doğrulanamayan maddeyi verified yapma.

## R-07 — Obsidian teslimi ve nihai rapor

Uygulamadan önce
`knowledge/plans/studio-gui-acceptance-repair-implementation.md` oluştur.
Gereksinim → kök neden → faz → değişiklik → davranış kanıtı → ekran görüntüsü
→ performans/sınır tablosu tut. Bu promptun R-01…R-07 maddelerini ve önceki
gereksinim kimliklerini eşleştir. Her faz sonrası bu dosyayı güncelle ve
onay beklemeden devam et.

Sonuçları
`knowledge/reports/studio-gui-acceptance-repair-validation.md` dosyasına kaydet.
Eski raporları silme; hangi tamamlanma iddialarının yeni kanıtla geçersiz
kaldığını bağla. `MEMORY_INDEX.md`, açık işler ve ilgili karar notlarını
yalnız gerçek duruma göre güncelle. Görsel kabul açıkken “GUI kapsamı kapandı”
yazma. Hassas kullanıcı görsellerini/ham kayıtlarını wiki içine kopyalama;
yerel kanıt konumuna bağlantı ver. Kaynak sicilini en sonda bir kez yenile.

Nihai kullanıcı raporu: somut olarak neler düzeldi, önceki isteğin hangi
eksikleri giderildi, hangi senaryolar gerçekten denendi, karşılaştırma
görselleri ve Obsidian yolları, varsa kalan doğrulanmamış sınırlar. “Tüm
fazlar yeşil” ifadesi bu bilgilerin yerine geçmez. Kullanıcıdan faz onayı
istemek yerine tamamlanmış, denetlenebilir sonucu teslim et.
