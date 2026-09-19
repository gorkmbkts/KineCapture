---
type: legacy-memory-section
status: archived
title: "9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2978-2992"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](8-8-test-komutlari.md) · [sonraki](9-01-donanim-dumani-gercek-zed-2i.md) →

Alt notlar: [Donanım dumanı — GERÇEK ZED 2i](9-01-donanim-dumani-gercek-zed-2i.md) · [Redesign doğrulaması (2026-08-21, donanımsız)](9-02-redesign-dogrulamasi-2026-08-21-donanimsiz.md) · [Ham arşiv / kişi kilidi / sürekli aktivite doğrulaması (2026-08-24)](9-03-ham-arsiv-kisi-kilidi-surekli-aktivite-dogrulamasi-2026-08-24.md) · [Özellik katmanı doğrulaması (2026-08-23)](9-04-ozellik-katmani-dogrulamasi-2026-08-23.md) · [Ek olarak: donanımsız gövde dönüşümü testleri](9-05-ek-olarak-donanimsiz-govde-donusumu-testleri.md) · [Geliştirme sırasında bulunup düzeltilen gerçek hatalar](9-06-gelistirme-sirasinda-bulunup-duzeltilen-gercek-hatalar.md)

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md), [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md).

## 9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar

Hepsi kullanıcının Windows makinesinde, `KineSynth` environment içinde
çalıştırıldı.

| Doğrulama | Komut | Sonuç |
|---|---|---|
| Interpreter | `conda run -n KineSynth python -c "import sys; print(sys.executable)"` | `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`, Python 3.11.14 |
| Test paketi | `.\scripts\run_tests.ps1` | **561 passed**, 178.46 s (2026-08-26) |
| ZED'siz import | alt süreçte `sys.modules` kontrolü | `pyzed` hiç yüklenmedi |
| Self test | `python -m kinecapture --self-test` | exit 0; proje→export tamamı OK |
| Cihaz listesi | `python -m kinecapture --list-devices` | ZED SDK 5.4.1, ZED 2i S/N 31844341 AVAILABLE |
| İskelet tablosu | `python -m kinecapture.tools.verify_zed_topology` | BODY_18/34/38 üçü de SDK ile birebir uyuşuyor |
| GUI dumanı (offscreen) | 8 sayfa gezinme + tema değişimi | Hepsi kuruldu, gezinildi, iki tema da uygulandı |
