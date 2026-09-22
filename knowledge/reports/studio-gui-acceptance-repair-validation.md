---
type: report
status: current
created: 2026-09-20
updated: 2026-09-20
tags:
  - studio
  - gui
  - annotation
  - acceptance
  - measurement
---

# Studio GUI kabul onarımı — çalıştırılan doğrulamalar

> Sonraki gerçek kullanımda kayıt başlangıcı, uzun kişi kaybı ve kaybolan
> yardımcı panel bildirildi. Bu raporun geçmiş ölçümleri korunur; bütün gerçek
> kullanımın sorunsuz olduğu sonucu çıkarılamaz. [Yeni bulgular ve görev](../audits/capture-tracking-gui-issues-2026-09-20.md).

Yalnız **gerçekten çalıştırılan** kontroller ve ölçümler. Plan ve gerekçeler
[uygulama planında](../plans/studio-gui-acceptance-repair-implementation.md);
reddedilen durumun kanıtı
[20 Eylül denetiminde](../audits/studio-gui-acceptance-audit-2026-09-20.md).

Kanıt düzeyi: `verified` (bu ortamda çalıştırıldı) · `observed` (gözlendi) ·
`doğrulanmadı` (çalıştırılamadı).

## Ortam ve kanıt konumu

| | |
|---|---|
| Python | 3.11.14 (`KineSynth`) |
| Qt platformu | ölçümlerde `QT_QPA_PLATFORM=windows`, gerçek GL |
| Pencere | tam ekran (1920×1009 istemci alanı) |
| Fixture | sentetik 24 kare, 320×180; ayrı veri/kimlik kökü |
| Tarih | 2026-09-20 |

Ekran görüntüleri ve geometri manifesti (wiki dışında, yerel):

`C:\Users\gorke\.codex\visualizations\2026\09\20\gui-repair-after`

Kullanıcı kaydı, etiketi, kimlik veritabanı ve ayarları **okunmadı ve
yazılmadı**. Önceki turun raporu silinmedi; hangi iddiaların geçersiz kaldığı
aşağıda tek tek yazılı.

## 1. Önceki turun geçersiz kalan iddiaları

| Önceki iddia | Yeni kanıt |
|---|---|
| "Kullanılmayan yükseklik ≤ 24 px" | Ölçüt yanlıştı: bantların **konumları** değil yükseklikleri toplanıyordu. Gerçek ölçümde sahne editörün üstüne **8–77 px biniyordu**. |
| "Üç sekmede kaydırma yok" | Doğrudur, ama kaydırma yerine **binme** vardı: kamera paneli 455 px'lik bantta 652 px istiyordu. |
| "3B görünümde 'eklem seç' durumu" | Metin **hiç çizilmiyordu**. `QOpenGLWidget` üstünde `QPainter` ile yazılan her not görünmezdi. |
| "Eklem seçimi çalışıyor" | Veri yolu çalışıyordu; **gerçek çift tık** sınanmamıştı, yüksek DPI yarıçapı yanlıştı, adsız eklem sessizce düşüyordu. |
| "Presetler doğru" | Açı aritmetiği doğruydu; **referans** anatomik değildi ve y-up kayıtlarda sağ/sol **aynalıydı**. |

## 2. Bulunan ve düzeltilen gerçek hatalar

Onu da ölçülerek bulundu, hiçbiri ekran görüntüsüne bakılarak tahmin
edilmedi.

| # | Hata | Nasıl bulundu | Durum |
|---|---|---|---|
| 1 | Preset offsetleri y-up kayıtlarda sağ/sol aynalıyordu | Bedeni bilinen fixture'da "Sağ" sol omzun yanına düştü | düzeltildi (`turn_sense`) |
| 2 | "Üst" 78°'ydi ve tam tepeden diye sunuluyordu | Preset tablosu + kutup dejenerasyonu okundu | düzeltildi (90°, kutup güvenli) |
| 3 | Anatomik ön, sanal kameranın açısıydı | `_after_open` okundu | düzeltildi (`facing_azimuth`) |
| 4 | `Severity.SUCCESS` yok; sınıf onayı her seferinde çöküyordu | Qt sinyali istisnayı yutuyordu, test stderr'de gördü | düzeltildi |
| 5 | Yeni seçilen eklemler `class_default` diye yazılıyordu | Kalıcılık testi | düzeltildi (`reviewed`) |
| 6 | Yüksek DPI'da isabet yarıçapı ölçekle büyüyordu | Üç DPI oranında test | düzeltildi |
| 7 | Solver bant boşluklarını ve timeline'ın gerçek tabanını saymıyordu | `overlaps()` ölçümü | düzeltildi |
| 8 | Sınıf şeridi `minimumSizeHint` override'ı ebeveyne ulaşmıyordu | `overlaps()` ölçümü | düzeltildi |
| 9 | Sentetik yeniden işleme `body_format`'ı yok sayıyordu | Biçim testi `mock_16` gördü | düzeltildi |
| 10 | Kaydın iskeletinde olmayan rol yazılabiliyordu | Çapraz biçim testi | düzeltildi (`roles_not_in_skeleton`) |
| 11 | Adı olmayan eklem seçilip sessizce düşüyordu | BODY_38 rol kapsamı sayıldı | düzeltildi (reddediliyor) |
| 12 | 3B üstündeki notların **hiçbiri** görünmüyordu | Bannerın rengi piksel piksel arandı: 0/99 | düzeltildi (widget katmanı, 85/99) |

(12) önceki turlardan beri süregelen bir kusurdur ve "Bu sürümde 3B eklem
verisi yok." mesajını da kapsıyordu.

## 3. Yerleşim — `verified`

Tam ekran, gerçek GL, 13 ekran görüntüsü:

| Ölçüm | Sonuç |
|---|---|
| Binen widget çifti | **0** (13/13 görüntü) |
| Panel içi kaydırma aralığı | **0** (kamera · etiket özeti · kişi) |
| Editör bandında kaydırma | **0** (hareket ve hata modu) |
| Kırpılan denetim | **0** |
| Kullanılmayan yükseklik | **0 px** |
| Yeni sınıf kutusu genişliği | **220 px** (satırı kaplamıyor) |

Bant paylaşımı (1920×1009 tam ekran): sahne 478 · editör 129 · araç 48 ·
timeline 202. Sahne içinde görüntü 850 · 3B **478×476 (kare)** · panel 465.

Önce/sonra, denetimin penceresinde (1852×830 istemci alanı):

| | Önce | Sonra |
|---|---|---|
| Alt bantta boş alan | ~135 px | **0** |
| Hareket düzenleyicisi kaydırması | 319 px | **0** |
| Hata düzenleyicisi kaydırması | 124 px | **0** |
| Kamera sekmesi kaydırması | 136 px | **0** |
| Özet kaydırması | 124 px | **0** |
| Sahne/editör binmesi | — | **0** |

## 4. Eklem seçimi — `verified`, gerçek olaylarla

`QTest.mouseDClick` ile, eklemin **izdüşüm pikseline**; izdüşüm widget'ın
kendisinden alınıyor, yeniden hesaplanmıyor.

| Kontrol | Sonuç |
|---|---|
| Tek eklem seçme | ✓ |
| Çoklu seçim (3 eklem) | ✓ |
| Tekrar çift tıkla çıkarma | ✓ |
| Boş alan hiçbir şey seçmiyor | ✓ |
| Orbit sürüklemesinden sonra gelen çift tık seçmiyor | ✓ |
| Picking açıkken kamera dönüyor | ✓ |
| NaN eklem seçilemiyor | ✓ |
| Yarıçap %100/%150/%200'de aynı | ✓ |
| Taslak açılınca oynatma duruyor | ✓ |
| Banner **görünür** (metin değil, görünürlük) | ✓ |
| Sınıf oluştur → uygula → panel açık kalıyor | ✓ |
| Sürümü kapatıp açınca kalıcı | ✓ |

## 5. İskelet biçimleri — `verified`

Aynı kayıt üç biçime **gerçekten yeniden işlendi**.

| Biçim | Eklem | Rol | Adsız eklem |
|---|---|---|---|
| `zed_body_18` | 18 | 14 | 4 (gözler, kulaklar) |
| `zed_body_34` | 34 | 26 (tamamı) | 8 (parmak, göz, kulak) |
| `zed_body_38` | 38 | 23 | 15 (yüz, parmak, küçük parmak, `spine_1`) |
| `mock_16` | 16 | 16 | 0 |
| `rehab24_6_mocap` | 26 | 23 | 3 |

Kontroller: her biçimin rol tablosu var · her rol **adı kendisiyle uyuşan**
bir ekleme düşüyor (sağ/sol dahil) · iki rol aynı eklemi paylaşmıyor · bir
çiftin sağı ve solu farklı eklemler · her biçimde gerçek çift tıkla seçilen
eklemin **adı doğru yazılıyor** · adı olmayan eklem gerçek çift tıkla
**reddediliyor** · başka biçimin sınıfı buraya **yazılamıyor**.

`rehab24_6_mocap` bir **export hedefidir**, kameranın ürettiği bir biçim
değil; sentetik duruşu yok ve istenirse açık hata veriyor.

## 6. Preset referansı — `verified`

Omuz çizgisinden ölçülen ön yönle, tam ekran gerçek pencerede:

| Preset | Azimut | Yükseliş | Referans |
|---|---|---|---|
| Ön | 90° | 8° | 90° |
| Sağ | 180° | 8° | 90° |
| Üst | 90° | **90°** | 90° |
| Kayıt yönü | 90° | 8° | 90° |

Kamera paneli: "Ön yön omuz çizgisinden ölçüldü." · kaynak `shoulders`.

Tepeden bakış aritmetiği: baş ve ayak **aynı piksele** düşüyor (0.0 px),
omuzlar 93 px ayrı, matris sonlu.

## 7. Testler

Yeni dosyalar: `test_studio_facing.py` (18) ·
`test_studio_gui_harness.py` (20) · `test_studio_editor_band.py` (28) ·
`test_studio_joint_picking.py` (21) · `test_studio_skeleton_formats.py`
(34 + 1 anlamlı skip).

**Kabul koşusu** — proje kuralı gereği dosya dosya, `QT_QPA_PLATFORM=offscreen`:
**88/89 dosya yeşil** (2279 s). Tek düşüş `test_processing_pipeline.py`
içindeki duraklat/sürdür ailesi — test notunda bu çalışmalardan **önce**
kayıtlı aralıklı yarış; izole koşuda **3/3 geçti** (iki ayrı turda iki farklı
test bu aileden düştü, ikisi de izole geçti).

Yerleşim ve etkileşim ölçümleri `QT_QPA_PLATFORM=windows` ile gerçek
pencerede alındı; offscreen'de font veritabanı boş olduğu için oradan alınan
geometri kanıt sayılmaz.

Önceki turun `test_studio_label_panel.py` içindeki eklem grubu **kaldırıldı**:
`_joint_picked(index)` doğrudan çağırıyordu ve denetimin eleştirisi buydu.
Yerini gerçek olaylı dosya aldı; kaldırıldığı yerde nedeni yazılı.

## 8. Kalan doğrulanmamış sınırlar

- **Gerçek ZED SVO ile yeniden işleme** çalıştırılmadı: donanım/SVO yok.
  `SvoSource` zaten `profile.body_format` ile SDK'yı yeniden çalıştırıyor ve
  kod okunarak doğrulandı, fakat **çalıştırılmadı**.
- **Gerçek eklem verisiyle** etiketleme ölçülmedi; fixture sentetik.
- **Canlı kamera, GPU ve kayıt kaybı** ölçülmedi.
- **Fare ile kamera sürükleme** el ile denenmedi; `QTest` ile sınandı.
- **Tam ekran dışındaki pencere boyutları** artık desteklenmiyor (20 Eylül
  kullanıcı kararı), bu yüzden o boyutlar kabul hedefi değildir.
- `rehab24_6_mocap` sentetik olarak üretilemez; export hedefi olarak kalır.
