# KineCapture — Squat doğruluğu ve offline işleme incelemesi

10 Eylül 2026 · Salt okunur inceleme · Uygulama 0.10.0 · ZED SDK 5.4.1

Bu rapor, kullanıcının [inceleme görevi](C:/Users/gorke/Desktop/KineCapture/GPT6_ASTRA_KINECAPTURE_SQUAT_OFFLINE_INCELEME_GOREVI.md) üzerine hazırlanmıştır. Kaynak kodu, test kodu, şemalar, kullanıcı tercihleri, identity DB ve mevcut kayıtlar değiştirilmedi. Yalnız rapor ve MEMORY.md yazıldı; deneyler benzersiz geçici dizinde yürütüldü. Aşağıdaki geliştirme maddeleri öneridir; henüz uygulanmadı.

Kanıt etiketleri: **Bugün doğrulandı** = bu oturumda kod, dosya, log veya deneyle kontrol edildi; **Önceki ölçüm** = geçmiş ölçümün aktarımı, bugün aynı ham veriden yeniden üretilemedi; **Güçlü çıkarım** = birden fazla bulgunun desteklediği açıklama; **Hipotez** = kontrollü deney bekliyor; **Bilinmiyor** = mevcut kanıtla belirlenemedi. Logun bugün okunması, geçmiş deneyin bugün tekrarlandığı anlamına gelmez.

## 1. Kısa sonuç ve karar önerisi

**Güçlü çıkarım:** Squatta düz kalan dizin en olası açıklaması, özellikle önden görünümde alt gövdenin örtüşmesiyle birlikte SDK'nın poz tahmini/fitting yolunun yanlış bacak çözümüne yerleşmesidir. “Model squat görmedi” sonucunu destekleyecek eğitim verisi bilgimiz yok. Önceki yanlış karede SDK'nın 2B noktası da yanlıştı; yalnız depth veya uygulamanın çizimi sorunu açıklamıyor.

**Önceki ölçüm:** Aynı squat SVO'sunda BODY_34 ile kalan hata BODY_38 ile belirgin azalmıştı. Bu, BODY_38'i iyi bir başlangıç adayı yapar; iki klip ve tek sporcu, genellenebilir doğruluk kanıtı değildir. Bugün o ham squat kayıtları bulunmadığından bu açı ölçümlerini yeniden hesaplamadım.

**Bugün doğrulandı:** İki farklı eski SVO üzerinde offline BODY_38 yaklaşık **13,8–14,8 FPS** çalıştı. Kaynak 30 FPS olmasına rağmen, hızlı RGB geçişiyle aynı okunabilir kareleri sırasıyla işledi; yavaşlık ek kare atlamasına yol açmadı. Ancak dosyaların bildirdiği kare sayılarıyla okunabilen kare sayıları uyuşmadı. Bu yüzden deney çıktıları “eksiksiz” diye yayımlanmadı. Offline ürünün asıl gereksinimi yalnız model çalıştırmak değil, kapsamı doğrulamaktır.

**Bugün doğrulandı — yeni ve öncelikli:** Canlı depth arşivi yolunda SDK belleğinin yeniden kullanılmasından kaynaklanan veri bütünlüğü hatası var. Değiştirilmemiş arşiv yazıcısına üç farklı depth karesi gönderildiğinde, üçü de son karenin verisiyle saklandı. Bu hata, SDK'nın squat iskeletini neden yanlış tahmin ettiğinin açıklaması değildir; arşivlenen depth'in güvenilirliğini ayrıca etkiler.

**Önerilen yol:** Önce bu küçük veri bütünlüğü düzeltmesi ve kare/zaman ölçümü; ardından **Plan 2: yalnız ham SVO kaydı + sürümlü offline BODY_38**. Çoklu kişide önce offline görüntü kartlarıyla seçim; saha pilotunda koç yükü yüksek çıkarsa **Plan 3'ün hafif canlı seçim ipucu** eklenmeli. Plan 1'in desteklenen FPS, codec doğruluğu ve kurulum rehberi iyileştirmeleri bu yolu destekler. Plan 4, ölçülen doğruluk yetmezse açılmalı.

| İstenen açık cevap | Sonuç |
|---|---|
| Model squat görmediği için mi? | **Bilinmiyor.** Eğitim kümesine erişim yok. Görünüm/örtüşme ile model ve fitting davranışı daha güçlü açıklama. |
| BODY_38 ne kadar güvenilir? | **Önceki ölçüm:** aynı kayıtta umut verici; farklı sporculara genelleme henüz yok. Bugünkü eski videolar squat doğruluğu testi değil. |
| Offline yalnız FPS'i mi çözer? | Canlı süre baskısını kaldırır. Doğruluk için model/format seçimi, çekim açısı, görüntü kalitesi, kişi eşleme ve bağımsız QC gerekir. Aynı hatalı modeli daha yavaş çalıştırmak çözüm garantisi değil. |
| Raw-only kaynak FPS için yeterli mi? | **Hipotez:** güçlü aday. Body/depth hesaplama yanında float32 sıkıştırma, tam proxy ve gereksiz tam çözünürlük kopyaları da canlı hattan çıkmalı. USB, encoding ve disk sınırları ayrıca ölçülmeli. |
| Çoklu kişi koçu yormadan nasıl çözülür? | Her track için başlangıç/orta/son görüntü kartı, tek sporcu seçimi, zaman çizelgesinde önizleme ve yalnız belirsiz aralıklarda onay. Tracker ID'si katılımcı kimliği sayılmaz. |
| En küçük ilk değişiklik? | Onay sonrası SDK depth tamponundan sahip olunan kare kopyası üretmek ve tampon yeniden kullanımını yakalayan regresyon testi. Sonraki küçük adım, kaynak timestamp/kapsam ve aşama sürelerinin ölçümü; ardından capture-only teknik deneme. |

## 2. Bugünkü veri envanteri ve korunma durumu

**Bugün doğrulandı:** [Kullanıcı tercihi](C:/Users/gorke/.kinecapture/user_state.yaml), artık bulunmayan `C:\Users\gorke\AppData\Local\Temp\pytest-of-gorke\pytest-386\viewports0\datasets` kökünü gösteriyor. Salt okunur SQLite sorgusunda `prj_20260902T072943_e359` — KineSynth ve `prj_20260903T124439_8b0e` — Eklemtest proje kayıtları da bu geçici köke bağlı. Tercih ve DB düzeltilmedi; kalıcı projeler içe aktarılmadı.

**Bugün doğrulandı:** Erişilebilir kullanıcı profili taramasında iki SVO2 bulundu. Tarama, ilgisiz bir Windows CloudStore alt yolunda hata verdi; bütün diskler/yedekler üzerinde mutlak yokluk iddiası değildir. Kullanıcının kötü squat kayıtlarını kendisinin sildiği açıklaması esas alındı. Bunları istemsiz veri kaybı diye sınıflandırmıyorum.

| Kaynak | Bugün mevcut kanıt | Bu raporda kullanım |
|---|---|---|
| 2 Eylül kötü squat take'leri `075046_63e2`, `075335_36a0` | Ham SVO/tam stream bulunmadı; geçmiş ölçümler, log ve yedi tanı PNG'si var | Görsel hata ve geçmiş A/B aktarımı; yeni açı hesabı yok |
| 2 Eylül `113715_20ed` | Log: 610 kare, yaklaşık 43 s, 14,2 FPS; depth kuyruğunda 15 kayıp, PARTIAL | Performans ve arşiv kaybı olayı |
| 3 Eylül `124732_4a81` | Log: 1078 kare, 45,9 s, 23,4 FPS; ham take yok | Farklı testteki performans gözlemi; 15 → 23,4 kontrollü iyileşme kanıtı değil |
| A: 20 Ağustos kalıcı take | SVO, proxy, skeleton, take ve kalite metadata'sı | Offline fizibilite, zaman eşleme, checksum |
| B: 21 Ağustos kalıcı take | Aynı temel dosyalar; ayrıca eski annotation | Aynı teknik deneyler, depth tampon deneyi |

Kalıcı take yolları:

- A: [take_20260820T165211_daeb](C:/Users/gorke/KineCapture/datasets/projects/prj_20260820T164820_1e49/participants/P0001/sessions/ses_20260820T165034_c665/takes/take_20260820T165211_daeb/take.json)
- B: [take_20260821T111845_4ed7](C:/Users/gorke/KineCapture/datasets/projects/prj_20260821T111333_a60a/participants/P0001/sessions/ses_20260821T111428_c99a/takes/take_20260821T111845_4ed7/take.json)
- Geçmiş squat görselleri: [p165 RGB](C:/Users/gorke/AppData/Local/Temp/kinecapture_squat_diag_20260902/take075335_p165.png), [p165 bindirme](C:/Users/gorke/AppData/Local/Temp/kinecapture_squat_diag_20260902/take075335_overlay_p165.png). Bunlar yerelde incelendi; dış servise gönderilmedi.
- Olay kaynağı: [uygulama logu](C:/Users/gorke/KineCapture/logs/kinecapture.log:6193).

| Eski metadata | A | B |
|---|---:|---:|
| Uygulama / take / skeleton sürümü | 0.3.0 / 1.0.0 / 1.0.0 | 0.3.0 / 1.0.0 / 1.0.0 |
| Profil | HD720/30, MEDIUM, NEURAL_LIGHT, BODY_34, fitting açık | Aynı |
| Canlı stream kare sayısı | 668 | 230 |
| Süre / metadata FPS | 22,268 s / 29,9532 | 7,6671 s / 29,8679 |
| En az bir gövde bulunan kare | 613 (%91,77) | 230 (%100) |
| En büyük timestamp aralığı | 66,745 ms | 66,758 ms |
| Metadata backend drop sayacı | 4 | 86 |
| SVO boyutu | 37.191.407 bayt | 13.089.514 bayt |
| Mevcut kişi kilidi / ayrı depth arşivi | Yok; erken şema | Yok; erken şema |

**Bugün doğrulandı:** B'nin proxy örnek karesinde laboratuvarda oturan ana kişi ve sağ kenarda kısmen görünen ikinci kişi var. Bu bir squat doğruluk referansı değildir. BODY_38'in daha çok kişi bulması, doğru katılımcıyı seçtiğini veya daha doğru diz açısı ürettiğini tek başına göstermez.

**Bugün doğrulandı:** Güncel tercih HD720/30, QUALITY, ACCURATE, BODY_38, fitting açık, confidence 40, H264 tercihi, float32_lossless depth, preview 30 FPS. Bu ayar eski take'lerin provenance'ı yerine geçmez. Donanım RTX 2060 6 GB, i7-10750H 6C/12T, yaklaşık 15,84 GiB RAM; driver 616.56, Python 3.11.14, SDK 5.4.1. Kamera listesi boştu.

**Bugün doğrulandı:** Deney öncesi yaklaşık 207 GB boş alan vardı. Tam depth arşivi üretilmedi; tampon doğrulaması yalnız üç kareyle yapıldı. Kaynak/test/config dosyaları, pyproject, gerçek tercih, identity DB ve iki take içindeki dosyaları kapsayan 154 dosyanın hash ve değişiklik zamanları deneyler ve testler sonrasında aynı kaldı. Bu kontrol bütün kullanıcı diskini kapsamaz.

## 3. Kod, log ve deneylerde yeni bulgular

### 3.1. SDK depth tamponu arşivde farklı kareleri aynı veriye dönüştürebiliyor

**Bugün doğrulandı:** [zed.py:533](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/camera/zed.py:533), `np.ascontiguousarray(self._mat_depth.get_data(), dtype=np.float32)` kullanıyor. Yerel SDK'da `get_data()` varsayılanı `deep_copy=False`. Veri zaten bitişik float32 olduğunda `ascontiguousarray` kopya oluşturmuyor. Sonraki `retrieve_measure`, önceki kareye ait sanılan belleği değiştiriyor. [FramePacket](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/domain/models.py:371) sahip olunan kopya garantisi vermiyor; [RgbdArchiveWriter.add_frame](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/recording/rgbd_archive.py:431) de `np.asarray` ile bu belleği chunk dolana kadar tutuyor.

Deneyde önce her depth karesinin bağımsız referans kopyası alındı; uygulamadaki ifadeyle elde edilen tamponlar değiştirilmemiş yazıcıya gönderildi. Üç karelik chunk için sonuç:

| Arşiv konumu | Kendi özgün karesine eşit mi? | Üçüncü/son kareye eşit mi? |
|---|---|---|
| 0 | Hayır | Evet |
| 1 | Hayır | Evet |
| 2 | Evet | Evet |

`shares_memory(first,last)=true`; NaN'lar eşit kabul edilerek karşılaştırıldı. Ayrıca dört BODY geçişinin tampon denemelerinde önceki array'in sonraki retrieval ile değiştiği görüldü. Bu, sadece koddan şüphelenilen bir yarış değil, gerçek SDK belleği ve mevcut arşiv yazıcısıyla tekrarlanmış bozulmadır. Tam canlı GUI kaydının her chunk'ının aynı şekilde bozulduğunu ölçmedim; etkilenen geçmiş kare sayısı **bilinmiyor**.

**Güçlü çıkarım:** “Kayıpsız sıkıştırıldı” ile “doğru anın ölçümü saklandı” farklı koşullardır. Codec sayısal olarak kayıpsız olsa bile yanlış tampon sıkıştırılabilir. MEMORY.md'deki canlı depth'in birebir korunduğu genel kabul bu bulguyla sınırlandırılmalıdır. Eski canlı/replay depth farklarının büyüklüğü, bu hata dışlanmadan saf SDK farkı diye yorumlanamaz. SVO'dan üretilen depth yine `reconstructed_offline` sayılmalıdır; önceki ölçümün birebir geri getirildiği varsayılmamalıdır.

Önerilen küçük düzeltme: SDK sınırında açık sahiplik/kopya sözleşmesi; acquisition → writer geçişinde değişmez kare verisi; yeniden kullanılan tamponla regresyon testi. Kopyalama maliyeti ve kuyruk RAM'i ölçülmeli. Eski ham depth dosyaları düzeltilmiş değerlerle üzerlerine yazılmamalı. Bu arşiv hatası, SDK'nın kendi ürettiği skeleton geometrisinden ayrı tutulmalı.

### 3.2. Offline bütün okunabilir kareleri işledi; bildirilen kaynak sayısına ulaşamadı

**Bugün doğrulandı:** Her SVO için sıralı bir RGB geçişi ve BODY_34/BODY_38 geçişleri yapıldı. `svo_real_time_mode=False`, HD720 kaynak, 640×360 RGB retrieval; body deneylerinde ACCURATE + NEURAL_PLUS + fitting açık + confidence 40 + reduced precision kapalı kullanıldı. Model açılışı süre tablosuna dahil değil. Eski canlı MEDIUM/NEURAL_LIGHT profiliyle aynı deney değildir.

| Take / geçiş | SDK bildirimi | Okunan kare | Gövdeli kare | Çok gövdeli kare | İşlem süresi | İşlem FPS |
|---|---:|---:|---:|---:|---:|---:|
| A / RGB, depth kapalı | 668 | 667 | Uygulanmaz | Uygulanmaz | 9,607 s | 69,43 |
| A / BODY_34 | 668 | 667 | 609 | 34 | 39,197 s | 17,02 |
| A / BODY_38 | 668 | 667 | 615 | 20 | 45,055 s | 14,80 |
| B / RGB, depth kapalı | 230 | 229 | Uygulanmaz | Uygulanmaz | 3,520 s | 65,07 |
| B / BODY_34 | 230 | 229 | 226 | 0 | 13,322 s | 17,19 |
| B / BODY_38 | 230 | 229 | 229 | 229 | 16,601 s | 13,79 |

RGB hızları **SVO decoding ölçümüdür; canlı kayıt/NVENC performansı değildir**. BODY_38'de B'nin ikinci kişisinin her karede bulunması maliyete katkı verebilir; bunu tek değişkenli kişi sayısı deneyiyle ayırmadım.

**Bugün doğrulandı:** A'da konumlar 0–666; B'de 0–228 okundu. İç boşluk, tekrar eden konum ve ters timestamp yoktu. Bildirilen son konuma ayrıca seek yapıldığında da EOF döndü. Bu nedenle “100% bildirilen kaynak kapsamı” testi başarısız. Altı tam geçiş de `.partial.jsonl` olarak tutuldu; tam çıktı yayımlanmadı. **Bilinmiyor:** son konum davranışı SDK'nın sayım/EOF sözleşmesi, eski kayıt sınırı veya dosya sorunu mu? Dosyaların kayıtlı SVO hash'leriyle eşleşmesi, hatanın bu incelemede oluşmadığını gösterir; dosyanın baştan kusursuz olduğunu kanıtlamaz. Otomatik “N−1 normaldir” istisnası önerilmiyor.

### 3.3. Canlı skeleton konumu ve SVO konumu birebir değil

**Bugün doğrulandı:** İki take'te de canlı stream'in **ilk** karesi SVO'nun ilk okunabilir timestamp'inden yaklaşık 66,7 ms önce. Kalan canlı kareler mikro saniye çözünürlüğüne indirgenince SVO ile tam eşleşiyor:

- A: `live[1:]` içindeki 667 timestamp, `svo[0:667]` ile eşit; eşleşmeyen canlı ilk kare farkı 66,744899 ms.
- B: `live[1:]` içindeki 229 timestamp, `svo[0:229]` ile eşit; eşleşmeyen canlı ilk kare farkı 66,757700 ms.

Buradaki eksik eşleşme “canlı son kare kayboldu” değildir. Bildirilen son SVO konumunun okunamaması ile canlı ilk karenin eşleşmemesi ayrı gözlemlerdir; aralarındaki nedensellik kanıtlanmadı. **Güçlü çıkarım:** skeleton dosyasını offline sonuçla aynı ad altında değiştirmek eski annotation sınırlarını bir konum kaydırabilir. Timestamp tabanlı açık eşleme ve sürüm bağlama zorunludur.

### 3.4. Codec beyanı ve kaynak sayaçları gerçeği tam temsil etmiyor

**Bugün doğrulandı:** [start_native_recording](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/camera/zed.py:649), profil seçimini kullanmadan `H264` geçiriyor. [Manifest](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/recording/take_writer.py:714), profil tercihinden compression/lossless yazıyor. Bugünkü tercih zaten H264 olduğundan bu tercih için uyuşmazlık gösterilmedi; farklı codec seçildiğinde beyan ile çağrı ayrışabilecek kod yolu mevcut. H264 kayıplıdır; “lossless-by-default” açıklaması yanıltıcı. SVO'nun korunması, görüntü sıkıştırmasının kayıpsız olduğu anlamına gelmez. [Resmî recording belgesi](https://docs.stereolabs.com/docs/development/zed-sdk/modules/camera/recording) codec seçeneklerini ve NVENC yolunu açıklar.

**Bilinmiyor:** Eski iki SVO'nun gerçek codec'i. Playback'te `get_recording_parameters()` H265 döndürdü; yeni bir `RecordingParameters` nesnesinin varsayılanı da H265. Getter'ın kaynak container codec'ini gösterdiği kanıtlanmadığından eski dosyalara H265 etiketi koymadım. Gelecekte requested, SDK'ya applied ve güvenilir readback ayrı tutulmalı; readback doğrulanamıyorsa `unknown` yazılmalı.

**Bugün doğrulandı:** [zed.py:538](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/camera/zed.py:538) kare indeksini her başarılı grab'de yerel artırıyor. [Manifestteki](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/recording/take_writer.py:697) “kameranın kendi sayacı; kare düşünce ayrışır” açıklaması bu backend için doğru değil. `missing_frame_indices=0`, sensör karelerinin eksiksiz yakalandığını kanıtlayamaz. Backend drop sayacı da take başına sıfırlanmış delta olarak yorumlanmamalı; geçmiş metadata'daki 4/86 değerleri kayıt içi kayıp adedi sayılmamalı. Gerekli ayrı ölçüler: acquisition ordinal, kamera timestamp'i, varsa doğrulanmış fiziksel source counter, take başı/sonu drop deltası, SVO decoding kapsamı ve writer kaybı.

### 3.5. Kapanış, checksum ve yeniden işleme için sözleşme açıkları

**Bugün doğrulandı — kod yolu:** [stop_recording](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/capture/service.py:599) native kaydı durdurduktan sonra writer kuyruğuna sentinel koyuyor; acquisition döngüsü bu sırada `_writer` var oldukça paket ekleyebiliyor. Writer için zaman aşımı sonrası yalnız log yazılıp finalize'a devam edilebiliyor; dolu kuyruğa sentinel koyma çağrısında ayrı zaman aşımı yok. **Hipotez:** sınırda kuyruk/sentinel yarışı veya yavaş kapanış, akış sınırlarını ayrıştırabilir. Bugünkü eski dosya eşleme farkının kesin nedeni olduğunu iddia etmiyorum. Başlat/durdur bariyeri ve fault-injection testi gerekli.

**Bugün doğrulandı:** [TakeWriter.finalize](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/recording/take_writer.py:635) tamamlanmış take'i checksum dosyasından önce kaydediyor. Tek tek dosyaların atomik yazılması, bütün çok dosyalı işlemin atomik olduğu anlamına gelmiyor. Süreç bu arada kapanırsa doğrulama belgesi olmadan tamamlanmış görünen take kalabilir; bu tur süreç öldürme deneyi yapılmadı.

**Bugün doğrulandı:** İki eski take'te mevcut checksum belgesine göre SVO, proxy ve skeleton eşleşiyor; **iki take.json hash'i de eşleşmiyor**. Bu uyumsuzluk inceleme öncesinde de vardı; inceleme öncesi/sonrası take.json hash'leri aynı. **Güçlü çıkarım:** [kayıt sonrası kalite/not kaydı](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/gui/pages/capture.py:1299) take.json'u değiştirip checksum'u güncellemediği için olağan kullanıcı düzenlemesiyle bu durum oluşabilir. Geçmiş iki değişikliğin fiilî nedeni bilinmiyor. Değişmez ham varlık manifesti ile değişebilir kalite, not ve iş durumu ayrılmalı.

**Bugün doğrulandı:** 40 karede kooperatif iptal denendi; kaynak hash'i korundu ve yalnız staging/partial çıktı kaldı. Bu, güvenli iptalin sınırlı kanıtıdır. İşletim sistemi çökmesi, elektrik kesintisi, tracker durumuyla resume ve başarılı atomik publish yolu denenmedi. Tam geçişler kapsam kontrolünü geçmediği için publish başarı testi sayılmaz.

### 3.6. Raw-only bir ayar değişikliğinden daha büyük

**Bugün doğrulandı:** Backend body modülünü kapatabiliyor ve depth NONE açılabiliyor; SDK ile SVO okuma da çalıştı. Ancak mevcut uygulamada SVO input backend'i veya genel offline iş kuyruğu bulunmadı. Normal bağlantı yolu fiziksel cihaz arıyor. CaptureMode mevcut guided/free iş anlamını taşıyor; aynı enum içine inference modu sıkıştırılmamalı.

**Bugün doğrulandı:** TakeWriter skeleton ve proxy merkezli; [load_take](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/playback/take_reader.py:671) sabit skeleton/proxy yollarını açıyor; inceleme kare sayısı skeleton'dan geliyor. [usable_for_export](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/domain/project.py:565) finalize ve kaliteye bakıyor, offline iş/QC hazır olma durumunu bilmiyor. `Take.from_dict` bilinmeyen alanları koruyan genel bir sürüm deposu değil. Yeni JSON alanı eklemek reader/export davranışını kendiliğinden düzeltmez. Boş skeleton dosyası oluşturup raw-only take'i normal tamamlanmış veri gibi göstermek uygun değil.

### 3.7. Çoklu kişi ve GUI ölçümleri

**Bugün doğrulandı:** Mevcut SubjectLock, 2B keypoint tıklaması, body ID, kök konumu ve beden oranlarından yararlanıyor. Eşzamanlı görülen başka ID'leri elemesi yararlı; fakat aynı tracker ID'si geri geldiğinde hızlı yol güveniyor. ID'nin başka kişiye yeniden verilmesi, sıfır yanlış bağlanma garantisini engeller. Bounding-box ipucu için mevcut sınıf doğrudan kullanılamaz; ortak audit ve belirsizlik ilkeleri yeniden kullanılabilir. [SubjectLock](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/capture/subject_lock.py:447)

**Bugün doğrulandı:** [select_subject](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/capture/service.py:219), tıklanan body ile birlikte görüntülenen paketin timestamp'ini almak yerine yeniden `peek_frame()` çağırıyor. Yeni seçim ipucu, koçun gerçekten gördüğü karenin timestamp'i ve koordinat dönüşümüyle kaydedilmeli.

**Bugün doğrulandı:** `tracking_coverage`, herhangi bir kişi bulunmasını sayıyor. [subject_coverage](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/domain/project.py:482) paydasına ambiguous kareleri katmıyor. Arka plandaki kişi takip edilirken yüksek genel coverage veya belirsiz aralıklar dışlanınca yüksek subject coverage görülebilir. Ürün, seçili sporcu kapsamını tüm ilgili kaynak kareleri üzerinden vermeli; locked/lost/ambiguous/no-detection ayrı gösterilmeli. Henüz işlenmemiş veri “%0 takip başarısı” sayılmamalı.

### 3.8. Gerçekte çalıştırılan kontroller ve hafıza çelişkileri

**Bugün doğrulandı:** SDK topoloji kontrolü BODY_18 için 18 eklem/19 bağlantı, BODY_34 için 34/35, BODY_38 için 38/37 eşleşmesi verdi. Uygulamanın keypoint aktarımında diz geometrisini gizlice düzleştiren bir dönüşüm bulunmadı. Bu, SDK pozunun anatomik doğruluğunu doğrulayan bir test değildir.

**Bugün doğrulandı:** Altı ilgili test dosyası kısa, izole temp köküyle **143 passed in 23.73s** verdi: zed adapter, capture, RGB-D archive, subject lock, storage ve capture subject GUI. İlk aynı kapsamlı koşu uzun deney dizininde 13 failure ve 14 setup error verdi; WinError 3 dosya yolu sorunları görüldü. Kısa kökle tekrar geçti. MEMORY.md'deki uzun yol sorununu yalnız proxy ile sınırlayan eski ifade bu deneyle uyumlu değil; metadata taraması/depth dosyası erişimi de etkilendi. Kısa yol kullanmak bu sorunu çözülmüş yapmaz.

Testler mevcut offscreen GUI davranışlarını kapsar; gerçek koç kullanımı, canlı kamera veya yeni offline ürün akışı doğrulanmadı. Arşiv testlerinin geçmesi, yeniden kullanılan SDK tamponunu sınamadıkları için 3.1'deki hatayı çürütmez. Tam test paketi ve self-test çalıştırılmadı. Başlangıç Git ağacı temizdi; görev belgesindeki eski dirty liste HEAD'e alınmış durumdaydı, kullanıcı işi geri alınmadı.

## 4. Squat kök nedenlerinin olasılık sırası

Sıra, nicel olasılık hesabı değildir. İlk maddeler aynı neden zincirinin parçaları olabilir. **Bugün doğrulanan arşiv hatası** bu tablodaki SDK iskelet hatasıyla karıştırılmamalıdır.

| Sıra / aday | Kanıt ve karşı kanıt | Sınıf | Doğrulayacak veya zayıflatacak deney |
|---|---|---|---|
| 1. 2B poz tahmini + önden sagittal hareket/örtüşme | Önceki yanlış dizin SDK 2B noktası da yanlış; görüntüde gerçek bükülme var. Kalça/diz/ayak bileğinin görüntüde üst üste gelmesi yanlış çözüme elverişli. | **Güçlü çıkarım**; 2B ölçüm ayrıntısı **Önceki ölçüm** | Aynı sporcuda ön/oblik/yan, eşit profil; dip karelerde bağımsız 2B işaretleme. Örtüşme yokken de aynı hata sürerse açı açıklaması zayıflar. |
| 2. BODY_34/BODY_38 formatına bağlı tahmin/fitting davranışı | Aynı eski SVO'da 34 düz diz bırakırken 38 bükülme üretti. İki formatın SDK 5.4.1'de bütün iç ağ farkları açıklanmış değil; yalnız daha çok eklem olduğu için düzeldi denemez. | **Önceki ölçüm**, genelleme **Bilinmiyor** | En az 5 sporcunun aynı SVO'larında 34/38 karşılaştırması; aynı model seviyesi/depth/fitting/precision. İyileşmenin kişi ve açı bazında tekrarı. |
| 3. Fitting/prediction'ın yanlış pozu sürdürmesi | Fitting geçmiş ve insan kinematiği kullanıyor; uygulamada açık. Yerel smoothing 0, prediction timeout yaklaşık 0,2 s. | **Hipotez** | Desteklenen formatta fitting ve prediction timeout ayrı A/B; 34'te fitting gerekliliğini ihlal etmeden. Tam resetli replay ve dipten önce/sonra hata süresi. |
| 4. Alt beden piksel alanı, koyu kıyafet/zemin, ayak örtülmesi | Görsel belirsizliği artırabilir; bunları izole eden kayıt yok. | **Hipotez** | Mesafe, ışık, kıyafet ve arka planı tek tek değiştir; ayak görünürlüğü ve alt beden piksel boyutunu kaydet. |
| 5. Depth kalitesi/modu | 3B konumu etkileyebilir; fakat yanlış 2B tahmini tek başına açıklamaz. NEURAL_PLUS kullanılmış olması doğru poz garantisi değil. | **Hipotez**, tek neden olarak zayıf | Aynı kaynakta NEURAL_LIGHT/QUALITY/NEURAL_PLUS; 2B hata ile doğru 2B fakat yanlış depth durumunu ayır; sahip olunan canlı depth kopyalarıyla karşılaştır. |
| 6. Düşük FPS ve büyük zaman aralıkları | 14–15 FPS ve 133–334 ms eski aralıklar tracker'ı zorlayabilir. Aynı BODY_34'ün offline eski kaynakta hatayı sürdürmesi FPS'in tek neden olmadığını gösterir. Offline, çekimde zaten kaydedilmemiş hareketi geri getiremez. | **Güçlü çıkarım** destekleyici etken | Tam kaynak hızlı klip ile kontrollü seyreltilmiş türevi karşılaştır; timestamp'leri koru, tracker'ı yeniden başlat. Sonra gerçek raw-only kayıtla karşılaştır. |
| 7. H264 sıkıştırma | İnce ayrıntıyı bozabilir; aynı kaynakta yalnız format değişimiyle iyileşme bunu başat açıklama olmaktan uzaklaştırıyor. Yerel codec A/B yok. | **Hipotez** | H264/H264_LOSSLESS/LOSSLESS, eşleşen protokol; dip keypoint hatası, görüntü ayrıntısı, FPS, boyut ve encoder yükü. |
| 8. Uygulamada indeks/projeksiyon/bindirme/confidence ölçeği | Bugünkü topoloji eşleşiyor; aktarımda gizli düzeltme yok. Önceki reprojection medyan 0,00/p95 0,01 px; yanlış diz confidence yaklaşık 0,971. Sırf confidence artırmak elemez. | Kod/topoloji **Bugün doğrulandı**; sayılar **Önceki ölçüm** | Yeni hatalı karede SDK doğrudan 2B/3B çıktısı, kaydedilen stream ve GUI karşılaştırması; ölçek ve eklem isimleri kontrolü. |
| 9. “Eğitimde squat yoktu” | Eğitim örnekleri/squat dağılımı bilinmiyor. Model davranışından veri kümesinin yokluğu çıkarsanamaz. | **Bilinmiyor** | Üreticinin eğitim/validasyon açıklaması veya ilgili veri erişimi; yerel hata tek başına bu iddiayı kanıtlamaz. |

SDK belgeleri, görüntüden 2B tahminin depth/positional tracking ile 3B'ye taşındığını; fitting'in tarihçe ve kinematik kısıt kullandığını söylüyor. Eklem noktaları kalibre edilmiş anatomik merkezler değil, öğrenilmiş tahminlerdir. Bu nedenle sporcu ve kurulum özelinde bağımsız referans gerekir. [Stereolabs Body Tracking Overview](https://docs.stereolabs.com/docs/development/zed-sdk/modules/body-tracking)

Önceki BODY_38 dip değerleri 45–61° ve BODY_34'ün 178,8–179° değerleri, kalça–diz–ayak bileği vektörleri arasındaki **iç açı** olarak okunmalı; 180° düz bacağa karşılık gelir. Klinik fleksiyon açısı gibi 0° düz bacak kabul eden tanımla karıştırılmamalı. Önden tek 2B referans da gerçek 3B fleksiyon için yeterli ground truth değildir.

## 5. Canlı performans bütçesi ve çıkarılabilecek işler

**Bugün doğrulandı — kod akışı:** Acquisition thread `grab → RGB retrieval/dönüşüm → depth retrieval → body retrieval → preview yayını → kayıt kuyruğu` sırasını izliyor. Native SVO encoding SDK'nın kayıt/grab yolunda. Writer thread skeleton serileştirme, proxy ve depth chunk hazırlama yapıyor; depth sıkıştırma işçileri ayrıca çalışıyor. GUI ayrı timer ile son paketi çiziyor. Ayrı thread kullanılması GPU, bellek bant genişliği, CPU ve diskin ortak bütçesini ortadan kaldırmıyor.

30 FPS'te kaynak kare bütçesi 33,33 ms. Eski 14–15 FPS yaklaşık 67–71 ms/kare mertebesinde. Bugünkü host API süreleri:

| Offline profil | grab medyan / p95 | RGB alma medyan / p95 | Body alma medyan / p95 |
|---|---:|---:|---:|
| A / 34 | 47,97 / 53,90 ms | 0,90 / 1,48 ms | 7,98 / 12,62 ms |
| A / 38 | 50,29 / 56,62 ms | 1,00 / 1,71 ms | 15,40 / 24,10 ms |
| B / 34 | 47,79 / 53,18 ms | 0,92 / 1,52 ms | 7,46 / 10,06 ms |
| B / 38 | 48,92 / 56,01 ms | 1,03 / 1,75 ms | 20,17 / 26,82 ms |

**Bugün doğrulandı, sınırlı ölçüm:** Bunlar Python tarafında duvar saati süreleri; GPU kernel profiling değil. `grab` depth dahil SDK işlerini kapsayabilir; 48–50 ms'nin tamamını saf depth diye etiketlemiyorum. Body sütunu SDK retrieval yanında keypoint dizilerini Python listelerine hazırlamayı da içeriyor. RGB retrieval 640×360; uygulamanın tam çözünürlük alma/dönüştürme yoluyla aynı maliyet değil. Medyanlar bağımsız olduğu için satır toplamı kesin kare süresi değildir. JSON yazımı/diğer işler toplam süreye dahil; tam proxy ve tam depth arşivi yok. Açılış, uzun oturum, ısınma ve disk baskısı kontrollü canlı benchmark yapılmadı.

| Aşama | Mevcut kanıt / zorunluluk | Önerilen değişiklik ve ölçüm |
|---|---|---|
| Kamera grab + native encoding | Kaynak için zorunlu. **Bilinmiyor:** bu makinede capture-only canlı maliyeti. | Kaynak 30 FPS, body/depth kapalı SVO denemesi. Encoding durumu, acquisition timestamp'i, per-take drop deltası, CPU/GPU/NVENC/disk yazımı. |
| RGB retrieval ve kopyalar | **Bugün doğrulandı:** her grab'de tam görüntü alınıp dönüştürülüyor. | SVO her kareyi alırken yalnız preview gerektiğinde düşük çözünürlüklü RGB iste; ayrı preview paketi. Kaynak hızı azaltılmasın. |
| Depth compute/retrieval | Ağır SDK yolunun parçası; saf maliyet ayrılmadı. | Raw-only'de modül ve retrieval kapalı. Live modda depth-only A/B; stabilizasyon/positional tracking gereksinimleri birlikte doğrulansın. |
| Body inference/fitting/tracking | Bugünkü 38 retrieval'ı 34'ten daha pahalı; kişi sayısı da değişiyor. | Raw-only'de kapalı; offline ACCURATE/38 başlangıç. Canlı ipucu için ayrı düşük maliyetli detector bütçesi. |
| Skeleton JSONL | Doğru zamanda tüm tespitleri korumak gerekli; maliyeti tek başına ölçülmedi. | Offline'a taşı; tespitsiz karede de boş detection satırı yaz. Yazma süresi/bayt ölçümü. |
| Proxy video | İnceleme kolaylığı; native kaynak için zorunlu değil. | Raw-only'de sonradan üret; kaynak timestamp eşlemesini koru. Preview ile proxy aynı iş değil. |
| Lossless float32 depth | **Bugün doğrulandı:** logda kuyruk taşması; ayrıca tampon sahiplik hatası. | Önce sahiplik düzeltmesi. Raw-only'de hiç canlı depth ölçülmediği açıkça beyan edilerek kapat; gereken offline depth'i ayrı türetilmiş ürün yap. |
| GUI repaint | **Bugün doğrulandı:** preview timer acquisition'dan zaten ayrı. | Sadece FPS slider düşürmek SDK hesaplarını/kopyaları kaldırmaz. 10–15 FPS/uygun preview boyutu adaylarını GUI tepkisiyle ölç. |
| Kuyruk/disk/kapanış | Sonlu kuyrukta taşma ve kapanış yarışı riski var. | Kuyruk doluluk/zaman, yazma gecikmesi, bytes/s, RAM ve stop süresi; sonlu bellek bütçesi, kayıt öncesi alan kontrolü, sessiz kayıp yerine açık partial. |

Resmî belgeler H264/H265'in NVENC ile düşük ek yük amaçladığını ve SVO playback üzerinde SDK modüllerinin çalışabildiğini doğruluyor; bu, yerel 30 FPS garantisi değildir. [Video Recording](https://docs.stereolabs.com/docs/development/zed-sdk/modules/camera/recording)

**Öneri:** NEURAL_LIGHT/QUALITY ile NEURAL_PLUS ayrı karşılaştırılsın. Resmî depth belgeleri NEURAL_PLUS'ı daha pahalı seçenek olarak tanımlar; başka GPU/SDK için verilen FPS tabloları RTX 2060'a taşınmamalı. [Depth Modes](https://docs.stereolabs.com/docs/development/zed-sdk/modules/depth-sensing/depth-modes)

**Bugün doğrulandı:** SDK 5.4.1'de `allow_reduced_precision_inference=False`, runtime smoothing 0, minimum keypoint threshold 0, prediction timeout yaklaşık 0,2 s; init depth stabilization varsayılanı 30. `set_as_static` mevcut. Offline karşılaştırmada tam precision korunmalı; FAST/MEDIUM veya reduced precision yalnız kontrollü canlı ipucu adayı. BODY_34 fitting gerekliliği yüzünden fitting kapalı deneyi her format için geçerli sayılmamalı. [Body Tracking API](https://www.stereolabs.com/docs/development/zed-sdk/modules/body-tracking/using-the-api)

**Öneri:** Sabit kamerada positional tracking static ayarı ve stabilizasyon 0/30 A/B yapılabilir. Stabilizasyonu kapatmanın hesap yükü/kararlılık dengesi vardır; depth menzilini kısaltmanın doğrudan FPS artışı sağlayacağı varsayılmamalı. Depth confidence ile keypoint confidence'ın yönleri farklıdır; ortak eşik gibi kullanılmamalı. [Depth Settings](https://docs.stereolabs.com/docs/development/zed-sdk/modules/depth-sensing/depth-settings)

Düşük çözünürlüklü depth retrieval mümkün olsa da bu, ağın daha ucuz inference yaptığı anlamına gelmez. [Depth API](https://docs.stereolabs.com/docs/development/zed-sdk/modules/depth-sensing/using-the-api) **Bugün doğrulandı:** mevcut FramePacket, RGB ve depth için aynı H×W boyutunu istiyor. Live modda düşük çözünürlüklü önizleme ayrı ürün olmalı; arşiv için gereken tam ölçümün yerine sessizce konmamalı.

**Hesap / kapasite önerisi:** Ondalık GB ile sıkıştırılmamış tek float32 depth: HD720/30 için 6,64 GB/dakika; HD1080/30 için 14,93 GB/dakika. Eski byteshuffle+zip ölçümü yaklaşık 3,53 GB/dakika ve H264 SVO yaklaşık 96 MB/dakika idi (**Önceki ölçüm**, sahneye bağlı; yeni tampon hatası nedeniyle depth ölçümünün temsil gücü yeniden sınanmalı). Eski H264_LOSSLESS yaklaşık 1,12 GB/dakika, LOSSLESS yaklaşık 2,95 GB/dakika değerleri de genel kapasite garantisi değildir. Bugünkü iki eski SVO yaklaşık 100–102 MB/dakika mertebesinde; bundan codec kimliği çıkarılamaz.

HD1080 RGB uint8 + sahip olunan float32 depth için 120 paket yaklaşık **1,74 GB yalnız görüntü payload'u** eder. On beş depth karelik chunk yaklaşık 124 MB; işçi ve bekleyen chunk'lar ek RAM ister. Kuyruğu büyütmek, sürdürülemeyen yazma hızını düzeltmez. Özellikle sahiplik hatası giderildiğinde gerçek bellek ihtiyacı görünür hale gelecektir. Disk tahmini kaynak codec'i, offline depth saklama politikası ve yeni sürüm sayısını ayrı göstermeli; offline iş başlamadan staging + nihai çıktı için alan ayrılmalıdır.

## 6. Dört uygulanabilir planın karşılaştırması

Bu bölümdeki süre ve etkiler **mühendislik tahminidir**, tamamlanmış iş veya ölçülmüş kazanım değildir. Varsayım: mevcut kodu bilen bir geliştirici, mevcut KineSynth ortamı, kamera erişimi ayrıca sağlanacak, test ve temel GUI entegrasyonu dahil. Saha organizasyonu, satın alma, bilimsel validasyon ve yeni model eğitimi süreleri hariç. Planlar alternatif kapsamlar taşır; süreleri birbirine toplanmamalı. Ortak veri bütünlüğü ve gözlemleme tabanı yaklaşık 2–4 iş günü olarak ayrıca ayrılmalı.

| Karşılaştırma alanı | Plan 1 — Mevcut canlı hattı iyileştir | Plan 2 — Raw-only + offline BODY_38 | Plan 3 — Hafif canlı kişi ipucu + offline | Plan 4 — Doğruluk için alternatif model / çoklu görüş |
|---|---|---|---|---|
| Kısa açıklama | Desteklenen FPS, BODY_38, daha hafif depth, preview ayrımı ve çekim rehberi; aynı temel kayıt mimarisi | Canlı yalnız değişmez stereo SVO + hafif RGB; iskelet/proxy/gereken depth daha sonra | Plan 2'ye düşük frekanslı kişi kutusu ve timestamp'li seçim ipucu ekle | BODY_38 QC başarısızlığında alternatif sürüm; gerekirse stereo pose fusion veya senkron ikinci kamera |
| Canlı capture FPS etkisi | İyileşme olası; 30 garanti değil. Body/depth/arşiv bütçesi sürer | Kaynak hıza yaklaşmak için en güçlü sadeleştirme; canlı deneme henüz yok | Plan 2'den ek CPU/GPU yükü; ipucu kaynak kayda engel olmamalı | Ham kayıt Plan 2'ye benzer; ikinci kamera USB/disk yükünü büyütür |
| Squat doğruluğu etkisi | BODY_38 ve oblik açı aday; hafif depth/model ters etki yapabilir | Tam kaynakta ACCURATE/38 ve alternatif replay mümkün; semantik hata kendiliğinden çözülmez | Nihai doğruluk Plan 2 ile aynı; temel kazanç doğru sporcuyu ilişkilendirme | En yüksek araştırma potansiyeli; kalibrasyon ve referans olmadan üstünlük iddiası yok |
| Çoklu kişi | Mevcut skeleton tıklaması; kaybolma/ID dönüşünde açık teyit | Offline tüm track'ler → görüntü kartları → bir sporcu seçimi → belirsiz aralık kontrolü | Canlı seçilen kutu yalnız ipucu; offline track'lerle timestamp/örtüşme eşleme; belirsizde koç | Aynı kişi farklı model/kameralarda eşlenir; yanlış eşleme maliyeti daha yüksek |
| Koç akışı | Katılımcı → Canlı iskelet → kişiyi tıkla → kayıt → inceleme | Katılımcı → Hızlı kayıt → kayıt → kuyruk → sporcu seç → işaretli bölümleri kontrol et | Katılımcı → Hızlı kayıt → sporcuyu tıkla → kayıt → önerilen kişiyi teyit et | Koç aynı akışı görür; “Alternatif sonuç kontrol istiyor”; teknik kalibrasyon ayrı görev |
| Depolama | Mevcut SVO + proxy + canlı depth; yüksek maliyet sürer | Capture'da büyük depth arşivi yok; SVO + küçük ledger. Sonradan proxy/skeleton, gerekirse offline depth ve ek sürümler | Plan 2 + küçük ipucu/audit ve yerel thumbnails | Model sürümleri ve olası ikinci SVO; stereo kaynak yaklaşık kamera sayısıyla artar, kesin oran ölçülür |
| İşlem/kuyruk | Canlı süre bütçesi zorunlu; writer taşmasına çözüm gerekir | Bir GPU işi; kaynak süresinden uzun olabilir. Gece/sonra işle, kayıt başladığında duraklat, iptal/yeniden dene | Aynı kuyruk; offline bütün track geçişi ve ipucu eşleme | Alternatif işler seçici çalışır; ağır iş istasyonu seçeneği, daha uzun kuyruk |
| Şema/provenance | Codec applied/requested, doğru sayaç anlamı ve QC metadata; küçük ama açık sürüm kararı | Capture/processing/QC ayrı durum; immutable derived sürümü, kaynak hash, frame map, annotation/export bağı | Plan 2 + canlı hint şeması, koordinat ve timestamp, ilişkilendirme revizyonu | Modelden bağımsız skeleton spec, kamera kalibrasyonu/zaman eşleme, yöntem ve referans sürümü |
| Kod büyüklüğü | Küçük–orta; capture/backend/ayar/QC | Büyük; backend, writer, domain, worker, reader, annotation, dataset/export ve GUI | Plan 2 üzerine orta ek kapsam; farklı detector/tracker adaptörü | Büyük ve araştırma belirsizliği yüksek; seçilen alt yönteme göre değişir |
| Test zorluğu | Orta; gerçek kamera hız/kalite A/B gerekir | Yüksek; EOF/count, sıralama, tespitsiz kare, cancel/crash/disk, legacy ve annotation sürümü | Yüksek; kalabalık, ID değişimi, önde kesişme, stale preview, yanlış ipucu | Çok yüksek; senkronizasyon, kalibrasyon, model farkı ve bağımsız doğruluk referansı |
| Ana risk / geri dönüş | Hafif profil daha hızlı ama daha yanlış olabilir; profil bazında eskiye dön | “Tamam” görünen eksik/yanlış kişili veri; özellik bayrağıyla yeni modu kapat, eski take/derived sürümleri koru | İpucunun yanlış kişiye kayması; ipucunu devre dışı bırakıp Plan 2 offline seçime dön | Karmaşıklık ve maliyet doğruluğu artırmayabilir; BODY_38 sürümünü ve tek kamera kaydını koru |
| Tahmini iş yükü | Ortak tabandan sonra 3–6 iş günü | Ortak tabandan sonra 15–25 iş günü; 2–4 günlük teknik deneme bu kapsamın yalnız başlangıcı | Plan 2 kapsamıyla toplam yaklaşık 20–35 iş günü; ek 5–10 gün | İlk sınırlı araştırma/karşılaştırma 6–12 hafta; satın alma, saha ve eğitim ek süre |
| Öncelik | **Hemen:** ölçüm ve güvenli profil iyileştirmeleri | **Ana yön:** aşamalı ürün geliştirme | **Sonra:** koç yükü pilotta gerektirirse | **Araştırma:** BODY_38 doğruluk kapısını geçmezse |

Önceki 1–2 hafta ürün tahmini dar kalıyor: bugünkü indeks farkı, tampon sahipliği, raw-only state/export sözleşmesi ve tracker resume davranışı yalnız “SVO açıp model çalıştırma” kapsamına sığmıyor. Kapsamı azaltılmış teknik deneme yine 2–4 günde mümkün olabilir; güvenilir koç ürünü ile karıştırılmamalı.

### Plan 2 için önerilen veri ve iş sözleşmesi

Aşağıdaki tasarım henüz uygulanmadı; yeni sürüm numaraları bu turda atanmadı.

1. **Kayıt yaşam döngüsü ile işleme durumunu ayır.** Capture `recording / finalized / partial`; kaynak doğrulaması `pending / valid / mismatch`; processing `awaiting / queued / processing / paused / cancelled / failed / processed`; insan kontrolü `needs_review / approved / rejected`. Nihai isimler domain tasarımında sadeleştirilebilir, fakat birbirinden bağımsız gerçekler tek “tamam” alanına sığdırılmamalı. Tam kapanmış raw-only kayıt, iskeleti henüz yokken de geçerli ham varlık olabilir. Export için doğrulanmış kaynak/istenen kapsam, seçilmiş derived sürüm, kişi eşleme ve gerekli QC birlikte aranmalı.
2. **Kaynak zaman çizelgesini iskeletten bağımsız kur.** Başarılı grab başına camera timestamp, capture ordinal, native recording etkinliği ve varsa doğrulanmış source counter yaz. Offline'da SVO position ve timestamp'i bu ledger ile eşle. Sayaç yoksa yok yaz; yerel sayacı fiziksel kamera sayacı diye sunma. SDK'nin declared count'u, decoded count ve kayıttaki ledger sayısı ayrı değerler olsun. Mikro saniye timestamp nicemlemesi açık toleransla ele alınsın. Aynı timestamp tekrar ederse yalnız yakın komşulukla sessiz eşleme yapılmasın.
3. **Ham varlığı değişmez tut.** Kaynak SVO hash'i, boyutu, kayıt sınırı, calibration, units/coordinate system, requested/applied codec ve actual FPS kaydedilsin. Kaynak hash doğrulanmadan offline iş başlamasın; başarıda tekrar kontrol edilsin. Not/kalite/iş ilerlemesi ham checksum belgesini geçersizleştirecek biçimde aynı mutable dosyaya bağlanmasın.
4. **Her türetim ayrı sürüm olsun.** Örneğin take altındaki `derived/versions/<id>/` mantığı; gerçek klasör/şema kararı geliştirmede verilecek. Manifest: kaynak hash, iş parametreleri hash'i, uygulama/worker kod revizyonu, SDK/Python wrapper/driver, donanım, model seviyesi, BODY formatı, depth modu, fitting/tracking/smoothing/prediction, precision, gerçek init/runtime değerleri, calibration, koordinatlar, çıktı hash'leri ve frame map. Erişilebiliyorsa model/engine dosya hash'i; bulunamıyorsa bilinmiyor. Aynı SDK sürüm adı bit düzeyinde tekrar üretilebilirlik garantisi sayılmasın.
5. **Tüm okunabilir kareler ve kişiler işlensin.** `svo_real_time_mode=False`; detection bulunmayan karede de source timestamp'li boş satır yaz. Her kareyi bir kez işle; arada kaynak atlama/tekrar varsa işaretle. Tüm track'leri audit için sakla; seçili sporcunun çıktı görünümü association revizyonundan türesin. Aynı model parametreleriyle bütün kişiler zaten hesaplandıysa, koç seçiminden sonra yalnız filtrelemek için ikinci ağır inference yapılmasın. İkinci geçiş ancak yöntem/parametre değiştiğinde gerekli.
6. **Live measurement ile offline reconstruction ayrımı görünür olsun.** Raw-only modunda hiç canlı depth ölçülmediğini belirt. Offline depth `reconstructed_offline`; varsa canlı depth `measured_live` ve sahiplik/doğrulama durumu ayrı. Depth'i arşivlememek, skeleton üretmek için SDK içinde depth hesaplanmadığı anlamına gelmez. Sonuç için gerekmeyen tam depth'i kalıcı yazma; kullanıcıya saklama maliyetini göster.
7. **Staging ve doğrulama sonrası atomik yayın.** Aynı volume'de işe özel staging; dosyaları kapat/flush et, kapsam ve checksum doğrula, son manifest/commit işaretini yaz, sonra atomik rename/publish. Dizin yayınının Windows davranışı ve hata durumları test edilsin. Yarım işler reader/export keşfinde tamamlanmış sayılmasın. Kapsam uyuşmazlığında hamı koru, çıktı karantinada kalsın; eksik kaynak kabul edilecekse açık kalite kararı ve sınırlı kapsam kaydı gerekir. Sessiz N−1 istisnası yok.
8. **Kuyruk ve recovery gerçeğe uygun olsun.** Başlangıçta tek GPU işi, sınırlı CPU sıkıştırma; bir işin iki süreçte açılmasını engelleyen kilit. Kayıt öncelikli kaynak politikası. Pause aynı süreçte kamera/tracker durumunu tutabilir; uygulama kapanınca bu durumun serialize edilebildiğini varsayma. İlk sürümde güvenilir resume: kaynak başından yeniden işle veya checkpoint'e kadar history'yi tekrar oynat, doğrulanmış prefix'i yeniden kur. Doğrudan kare N'ye seek edip yeni tracker ID'lerini eski çıktı devamı sayma. Retry yeni staging açsın; aynı fingerprint ve tamamlanmış geçerli sonuç varsa tekrar üretim yerine onu göster. Gece işleme kullanıcı ayarı olsun; bu incelemede otomasyon kurulmadı.
9. **Annotation sürüm bağı açık olsun.** Annotation başlamadan önce koç geçerli derived sürümü seçebilir. Başladıktan sonra her annotation revision, skeleton version + subject association revision + source timeline/frame map'e sabitlenmeli. Yeniden işleme yeni sürüm üretir; mevcut annotation ve release'i otomatik taşımaz. Açık “yeni sonuçla incele” işlemi ayrı annotation revision yaratabilir; eşlenemeyen sınırlar/kişiler insan kontrolü gerektirir. BODY_34 ↔ BODY_38 indeksleri farklı spec üzerinden okunmalı. Aynı kaydın farklı derived sürümleri train/test taraflarına dağıtılmamalı; split, katılımcı/kaynak take düzeyinde sabit kalmalı.
10. **QC tespit eder, kaynak noktaları değiştirmez.** Sol/sağ diz farkı, gerçek dt ile açısal hız, kemik uzunluğu sıçraması, ayak sürekliliği, body confidence ve squat fazıyla uyum birlikte aday işaret üretsin. Ayakta 180° diz normaldir; yalnız “diz düz” diye hata verme. Asimetri gerçek hareket özelliği olabilir; zorla simetrileştirme yapma. Eksik kareleri veya dipleri sessiz interpolate etme. Şüpheli aralık → yerel RGB/iskelet karşılaştırması → insan kararı veya ayrı alternatif sürüm.

Mevcut mock backend korunmalı. Yeni kamera gerektirmeyen fake source, deterministic timestamp dizisi ve bozuk/eksik kaynak senaryoları aynı sözleşmelerle çalışmalı; gerçek SDK testi bunları tamamlamalı.

### Plan 4'ün kapsamı nasıl sınırlanmalı?

Önce BODY_38 + QC ile hangi açı/sporcu grubunda başarısız kalındığı ölçülsün. Ardından yalnız başarısız aralıklarda alternatif 2B pose yaklaşımı değerlendirilsin; stereo eşleme/triangulation için sağ-sol görüntü eşzamanlılığı, görünürlük, calibration ve ortak eklem tanımı zorunlu. “RGB modeli + depth” doğrudan anatomik ground truth üretmez. Alternatif model bu tur seçilmedi veya kurulmadı; ortam değişikliği yapılmadı.

İkinci kamera, örtüşmeyle kaybolan görünürlüğü azaltabilecek araştırma seçeneği; eşzamanlama, kalibrasyon, ikinci USB/recording hattı, kurulum ve kişi eşleme maliyeti getirir. Güçlü işlem bilgisayarı kuyruk süresini azaltabilir ama yanlış poz modelinin semantik hatasını tek başına çözmez. Satın alma kararı için henüz ölçüm yok. Akademik eklem açısı doğruluğu temel hedefse referans yöntem ve kabul hatası önce belirlenmeli; yalnız görsel olarak iyi duran skeleton yeterli değildir.

## 7. Önerilen aşamalı yol haritası

Bu tablo uygulama onayından sonraki sıradır. Kalıcı kök seçimi bu raporda yapılmadı; mevcut veriler taşınmadı. Her faz ayrı değerlendirilebilir olmalı.

| Faz / kapsam | Bitti sayılma ölçütü | Koçun gördüğü akış | Başarısızlık ve geri dönüş |
|---|---|---|---|
| **0 — Veri bütünlüğü, kalıcı hedef, ölçüm** | SDK tampon yeniden kullanım testi farklı kareleri doğru arşivler; eski mock/live tests geçer. Yeni kalıcı test kökü açıkça seçilir, eski take'ler korunur. Requested/applied codec/FPS, timestamp ve kuyruk ölçüleri görünür; start/stop ve checksum sözleşmesi test edilir. | Veri klasörünün geçerliliği, kalan süre/alan; canlı kayıt durumu ve anlaşılır eksiklik mesajı. Teknik süreler Ayrıntılar'da. | Kök yok/yazılamıyor/geçici test kökü ise yeni çekim başlamaz; mevcut kayıtlar açılabilir. Düzeltme testte başarısızsa patch geri alınır; arşiv doğruluğu doğrulanana dek “birebir canlı depth” iddiası yapılmaz. |
| **1 — Küçük capture-only teknik deneme** | SVO + bağımsız frame ledger + hafif RGB. Body/depth/proxy/compression gerçekten canlı yolun dışında. Mock start/stop/cancel çalışır. Kamera bağlanınca kaynak hızı/kapsam kapıları ölçülür. | Deneme akışında büyük RGB, katılımcı, süre, disk ve kayıt durumu; “İskelet sonra hazırlanacak.” | Kayıp/codec/yazma sorunu açık partial verir. Yeni mod özellik bayrağıyla kapanır; eski live mod mevcut kalır. Başarısız deneme üründe önerilen varsayılan yapılmaz. |
| **2 — Offline BODY_38 ve sürümlü sonuç** | Sıralı worker, boş detection kareleri, frame map, source hash, staging/publish ve crash/cancel/retry testleri. Eski iki N−1 dosya otomatik tam kabul edilmez. Reader/annotation/export seçilen sürüme bağlanır. | Kayıt “İşlem bekliyor” → “İşleniyor” → “İskelet hazır / kontrol gerekiyor”. İşe ve tahmini süreye erişim. | Disk dolu/model açılamadı/kare uyuşmazlığı ayrı neden; ham veri değişmez. Retry yeni staging; eski geçerli sürüme dönülür, etiketler otomatik taşınmaz. |
| **3 — Koç için kişi seçimi ve iş kuyruğu** | Track kartları, bir kez seçim, belirsiz aralık onayı, onay revision'ı; queued/pause/cancel/retry, restart recovery. Yanlış kişiye sessiz geçiş yok. Temsilî kullanıcı görevleri ve erişilebilir uyarılar test edilir. | Katılımcı → kayıt → karttan sporcu → işaretli bölümleri kontrol → etiketleme. Model adları Ayrıntılar'da. | Eşleme belirsizse yalnız ilgili aralıklar bekler. İşlenen diğer kayıtlar erişilebilir; export kişi onayı eksik aralığı gizlice kullanmaz. Gerekirse tamamen manuel offline seçime dön. |
| **4 — Gerçek ZED A/B ve saha pilotu** | Bölüm 9'daki en az 5 sporcu, açılar, hız/kapsam, yanlış kişi ve doğruluk kapıları raporlanır. Tek başarılı klip kabul edilmez. Koç süre/hata hedefleri sağlanır. | Görünür RGB/iskelet, kayıt öncesi hazır sinyali, her klip sonrası sonuç ve dosya kontrolü. | Başarısız profili yaygınlaştırma; geçerli düşük riskli profil veya raw-only veri toplama ile sınırlı kal. Doğruluk yetersiz veriyi eğitimde onaylı sayma. |
| **5 — Gerekiyorsa alternatif model/çoklu görüş** | Aynı başarısız örnekler ve bağımsız referansta ölçülen iyileşme; ek kurulum/disk/koç maliyeti kabul edilir. | “Alternatif sonuç var” ve senkron önizleme; yöntemi otomatik değiştirmeden onay. | İyileşme yoksa araştırma kolunu durdur; önceki kaynaklar, BODY_38 sürümü ve annotation'lar korunur. |

Faz 1'in kod denemesi kamera olmadan başlayabilir; gerçek capture FPS kabulü kamera bekler. Faz 2–3'te eski verilerle güvenlik ve GUI geliştirilebilir; bunlar Faz 4'ün fiziksel squat kanıtının yerine geçmez. Plan 3'teki hafif canlı tracker, Faz 3/4'te offline seçimin pratikte koçu zorladığı görülürse eklenmeli.

## 8. Koç için somut GUI ve çoklu kişi tasarımı

**Bugün doğrulandı:** Capture ekranı RGB/depth ve 3B skeleton alanları, ayrı modeless bilgi penceresi ve ana ekranda kritik durumlar kullanıyor. Review tek viewport ve hareket/hata zaman çizgileri etrafında kurulmuş. Yeni mod bu düzeni ham kayıtta boş 3B alanla doldurmamalı; incelemenin iki seviyeli etiketleme akışı korunmalı.

### Normal kayıt ve inceleme akışı

1. **Katılımcı seçimi sonrası**, Capture'ın üst kontrol grubunda “Kayıt modu”:
   - `Hızlı kayıt · İskeleti sonra çıkar (önerilen)`
   - `Canlı iskelet · Daha yüksek sistem yükü`

   Bu hedef ürün tasarımıdır. Plan 1 tek başına uygulanırsa mevcut olmayan hızlı mod çalışıyor gibi sunulmaz; raw-only doğrulanana kadar “önerilen” varsayılan yapılmaz.
2. **Hızlı kayıt ekranı:** Büyük RGB; üstte katılımcı adı/kodu ve kayıt durumu, altta süre/diskten kalan yaklaşık kayıt süresi. “İskelet kayıt sonrası hazırlanacak” kısa metni. Kameranın gerçek acquisition hızı ve kayıp varsa anlaşılır uyarı; model, checksum, engine ve teknik profil Ayrıntılar'da. Live modda mevcut iskelet görünümü kullanılabilir. Renk tek başına uyarı taşımasın; ikon ve metin de olsun.
3. **Kişi kararı:** Plan 2'de kayıt öncesi “Sporcuyu işlem sonrası seçeceksiniz”; tek-sporcu alanı kullanmak seçimi kolaylaştırır ama otomatik kimlik doğrulaması değildir. Plan 3'te koç görüntüde sporcuyu tıklar; görünür kutuda “Seçim ipucu” yazar. Kutunun kaybolması kayıt kaybıyla karıştırılmaz; kaynak kayıt devam eder, belirsizlik audit edilir.
4. **Kayıt bitişi:** “Ham kayıt kaydedildi · İskelet bekliyor”. Seçenekler “Şimdi işle” ve “Kuyruğa ekle”. Kaynak doğrulaması henüz bitmediyse ayrı gösterilir; body bulunmadığı için kayıt başarısız denmez. İptal düğmesi “İşlemeyi iptal et” anlamını taşır; ham kaydı silme ile birleşmez.
5. **İlk offline geçiş sonrası:** Her track için başlangıç/orta/son küçük görüntü, görünme süresi, ilk/son zaman ve varsa kopma sayısı. Teknik ID küçük ayrıntı olabilir; ana başlık “Kişi 1”, “Kişi 2”. Track parçaları henüz aynı insan kabul edilmediyse ayrı aday olarak kalır. Koç “İşlenecek sporcu”yu seçer; büyük önizleme ve zaman çizgisi seçimi gösterir. İlk geçiş tüm kişilerin iskeletini zaten üretmişse ikinci inference bekletilmez.
6. **Yalnız belirsiz bölgeler:** Kayıp, ID değişimi, iki adayın kesişmesi veya hint uyuşmazlığı sarı/kırmızı + metinle gösterilir. Koç “Aynı sporcu”, “Diğer kişi”, “Bu bölümde sporcu yok” kararını ilgili aralığa verir. Sistem en yakın/ilk kişiye sessiz fallback yapmaz. Belirsiz bölümü onaylamadan bütün take'i eksiksiz seçili sporcu verisi diye sunmaz.
7. **Sonuç ve etiketleme:** “İskelet hazır”, “4 bölüm insan kontrolü istiyor”, gerçekten kapsam tam ise “Kayıt eksiksiz işlendi”. Kaynak kapsamı uyuşmuyorsa açık “Kaynak kare sayısı uyuşmuyor; kontrol gerekli”. Review'da normal hareket/hata etiketleme; aktif skeleton ve kişi seçimi revizyonu sabit. Sonradan yeni model sonucu gelmesi mevcut etiketleri değiştirmez.

### Kişi seçme seçeneklerinin karşılaştırması

| Yaklaşım | Yanlış kişi riski | Canlı yük | Koç adımı | Gizlilik / öneri |
|---|---|---|---|---|
| Tamamen offline görüntü kartları | Track parçalanması/kesişme var; bütün zaman çizgisi görülebilir, belirsiz bölge teyidi zorunlu | Ek detector yükü yok | Genellikle kayıt sonrası bir seçim, sonra yalnız işaretli bölümler | Yerel kısa görüntüler; yüz tanıma yok. **İlk öneri.** |
| Çekim öncesi hafif kutu tracker | Görünüm/örtüşmede drift ve ID değişimi; tek tıklama bütün kaydı kanıtlamaz | Düşük olması hedeflenir ama ölçülmedi | Kayıt öncesi tıkla; koparsa yeniden seç veya sonraya bırak | Hint yalnız bu kayıt içinde; ayrıca offline teyit gerektirir |
| Hibrit | İki kanıt uyuşursa daha az koç işi; aynı hatayı paylaşmaları mümkün | Hafif canlı ek maliyet + offline eşleme | Başta tıkla, sonra öneriyi teyit et; belirsizde aralık seçimi | Biyometrik kayıtlar arası DB yok. **Pilot ihtiyacına göre.** |
| Tek-sporcu çekim alanı | Riski azaltır; arka plandaki insan/çıkıp dönme hâlâ mümkün | Ek hesap yok | Alanı hazırla; kısa sonuç kontrolü | Az gereksiz görüntü; organizasyon yükü var. Tek başına güvenlik mekanizması değil |

Canlı hint için önerilen kayıt: gösterilen karenin source timestamp'i, normalize bbox, görüntü dönüşümü/çözünürlüğü, yerel track ID, seçim/kaybolma olayı ve detector sürümü. Offline eşleme, zaman örtüşmesi + kutu/konum sürekliliği + eş-görünürlük ile aday üretir. Boy veya beden oranı aynı kişiyi kanıtlamaz. Aynı ID dönüşünde bile uzun kayıp/kesişme sonrası teyit gerekebilir. Yüz tanıma ve kayıtlar arası biyometrik profil önerilmiyor; thumbnails mevcut proje erişim kuralları içinde yerel tutulmalı.

### Kuyruk ve hata durumlarında kullanılacak dil

| Durum | Ana ekranda mesaj ve eylem |
|---|---|
| Kaynak yok / eski proje yolu geçersiz | “Kayıt dosyası bulunamadı” veya “Yeni kayıt için veri klasörü seçin”; bulunan take'leri kayıp sayma, otomatik DB temizleme yapma |
| Disk yetersiz | Kayıttan/işten önce alan ihtiyacını göster; başka onaylı hedef veya sonra işle. İş ortasında durursa hamı koru, tamamlandı deme |
| Model ilk açılışı | “İşlem hazırlanıyor”; kare yüzdesi henüz yok, iptal erişilebilir. İlk açılış süresini klip ETA'sıyla karıştırma |
| İşleniyor | “İşlenen 412 / doğrulanmış 900 kare”, kuyruk sırası, tahmini süre. Toplam bilinmiyorsa sayı ve belirsiz toplam; uydurma yüzde yok |
| Yeni canlı kayıt başlıyor | Offline işi güvenli sınırda duraklat; “Kayıttan sonra devam edecek”. GPU belleği gerekiyorsa işi kapatıp güvenilir replay ile yeniden başlat |
| Kişi bulunamadı | “Bu bölümde kişi bulunamadı”; kaynak kare işlenmiş olabilir. Tespitsiz kareyi dropped frame ile karıştırma |
| ID değişti / iki aday benzer | “02:13–02:16 arasında sporcuyu doğrulayın”; ilgili aralığa doğrudan git |
| Kare sayısı/timestamp uyuşmuyor | “Kaynak kapsamı doğrulanamadı”; tanılama, yeniden dene veya açık teknik inceleme. “Eksiksiz” ve normal export kapalı |
| İşlem başarısız / uygulama yeniden açıldı | “İşlem yarım kaldı; ham kayıt güvende”; tekrar dene/baştan sürdür. Yarım derived sonuç final listede görünmez |
| İşleme iptali | “İşlem iptal edildi; ham kayıt saklandı”; sonradan yeniden kuyruğa alınabilir |
| Yeni skeleton sürümü | “Yeni sonuç hazır; mevcut etiketler önceki sonuca bağlı”; açık karşılaştırma/yeni annotation revision işlemi |

ETA, birkaç saniyelik model ısınmasından sonra ölçülen işlem hızından üretilmeli; kişi sayısı ve depth saklamasına göre değişebilir. Bugünkü iki kısa BODY_38 deneyi 30 FPS kaynağın yaklaşık 2,0–2,2 katı süre gerektirdi. Bu hız aynı kalırsa 10 dakikalık klip yalnız işleme açısından yaklaşık 20–22 dakika demektir; proxy/depth yazımı, açılış ve gerçek oturum yükü eklenir. Bu değer kuyruk planlama örneğidir, ürün taahhüdü değildir.

## 9. Planlardan sonra uygulanacak ZED A/B protokolü

Bu protokol **gelecek test planıdır; bu turda canlı çekim yapılmadı**. Önce küçük fiziksel doğrulama, sonra sporcular arası pilot. Profil değişikliği ve hareket tekrarından kaynaklanan etkiler birbirinden ayrılmalı.

### İlk kısa interaktif oturum

Amaç: önceki düz diz hatasının yeniden görülüp görülmediğini, BODY_38 farkını ve yeni kaydın kaynak/skeleton sınırını kontrol etmek. İlk oturum **2 kısa karşılaştırma klibi, gerekirse 1 oblik tekrar**, kurulum ve dosya kontrolleriyle yaklaşık **15–25 dakika** planlanabilir. Klip başına normal tempoda 8–10 squat; canlı BODY_34 ve BODY_38 aynı diğer ayarlarla. Mevcut kodla yapılabilen ölçüm sınırında kalınır; raw-only karşılaştırması özellik hazır olunca eklenir. Aynı ham SVO daha sonra her iki formatla offline işlenir. Çekimler aynı hareketin birebir kopyası olmadığından canlı klipler arası açı farkı tek başına model etkisi diye yorumlanmaz.

Kullanıcıdan o oturumda ZED'i bağlaması ve fiziksel olarak hazır olduğunu belirtmesi istenir. Yeni veriden önce kalıcı test kökü kullanıcıyla belirlenir; mevcut iki kalıcı projeye yazılmaz ve artık bulunmayan pytest kökü kullanılmaz. RGB ve skeleton kullanıcının monitöründe görünür açılır. Giriş gerekiyorsa kullanıcı parolasını uygulamada kendisi girer. Tam beden ve ayak görünürlüğü, kamera yüksekliği/mesafe, ışık, disk alanı ve kablo düzeni kontrol edilip açık “hazır” sinyalinden sonra kayıt başlar. Kullanıcı dur derse veya hareket sırasında sorun bildirirse kayıt güvenli kapatılır. Her klip sonunda SVO varlığı, partial/final durumu, timestamp kapsamı ve checksum kontrol edilir; kamera ve pencere güvenli kapatılıp alınan klipler özetlenir.

### Pilot matrisi: tek başarılı videodan genellemeyi engelle

En az **5 sporcu**; farklı boy, kıyafet ve vücut yapısı. Her koşulda normal antrenman hızı korunur. Yük/tekrar temposu ve dinlenme düzeni aynı protokolle not edilir; model ayarı değişirken sporcu gereksiz yorulmasın diye oturumlar bölünür. Tüm olası faktörlerin tam çarpımını çekmek yerine bloklar kullanılır; aşağıdaki kapsam azaltımları raporda açık kalır.

| Blok | Kontrollü karşılaştırma | Tasarım ve amaç |
|---|---|---|
| A — Ana squat doğruluğu ve capture | 5 sporcu × ön / 30–45° oblik / yan × canlı / raw-only × 2 tekrar = 60 kısa klip | HD720/30, sabit codec, aynı ışık/mesafe, tek kişi. Canlı başlangıç profili BODY_38; her SVO offline 34 ve 38 ile aynı ACCURATE/depth/fitting/precision üzerinden eşleşmiş A/B. İki koşulun çekim sırası dengelenir. |
| B — Canlı format etkisi | BODY_34 ve BODY_38, her sporcuda en az ön açı eşli tekrar | Aynı camera/depth/model seviyesi ve arşiv profili; canlı hız ve dip hata süreleri. Offline aynı kaynak karşılaştırmasıyla çekim tekrarı etkisinden ayrıştır. |
| C — Çözünürlük ve depth | HD720/30; gerekirse HD1080/30. NEURAL_LIGHT, QUALITY, NEURAL_PLUS | Önce aynı SVO'da depth modu A/B; çözünürlük için ayrı, dengelenmiş çekimler. HD1080 yalnız alt beden piksel alanı/doğruluk kazancı disk ve süreye değiyorsa. Aynı anda resolution ve depth değiştirme. |
| D — Codec | H264, H264_LOSSLESS; disk elverirse LOSSLESS veya H265 ailesi | Önce kısa kayıtla gerçek applied codec/readback doğrula. Aynı sahne/hareket protokolü ve dengeli sıra. Görüntü ayrıntısı, knee hata oranı, capture FPS, bytes/dakika, encoder/disk yükü. Sonradan transcode deneyi canlı encoder testinin yerine geçmez. |
| E — Çoklu kişi | Tek kişi; arka planda 1–2 kişi; önden kesişme; seçili sporcunun çıkıp dönmesi | En az 5 sporcuda kişi kimliği zaman çizelgesi manuel referanslı. Benzer kıyafet ve ID değişimi örnekleri. Kaybolma ile yanlış kişiye geçiş ayrı olaylar. |
| F — İşleme/ayar maliyeti | FAST/MEDIUM/ACCURATE, reduced precision açık/kapalı; uygun formatta fitting/prediction; stabilizasyon 0/30 ve static camera | Önce aynı kaynak üzerinde tek değişkenli offline doğruluk/maliyet incelemesi; umut veren canlı seçenekleri kamerada doğrula. SDK'nin desteklemediği kombinasyonu A/B sayma. |
| G — Koç ve dayanıklılık | Mümkünse 3 antrenör, temsilî 10'ar görev; daha uzun 2–3 dakikalık capture stres kaydı | Kişi seçimi, belirsiz bölüm, kuyruk, iptal, yeniden açma ve sonuç kontrolü. Disk dolu, worker hatası ve kapanış testleri sentetik/izole ortamda ayrıca yapılır. |

Kamera modları cihazın desteklediği FPS değerleriyle sınırlandırılmalı. ZED 2i için HD1080'de 15/30, HD720'de 15/30/60 seçenekleri ürün bilgisinde yer alır; bu görevde karşılaştırma kaynağı 30 FPS tutulur. İstenen 25'in gerçek 30'a dönüşmesi sessiz geçmemeli; açılış sonrası gerçek değer gösterilip manifestte tutulmalı. [ZED 2i ürün özellikleri](https://store.stereolabs.com/products/zed-2i)

Kurulum rehberi koça şu somut geri bildirimi vermeli: squat boyunca baş/kalça/diz ve ayaklar kadrajda; alt bedende yeterli piksel alanı; ayakların birbirini/ekipmanı örtmemesi; sabit tripod ve kaydedilmiş kamera yüksekliği/mesafe; homojen ışık, koyu kıyafet ile zeminin ayırt edilebilmesi. 30–45° açı umut veren başlangıçtır; bütün hareket türleri veya iki bacağın görünürlüğü için otomatik optimum kabul edilmez. Maruziyet/hareket bulanıklığı ve kamera ayarları da kayda alınmalı.

### Metrikler ve referans yöntemi

| Alan | Nasıl ölçülecek? |
|---|---|
| Kaynak kapsamı | Gerçek camera FPS, capture ledger adedi, SDK bildirimi, okunabilir SVO adedi, writer adedi, timestamp gap dağılımı, tekil/tekrarlı konumlar. “Yakalanmış her kare işlendi” ile “kamera zamanında her kare yakalandı” ayrı ölçüler. |
| Canlı hız | Kayıt içi timestamp'lerden acquisition FPS; medyan/p95/p99 kare aralığı; warmup ve stop sınırları ayrı. Preview FPS ölçüsü bunun yerine kullanılmaz. |
| Yük ve kayıp | Aşama süreleri, kayıt kuyruğu/chunk kuyruğu dolulukları, her katmanda dropped frames, per-take backend delta, RAM/VRAM, GPU/NVENC/CPU, disk bytes/s, finalize süresi. |
| İskelet bulunma | Herhangi kişi coverage, seçili kişi coverage, lost/ambiguous/no-detection oranları ayrı. Seçili kişi paydası ilgili tüm kaynak kareleri; belirsiz kareler gizlenmez. |
| Squat doğruluğu | RGB'den bağımsız seçilen bütün dip anları ve komşu kareler; sol/sağ kalça-diz-ayak bileği işaretlemesi. İki değerlendirici, model adını gizleyen sıra; görünmeyen eklem uydurulmaz. 2B piksel hatasını beden boyutuyla normalize et. |
| 3B açı doğruluğu | Aynı eklem/açı tanımında senkron yan referans veya daha güçlü marker/multiview yöntem. Önden 2B açıyla 3B mutlak açı hatası iddiası kurma. Dip MAE, bias ve hata dağılımı; kişi/tekrar düzeyinde özet. |
| Yüksek güvenli yanlış iskelet | Önceden seçilmiş yüksek confidence eşiğinin üstünde bağımsız referansa göre yanlış joint/frame oranı; ayrıca yanlış düz dizin sürme süresi. Confidence bir doğruluk olasılığı gibi sunulmaz. |
| Kişi doğruluğu | Manuel kimlik zaman çizgisine göre yanlış kişiye bağlanan frame ve olay sayısı, ID switch, false reassociation, çıkıp dönme sonrası toparlanma ve koç müdahalesi. |
| Kullanılabilirlik | Sporcuyu seçme ve sonucu onaylama süresi, yanlış seçim, kaç düzeltme, kaç tıklama, tamamlanamayan görev, iptal/yeniden dene başarısı. |

Önce modelden bağımsız dip referansları seçilmeli; yalnız modelin iyi bulduğu kareleri değerlendirmek seçim yanlılığı üretir. Tespitsiz veya referansı örtülü karelerin sayısı ayrıca raporlanmalı. İki formatın eklem isimleri kendi spec'lerinden çözülmeli. Sonuçlar binlerce kareyi bağımsız örnek sayarak değil, sporcu ve tekrar bazında da gösterilmeli; 5 sporcu saha genellemesi için ilk pilot büyüklüğüdür.

### Pilot başlamadan sabitlenecek başarı kapıları

Aşağıdaki sayılar **önerilen mühendislik kabul eşikleridir**; evrensel biyomekanik doğruluk standardı veya elde edilmiş sonuç değildir. Projenin kullanım amacı ve referans kalitesiyle pilot öncesi kesinleştirilip sonuç görüldükten sonra gevşetilmemeli.

| Kapı | Önerilen kabul koşulu | Başarısızlık davranışı |
|---|---|---|
| Ham capture | Normal oturumda gerçek kaynak FPS'in en az %98'i; 30 için ≥29,4 FPS. Writer/encoder kuyruğunda sıfır açıklanmamış kayıp; nominal aralığın 1,5 katını aşan her gap araştırılır. Kaydedilen ledger ile decoded kaynak arasında sıfır açıklanmamış fark. | Ortalama FPS iyi olsa da sessiz kayıp varsa geçmez. Açıklanmış eksik kaynak partial/istisna olarak kalır; normal “tam” kabul edilmez. |
| Offline kapsam | Doğrulanmış kaynak ledger'ının %100'ü; her konum bir kez, doğru timestamp; detection boş olsa da satır var. | N−1 veya timestamp kayması yayımlanmaz; kaynak/SDK sınırı incelemesi. |
| Kişi güvenilirliği | Pilotun onaylı çıktılarında yanlış kişiye sessiz bağlanma 0; bütün bilinen belirsiz aralıklar koça gösterilmiş ve çözülmüş. | Canlı hint'i devre dışı bırak/offline manuel eşlemeye dön. Pilot sıfırı gelecekte hata olasılığı sıfır demek değildir. |
| BODY_38 iyileşmesi | Başlangıç hatası bulunan koşullarda en az 4/5 sporcuda yüksek güvenli yanlış poz oranının BODY_34'e göre düşmesi; herhangi bir sporcuda belirgin sistematik yeni hata kalmaması. Hata yoksa iyileşme iddiası yerine non-regression raporu. | Yalnız ortalama iyileşmeyle kabul etme; başarısız açı/sporcu grubunu incele, QC/alternatif yöntem. |
| Diz doğruluğu | Ön taslak: bağımsız değerlendirilen karelerde yüksek confidence (örn. ≥0,8 normalize) ve ciddi hata birlikteliği <%1. Ciddi hata tanımı pilot öncesi: güvenilir eşdeğer açı referansında >20° fark veya anotatörce belirlenmiş açık yanlış düz bacak. Güçlü 3B/sagittal referans varsa dip açı MAE hedefi ≤10° ayrıca değerlendirilebilir. | Referans yetersizse bu nicel açı kapısı doğrulanmış sayılmaz. Eşikleri kullanım amacına göre pilot öncesi netleştir; sayısal doğruluk yoksa yalnız görsel tutarlılık iddiası. |
| Koç yükü | Basit çoklu kişi klibinde sporcu seçimi medyan ≤30 s ve ana seçim ≤2 işlem; görevlerde yanlış kişiyle onay 0; belirsiz olaylar ayrı süre raporu. | Akışı sadeleştir; kart kalitesini artır veya Plan 3 hint ekle. |
| Veri güvenliği/recovery | Kaynak hash'i değişmiyor; cancel/crash/disk hatasında final derived görünmüyor; annotation/release önceki sürümüne bağlı; eski/mock veri açılıyor. | Özelliği pilot dışı tut; önce sözleşme hatasını düzelt. |

Eşiklerde iki bağımsız iddia var: capture'ın eksiksizliği ve kinematik doğruluk. Biri diğerini kanıtlamaz. Kamera/senaryo/kişi bazında başarısız hücreler gösterilmeli; yalnız başarılı videonun ekran görüntüsüyle karar verilmemeli.

## 10. Bilinmeyenler, uygulanmayanlar ve sonraki kararda gereken bilgiler

| Bilinmeyen | Bugün neden kapanmadı? | Daha sonra nasıl kapatılır? |
|---|---|---|
| Modelin squat eğitim örnekleri ve SDK 5.4.1 formatlarının bütün iç farkları | Üretici eğitim kümesi/iç mimari erişimi yok | Üretici açıklaması; yerel A/B yalnız davranışı ölçer |
| Eski kötü squat açıları ve 2B/3B reprojection hesabının tekrarı | Kullanıcının sildiği ham dosyalar yok | Yeni kontrollü kayıt; bugünkü PNG'leri tam stream yerine kullanmama |
| BODY_38'in farklı sporculara genellenmesi | Eski iki squat klibi tek sporcu; bugünkü iki kalıcı klip farklı teknik kayıt | En az 5 sporculu protokol |
| Gerçek raw-only acquisition FPS / encoder ve disk maliyeti | Kamera bağlı değil; mevcut uygulamada ürün modu yok | Faz 1 denemesi ve gerçek capture benchmark |
| Eski SVO'nun codec kimliği ve N−1 EOF nedeni | Playback getter kaynak codec'i olarak doğrulanmadı; son konum okunamıyor | Güvenilir container/SDK provenance ve yeni düzgün kapanış kayıtlarıyla sayım/seek karşılaştırması |
| Geçmiş depth arşivlerinin ne kadar etkilendiği | Bugünkü hata gerçek; mevcut iki eski take'te ayrı depth arşivi yok | Varsa başka arşivleri değişmeden incele; sahip olunan tamponlarla yeni referans al |
| Start/stop yarışının fiilî etkisi, crash ve resume | Kod riski bulundu; yalnız kooperatif 40 kare iptali denendi | Yavaş writer, dolu kuyruk, süreç sonlandırma ve restart fault-injection |
| FAST/reduced precision, fitting, codec ve çoklu görüşün kazancı | Bu tur bounded BODY_34/38 deneyi yapıldı; diğer A/B'ler yapılmadı | Aynı kaynakta tek faktörlü test; cihaz gerektirenler pilotta |
| Koçların kabul edebileceği bekleme ve kontrol süresi | Kullanıcı çalışması yapılmadı | Kısa koç görev testi; günlük oturum hacmi ve kuyruk planı |

Uygulamaya geçiş kararında kullanıcıdan gerekecek bilgiler: kalıcı yeni test proje konumu ve kullanılabilir disk; günlük/haftalık kayıt süresi ve sonucu aynı gün görme gereksinimi; hedefin görsel egzersiz etiketleme mi yoksa nicel eklem açısı araştırması mı olduğu; referans cihaz/kamera erişimi; salonun kişi yoğunluğu ve koçların iş akışı. Bunlar bugünkü salt okunur incelemeyi durdurma nedeni yapılmadı. Yeni donanım oturumunda ayrıca fiziksel hazırlık onayı alınır.

**Değişmeyen gerçek sürümler — Bugün doğrulandı:** app/package 0.10.0; project 1.1.0; session 2.0.0; take 1.1.0; skeleton stream 1.1.0; annotation/release 2.2.0; label 2.0.0; feature spec/raw archive 1.0.0; identity SQLite 1. Yeni processing/derived/association şema sürümü belirlenmedi veya uygulanmadı. Kaynak: [sürüm sabitleri](C:/Users/gorke/Desktop/KineCapture/src/kinecapture/__init__.py:22), [pyproject](C:/Users/gorke/Desktop/KineCapture/pyproject.toml:7) ve read-only SQLite sorgusu.

Resmî belgeler 10 Eylül 2026'da kontrol edildi. Web sayfaları SDK 5.4.1'e sabitlenmiş bir dokümantasyon snapshot'ı değil; kullanılan seçeneklerin yerel SDK'da varlığı ayrıca sorgulandı. Belgedeki başka donanım performansı yerel sonuç diye kullanılmadı; paket/SDK güncellemesi yapılmadı.

### Deney kanıtları ve yeniden inceleme notu

Deney kökü: `C:\Users\gorke\AppData\Local\Temp\kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d`. Bunlar özel, yerel, türetilmiş/geçici çıktılardır; kalıcı raporun sayısal bulguları yukarıda yer alır. Geçici dosyalar ileride temizlenebilir. Mevcut deney dizinindeki betikler aynı çıktı adlarını kullandığı için körlemesine tekrar çalıştırılmamalı; yeni deney benzersiz dizinde yapılmalı.

| Kanıt | İçerik |
|---|---|
| [audit.py](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/audit.py) / [deney özeti](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/experiment_summary.json) | İki RGB, dört BODY geçişi ve 40 kare iptal; kaynak hash, konum/timestamp, performans ve ilk tampon bulgusu. Timing array'leri JSON özetinde metin olarak serialize edilmiş; rapor tablosunda sayısal okunmuştur. |
| [followup.py](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/followup.py) / [depth sonucu](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/depth_ownership_probe.json) | Üç gerçek SDK depth karesinin değiştirilmemiş arşiv yazıcısından geri okunması; false/false/true özgün kare eşleşmesi |
| [tail_probe.json](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/tail_probe.json) / [eşleme ve checksum](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/mapping_and_checksums.json) | Son konum seek, eşleşmeyen canlı ilk kare ve eski checksum denetimi |
| [pytest XML](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/pytest_short_path.xml) | Kısa izole kökte 143 başarılı test |
| [son değişmezlik kontrolü](C:/Users/gorke/AppData/Local/Temp/kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d/final_immutability_check.json) | 154 dosya, değişen yok; rapor/MEMORY bu kaynak koruma kontrolünün dışında |

Başarılı test koşusu mevcut `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe` ile, `-B -m pytest -o addopts='' -q --tb=short -p no:cacheprovider` seçenekleriyle, kısa ve yeni `C:\Users\gorke\AppData\Local\Temp\kcA3213` basetemp'inde yapıldı. Dosyalar: `tests/test_zed_adapter.py`, `tests/test_capture.py`, `tests/test_rgbd_archive.py`, `tests/test_subject_lock.py`, `tests/test_storage.py`, `tests/test_capture_subject_gui.py`. Yeni test kodu yazılmadı. SDK topoloji komutu `-B -m kinecapture.tools.verify_zed_topology` çalıştırıldı. Tam suite, self-test, canlı kamera, güç kesintisi, başarılı publish ve gerçek koç pilotu bu raporun doğrulama kapsamında değildir.

**Teslim kararı:** İnceleme ve dört plan tamamlandı. İlk uygulama önerisi depth tampon sahipliği düzeltmesi + gözlemleme, devamında Plan 2'dir. Görev dosyasındaki “raporu verdikten sonra dur; henüz kod uygulama” sınırı gereği uygulamaya geçilmedi; geliştirme kullanıcı onayını bekliyor.
