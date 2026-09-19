---
type: legacy-memory-section
status: archived
title: "6AD. Studio F9–F15 — 3B, sporcu, dışa aktarım, cila (2026-09-14)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3401-3462"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6ac-6ac-studio-f8-etiketleme-kanonik-sidecar-1-1-0-2026-09-14.md) · [sonraki](6af-6af-17-eylul-gercek-zed-kaydindan-etiketlemeye-giden-zincir.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md).

## 6AD. Studio F9–F15 — 3B, sporcu, dışa aktarım, cila (2026-09-14)

F8'in üstüne kalan yedi faz. Ayrıntılı sonuçlar
`FAZ_PLANI_PYSIDE6_STUDIO.md` bölüm 7'de; burada yalnız kalıcı olanlar.

### Kalıcı teknik kararlar

1. **3B görünüm yalnız Qt'nin GL sınıflarını kullanır.** PyOpenGL ortamda
   kurulu ama hızlandırıcısı numpy 2.x ile ikili uyumsuz
   (`numpy.dtype size changed, Expected 96 ... got 88`) ve ilk dizide patlıyor.
   `QOpenGLBuffer` + `QOpenGLShaderProgram` + `context().functions()` ile
   yazıldı; köşe verisi VBO'ya bir kez ayrılıp içine yazılıyor.
2. **Yukarı ekseni kayıttan okunur** (`processing_camera.coordinate_system`).
   Varsayılsaydı bir z-up kaydı yan yatardı.
3. **"Tamamlandı" = terfi etmiş.** `process_take` önce `state: complete`
   yazıp sonra klasörü `.run_x.partial` → `run_x` olarak adlandırıyor; arada
   okuyan herkes açılamayan bir sürüm görüyordu. `ProcessingRunSummary`
   artık terfiyi de şart koşuyor ve gerçek klasör adını taşıyor.
4. **Kişi seçilmeden işlenmiş sürüm etiketleme ekranından kurtarılamaz.**
   Diziler işleme anında yazıldı ve yalnız seçili bedenin eklemlerini taşıyor;
   sonradan sporcu seçmek onları doldurmaz. Ekran "sporcu işaretlenmiş hâlde
   yeniden işleyin" diyor ve sürümü hazır saymıyor.
5. **Dışa aktarımda dört kapı** (`export/canonical.py`): sürüm tamamlanmış +
   checksum tutuyor · sporcu seçilmiş + belirsiz aralıklar yanıtlanmış ·
   etiket belgesi sürümüne karşı doğrulanıyor · her hareket hazır. Reddedilen
   sürüm **pakete nedeniyle yazılıyor**.
6. **Diziler dilimlenir, yeniden hesaplanmaz**; manifest hangisi olduğunu
   söyler. Hata aralıkları örneğe göreli ve iki ucu dahil.
7. **Otomatik kayıt**: son değişiklikten 4 sn sonra. Başarısız yazma işi
   kaybetmez — kayıt kirli kalır ve yeniden denenir.
8. **Yardımcı pencerelerin içeriği Qt'siz toplanır** (`services/inspectors.py`),
   böylece Qt açmadan test edilebiliyor. Log penceresi uygulamanın kayıt
   seviyesini **değiştirmiyor**; hangi seviyede olduğunu yazıyor.

### Ölçümler (60 dk / 60 FPS / BODY_38 = 216000 kare, `windows` platformu)

Boşta kare 0,72 ms (bütçe 8) · tarama 0,84 ms (bütçe 50) · 600 karelik 3B
pencere 0,17 ms · 3B çizim 2,1–2,3 ms · zirve RSS **144 MB** (bütçe 1,5 GB).
Zaman çizelgesi: 100 aralıkla 5,6 ms, 600 aralıkla 13,9 ms medyan; oynatma
çizgisi hareketi 0,11 ms. (F1 tabanı 292–323 ms.)

Ekranların en küçük boyutu: Etiketleme 822×500, Yakalama 802×406, diğerleri
daha küçük. 1366×768'de %100/%125/%150 hepsi sığıyor; %200 o panelde üç ekranı
taşırıyor, yüksek çözünürlüklü ekranda (4K/%200 = 1920×1080 mantıksal) hepsi
sığıyor.

### Test ortamı

`pytest tests/` tek süreçte tamamlanmıyor; dosya dosya çalıştırılıyor.
Yerleşim/genişlik ölçümleri `offscreen`'de anlamsız — o testler orada
atlanıyor ve `QT_QPA_PLATFORM=windows` ile ayrıca koşuluyor.

### Hâlâ açık (donanım gerektiriyor)

- Gerçek ZED ile tek kişilik tam tur: 60 FPS sürdürülebilirliği, canlı
  iskeletin 2B/3B görünümde doğruluğu, gerçek derinlik.
- **İki kişinin gerçekten karıştığı bir kayıt**: mock backend iki bedeni temiz
  izliyor, tracker hiç kararsız kalmıyor, bu yüzden belirsiz aralık akışı
  yalnız sentetik akışlarla test edilebildi.
- Yakalama ekranının tıkla-seç kişi akışı: `select_subject` viewmodel'de var
  ama uçtan uca betiklerde çalışmadı; çapa dosyası elle yazıldı.
