---
type: legacy-memory-section
status: archived
title: "5. Gerçekten çalışan özellikler"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "173-221"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](4-4-zed-sdk-ve-donanim-dogrulanmis.md) · [sonraki](6-6-bu-gorevde-alinan-kalici-teknik-kararlar.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md).

## 5. Gerçekten çalışan özellikler

Aşağıdakiler çalıştırılarak doğrulanmıştır (bkz. bölüm 9).

- Paket ZED SDK olmadan import edilebiliyor; `pyzed` hiçbir zaman modül
  seviyesinde import edilmiyor (alt süreçte `sys.modules` kontrolüyle test).
- `--diagnose`, `--list-devices`, `--self-test` CLI komutları.
- Deterministik sentetik backend: aynı seed → byte düzeyinde aynı RGB ve aynı
  eklem dizileri; farklı seed → farklı görüntü. Çok gövde, takip kaybı ve
  düşük güven senaryoları scriptli.
- Gerçek ZED backend: RGB, derinlik, BODY_34 vücut takibi, SVO2 native kayıt,
  cihaz enumerasyonu, temiz kapanış, kopma tespiti.
- Threaded capture: acquisition thread + writer thread; GUI yalnız okuyor.
  Önizleme kaybı ve kayıt kaybı **ayrı** sayılıyor.
- Kayıt: `skeleton.jsonl` (append-safe), `proxy.mp4`, `capture.svo2`,
  `quality.json`, `checksums.json`, atomik `take.json`.
- Yarım kayıt tespiti ve kurtarma; kapanış sırasında güvenli finalize.
- Senkron oynatma (QTimer), hız kontrolü, kare adımlama, döngü aralığı.
- Katmanlı zaman çizelgesi: veri kapsamı, takip güveni, marker'lar,
  tekrarlar; sürükleyerek oluşturma/taşıma/yeniden boyutlandırma, zoom/pan.
- Hareket sample'ı CRUD: oluştur, böl, birleştir, dışla/geri al, sil;
  undo/redo; marker'lardan sınır önerisi; çakışma doğrulaması.
- **İki seviyeli etiketleme**: hareket türü + ikili doğru/yanlış (seviye 1),
  hareketin içinde hata sınıfına bağlı zamansal aralıklar (seviye 2). Tek/çok,
  aynı sınıftan tekrarlı ve çakışan aralıklar; aralık ana hareketin dışına
  çıkamaz; ana sınır daralınca kırpma/kaldırma raporlanır ve geri alınabilir.
- **Etiketleme sırasında hata sınıfı oluşturma**: aranabilir seçici, Enter ile
  oluştur-veya-yeniden-kullan, büyük/küçük harf ve boşluk farkına dayanıklı
  tekrar kontrolü, projeye atomik kalıcı yazım.
- Autosave; öncekini kopyala; tümüne uygula; sonraki eksik kayda geç.
- Dataset paneli: sayımlar, filtreler, dağılımlar, kalite bulguları.
- Sürümlü export: `[T,J,3] float32` + manifest + skeleton spec + label
  mapping + feature spec + fingerprint + validation report + excluded;
  staging → atomik yayın; iptal ve hata durumunda hiçbir şey yayımlanmaz.
- **Seçilebilir iskelet özellikleri**: kalite maskeleri, tracker ham çıktıları,
  alternatif koordinat temsilleri, kemik geometrisi, zaman damgası tabanlı
  kinematik, anatomik açılar, bilateral simetri, mesafe/oran proxy'leri ve
  klasik ML için sabit uzunluklu özet vektörü. Export ekranında aranabilir
  seçim + 5 preset.
- Modern GUI: 8 çalışma alanı, daraltılabilir navigasyon, koyu **ve** açık
  tema, 43 vektör ikon (emoji yok), inline form doğrulama, hata bandı,
  klavye kısayolları, kalabalık yan panellerde kaydırma.
- **Tek görüntü alanı**: RGB / İskelet / RGB+İskelet modları; kalıcı iki panel
  yok. Proxy video yoksa iskelet modu çalışmaya devam eder.
- **İki modlu zaman çizelgesi**: HAREKET ve HATA şeritleri; hata modunda seçili
  hareketin dışı maskelenir, çakışan aralıklar ayrı satırlara yığılır, her
  aralık sınıf adıyla birlikte çizilir (yalnız renge bağımlı değil).
  Bütün sayfalar gerçekten çizdirilerek doğrulandı (ekran görüntüsü alındı).
