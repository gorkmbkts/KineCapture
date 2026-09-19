---
type: legacy-memory-section
status: archived
title: "Etiketleme arayüzü — iki katman, iki küçük pencere"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1097-1114"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) · ← [önceki](6g-03-bindirme-hizasi-kok-neden-ofis-ofseti-degil.md) · [sonraki](6g-05-sinif-olusturma-iptal-ve-hazir-olma-semantigi.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Etiketleme arayüzü — iki katman, iki küçük pencere

- Kalıcı sağ panel, hareket listesi, hata listesi ve sürekli açık sınıf
  formları kaldırıldı. Zaman çizelgesi hem liste hem seçim yüzeyi.
- Kompakt, her zaman görünür eylem satırı: `Hareket ekle`, `Hata ekle`,
  `Etiketle`, sil/geri al/yinele/oynat-döngüle (ikon), ilerleme chip'i,
  `Sonraki eksik`, `Diğer…` menüsü (böl, birleştir, dışla, marker'lardan
  oluştur, yakınlaştır).
- **Çift tık** (veya `Enter`): hareket bandında `MovementLabelDialog`, hata
  bandında `ErrorLabelDialog` (`gui/widgets/label_dialogs.py`).
- Ortak `LabelClassPicker` (`gui/widgets/label_picker.py`, `LabelKind`
  parametreli) hem hareket hem hata sözlüğüne hizmet ediyor. Eski
  `gui/widgets/error_picker.py` **silindi** (kullanan kalmadı).
- Aralık **oluşturmak** pencere açmaz. Arka arkaya on tekrar çizerken on modal
  kabul edilemez; etiketleme ayrı ve açık bir eylem.
- `ReviewPage._run_dialog(dialog)` tek modal noktası — testler bu metodu
  değiştirerek gerçek diyalog widget'ını insansız sürüyor.
