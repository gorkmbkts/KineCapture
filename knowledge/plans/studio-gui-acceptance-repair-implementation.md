---
type: plan
status: in-progress
created: 2026-09-20
updated: 2026-09-20
implementation_status: in-progress
tags:
  - studio
  - gui
  - annotation
  - acceptance
---

# Studio GUI kabul onarımı — uygulama planı

Görev: [düzeltme brifi](../../promts/CLAUDE_STUDIO_GUI_ACCEPTANCE_REPAIR_PROMPT_2026-09-20.md) ·
Denetim: [20 Eylül kabul denetimi](../audits/studio-gui-acceptance-audit-2026-09-20.md) ·
Karar: [yerleşim ve etiketleme yönü](../decisions/studio-gui-repair-2026-09-20.md) ·
Regresyon kapsamı: [19 Eylül gereksinimleri](../../promts/CLAUDE_STUDIO_GUI_FINAL_REFINEMENT_PROMPT_2026-09-19.md)

Sonuçlar: [doğrulama raporu](../reports/studio-gui-acceptance-repair-validation.md)

## 0. Kod okumasıyla saptanan kök nedenler

Aşağıdakilerin hepsi **kodda okunarak** bulundu; denetimin `observed`
bulgularının kod karşılığıdır. Ekran görüntüsü tek başına kök neden değildir.

| Belirti | Kök neden | Kanıt |
|---|---|---|
| Alt bant boş | `solve_stage` genişlikten sınırlanıyor: `band_height(panel) = (1852−465)/2.778 = 499`, tavan ise `830−148−48 = 634`. Kullanılmayan **135 px** `bands.addStretch(1)` ile dibe toplanıyor. | `stage_layout.py:109-128`; `review.py:190-194` yorumu bunu *tercih* olarak açıklıyor |
| Sağ panel kaydırıyor | `_build_inspector` her şeyi bir `QScrollArea` içine koyuyor; `_scrolled()` kamera ve kişi için aynısını yapıyor | `review.py:592-600`, `review.py:641-649` |
| Her düzenleyicinin üstünde hareket listesi | `movement_list` ortak `column`'a, `self.inspector` yığınının **üstüne** ekleniyor | `review.py:580-586` |
| Eski checkbox eklem listesi | `_build_error_inspector` hâlâ `self.role_list` kuruyor | `review.py:960-964` |
| Preset referansı yanlış | `set_reference_azimuth(self.skeleton.camera.azimuth)` — anatomik ön değil, o anki **sanal kameranın** açısı; varsayılan 35° | `review.py:1180`; `services/skeleton3d.py:59` |
| "Üst" tam tepeden değil | Preset 78° ilan ediyor; 90°'de `cross(forward, up)` sıfırlanıp view matrisi bozulduğu için kaçınılmış | `camera_presets.py:54`; `services/skeleton3d.py:143-152` |

`MAX_ELEVATION` 89.43°'dir, yani 78° **clamp değil**, presetin kendi değeri.

## 1. Fazlar

Sıra bağımlılığa göre: ölçüm altyapısı → veri doğruluğu → yerleşim → panel
içeriği → etkileşim → regresyon → kabul.

### P1 — Gerçek girdi olaylarıyla ölçüm altyapısı

**Neden önce.** Sonraki her iddia bununla kapatılacak. Denetimin kendi notu
`_joint_picked(index)` doğrudan çağrısının kabul kapatmadığını söylüyor;
bu yüzden harness `QTest` ile gerçek fare olayı göndermeli.

**Çıktı.** `tests/_gui_harness.py` (paylaşılan fixture) + scratchpad ölçüm
betiği: gerçek Windows Qt penceresi, gerçek GL, **anatomik önü bilinen
asimetrik** sentetik iskelet, 1920×1080 / 1366×768 / minimum ve ≥1 yüksek DPI.
`QTest.mouseClick` / `mouseDClick` / `mouseMove` yolları.

**Kapanış kontrolü.** Harness kendi kendini doğrular: fixture'ın ön yönü
bilinen bir değere eşit; `QTest` çift tıklaması `joint_picked` sinyalini
üretiyor.

### P2 — Anatomik ön yön ve gerçek tepeden bakış (R-04)

**Kök neden.** Yukarıda. Servis katmanında yön hesabı yok; çağıran taraf
kamera açısını referans veriyor.

**Çıktı.** `services/skeleton3d.py` içine Qt'siz `facing_azimuth(...)`:
omuz çizgisi ve kalça çizgisinden yer düzlemine izdüşümlü yön; kaynak
(`shoulders` / `hips` / `recording` / `manual` / `unknown`) ayrı döner.
`_after_open` bunu kullanır. `view_matrix` kutupta yedek `up` vektörüne
geçer; "Üst" gerçek tepeden bakış olur.

**Kapanış kontrolü.** Bilinen yönlü fixture'da `front` kamerası sporcunun
önünde; `right`/`left` anatomik sağ/sol; kayıt yeniden açıldığında referans
eski kameradan **etkilenmiyor**; kaynak adı panelde görünür.

### P3 — Kazanılan alanı etiketlemeye ayır (R-01)

**Çıktı.** Yeni `views/annotationbar.py`: yatay gruplu, bağlama duyarlı
**alt düzenleyici** (hareket / hata). `stage_layout.solve_stage` artık artan
yüksekliği `editor_height` olarak döndürür; `bands.addStretch(1)` kalkar.
Hareket ve hata formları sağ panelden çıkar; tekrarlanan hareket listesi
kalkar.

**Kapanış kontrolü.** Aynı pencerede kullanılmayan yükseklik ölçülür ve
**önce/sonra** tabloya girer; pencere büyüyünce gerçek içerik büyür; panel
değişince sahne zıplamaz; RGB oranı korunur; 3B alan kare kalır.

### P4 — Üst panelde kaydırma yok (R-02)

**Çıktı.** Kamera: kompakt preset matrisi + küçük yön göstergesi + temel
eylemler; ileri seçenekler ayrı mini pencereye. Özet: sayımlar + sıradaki
eksik + az sayıda kart; tam liste ayrı pencerede. Kişi: seçili kişi ve
güvenli işlemler; aday seçici ayrı.

**Kapanış kontrolü.** Üç sekmenin **her birinde** dikey ve yatay kaydırma
aralığı **0**; aynı anda hiçbir denetim kırpılmıyor; uzun Türkçe sınıf adı,
çok sınıf ve dar pencere ile tekrar ölçülür.

### P5 — Eklem seçimi ana etkileşim (R-03)

**Çıktı.** `role_list` ana akıştan çıkar; seçili eklemler okunabilir özet.
Taslak durumu görünür: talimat, sayı, iptal. Taslak açılırken oynatma
güvenli biçimde durur. Mevcut kanıtı düzenlemek ayrı açık eylem.

**Kapanış kontrolü.** `QTest` ile gerçek çift tık: bir/çok eklem, tekrar
kaldırma, orbit sürüklemesiyle karışmama, yüksek DPI ve farklı zoom'da
isabet; sınıf oluşturma → otomatik atama → yeniden açınca kalıcılık;
`roles_origin` ayrımı korunur.

### P6 — Eski gereksinim kimliklerinin regresyonu (R-05)

Önceki promptun bütün kimlikleri matrise alınır; yapılmış olan korunur,
eksik olan düzeltilir. Zemin ayrı incelenir: up-axis, dönüşüm, düzlem
denklemi ve geçerli ayak referansı.

### P7 — Kabul, performans ve teslim (R-06, R-07)

Dosya dosya test koşusu; gerçek pencere ekran görüntüleri; önce/sonra
performans; doğrulama raporu; `MEMORY_INDEX` yalnız gerçek duruma göre.

## 2. Gereksinim → faz eşlemesi

| Kimlik | Faz | Durum |
|---|---|---|
| R-01 kazanılan alan | P3 | planlandı |
| R-02 kaydırma yasağı | P4 | planlandı |
| R-03 eklem seçimi | P5 | planlandı |
| R-04 preset referansı | P2 | planlandı |
| R-05 regresyon | P6 | planlandı |
| R-06 kullanıcı akışıyla kabul | P1, P7 | planlandı |
| R-07 Obsidian teslimi | P1–P7 | sürüyor |

19 Eylül kimliklerinin tam matrisi P6'da bu dosyaya eklenecek.

## 3. İlerleme günlüğü

### P0 — İnceleme · tamamlandı

Kod okundu, denetim kanıtı açıldı, kök nedenler yukarıdaki tabloya yazıldı.
Ölçüm denemesi: sürüm açılmadan yapılan ilk ölçüm **geçersizdi** — düzenleyici
hiç yerleşmediği için 640×480 varsayılan boyutlar okundu. Gerçek ölçüm
fixture ile açılmış sürüm gerektiriyor; P1 bunun içindir.

### P2 — Anatomik ön yön ve gerçek tepeden bakış · tamamlandı

Sıra P1'den önce alındı: P1 harness'inin kendi doğrulaması "ön yönü bilinen
fixture"a dayanıyor, o da bu fazın çıktısı.

**Yeni servis** `services/skeleton3d.py::facing_azimuth`. Omuz çizgisinden
(yoksa kalça) yer düzlemine izdüşümle yön; pencere ortalanır, NaN atlanır,
doldurulmaz. Kaynak ayrı döner: `shoulders` · `hips` · `manual` · `unknown`.
Formül `facing = normalise(cross(sol_omuz − sağ_omuz, yukarı))`; işaret
koordinat sisteminin el yönlülüğüne bağlı olduğu için `is_left_handed` ile
çevriliyor.

**Bulunan gerçek hata 1 — preset sağ/sol aynalıydı.** `OrbitCamera` yer
düzlemini "yukarı olmayan iki eksen, artan indis sırasıyla" diye
parametreleştiriyor. Bu sıralama **y-up'ta sol elli** (x × z = −y),
**z-up'ta sağ elli** (x × y = +z). Preset offsetleri tek bir yöne göre
yazıldığı için y-up kayıtlarda — yani ZED'in ürettiği kayıtlarda — "Sağ"
sporcunun **sol** omzunun yanına gidiyordu. Yeni `camera_presets.turn_sense`
tabanın determinantını alıp offseti kameranın kendi yönüne çeviriyor.
Eski referans zaten keyfî olduğu için bu hata daha önce görünür değildi.

**Bulunan gerçek hata 2 — "Üst" tepeden değildi.** Preset 78° ilan ediyordu;
sebebi kutupta `cross(forward, up)`'ın sıfırlanması. Çözüm yerine kaçınma
adlandırılmıştı. `OrbitCamera._reference_up` kutba yaklaşırken referansı bir
yer eksenine deviriyor; `MIN/MAX_ELEVATION` artık kutba 1e-4 kalıyor ve
preset **90°**. Doğrulama: tepeden bakışta baş ve ayak **aynı piksele**
düşüyor (0.0 px), omuzlar 93 px ayrı, matris sonlu.

**"Kayıt yönü" artık "Ön"ün ikinci adı değil.** Yeni
`skeleton3d.recording_azimuth(coordinate_system)` kaynak kameranın kendi
yönünü çözüyor (`right_handed_y_up` → 90°, `left_handed_y_up` → 270°,
`right_handed_z_up` → 270°, `..._x_fwd` → 180°, bilinmeyen → `None`).
`Preset.anatomical=False` olan tek preset bunu mutlak açı olarak kullanıyor;
konvansiyon bilinmiyorsa buton **devre dışı** ve nedeni tooltip'te.

**Dürüstlük.** Beden okunamazsa açı uydurulmuyor: kaynak `unknown` kalıyor,
kamera paneli "Ön yön belirlenemedi… 'Bunu ön yap' diyebilirsiniz" yazıyor ve
satır uyarı rengi alıyor.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_facing.py` **18 test**
yeşil: dört yön, y-up ve z-up, el yönlülüğü, pencere ortalama, NaN, omuz→kalça
geri çekilmesi, çakışan omuz, yatık omuz çizgisi reddi, ve **yan presetlerin
adını taşıdıkları omzun yanına düşmesi** (iki up ekseni için).
`test_studio_skeleton_view.py` ve `test_studio_workload.py` yeşil.

**Kendi eski testlerimden ikisi düştü ve haklı olarak düştü.**
`test_a_preset_is_measured_from_a_fixed_reference` yalnız "çeyrek tur mu"
diye soruyordu — denetimin "açı aritmetiği kullanıcının Ön beklentisini
doğrulamıyor" eleştirisinin birebir örneği; artık iki yan presetin **zıt**
yönlerde çeyrek tur olduğu, hangi tarafa düştüğü ise bedeni bilinen fixture'da
sınanıyor. `test_the_top_preset_does_not_reach_the_pole` kaçınmayı
koruyordu; yerine matrisin kutupta kullanılabilir olduğu sınanıyor.

### P1 — Gerçek girdi olaylarıyla harness · tamamlandı

**Çıktı.** `tests/_gui_harness.py`: gerçek pencere + gerçek işlenmiş sürüm;
`QTest.mouseClick` / `mouseDClick` / çok adımlı `drag`; timeline ve 3B için
widget'ın **kendi geometrisinden** hesaplanan tıklama noktası; kaydırma sayımı
ve kırpılma denetimi; ve anatomik önü **yapım gereği bilinen** asimetrik
gövde (`facing_pose`).

**Harness'in kendisi sınandı** (`tests/test_studio_gui_harness.py`, 19 test):
çift tık gerçekten widget'ın `mouseDoubleClickEvent`'ine ulaşıyor; sürükleme
tek sıçrama değil en az beş `mouseMove` gönderiyor; kaydırma sayımı var olan
kaydırmayı görüyor, olmayanı uydurmuyor; gövde iddia ettiği yöne bakıyor ve
asimetrik. Bir test helper'ı sessizce hiçbir şey yapmıyorsa üstüne kurulan
her test boşuna yeşildir — bu dosya onun için var.

**Bulunan gerçek hata (kendi testimde).** İlk `facing_pose` "sol"u (a, b)
düzleminde sabit bir çeyrek turla üretiyordu; y-up'ta doğru, z-up'ta yanlış
sonuç veriyordu. Sebep P2'de bulunan asimetrinin ta kendisi: (x, z, y) sol
elli, (x, y, z) sağ elli. Fixture da artık `left = up × forward` ile üç
boyutta türetiyor.

### P3 — Kazanılan alan etiketlemeye ayrıldı · tamamlandı

**Solver.** `solve_stage` artık `editor_height` ve `slack_height` döndürüyor.
Editörün **tabanı** tavan hesabına giriyor (çalışma yüzeyi, artık değil);
tabanın üstü sahnenin kullanamadığı yükseklikten geliyor.

| Pencere | Sahne | Editör | Artan |
|---|---|---|---|
| 1852×830 (denetimin penceresi) | 498 | **136** | **0** |
| 1852×940 | 498 | 220 (tavan) | 26 |
| 1318×628 | 306 | 126 | 0 |
| 1072×560 | 260 | 104 | 0 |

Denetimde boş bant olarak duran 135 px artık editör.

**Yeni `views/annotationbar.py`.** Yatay gruplu, iki modlu bant:
*seçili aralık* (başlık, durum, başlangıç/bitiş) · *sınıf* (buton şeridi +
yeni sınıf satırı) · *durum ve eylemler*. Hata modunda ayrıca *ilgili
eklemler* grubu. Seçim yokken tek satır — dolgu kartı değil.
Sınıf şeridi için Qt'de olmayan `FlowLayout` yazıldı: sabit ızgara kısa
adlarda genişlik harcar, uzun adlarda kırpar; kaydırma ise yasak.
`VISIBLE_CLASSES = 6`, gerisi "+N sınıf…" ile ayrı pencerede. Seçili sınıf
her zaman butonlar arasında — bantta olmayan bir sınıf "sınıf yok" gibi
okunurdu.

**Sağ panelden çıkanlar.** Hareket ve hata formları; her düzenleyicinin
üstünde tekrarlanan hareket listesi; checkbox eklem listesi. Not, sınıf
listesi ve eklem kanıtı düzenleme ayrı pencerelere
(`views/labelwindows.py`).

### P4 — Üst panelde kaydırma yok · tamamlandı

`_build_inspector` artık **hiçbir** `QScrollArea` kurmuyor; `_scrolled()`
yardımcısı silindi. Kişi paneli ikiye ayrıldı: panelde seçili sporcu, sayımlar
ve güvenli eylemler; kişi kartları ile belirsiz aralık listeleri
`SubjectListWindow` içinde. Paneller listeleri kendisi çiziyor
(`attach_lists`), yani bir kart nasıl görünür sorusunun tek cevabı var.

**Ölçüm.** `scroll_census` üç görünümde × dört pencere boyutunda
(1920×1080, 1600×900, 1366×768, 1129×700) **boş**. Editör bandı da her iki
modda boş.

**Bulunan gerçek hatalar.**
1. `ErrorRow` `roles_origin` taşımıyordu; kayıtta ayrım vardı ama ekran
   okuyamıyordu. Eklendi (`note` ile birlikte).
2. Yeni bandın "Sonraki eksik" butonu toolbar'daki ile **aynı attribute
   adını** kullanıyordu; ikincisi birincisinin üstüne yazıp sessizce
   bağlantısız bırakıyordu. Ayrı ad verildi.
3. `setFixedHeight(KcControlHeightSmall)` çağrıları stil sayfasının
   `min-height`'i tarafından eziliyordu: kontrol 24 px iddia edip 38 px
   oluyordu ve bant 7 px kısa kalıp spin box'ı kırpıyordu. Çağrılar
   kaldırıldı; yüksekliğe tek yer karar veriyor.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_editor_band.py`
**28 test** yeşil: solver aritmetiği, gerçek ekranda kullanılmayan yükseklik
≤ 24 px, üç sekme × dört boyutta sıfır kaydırma, iki mod, kırpılma yok,
14 sınıfla bant listeye dönüşmüyor, seçili sınıf her zaman görünür.

### P5 — Eklem seçimi ana etkileşim · tamamlandı

**Görünür durum.** Taslak açıkken 3B görünümün üstünde hata renginde bir
şerit: "Eklem seçin: … çift tıklayın" / "Eklem seçimi açık · N seçildi ·
çıkarmak için tekrar çift tıklayın". Talimat işaretlemenin yapıldığı yerde;
aynı metin sınıf şeridinin altında da var. Taslak kapanınca şerit siliniyor.

**Oynatma duruyor.** Taslak açılırken `playing` kapanıyor: hareket eden bir
bedende işaretleme, o anda imlecin altında ne varsa onu işaretlemektir.
Oynatma çizgisi kıpırdamıyor, hiçbir şey yazılmıyor.

**Bulunan gerçek hata 1 — yüksek DPI'da isabet yarıçapı.** `joint_at`
yarıçapı `PICK_RADIUS_PX * devicePixelRatioF()` ile çarpıyordu; oysa hem
izdüşüm hem fare konumu **mantıksal** piksel. %150 ölçekte düğüm ekranda aynı
boyutta kalırken tolerans 14'ten 21 mantıksal piksele çıkıyordu — hedefe
benzemeyen bir yerden tıklamak işe yarıyordu. Çarpan kaldırıldı; test üç
ölçekte (1.0 / 1.5 / 2.0) yarıçapın sabit olduğunu doğruluyor.

**Bulunan gerçek hata 2 — `Severity.SUCCESS` yok.** `_create_fault_class`
sınıfı yazdıktan sonra onay bildirimini kurarken `AttributeError` fırlatıyordu.
Qt sinyal işleyicisi Python istisnasını yutup stderr'e yazdığı için sınıf
oluşuyor, **onay mesajı her seferinde sessizce çöküyordu**. Önceki turun
testleri şemayı kontrol ettiği için bunu göremedi. `Severity.INFO` yapıldı.

**Bulunan gerçek hata 3 — yeni seçilen eklemler "miras" diye yazılıyordu.**
Sınıf oluşturulduktan sonra aralığa `apply_error_class` ile uygulanıyordu; o
ise sınıfın **varsayılanını** yazar ve `roles_origin = class_default` bırakır.
Oysa eklemler az önce bu tekrar için işaretlenmişti. Artık `label_error(...)`
ile `reviewed` olarak yazılıyor — kaydın koruduğu tek ayrım buydu ve tersine
çevrilmişti.

**Eski checkbox listesi ana akıştan çıktı.** Seçili eklemler okunabilir özet
("sol diz, sağ diz +2") ve kaynağı ("bu aralık için seçildi" / "sınıfın
varsayılanı"). İsimle düzeltme `JointEvidenceWindow` içinde, açık bir
"Eklemleri düzenle" eylemiyle; pencere yalnız o aralığın kanıtını değiştirir,
sınıfın varsayılanına dokunmaz.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_joint_picking.py`
**20 test** yeşil ve hepsi `QTest` ile gerçek olay gönderiyor: tek/çok eklem,
tekrar çift tıkla çıkarma, boş alan hiçbir şey seçmiyor, orbit sürüklemesinin
ardından gelen çift tık seçmiyor, picking açıkken kamera dönüyor, NaN eklem
seçilemiyor, üç DPI ölçeğinde yarıçap sabit, sınıf oluştur → uygula → panel
açık kalıyor → **sürümü kapatıp açınca kalıcı**.

**Önceki turun eklem testleri kaldırıldı.** `test_studio_label_panel.py`
içindeki grup `_joint_picked(index)` doğrudan çağırıyordu — denetimin
eleştirdiği şeyin ta kendisi. Yerini gerçek olaylı dosya aldı; kaldırıldığı
dosyada nedeni yazılı.

### P6 — Kullanıcının oturum içi üç isteği · tamamlandı

**1. Yeni sınıf kutusu satırı kaplıyordu.** `row.addWidget(self.new_name, 1)`
esnemeyi ona veriyordu; geniş pencerede alan ~1180 px'lik bir şerit oluyordu.
Sabit **220 px** (`NEW_NAME_WIDTH`) yapıldı, artan genişlik satır sonundaki
boşluğa gidiyor.

**2. "Hiçbir şey üst üste binmesin."** Ölçülmeden iddia edilemezdi; harness'e
`overlaps()` eklendi: aynı ebeveynin görünür çocukları arasında kesişim
arıyor, **widget'ların kendi geometrisinden**. İlk koşuda **gerçek binmeler**
buldu ve üçü de düzeltildi:

- **Bantlar sahnenin üstüne biniyordu** (1900×970'te 8 px, 1366×768'te 33 px,
  minimumda 77 px). İki ayrı kök neden vardı. (a) Solver'a timeline'ın
  yüksekliği token'dan veriliyordu: `KcTimelineMinHeight = 148` yalnız şeritleri
  sayıyor, cetvel ve boşluklarla gerçek taban **202**. (b) Bantlar arasındaki
  **boşluklar hiç sayılmıyordu** (3 × 4 px). Eskiden alttaki `addStretch`
  hatayı yutuyordu; editör o yüksekliği alınca hata görünür oldu. Artık
  timeline kendi `minimumHeight`'ini söylüyor ve `solve_stage` `band_spacing`
  alıyor.
- **Kamera paneli kendi içinde biniyordu**: 455 px'lik bantta **652 px**
  istiyordu, pusula altındaki satırın üstüne çiziliyordu. Panel sıkıştırıldı
  (pusula 96→72, presetler 3 sütun, üç temel araç) ve bakışı kaydet / kayıtlı
  bakış / bunu ön yap / hareketi azalt `AdvancedCameraWindow`'a taşındı.
  Yeni ölçüm: **454 px**.
- **Sınıf şeridi kendi içinde biniyordu**: `minimumSizeHint` override'ı
  ebeveyn layout'a **ulaşmıyor** — bir widget'ın layout'u varsa Qt
  `qSmartMinSize` layout'un minimumunu alıp hint'i hiç sormuyor. Şerit 101 px
  istiyor, 118 px çiziyordu. Gerçek `setMinimumHeight` kondu.

Son ölçüm: 13 ekran görüntüsünün hepsinde **binme 0, kaydırma 0, kırpılma 0**.

**3. Uygulama artık yalnız tam ekran.** Kullanıcı kararı: farklı pencere
boyutları desteklenmeyecek. `run_studio` her zaman `showMaximized`, ve
`StudioWindow.showEvent` bunu her yoldan geçen yerde uyguluyor — sonradan
gelen bir `show()` eskisinden sıyrılabiliyordu. Hatırlanmış "restored"
geometri artık uygulanmıyor.

### P6b — Bütün iskelet biçimlerinde eklem etiketleme · tamamlandı

Kullanıcının isteği: kamera bağlı değilken de BODY_18 / BODY_34 / BODY_38'in
desteklendiğinden ve **yanlış etiketleme olmadığından** emin olmak.

**Bulunan gerçek hata 1 — sentetik yeniden işleme biçimi yok sayıyordu.**
`SyntheticSource` üreticisini `skeleton` vermeden kuruyordu; hangi biçim
istenirse istensin **`mock_16`** üretiyordu ve sürüm kendini öyle ilan
ediyordu. `jobs.py` içindeki tutarlılık kapısı geçiyordu çünkü kaynak ve
paketler kendi aralarında tutarlıydı. Gerçek SVO yolu (`SvoSource`) zaten
`profile.body_format` ile SDK'yı yeniden çalıştırıyor, yani **gerçek
kayıtlar etkilenmemişti**; etkilenen şey sentetik yolla diğer biçimlerin
sınanamamasıydı. Artık `profile.body_format` uygulanıyor, bilinmeyen biçim
sessizce değiştirilmiyor, hata veriyor.

**Bulunan gerçek hata 2 — kaydın iskeletinde olmayan rol yazılabiliyordu.**
`AnnotationStore.label_error` köken/durum tutarlılığını denetliyordu ama
rolün **bu kaydın iskeletinde var olup olmadığını** denetlemiyordu. BODY_34
üzerinde tanımlanmış bir sınıf `head`, `left_hand`, `right_hand` adlarını
taşıyabilir; BODY_38'de bunların üçü de yok. Store artık `skeleton` alıyor ve
`roles_not_in_skeleton` ile **reddediyor** — sessizce kırpmıyor, çünkü
kırpmak yapılan iddiadan farklı bir iddiayı kaydetmek olurdu.

**Bulunan gerçek hata 3 — adı olmayan eklem sessizce düşüyordu.** BODY_38'in
38 ekleminin 15'i (gözler, kulaklar, parmak uçları, küçük parmaklar,
`spine_1`) rol taşımıyor. Çift tıklayınca vurgulanıyor ve sayaç artıyordu,
sonra `_role_names` onu atıyordu: üç eklem seçip ikisinin kaydedildiği,
ekranda bunu söyleyen hiçbir şey olmayan bir durum. Artık **seçilmiyor** ve
nedeni hem 3B şeridinde hem şerit ipucunda yazıyor.

**Mock jeneratörü bütün ZED eklemlerini üretebiliyor.** `_REST_POSE` 16'dan
40 girdiye çıkarıldı (omurga, yüz işaretleri, köprücük, el/parmak zinciri,
ayak/topuk/parmak). Sentetik oldukları ve ölçüm olmadıkları yazılı. Böylece
üç biçim de kamera olmadan üretilip sınanabiliyor. `rehab24_6_mocap` bir
**export hedefi**, kameranın ürettiği bir biçim değil; duruşu yok ve
istenirse açık bir hata veriyor.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_skeleton_formats.py`
**34 test yeşil, 1 anlamlı skip** (BODY_34 zaten bütün rollere sahip):
her biçimin rol tablosu var; her rol **adı kendisiyle uyuşan** bir ekleme
düşüyor (sağ/sol dahil); iki rol aynı eklemi paylaşmıyor; bir çiftin sağı ve
solu farklı eklemler; store eksik rolü reddediyor; iskeleti bilinmeyen sürüm
iddiada bulunmuyor; **aynı kayıt üç biçime yeniden işleniyor** ve her birinde
gerçek çift tıkla seçilen eklemin **adı doğru yazılıyor**; adı olmayan eklem
gerçek çift tıkla reddediliyor; başka biçimin sınıfı buraya yazılamıyor.

### P7 — Kabul, kanıt ve teslim · tamamlandı

**Görsel kanıt.** Gerçek `StudioWindow`, gerçek Qt/GL, tam ekran, gerçek
`QTest` olayları. 13 ekran görüntüsü + geometri manifesti:
`C:/Users/gorke/.codex/visualizations/2026/09/20/gui-repair-after`.
Hepsinde binme 0, kaydırma 0, kırpılma 0, kullanılmayan yükseklik 0.

**Bulunan son gerçek hata — 3B üstündeki metinlerin hiçbiri görünmüyordu.**
Banner eklendikten sonra ekran görüntüsünde yoktu. Ölçüldü: bannerın
renginden **0/99 piksel**. `QPainter` ile `QOpenGLWidget` üstüne yazmak ne
`paintEvent`'te ne `paintGL` sonunda çalışıyor. Notlar çocuk widget'a
çevrildi: **85/99**. Bu kusur önceki turlardan beri vardı ve "Bu sürümde 3B
eklem verisi yok." mesajını da kapsıyordu. Test artık dizgeyi değil
**görünürlüğü** sınıyor — ilk yazdığım test yalnız dizgeyi okuduğu için iki
başarısız denemeden de geçmişti.

**Yapıya uyarlanan eski testler.** `test_studio_review_gui` (kaldırılan
hareket listesi → timeline aralıkları ve bandın modu),
`test_studio_subject_gui` ve `test_studio_polish` (listeler pencereye taşındı,
panel `attach_lists` ile ödünç layout alıyor), `test_processing_pipeline`
(16 eklem sabiti → sürümün kendi `skeleton_spec.json`'undaki sayı).

**Bilinen aralıklı test.** `test_cancelling_a_paused_job_does_not_wait_for_a_resume`
bir turda düştü; izole koşuda **3/3 geçti**. Test notunda bu çalışmalardan
önce kayıtlı duraklat/sürdür yarışı.

**Teslim.** [Doğrulama raporu](../reports/studio-gui-acceptance-repair-validation.md);
`MEMORY_INDEX`, açık sorular ve test protokolü gerçek duruma göre
güncellendi. Görsel kabul kullanıcıda olduğu için hiçbir yere "GUI kapsamı
kapandı" yazılmadı.

### Devam noktası

**Sıradaki faz:** yok — P1–P7 tamamlandı. Kabul kullanıcıdadır.
**Son tamamlanan:** P7.
