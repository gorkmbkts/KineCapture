---
type: decision
status: decision
applied: 2026-09-21
updated: 2026-09-22
tags:
  - studio
  - gui
  - acceptance
---

# 21 Eylül — kullanıcı GUI revizyonu

## Durum ve kanıt

- `decision`: Kullanıcı, son Claude/Codex düzenlemeleri sonrasında kalan GUI sorunları için yeni Claude Code promptu hazırlanmasını ve Obsidian'a işlenmesini istedi.
- `observed`: Kullanıcının sağladığı 13 görselde önizleme geometrisi, bildirim kaplamaları, panel boşluk/hiza sorunları ve editör alanlarındaki sıkışma görülüyor. Görseller farklı durumların statik kanıtıdır; kök neden veya etkileşim testi değildir.
- `verified`: **Prompt 21 Eylül'de uygulandı.** İş kuyruğu eylemlerinin
  çalışmama nedeni bulundu ve düzeltildi: kuyruk 400 ms'de bir yeniden
  okunuyor, model sıfırlaması tablonun seçimini siliyor ve seçim olmadan dört
  eylem de pasifleşiyordu. Editör ilk açılışta artık hareket içeriğini
  gösteriyor. Uygulama gerçek masaüstünde maksimize açıldı, ekran görüntüleri
  incelendi ve durum geçişleri gerçek çocuk süreçlerle sürüldü.
  [Uygulama ve doğrulama raporu](../reports/studio-gui-user-revision-validation-2026-09-21.md).
- `open`: **Kullanıcı görsel kabulü alınmadı.** Ölçüm ve ekran görüntüsü
  kabul yerine geçmez.
- `open`: Gerçek ZED kamerayla hiçbir madde denenmedi; yakalama tarafı sentetik
  mock backend ile doğrulandı.

## 22 Eylül ek kullanıcı kararları

9. Yakalamada önizlemenin sağındaki container önizleme ile **aynı yükseklikte
   ve hizalı** olacak; kısa kalmayacak. Eski boyutuna döndükten sonra içerik
   daha ferah yayılacak.
10. Etiketleme bandında hareket ve hata aralığının **başlangıç/bitiş sayı
    kutuları, sınıf eklemek için olan metin kutusunun altında** ve onunla üst
    alt hizalı olacak.
11. Projeler'de katılımcı seçmeden Yakalama'ya geçilmek istenirse, önce
    katılımcı seçilmesi ya da oluşturulması gerektiği **popup bildirimle**
    söylenecek.
12. Yakalama sırasında GUI'nin üstündeki **ikinci kaydı durdur düğmesi ve süre
    metni kaldırılacak**; aynı içerik sekmenin altında zaten var. Kullanıcı
    kararı: şeridin tamamı kalksın.
13. İş kuyruğu tablosu container'a sığacak; en sağdaki hücrenin taşan metni
    **"…" ile kısaltılacak**. Kuyruk düğmelerinden **Duraklat ve Devam et
    kaldırılacak**; **Yeniden dene** ve (kullanıcı kararı) **İptal** kalacak,
    Yeniden dene'nin çalıştığı doğrulanacak.
14. İşleme ekranındaki **"Ayrıntılar" katlanır profil bloğu kaldırılacak**:
    açıldığında içerik sayfadan taşıyor ve orada görülmesi gerekmiyor.
15. **Veri Seti sayfasına amaç kazandırılacak.** Soldaki kayıt listesi
    daraltılacak; "Yenile" ve "Etiketlemede aç" listenin üstündeki arama
    satırına taşınacak; açılan sağ alana veri setinin kendi istatistikleri
    konacak. Kullanıcı seçimi: **hareket sınıfı dağılımı, hata sınıfı
    dağılımı, hazırlık durumu ve katılımcı başına kapsam**.
16. Etiketleme bandının **"Hata aralığı ekle" düğmesi kaldırılacak**; hata
    zaten zaman çizelgesinin kendi aracıyla çiziliyor. Bandın alt satırındaki
    eylemler, yine container'ın **sağına yaslı**, soldan sağa:
    hareket kipi **çöp kutusu · Diğer sınıflar · Sınıfsızlara uygula**; hata
    kipi **çöp kutusu · Diğer sınıflar · Eklemleri düzenle · Harekete dön ·
    Not**. Kullanıcıya sorulup yanıtlanan iki nokta: hata kipinde Diğer
    sınıflar **çöpün hemen sağında**; Diğer sınıflar **her zaman görünür**
    (yalnız sınıf taşınca değil).
17. Etiketleme 3B görünümünde iskelet zemin ızgarasının **ortasında** duracak,
    kenarında değil.

## Kalıcı kullanıcı kararları

1. Tek hedef **maksimize pencereli** GUI ve kullanıcının mevcut Windows ölçeği. Küçültme/büyütme kontrolleri kaldırılacak; özel kenarlıksız fullscreen istenmiyor. Farklı DPI/pencere boyutu test matrisi istenmiyor; gerçek hedef görüntü ve işlev testleri isteniyor.
2. Açıkça kaldırılması istenmeyen içerik ve container'lar korunacak. Eski tamamlanmamış işlere otomatik dönülmeyecek; bu revizyonun kapsamı yürütülecek.
3. Yakalama önizlemesi kamera öncesi/sonrası aynı dış geometriyi koruyacak. Bağlantı düğmesi kayıt alt satırında Kayda başla'nın hemen arkasına dönecek; bağlıyken yeşil olacak.
4. Yakalamadaki değişken sağ panel ve RGB üstü kamera/kadraj bildirimleri kaldırılıp sistem/tanı bilgileri Araçlar'a taşınacak. Kişi seçmeden kayıt denemesi popup'ı kalacak; seçili kişinin çerçevesindeki metin kalkacak, çerçeve kalacak. Sabit alt satır metrikleri korunacak.
5. İşleme ana container'ları eşit yükseklikte/hizada olacak. Kuyruk eylemleri çalışır hâle getirilecek; gerçekten desteklenemeyen düğme gerekçesiyle kaldırılabilir.
6. Etiketleme sağ panelinde dar ikon şeridi, dengeli preset/sporcu içerikleri; pusula kaldırılacak, diğer işlevler korunacak.
7. **Yalnız Etiket özeti sekmesinde çubuksuz kaydırmaya izin var.** Diğer panel içeriklerinde kaydırma yasağı sürüyor; satırlar çoğaldıkça ezilmeyecek.
8. Hareket/hata editörü ilk açılışta hareket içeriğini gösterecek. Dört dar sütun görünümü yerine kısa/geniş banda uygun akış; solda yeni sınıf alanı, kapasiteyi aşınca Diğer sınıflar, en son kullanılan sınıf ilk sırada. Başlangıç/bitiş sayıları kırpılmayacak.
   `superseded` (yalnız "kapasiteyi aşınca Diğer sınıflar" bakımından): 22 Eylül kararı 16 ile Diğer sınıflar sınıf satırından alt satıra indi ve her zaman görünür.

**Tasarım önerisi, kullanıcı kararı değil:** Codex; sınıf oluşturma ve hızlı sınıf seçimine öncelik veren, aralık ve bağlamsal eylemleri aynı banda yerleştiren bir veya iki yatay hat önerdi. Uygulama tekniği Claude'a bırakıldı; ayrıntılı zorunlu sonuçlar promptta.

## Önceki kararlarla ilişki

`superseded` (yalnız çelişen karar bakımından): [20 Eylül GUI onarımı](studio-gui-repair-2026-09-20.md) ve [kayıt/takip/GUI kararları](../audits/capture-tracking-gui-issues-2026-09-20.md) içindeki tüm yardımcı panelleri kaydırmasız tutma ve bağlantı düğmesini üstte tutma tercihleri, sırasıyla Etiket özeti istisnası ve alt satır kararıyla değişti. Eski doğrulama sonuçları tarihsel kanıt olarak kalır; yeni görünümün kabulü yerine geçmez.

[Codex devir notunda](../plans/capture-tracking-gui-repair-handoff-codex.md) kalan eski test/GUI işleri kendiliğinden sürdürülmeyecek. Yeni görev gerekli işlev testlerini kapsar; önceki turdaki test durdurma talebi yeni promptu “test yapma” talebine dönüştürmez.

## Kaynak ve gezinme

- [Uygulama ve doğrulama raporu](../reports/studio-gui-user-revision-validation-2026-09-21.md)
- [Kaynak konumları ve kanıt sınırları](../sources/gui-user-feedback-2026-09-21.md)
- [Claude Code görev promptu](../../promts/CLAUDE_STUDIO_GUI_USER_REVISION_PROMPT_2026-09-21.md)
- [Açık sorular](../open-questions.md)
- [Wiki ana sayfası](../index.md) · [Hafıza indeksi](../../MEMORY_INDEX.md)
