# KineCapture — kısa hafıza indeksi

Bu dosya her görevde okunacak tek başlangıç kaynağıdır. Ayrıntı için yalnız
ilgili bağlantıyı aç. Tarihsel arşivi topluca yükleme.

## Güncel durum

- **23 Eylül: yayın kapısı ve temiz Windows kurucusu planlandı, uygulanmadı.**
  Önce export doğruluğu + ölçek testleri (≥30k segment, ≥30k run, ≥100 sınıf),
  sonra conda-pack + preflight (ZED SDK birebir 5.4.1, NVIDIA sürücü ≥ min)
  kurucu; sıfır veri, sistem sahibi `gorkembektas` yalnız scrypt özetiyle.
  [Karar](knowledge/decisions/windows-installer-release-2026-09-23.md) ·
  [Prompt](promts/CLAUDE_RELEASE_GATE_AND_WINDOWS_INSTALLER_PROMPT_2026-09-23.md).

- **21 Eylül son kullanıcı GUI revizyonu uygulandı; kullanıcı kabulü açık.**
  [Kararlar](knowledge/decisions/studio-gui-user-revision-2026-09-21.md) ·
  [Uygulama ve doğrulama](knowledge/reports/studio-gui-user-revision-validation-2026-09-21.md) ·
  [Prompt](promts/CLAUDE_STUDIO_GUI_USER_REVISION_PROMPT_2026-09-21.md).
  Tek maksimize pencere (küçültme/büyütme yok); yakalamada önizleme kutusu
  kameradan bağımsız sabit; resmin ve sağ panelin üzerindeki kamera/kadraj
  bildirimleri **Araçlar › Yakalama Durumu**'na taşındı; bağlantı düğmesi kayıt
  satırında ve bağlıyken yeşil; işleme iki container'ı aynı hizada; etiketleme
  editörü iki yatay hat ve ilk açılışta hareket kipi; yalnız Etiket özeti
  sekmesi çubuksuz kaydırıyor. Ölçüm 1920×1080, %100 ölçek. Görsel kabul açık.
  **22 Eylül düzeltmeleri:** yakalama sağ container'ı önizlemeyle aynı kutu
  (aynı üst/alt/yükseklik), kazanılan yer blokların arasına dağıtılıyor;
  etiketleme bandı ızgara oldu ve Başlangıç/Bitiş kutuları yeni sınıf metin
  kutusunun tam altında, aynı sol ve sağ kenarda; kapalı gezinme adımı artık
  **devre dışı değil sönük** (devre dışı düğme click göndermediği için uyarı
  hiç çıkmıyordu); üst şeritteki kayıt göstergesi/süre/durdur kaldırıldı; iş
  kuyruğu tablosu container'a sığıyor ve son sütun "…" ile kısalıyor, kuyrukta
  yalnız **İptal + Yeniden dene** kaldı, "Ayrıntılar" katlanır profil bloğu
  kaldırıldı; **Veri Seti** sağ yarısı dört istatistik bloğu oldu (hareket
  sınıfı, hata sınıfı, hazırlık durumu, katılımcı başına kapsam) ve liste
  daraltılıp eylemleri kendi üstüne alındı.
  **22 Eylül üçüncü tur:** bantta "Hata aralığı ekle" kaldırıldı; eylemler alt
  satırda sağa yaslı — hareket: çöp · Diğer sınıflar · Sınıfsızlara uygula;
  hata: çöp · Diğer sınıflar · Eklemleri düzenle · Harekete dön · Not; Diğer
  sınıflar her zaman görünür. 3B ızgara **ölçülmüş zeminde kameraya
  merkezleniyordu** (sporcu 3,03 m, ızgara ±3 m); artık ayak pivotunda
  (0,00 m, gerçek sürümde ölçüldü).

- **İş kuyruğu düğmeleri çalışıyor; sorun servis değil seçimdi.**
  `RowTableModel.set_rows` modeli sıfırlar, sıfırlama tablonun seçimini siler ve
  kuyruk 400 ms'de bir yeniden okunur; seçim olmadan Duraklat/Devam et/İptal/
  Yeniden dene pasifleşiyordu. Satırlar artık kimliğe göre yeniden seçiliyor.
  Durum geçişleri gerçek çocuk süreçlerle doğrulandı.

- Studio F0–F15 tamamlandı; kayıt → işleme → etiketleme zinciri gerçek ZED ile
  18 Eylül 2026'da doğrulandı.
- Studio GUI F1–F17 uygulandı, kullanıcı **kabul etmedi**; 20 Eylül onarımı
  P1–P7 ile yapıldı. Alan kullanımı, panel kaydırması, eklem seçimi ve preset
  referansı düzeltildi ve ölçüldü. Kapsam kapanışı kabul ölçütlerine bağlıdır,
  test sayısına değil.
- 20 Eylül gerçek kullanım bulguları **21 Eylül'de onarıldı** (C-01…C-07):
  sızan veri kökü, 279 karakterlik kayıt hedefi, 10,6 sn sonrası kişi kaybı,
  kaybolan sağ panel, proje/katılımcı kapıları, zıplayan yakalama düzeni,
  kırpılan bildirim eylemleri.
  [Kanıt ve kararlar](knowledge/audits/capture-tracking-gui-issues-2026-09-20.md) ·
  [Faz planı](knowledge/plans/capture-tracking-gui-repair-implementation.md) ·
  [Doğrulama](knowledge/reports/capture-tracking-gui-repair-validation.md) ·
  [Codex'e devir](knowledge/plans/capture-tracking-gui-repair-handoff-codex.md).
  Kapsam kapanışı kullanıcı kabulüne bağlıdır.
- **Her açılış Projeler.** Projeler dışındaki her ekran açık bir **proje**,
  Yakalama ayrıca seçili bir **katılımcı** ister; kural `navigate` içinde, yani
  kısayol, bildirim eylemi ve kayıt komutu için de geçerli. Otomatik katılımcı
  oluşturma kaldırıldı.
- **Kişi kilidi artık kurtarılabilir.** Uzuv oranı kimliği söyler; eklem
  bulutunun boyu duruştur ve tek başına veto edemez. `AMBIGUOUS` terminal
  değil: kilit yalnız **kendi** tracker kimliğine, 30 kare kesintisiz uyumla
  döner. Gerçek GUI TEST kaydı yeniden işlendiğinde kişi kapsaması
  **622/1473 → 1473/1473**.
- **Ham kayıt hedefi ön kontrolden geçiyor.** ZED SDK çıplak yol açar ve bu
  makinede `LongPathsEnabled = 0`; 259 karakteri aşan hedef reddedilir, hata
  gerçek nedeni söyler, önizleme durmaz.
- **Hedef yalnız maksimize pencereli kullanım** (21 Eylül kullanıcı kararı);
  kenarlıksız fullscreen değil. Küçültme/büyütme kontrolleri **kaldırıldı**,
  kapatma korundu; pencereyi normale döndüren her yol yeniden maksimize ile
  yanıtlanıyor. Farklı DPI/pencere boyutu test matrisi istenmiyor.
- İskelet biçimleri: `BODY_18` · `BODY_34` · `BODY_38` üretilebilir ve
  etiketlenebilir; roller kaydın kendi iskeletine karşı denetlenir
  (`roles_not_in_skeleton`). `rehab24_6_mocap` yalnız export hedefidir.
- Uygulama `0.11.0`; processing **`1.3.0`** (`subject_coverage` bloğu; 1.2.0
  sürümleri `features.json`'dan okunur); canonical
  annotation **`1.2.0`** (`roles_origin`/`roles_revision`); canonical release
  **`1.1.0`**; floor `1.0.0`; tokens **`1.3.0`**; subject association `1.2.0`;
  identity şema `1`.
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
- Studio GUI 21 Eylül kullanıcı revizyonu:
  [Kararlar](knowledge/decisions/studio-gui-user-revision-2026-09-21.md) ·
  [Doğrulama](knowledge/reports/studio-gui-user-revision-validation-2026-09-21.md) ·
  [Kaynak görseller](knowledge/sources/gui-user-feedback-2026-09-21.md)
- Studio GUI: 19 Eylül tasarımı + 20 Eylül kabul onarımı. Onarımın kanıtı
  ayrı plan ve raporda:
  [Kabul denetimi](knowledge/audits/studio-gui-acceptance-audit-2026-09-20.md) ·
  [Onarım kararı](knowledge/decisions/studio-gui-repair-2026-09-20.md) ·
  [Onarım planı](knowledge/plans/studio-gui-acceptance-repair-implementation.md) ·
  [Onarım doğrulaması](knowledge/reports/studio-gui-acceptance-repair-validation.md)
- Studio GUI tasarımı ve önceki uygulama kayıtları (tam kabul iddiası superseded):
  [Tasarım](knowledge/decisions/studio-gui-refinement-2026-09-19.md) ·
  [Fikir haritası](knowledge/decisions/studio-gui-design-map-2026-09-19.md) ·
  [Faz planı](knowledge/plans/studio-gui-refinement-implementation.md) ·
  [Doğrulama raporu](knowledge/reports/studio-gui-refinement-validation.md) ·
  [Claude görevi](promts/CLAUDE_STUDIO_GUI_FINAL_REFINEMENT_PROMPT_2026-09-19.md)
- Kayıt/takip/GUI onarımı (21 Eylül):
  [Claude promptu](promts/CLAUDE_CAPTURE_TRACKING_GUI_REPAIR_PROMPT_2026-09-20.md) ·
  [Salt okunur bulgular ve kararlar](knowledge/audits/capture-tracking-gui-issues-2026-09-20.md) ·
  [Faz planı](knowledge/plans/capture-tracking-gui-repair-implementation.md) ·
  [Doğrulama](knowledge/reports/capture-tracking-gui-repair-validation.md)
- Önceki GUI düzeltmesi:
  [Denetim ve nedenler](knowledge/audits/studio-gui-acceptance-audit-2026-09-20.md) ·
  [Yeni karar/fikir haritası](knowledge/decisions/studio-gui-repair-2026-09-20.md) ·
  [Claude düzeltme görevi](promts/CLAUDE_STUDIO_GUI_ACCEPTANCE_REPAIR_PROMPT_2026-09-20.md)
- Yayın kapısı ve Windows kurucusu:
  [Karar](knowledge/decisions/windows-installer-release-2026-09-23.md) ·
  [Prompt](promts/CLAUDE_RELEASE_GATE_AND_WINDOWS_INSTALLER_PROMPT_2026-09-23.md)
- Commit geçmişi:
  [Git kilometre taşları](knowledge/milestones/git-history.md)
- Studio F0–F15 faz özeti:
  [Studio fazları](knowledge/milestones/studio-f0-f15.md)
- Eski belgeler ve konuşmalar:
  [Kaynak sicili](knowledge/sources/source-registry.md)

## Bilinen açıklar

- **Gerçek kamerayla kayıt denenmedi** (kamera bağlı değil): uzun yol reddi ve
  kurtarılabilir başlangıç sentetik backend ile sınandı, SDK'nın kendi
  reddiyle değil. `MAX_PATH` sınırı Win32 çağrılarıyla ölçüldü.
- Kişi kilidinin **kurtarma yolu** gerçek kayıtta tetiklenmedi; yanlış veto
  kaldırıldığı için ihtiyaç kalmadı. Yalnız sentetik regresyonlarla sınandı.
- Gerçek iki kişili kadraj üretilemedi; subject-lock çok kişili davranışı
  yalnız sentetik test edildi.
- Kişi seçilmeden alınan iki eski kayıt için kare-anchor seçici yok.
- Sporcu seçimi ile işlemede kilitlenen kişi arasında uyuşmazlık kapısı yok
  (kodda doğrulandı, 18 Eylül 2026).
- Kanonik export paketi gerçek kayıtla uçtan uca doğrulanmadı.
- GPU kullanımı ve canlı kayıt kaybı önce/sonra karşılaştırması ölçülmedi;
  3B çizim ölçümü gerçek eklem verisiyle değil sentetik koordinatlarla alındı
  (19 Eylül koşusundaki sürüm `needs_subject_selection` idi; 20 Eylül gerçek
  kaydında 622/1473 kare kişi verisi bulundu, performans ölçümü yapılmadı).
- Sürücü MSAA vermiyor (`setSamples(4)` → `samples: 0`); kenar yumuşatma
  `fwidth` tabanlı analitik yolla yapılıyor.
- **`QOpenGLWidget` üzerine `QPainter` ile yazılan metin görünmez**; ne
  `paintEvent`'te ne `paintGL` sonunda. 3B görünümdeki notlar çocuk widget
  olarak çiziliyor. Ölçülerek bulundu (0/99 → 85/99 piksel).
- Gerçek SVO ile yeniden işleme (BODY_18/34/38) **çalıştırılmadı**; kod
  okundu, donanım yok.
- `test_processing_pipeline.py` ve `test_identity.py` eşzamanlılık testi
  aralıklı takılabiliyor; ayrıntı test ve ölçüm notunda.
- SDK ilk model optimizasyonu uzun sürebilir; proxy video Windows uzun yolda
  açılamayabilir; `dataset_root` eski yolu gösterebilir; proje kilidi yok.

## Sonraki önerilen iş

**Sonraki iş: 21 Eylül revizyonunun kullanıcı görsel kabulünü almak.** Kapsam
uygulandı ve ölçüldü; kabul alınmadan kapsam kapatılmaz. Kabul gelirse açık
kalan maddeler [doğrulama raporunun](knowledge/reports/studio-gui-user-revision-validation-2026-09-21.md)
son bölümündedir. Aşağıdaki eski devir/test açıkları kendiliğinden sürdürülmez.

Önceki durum kaydı: Codex devir onarımını
teslim etti. Kullanıcı son düzenlemelerden sonra tekrar test istemedi;
koşu **47/95** dosyada durduruldu (**45 yeşil / 2 başarısız**, tamamlanan
dosyalar 784,7 sn). Son `%150` etiketleme paneli/band düzenlemesi
**doğrulanmadı**; görsel kabul açık. Gerçek SVO tekrarında kişi kilidi
**1473/1473**. Ayrıntı ve eski rapordaki binme iddiasının düzeltmesi
[teslim belgesinde](knowledge/plans/capture-tracking-gui-repair-handoff-codex.md).

Gerçek kamera bağlanınca: uzun yollu bir projede kaydın gerçekten reddedildiğini
ve kısa yolda başladığını gör; başarısız başlangıçtan sonra önizlemenin sürdüğünü
ve tekrar denemenin çalıştığını canlı doğrula. Görsel ve etkileşim kabulü
sağlanmadan kapsamı kapatma. GUI dışında eski kayıtlar için
kare-anchor seçici, gerçek kanonik export, iki kişili kadraj ve sporcu/işleme
kimliği uyuşmazlık kapısı açık. GPU, canlı kayıt kaybı ve gerçek eklemle çizim
ölçümleri de ayrıca açık; tasarım onayı bunların kanıtı değildir.

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
