# KineCapture — kısa hafıza indeksi

Bu dosya her görevde okunacak tek başlangıç kaynağıdır. Ayrıntı için yalnız
ilgili bağlantıyı aç. Tarihsel arşivi topluca yükleme.

## Güncel durum

- Studio F0–F15 tamamlandı; kayıt → işleme → etiketleme zinciri gerçek ZED ile
  18 Eylül 2026'da doğrulandı.
- Uygulama `0.11.0`; processing `1.1.0`; canonical annotation `1.1.0`;
  subject association `1.2.0`; identity şema `1`.
- Ortam: `KineSynth`, Python 3.11.14, PySide6 6.10.1, numpy 2.4.6,
  OpenCV 4.12, ZED SDK 5.4.1 / pyzed 5.4.
- Durum makinesi:
  `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING → REVIEWING`;
  hata durumu `ERROR`.

Ana görünüm: [KineCapture wiki](knowledge/index.md)

## Göreve göre yönlendirme

- Mimari ve modül sınırları:
  [Sistem haritası](knowledge/architecture/system-map.md)
- Hafıza, Obsidian ve token politikası:
  [Hafıza sistemi](knowledge/architecture/memory-system.md)
- Kayıt → işleme → etiketleme → export:
  [Veri hattı](knowledge/concepts/pipeline.md)
- Etiket modeli ve özellik katmanı:
  [Etiket ve feature sözleşmesi](knowledge/concepts/annotation-and-features.md)
- RGB-D, SVO2 ve depth sınırları:
  [RGB-D ve depth](knowledge/concepts/rgbd-and-depth.md)
- Kimlik ve proje erişimi:
  [Kimlik ve erişim](knowledge/concepts/identity-and-access.md)
- Kişi seçimi, anchor ve subject lock:
  [Kişi seçimi](knowledge/concepts/subject-selection.md)
- Ham veri, atomik yazım ve kanıt düzeyi:
  [Veri bütünlüğü](knowledge/concepts/data-integrity.md)
- Testin hangi koşuda kanıt sayıldığı:
  [Test ve ölçüm ortamı](knowledge/protocols/test-and-measurement.md)
- Gerçek kamera sonuçları:
  [18 Eylül canlı ZED doğrulaması](knowledge/experiments/2026-09-18-live-zed.md)
- Açıklar ve sonraki adım:
  [Açık sorular](knowledge/open-questions.md)
- Commit geçmişi:
  [Git kilometre taşları](knowledge/milestones/git-history.md)
- Studio F0–F15 faz özeti:
  [Studio fazları](knowledge/milestones/studio-f0-f15.md)
- Eski belgeler ve konuşmalar:
  [Kaynak sicili](knowledge/sources/source-registry.md)

## Bilinen açıklar

- Gerçek iki kişili kadraj üretilemedi; subject-lock çok kişili davranışı
  yalnız sentetik test edildi.
- Kişi seçilmeden alınan iki eski kayıt için kare-anchor seçici yok.
- Sporcu seçimi ile işlemede kilitlenen kişi arasında uyuşmazlık kapısı yok
  (kodda doğrulandı, 18 Eylül 2026).
- Kanonik export paketi gerçek kayıtla uçtan uca doğrulanmadı.
- `test_processing_pipeline.py` ve `test_identity.py` eşzamanlılık testi
  aralıklı takılabiliyor; ayrıntı test ve ölçüm notunda.
- SDK ilk model optimizasyonu uzun sürebilir; proxy video Windows uzun yolda
  açılamayabilir; `dataset_root` eski yolu gösterebilir; proje kilidi yok.

## Sonraki önerilen iş

Kişi seçilmemiş eski kayıtlar için kare-anchor seçici; ardından gerçek kayıtla
uçtan uca kanonik paket doğrulaması.

## Arşiv ve kaynaklar

- Bölünmüş eski hafıza: [Tarihsel MEMORY arşivi](knowledge/archive/memory/index.md)
- Eski görev promptları: [Prompt arşivi](promts/index.md)
- Eski plan ve raporlar: [Rapor arşivi](knowledge/archive/reports/index.md)
- Eski görev/prompt belgelerinin tamamı:
  [Belge sicili](knowledge/sources/document-registry.md)
- Claude ve Codex oturum kaynakları:
  [Konuşma sicili](knowledge/sources/conversation-registry.md)
- Oturum kapsaması ve karar defteri (sicil dosya sayar; Claude dosyalarının
  ikisi bir konuşmanın çatal kopyasıdır):
  [Hafıza aktarım denetimi](knowledge/audits/claude-memory-migration-audit-2026-09-18.md)
