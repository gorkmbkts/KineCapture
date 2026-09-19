---
type: protocol
status: current
updated: 2026-09-18
tags:
  - test
  - measurement
  - environment
---

# Test ve ölçüm ortamı

Hangi koşuda alınan sonucun kanıt sayılabileceğini belirler. Bir ölçüm yanlış
ortamda alındıysa "çalıştırılmış test" değildir.

## Ortam

Yalnız mevcut `KineSynth` conda ortamı kullanılır:
`C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`. Betikler ortamı bulamazsa
başka ortama düşmez, durup ne yapılacağını söyler.

## Koşu biçimi

- **Tam `pytest` tek süreçte bitmiyor.** F1'de yaklaşık 28 dakikada
  tamamlanmadı; dosya dosya koşuda 39 dosyanın 38'i yaklaşık 6 dakikada yeşildi.
  Sonraki bütün turlarda kabul koşusu **dosya dosya** yapıldı ve proje kuralı
  hâline geldi. Neden bulunmadı; `status: open`.
- Tek dosyalık ve hedefli koşular normal biçimde çalışır.

## Qt platformu

- **`QT_QPA_PLATFORM=offscreen` altında font ailesi yoktur.** Bu denetimde
  yeniden ölçüldü: `QFontDatabase.families()` boş liste döndürüyor. Her metin
  tofu kutusu olarak ölçüldüğü için **yerleşim, genişlik, kırpılma ve minimum
  boyut ölçümleri offscreen'de geçersizdir**; aynı kabuk offscreen'de 1514 px
  minimum genişlik iddia ederken gerçek platformda 1120 px'e sığıyordu.
- Yerleşim ve görsel kabul ölçümleri `QT_QPA_PLATFORM=windows` ile, gerçek
  pencerede alınır. Çizim/segfault testleri offscreen'de kalabilir.
- Sonuç: 2026-09-13 öncesindeki offscreen yerleşim ölçümleri şüphelidir.

Bu madde
[eski test komutları notundaki](../archive/memory/8-8-test-komutlari.md)
"GUI testleri offscreen ile çalışır" ifadesini `superseded` yapar.

## Süreç geneli stil sızıntısı

`studio/views/theming.py:44` temayı `QApplication.setStyleSheet` ile
**süreç geneli** uygular. Aynı pytest sürecinde önce Studio testleri koşarsa
eski `gui/` widget ölçümleri bozulur; gözlenen örnek bir butonun 20 px yerine
46 px ölçülmesidir. Gerçek üründe tek arayüz çalıştığı için bu bir ürün hatası
değil, bir **ölçüm tuzağıdır**. Eski GUI ölçüm testi kendi stil sayfasıyla
yalıtılmış fixture kullanır.

## Bilinen aralıklı testler

| Test | Davranış | Durum |
|---|---|---|
| `tests/test_processing_pipeline.py` duraklat/sürdür | yaklaşık üç koşudan birinde takılıyor; alt sürecin `job.json`'a `paused` yazmasını bekleyen zamanlama yarışı | `observed` |
| `tests/test_identity.py:269` `test_participant_codes_are_unique_under_concurrent_allocation` | tam suite yükünde Windows dosya kilidi yarışıyla `PermissionError`; izole koşuda tekrar tekrar geçiyor | `observed`, en az 2026-08-31'den beri |

İkisi de bu çalışmalardan önce vardı ve ilgili modüller değişmeden de
düşebiliyor. Bir turda düştüklerinde önce izole koşuyla ayırt edin.

## Açık çelişki

`scripts/run_tests.ps1` hâlâ `QT_QPA_PLATFORM = 'offscreen'` ayarlıyor ve tek
süreçte `pytest` çağırıyor; yani betik yukarıdaki iki kuralın ikisine de
uymuyor. Betik bu denetimde değiştirilmedi. Kabul koşusu yapacak olan, betiği
kullanmak yerine dosya dosya ve `windows` platformuyla koşmalıdır.

İlgili: [Veri bütünlüğü ve kanıt](../concepts/data-integrity.md),
[AI hafıza iş akışı](ai-memory-workflow.md),
[Açık sorular](../open-questions.md),
[Hafıza aktarım denetimi](../audits/claude-memory-migration-audit-2026-09-18.md).

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [8. Test komutları](../archive/memory/8-8-test-komutlari.md)
- [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](../archive/memory/9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md)
- [QFont::setPointSize uyarısı — Qt kaynaklı, kanıtlandı](../archive/memory/6i-09-qfont-setpointsize-uyarisi-qt-kaynakli-kanitlandi.md)
- [Gerçekten çalıştırılanlar](../archive/memory/6i-10-gercekten-calistirilanlar.md)
- [Bu turda GERÇEKTEN çalıştırılanlar](../archive/memory/6g-09-bu-turda-gercekten-calistirilanlar.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
