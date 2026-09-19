---
type: legacy-memory-section
status: archived
title: "6X. Tek kişiyle operatör kontrollü ZED testi — devam ediyor (2026-09-13)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2546-2579"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6w-6w-staj-defteri-zamanlama-dili-denetimi-ve-portal-metinleri-2026-09-11.md) · [sonraki](6y-6y-pyside6-arayuz-yeniden-yapimi-f0-hafiza-politikasi-f1-tespiti-2026-09.md) →

Güncel karşılığı: [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md), [Kişi seçimi ve subject lock](../../concepts/subject-selection.md).

## 6X. Tek kişiyle operatör kontrollü ZED testi — devam ediyor (2026-09-13)

Kullanıcı ZED'i bağladı; testte yalnız kendisi var. Baş/ayak kadrajını görüp
kaydı kendi başlatıp durdurmak istiyor. Yeni bağımsız
`tools/live_validation.py` penceresi bu amaçla eklendi: kırpılmayan RGB,
isteğe bağlı hafif 2D iskelet, model tahmini olduğu belirtilen kadraj ipucu,
Başlat/R, Durdur/Esc, iptal edilebilir 8 saniye hazırlık, varsayılan 20 saniye
kayıt üst sınırı ve Testi bitir. Ağır start/stop/finalize ayrı kontrol işçisinde;
ham kayıt kullanıcı düğmesi olmadan başlamaz. Tek kişinin seçimi kullanıcının
açık talebine dayanır; görüntü timestamp'li anchor yalnız kayıt başladıktan
sonraki tek ve kadrajda görünen kişi karesine yazılır. Çok kişili doğrulama yok.

Sentetik kontrol ilk turda 8 geçti / 1 hata: UI Take.duration_s yerine gerçek
Take.metrics.duration_s okumalıydı. Düzeltildikten sonra canlı test penceresi
ve capture architecture kapsamı **9 passed / 2.65 s**; JUnit
`C:\Users\gorke\KineCapture\zed_20260913\ui_tests_retry.xml`.
Geri sayımı iptal etmek kayıt yaratmıyor; manuel stop ve aktif kayıtta pencere
bitirme iki ayrı finalized mock take üretiyor. Yeni environment/paket yok.
App/package 0.11.0; take/skeleton 1.2.0, raw 1.1.0, processing 1.0.0,
canonical annotation 1.0.0; diğer şemalar 6V ile aynı ve değiştirilmedi.

SDK 5.4.1 ZED 2i S/N 31844341 AVAILABLE; 1280×720, 60 FPS, gerçek depth NONE,
body kapalı bağlantı doğrulandı. Başlangıç boş disk yaklaşık 203 GB.
İlk set `C:\Users\gorke\KineCapture\zed_20260913` altında 60 ve 40 saniyelik
iki gerçek kayıt içeriyor. Kullanıcı görüntüleri beğenmediğini ve kullanım
kesintisi yaşandığını belirterek **yeni set istedi**. İlk set silinmedi;
asıl yeni değerlendirme `C:\Users\gorke\KineCapture\zed_20260913_b` altındadır.
Yeni pencerede kullanıcı kontrollü çekim devam ediyor; GPU offline işi pencere
Testi bitir ile kapatılmadan başlamayacak. İki ilk 20 saniyelik yeni kaydın
ikisi de front_pose seçimiyle kaydedilmiş; ikinci çekimin gerçek yönü soruldu.
Kaynaklar partial: native status false olayı var; tek başına başarı iddiası
yok. SVO yeniden okuma ve nihai rapor henüz tamamlanmadı. Bu bölüm geçici devam
noktasıdır; bitince gerçek ölçümler ve doğrulanamayanlar eklenmelidir.
