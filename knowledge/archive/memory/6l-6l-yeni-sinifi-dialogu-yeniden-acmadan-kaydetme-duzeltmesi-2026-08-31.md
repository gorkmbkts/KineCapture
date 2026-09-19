---
type: legacy-memory-section
status: archived
title: "6L. Yeni sınıfı dialogu yeniden açmadan kaydetme düzeltmesi (2026-08-31)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1715-1755"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6k-6k-etkilenen-eklem-kaniti-ve-gui-cilasi-uygulandi-2026-08-31.md) · [sonraki](6m-6m-30-gunluk-zorunlu-staj-raporu-icin-kaynak-denetimi-ve-anlati-plani-20.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6L. Yeni sınıfı dialogu yeniden açmadan kaydetme düzeltmesi (2026-08-31)

Hareket ve hata etiketleme pencerelerinde yeni bir sınıf adı yazıp `Yeni …
türü ekle` denildiğinde taslak sınıf doğru biçimde tutuluyor, fakat `Kaydet`
düğmesinin uygunluk durumu yeniden hesaplanmıyordu. Bu nedenle sınıf ancak
dialog kapatılıp yeniden açıldıktan sonra atanabiliyordu.

- `MovementLabelDialog._creation_requested()` pending sınıfı kaydettikten
  sonra save gate'i yeniden hesaplıyor.
- `ErrorLabelDialog._sync()` pending sınıfta erken çıkmıyor; sınıf ile eklem
  doğrulamasını birlikte hesaplıyor. Yeni sınıf geçerli olsa bile
  “işaretlenen eklemler” seçilip node seçilmemişse kayıt hâlâ doğru biçimde
  engelleniyor.
- Yeni sınıfın gerçek oluşturulması ve aynı hareket/hata intervaline atanması
  mevcut `ReviewPage` akışında kaldı. Böylece proje sözlüğünün atomik yazımı,
  duplicate-normalization, iptalde sınıfın proje düzeyinde kalması ve hata
  intervalinin class + joint + note tek-işlem güncellemesi değişmedi.
- `tests/test_label_dialog_class_creation.py`, iki gerçek dialogda başlangıçta
  pasif olan `Kaydet` düğmesinin yeni sınıf tıklamasından sonra aynı pencere
  içinde etkinleştiğini ve gerçek Save tıklamasının dialogu kabul ettiğini
  sabitliyor.

Gerçek kod sürümleri değişmedi: app/package `0.10.0`, annotation/release
`2.2.0`, label `2.0.0`; diğer schema sürümleri bölüm 6K ile aynıdır.

Gerçekten çalıştırılan doğrulamalar:

- `tests/test_label_dialog_class_creation.py -q` → **2 passed**.
- İki mevcut sınıf oluşturma/atama ve iki eklem-save doğrulama testi →
  **4 passed**.
- Yeni dialog testleri + `test_review_flow.py` ve `test_annotations.py`
  içindeki `class` odaklı kapsam → **22 passed**. Bu komut önceki dört testten
  bazılarını tekrar içerir; sayılar bağımsız toplam gibi toplanmamalıdır.
- `scripts/run_tests.ps1 -Quiet` başlatıldı ve yaklaşık `%57` ilerlemeye kadar
  hata görülmedi; aynı makinedeki başka yüksek kaynaklı Python sürecine
  müdahale etmemek için bu Codex test süreci kullanıcıya bildirildikten sonra
  elle durduruldu. **Tam paket tamamlanmış veya geçmiş sayılmamalıdır.**

Bu küçük GUI durum düzeltmesinde ZED donanımı, self-test ve paket/wheel testi
çalıştırılmadı; kamera, export, şema ve paket kaynağı değiştirilmedi.
