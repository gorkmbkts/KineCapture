---
type: concept
status: decision
updated: 2026-09-18
tags:
  - data-integrity
  - evidence
---

# Veri bütünlüğü ve kanıt

## Değişmezler

- Kullanıcı verisi varsayılan olarak silinmez veya üzerine yazılmaz.
- JSON yazımları `kinecapture.core.jsonio` üzerinden atomiktir.
- Ham kayıt değişmezdir; etiketler ayrı sidecar'lardadır.
- Sentetik veri `DataOrigin.SYNTHETIC` ile uçtan uca işaretlenir.
- Eksik veya belirsiz eklem uydurulmaz; NaN korunur.
- Çalıştırılmamış test “geçti” sayılmaz.

## Kanıt önceliği

1. Mevcut kod ve değişmez ham veri
2. Çalıştırılmış test veya gerçek cihaz ölçümü
3. Git geçmişi
4. `verified` wiki notu
5. Konuşma özeti, gözlem veya hipotez

## Durum sözlüğü

- `verified`: bağımsız kanıtla doğrulandı
- `observed`: görüldü, nedeni kesin değil
- `decision`: bilinçli ürün/mimari tercihi
- `hypothesis`: sınanmadı
- `open`: çözülmedi
- `superseded`: daha yeni kanıtla geçersiz kaldı

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [6. Bu görevde alınan kalıcı teknik kararlar](../archive/memory/6-6-bu-gorevde-alinan-kalici-teknik-kararlar.md)
- [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](../archive/memory/6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md)
- [Geliştirme sırasında bulunup düzeltilen gerçek hatalar](../archive/memory/9-06-gelistirme-sirasinda-bulunup-duzeltilen-gercek-hatalar.md)
- [10. Bilinen sorunlar, riskler ve sınırlar](../archive/memory/10-10-bilinen-sorunlar-riskler-ve-sinirlar.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
