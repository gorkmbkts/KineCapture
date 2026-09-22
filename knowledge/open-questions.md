---
type: open-questions
status: current
updated: 2026-09-21
tags:
  - open
---

# Açık sorular ve sonraki işler

## Öncelikli — 21 Eylül kullanıcı GUI revizyonunun kabulü

Kapsam **uygulandı ve ölçüldü**; bekleyen tek şey kullanıcının görsel kabulü.
[Kararlar](decisions/studio-gui-user-revision-2026-09-21.md) ·
[Uygulama ve doğrulama](reports/studio-gui-user-revision-validation-2026-09-21.md) ·
[Prompt](../promts/CLAUDE_STUDIO_GUI_USER_REVISION_PROMPT_2026-09-21.md).

Bu turdan kalan açıklar:

- Gerçek ZED kamerayla hiçbir yakalama maddesi denenmedi; yeşil bağlantı
  düğmesi, sabit önizleme kutusu ve kişi seçme uyarısı sentetik mock backend
  ile doğrulandı.
- İşleme kuyruğunun durum geçişleri gerçek çocuk süreçlerle sürüldü; gerçek
  bir işleme işi ortasında Duraklat/Devam et denenmedi.
- Tüm test paketinin tek koşusu bu turda tamamlanmadı; revizyonla ilgili
  dosyalar gruplar hâlinde koşuldu ve geçti.
- `tests/test_studio_workload.py::test_leaving_the_labelling_screen_stops_playback`
  çalışma ağacında zaten başarısız ve bu turun dışında bırakıldı: fixture proje
  açmadığı için `navigate` reddediliyor, etiketleme sayfası hiç etkinleşmiyor.
  Ürün doğru davranıyor; testin ön koşulu eksik.
  [Ayrıntı](reports/studio-gui-user-revision-validation-2026-09-21.md).

Eski açık işlere otomatik dönüş yok; aşağıdaki kayıtlar tarihsel bağlam ve
ayrı bekleyen işlerdir.

## Önceki öncelik kaydı — güncel görev olarak sürdürülmez

20 Eylül akşamı gerçek kullanımda: etkin veri kökü Claude test dizinine
işaret ediyor; `SVO RECORDING ERROR` var; GUI TEST sürümünde 10,6 sn sonrası
kişi kaybı ve aynı-ID kanıt çatışması saptandı. Sağ yardımcı panel kaybolmuş;
başlangıç/proje/katılımcı kapıları, capture sabit düzeni ve toast kırpılması
yeni görevde ele alınacak. [Kanıt/kararlar](audits/capture-tracking-gui-issues-2026-09-20.md).

GUI kabulü 20 Eylül'de yeniden açıldı: kullanılmayan alan, kaydırmalı yardımcı
panel, eklem seçimi deneyimi ve anatomik preset referansı. Alt hareket/hata
editörü ve kaydırmasız üst panel yeni karar olarak kaydedildi.
[Denetim ve düzeltme görevi](audits/studio-gui-acceptance-audit-2026-09-20.md).

1. Kişi seçilmeden alınmış iki eski kayıt için kare-anchor seçici.
2. **Sporcu seçimi ile işlemede kilitlenen kişi arasında uyuşmazlık kapısı
   yok.** `validate_subject_review` yalnız seçilen kimliğin sürümde bulunup
   bulunmadığına bakıyor (`unknown_athlete_tracker`); kanonik export ise yalnız
   "sporcu seçilmedi" durumunu reddediyor. İşleme A kişisini kilitlemişken
   sporcu olarak B seçilirse dışa aktarılan diziler A'nın koordinatlarıdır,
   manifest ise `athlete_tracker_id = B` yazar ve hiçbir kapı itiraz etmez.
   Kilitlenen kimlik `features.json` içindeki `subject_association` alanında
   zaten yazılı olduğundan kapı uygulanabilir durumdadır. Tek kişilik kayıtta
   ortaya çıkamaz. Durum: `verified` açık (18 Eylül 2026 kod denetimi —
   `processing/subject_review.py:391-407`, `export/canonical.py:246`,
   `processing/jobs.py:534`).
3. Gerçek kayıtla kanonik export paketinin uçtan uca doğrulanması.
4. İki kişinin aynı kadrajda olduğu gerçek subject-lock testi.

## 21 Eylül kayıt/takip/GUI onarımından kalan açıklar

- **Gerçek kamerayla kayıt denenmedi.** Kayıt hedefi uzunluk kontrolü ve
  kurtarılabilir başlangıç sentetik backend ile sınandı. Bu makinede
  `LongPathsEnabled = 0` olduğu ve 279 karakterde çıplak `CreateFileW`/`A`
  çağrılarının WinError 3 verdiği ölçüldü; ZED SDK'nın **kendi** reddi tekrar
  üretilmedi.
- **Kişi kilidinin kurtarma yolu gerçek kayıtta tetiklenmedi.** Yanlış veto
  kaldırıldığı için 1473 karenin tamamı kilitli kaldı; kurtarma yalnız
  sentetik regresyonlarla sınandı.
- İki kişili **gerçek** kadraj hâlâ yok. GUI TEST kaydındaki ikinci beden
  aynadaki yansımadır ve diskalifiye edilmiştir.
- Identity veritabanında yolları artık var olmayan üç proje kaydı duruyor
  (ikisi eski pytest geçici dizinlerinden, biri 20 Eylül'de sızan kökten).
  Kullanıcının veritabanı; temizlenmedi.

## 20 Eylül kabul onarımından kalan açıklar

- **Gerçek SVO ile yeniden işleme** (BODY_18 / BODY_34 / BODY_38)
  çalıştırılmadı. `SvoSource` zaten `profile.body_format` ile SDK'yı yeniden
  çalıştırıyor ve kod okunarak doğrulandı; donanım/SVO olmadığı için
  **çalıştırılmadı**. Sentetik yolla üç biçim de üretilip etiketlendi.
- **Gerçek eklem verisiyle** etiketleme ölçülmedi; fixture sentetik.
- `rehab24_6_mocap` sentetik olarak üretilemez (export hedefi); duruş tablosu
  yok ve istenirse açık hata veriyor.

## Studio GUI turundan kalan ölçüm açıkları

Bunlar **alınamamış ölçümler**; yukarıdaki GUI kabul açıklarından ayrıdır.
19 Eylül kapsam kapanışı 20 Eylül denetimiyle yeniden açıldı. Önceki ölçümlerin ayrıntısı
[doğrulama raporunda](reports/studio-gui-refinement-validation.md).

- **GPU kullanımı ölçülmedi.** Tahminle doldurulmadı.
- **Canlı kayıt kaybı önce/sonra karşılaştırması yapılmadı**; donanım
  gerektiriyor.
- **Gerçek eklem verisiyle 3B çizim ölçülmedi.** Diskteki tek tam sürüm
  `needs_subject_selection` ile işlenmiş, bütün eklemleri NaN. Raporlanan
  sayılar sentetik koordinatlarla alındı ve öyle etiketlendi.
- **Hareketli kamerayla çekilmiş SVO yok**; zemin bloğunun `camera_moved`
  dönüşüm yolu doğrulanmadı.
- **Fare ile kamera sürükleme el ile denenmedi**; kamera geometrisi presetler
  ve birim testlerle doğrulandı.
- **Sürücü MSAA vermiyor** (`setSamples(4)` → `samples: 0`). Kenar yumuşatma
  `fwidth` tabanlı analitik yolla yapıldı; bu bir geçici çözüm değil, ölçülen
  kısıt karşısında seçilen yol.

## Bilinen teknik riskler

- `test_processing_pipeline.py` duraklat/sürdür yaklaşık üç koşudan birinde
  takılabiliyor.
- `test_identity.py` eşzamanlı katılımcı kodu testi tam suite yükünde Windows
  dosya kilidiyle düşebiliyor; izole koşuda geçiyor.
- Test ve ölçüm ortamı sınırları: [Test ve ölçüm ortamı](protocols/test-and-measurement.md).
- SDK ilk model optimizasyonu dakikalar sürebilir.
- Proxy video Windows uzun yolunda açılamayabilir.
- `dataset_root` eski yolu gösterebilir.
- Proje kilidi yok.
- PyOpenGL numpy 2.x ile uyumsuz; 3B yalnız Qt GL sınıflarıyla yürütülür.
- **Offscreen'de alınan yerleşim ölçümü kanıt değildir.** Font veritabanı boş
  olduğu için her glif aynı genişlikte; bu turda iki gerçek hata yalnız
  `QT_QPA_PLATFORM=windows` altında ortaya çıktı (ayrılmış genişliğin yanlış
  fontta ölçülmesi ve Yakalama ekranının %150'de sığmaması).

Bir madde kapanınca doğrulama kaynağıyla ilgili nota taşınır ve bu liste
kısaltılır.

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [10. Bilinen sorunlar, riskler ve sınırlar](archive/memory/10-10-bilinen-sorunlar-riskler-ve-sinirlar.md)
- [11. Henüz uygulanmayanlar](archive/memory/11-11-henuz-uygulanmayanlar.md)
- [12. Sonraki önerilen adım](archive/memory/12-12-sonraki-onerilen-adim.md)

Tam liste: [Tarihsel MEMORY arşivi](archive/memory/index.md).
