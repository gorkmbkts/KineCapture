---
type: audit
status: open
updated: 2026-09-20
tags: [studio, gui, acceptance, evidence]
---

# Studio GUI — tamamlanma iddiasının yeniden değerlendirilmesi

## Sonuç ve kapsam

`decision`: Kullanıcı 20 Eylül'de GUI sonucunu kabul etmedi; kullanılmayan
alan, kaydırmalı sağ panel, iskelet üzerinden eklem seçimi deneyimi ve yanlış
preset açılarını yeniden açtı. Yeni karar: üstte üç yardımcı sekme, altta
ayrı hareket/hata düzenleyicisi; üst panelde kaydırma kesinlikle olmayacak.

`observed`: Python ile gerçek Windows Qt arayüzü görüntülendi. 13 PNG ve
geometri manifesti kaydedildi. Bu bir uygulama düzeltmesi değildir; ürün kodu
bu denetimde değiştirilmedi ve tam test suite'i çalıştırılmadı.

`superseded`: Önceki “F1–F17 tamamlandı, GUI kapsamı kapandı” ifadesi kullanıcı
deneyiminin kabulü anlamında geçerli değildir. Önceki testlerin gerçekten
alınmış sonuçları iptal edilmiyor; sonuçlardan çıkarılan kapsam kapanışı
yeniden açılıyor.

## Kanıtın üretimi ve sınırı

Başlangıçta normal `python -m kinecapture` çalıştırıldı ve yükleme yüzeyi
görüldü. Kullanıcı masaüstü otomasyonunu durdurup limit nedeniyle Python
ile ekran üretimini istedi. Sonraki kayıtlar KineSynth içinden uygulamanın
gerçek `StudioWindow`/`ReviewPage` sınıfları ve mevcut test fixture'larıyla
ayrı veri/kimlik/ayar kökünde üretildi. Qt platformu Windows, pencere 1900×970,
sentetik 24 kare, kaynak boyutu 320×180. Kamera bağlanmadı; gerçek kayıt veya
kullanıcı etiketleri değiştirilmedi.

Sayfa durumları programatik kuruldu; fixture'ın doğrudan session attach
yolundan sonra normal hazır-yüzey handler'ı çağrıldı. Dolayısıyla bu tur
gerçek açılış/picking/tek-tık uçtan uca kabul testi değildir. Proxy video
yokluğu fixture kaynaklıdır. Diğer sayfalardaki liste durumları boştur;
bu ekranlar dolu veri, işleme performansı veya export kabulünü kanıtlamaz.
Giriş ekranı bu tur yeniden görüntülenmedi. Canlı donanım ölçümü yapılmadı.

Kanıt klasörü (wiki dışında, yerel):

`C:\Users\gorke\.codex\visualizations\2026\09\19\01a0b73e-0a13-7be0-a8ad-eb03e808cc4d\gui-audit-2026-09-20`

Tekrarlama betiği `capture_audit.py`; ölçüm `manifest.json`.

## Bulgular

| Kimlik | Kanıt düzeyi ve bulgu | Kaynak |
|---|---|---|
| A01 | `verified` Kod artan yüksekliği özellikle altta boşluk olarak topluyor; kullanıcı kazanılan alanı kullanmak istiyor. | `review.py`, `bands.addStretch(1)` açıklaması; `stage_layout.py`; `02-annotation-movement.png` |
| A02 | `observed` 465×496 sağ panelde hareket 319 px, hata 124 px, kamera 136 px, özet 124 px dış dikey kaydırma. İki sınıfın alanı bile 14 px kaydırıyor. | `manifest.json`; `02`, `03`, `05`, `09` PNG |
| A03 | `verified` Üç sağ sekme QScrollArea ile sarılmış; hata formunda eski checkbox eklem listesi var. Bu tesadüfi scrollbar değil, açık yerleşim tercihi. | `review.py::_build_inspector`, `_scrolled`, `_build_error_inspector`; `labelviews.py` |
| A04 | `verified` Eklem picking altyapısı mevcut; yeni sınıf adı yazılınca seçim taslağı açılıyor. `observed` Görselde çift tık talimatı çıkıyor ama eski liste aynı anda duruyor. Gerçek çift tık başarısı bu tur sınanmadı. | `review.py::_fault_draft_typed`, `_joint_picked`; `04-error-joint-selection-draft.png` |
| A05 | `verified` Anatomik ön, eklem verisinden türetilmek yerine o anki kameranın azimutundan atanıyor. Varsayılan kamera 35°. Hatırlanmış kamera da referansı etkileyebilir. | `review.py::_after_open` → `set_reference_azimuth(self.skeleton.camera.azimuth)`; `services/skeleton3d.py::OrbitCamera` |
| A06 | `verified` Kayıt yönü presetinin azimutu da aynı referans+0°; üst preset 78°. Kaynak kamera ve anatomik ön ayrımını yeniden doğrulamak gerekiyor. | `services/camera_presets.py::PRESETS`, `camera_for_preset` |
| A07 | `observed` 3B alan 498×496; kare iç viewport/çerçeve hesabı yeniden kabul kapsamına alındı. | manifest |
| A08 | `observed` Özet görünümü de form boyutlarından etkilenerek scroll taşıyor; hareket editöründe tekrar hareket listesiyle geniş boşluk var. | `02`, `09`; inspector stack ve ortak üst liste |
| A09 | `observed` Küresel/renkli düğümler, tek araç satırı, dikey ikonlar, üst check kaldırılması, capture Bağlan konumu ve tek alt satır mevcut. Hepsini yapılmamış saymak yanlış. | PNG'ler ve mevcut kod |

Zeminin sentetik görüntüsü ayrıca kontrol edilmeli; bu tur SDK zemin
çıkarımı veya gerçek kayıt koordinatları için hata teşhisi koymaz. Bağlantısız
capture düğmesi disabled; etkin kayıt rengini bu görüntüyle değerlendiremeyiz.

## Önceki çalışma neden sonucu karşılamadı?

Claude'un iç niyeti veya bütün çalışma süreci bilinmiyor. Aşağıdakiler
kayıt/kod kaynaklı nedenlerdir; motivasyon tahmini değildir:

1. **Yerleşim tercihi kullanıcı amacından saptı.** Kod yorumları kazanılan
   yüksekliği boş marj olarak bırakmayı, yoğun paneli ise scroll içine almayı
   bilinçli uygulama tercihi olarak açıklıyor. Teknik taşmayı önlemek alanın
   etiketleme işinde kullanıldığı anlamına gelmedi.
2. **Preset referansının anlamı eksik kuruldu.** Servis bağıl açı ve animasyonu
   hesaplıyor, fakat çağıran taraf anatomik ön yerine kamera açısını veriyor.
   Açı aritmetiği testi kullanıcının “Ön” beklentisini doğrulamıyor.
3. **Bazı testler kullanıcı girişini atlıyor.** `test_studio_label_panel.py`
   eklem seçimi testlerinde `_joint_picked(index)` doğrudan çağrılıyor. Bu
   veri atamasını sınar, düğüme çift tıklamanın erişilebilirliğini/isabetini
   tek başına sınamaz. Seçimin hiç uygulanmadığı sonucu da çıkarılamaz.
4. **Kabul kapsamından geniş tamamlanma ifadesi kullanıldı.** Önceki rapor
   gerçek eklemli çizimin ve fareyle sürüklemenin denenmediğini açıkça
   söylüyor; hafıza indeksi buna rağmen GUI kapsamını kapatmış. Gerçek pencere
   ölçümü yapılmış olması tüm kullanıcı akışlarının doğrulandığı anlamına
   gelmiyor. Raporun son tablo satırı 83/84 derken indeks 83/83 diyordu;
   izole tekrarlar ile ilk/son koşu sonuçları tek sayıya indirgenmemeli.
5. **Yeni gereksinimi eski eksikle ayırmak gerekir.** Kesin kaydırma yasağı
   ve alt iki modlu yeni editör 20 Eylül netleştirmesidir. Bunların tamamını
   önceki Claude'un açık talimatı ihlal etmesi diye yazmak doğru olmaz.
   Önceki prompt görsel kabul istiyordu, fakat eski sağ paneldeki üçlü etiket
   varyantı şimdi değişiyor. Yeni brif bu kabul ölçütünü somutlaştırıyor.

## İzlenebilir kaynaklar ve devam

- [Önceki uygulama planı](../plans/studio-gui-refinement-implementation.md)
- [Önceki doğrulama raporu](../reports/studio-gui-refinement-validation.md)
- [Yeni tasarım/fikir haritası](../decisions/studio-gui-repair-2026-09-20.md)
- [Claude düzeltme görevi](../../promts/CLAUDE_STUDIO_GUI_ACCEPTANCE_REPAIR_PROMPT_2026-09-20.md)

`open`: Yeni tasarım henüz uygulanmadı; gerçek eklemle picking/preset,
yüksek DPI ve minimum boyut, dolu diğer sayfalar ve performans kabulü
düzeltme görevinin sorumluluğunda. Önceki başarıları koruyarak bütün eski
gereksinim kimlikleri yeniden kontrol edilecek.
