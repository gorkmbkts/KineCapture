---
type: legacy-memory-section
status: archived
title: "Bu turda GERÇEKTEN çalıştırılanlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1181-1196"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-08-surumler.md) · [sonraki](6h-6h-sonraki-claude-gui-veri-gorevi-prompt-hazirligi-2026-08-30.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md).

### Bu turda GERÇEKTEN çalıştırılanlar

- `python -m pytest tests/` → **585 passed**, 196.75 s (uygulama sonrası tam
  tur; ara turlarda 25 kırmızı test yeni arayüze göre yeniden yazıldı).
- `.\scripts\run_tests.ps1 -Quiet` → "Testler gecti." (KineSynth, Python 3.11.14).
- `python -m kinecapture --self-test` → uçtan uca sentetik akış OK; export
  `dataset_v001`, 2 hareket örneği, 1 sürekli örnek, doğrulama geçti.
- İki ekran offscreen olarak **1120x700, 1366x768, 1600x980** boyutlarında ve
  **dark/light** temalarda gerçek `grab()` ile render edildi; `minimumSizeHint`
  değerleri ölçüldü, `FlowContainer` içindeki her kontrolün kutusunun içinde
  kaldığı test edildi.
- **Donanımda doğrulanmadı:** bu turda ZED 2i ile canlı kayıt alınmadı. Kişi
  kilidi, ham arşiv ve bindirme hizası mock backend ile ve daha önce (bölüm
  6D) alınmış gerçek kayıtların dosyalarıyla doğrulandı. Gerçek kamerada
  Capture uyarı şeridinin canlı kayıt kaybı senaryosu tetiklenmedi.
