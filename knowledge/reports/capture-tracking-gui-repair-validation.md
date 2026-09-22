---
type: report
status: current
created: 2026-09-21
updated: 2026-09-21
tags:
  - capture
  - subject-tracking
  - studio
  - gui
  - measurement
---

# Kayıt, kişi takibi ve GUI onarımı — çalıştırılan doğrulamalar

Yalnız **gerçekten çalıştırılan** kontroller. Kök nedenler ve fazlar
[uygulama planında](../plans/capture-tracking-gui-repair-implementation.md);
görev ve salt okunur ön bulgular
[20 Eylül kabul notunda](../audits/capture-tracking-gui-issues-2026-09-20.md).

Kanıt düzeyi: `verified` (bu ortamda çalıştırıldı) · `observed` ·
`doğrulanmadı`.

## Son teslim durumu · 21 Eylül, Codex

**Kullanıcı kararı (`decision`):** Son düzenlemelerden sonra testler tekrar
çalıştırılmayacak; sonraki iş GUI görünümünü değiştirmek. Çalışan koşu bu
istekle durduruldu. Kod teslim edildi; son görsel değişiklikler
**doğrulanmadı**, GUI kabulü verilmiş sayılmaz.

**Önemli kanıt düzeltmesi:** Önceki `%150` raporundaki "etiketlemede binme
0" iddiası `superseded`. Hem eski hem Codex manifestinde sahne ile editör
bandı **83 px** kesişiyordu. Önceki betik ayrıca yalnız son açık sağ panel
sekmesinin binmesini topluyordu; kamera sekmesindeki taşmaları kapsamıyordu.
Son kodda sahne yüksekliği kalan gerçek bütçeyi aşamaz; kısa sağ panelde
ana kamera açıları korunur, tam kamera/kişi kontrolleri modeless pencereden
açılır. Betik artık üç sekmenin binmelerini ayrı toplar. Bu son panel
düzenlemesi ve yeni ölçüm betiği kullanıcı isteği doğrultusunda **yeniden
çalıştırılmadı**; aşağıdaki eski görüntüler son panel düzeninin kanıtı değildir.

## Ortam ve kanıt konumu

| | |
|---|---|
| Python | 3.11.14 (`KineSynth`), PySide6 6.10.1, pyzed 5.4.1 |
| Pencere | tam ekran, %100'de **1920×1009**, %150'de **1280×673** mantıksal |
| Qt platformu | ölçümlerde `windows`, gerçek yazı tipleri ve gerçek GL |
| Gerçek kayıt | GUI TEST · `take_20260920T195059_c183` · BODY_38 · 1473 kare |
| Donanım | kamera **bağlı değil**; SVO yeniden oynatma donanım gerektirmiyor |
| Tarih | 2026-09-21 |

Ekran görüntüleri ve geometri manifesti (wiki dışında, yerel):

- **Son kod, Codex doğrulaması:**
  `C:\Users\gorke\.codex\visualizations\2026\09\21\capture-tracking-codex-final`
  (`100/manifest.json`, `150/manifest.json`, `subject_lock_replay.jsonl`,
  `suite_final.json` ve dosya başına `suite_final_logs/`).
- Önceki Claude ölçümleri (tarihsel):
- `C:\Users\gorke\.codex\visualizations\2026\09\21\capture-tracking-after`
- `C:\Users\gorke\.codex\visualizations\2026\09\21\capture-tracking-after-150`

Kullanıcının ham SVO'su, etiketleri ve mevcut sürümü **değiştirilmedi**.
Kullanıcı verisi yalnız okundu; uygulamanın kendi durumu (tercih, kimlik,
pencere) ölçümlerde sandbox'a alındı.

## C-01 · Veri kökü ve kayıt başlatma

### Belirti → kök neden

| Belirti | Kök neden (ölçüldü) |
|---|---|
| `dataset_root` Claude scratchpad'inde | Tercih dosyasının yolu **modül sabiti**ydi. `pytest` onu yönlendirir; **pytest dışında çalışan ölçüm betiği** yönlendiremez. 20 Eylül'de `measure_waste.py` gerçek pencereyi sandbox veri köküyle açtı; oturum açınca `save_user_state` **gerçek** dosyaya yazdı. |
| `SVO RECORDING ERROR` | Hedef yol **279 karakter**; bu makinede `LongPathsEnabled = 0`. Projenin kendi yazıcıları `\\?\` öneki kullandığı için `take.json` aynı derinliğe yazıldı; SDK'ya çıplak yol verildiği için `enable_recording` başarısız oldu. |
| "Disk alanını ve hedef klasörün yazma iznini kontrol edin" | Her SDK hatası için tek sabit metin. Diskte 138 GB boştu, klasör yazılabilirdi. |
| Başarısız başlangıçta donmuş kare | `_fail` → `ERROR`; bu durumdan çıkış yalnız `DISCONNECTED` üzerinden. Önizleme iş parçacığı durduruluyordu. |

### Çalıştırılan ölçüm — `verified`

Gerçek makine, tam olarak başarısız hedefin uzunluğunda (279 karakter,
dizin 240):

| Çağrı | Sonuç |
|---|---|
| çıplak `CreateFileW` | **başarısız**, WinError 3 |
| çıplak `CreateFileA` | **başarısız**, WinError 3 |
| `\\?\` önekli `CreateFileW` | **başarılı** |

Çalışan eski projenin hedefi 164 karakter — kullanıcının "eski projede kayıt
alabiliyordum" bildirimiyle tutarlı.

### Düzeltme

`AppConfig.user_state_path` konfigürasyonun parçası; `AppConfig.sandboxed(root)`
veri kökü, kimlik, log ve tercih dosyasını **birlikte** taşır. Verisi geçici
ağaçta olan bir konfigürasyonun sandbox dışındaki tercih dosyasına yazması
**reddediliyor**. Ayar dosyası `user_state_path` belirleyemiyor.

`ProjectWorkspace.longest_raw_path()` + `CameraBackend.native_recording_path_limit`
→ `CaptureService.check_recording_target(workspace)`; `_start_recording`
**`prepare_take`'ten önce** çağırıyor. Başarısız başlangıç `_abort_start`:
`ERROR`'a geçilmiyor, **önizleme sürüyor**, tekrar denenebiliyor. SDK yine
reddederse hata gerçek hedefi, uzunluğu, sınırı, codec'i, klasörün varlığını,
yazılabilirliğini ve boş alanı taşıyor.

### Kullanıcının dosyası — `verified`

Yedek: `~/.kinecapture/user_state.yaml.bak-2026-09-20-leak`.
`dataset_root` → `C:\kc15\ry8kajfjq\datasets` (kanıt: `last_project_path` ve
identity veritabanındaki **GUI TEST** kaydı aynı kökü gösteriyor).
`capture` bloğu **değiştirilmedi**: 22:50 kaydının kendi `capture_profile`'ı
ile birebir aynı, yani kullanıcının gerçek tercihi.

### Kalan

Identity veritabanında iki **pytest geçici dizinine** işaret eden proje kaydı
duruyor (`prj_20260902…`, `prj_20260903…`) ve kullanıcının 20 Eylül'de sızan
kökte açtığı `prj_20260920T195851_f700`. Bunlar **silinmedi**: kullanıcının
kimlik veritabanı ve kararı. Yolları artık yok, listede kırık görünürler.

## C-02 · 10,6 saniye sonrası kişi kaybı

### Nasıl ölçüldü — `verified`

SVO gerçekten yeniden oynatıldı ve **gerçek `SubjectLock`** kare kare
sürüldü; her karede durum, sebep, çelişki sayacı ve vetoyu oluşturan iki
benzerlik skoru kaydedildi. Kayıtlı sürümün sayıları üç kare içinde yeniden
üretildi (622/4/847 → 625/4/843): arıza sadık biçimde canlandırıldı.

### Kök neden

**1. Veto bir duruş ölçüsünü kimlik ölçüsü sanıyordu.**

| kare | uzuv skoru | stature skoru | ölçülen boy | imza |
|---|---|---|---|---|
| 616 | 0,9936 | 0,6425 | 1,3763 | 1,4540 |
| 622 | 0,9925 | 0,4626 | 1,3354 | 1,4520 |
| 627 | 0,9919 | 0,3137 | 1,3010 | 1,4498 |
| **628** | 0,9917 | **0,2933** | 1,2961 | 1,4498 |
| 629 | 0,9916 | 0,2731 | 1,2917 | 1,4498 |
| **630** | 0,9915 | 0,2544 | 1,2876 | → **ambiguous** |

Kimliği söyleyen uzuv uzunluğu skoru olayın **her karesinde 0,99**'da kaldı.
"stature" burada eklem bulutunun dikey uzanımı — yani **duruş** ölçüsü. Sporcu
öne eğildi, skor 0,3 eşiğinin altına indi, üç kare sonunda kilit kimlik
çatışması ilan etti.

**2. `AMBIGUOUS` terminal durumdu.** `update` o noktadan sonra ilk satırında
dönüyordu. 630'dan sonraki **832 karenin hepsinde** tracker 0 kadrajdaydı;
kaydedilen tek sebep `awaiting_confirmation`. Kurtarma yalnız operatörün
`confirm()` çağrısıyla mümkündü — **offline işlemede operatör yok**.

**3. Çelişki dalında `_remember` çağrılmıyordu**, "en son ne zaman görüldü"
donuyor, `gap` büyüyor ve `gap > give_up_seconds` her kareyi kendi başına
çelişki yapıyordu: kendini besleyen bir anlaşmazlık.

### Aynadaki yansıma — `verified`

`multi_person_frames: 631`, tracker kimliği 1. Kök konumu x≈0,98 z≈−3,47
(sporcu x≈0,27 z≈−2,82), boyu 1,74 ve **donuk**, durumu `searching` iken
sporcu `ok`. 397. kareden itibaren sporcuyla aynı karede göründüğü için
**tanım gereği diskalifiye** — kilit ona hiçbir koşulda geçemez. Bu davranış
korundu; yansıma kök neden **değil**, fakat `len(present) > 1` koşulunu
sağlayarak vetoyu silahlandıran şey oydu.

### Düzeltme

`_proportions_contradict`: yalnız **uzuv** skoru vetolayabilir; stature ancak
uzuv kanıtı hiç yokken (üçten az ortak segment) konuşur. Yeniden eşleştirme
**puanlamasında** her iki terim de ağırlığını koruyor.

`_try_recover`: belirsiz kilit **yalnız zaten üzerinde olduğu tracker
kimliğine**, seçili kişiyle aynı karede hiç görülmemiş olması şartıyla,
çözümlenmiş ve oranları uyumlu hâlde `recovery_frames` (30 kare) boyunca
kesintisiz göründüyse geri döner. Başka bir bedene **hiçbir koşulda**
geçmez. Çelişki dalında görülme zamanı güncellenir; güvenilir konum ve imza
reddedilen kareden öğrenmez.

**Codex son koşu düzeltmesi — `verified`.** İlk düzeltmedeki `_remember`
çağrısı konumu da güncelliyordu: dört metre sıçrayan reddedilmiş kare, bir
sonraki karenin konum referansı oluyordu. `test_capture_architecture.py`
içindeki iki mevcut regresyon testi bunu yakaladı. Yalnız zaman damgasını
yenilemek hem donan `gap` sorununu hem yanlış konumun öğrenilmesini önlüyor.
Tek bozuk kareden sonra doğru kişi hemen dönebiliyor; art arda imkânsız
konumlar hâlâ reddediliyor. Dört saniyelik oran çelişkisinden sonra dönüş de
`test_subject_lock_recovery.py` içinde doğrulandı.

Son kodla **aynı ham SVO yeniden oynatıldı** (`diag_lock.py`, 124,1 sn):
ilk seçim karesi + 1472 kilitli kare = **1473/1473**, kayıp **0**, belirsiz
**0**, kurtarma **0**, çok bedenli kare **631**. Bu salt okunur offline
doğrulamadır; yeni processing sürümü yazılmadı ve canlı kamera kullanılmadı.

### Gerçek kayıtta önce/sonra — `verified`

Aynı ham SVO, yeni sürüm (`run_a79158c706454edc`, şema 1.3.0):

| | mevcut sürüm `run_4b8fd122e2c44eee` | yeni sürüm |
|---|---|---|
| `subject_present` true | **622 / 1473** | **1473 / 1473** |
| son sonlu eklem karesi | 623 | 1472 |
| ambiguous kare | 847 | **0** |
| lost kare | 4 | **0** |
| çok kişili kare | 631 | 631 (değişmedi) |
| yeniden eşleştirme | 0 | 0 (gerek kalmadı) |
| kurtarma | — | 0 (yanlış veto hiç tetiklenmedi) |

Tam ekran gerçek pencerede, kullanıcının işaret ettiği anlar:

| an | kare | iskelet |
|---|---|---|
| 8,12 sn | 487 | var |
| 10,60 sn | 636 | **var** (eskiden yok) |
| 11,25 sn | 675 | **var** (eskiden yok) |
| 20,00 sn | 1200 | **var** |
| 24,00 sn | 1440 | **var** |

`09-review-*.png`. Zaman çizelgesinin "Kişi" şeridi kaydın tamamında dolu.

### Kaynak eşlemesinin doğruluğu — `verified`

Kaydedilen `timestamps` ve `source_positions` dizilerinde geriye gidiş 0;
capture 1475, SVO başlığı 1474, okunan 1473, eşleşen 1473. **2 eşleşmeyen
kare gerçekten var** ve yeniden işleme onu geri getirmedi — getiremez de.
Aynı mikrosaniyeli kareler tekleştirilmedi, sıraya göre eşleştirildi.

## C-03 · Kaynak kapsamı ile kişi kapsamı

`IssueAxis` (source · timing · subject · proxy · note · **unknown**) ve
`IssueWeight` (note · caution · blocking) açık sözleşme. Tanınmayan kod kendi
ekseninde ve **caution** ağırlığında: bu sürümün kodu bilmemesi, kodun
zararsız olduğunun kanıtı değil.

`coverage_verified` artık yalnız **ham kaynak** sorusunu yanıtlıyor;
`subject_verified` ayrı eksen (`None` = kaydedilmedi, "kimse yok" değil).
İşleme şeması **1.3.0**: `job.json` `subject_coverage` bloğu taşıyor; 1.2.0
sürümleri için okuyucu `features.json`'a düşüyor — gerçek sürümde **622**
okundu.

Gerçek iki sürümle çalıştırılan ileti — `verified`:

| sürüm | başlık | ayrıntı |
|---|---|---|
| eski | "Bu sürümde hem kaynak hem kişi kapsamı eksik." | kaynak 1473/1475 kare eşleşti · kişi **622/1473** karede izlendi. Yeniden işleme kişi takibini yeniden dener; ham kayıtta olmayan kareyi geri getiremez. Ayrıca 2 bilgi notu var. |
| yeni | "Bu sürümde ham kaynağın bazı kareleri eşleştirilemedi." | kaynak 1473/1475 kare eşleşti · kişi **1473/1473** karede izlendi. … |

Salt bilgi notu (`subject_anchor_before_recording`,
`capture_timestamp_duplicated`) artık **uyarı üretmiyor**; detayda sayılıyor.
Export kapıları dokunulmadı: `export/canonical.py` hâlâ `job["issues"]`
listesini olduğu gibi pakete yazıyor.

## C-04 · Sağ yardımcı panel

**Gerçek pencerede yeniden üretildi.** Kullanıcının kendi `window_state.json`
değerleriyle, gerçek sürüm açık: panel görünmüyor, düğme **"açık" görünüyor**,
`QTest` ile gerçek tıklamalarda 1. tık hiçbir şey yapmıyor, 2. tık gizliyor,
gizli durum oturum boyunca kalıyordu. Neden: sayfanın kendi paneli, kabuğun
**kendi** paneline ait genel bir tercihe bağlıydı.

Düzeltme: `StudioPage.inspector_is_permanent`. Etiketleme panelinin
görünürlüğü artık bir tercih değil; düğme sahiplenen sayfada devre dışı ve
"gizlenemez" diyor. Kaydedilmiş `inspector_open: false` bu paneli etkilemiyor.

Tam ekran ölçüm — `verified`:

| | |
|---|---|
| panel görünür | **evet** |
| düğme etkin | hayır (kalıcı) |
| üç gerçek tıklamadan sonra | **görünür** |
| sekme değiştirip dönünce | **görünür** |
| panel içi kaydırma (kamera · etiket özeti · kişi) | **0 · 0 · 0** |
| etiketleme sayfasında binen widget çifti | **0** |

Presetler: ana panelde **Ön · Sağ · Sol · Üst · 45°**; menüde Arka, Ön-sol 45°,
Kayıt yönü. Anatomik referans ve en kısa yol animasyonu korundu.

**Bu turda bulunan ek hata.** Sayfadan çıkıp dönünce editör bandı sahnenin
**10 piksel üstüne** biniyordu: araç çubuğu ilk gösterimde 48, ikincisinde 62
piksel bildiriyor; çözücü küçük sayıyla bölüşüyor, bant büyük olanı alıyordu.
Çözücü artık bandın gerçek yüksekliğini de okuyor ve araç çubuğu/timeline
yeniden boyutlanınca yeniden çözülüyor.

## C-05 · Başlangıç, proje ve katılımcı kapıları

Her açılış ve her oturum açma **Projeler**; `window_state.active_page`
yazılmaya devam ediyor ama **geri yüklenmiyor** (alanın kendi belgesinde
yazılı).

Tam ekran ölçüm — `verified`: proje yokken kapalı olan sekmeler
`capture · processing · library · review · dataset · export · settings`;
açık olan yalnız `projects`. Proje açıldıktan sonra Yakalama'nın gerekçesi
"Kayıt için önce bir katılımcı seçin." → katılımcı seçilince **boş**.

Kural `navigate` içinde — düğmede değil — çünkü içeri giren yollar arasında
`Ctrl+1..8`, adım kısayolları, bildirim kartı eylemleri ve doğrudan
yönlendiren kod da var. Nav bar aynı kuralı okuyup engelli adımları
soluklaştırıyor; adım kısayolu engelli hedefte duruyor. Kayıt komutunun
kendisi de aynı kapıyı geçiyor (Space/F5 düğmeye uğramıyor).

**Otomatik katılımcı oluşturma kaldırıldı**: `_current_session` artık ne
katılımcı yaratıyor ne de listedeki ilkine düşüyor. Projeler'de katılımcı
**oluşturmak onu seçmek** sayılıyor. Proje değişince eski projenin katılımcısı
taşınmıyor.

Kamera görüntüsündeki beden ile proje katılımcısı ayrı kavram olarak ayrı
bloklarda: **KAYIT HEDEFİ** (kaydın yazılacağı klasör) ve **GÖRÜNTÜDEKİ KİŞİ**
(kadrajdaki hangi beden).

## C-06 · Yakalama görünümü

Uyarı şeridi sayfadan çıktı; yerine konsolun altında yükseklik ayrılmış
**DURUM** bölmesi. Bloklar yüksekliklerini ilk gerçek yerleşimden sonra
ayırıyor. RGB kendi oranının kullanabileceği genişliği alıyor; kalan konsola
gidiyor. `QScrollArea` kaldırıldı; yükseklik yetmezse konsol **iki sütuna**
geçiyor.

Tam ekran ölçüm — `verified`. Kadraj hükmü beş durum arasında değişirken,
iki uyarı gelip giderken ve kişi seçilip bırakılırken **15 denetimin konumu
ve boyutu bit birebir aynı**:

| geçiş | yeri değişen denetim |
|---|---|
| kimse yok → tamam → ayak dışarıda → dar → kalabalık | **0 · 0 · 0 · 0 · 0** |
| iki uyarı geldi → gitti | **0 · 0** |
| kişi seçildi → bırakıldı | **0 · 0** |

| ölçüm | %100 (1920×1009) | %150 (1280×673) |
|---|---|---|
| RGB genişliği | **1319** | 600 |
| RGB yüksekliği | 742 | 406 |
| oran | **1,778** (= 16:9) | 1,478 (pencere dar; dikey letterbox) |
| konsol | 460 (okunur tavan) | 616 |
| konsol sütunu | **1** | **2** |
| konsol kaydırması | **0** | **0** |
| binen widget çifti | **0** | **0** |
| kırpılan denetim | **0** | **0** |

**Son ölçüm — `verified`.** `%100`'de bağlanma, kişi seçimi, gerçekten
başlayan sentetik kayıt ve durdurma dâhil bütün geçişlerde hareket **0**.
`%150`'de yalnız `marker_button` bağlanınca yatayda **1 px** kayıyor;
kayıt/durdurma bu farkı büyütmüyor. Mod etiketi artık güncel yazı tipi ve
status-pill boşluklarıyla ölçülüyor. Kayıt düğmesinin içerik yüksekliği
stilde sabit: `%150`'de kayıt başlayınca görülen **2 px** büyüme giderildi.

**Kanıt düzeltmesi — `superseded`.** Önceki manifestlerde
`recording_started: false` olduğu hâlde ekran görüntüsü "Kayıt sürüyor"
diye adlandırılmıştı; bunlar kayıt sırasındaki düzeni kanıtlamaz.
Yeni betik mock kamerada açıkça **sentetik seçim kutusu** üretir (eklemler
NaN kalır, CPU kişi tespiti kanıtı değildir), normal kişi seçimi ve kayıt
yolunu çalıştırır; kayıt durumu ve yazılmış kare sayısı doğrulanmadan
ölçüm yapmaz. Son iki manifestte `recording_started: true`; kayıt sırasında
kaydırma, binme ve kırpılma **0**. Her koşu ayrı geçici sandbox kullanır.

Canlı görüntüdeki "Kadrajda kimse yok" artık resmin üstüne basılmıyor; kişi
seçimi reddi yalnız bildirim kartı — aynı cümle iki yerde değil. Ret metni
durum değişene kadar tekrar edilmiyor. Kamera bağlı değil placeholder'ı, geri
sayım ve kayıt çerçevesi dokunulmadı.

## C-07 · Bildirim kartları

Kök neden: `QPushButton` metninden dar olduğunda ne sarar ne eler — metni
ortalar ve **iki uçtan keser**. Kart genişliği sabitti (400) ve eylem satırı
`QHBoxLayout`'tu.

Düzeltme: her düğme kendi metninin genişliğini gerçek yazı tipiyle ayırıyor;
eylem satırı **saran** `FlowLayout`; kart genişliği içeriğe göre büyüyor.
"Ayrıntılar" ayrı pencerede tam metni gösteriyor — teknik satır boşluksuz kod
listesi olduğu için bir etiket onu saramıyordu.

Bu sırada iki ölçüm hatası daha bulundu: katman yeniden yerleşimi
**özyinelemeliydi**, ve ölçüm **widget'ın önbellekli `sizeHint`'ini** okuyordu
— bir kez üç satır sarmış olarak ölçülen kart sonsuza dek o yüksekliği
bildiriyordu (134 px içerik için 286 px kart).

Tam ekran ölçüm — `verified`, gerçek kartla (`Etiketlemeyi aç` + `Sürüm
listesi` + `Ayrıntılar` + `Kapat`):

| | %100 | %150 |
|---|---|---|
| kart | 436×151 | 435×152 |
| kırpılan düğme | **0** | **0** |
| ayrıntı penceresi | 310 karakter, tam metin | aynı |

## C-08 · Bu turda bulunan ek görsel hata

**2B kaplamada köşeye giden kemikler.** Gerçek kaydın her karesinde bir yüz
eklemi gizlendiğinde sporcunun omzundan resmin sol üst köşesine dört beyaz
çizgi gidiyordu. ZED, resimde yerleştiremediği eklem için `(-1, -1)` yazıyor;
`-1` sonlu bir sayı olduğu için çizicinin `isfinite` kontrolü onu geçiriyordu.
Dizi sentinel'i **olduğu gibi** tutuyor (ham geçiş ham geçiştir); okuyucu artık
sürümün kendi geçerlilik maskesini soruyor ve negatif pikseli kendi başına
reddediyor. Gerçek sürümde kare 0'da çizilebilir eklem 38 → **34**.

## Testler

Bu turda yeni: `test_user_state_isolation.py` (6) ·
`test_recording_target.py` (6) · `test_subject_lock_recovery.py` (11) ·
`test_studio_capture_layout.py` (14) · `test_studio_toast_actions.py` (13) ·
`test_studio_review_overlay.py` (4).

Kuralı değişen eski testler yeni kurala göre yeniden yazıldı
(`test_studio_shell.py`, `test_studio_capture.py`,
`test_studio_capture_target.py`, `test_studio_library.py`,
`test_studio_toasts.py`, `test_studio_shell_gui.py`,
`test_studio_capture_row.py`, `test_studio_review_bands.py`). GUI fikstürleri
ya kapıdan geçiyor (`enter_the_workspace`) ya da sayfayı doğrudan gösteriyor
(`show_page_directly`); ikincisi yalnız ekranın kendi çizimini ölçen
dosyalarda ve gerekçesi orada yazılı.

Claude devir kapsamı: **28 kaynak dosyası** (biri yeni: `services/capture_layout.py`),
**22 test dosyası** (6'sı yeni).

**Codex koşusu — kısmi, kullanıcı isteğiyle durduruldu.** 95 dosyanın
**47**'si sonuçlandı: **45 yeşil, 2 başarısız**. Tamamlanan dosyaların toplam
süresi **784,7 sn**; bu tüm koşunun duvar saati süresi değildir. Kalan 48
dosyanın bu koşuda tamamlanmış sonucu yok. Kanıt:
`suite_stopped_by_user.json` ve `suite_final_logs/`.

- `test_capture_architecture.py`: ilk taramada iki gerçek konum regresyonu
  bulundu ve düzeltildi; izole **9/9** ve sonraki süpürmede yeşil.
  İlgili `test_subject_lock.py` **22/22**, `test_subject_lock_recovery.py`
  **11/11** izole geçti. Uzun çelişki sonrası dönüş için sonradan eklenen
  ek assertion yeniden koşulmadı.
- `test_processing_floor.py`: eski `1.2.0` beklentisi mevcut `1.3.0`
  sözleşmesine güncellendi; izole ve sonraki süpürmede **17/17** geçti.
- `test_processing_pipeline.py`: `test_pause_holds_the_job_and_resume_finishes_it`
  `paused` beklerken son durum `failed` görüldü. Bilinen aralıklı test ailesi;
  bu olayın aynı yarış olduğu **kanıtlanmadı**. Kullanıcı durdurduğu için
  üç izole tekrar yapılmadı. Uzun yolda proxy üretilemediği için ayrıca
  **1 test atlandı**.
- `test_studio_capture_row.py`: FPS için ayrılan `000.0` örneği yerine
  `00000` ölçen eski beklenti başarısız oldu (36/40 px). Test, tanımlı
  `_sample` genişliğini denetleyecek şekilde düzeltildi; **tekrar koşulmadı**.
- Yükseklik bütçesi regresyonu eklendikten sonra
  `test_studio_stage_layout.py` **22/22** geçti. Son kamera/kişi paneli
  düzenlemesi ve buna uyarlanan diğer testler **yeniden koşulmadı**.

Kullanıcının tercih, pencere ve kimlik dosyaları son SHA-256 kontrolünde
başlangıçla aynı: `user_state_before.json` / `user_state_after.json`.

## Kalan doğrulanmamış sınırlar

- **Gerçek kamerayla kayıt denenmedi**; kamera bağlı değil. Uzun yol
  reddi ve kurtarılabilir başlangıç **sentetik backend** ile sınandı, gerçek
  SDK reddiyle değil. SDK'nın `MAX_PATH` sınırı bu makinede Win32 çağrılarıyla
  ölçüldü; SDK'nın **kendi** hata kodu tekrar üretilmedi.
- **Gerçek uzun yollu bir projede gerçek kayıt** alınıp reddedildiği
  görülmedi; aynı nedenle.
- Canlı kamera, GPU ve kayıt kaybı önce/sonra ölçülmedi.
- Kurtarma yolu (`_try_recover`) gerçek kayıtta **tetiklenmedi**: yanlış veto
  kaldırıldığı için ihtiyaç kalmadı. Yalnız sentetik regresyonlarla sınandı.
- İki kişili **gerçek** kadraj hâlâ yok; yansıma tek gerçek ikinci bedendir.
- `rehab24_6_mocap` sentetik üretilemez; export hedefi olarak kalır.
- Identity veritabanındaki kırık proje kayıtları temizlenmedi (kullanıcının
  kararı).
