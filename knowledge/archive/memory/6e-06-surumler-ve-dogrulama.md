---
type: legacy-memory-section
status: archived
title: "Sürümler ve doğrulama"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "911-954"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · ← [önceki](6e-05-gui.md) · [sonraki](6f-6f-capture-ve-inceleme-etiketleme-sadelestirme-promptu-2026-08-27.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### Sürümler ve doğrulama

- Uygulama/paket: **0.9.0**.
- `PROJECT_SCHEMA_VERSION`: **1.1.0**.
- `SESSION_SCHEMA_VERSION`: **2.0.0** (minimum participant +
  `operator_user_id`).
- `TAKE_SCHEMA_VERSION`: **1.1.0** (`operator_user_id`).
- Identity SQLite schema: **1**. Annotation/export/feature/raw schema sürümleri
  bu görevde değişmedi.
- Yeni bağımlılık kurulmadı; yalnız standart kütüphane `sqlite3`, `hashlib`,
  `secrets` kullanıldı.

Gerçekten çalıştırılan sonuçlar:

```text
.\scripts\run_tests.ps1
  KineSynth · Python 3.11.14 · 561 passed in 178.46 s

conda run -n KineSynth python -m kinecapture --self-test
  exit 0 · 72 kare · playback OK · ham RGB-D 72/72
  2 hareket + 1 hata aralığı + 1 sürekli örnek · export doğrulama geçti

GUI offscreen smoke/paint
  ilk kurulum, login, self-registration, owner dialogu, bütün çalışma
  sayfaları, minimum 1120x700 ve dark/light: geçti
```

**Bu görevde gerçek ZED kamera yeniden çalıştırılmadı.** Capture ana düzeni ve
donanım backend'i değiştirilmedi; mock hattı ve bütün donanımsız regresyonlar
geçti. Önceki 2026-08-24 donanım kanıtı geçerlidir fakat bu auth turunun yeni
bir donanım doğrulaması değildir.

Legacy test verisi için silme öncesi üç kesin KineCapture proje dizini
doğrulandı (`muhasebe`, `Full Test`, `Demo`). PowerShell `Remove-Item`
runtime güvenlik katmanı tarafından işlem başlamadan reddedildi; ardından üç
hedefin de hâlâ var olduğu doğrulandı. **Hiçbir eski klasör silinmedi.** Yeni
identity DB bunları otomatik kaydetmez/açmaz. Kalan kesin yollar:

```text
C:\Users\gorke\KineCapture\datasets\projects\prj_20260820T164820_1e49
C:\Users\gorke\KineCapture\datasets\projects\prj_20260821T111333_a60a
C:\Users\gorke\AppData\Local\Temp\shots4_iu_kvaue\datasets\projects\prj_20260824T135007_2cb6
```
