---
type: legacy-memory-section
status: archived
title: "Geliştirme sırasında bulunup düzeltilen gerçek hatalar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3190-3227"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · ← [önceki](9-05-ek-olarak-donanimsiz-govde-donusumu-testleri.md) · [sonraki](10-10-bilinen-sorunlar-riskler-ve-sinirlar.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md).

### Geliştirme sırasında bulunup düzeltilen gerçek hatalar

1. **Windows 260 karakter yol sınırı**: derin dizin yapısı + uzun kimlikler
   `FileNotFoundError` üretiyordu. `core/paths.py` ile `\\?\` öneki eklendi,
   geçici dosya öneki kısaltıldı.
2. **Tekrar aralığı anlamı çelişkiliydi**: GUI konum, export kamera kare
   numarası varsayıyordu; kare düşünce ayrışıyorlardı. Konum standardı
   seçildi ve manifest ikisini birden yazacak biçimde genişletildi.
3. **Sentetik backend seed'i görüntüyü etkilemiyordu**: farklı seed aynı
   kareyi üretiyordu. Arka plana seed'e bağlı ton ve grain eklendi.
4. **İlk gövde seçimi "kimlik değişimi" sayılıyordu**: `None → 1` geçişi
   metadata'ya sahte bir değişim yazıyordu.
5. **Boş export nedeni gizliydi**: yalnız "örnek bulunamadı" diyordu; artık
   dışlanma nedenlerini ve hedefe uygun çözümü yazıyor.
6. **Derinlik renklendirmesinde NaN cast uyarısı**: ramp yalnız ölçülen
   piksellere uygulanacak biçimde düzeltildi.
7. **GUI çizim çökmesi (segfault)**: `QPainter.drawPolygon` timeline'da üç
   ayrı `QPointF` argümanıyla çağrılıyordu. PySide6 bunu Qt'nin
   `(const QPointF *, int)` aşırı yüklemesine bağlıyor, ikinci nokta "adet"
   olarak yorumlanıyor ve dizinin çok ötesi okunuyor → **access violation**.
   İnceleme sayfasına her geçişte uygulamayı çökürtüyordu. `QPolygonF` ile
   düzeltildi.
   **Neden kaçtı:** hiçbir test widget'ları gerçekten çizdirmiyordu; kurma ve
   veri verme paint kodunu hiç çalıştırmıyor. `tests/test_gui_painting.py`
   (31 test) eklendi: her özel widget `grab()` ile gerçekten çizdiriliyor
   (boş, tek kare, tamamı NaN, en yakın/uzak zoom, çoklu gövde, her tema).
   Düzeltme geri alınarak testin gerçekten yakaladığı doğrulandı.
8. **Capture ve İnceleme yan panelleri taşıyordu**: sağ sütundaki kartlar
   980 px yükseklikte sıkışıp metinleri üst üste biniyor, form alanları
   kırpılıyordu. Her iki panel kaydırılabilir hale getirildi.
9. **Testler gerçek kullanıcı ayarlarını bozuyordu**: GUI testleri tema ve
   proje değiştirdiğinde `AppState.save_preferences()` gerçek
   `~/.kinecapture/user_state.yaml` dosyasına yazıyor, pytest'in geçici
   klasörü kullanıcının dataset kökü olarak kaydediliyordu. conftest'te
   autouse bir fixture ile `USER_STATE_PATH` izole edildi ve
   `tests/test_user_state.py` bunu koruyan 5 test eklendi. Kirlenen dosya
   silindi.
