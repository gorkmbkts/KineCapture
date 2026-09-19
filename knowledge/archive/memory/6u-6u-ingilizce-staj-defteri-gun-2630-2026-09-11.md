---
type: legacy-memory-section
status: archived
title: "6U. İngilizce staj defteri gün 26–30 (2026-09-11)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2335-2374"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6t-06-oneri-ve-kalici-sinir.md) · [sonraki](6v-6v-capture-verileri-hesapla-etiketleme-backend-devami-2026-09-11.md) →

Güncel karşılığı: [Staj raporu turları](../../milestones/internship-reports.md).

## 6U. İngilizce staj defteri gün 26–30 (2026-09-11)

Kullanıcının devam isteği üzerine staj defterinin son beş günü İngilizce olarak
hazırlandı ve
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Internship_Report_Days_26_30_EN.docx`
yoluna kaydedildi. Önceki raporun sade Word düzeni şablon olarak korundu; yeni
belge 8 sayfa, 5 `Heading 1` gün başlığı ve 5 satır içi görsel içeriyor. Günlük
metin uzunlukları sırasıyla 368, 357, 332, 352 ve 351 kelime. Günlerin açılışları
ve anlatım akışı birbirinden farklı tutuldu; kronolojik bir laboratuvar özeti
yerine o gün yapılan mühendislik işine odaklanıldı.

Rapor kapsamı gerçek kod ve yerel kanıta dayanıyor: gün 26 kayıtlı squat
verisindeki BODY_34 düz-bacak hatasının BODY_38 ile karşılaştırılması; gün 27
değişmez SVO2 kaynağını merkeze alan raw-first kayıt profili; gün 28 kayıttan
bağımsız, bounded latest-frame önizleme çalışanı; gün 29 hash korumalı,
iptal/yeniden başlatma destekli ve atomik yayımlanan offline işleme; gün 30 ise
checksum doğrulamalı review sınırı ve canonical source anchor kullanımı. Yerel
Squat BODY_34 overlay karesiyle birlikte `CaptureProfile`, `LatestWorker`,
`process_take` ve `ReviewDataset` gerçek kod parçalarından dört okunabilir görsel
üretildi. Bu rapor turunda uygulama kaynak koduna veya şemalara değişiklik
yapılmadı; kullanıcının mevcut working-tree çalışması korundu.

Rapor hazırlanırken gerçek sürümler yeniden doğrulandı: app/package `0.11.0`,
project `1.1.0`, session `2.0.0`, take/skeleton stream `1.2.0`, raw archive
`1.1.0`, annotation/release `2.2.0`, label `2.0.0`, feature `1.0.0`, identity
SQLite `1`. Seçilmiş mimari ve işleme testleri önce varsayılan uzun Windows temp
yoluyla çalıştırıldı: 17 geçti, `Path.exists()` uzun türetilmiş yol sınırına
takıldığı için 1 test kaldı. Aynı kapsam kısa ve izole
`--basetemp C:\Users\gorke\AppData\Local\Temp\kc_report_2630` ile tekrarlandı;
18 test 5.50 saniyede geçti. Bu sonuç kısa çalışma yolundaki uygulama
davranışını doğruluyor, Windows uzun-yol hassasiyetini ortadan kaldırmıyor.

Belge kalite kontrolünde DOCX ZIP bütünlüğü geçti, beş başlık/beş görsel ve eski
gün 16–25 metninin bulunmadığı doğrulandı. Sekiz sayfanın tamamı render edilip
görsel olarak incelendi; kırpılma, üst üste binme, eksik görsel veya bozuk
karakter görülmedi. Erişilebilirlik denetimi high/medium/low için `0/0/0`, görsel
denetimi 5 inline şekil, heading denetimi 5 başlık verdi. Tam pytest paketi,
uygulama self-test'i, wheel/package testi ve bağlı canlı ZED testi bu rapor
turunda çalıştırılmadı.
