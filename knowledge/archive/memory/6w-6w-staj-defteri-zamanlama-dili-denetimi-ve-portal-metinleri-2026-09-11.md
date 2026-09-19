---
type: legacy-memory-section
status: archived
title: "6W. Staj defteri zamanlama dili denetimi ve portal metinleri (2026-09-11)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2512-2545"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6v-05-devam-noktasi-donanim-bekleniyor.md) · [sonraki](6x-6x-tek-kisiyle-operator-kontrollu-zed-testi-devam-ediyor-2026-09-13.md) →

Güncel karşılığı: [Staj raporu turları](../../milestones/internship-reports.md).

## 6W. Staj defteri zamanlama dili denetimi ve portal metinleri (2026-09-11)

Dört staj DOCX'i salt okunur olarak tarandı; ZIP bütünlükleri geçti ve toplam
30 gün başlığı doğrulandı. Çıktı
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\Internship_Report_Form_Texts_and_Timing_Audit.txt`
yoluna UTF-8 düz metin olarak yazıldı. Mevcut DOCX'ler değiştirilmedi.

Günlük ana metinlerinin büyük bölümü o güne ait çalışma kaydı gibi okunuyor.
Dokuz riskli/meta ifade konumuyla birlikte işaretlendi: ilk beş gün girişindeki
`taslak bölüm`; gün 8 ve 10'daki sonradan bilinen modeli anlatan `later`
ifadeleri; gün 16–25 ile 26–30 girişlerindeki `this section records...` ve
sonradan görsel üretimini açıklayan cümle; gün 25'te `last day of this section`
ve `ten-day period`; gün 30'da `I concluded the thirty-day report`. Her biri
için günlük dilini koruyan kısa alternatif verildi. `today`, `yesterday` ve
`the previous day` ifadeleri kronolojiyi desteklediği için sorun sayılmadı.
Ek tutarlılık riski: gün 1–5 Türkçe, gün 6–30 İngilizcedir.

Portal için kısa, resmî İngilizce `Table of Contents`, 129 sözcüklük `Abstract`,
kurumun tam adı/adresi/tarihçesi/faaliyet alanı/organizasyon yapısı ve 120
sözcüklük `Conclusion` hazırlandı. `Internship Activities, Job Descriptions and
Content` yalnız içindekiler girdisi olarak geçer; kullanıcı talebi gereği bu
bölüm için gövde metni yazılmadı, çünkü sistem günlük metin ve görsellerden
otomatik üretecek. YTÜ resmî sayfalarından Davutpaşa Kampüsü A Blok adresi,
üniversitenin 1911 kökeni, 1992 adı ve Kontrol ve Otomasyon Mühendisliği
Bölümünün 2009'da bağımsız bölüm oluşu kontrol edildi.

Bu turda uygulama kaynak/test/config dosyaları, kullanıcı kayıtları, şemalar ve
dört DOCX değiştirilmedi. Uygulama pytest'i, self-test, wheel, GUI render'ı veya
ZED donanım testi çalıştırılmadı; görev metin denetimi ve TXT üretimiydi. Gerçek
sürüm sabitleri yeniden okundu: app/package `0.11.0`, project `1.1.0`, session
`2.0.0`, take/skeleton stream `1.2.0`, raw archive `1.1.0`, annotation/release
`2.2.0`, label `2.0.0`, feature `1.0.0`, identity SQLite `1`. Kullanıcının
önceden var olan geniş backend/processing working-tree değişiklikleri korundu.
