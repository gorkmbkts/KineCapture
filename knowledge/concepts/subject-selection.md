---
type: concept
status: verified
updated: 2026-09-21
tags:
  - subject-lock
  - capture
---

# Kişi seçimi ve subject lock

## Güncel davranış

- Kayıt için kişi seçimi zorunludur; anchor yoksa `_can_record()` reddeder.
- Red nedeni tek bildirim kartıyla gösterilir; görüntü üstündeki ikinci
  kopya 21 Eylül onarımında kaldırıldı (önceki çift gösterim `superseded`).
- Seçilen kişinin çerçevesi önizlemede çizilir.
- Kayıt öncesi anchor ilk kaydedilen kareye uygulanır.
- Vücut imzası yalnız `tracking_state == ok` karelerinden hesaplanır.
- İmza vetosu yalnız çok bedenli karelerde ve üç çelişki karesinden sonra
  devreye girer.
- Uzuv kanıtı varsa duruşla değişen eklem bulutu yüksekliği tek başına veto
  edemez. `AMBIGUOUS`, yalnız kendi tracker kimliğinin 30 kesintisiz uyumlu
  karesiyle kurtarılabilir; başka kişiye geçmez.
- Çelişkili kare görülme zamanını yeniler, **güvenilir konumu ve imzayı
  değiştirmez**. Mevcut sıçrama regresyon testleri ve uzun çelişki sonrası
  dönüş testiyle doğrulandı; ayrıntı
  [onarım raporunda](../reports/capture-tracking-gui-repair-validation.md).

## Kanıt sınırı

Tek kişili gerçek ZED kaydı uçtan uca doğrulandı. Gerçek iki kişili kadraj
oluşturulamadığından çok kişili davranış yalnız sentetik test kanıtına sahiptir.

Kişi seçilmeden alınmış eski iki kayıt için sonradan kare-anchor seçici henüz
yoktur.

İlgili: [Canlı ZED doğrulaması](../experiments/2026-09-18-live-zed.md),
[Açık sorular](../open-questions.md).

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [Kişi kilidi (`capture/subject_lock.py`, algoritma sürümü 1.0.0)](../archive/memory/6d-04-kisi-kilidi-capture-subject-lock-py-algoritma-surumu-1-0-0.md)
- [6P. Squat bacak takibi ve ertelenmiş iskelet işleme tanısı (2026-09-02)](../archive/memory/6p-6p-squat-bacak-takibi-ve-ertelenmis-iskelet-isleme-tanisi-2026-09-02.md)
- [6X. Tek kişiyle operatör kontrollü ZED testi — devam ediyor (2026-09-13)](../archive/memory/6x-6x-tek-kisiyle-operator-kontrollu-zed-testi-devam-ediyor-2026-09-13.md)
- [6AF. 17 Eylül — gerçek ZED kaydından etiketlemeye giden zincir](../archive/memory/6af-6af-17-eylul-gercek-zed-kaydindan-etiketlemeye-giden-zincir.md)
- [6AG. 18 Eylül — canlı ZED turu ve veri kalitesi ölçümleri](../archive/memory/6ag-6ag-18-eylul-canli-zed-turu-ve-veri-kalitesi-olcumleri.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
