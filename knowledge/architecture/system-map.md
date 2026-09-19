---
type: architecture
status: verified
updated: 2026-09-18
tags:
  - architecture
---

# Sistem haritası

## Katmanlar

| Paket | Sorumluluk |
|---|---|
| `core/` | Hatalar, kimlikler, atomik JSON, yollar, config, fingerprint |
| `domain/`, `dataset/` | Modeller, proje çalışma alanı, indeks, silme, özet |
| `camera/` | Mock ve ZED backend; `pyzed` yalnız `zed.py` içinde gecikmeli import |
| `capture/`, `preview/`, `recording/` | Canlı önizleme, kişi kilidi ve değişmez kayıt yazımı |
| `processing/` | Offline kaynak, iş, review, annotation, array, özet ve depth |
| `playback/`, `annotations/`, `export/`, `features/` | Okuma, etiket, kanonik yayın ve özellikler |
| `identity/` | Yerel SQLite kimlik ve erişim |
| `studio/` | PySide6 servis, viewmodel, tema ve yeni arayüz |
| `gui/` | `--legacy-gui` ile açılan eski arayüz |

## Kritik sınırlar

- Kamera bağımlılığı yalnız kamera katmanında bulunur.
- Ham kayıt değişmez; insan kararları sidecar dosyalarında yaşar.
- Canlı toplama ve offline yeniden üretim ayrı süreçlerdir.
- GUI thread kamera, disk veya işleme işiyle bloklanmaz.
- Eksik ölçüm tahmin edilmez; NaN olarak korunur.

İlgili: [Veri hattı](../concepts/pipeline.md),
[Veri bütünlüğü](../concepts/data-integrity.md).

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [3. Ortam — DOĞRULANMIŞ](../archive/memory/3-3-ortam-dogrulanmis.md)
- [6. Bu görevde alınan kalıcı teknik kararlar](../archive/memory/6-6-bu-gorevde-alinan-kalici-teknik-kararlar.md)
- [7. Mimari sınırlar](../archive/memory/7-7-mimari-sinirlar.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
