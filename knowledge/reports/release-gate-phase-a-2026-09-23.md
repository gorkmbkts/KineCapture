---
type: report
status: current
updated: 2026-09-24
tags:
  - release
  - export
  - stress-test
  - packaging
  - validation
---

# 23 Eylül yayın kapısı — Faz A doğrulaması

[Görev](../../promts/CLAUDE_RELEASE_GATE_AND_WINDOWS_INSTALLER_PROMPT_2026-09-23.md) ·
[Karar notu](../decisions/windows-installer-release-2026-09-23.md) ·
[Test ve ölçüm ortamı](../protocols/test-and-measurement.md)

> Kapı özeti ve açık kalanlar en sonda. Faz B (kurucu) ayrı raporda.

## Ölçüm koşulları

- Makine: Intel i7-10750H (6 çekirdek / 12 iş parçacığı), 16 GB RAM,
  Windows 11 Pro 10.0.26200, NVIDIA sürücüsü 616.56, ZED SDK 5.4.1,
  `LongPathsEnabled = 0`.
- Ortam: `KineSynth` — Python 3.11.14, PySide6 6.10.1, numpy 2.4.6,
  OpenCV 4.12.0, pyzed 5.4, pytest 9.0.1. Hiçbir ortama paket kurulmadı.
- Taban: commit `24c1509`; değişiklikler çalışma ağacında, commit edilmedi.
- `observed`: Bu makinede yeni yazılmış bir dosyanın **ilk** açılışı ~40 kat
  yavaş (500 sürümde dosya başına 3,9 ms ↔ ikinci okumada 0,09 ms). Neden
  büyük olasılıkla Windows Defender'ın erişimde taraması; güvenlik ayarlarına
  dokunulmadı. Ölçek sonuçları bu yüzden "ilk okuma" ve "ısınmış" olarak ayrı
  verilir.
- Kullanıcı verisi yalnız okundu. Gerçek kayıtlarla yapılan her şey geçici
  **kopya** üzerinde; orijinal dosyaların SHA-256'sı önce/sonra karşılaştırıldı.

## A1 — Temel koşu

Taban her iki koşuda da commit `24c1509`'un değiştirilmemiş kopyası
(`git archive`; `PYTHONPATH` o kopyanın `src`'si). Çalışma ağacındaki
değişiklikler bu sonuçlara karışmadı.

| Koşu | Sonuç | Süre |
|---|---|---|
| `run_tests.ps1` (eski hâli: tek süreç) | 41/98 dosya, **859 test geçti, 0 başarısız**; ardından `test_studio_auth_gui.py`'nin `gate` fikstüründe 10 dakikadan uzun takıldı ve durduruldu | ~54 dk |
| `run_tests.ps1` (yeni hâli: dosya dosya) | **97/98 dosya yeşil**; 1 başarısız | 2827 s |

`verified` — **Tek süreçli koşunun bitmemesinin nedeni** (protokol notunda
`open` duruyordu): `faulthandler` dökümü GUI thread'ini
`studio/views/theming.py` `apply_application_theme` içinde gösterdi. Testlerin
kapatıp **silmediği** pencereler süreçte birikiyor (aynı süreçte ölçüldü:
kimlik testlerine gelindiğinde **322 üst düzey pencere, 15 527 widget**), her
`build_window` uygulama geneli stil sayfasını uyguluyor ve bu maliyet canlı
widget sayısıyla doğrusal: 0 / 1 960 / 3 920 / 7 889 / 15 827 widget için
0,02 / 0,76 / 1,52 / 3,17 / 6,64 s. Testler ilerledikçe her pencere
kurulumu pahalanıyor, toplam süre ikinci dereceden büyüyor. Ürün tek pencereyle
çalıştığı için bu bir **test düzeneği** sorunudur; `run_tests.ps1` artık
varsayılan olarak dosya dosya koşuyor (proje kuralı), eski davranış
`-SingleProcess` ile duruyor.

Başarısız test sınıflandırması:

| Test | Sınıf | Açıklama |
|---|---|---|
| `test_studio_workload.py::test_leaving_the_labelling_screen_stops_playback` | **eskimiş test** (deterministik, 2/2 izole koşuda da) | Fikstür proje açmıyordu; 20 Eylül proje kapısından beri `navigate` reddediliyor ve sayfa hiç devreden çıkmıyor. Fikstür kapıdan geçirildi; dosyanın 13 testi yeşil ve ürün oynatmayı gerçekten durduruyor |
| `test_processing_pipeline.py` duraklat/sürdür | bilinen aralıklı | bu koşularda **düşmedi** |
| `test_identity.py` eşzamanlılık | bilinen aralıklı | bu koşularda **düşmedi** |

### Son kodla tam koşu (24 Eylül)

`verified` — `scripts/run_tests.ps1 -Report -LogDir` (dosya dosya, KineSynth,
çalışma ağacının son hâli): **103 dosyadan 102'si yeşil, 2725 s; 2099 geçti,
2 başarısız, 38 atlandı.**

| Başarısız | Sınıf | Açıklama |
|---|---|---|
| `test_studio_projects_gui.py` (2 test) | **gerçek hata**, bu gece eklendi | S12'de katılımcı/oturum okuması iş parçacığına alınmıştı; art arda eklenen katılımcıların taramaları havuzda **sırasız** bitince eskisi yenisinin üstüne yazıyordu (4 katılımcı eklenince 3 görünüyordu). Düzeltme: her okuma bir sıra numarası alır, yalnız en yenisi ekrana yansır; tarama sürerken seçim değişirse yeni indeksle yeniden okunur. Hatayı yeniden üreten iki deterministik test eklendi ve **eski kodda düştükleri** gösterildi. Testteki tek `processEvents` beklemesi, pencerenin arka plan işleri bitene kadar beklemeye çevrildi (doğrulanan koşul aynı). Etkilenen 8 dosya yeniden: **8/8 yeşil** |

`verified` — **Düzeltmeden sonra ikinci tam koşu** (24 Eylül 02:58–03:44,
aynı betik, son kod): **103/103 dosya yeşil, 2750 s; 2102 geçti, 0 başarısız,
38 atlandı.** `test_studio_projects_gui.py` 16/16. Bu, sabahki kurucunun
(`build_installer.ps1 -Fresh`, 02:45) derlendiği koddur.

Atlanan 38 testin hepsi önceden var olan koşullu atlamalar: 33'ü
`test_studio_polish.py`'de offscreen platformunda yazı tipi olmadığı için
genişlik ölçümleri (`QT_QPA_PLATFORM=windows` ister), birer tane offscreen'de
GL bağlamı ve yerleşim boyutu, kayıtta belirsiz aralık bulunmaması, uzun yolda
proxy videosu. Bilinen iki aralıklı test (`test_processing_pipeline.py`
duraklat/sürdür, `test_identity.py` eşzamanlı kod ayırma) bu koşuda düşmedi.

`verified` — Atlanan 33 yazı tipi testi ayrıca gerçek `windows` platformunda
koşturuldu: **28 geçti, 5 başarısız** — `test_every_screen_fits_a_laptop_at_normal_scalings`
(`capture` %150, `dataset` %125 ve %150, `review` %150; ör. etiketleme
sayfasının en küçük genişliği 1047 px, test ≤ 900 bekliyor) ve
`test_the_widest_screens_are_the_ones_with_two_viewports`. **Aynı 5 test
bu gecenin hiçbir değişikliğini içermeyen `24c1509`'da da başarısız**
(`git archive` kopyası; paketin o kopyadan yüklendiği denetlendi): önceden var
olan, offscreen koşularda atlandığı için görünmeyen bir bulgu. Testler, 21
Eylül'de kullanıcının "yalnız maksimize pencere, farklı DPI/pencere boyutu
test matrisi istenmiyor" kararından önceki dizüstü ölçeklemesi gereksinimini
taşıyor; testlerin bu karara göre güncellenmesi mi, yerleşimin daraltılması mı
— **kullanıcı kararı**, değiştirilmedi.

## A2 — Dataset export doğruluğu

### Yöntem

`verified`: Uçtan uca sentetik zincir ürünün kendi servisleriyle kuruldu
(`tests/release_chain.py`): mock kamera → `TakeWriter` → `process_take`
(`SyntheticSource`, **BODY_18 / BODY_34 / BODY_38**) → `AnnotationStore` +
`SubjectStore` (etiketleme ekranının kullandıkları) → `build_release`.

Paket, export kodunu **hiç içe aktarmayan** bağımsız bir okuyucuyla
(`tests/release_oracle.py`; yalnız `json`, `hashlib`, `numpy`) projenin kendi
dosyalarından türetilen beklentiye karşı alan alan ve dizi dizi karşılaştırılır:
örnek/segment sayısı, sınıf listesi ve sınıf→indeks, her segmentin
başlangıç/bitiş karesi ve zaman damgası, hareket/hata sınıfı, eklem rolleri,
eklem durumu, rol kökeni, notlar, katılımcı/oturum/proje, köken
(`synthetic`/`real`), iskelet, NaN maskesi, yoğun hata hedefi, manifest
sayıları ve şema sürümleri, `checksums.json`, reddedilen sürümler ve atlanan
hareketlerin gerekçeleri. Senaryo Türkçe/boşluklu proje, sınıf ve veri kökü
adları, özel karakterli sınıflar, ilk ve son kareye değen segmentler, tek
kareli segment, çakışan hareketler ve çakışan hata aralıkları, tanımlı ama hiç
kullanılmamış sınıf ve NaN'lı eklemler içerir. Katılımcılar tasarım gereği
anonim koddur (`P0001`); "Türkçe katılımcı adı" uygulanamaz.

### Bulunan ve düzeltilen hatalar

Her biri için önce başarısız regresyon testi yazıldı, sonra düzeltildi
(`tests/test_release_gate_export.py`, son hâli 23 test).

| # | Hata | Etki | Düzeltme |
|---|---|---|---|
| 1 | Kanonik pakette katılımcı, oturum, proje, köken ve iskelet yoktu | Paket katılımcıya göre bölünemiyordu; 18/34/38 eklemli diziler aynı pakette hangi eklem sırasıyla yazıldığını söylemiyordu; sentetik kayıt işaretsiz çıkıyordu (eski `ReleaseBuilder` bunları taşıyordu) | Şema **1.1.0 → 1.2.0** (toplamsal): örnek ve sürüm başına `participant_id`, `session_id`, `project_id`, `origin`, `skeleton_format`; manifestte `skeletons` (eklem düzeni), `projects`, `counts.participants`, `counts.samples_synthetic` |
| 2 | Pakette dosya bütünlük listesi yoktu | Kesik/bozuk `.npy` fark edilemezdi | `checksums.json`: paketteki her dosya (kendisi hariç), yazılan baytlardan hesaplanır |
| 3 | **Taşınan/kopyalanan proje:** `job.json`'daki mutlak `take_dir` izleniyordu | Kopyadan export orijinal konumun etiketlerini okuyordu (orijinal silinince 0 örnek); kopyada etiketleme **orijinal projeye yazıyordu** | `run_take_dir`: sürüm yerinde duruyorsa take, sürümün bulunduğu klasördür; `ReviewDataset`, `current_revisions`, `restart_job` bunu kullanır |
| 4 | Elle bozulmuş `sample_id` (`..\..\x`) paket dışına yol oluyordu; iki sürümde aynı kimlik ikincinin dizilerini birincinin üstüne yazıyordu | Paket dışına yazma / sessiz veri karışması | `validate_document` güvensiz kimliği reddeder; derleme çakışan sürümü `duplicate_sample` ile dışarıda bırakır; aynı adla farklı eklem düzeni `skeleton_mismatch` |
| 5 | Sınıf kodu 48 karakterde kesiliyor, yalnız sembollü adlar `label`'a düşüyordu; ikinci sınıf "zaten tanımlı" diye reddediliyordu | 100+ sınıflık sözlükte ayrı sınıflar oluşturulamıyordu | Kod eşitliği yalnız kayıpsız slug'da "aynı sınıf" sayılır; çakışan yeni sınıfa `-2`, `-3` eki |
| 6 | `checksums.json` yürüyüşü, klasörü kısa ama dosyası 259 karakteri aşan dosyaları sessizce atlıyordu | Bütünlük listesi eksik (A3 duman testinde 4706 dosyanın 588'i) | `core.paths.iter_files`: her zaman `\\?\` biçiminde yürür; paket, işleme sürümü ve ham kaynak parmak izi aynı yolu kullanır |

`verified`: 1–5 A2 testleriyle, 6 A3 duman ölçümüyle bulundu ve regresyon
testiyle kapatıldı. Paketin **içeriği** (sınırlar, sınıflar, aralıklar, diziler,
NaN) düzeltmelerden önce de oracle ile birebir tutuyordu; hatalar kaynak
bilgisi, bütünlük ve konum sınıfındaydı.

### Diğer sonuçlar

- `verified` Belirlenimcilik: aynı girdiyle iki derleme; `manifest.created_at`
  (ve dolayısıyla `checksums.json`'daki manifest satırı) dışında bütün dosyalar
  bayt düzeyinde aynı.
- `verified` Kesinti: derleme ortasında süreç `TerminateProcess` ile
  öldürüldü; geriye yalnız manifestsiz, checksum'sız gizli
  `.v0001.partial` kaldı; sonraki derleme aynı adı temiz aldı ve oracle'dan
  geçti. Güç kesintisinde dosya verisinin diske yazıldığı (fsync) sınanmadı.
- `verified` 259 karakteri aşan hedef: paket dosyaları MAX_PATH'i geçerken
  derleme ve oracle doğrulaması tam.
- `verified` Seçenekler: ekrandaki iki anahtar (güven dizisi, yoğun hedef)
  kapalıyken paket yine oracle ile birebir.
- `verified` `rehab24_6_mocap`: yalnız **eski** `ReleaseBuilder`'da
  (`--legacy-gui`) bir export hedefi. Kaynak eklemin indeksini taşıyan BODY_34
  akışıyla, iki spesifikasyondan elle yazılmış eşleme tablosuna karşı: 23 eklem
  adıyla doğru sütunda, 3 eşlemesiz eklem NaN. `open`: Studio'nun kanonik
  paketinde bu hedef **yok**; eklenip eklenmeyeceği ürün kararıdır.
- `decision` (mevcut davranış, değiştirilmedi): kanonik export sentetik kaydı
  dışlamaz, artık işaretler. Eski yol varsayılan olarak dışlıyordu.

### Gerçek veri

`verified`: Bu makinedeki gerçek ZED kayıtlarından etiketli dört sürümün
**kopyası** (`scripts/measure/real_export_check.py`) üzerinde kanonik export
çalıştırıldı ve oracle ile doğrulandı:

| Sürüm | Sonuç | Oracle | Orijinal dosyalar |
|---|---|---|---|
| `run_30bedb8d…` (21 Eylül, BODY_38, 1825 kare) | 2 örnek yazıldı | 0 sorun | 541 dosya, hash değişmedi |
| `run_908d9623…` (aynı kayıt) | reddedildi: `open_errors` | kuralla uyumlu | aynı sayım |
| `run_04e41587…` (22 Eylül) | reddedildi: `open_errors`, `no_ready_samples` | 0 sorun | 150 dosya, değişmedi |
| `run_61ef0f7c…` (17 Eylül) | reddedildi: `athlete_not_chosen`, `open_errors`, `no_ready_samples` | 0 sorun | 215 dosya, değişmedi |

Bu, açık listedeki "Kanonik export paketi gerçek kayıtla uçtan uca
doğrulanmadı" maddesini **bir gerçek sürüm ve iki örnek** ölçüsünde kapatır;
gerçek kayıtla hata aralığı içeren bir örnek pakete girmedi (etiketler
tamamlanmamış).

## A3 — Ölçek ve dayanıklılık

### Yöntem

- Üretici: `scripts/measure/scale_dataset.py` — sabit tohum, yalnız geçici
  klasör (gerçek konumu reddeder, testli). Projeyi uygulamanın kendi
  `ProjectWorkspace`'i kurar; her kayıt `ReviewDataset`'in açtığı ve
  `build_release`'in export ettiği gerçek şemada bir sürüm (checksum listesi,
  kaynak haritası, diziler, etiket ve sporcu dosyaları) taşır. Sınıf adları
  Türkçe harf, boşluk ve noktalama içerir. Sürümlerin ~%1'i sporcusuz, ~%1'i
  sınıfsız hata aralıklı bırakılır; bekleyen (işlenmemiş) kayıtlar kuyruğu
  doldurur.
- Arka uç: `scripts/measure/scale_backend.py` — her senaryo ayrı süreçte;
  faz başına süre ve 10 ms'de bir örneklenen tepe RSS; sayımlar (kayıt,
  sürüm, bekleyen, hareket, sınıf dağılımı, reddedilen) üretilenle
  karşılaştırılır; export ölçekte oracle ile tam doğrulanır.
- GUI: `scripts/measure/scale_gui.py` — ürünün kendi `StudioWindow`'u
  (tercih/kimlik/log sandbox'ta), gerçek `windows` platformu, maksimize
  pencere. GUI thread'inde 5 ms'lik zamanlayıcının gecikmesi = olay döngüsü
  bloklanması; 150 ms'yi aşan her anda GUI thread'inin Python yığını
  örneklenir. Etiketleme ekranı gerçek kayıt→işleme zinciriyle üretilmiş
  3000 karelik, 600 hareketli bir sürümle ölçülür.

### Bulunan ve düzeltilen darboğazlar

Her biri için regresyon testi var (`tests/test_release_gate_scale.py`,
`tests/test_release_gate_export.py`); "önce" değerleri aynı makinede, aynı
düzenekle ölçüldü.

| # | Yer | Önce | Neden | Düzeltme |
|---|---|---|---|---|
| S1 | Export `checksums.json` | 200 sürüm: 21,3 s | yazılan her dosya özeti için yeniden açılıp okunuyordu | özet yazılan baytlardan; 8,8 s |
| S2 | Etiketleme: hareket seçimi | 100 harekette tıklama başına 176 ms | seçim tüm satırları yeniden kuruyor, zaman çizelgesi ve özet kartları iki kez yıkılıp kuruluyordu | seçim yalnız seçimi değiştirir; ~35 ms |
| S3 | Etiketleme: etiket düzenleme | 100 harekette düzenleme başına ~184 ms | hareket ve hata listeleri ayrı ayrı bildiriliyor, sayfa her birinde her şeyi yeniden kuruyordu | tek `labels_changed` olayı; sonuç aşağıda |
| S4 | Dışa Aktarım'a dönüş | 500 sürümde GUI thread'i 660 ms | tazelik denetimi her sürümün iki yan dosyasını GUI thread'inde okuyordu | denetim iş parçacığında; yazma öncesi denetim de |
| S5 | İşlenen Videolar / Dışa Aktarım yenilemesi | 10k sürümde 1,5 s GUI thread'inde | sürüm satırları (her biri bir `stat`) GUI thread'inde kuruluyordu | iş parçacığında |
| S6 | Veri Seti her ziyaret | 10k sürüm: 52,7 s ilk okuma / 7,0 s ısınmış | her ziyaret her sürümün iki yan dosyasını yeniden ayrıştırıyordu | sürüm başına önbellek (boyut + zaman damgası + sözlük); 10k'da 5,0 s, bunun ~1,7 s'si indeks |
| S7 | İş bitince kuyruk yenilemesi | 10k kayıtta 18,9 s (ısınmış) her işte | bütün proje zorla yeniden taranıyordu | yalnız işin kaydı zorla okunur |
| S8 | Liste ekranlarında sütun genişliği | tema değişiminde 490 000 `data()` çağrısı | `ResizeToContents` varsayılan 1000 satır ölçüyordu | 64 satır |
| S9 | Tema değişimi | 912 widget'ta 7,9–8,9 s | yukarıdaki + her değişimde Fusion stili yeniden kuruluyordu | stil bir kez; sonuç aşağıda |
| S10 | Dışa Aktarım arama kutusu | — | kutu Qt'nin kendi filtresine bağlıydı, `SearchProxy` onu okumuyordu: **arama hiç çalışmıyordu** | `set_search`'e bağlandı |
| S11 | Kontrol ve paket yazma | 10k sürümde ~8 dk yalnız "kontrol ediliyor" | ilerleme yoktu (iş parçacığında olduğu için kabul ölçütü sağlanıyordu) | `n/N sürüm` sayacı |

### Arka uç ölçek eğrisi

`verified` (aynı makine, düzeltmeler sonrası kod, her senaryo ayrı süreç; 1k
ve 10k'lık senaryolar diğer işlerle çakışmadan, 30k arka planda yalnız
yazı düzenlemesi sürerken koştu). Üç eksen ayrı ayrı büyütüldü: kayıt/sürüm
sayısı (`runs_*`, her sürümde bir hareket), sürüm başına hareket sayısı
(`segments_*`, 1000 sürüm), sınıf sayısı (`classes_*`, 1000 sürüm, 10 000
hareket). Her export ölçekte bağımsız oracle ile **tam** doğrulandı.

| Faz — s (tepe RSS MB) | runs_1k | runs_10k | runs_30k |
|---|---|---|---|
| `generate` | 50,0 (106) | 513,4 (629) | 1 482,5 (1802) |
| `index_cold` | 8,1 (95) | 68,2 (167) | 477,9 (404) |
| `index_rescan` | 1,7 (95) | 18,9 (186) | 61,1 (465) |
| `index_warm` | 0,2 (91) | 1,7 (135) | 4,9 (288) |
| `library` | 0,1 (91) | 1,5 (105) | 10,0 (164) |
| `dataset_rows` | 11,7 (69) | 52,7 (105) | 405,6 (158) |
| `dataset_rows_again` | 0,7 (69) | 7,0 (100) | 184,2 (191) |
| `dataset_screen_first` | 1,2 (69) | 11,8 (138) | 43,0 (324) |
| `dataset_screen_again` | 0,5 (69) | 5,0 (169) | 25,2 (416) |
| `export` | 26,1 (74) | 492,5 (303) | 2 203,6 (831) |
| `oracle` | 38,2 (103) | 491,5 (609) | 3 372,0 (1695) |
| paket: dosya / MB | 7 843 / 20 | 78 403 / 202 | 235 203 / 605 |
| örnek / reddedilen sürüm | 980 / 20 | 9 800 / 200 | 29 400 / 600 |
| oracle sorunu | 0 | 0 | 0 |

| Faz — s (tepe RSS MB) | segments_1k | segments_10k | segments_30k |
|---|---|---|---|
| `generate` | 52,8 (105) | 51,7 (106) | 53,1 (105) |
| `index_cold` | 8,3 (89) | 7,8 (86) | 8,0 (90) |
| `index_rescan` | 1,8 (87) | 1,7 (87) | 1,7 (88) |
| `index_warm` | 0,2 (85) | 0,2 (85) | 0,2 (86) |
| `library` | 0,1 (86) | 0,1 (85) | 0,1 (69) |
| `dataset_rows` | 12,8 (86) | 12,7 (85) | 13,7 (72) |
| `dataset_rows_again` | 0,7 (69) | 1,0 (81) | 1,5 (77) |
| `dataset_screen_first` | 1,2 (69) | 1,5 (82) | 2,1 (77) |
| `dataset_screen_again` | 0,5 (68) | 0,5 (82) | 0,5 (77) |
| `export` | 27,0 (74) | 78,8 (225) | 200,5 (568) |
| `oracle` | 42,6 (103) | 282,1 (359) | 1 059,1 (933) |
| paket: dosya / MB | 7 843 / 20 | 78 403 / 58 | 235 203 / 138 |
| örnek / reddedilen sürüm | 980 / 20 | 9 800 / 20 | 29 400 / 20 |
| oracle sorunu | 0 | 0 | 0 |

| Faz — s (tepe RSS MB) | classes_100 | classes_150 | classes_200 |
|---|---|---|---|
| `generate` | 56,1 (105) | 52,6 (105) | 52,0 (105) |
| `index_cold` | 8,7 (90) | 8,0 (95) | 7,9 (92) |
| `index_rescan` | 1,9 (90) | 1,8 (95) | 1,7 (91) |
| `index_warm` | 0,2 (86) | 0,2 (91) | 0,2 (88) |
| `library` | 0,2 (87) | 0,2 (92) | 0,1 (88) |
| `dataset_rows` | 14,1 (87) | 13,4 (70) | 13,9 (71) |
| `dataset_rows_again` | 1,1 (83) | 1,0 (71) | 1,1 (71) |
| `dataset_screen_first` | 1,6 (84) | 1,5 (71) | 1,6 (72) |
| `dataset_screen_again` | 0,7 (84) | 0,5 (71) | 0,5 (71) |
| `export` | 82,4 (224) | 76,5 (225) | 79,7 (210) |
| `oracle` | 303,4 (360) | 281,4 (363) | 286,0 (365) |
| paket: dosya / MB | 78 403 / 58 | 78 403 / 60 | 78 403 / 62 |
| örnek / reddedilen sürüm | 9 800 / 20 | 9 800 / 20 | 9 800 / 20 |
| oracle sorunu | 0 | 0 | 0 |

Okuma:

- **Doğruluk her ölçekte tam:** 30 000 sürüm ve 30 000 hareket, 100 hareket
  ve 101 hata sınıfı; 29 400 örnek pakete girdi, 600 sürüm tasarım gereği
  reddedildi (300 sporcusuz, 300 sınıfsız hata aralıklı); oracle **0 sorun**,
  `checksums.json` 235 203 dosyanın hepsini doğru listeliyor.
- **Sınıf sayısı** (100 → 150 → 200) hiçbir fazı değiştirmiyor; **hareket
  sayısı** yalnız export'u ve oracle'ı büyütüyor, ekranları değil.
- `observed` **Kayıt sayısında büyüme doğrusalın üstünde:** 10k → 30k'da soğuk
  indeks ×7,0 (68 → 478 s), ısınmış Veri Seti satırları ×26 (7 → 184 s),
  export ×4,5 (493 → 2204 s). 30k'lık proje 393 202 dosya / 873 MB; olası
  neden dosya sistemi meta veri önbelleğinin ve Defender taramasının bu dosya
  sayısında tutmaması (`hypothesis`, ayrıca ölçülmedi). Bu işlerin hepsi iş
  parçacığında koşar, GUI thread'ini bloklamaz; ama 30k kayıtta Veri Seti
  ekranı her ziyarette dakikalar, export yarım saatten fazla sürer —
  **açık madde**.
- Etiketleme ekranı sürüm açılışı ölçekten bağımsız: 50 sürümde ortalama
  16–47 ms, en çok 97 ms.


### GUI, düzeltmelerden sonra

Ölçüt: GUI thread'i bir kullanıcı eyleminde **250 ms'den uzun** bloklanmaz.
`verified` (ürünün kendi `StudioWindow`'u; ~300 sürüm, sandbox'ta; aynı
makinede başka ölçümler sürerken, yani kötümser):

| Ekran / eylem | Önce | Sonra |
|---|---|---|
| İşlenen Videolar dolumu | 332 ms blok | 54 ms |
| Veri Seti dolumu | 217 ms | 43 ms |
| Veri Seti arama, tuş başına | ~150 ms | 26–64 ms |
| Dışa Aktarım'a dönüş | 661 ms (500 sürüm) | 27 ms |
| Etiketleme sürüm açılışı | 304 ms | 204 ms |
| Hareket seçimi, tıklama başına | 176 ms | 32 ms (en çok 37) |
| Etiket düzenleme | ~184 ms | 128 ms (en çok 137) |
| Sınıf tarayıcısı aç / ara | — | 12 / 19 ms |
| Tekrarlı gezinme döngüsü (en uzun blok) | 663 ms | 72 ms; RSS ve widget sayısı döngüler boyunca sabit (sızıntı yok) |
| Tema değişimi | 7,9–8,9 s | 1,4 s (boşta) – 3,2 s (yük altında) — **ölçütü karşılamıyor** |
| Projeler açılışı | — | 290 ms → S12 |

- **S12** (24 Eylül): Projeler ekranı katılımcı ve oturum listesini GUI
  thread'inde diskten okuyordu; katılımcı seçili değilken bu, projedeki
  **her** oturumun JSON'u demek (300 sürümde 290 ms, ölçekle büyür). Okuma
  iş parçacığına alındı; her okuma bir sıra numarası alır ve yalnız en yenisi
  ekrana yansır (ilk hâlindeki sırasız bitme hatasını son tam koşu yakaladı,
  bkz. A1). Regresyon testleri: tarama sürerken seçim, eski taramanın en son
  bitmesi; ilgili 8 dosya yeşil.
- **Tema değişimi** (`open`): Fusion'ın her değişimde yeniden kurulması (S9) ve
  1000 satırlık sütun ölçümü (S8) kaldırıldıktan sonra kalan maliyet Qt'nin
  uygulama geneli stil sayfasını 1066 widget'a yeniden uygulaması
  (`setStyleSheet` 1,24 s, `repolish_all` 0,14 s; profil). İş parçacığına
  alınamaz (Qt widget'ları yalnız GUI thread'inde). Nadir ve açık bir kullanıcı
  eylemi; kabul mü, stil sayfasının (ör. `QWidget` yazı tipi kuralı)
  yeniden düzenlenmesi mi — kullanıcı kararı.


### GUI, 30 000 kayıt (24 Eylül, gerçek `windows` platformu)

`verified` — ürünün kendi `StudioWindow`'u, maksimize pencere, sandbox'ta;
30 001 sürüm + 3 000 bekleyen kayıt, 100 katılımcı, 100 hareket + 101 hata
sınıfı; etiketleme ekranı için gerçek kayıt→işleme zinciriyle üretilmiş 3 000
kare, **600 hareket**, 200 hata aralıklı bir sürüm. Tek başına koştu (başka iş
yok). Sol sütun ~300 sürümlük ölçüm (offscreen, yük altında), sağ sütun 30k.

| Faz — dolma s / en uzun blok ms (>250 ms sayısı) | offscreen, 303 sürüm | windows, 30001 sürüm |
|---|---|---|
| `projects_open` | 0,39 / 290 (1) | 12,76 / 636 (4) |
| `library` | 0,16 / 54 (0) | 19,59 / 593 (2) |
| `dataset` | 4,18 / 43 (0) | 413,32 / 770 (3) |
| `dataset_search` | 0,33 / 289 (1) | 2,90 / 2895 (6) |
| `processing_queue` | 0,13 / 63 (0) | 7,43 / 773 (1) |
| `export_page` | 0,14 / 37 (0) | 11,33 / 479 (2) |
| `export_check` | 15,68 / 53 (0) | 1859,61 / 144 (0) |
| `export_leave` | 0,20 / 38 (0) | 22,40 / 505 (2) |
| `export_return` | 0,16 / 27 (0) | 12,03 / 1815 (1) |
| `review_open` | 0,32 / 204 (0) | 1,36 / 348 (2) |
| `label_summary` | 0,09 / 52 (0) | 0,48 / 302 (1) |
| `timeline_scrub` | 0,05 / 48 (0) | 0,33 / 323 (1) |
| `select_movements` | 0,81 / 804 (1) | 4,47 / 4467 (1) |
| `label_edits` | 1,28 / 1281 (1) | 3,49 / 3486 (10) |
| `class_browser_open` | 0,01 / 12 (0) | 0,07 / 43 (0) |
| `class_browser_search` | 0,02 / 19 (0) | 0,06 / 51 (0) |
| `theme_toggle` | 3,23 / 3158 (1) | 3,95 / 3736 (1) |
| `theme_toggle_back` | 3,28 / 3227 (1) | 3,99 / 3796 (1) |

İşlem başına (30k): Veri Seti araması tuş başına **797 / 563 / 562 / 323 /
282 / 368 ms**; hareket seçimi **179 ms** ortalama (en çok 189; 600 hareket);
etiket düzenleme **349 ms** ortalama (en çok 365). Tekrarlı gezinme döngüsü
52 s; döngü başına en uzun blok ~1,9–2,0 s, 7–8 takılma; **sızıntı yok**
(ısınmadan sonra RSS +0,1 MB, widget sayısı 916 sabit); yakalanmamış istisna 0.

Okuma:

- **Ölçütü karşılayanlar:** 30 000 sürümün dışa aktarım kontrolü (31 dk, iş
  parçacığında; GUI en çok 144 ms), sınıf tarayıcısı (43 / 51 ms), 600
  hareketli sürümde hareket seçimi (< 190 ms), zaman çizelgesinde gezinme.
- **Karşılamayanlar (`open`):** liste ekranları 30 000 satırı tablo modeline
  aktarırken ve süzerken GUI thread'ini **0,5–1,8 s** bloklar (Projeler 636,
  İşlenen Videolar 593, Veri Seti 770, iş kuyruğu 773, Dışa Aktarım 479, Dışa
  Aktarım'a dönüş **1815 ms**); arama tuş başına 0,3–0,8 s; 600 hareketli
  sürümde etiket düzenleme ~350 ms ve etiket özeti 302 ms; tema değişimi 3,7 s.
- Yığın örneklerinin gösterdiği yerler: Veri Seti istatistik özetinin GUI
  thread'inde hesaplanması (`views/pages/dataset.py` `_show_stats`), zaman
  çizelgesinin 600 aralığı ve tutamaçlarını her seçimde yeniden boyaması
  (`timeline.py` `_paint_intervals` / `_paint_handles`), iş kuyruğunda
  kayıtların GUI thread'inde sıralanması (`processing.py` `_refill` →
  `sorted_takes`), bağlam şeridindeki disk yolu denetimleri
  (`context.py` `path_exists`). Gereken iş: artımlı/tembel tablo modeli,
  gecikmeli arama ve arka planda süzme, istatistiklerin iş parçacığında
  hesaplanması, zaman çizelgesinde değişmeyen katmanın önbelleği.
- Ölçüm sonunda, pencere kapanırken hâlâ süren bir arka plan işi silinmiş
  sinyal nesnesine sonuç göndermeye çalıştı ("Signal source has been
  deleted", `views/tasks.py`): kapanışta görülen, veri kaybı olmayan bir hata
  izi (`observed`).

## A4 — Paketlenebilirlik

| Madde | Bulgu | Durum |
|---|---|---|
| Depo-göreli yollar | `default_config_path()` `parents[3]/configs/default.yaml` arıyordu; wheel kurulumunda `Lib/configs/…` yok ve yükleyici **sessizce** dataclass varsayılanlarına düşüyordu | `verified` düzeltildi: dosya paket verisi (`kinecapture/resources/default.yaml`, `importlib.resources`); eksikse uyarı ve self-check hatası. Silme koruması `parents[3]` yerine paket klasörü, checkout ve `sys.prefix`'i korur. Paket içinde `__file__` ile paket dışına çıkan veya makineye özel yol kalmadığı testle taranıyor |
| Kurulum dizinine yazma | Bütün kullanıcı durumu `~/.kinecapture`, `~/KineCapture`, `%LOCALAPPDATA%\KineCapture` altında; cwd-göreli yazım yok | kodda `verified`; kurulu dizin anlık görüntü karşılaştırması Faz B'de |
| Konsolsuz çalışma | `pythonw.exe` altında `sys.stderr` None: konsol log işleyicisi artık eklenmiyor | `verified`: `pythonw -m kinecapture --self-check` **hiç standart tanıtıcı verilmeden** (kısayolun yaptığı gibi) başlatıldı; rapor ve log dosyası yazıldı, çıkış 0 |
| Çocuk süreçler | İşleme çocuğunun stdout/stderr'i **okunmayan borulara** bağlıydı: 1 MB yazan çocuk 20 s sonra hâlâ bloklu, iş sonsuza dek "çalışıyor" | `verified` düzeltildi: çıktı log dosyasına (`logs/processing/…`), hata ayrıntısı dosyanın sonundan; `CREATE_NO_WINDOW` + `CREATE_NEW_PROCESS_GROUP`; çalışma dizini log klasörü |
| Kaynaklar | Tema, yazı tipi, 72 ikon, logo, lisanslar wheel'de | `verified` wheel derlenip içeriği test edildi. **Önizleme modelleri** yalnız `~/.cache/kinecapture/models`'ten okunuyordu: temiz kurulumda kişi seçilemez, dolayısıyla kayıt başlatılamazdı. Artık `<sys.prefix>/share/kinecapture/models` de aranıyor; kurucu modelleri oraya koymalı (Faz B) |
| ZED SDK yokken | `pyzed` içe aktarılamadığında pencere kuruluyor, self-check "kamera kullanılamaz, diğer ekranlar çalışır" diyor | `verified` (içe aktarımı engelleyen sahte `pyzed` ile); `--expect-zed-sdk 5.4.1` verilirse başarısız sayılıyor |
| Self-check | `python -m kinecapture --self-check [--report] [--expect-zed-sdk] [--require-preview-models]` eklendi: paket, ayar, kaynaklar, Qt eklentisi, başsız Studio penceresi (sandbox), kullanıcı klasörleri yazılabilirliği, önizleme modelleri (SHA-256), ZED SDK sürümü | `verified` |
| Wheel kurulumu klon ortamda | `conda create --prefix C:\KCBuild\env --clone KineSynth --offline` (107 paket, 56 728 dosya; KineSynth'e dokunulmadı), editable `kinecapture` kaldırıldı, `pip wheel . --no-deps --no-build-isolation --no-index` ile üretilen `kinecapture-0.11.0` tekerleği kuruldu; testler depo kökünden klonun yorumlayıcısıyla koştu ve paketin `C:\KCBuild\env\Lib\site-packages` içinden yüklendiği her koşuda denetlendi | `verified`: 6 dosya (paketleme, A4, sahip tohumu, A2 export, Studio iş yükü, kurucu) **115/115 geçti** (son kodla sıfırdan klonlanan ortamda, 24 Eylül 02:50: **117/117**). İlk denemede 1 başarısız: kurulum klasörünü koruyan test, `C:\KCBuild` gibi sürücü köküne yakın bir klasörde retin derinlik kuralından (`delete_target_too_shallow`) geldiğini görmüyordu — ret doğru, test beklentisi dar; derinliğe göre iki kod da ret olarak kabul ediliyor, iki ortamda da geçiyor |

Testler: `tests/test_release_gate_packaging.py` (10), `tests/test_packaging.py`
(wheel kaynak içeriği).

## Kapı özeti

| Madde | Durum |
|---|---|
| A1 temel koşu | `verified` — son kodla dosya dosya tam koşu: ilk koşu 102/103 (bu gece eklenen bir sıralama hatasını yakaladı, düzeltildi); **ikinci koşu 103/103, 2102 geçti, 0 başarısız**, 38 koşullu atlama; `windows` platformunda önceden var olan 5 yerleşim testi başarısız (`24c1509`'da da) |
| A2 export doğruluğu | `verified` — 6 hata bulundu ve regresyon testiyle kapatıldı (şema 1.2.0); BODY_18/34/38, belirlenimcilik, kesinti, uzun yol, seçenekler, bağımsız oracle; gerçek veri **kısmen** (hata aralıklı gerçek örnek yok) |
| A3 ölçek | `verified` — 30k kayıt, 30k hareket, 100–200 sınıf, oracle 0 sorun; GUI darboğazları S1–S12 kapatıldı, ~300 sürümde tema dışında ölçüt karşılanıyor, sızıntı yok. **Karşılanmayan:** 30k kayıtta liste ekranları 0,5–1,8 s ve arama tuş başına 0,3–0,8 s GUI bloğu; 600 hareketli sürümde etiket düzenleme ~350 ms; tema değişimi 3,7 s; iş parçacığındaki işlerin doğrusalın üstünde büyümesi |
| A4 paketlenebilirlik | `verified` — depo-göreli yol yok, kaynaklar paket verisi, konsolsuz çalışma, alt süreçler, ZED'siz açılış, tekerlek klonda 115/115; kurulu uygulama kurucudan doğrulandı (Faz B) |

**Kapı kararı:** Faz A **koşullu**: doğruluk (export, oracle, testler) ve
paketlenebilirlik tam; ölçekte **GUI ölçütü (250 ms) 30 000 kayıtta liste
ekranlarında ve tema değişiminde karşılanmıyor**, iş parçacığındaki işler
30k'da dakikalar sürüyor. Kullanıcı 23 Eylül akşamı sabaha kadar müdahalesiz
kurucu istediği için onay beklenmeden Faz B'ye geçildi; bu maddeler onun
kararına açık bırakıldı (ürün ~yüzlerce sürümde ölçütü tema dışında
karşılıyor).

## Açık kalanlar (Faz A)

- **30k kayıtta liste ekranlarının GUI bloğu** (0,5–1,8 s; arama tuş başına
  0,3–0,8 s) ve 600 hareketli sürümde etiket düzenleme (~350 ms) — yerleri
  ve gereken iş "GUI, 30 000 kayıt" bölümünde.
- **Tema değişimi** 1,4–3,8 s GUI blok (ölçüt 250 ms) — kabul ya da stil
  sayfası yeniden düzenlemesi, kullanıcı kararı.
- **30k kayıtta doğrusalın üstünde büyüme** (iş parçacığında): soğuk indeks
  ×7, ısınmış Veri Seti ×26, export ×4,5 (10k → 30k). Neden `hypothesis`.
- **Gerçek kayıtla hata aralıklı örnek** pakete girmedi (etiketler
  tamamlanmamış).
- `rehab24_6_mocap` Studio'nun kanonik paketinde yok (yalnız eski
  `ReleaseBuilder`) — ürün kararı.
- Kanonik export sentetik kaydı dışlamıyor, `origin` ile işaretliyor —
  değiştirilmesi istenirse karar.
- Bilinen aralıklı iki test (`test_processing_pipeline.py` duraklat/sürdür,
  `test_identity.py` eşzamanlı kod ayırma) bu koşularda düşmedi.
