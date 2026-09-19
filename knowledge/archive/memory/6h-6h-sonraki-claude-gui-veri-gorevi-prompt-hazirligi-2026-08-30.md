---
type: legacy-memory-section
status: archived
title: "6H. Sonraki Claude GUI/veri görevi — prompt hazırlığı (2026-08-30)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1197-1288"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6g-09-bu-turda-gercekten-calistirilanlar.md) · [sonraki](6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6H. Sonraki Claude GUI/veri görevi — prompt hazırlığı (2026-08-30)

> **Tarihsel.** Bu bölüm görev *öncesi* durumu ve onaylanan ürün
> kararlarını kaydeder. Başlığındaki "HENÜZ UYGULANMADI" artık geçerli
> değildir: prompt aynı gün uygulandı. Uygulanmış sonuç için **bölüm
> 6I**'ye bakın.

Kullanıcı son 0.8.0 arayüzünü yeniden değerlendirdi; mevcut kod, ilgili
testler ve geçici/izole GUI render'ları incelendikten sonra
CLAUDE_PROJECT_DELETE_LABELING_EXPORT_GUI_PROMPT.md oluşturuldu. Bu bölüm
uygulanmış özellikleri değil, onaylanan ürün kararlarını ve prompt hazırlama
denetimini kaydeder.

### Onaylanan ürün kararları

- **Proje silme kalıcıdır:** yalnız identity modelindeki tek System
  Owner/admin kullanabilir. Başarılı işlem proje klasörünü; ham kayıt, proxy,
  iskelet, annotation ve release'ler dahil fiziksel olarak kaldırmalı ve disk
  alanını boşaltmalıdır. Listeden kaldırma, soft delete, Recycle Bin veya
  kalıcı trash yeterli değildir. Normal user hem GUI hem servis katmanında
  engellenmelidir.
- Silme için proje adı/doğrulama metni isteyen güçlü bir onay, canonical path
  ve manifest kimliği kontrolü, geniş kök/symlink-junction koruması, aktif
  handle'ların kapanması, SQLite ilişki/audit düzeni ve kısmi hata/recovery
  politikası promptta zorunlu tutuldu. Gerçek kullanıcı projesi üzerinde
  destructive test yasaktır; yalnız disposable temp proje kullanılacaktır.
- **Correctness kullanıcı seçimi değildir:** hareket sınıfı kaydedilmiş ve
  sınıflandırılmış geçerli hata aralığı yoksa hareket otomatik Doğru ve
  export-ready; en az bir sınıflandırılmış hata aralığı varsa Hatalı; son hata
  aralığı silinirse yeniden Doğru olur. Sınıfsız/geçersiz hata aralığı
  hareketi unready bırakır.
- Mevcut 2.0.0 annotation'larda explicit Hatalı kararı olup hata aralığı
  bulunmaması sessizce Doğru'ya çevrilmeyecek; legacy çelişkisi görünür ve
  çözülene kadar export dışı olacaktır. Correctness otoritesi değiştiği için
  uygulayıcı gerçek schema/reader etkisini inceleyip uygun sürümleme ve
  idempotent migration kararı vermelidir.
- **Timeline trim preview** hem mevcut hareket/hata aralığının start/end
  kenarını düzenlerken hem de yeni hareket/hata aralığını ilk kez çizerken
  sürüklenen endpoint karesini gösterir. Drag başlangıcındaki playhead
  saklanır; release/cancel sonrasında oraya dönülür. MouseMove başına
  repository mutation/undo/autosave yapılmaz, final değişiklik tek işlem
  olarak commit edilir.
- Export artık KineSynthV3 Transformer uyumluluğunu varsayılan hedef veya
  öncelik saymayacaktır. Yeni model için modelden bağımsız, self-describing,
  provenance/mask/unit/shape/dtype/label mapping/error interval/derived
  correctness içeren canonical dataset önceliklidir. Legacy uyumluluk
  gerekirse ikincil ve açıkça işaretli kalabilir.
- Export ile Ayarlar ve Tanılama sabit yoğun yan yana sütunlar yerine
  1120x700, 1366x768 ve 1600x980'de erişilebilir responsive/scroll
  mimarisine geçirilecektir. Tüm sayfalar dolu fixture'larla genel geometri
  denetimine alınacaktır.
- files/Yıldız_Technical_University_Logo.png (RGBA, 398x405) açık
  NavigationRail'de Daralt düğmesinin hemen üstünde, oranı korunmuş ve
  ortalanmış gösterilecek; rail daralınca tamamen gizlenecek ve boşluk
  bırakmayacaktır. Görsel paket kaynağına dahil edilecek, cwd-relative
  development path'e bağlı kalmayacaktır.

### Prompt hazırlama sırasında doğrulanan mevcut durum

- ProjectsPage ve IdentityService'te proje silme akışı yoktur.
- Hareket dialogu, MovementSample, evaluate_sample, Dataset ve export
  explicit stored correctness'e bağlıdır; yalnız GUI düğmesi kaldırmak yeterli
  değildir.
- TimelineWidget resize/move sırasında bounds sinyallerini sürekli gönderiyor;
  preview/restore sinyali veya tek commit transaction'ı yoktur.
- ExportPage hâlâ KineSynthV3 uyumu metni taşır ve sabit iki sütun kullanır.
- SettingsPage iki yoğun bağımsız scroll sütununda yatay taşan kontrol
  grupları kullanır. İzole render'da 1120x700 ve 1366x768 boyutlarında
  yatay scroll, sıkışan alanlar ve görünür viewport dışına kayan alt kartlar
  doğrulandı.
- Logo dosyası mevcuttur fakat bu turda kaynak/paketleme dosyalarına
  eklenmedi.

### Bu prompt hazırlama turunda gerçekten çalıştırılanlar

- conda run -n KineSynth python -m pytest tests/test_gui_painting.py
  tests/test_gui.py tests/test_export_gui.py tests/test_review_flow.py -q
  → **132 test geçti**.
- Aynı dört dosya --collect-only ile doğrulandı → **132 test toplandı**.
- Uygulama normal launcher ile açıldı; gerçek kullanıcı hesabıyla giriş
  yapılmadı ve gerçek veri değiştirilmedi. Export, Settings ve Projects
  sayfaları geçici identity DB + geçici proje ile offscreen olarak 1120x700
  ve 1366x768'de render edildi.
- Full tests/ turu ve self-test bu prompt-only turda yeniden
  çalıştırılmadı. Proje silme, yeni correctness, timeline preview, responsive
  refactor ve logo **henüz uygulanmadı veya işlevsel olarak doğrulanmadı**.
- Kaynak kod ve gerçek app/schema sürümleri değişmedi: app 0.8.0; project
  1.1.0, session 2.0.0, take 1.1.0, skeleton stream 1.1.0, annotation 2.0.0,
  label 2.0.0, release 2.0.0, feature spec 1.0.0, raw archive 1.0.0,
  identity SQLite schema 1. Bu turda yalnız yeni Claude promptu ve bu MEMORY
  bölümü eklendi.
