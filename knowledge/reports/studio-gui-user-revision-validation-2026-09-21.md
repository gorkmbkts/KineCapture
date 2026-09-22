---
type: report
status: verified
updated: 2026-09-21
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
  şey yapmıyor.
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
setinin dışında tut, hata aralığı ekle, sınıfsızlara uygula, silme; hata
kipinde başlangıç/bitiş, bağlı hareket, ilgili eklem özeti, tek "Eklemleri
düzenle", Harekete dön, Not ve silme; sağ panelde zemin, RGB iskelet kaplaması,
Gelişmiş, kamera presetleri, "ön" referansının açıklaması, sporcu seçimi ve
belirsiz aralık eylemleri.

## Çalıştırılan testler

`verified` — hepsi `QT_QPA_PLATFORM=offscreen` ile, kodun **son hâlinde**:

| Dosya(lar) | Sonuç |
|---|---|
| `test_studio_user_revision_2026_09_21.py` (bu turda yazıldı) | 11/11 |
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
