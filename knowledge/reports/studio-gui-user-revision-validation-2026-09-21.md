---
type: report
status: verified
updated: 2026-09-22
tags:
  - studio
  - gui
  - validation
---

# 21 Eylül kullanıcı GUI revizyonu — uygulama ve doğrulama

[Görev promptu](../../promts/CLAUDE_STUDIO_GUI_USER_REVISION_PROMPT_2026-09-21.md) ·
[Kalıcı kararlar](../decisions/studio-gui-user-revision-2026-09-21.md) ·
[Kaynak görseller](../sources/gui-user-feedback-2026-09-21.md)

## Nasıl doğrulandı

`verified`: Uygulama gerçek Windows masaüstünde, **maksimize pencerede** açıldı;
her ekranın ekran görüntüsü alınıp incelendi ve GUI kontrolleri gerçekten
tıklandı. Ölçüm ortamı: 1920×1080 ekran, `devicePixelRatio = 1.0`,
`logicalDpi = 96` (yani **%100 ölçek**), pencere `1920×1009` ve `isMaximized()`
doğru. Farklı DPI/ölçek matrisi çalıştırılmadı; kullanıcı kararı gereği
istenmiyor.

Sürüş betiği gerçek `StudioWindow` nesnesini sandbox bir veri kökünde kurar
(`AppConfig.sandboxed`), sentetik mock kamerayla 60 karelik bir kayıt üretip
işler ve ekranları gezer. Kullanıcının gerçek projesi, kaydı, etiketi ve
tercih dosyası okunmadı ve yazılmadı.

`observed`: Betik ve ekran görüntüleri oturuma özgü geçici dizinde
(`…\Temp\claude\…\scratchpad\shots\`); wiki'ye kopyalanmadı.

## Kabul tablosu

| Kontrol | Sonuç | Kanıt |
|---|---|---|
| Pencere | ✅ | `CustomizeWindowHint + WindowTitleHint + WindowCloseButtonHint`; küçültme/büyütme bayrakları yok, kapatma var. `showNormal()` çağrısı yeniden maksimize ile yanıtlanıyor. Kenarlıksız fullscreen değil. |
| Projeler | ✅ | Yenile artık `quiet` değil; dört düğme aynı yükseklik/yüzey/kenarlık ailesinde. Arama alanında büyüteç ikonu var, yer tutucu tam okunuyor (263 px alan, 182 px metin). |
| Yakalama geometrisi | ✅ | Bağlantı öncesi/sonrası/kesilince önizleme dikdörtgeni **birebir aynı**: `QRect(35, 0, 1326, 746)`. Konsol paneli de aynı. Kutu artık gelen kareden değil sayfadan çözülüyor; görüntü kutunun içinde letterbox ediliyor. |
| Yakalama içerikleri | ✅ | Sağ container'da DURUM bloğu, "etkin/kamera bağlı değil" rozeti ve kare bildirimi yok (dört blok kaldı, hepsi kontrol). RGB üzerinde kadraj başlığı, geçmiş özeti ve "seçilen kişi" yazısı çizilmiyor. Bilgi **Araçlar › Yakalama Durumu** penceresinde. |
| Kişi seçimi | ✅ | Seçim çerçevesi yazısız çiziliyor. Kişi seçmeden Kayda başla: kayıt başlamıyor (`is_recording` False) ve uyarı kartı her basışta yeniden çıkıyor (iki basış → iki mesaj, ekranda `×2`). |
| Kayıt satırı | ✅ | Ölçülen sıra: `record → connect → elapsed → acquisition → recording_loss → preview_loss → disk → marker`. Bağlıyken düğme yeşil (`kcConnected="connected"`) ve metni "Bağlantıyı kes". |
| İşleme yerleşimi | ✅ | İki ana tablo aynı üst ve alt sınırda: her ikisi de `92..669`. Başlık ve alt eylem bantları karşılıklı eşitleniyor. |
| İş kuyruğu | ✅ | Aşağıdaki bölüme bakın. |
| Sağ panel | ✅ | İkon şeridi 40 → **34 px**; pusula kaldırıldı, "Ön yön omuz çizgisinden ölçüldü" açıklaması korundu; preset/araç düğmeleri panel kenarına yapışmıyor, tek yükseklikte. Bakış ve Sporcu sekmelerinde kaydırma yok. |
| Etiket özeti | ✅ | Tek istisna olarak kaydırılıyor: `0..234` aralık, **çubuk görünmüyor**, son etikete erişiliyor. Kart aralığı sabit (`KcSpacingLg`), satırlar ezilmiyor. |
| Editör ilk açılış | ✅ | Etiketleme açıldığında bant hareket sayfasını gösteriyor (`modes.currentIndex() == 0`); sınıf şeridi canlı, aralık kontrolleri pasif ve "Hareket seçilmedi" yazıyor. Hata aralığı seçilince `fault`, "Harekete dön" ile geri. Bant yüksekliği iki kipte de 116 px. |
| Sınıf kapasitesi | ✅ | 0 sınıf → 0 çip, Diğer sınıflar gizli. 3 sınıf → 3 çip, gizli yok. 14 uzun Türkçe adlı sınıf → 7 çip + 7 gizli, **Diğer sınıflar** görünür. Çipler tek satır, ortadan kısaltma yok, en sağdaki çip 1202 px'te ve holder 1269 px. |
| Son kullanılan | ✅ | İkinci çipe basıldığında o sınıf ilk sıraya geçiyor ve hareket gerçekten o sınıfı taşıyor. Seçiciden seçilen sınıf, seçici kapanınca ilk çip oluyor. |
| Sayılar | ✅ | `FrameSpinBox` genişliği ölçülüyor: beş hanelik değer + stilin kendi bildirdiği ok/çerçeve genişliği. 68 px sabit genişlik kaldırıldı. |
| Koruma | ✅ | Kaldırılması istenmeyen hiçbir kontrol silinmedi; ayrıntı aşağıda. |

## 22 Eylül kullanıcı düzeltmesi

İki nokta ilk turdan sonra kullanıcı tarafından düzeltildi; ikisi de
`verified`, gerçek maksimize pencerede ölçüldü.

**1. Yakalama sağ container'ı önizlemeyle aynı kutu.** İlk turda paneli
içeriğine göre kısaltmıştım; kullanıcı önizlemeyle aynı yükseklikte ve hizalı
olmasını istedi. Panel artık tam olarak önizlemenin yüksekliğinde ve ikisi de
satırın üstüne hizalı: ölçüm `preview QRect(35, 0, 1326, 746)` ·
`console QRect(1377, 0, 460, 746)` — aynı üst, aynı alt, aynı yükseklik.

Kazanılan yer blokların *arasına* dağıtılıyor, içlerine değil: bir blok bir
başlık ve onun adlandırdığı kontrollerdir, onları birbirinden uzaklaştırmak
iyileştirmenin tersi olurdu. Her boşluk en çok `CONSOLE_GAP_MAX = 44` px
alıyor, ayırıcı çizgi boşluğun ortasında duruyor (iki yarım spacer), blok içi
satır aralığı `KcSpacingSm` → `KcSpacingMd` ve TEK BAŞINA ızgarasının dikey
aralığı `KcSpacingMd` → `KcSpacingLg` oldu.

**2. Etiketleme bandında sayı kutuları sınıf metin kutusunun altında.** Band
artık `QGridLayout`: iki satır, üç sütun.

| | sütun 0 | sütun 1 | sütun 2 |
|---|---|---|---|
| satır 0 | yeni sınıf alanı + Ekle | çizgi | kullanımdaki sınıflar |
| satır 1 | Başlangıç / Bitiş | çizgi | seçili aralık ve eylemleri |

Sol blok tek genişlikte: ölçülen `creator x=8 w=290`, `ranges x=8 w=290` —
aynı sol kenar, aynı sağ kenar, alt alta. Genişlik iki satırın kendi
`sizeHint`'lerinden alınıyor (`LEFT_BLOCK_MIN_WIDTH = 290` yalnız taban), sayı
kutuları kalan yeri eşit paylaşıyor (97/96 px). Izgara olduğu için bir satırın
yüksekliği bandın tamamında aynı. Hareket ve hata kipleri aynı bloğu aynı
yerde kullanıyor; bant yüksekliği iki kipte de 116 px.

Bunun için `ClassStrip` ikiye ayrıldı: sınıf **oluşturma** artık
`ClassCreator` (sol blokta), sınıf **seçme** `ClassStrip`'in kendisi (sağda).
Sinyaller ve `new_name` / `add_button` nitelikleri `ClassStrip`'te kaldı, yani
sınıf şeridini süren hiçbir kod değişmedi.

## 22 Eylül ikinci tur — dört kullanıcı bildirimi

`verified`: Hepsi gerçek maksimize pencerede (1920×1080, %100 ölçek) sürüldü.

**1. Gezinme kapısı sessizdi.** Kapalı bir adımın düğmesi `setEnabled(False)`
ile devre dışıydı; Qt devre dışı bir widget'tan `clicked` göndermez, dolayısıyla
katılımcı seçmeden Yakalama'ya basmak **hiçbir şey** yapmıyordu. Ret zaten
vardı ve doğru cümleyi söylüyordu — ateşleme şansı bulamıyordu. Düğme artık
devre dışı değil, `kcGated` özelliğiyle sönük; basış `navigate`'e ulaşıyor ve
kart çıkıyor. Ölçüm: `enabled=True`, `kcGated='true'`, mesaj
`"Kayıt için önce bir katılımcı seçin."`, sayfa değişmiyor. Cümleye
"Katılımcı ekle ile yeni bir tane oluşturun" eklendi.

**2. Üst şeritteki ikinci kayıt kontrolü.** `RecordingStrip` bağlam çubuğuna
artık eklenmiyor (kullanıcı kararı: şeridin tamamı). Widget siliniyor değil,
gizleniyor: kabuk onu hâlâ bağlıyor, kısayol ve metin tek yerde kalıyor.

**3. İş kuyruğu.** Son sütun (`Bulgular`) içeriğine göre boyutlanıyordu ve
içeriği cümlelerdi; tablo container'ı aşıyor, altında yatay kaydırma çubuğu
çıkıyordu. Artık son bölüm kalan genişliği alıyor, yatay kaydırma kapalı,
hücreler `ElideRight` ile "…" ile kısalıyor. Ölçüm: altı sütun **1114 px**,
viewport **1114 px**. Duraklat ve Devam et kaldırıldı; **İptal ve Yeniden
dene** kaldı (İptal'i kullanıcı istedi). Duraklatma üründen gitmedi: canlı
kayıt başlayınca çalışan işler hâlâ duraklatılıp sonra sürdürülüyor
(`pause_for_recording`), yalnız düğme değil.

`verified` — "Yeniden dene çalışıyor mu": gerçek çocuk süreçle sürüldü. İptal
sonrası iş `CANCELLED`, süreç çıkmış; Yeniden dene'den sonra **yeni** bir
süreç `RUNNING`. Testi: `test_retry_really_starts_the_job_again`.

**4. "Ayrıntılar" katlanır profili.** Açıldığında, yüksekliği diğer sütunla
eşitlenmiş bir bandın *içine* teknik liste koyuyordu; altındaki iki düğme
sayfadan taşıyordu. Kaldırıldı; tek satırlık özet kaldı, tam profil onun
ipucunda ve Ayarlar'da.

Ayrıca bu turda bulunan bir hata: ilerleme çubuğu gizliyken bant yüksekliği
ölçüldüğü için, bir iş çalışmaya başlayınca çubuk İptal ve Yeniden dene'nin
**üzerine** çiziliyordu. Bant artık çubuk görünürken ölçülüyor.

## 22 Eylül üçüncü tur — bant eylemleri ve 3B zemin ızgarası

Kararlar: [karar notu 16–17](../decisions/studio-gui-user-revision-2026-09-21.md).

**1. İskelet ızgaranın kenarındaydı.** `verified` — kök neden kodda bulundu ve
kullanıcının kendi sürümünde ölçüldü (855 kare, zemin SDK tarafından
`detected`). `Skeleton3DView.set_references` ızgarayı ayak pivotuna yalnız
**zemin ölçülmemişken** taşıyordu. Ölçülmüş zeminde yükseklik doğruydu ama
merkez kaydın orijininde, yani **kamerada** kalıyordu. Ayaklar merkezden
**3,03 m** uzaktaydı, ızgara her yöne **3,00 m** uzanıyor. Aynı görünümde
açılan sonraki sürüm de bir öncekinin merkezinde kalıyordu (0,70 m ve 0,48 m
sapma ölçüldü). Zemin ölçülmemiş sürümde sapma zaten 0,00 m'ydi. Son
kayıtların hepsinde zemin `detected` olduğu için hata her açılışta görünüyordu.

Kalıcı kural: ölçülmüş zemin yalnız **yüksekliği** verir. **Merkez** her
durumda ayak pivotundan gelir (referans penceresinde iki ayak bileğinin
ortalaması). Izgara hâlâ sürüm açılırken bir kez kuruluyor ve sporcuyu kare
kare izlemiyor; `floor_source` ayrımı değişmedi. Aynı gerçek sürüm, gerçek
maksimize pencerede, onarımdan sonra: merkez–pivot mesafesi **0,00 m**.

`superseded` (kısmen): [faz planındaki](../plans/studio-gui-refinement-implementation.md)
`FLOOR-01` "grid ayak altında + merkezli" doğrulaması yalnız zemin ölçülmemiş
yol için geçerliydi. F12'nin ölçülmüş zemin yolu merkezlemeyi atlıyordu.

**2. Bant eylemleri.** Karar 16 uygulandı. `Hata aralığı ekle` ve onun tek
kullanıcısı olan `ReviewPage._add_error_here` kaldırıldı. Diğer sınıflar
düğmesi (sinyali ve niteliğiyle) `ClassStrip`'te kaldı, ama artık
`ClassCreator` gibi bant tarafından yerleştiriliyor: sınıf satırına değil, alt
satırın eylemleri arasına. Çip satırında yalnız çipler ve ipucu kaldı.
Kapasite hesabı tek geçişe indi ve düğmenin eski yeri çiplere kaldı. Düğme
artık şeridin çocuğu olmadığı için `_set_editing_enabled` onu ayrıca kapatıyor.

`verified` — gerçek maksimize pencerede (istemci alanı 1920×1009, %100
ölçek), korumalı mock sürümüyle seçim yapılarak ölçüldü:

- hareket kipi: `çöp · Diğer sınıflar · Sınıfsızlara uygula`;
- hata kipi: `çöp · Diğer sınıflar · Eklemleri düzenle · Harekete dön · Not…`.

İki kipte de son düğmenin sağ kenarı satırın sağ kenarıyla aynı ve kırpılan
kontrol yok. Gerçek sürüm seçim yapılmadan açıldığında da hareket satırı aynı
sırada göründü.

Hata satırı bir düğme uzayınca bandın en küçük genişliği **1133 px**'e çıktı;
`test_the_bar_alone_fits_the_narrowest_supported_window` sınırı 1129 px.
`joint_origin` notu ("2 eklem · sınıftan"), hareket satırındaki eşdeğeri gibi
`NOTE_MIN_WIDTH` (32 px) tabanına alındı ve en küçük genişlik **1117 px**'e
indi. Hedef boyutta görünür bir değişiklik yok: etiket orada tam cümlesini
alıyor.

## Veri Seti: listeden veri setine

`decision`: Sayfa kayıtları listeliyor, oluşturdukları küme hakkında hiçbir
şey söylemiyordu. Kullanıcı isteği üzerine sağ yarı veri setinin kendi
sayılarına ayrıldı.

- Sol yarı **%66 → %52**: yedi kısa sütun 1900 pikselin üçte ikisini hiç
  gerektirmiyordu. Kendi araç satırı üstünde: arama, filtre, **Etiketlemede
  aç**, **Yenile**. Seçili kaydın ayrıntısı ve bekleyenleri listenin *altına*
  taşındı — bir satır hakkında oldukları için satırların yanında dururlar.
- Sağ yarı dört blok: **hazırlık durumu** (yığılmış oran + sayılar), **hareket
  sınıfı dağılımı**, **hata sınıfı dağılımı**, **katılımcı başına kapsam**.
- Grafikler `views/charts.py` içinde elle çiziliyor; her renk token'dan
  geliyor ve bir sınıfın çubuğu, zaman çizelgesinin o sınıfı boyadığı renk —
  sıralama sayıya göre değişse de sınıf rengini korusun diye sınıfın
  **kendi söz dağarcığındaki konumu** taşınıyor (`DatasetRow.class_order`).
- Sınıfsız tekrar/aralık kendi kovasında ve **her zaman son sırada**: bir
  sınıf değil, ama etiketlemekte olan biri için en önemli sayı, dolayısıyla
  gizlenmiyor.
- Grafikler **ekrandaki** satırlardan hesaplanıyor, viewmodel'den değil: arama
  ya da filtre listeyi daralttığında grafikler de daralıyor ve iki yarı asla
  çelişmiyor.

`verified`: Ölçüm — liste 961 px, istatistik sütunu 895 px; dağılımlar ve
kapsam gerçek projeden dolu geliyor; arama boş sonuç verince dört blok da
boşalıyor ve hazırlık oranı üç parçasını koruyor.

Bu turda bulunan bir yerleşim tuzağı: `SearchProxy.set_search` proxy'yi
geçersiz kılar ve geçersiz kılınmış bir proxy yeniden süzülene kadar sıfır
satır bildirir — aynı çağrı içinde okumak, satırlı bir tablonun yanında boş
bir grafik veriyordu. Yenileme artık bir sonraki olay turuna erteleniyor ve
tekrarlanan çağrılar tek geçişte birleşiyor.

## İş kuyruğu: neden çalışmıyordu

`verified`: Kök neden kuyruk servisi değil, **seçimin kaybolmasıydı**.
`RowTableModel.set_rows` modeli sıfırlar; sıfırlama `QTableView`'in seçimini
temizler. İşleme ekranı kuyruğu 400 ms'de bir yeniden okuduğu için seçilen iş
en fazla 400 ms seçili kalıyor, ardından `_job_selected` hiçbir şey seçili
görmediği için Duraklat, Devam et, İptal ve Yeniden dene yeniden pasifleşiyordu.
Düğmeler çalışıyordu; işaretçiyi üzerlerine götürmekten daha kısa süre.

Düzeltme: satırlar kimliğe göre (iş anahtarı / take kimliği) yeniden seçiliyor.
Ek olarak `QUEUED` iş de iptal edilebilir hale geldi ve pasif düğmenin nedeni
kuyruğun altında cümleyle yazılıyor.

`verified` — gerçek çocuk süreçlerle sürülen durum geçişleri (mock değil;
`psutil.suspend`, `psutil.resume` ve `terminate` gerçekten çağrıldı):

| Eylem | Sonuç |
|---|---|
| Seçim + 5 poll turu | Seçim korunuyor |
| Duraklat | `RUNNING → PAUSED`, süreç **hayatta** (öldürülmedi) |
| Devam et | `PAUSED → RUNNING` |
| İptal | `RUNNING → CANCELLED`, süreç çıktı; ham kayıt dosyaları **değişmedi** |
| Yeniden dene | Biten iş için yeni süreç başlıyor, `RUNNING` |

Hiçbir düğme kaldırılmadı; dördü de çalışıyor.

## İşlenen Videolar, Veri Seti, Dışa Aktarım, Ayarlar

İşlev değişikliği yok; yalnız istenen cila. İşlenen Videolar ve Veri Seti'nde
arama alanı büyüteç ikonu aldı, yer tutucu tam okunacak genişliğe getirildi ve
1650 px'e yayılan alan sınırlandı; Yenile düğmeleri diğerleriyle aynı yükseklik
ve yüzey ailesine alındı. Dışa Aktarım ve Ayarlar'a dokunulmadı; Ayarlar kendi
dikey kaydırmasını koruyor.

## Kalıcı teknik kararlar

- **Önizleme kutusu kameradan bağımsız.** `apply_stage_geometry` sabit referans
  orandan çözüyor; `_note_source_shape` artık yeniden yerleşim tetiklemiyor.
  Kaynağın kendi oranı `PreviewView._target_rect` içinde letterbox ile aynen
  korunuyor.
- **Bildirim kaldırma = yalnız görünürlük.** Kadraj ölçümü, uyarılar ve
  önizleme modeli notu hâlâ üretiliyor ve `CapturePage.status_sections`
  üzerinden **Araçlar › Yakalama Durumu** penceresine veriliyor. Kayıt
  korumaları ve kişi seçme zorunluluğu değişmedi.
- **Reddin tekrarı.** `toggle_recording` her basışta `_clear_refusal` çağırıyor;
  geri sayım tikinde tekrarı engelleyen deduplikasyon korunuyor.
- **Bant iki yatay hat.** Dört dikey sütun kaldırıldı. Sınıf şeridi kapasitesi
  gerçek çip genişliklerinden (gizli bir "cetvel" `QToolButton`'ın `sizeHint`'i)
  hesaplanıyor; `MIN_VISIBLE_CLASSES = 3`, `MAX_VISIBLE_CLASSES = 12`.
- **`ElidedLabel` yerleşim tuzağı.** `ElidedLabel` yatayda `Ignored` politika
  bildirir; içinde esneme olan bir satırda bu, minimum genişliğinin de yok
  sayılması demektir — ipucu satırı 1856 px genişlikteki şeritte `x = 1856`'ya,
  yani bandın dışına yerleşti. Banttaki bilgi etiketleri artık `BandLabel`:
  `sizeHint` tam cümleden gelir, taban küçük tutulur.
- **Pencereyi maksimize tutan koruma yalnız *geri dönüşü* yanıtlar.** İlk
  gösterimde de tetiklenen ilk sürüm, 1129×700 sürülen her test penceresini
  maksimize edip bütün yerleşim ölçümlerini bozuyordu (ölçülerek bulundu).
  Artık pencere bir kez maksimize olmadan koruma çalışmıyor.
- **Ölçüm yardımcısı bir kontrol değildir.** Çip genişliğini soran gizli
  `QToolButton` devre dışı, odaklanamaz ve fareye saydam; aksi hâlde "her
  kontrolün adı ya da ipucu olmalı" denetimine yakalanıyordu.
- **Aralık kontrolleri seçime bağlı.** Sürümün açık olması yeterli değil;
  `_set_editing_enabled` artık seçili hareket yoksa bandın aralık kontrollerini
  kapalı bırakıyor, böylece "Hata aralığı ekle" canlı görünüp sessizce hiçbir
  şey yapmıyor. (22 Eylül üçüncü tur: düğme kullanıcı isteğiyle kaldırıldı;
  kural silme düğmesi ve kare kutuları için sürüyor.)
- **Görünür widget'ı `setParent(None)` ile koparma.** Görünür bir widget'ın
  ebeveyni `None` olursa Qt onu **üst düzey pencere** yapar ve gösterir: sınıf
  çipi, etiketleme ekranında kendi başlık çubuğuyla küçük bir pencere olarak
  belirdi. Üç yerde (`ClassStrip`, `ClassPicker`, hareket özeti) önce `hide()`
  çağrılıyor.

## Korunan içerikler (envanter)

Kaldırılması istenmeyen ve teslimde **yerinde** olanlar: kayıt hedefi, kişi
seçimi ve "Kişi seçimini kaldır", kayıt modu ve "Modu uygula", geri sayım,
süre sonunda dur, aynalama, kadraj kılavuzu, süre/FPS/kayıt kaybı/önizleme
kaybı/diskte kalan metrikleri, işaret koy, zaman çizelgesi gezinme ve zoom
araçları, hareket kipinde sınıf seçme/ekleme, aralık, hazır bilgisi, veri
setinin dışında tut, hata aralığı ekle (22 Eylül üçüncü turda kullanıcı
isteğiyle kaldırıldı), sınıfsızlara uygula, silme; hata
kipinde başlangıç/bitiş, bağlı hareket, ilgili eklem özeti, tek "Eklemleri
düzenle", Harekete dön, Not ve silme; sağ panelde zemin, RGB iskelet kaplaması,
Gelişmiş, kamera presetleri, "ön" referansının açıklaması, sporcu seçimi ve
belirsiz aralık eylemleri.

## Çalıştırılan testler

`verified` — hepsi `QT_QPA_PLATFORM=offscreen` ile, kodun **son hâlinde**:

| Dosya(lar) | Sonuç |
|---|---|
| `test_studio_user_revision_2026_09_21.py` | 13/13 |
| `test_studio_user_revision_2026_09_22.py` (ikinci turda yazıldı) | 9/9 |
| `test_studio_editor_band.py` | 28/28 |
| `test_studio_capture_row.py` + `test_studio_capture_layout.py` | 37/37 |
| `test_studio_visual_language.py` + `test_shell_chrome_gui.py` | 92/92 |
| `test_studio_review_gui.py` + `test_studio_review.py` + `test_studio_review_open.py` + `test_joint_annotation_gui.py` | 89/89 |
| `test_studio_dataset_actions.py` + `test_studio_library.py` + `test_studio_processing.py` | 64/64 |
| `test_studio_projects_gui.py` + `test_studio_library.py` + `test_studio_processing.py` | 69/69 |
| `test_studio_shell.py` + `test_studio_toasts.py` | 48/48 |
| `test_studio_polish.py` + `test_studio_subject_gui.py` + `test_recording_reaches_labelling.py` | 97 (34 atlandı, 0 başarısız) |
| `test_studio_shell_gui.py` + `test_nav_logo.py` + `test_studio_brand.py` | geçti |
| `test_gui_viewports.py`, `test_gui_painting.py`, `test_export_gui.py`, `test_orphan_record_gui.py`, `test_project_deletion_gui.py`, `test_label_dialog_class_creation.py` | 188/188 |
| `test_studio_gui_harness.py` | 19/19 |
| `test_studio_capture.py` + `test_studio_capture_target.py` + `test_capture_subject_gui.py` | geçti |

`verified` — **üçüncü tur** (bant eylemleri ve 3B ızgara), kodun son hâlinde,
dosya başına ayrı süreçle, offscreen: 17 dosyada **344 geçti, 36 atlandı,
1 başarısız**. Yeni `test_studio_labelling_revision_2026_09_22.py` 13/13,
`test_studio_editor_band.py` 28/28 (en dar pencere testi dahil),
`test_studio_label_panel.py` 17/17, `test_studio_joint_picking.py` 21/21,
`test_studio_review_bands.py` 18 (+1 platform atlaması),
`test_studio_user_revision_2026_09_21.py` 13/13, `test_studio_skeleton_view.py`
43/43; ayrıca review, review_gui, skeleton3d, polish, skeleton_formats,
export_canonical, export_joint_evidence, export_gui ve processing_layout
yeşil. Başarısız olan tek test, aşağıda kayıtlı
`test_leaving_the_labelling_screen_stops_playback`. Nedeni bu turda yeniden
ölçüldü ve aynı: proje yokken `navigate("review")` → `False`, proje açıkken
etiketlemeden çıkınca `playing` → `False`.

`open`: **Tüm paketin tek koşusu bu turda tamamlanmadı.** GUI dosyaları tek
tek dakikalar sürüyor; yukarıdaki gruplar ayrı ayrı koşuldu ve her biri
tamamlandı. `test_processing_pipeline.py` ve `test_identity.py` eşzamanlılık
testlerinin aralıklı takılması
[test notundaki](../protocols/test-and-measurement.md) bilinen durumdur ve bu
turda çalıştırılmadı.

## Bu turda bulunan, bu turun dışında kalan bir açık

`verified`: `tests/test_studio_workload.py::test_leaving_the_labelling_screen_stops_playback`
çalışma ağacında **zaten başarısız**; bu turun değişiklikleriyle ilgisi yok ve
kapsam gereği düzeltilmedi.

Neden: testin `window` fixture'ı proje açmıyor. 20 Eylül kararından beri
Projeler dışındaki her ekran açık bir proje istiyor, dolayısıyla
`navigate("review")` ve `navigate("library")` reddediliyor, `active_page`
`projects` olarak kalıyor ve etiketleme sayfası hiç etkinleşmediği için
`page_deactivated` de hiç çalışmıyor — `playing` True kalıyor. Aynı dosyadaki
komşu test (`..._stops_its_clocks_when_it_is_left`) aynı nedenle geçiyor ama
boş yere geçiyor: saat zaten hiç başlamamış.

Ölçülerek doğrulandı: aynı adımlar `enter_the_workspace` ile proje açıldıktan
sonra çalıştırıldığında `active_page` sırasıyla `review` ve `library` oluyor ve
`playing` `False` dönüyor. Yani ürün doğru davranıyor; testin ön koşulu eksik.

## Superseded testler

Kullanıcı kararı eski sözleşmeyi değiştirdiği için üç test yeniden yazıldı;
silinmedi:

- `test_the_panel_holds_no_scroll_area_at_all` → `test_only_the_label_summary_may_scroll`
- `test_nothing_selected_is_a_line_not_a_filler_card` → `test_nothing_selected_still_shows_the_movement_editor`
- `test_connect_sits_on_the_heading_line` / `test_connect_is_above_the_record_target_panel` /
  `test_connect_is_not_in_the_control_row` → `test_connect_sits_beside_the_record_button`
  ve `test_connect_is_not_in_the_page_header`

`tests/_gui_harness.py` içindeki `clipped_controls`, eliden bir etiketin
**çizdiği** metni ölçecek biçimde düzeltildi: `ElidedLabel`'ın `sizeHint`'i
artık bilerek tam cümledir, ona göre ölçmek her kısaltmayı "kırpılma" sayardı.

## Açık kalanlar

- `open`: **Kullanıcı görsel kabulü alınmadı.** Bu belge ölçüm ve ekran
  görüntüsü raporudur; kabul yerine geçmez.
- `observed`: **1129×700 pencerede hata satırı kırpılıyor.** Offscreen
  ölçümde "Eklemleri düzenle" 114 px'e sığıyor (143 px gerekiyor) ve
  "Harekete dön" de kısa kalıyor, çünkü o boyutta bandın gerçek genişliği
  1117 px'lik en küçük genişliğin altında. Hedefte (maksimize, 1920) kırpılma
  yok. 21 Eylül kararı 1 farklı boyut matrisi istemediği için bu boyut için
  bir şey değiştirilmedi. Hareket satırı o boyutta da sığıyor.
- `open`: Gerçek ZED kamerayla hiçbir şey denenmedi (kamera bağlı değil). Kayıt
  satırı, yeşil bağlantı düğmesi ve önizleme geometrisi **sentetik mock
  backend** ile doğrulandı.
- `open`: Gerçek işleme işiyle uçtan uca Duraklat/Devam et denenmedi;
  durum geçişleri gerçek çocuk süreçlerle, Yeniden dene ise gerçek
  `kinecapture.processing` süreciyle sınandı.
- `open`: Ayarlar ekranı kendi dikey kaydırmasını koruyor. Kaydırma yasağı
  etiketleme sağ paneli içindir; Ayarlar bu turun kapsamında değildi.
- `open`: Bu makinede `LongPathsEnabled = 0` olduğu için sürüş betiği derin
  scratchpad yolunda `Path.exists()` yanıltıcı `False` döndürüyor; ham kaydın
  iptalden etkilenmediği pytest koşusunda (kısa yol) doğrulandı.
