---
type: plan
status: in-progress
created: 2026-09-20
updated: 2026-09-21
tags:
  - capture
  - subject-tracking
  - studio
  - gui
  - plan
---

# Kayıt, kişi takibi ve GUI onarımı — faz planı

Görev: [Claude promptu](../../promts/CLAUDE_CAPTURE_TRACKING_GUI_REPAIR_PROMPT_2026-09-20.md).
Salt okunur kanıt: [kabul notu](../audits/capture-tracking-gui-issues-2026-09-20.md).
Sonuçlar: [doğrulama raporu](../reports/capture-tracking-gui-repair-validation.md).

Bu plan **kod ve gerçek kayıt okunarak** çıkarıldı; brifteki ön teşhisler
doğrulanana kadar hipotez sayıldı. Aşağıdaki tablo P0'da ölçülerek kapandı.

## P0 — Kök nedenler (tamamlandı, ölçüldü)

| # | Belirti | Ölçülen kök neden | Kanıt |
|---|---|---|---|
| 1 | Etkin veri kökü Claude scratchpad'inde | `SessionService.save_user_state` **modül düzeyindeki** `USER_STATE_PATH`'e yazar. `pytest` bunu `conftest` ile yönlendirir; **pytest dışında çalışan ölçüm betikleri** yönlendiremez. 20 Eylül'de `scratchpad/measure_waste.py` gerçek `StudioWindow`'u sandbox `dataset_root` ile açtı, oturum açınca `save_user_state` **gerçek** `~/.kinecapture/user_state.yaml`'a yazdı. | Dosya mtime 23:24; `dataset_root` tam olarak o betiğin `waste_home/datasets`'i; `capture` bloğu da `AppConfig()` varsayılanlarına dönmüş (`enable_body_tracking: false`) |
| 2 | `SVO RECORDING ERROR` | Hedef yol **281 karakter**. Bu makinede `LongPathsEnabled = 0`. Projenin kendi yazıcıları `\?\` öneki kullandığı için `take.json` yazılabildi; `start_native_recording` SDK'ya **çıplak** yolu verdiği için `enable_recording` başarısız. Mesaj ise "disk/izin" diyordu. | `CreateFileW` çıplak → WinError 3; `CreateFileA` çıplak → WinError 3; `\?\` önekli → başarılı. Çalışan eski proje yolu 164 karakter. |
| 3 | 10,6 sn sonrası iskelet yok | `SubjectLockService.update` **AMBIGUOUS'u terminal durum** yapıyor: durum bir kez AMBIGUOUS olunca fonksiyon ilk satırda kısa devre yapıp bir daha hiçbir bedene bakmıyor. Kurtarma yalnız operatörün `confirm()` çağrısıyla mümkün; **offline işlemede operatör yok**. Ayrıca çatışma dalında `_remember` çağrılmadığı için `_last_seen_timestamp_ns` donuyor, `gap` büyüyor ve çatışma kendi kendini besliyor. | `features.json`: locked 622 + lost 4 + ambiguous **847** = 1473; tek olay `same_id_evidence_conflict` @626; `reassociations: 0`; `multi_person_frames: 631` (aynadaki yansıma), `disqualified_tracker_ids: [1]` |
| 4 | "Kaynak kapsamı doğrulanamadı" | `VersionRow.coverage_verified` = `not self.issues`. Bilgi niteliğindeki `subject_anchor_before_recording` bile uyarıyı tetikliyor; kişi kapsaması (622/1473) bu cümlede **hiç geçmiyor**. | `library.py:71`, `viewmodels/library.py:190` |
| 5 | Sağ yardımcı panel yok | Panel görünürlüğü **genel** `inspector_open` gözlemlenebilirine bağlı; sayfası kendi panelini sahiplenirken düğme "açık" görünüyor ama gözlemlenebilir `False`. İlk tıklama gözlemlenebiliri `True` yapıp hiçbir şeyi değiştirmiyor, ikinci tıklama paneli **gizliyor** ve `_inspector_by_page['review']=False` oturum boyunca kalıcı oluyor. | `shell.py:441-471`, `review.py:1368` |
| 6 | Yakalama paneli zıplıyor | `alert_strip` `body_layout`'ta sahnenin **üstünde**; kadraj uyarısı gelip gittikçe altındaki her şey kayıyor. Konsol grupları sabit yer ayırmıyor, `QScrollArea` içinde. | `pages/capture.py:189,259` |
| 7 | Bildirim butonları kırpık | Her kart `KcToastWidth = 400` ile **sabit genişlik**; eylem satırı 4 düğmeyi sıkıştırıyor. Ayrıca `_toggle_details` görünürlüğü değiştirip katmana yeniden ölçüm söylemiyor → kart altı kesiliyor. | `toasts.py:222,297`; `widgets.py:515` |

## Fazlar

- **P1 — C-01a.** Ayar yolu konfigürasyonun parçası olsun; sandbox kök taşıyan
  bir config gerçek tercih dosyasına **yazamasın**. Kullanıcının dosyasını
  yedekleyip kanıta dayalı kökle onar.
- **P2 — C-01b.** Kayıt hedefi için hafif ön kontrol (uzunluk, erişim, disk);
  nedene özgü hata metni; başarısız başlangıçta önizlemenin sürmesi ve tekrar
  denenebilmesi.
- **P3 — C-02.** AMBIGUOUS'un terminal olmaktan çıkması; aynı tracker kimliği
  tutarlı kanıtla dönünce güvenli kurtarma; gerçek take'in **yeni sürümü**.
- **P4 — C-03.** Kapsam eksenlerinin ayrılması (kaynak / zaman / kişi / proxy /
  bilgi notu), sayılarla anlatım, export kapılarının korunması.
- **P5 — C-04.** Sağ panel varsayılan görünür, sahiplenen sayfada genel tercih
  onu gizlemesin; preset sadeleştirme (Ön, Sağ, Sol, Üst, 45° + mini menü).
- **P6 — C-05.** Her açılışta Projeler; proje kapısı; yalnız Yakalama için
  katılımcı kapısı; otomatik katılımcı oluşturmanın kaldırılması.
- **P7 — C-06.** Sabit capture geometrisi, RGB gerçek oranı, canlı görüntüdeki
  büyük yönlendirme metinlerinin kaldırılması, tek kişi-seçimi bildirimi.
- **P8 — C-07.** Kart genişliği içeriğe göre; eylemlerin sarması; ayrıntının
  ayrı pencerede tam okunması.
- **P9 — Kabul.** Dosya dosya test koşusu, tam ekran gerçek pencere ölçümleri,
  ekran görüntüleri, rapor ve wiki güncellemesi.

## P1 — Ayar sızıntısı · tamamlandı

Tercih dosyasının yolu artık **konfigürasyonun parçası** (`AppConfig
.user_state_path`). `AppConfig.sandboxed(root)` veri kökü, kimlik, log ve
tercih dosyasını **birlikte** taşır; üçünü taşıyıp dördüncüyü bırakan betik
sızıntının kendisiydi. `save_user_state`, verisi geçici ağaçta olan bir
konfigürasyonun **sandbox dışındaki** tercih dosyasına yazmasını reddediyor.
Ayar dosyasının kendisi `user_state_path` **belirleyemez** (`from_mapping`
bu alanı okumaz), yoksa bir tercih dosyası sonraki bütün kayıtları başka yere
yönlendirebilirdi.

`tests/_gui_harness.py` artık `save_user_state`'i **stub'lamıyor**; gerçek
fonksiyonu çalıştırıyor ve reddedilmemesi kanıt oluyor.

Kullanıcının dosyası geri alınabilir biçimde onarıldı:
`~/.kinecapture/user_state.yaml.bak-2026-09-20-leak` yedeği alındı,
`dataset_root` kanıta dayalı olarak `C:\kc15
y8kajfjq\datasets` yapıldı
(`last_project_path` ve identity veritabanındaki **GUI TEST** kaydı aynı kökü
gösteriyor). `capture` bloğu **değiştirilmedi**: 22:50 kaydının kendi
`capture_profile`'ı ile birebir aynı, yani kullanıcının gerçek tercihi.

Yeni dosya: `tests/test_user_state_isolation.py` (6 test, hepsi yeşil).

## P2 — Kayıt hedefi ve kurtarılabilir başlangıç · tamamlandı

`ProjectWorkspace.longest_raw_path()` bir projenin üretebileceği **en derin**
ham dosya yolunu veriyor; bütün kimlikler sabit genişlikte olduğu için bu,
hiçbir şey yazılmadan bilinebiliyor. `CameraBackend.native_recording_path_limit`
her backend'in kendi tavanını söylüyor (ZED: `MAX_PATH`; mock: yok).
`CaptureService.check_recording_target(workspace)` bu ikisini birleştirip
`RecordingTargetCheck` döndürüyor ve `_start_recording` **`prepare_take`'ten
önce** çağırıyor.

Başarısız başlangıç artık `_fail` değil `_abort_start`: `ERROR`'a geçilmiyor,
`_stop_event` kurulmuyor, **önizleme sürüyor** ve tekrar denenebiliyor.

SDK yine de reddederse hata; gerçek hedefi, uzunluğu, sınırı, codec'i, klasörün
var olup olmadığını, yazılabilirliğini ve boş alanı taşıyor; tavsiye kanıta
göre seçiliyor. Her hataya "disk/izin" demek kaldırıldı.

Ölçüm (gerçek makine, `LongPathsEnabled = 0`), **tam 279 karakterde**
— başarısız kaydın gerçek hedef uzunluğu:

| Çağrı | Sonuç |
|---|---|
| çıplak `CreateFileW` | **başarısız**, WinError 3 |
| çıplak `CreateFileA` | **başarısız**, WinError 3 |
| `\?\` önekli `CreateFileW` | başarılı |

Bu yüzden `take.json` (aynı derinlik, projenin kendi önekli yazıcısı) yazıldı
ama SDK'nın `enable_recording`'i başarısız oldu. Çalışan eski projenin hedefi
164 karakter.

Yeni dosya: `tests/test_recording_target.py` (6 test, hepsi yeşil).

## P3 — Kişi kaybı · tamamlandı, gerçek kayıtla

**Nasıl ölçüldü.** SVO gerçekten yeniden oynatıldı (donanım gerekmiyor,
kamera bağlı değil) ve **gerçek `SubjectLock`** kare kare sürüldü; her karede
durum, sebep, çelişki sayacı ve vetoyu oluşturan iki benzerlik skoru
kaydedildi. Kayıtlı sürümün sayıları üç kare içinde yeniden üretildi
(622/4/847 → 625/4/843), yani arıza sadık biçimde canlandırıldı.

**Kök neden — iki kusur üst üste geldi.**

1. Veto bir **duruş** ölçüsünü kimlik ölçüsü sanıyordu. Kimliği söyleyen uzuv
   uzunluğu skoru olayın **her karesinde 0,992**'de kaldı; eklem bulutunun
   yüksekliği sporcu öne eğilirken 1,376 m'den 1,288 m'ye indi ve stature
   skorunu 0,3 eşiğinin altına taşıdı (628: 0,2933 · 629: 0,2731 · 630:
   0,2544). Üç kare sonunda kilit kimlik çatışması ilan etti.
2. `AMBIGUOUS` **terminal** durumdu. `update` o noktadan sonra ilk satırında
   dönüyor, bir daha hiçbir bedene bakmıyordu. 630'dan sonraki **832 karenin
   hepsinde** tracker 0 kadrajdaydı; tek kayıt "awaiting_confirmation".
3. Yan etki: çelişki dalında `_remember` çağrılmadığı için "en son ne zaman
   görüldü" donuyor, `gap` büyüyor ve `gap > give_up_seconds` her kareyi kendi
   başına çelişki yapıyordu — kendini besleyen bir anlaşmazlık.

**Düzeltmeler.** `_proportions_contradict`: yalnız uzuv skoru vetolayabilir;
stature ancak uzuv kanıtı hiç yokken konuşur (yeniden eşleştirme
**puanlamasında** her iki terim de ağırlığını koruyor). `_try_recover`:
belirsiz kilit, **yalnız zaten üzerinde olduğu tracker kimliğine**, seçili
kişiyle aynı karede hiç görülmemiş olması şartıyla ve `recovery_frames`
(30 kare) boyunca kesintisiz uyum varsa geri döner. Çelişki dalında artık
yalnız görülme zamanı yenileniyor; konum ve imza **değişmiyor**. Codex son
koşusunda `_remember`'ın reddedilen konumu da öğrendiği iki mevcut regresyon
testiyle bulundu ve düzeltildi; [kanıt](../reports/capture-tracking-gui-repair-validation.md).

**Aynadaki yansıma.** `multi_person_frames: 631`, tracker 1. Kök konumu
x≈0,98 z≈−3,47 (sporcu x≈0,27 z≈−2,82), stature 1,74 ve donuk, durumu
`searching`. 397. kareden itibaren sporcuyla aynı karede göründüğü için
**tanım gereği diskalifiye**; kilit ona hiçbir koşulda geçemez. Bu davranış
korundu, değiştirilmedi.

**Gerçek kayıtta önce/sonra** (aynı ham SVO, yeni sürüm):

| | `run_4b8fd122e2c44eee` (mevcut) | yeni sürüm |
|---|---|---|
| `subject_present` true | **622 / 1473** | **1473 / 1473** |
| son sonlu eklem karesi | 623 | 1472 |
| ambiguous | 847 | **0** |
| lost | 4 | **0** |
| çok kişili kare | 631 | 631 (değişmedi) |
| yeniden eşleştirme | 0 | 0 (gerek kalmadı) |

Mevcut sürüm ve etiket kanıtı **değiştirilmedi**; yeni sürüm yanına yazıldı.

Yeni dosya: `tests/test_subject_lock_recovery.py` (11 test). Mevcut
`test_subject_lock.py` (22 test) değişmeden yeşil.

## P4 — Kapsam eksenlerini ayırmak · tamamlandı

`IssueAxis` (source · timing · subject · proxy · note · **unknown**) ve
`IssueWeight` (note · caution · blocking) açık sözleşme oldu; her kod
`ISSUE_CATALOGUE`'da bir cümle, bir eksen ve bir ağırlık taşıyor. Tanınmayan
kod kendi ekseninde ve **caution** ağırlığında kalıyor: bu sürümün kodu
bilmemesi, kodun zararsız olduğunun kanıtı değil.

`VersionRow.coverage_verified` artık yalnız **ham kaynak** sorusunu
yanıtlıyor; `subject_verified` ayrı bir eksen (`None` = kaydedilmedi,
"kimse yok" değil). İşleme şeması **1.3.0**: `job.json` artık
`subject_coverage` bloğu taşıyor; 1.2.0 sürümleri için okuyucu kendi
`features.json`'una düşüyor (gerçek sürümde 622 okundu).

Kullanıcıya çıkan ileti artık sayılarla: *"kaynak 1473/1475 kare eşleşti ·
kişi 622/1473 karede izlendi"*, başlık hangi eksenin eksik olduğunu söylüyor,
"yeniden işle" neyi düzeltebileceğini ve neyi düzeltemeyeceğini belirtiyor.
Salt bilgi notu (`subject_anchor_before_recording`,
`capture_timestamp_duplicated`) artık **uyarı üretmiyor**; detayda sayılıyor.

## P5 — Sağ yardımcı panel · tamamlandı

**Gerçek pencerede yeniden üretildi.** Kullanıcının kendi `window_state.json`
değerleriyle (`inspector_open: false`, `active_page: processing`), gerçek GUI
TEST sürümü açık, tam ekran: panel görünmüyordu, düğme **"açık" görünüyordu**,
ve `QTest` ile gerçek tıklamalarda **1. tık hiçbir şey yapmıyor**, 2. tık
gizliyor, gizli durum `_inspector_by_page['review']` ile oturum boyunca
kalıyordu. Neden: sayfanın kendi paneli, kabuğun **kendi** paneline ait genel
bir tercihe bağlıydı; düğme sahiplenen sayfada zaten işaretli olduğu için
gözlemlenebilir ile görüntü ters düşüyordu.

**Karar.** Etiketleme panelinin görünürlüğü artık bir tercih değil:
`StudioPage.inspector_is_permanent`. Kabuk sahiplenen sayfada paneli her
durumda gösteriyor, kendi panelini kapatıyor, düğmeyi **devre dışı** bırakıp
"gizlenemez" diyor. Kaydedilmiş `inspector_open: false` artık bu paneli
etkilemiyor — göç bu.

Gerçek pencerede sonrası: üç tıklamada da `visible=True`, sekme değiştirip
dönünce `True`.

**Preset sadeleştirme.** Ana panelde beş yön: **Ön · Sağ · Sol · Üst · 45°**
(iki satır üç sütun, altıncı hücrede "Diğer ▾"). Menüde: Arka, Ön-sol 45°,
Kayıt yönü. Kısa etiket yalnız göz için; erişilebilir ad tam etiketi taşıyor.
Anatomik referans ve en kısa yol animasyonu dokunulmadı.

## P6 — Başlangıç ve kapılar · tamamlandı

`ShellViewModel` artık `window_state.active_page`'i **geri yüklemiyor**; her
açılış ve her oturum açma **Projeler**. Değer yazılmaya devam ediyor (son
oturumun nerede olduğunu söyler) ve bunun okunmadığı alanın kendi
belgesinde yazılı.

`gate_reason(key)` tek kural: Projeler dışındaki her ekran **proje**,
Yakalama ayrıca **katılımcı** ister. Kural `navigate` içinde — düğmede değil —
uygulanıyor, çünkü içeri giren yollar arasında `Ctrl+1..8`, adım kısayolları,
bildirim kartı eylemleri ve iş bitince doğrudan yönlendiren kod da var. Nav
bar aynı kuralı okuyup engelli adımları soluklaştırıyor ve nedenini ipucunda
yazıyor; adım kısayolu engelli hedefte **duruyor**, Projeler'e sekmiyor.

Reddedilince tek kart (`capture_needs_participant` / `needs_project`) ve
Projeler'e yönlendirme. Kayıt komutunun kendisi de aynı kapıyı geçiyor
(`_can_record`), çünkü Space ve F5 düğmeye uğramadan oraya varıyor.

**Otomatik katılımcı oluşturma kaldırıldı.** `_current_session` artık ne
katılımcı yaratıyor ne de listedeki ilkine düşüyor; reddediyor ve nereye
gidileceğini söylüyor. Katılımcıyı Projeler'de **oluşturmak onu seçmek
sayılıyor** (kullanıcı o kişinin var olmasını istedi). Proje değişince eski
projenin katılımcısı taşınmıyor (`open_project` zaten temizliyordu; artık
testi var).

Testler: `test_studio_shell.py`'ye 6 kapı testi eklendi; kuralı kodlayan eski
testler yeni kurala göre yeniden yazıldı (`test_studio_capture.py`,
`test_studio_capture_target.py`). GUI fikstürleri ya kapıdan geçiyor
(`enter_the_workspace`) ya da sayfayı doğrudan gösteriyor
(`show_page_directly`) — ikincisi yalnız ekranın kendi çizimini ölçen
dosyalarda, gerekçesi orada yazılı.

## P7 — Yakalama düzeni · tamamlandı

**Uyarı şeridi sayfadan çıktı.** Görüntünün üstünde duruyordu; her kadraj
uyarısı gelip gittiğinde altındaki her şey (görüntü, konsol, kayıt düğmesi)
aşağı yukarı kayıyordu. Yerine konsolun altında **yükseklik ayrılmış DURUM
bölmesi**: dört satır (kadraj · öneri · en acil uyarı · önizleme notu) artı
"Ayrıntılar". Satırlar sarmıyor, eliyor; tam metin ipucunda ve ayrıntı
penceresinde.

**Bloklar yüksekliklerini baştan ayırıyor** (`_ConsoleGroup.reserve`), ilk
gerçek yerleşimden sonra — daha önce ölçmek anlamsız: geometrisi olmayan bir
widget'ın `sizeHint`'i durum bölmesi için **2000 px** dönüyordu. Durum
satırları `_StatusLine`: yükseklik yazı tipinden alınıyor ve **monoton**
(bir stil değişimi üç piksel kısaltıp altındaki her şeyi kaydırıyordu).

**RGB gerçek oranıyla.** Yeni `services/capture_layout.py`: görüntü, kendi
en/boy oranının o yükseklikte kullanabileceği genişliği alıyor; kalan konsola
gidiyor, okunur bir üst sınıra kadar. Kırpma, esnetme, ölçek değişikliği yok —
letterbox kodu olduğu gibi duruyor, artık letterbox edecek siyah alan kalmıyor.
Tıklama eşlemesi aynı koddan geçtiği için değişmedi; testle doğrulandı.

**Scroll yerine iki sütun.** Konsol `QScrollArea`'dan çıktı. Bloklar yüksekliğe
sığmazsa konsol **iki sütuna** geçiyor (brifin kendi önerisi). Scroll
yasaklıydı; `QVBoxLayout` ise az yer verilince kırpmaz, **üst üste bindirir**.

**Görüntü üzerindeki tekrarlar kaldırıldı.** "Kadrajda kimse yok" artık
resmin üstüne basılmıyor (kadraj hükmü değil; ortada çerçevelenecek kimse
yok) — konsol söylüyor. Kişi seçimi reddi yalnız **bildirim kartı**; resmin
üstündeki kopya kaldırıldı. Ret metni **durum değişene kadar tekrar
edilmiyor**. Kamera bağlı değil placeholder'ı, geri sayım ve kayıt çerçevesi
dokunulmadı.

Yeni dosya: `tests/test_studio_capture_layout.py` (15 test). Kadraj hükmü beş
durum arasında değişirken **13 denetimin konumu bit birebir aynı**; uyarı
gelip giderken aynı; kişi seçilip bırakılırken aynı.

## P8 — Bildirim kartları · tamamlandı

**Kök neden.** `QPushButton` metninden dar olduğunda ne sarar ne eler:
metni ortalar ve **iki uçtan keser** — "Etiketlemeyi aç" ekrana "iketlemeyi a"
diye geliyordu. Kart genişliği `KcToastWidth = 400` ile sabitti ve eylem
satırı `QHBoxLayout`'tu.

**Düzeltme.** Her düğme kendi metninin genişliğini (gerçek yazı tipiyle)
ayırıyor; eylem satırı **saran** `FlowLayout`; kart genişliği içeriğe göre
büyüyor (400 taban, pencerenin izin verdiği kadar). "Ayrıntılar" artık kart
içinde açılmıyor, **ayrı pencerede** tam metni gösteriyor — teknik satır
boşluksuz kod listesi olduğu için bir etiket onu saramıyordu ve sağdan
taşıyordu; kartın yüksekliği de katlanma açılmadan ölçüldüğü için üstündeki
cümle alttan kesiliyordu.

**İki ölçüm hatası daha bulundu ve düzeltildi:** katman yeniden yerleşimi
**özyinelemeliydi** (kart doldurulurken `resized` gelip ortasında ölçüm
yapıyordu) ve ölçüm **widget'ın önbellekli `sizeHint`'ini** okuyordu — bir kez
üç satır sarmış olarak ölçülen kart sonsuza dek o yüksekliği bildiriyordu
(134 px içerik için 286 px kart).

Yeni dosya: `tests/test_studio_toast_actions.py` (12 test): gerçek kartın
kendisi, 0/1/2/3/5 eylem, binme yok, kart dışına çizim yok, ayrıntı
penceresinde tam teknik metin, yığılmış kartlar alt gezinmeyi kapatmıyor.

## P9 — Kabul, kanıt, teslim · kısmen tamamlandı

**Gerçek kayıt yeniden işlendi** (`run_a79158c706454edc`, şema 1.3.0): kişi
kapsaması **622/1473 → 1473/1473**. Kullanıcının orijinal sürümü ve ham SVO
dokunulmadı.

**Gerçek tam ekran ölçümleri alındı**, %100 (1920×1009) ve %150 (1280×673
mantıksal): kadraj/uyarı/kişi geçişlerinde hareket eden denetim **0**,
kaydırma **0**, binme **0**, kırpılma **0**; RGB oranı %100'de **1,778**;
etiketleme paneli üç gerçek tıklamadan sonra hâlâ görünür; 8,12 / 10,60 /
11,25 / 20 / 24 saniyede iskelet **var**.

**Bu fazda üç ek hata bulundu ve düzeltildi:** 2B kaplamadaki `(-1,-1)`
sentinel'i, sayfadan dönünce editör bandının sahneye **10 piksel** binmesi,
ve yakalama ekranında okumaların kendi yüksekliği/genişliğiyle alttaki
denetimleri kaydırması.

**Kullanıcı verisi hash ile doğrulandı:** tercih dosyası, pencere durumu ve
kimlik veritabanı bütün koşulardan sonra **bit birebir aynı**.

**Codex teslimi:** kişi kilidi konum regresyonu ve yakalama denetimlerinin
boyut değişimleri düzeltildi. `%150` etiketlemede daha önce atlanmış **83 px**
band binmesi bulundu; yükseklik bütçesi düzeltildi ve sığmayan kamera/kişi
kontrolleri ayrı pencereye açılacak şekilde düzenlendi. Bu son GUI kodu
**doğrulanmadı**. Önceki bütün sayfalar için "binme 0" iddiası `superseded`;
ayrıntı [raporda](../reports/capture-tracking-gui-repair-validation.md).

### Devam noktası

**Devir kapandı; görsel kabul açık.** Kullanıcı son düzenlemelerden sonra
tekrar test istemedi ve GUI görünümünü değiştirmeye geçmek istedi.
Koşu durduruldu: **47/95** dosya sonuçlandı, **45 yeşil / 2 başarısız**;
tamamlanan dosyalar **784,7 sn**. Son değişiklikler yeniden koşulmadı.
Sonraki iş kullanıcının GUI düzenlemeleridir; otomatik tam test tekrarı
başlatılmaz. [Teslim durumu](capture-tracking-gui-repair-handoff-codex.md).
