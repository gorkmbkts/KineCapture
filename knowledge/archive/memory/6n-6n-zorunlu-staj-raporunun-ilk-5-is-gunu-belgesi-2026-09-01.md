---
type: legacy-memory-section
status: archived
title: "6N. Zorunlu staj raporunun ilk 5 iş günü belgesi (2026-09-01)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1803-1829"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6m-6m-30-gunluk-zorunlu-staj-raporu-icin-kaynak-denetimi-ve-anlati-plani-20.md) · [sonraki](6o-6o-ingilizce-staj-raporu-615-is-gunleri-2026-09-02.md) →

Güncel karşılığı: [Staj raporu turları](../../milestones/internship-reports.md).

## 6N. Zorunlu staj raporunun ilk 5 iş günü belgesi (2026-09-01)

30 günlük rapor planının ilk beş günü, düzenlenebilir Word belgesi olarak
`C:\Users\gorke\Desktop\KineSynthV3\staj_raporu\KineSynthV3_Staj_Raporu_Ilk_5_Gun.docx`
yolunda üretildi. Kapakta yalnız kullanıcı tarafından verilen kurum bilgileri
kullanıldı: Yıldız Teknik Üniversitesi, Elektrik-Elektronik Fakültesi,
Kontrol ve Otomasyon Mühendisliği Bölümü ve araştırma laboratuvarı. Ad,
öğrenci numarası, staj tarihleri veya laboratuvarın özel adı uydurulmadı.

Günler sırasıyla proje bütününün incelenmesi, REHAB24-6 veri yapısı,
anotasyon/tekrar sınırları, tekrar bazlı indeksleme ve değişken uzunluklu veri
erişimi, KineSynthV3 masaüstü inceleme uygulamasını kapsar. Metinler birinci
tekil şahısla yazıldı; sözcük sayıları gün 1-5 için **509, 502, 500, 502 ve
500**'dür. YTÜ logosuna ek olarak her gün için kaynak proje artefaktlarından
bir teknik görsel, şekil açıklaması, kaynak satırı ve alternatif metin
eklendi. Belge 12 sayfadır.

Doğrulama olarak belge LibreOffice ile PDF/sayfa PNG'lerine çevrildi ve 12
sayfanın tamamı görsel olarak incelendi; kırpılma, taşma veya okunamayan görsel
görülmedi. `images_audit.py` altı görselin tamamının inline olduğunu,
`a11y_audit.py` yüksek/orta/düşük önem düzeyinde bulgu olmadığını ve
`heading_audit.py` beş adet Heading 1 başlığı bulunduğunu doğruladı. Bu turda
KineCapture/KineSynth kaynak kodu, kullanıcı verisi veya şemalar değiştirilmedi;
uygulama testi, self-test, GUI testi ve ZED donanım testi çalıştırılmadı.
Gerçek sürümler değişmedi: KineCapture **0.10.0** (annotation/release 2.2.0
dahil önceki bölümdeki şemalar), KineSynthV3 **0.3.0**.
