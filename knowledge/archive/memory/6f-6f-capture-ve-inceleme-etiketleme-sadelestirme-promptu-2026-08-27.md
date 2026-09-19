---
type: legacy-memory-section
status: archived
title: "6F. Capture ve İnceleme/Etiketleme sadeleştirme promptu (2026-08-27)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "955-1032"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6e-06-surumler-ve-dogrulama.md) · [sonraki](6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md), [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6F. Capture ve İnceleme/Etiketleme sadeleştirme promptu (2026-08-27)

> **Tarihsel.** Bu bölüm görev öncesi durumu ve prompt hazırlığını anlatır.
> Uygulanmış sonuç için **bölüm 6G**'ye bakın; buradaki "bugün şöyle"
> ifadeleri artık geçerli değildir.

**Durum: yalnız uygulama promptu hazırlandı; bu bölümdeki GUI değişiklikleri
henüz uygulanmadı.** Claude'un uygulaması için
`CLAUDE_CAPTURE_REVIEW_LABELING_UI_PROMPT.md` repository köküne eklendi.

### Kullanıcının yeni ürün kararları

1. Capture ekranındaki Ön kontrol, Kayıt Planı, Kayıt bilgisi, Kaydedilecek
   kişi ve Ham RGB-D arşivi kartları kalıcı sağ sütunda yer kaplamayacak;
   görünür bir düğmeyle açılan ayrı bilgi penceresinde erişilecek. RGB/derinlik
   ile 3B iskelet görüntüleri ana yatay alanın çoğunu kullanacak. Kayıt kaybı,
   disk, bağlantı ve kişi belirsizliği gibi kritik durumların kompakt uyarıları
   ana ekranda kalacak.
2. İnceleme ekranında yalnız kayıt sırasında seçilen/ilişkilendirilen kişinin
   iskeleti gösterilecek. Subject lock bulunan kayıtta otoritatif kaynak
   `SkeletonFrame.subject_body()` olacak; kişi o karede yoksa başka gövdeye
   fallback yapılmayacak. Legacy kayıtta kimlik uydurulmayacak.
3. RGB + İskelet kayması sabit görsel ofsetle değil; aynı RGB/skeleton karesi,
   tracker 2B noktaları, gerçek kamera calibration'ı, görüntü çözünürlüğü ve
   letterbox dönüşümü doğrulanarak çözülecek. Güvenilir projeksiyon verisi yoksa
   yaklaşık bindirme göstermek yerine dürüstçe kullanılamaz denecek.
4. İnceleme/Etiketleme ekranında yalnız iki yazılabilir zamansal katman olacak:
   **Hareket** ve seçili hareketin içindeki **Hata**. `Hareket ekle` / `Hata
   ekle` timeline çizimini hazırlar; mevcut aralığa çift tıklama, sınıf seçme
   ve yeni sınıf oluşturmayı sağlayan küçük bir pencere açar. Hareket
   sözlüğüne ekleme de hata sözlüğü gibi etiketleme anında mümkün olacak ve
   proje `label_schema.json` dosyasına atomik kaydolacak.
5. İnceleme ekranındaki Aktivite modu/şeridi/kartı/F3 akışı emekliye ayrılacak;
   arka plan/geçiş/hedef egzersiz/diğer hareket authoring'i yapılmayacak. Bu
   karar 6D'deki sürekli aktivite GUI kararını ürün akışı açısından geçersiz
   kılar. Buna rağmen eski `activity_intervals`, eski release'ler ve ham kayıt
   silinmeyecek veya otomatik olarak başka etikete dönüştürülmeyecek; geriye
   dönük okuma/kayıpsız koruma sürdürülecek.

### Prompt hazırlanırken gerçek kodda doğrulananlar

- `CapturePage` iki görüntü kartını ayrı bir yatay splitter'da tutuyor; ana
  splitter kalıcı sağ panel için `[900, 460]` başlangıç boyutu ve `3:2` stretch
  kullanıyor. Yan panelin minimum genişliği 400 px.
- `ReviewPage` görüntü/yan panel için `[820, 540]` ve `3:2` splitter kullanıyor.
  `Gövde` seçicisi olsa da `_redraw()` bütün `frame.bodies` listesini
  `SceneView`'a geçiriyor; seçici yalnız `active_id` değerini değiştiriyor.
  Dolayısıyla seçilmeyen iskeletler gerçekten çiziliyor.
- `SkeletonFrame.subject_body()` otoritatif subject tracker kimliğini buluyor
  ve başka gövdeye fallback yapmıyor; mevcut Review çizimi bu metodu
  kullanmıyor.
- `VideoView` kayıtlı `joint_positions_2d` varsa gerçek görüntü pikselini
  kullanıyor; alan yoksa `_focal_ratio = 0.75` tahminine düşüyor.
  `LoadedTake.video_position_for()` pozisyonu özdeş varsayıp kısa proxy'de son
  kareye clamp ediyor. Prompt her iki dürüstlük/senkronizasyon riskini test
  edilerek kaldırmayı şart koşuyor.
- `LabelSchema` hem `add_exercise()` hem `add_error_type()` sağlıyor ve
  `ProjectWorkspace.save_label_schema()` mevcut atomik JSON yolunu kullanıyor.
  Review'daki yerinde picker/oluşturma akışı bugün yalnız hata türünde var.
- Aktivite UI'si `TimelineMode.ACTIVITY`, sağ Aktivite kartı, timeline lane'i ve
  F3 kısayoluyla gerçekten mevcut; ekran görüntüsündeki `Aktivite durumları`
  düğmesi bu akışa ait.

### Sürümler ve bu prompt hazırlama turunun doğrulaması

- Gerçek kod sürümleri değişmedi: uygulama/paket **0.7.0**; project **1.1.0**;
  session **2.0.0**; take **1.1.0**; skeleton stream **1.1.0**; annotation,
  label ve release **2.0.0**; raw archive **1.0.0**; feature spec **1.0.0**;
  identity SQLite schema **1**.
- Kaynak kod, veri şeması ve paket sürümü değiştirilmedi; yalnız Claude görev
  promptu ile bu hafıza bölümü eklendi.
- Görsel ek `codex-clipboard-0bdf70b7-f06a-4114-bada-b2363291820b.png`
  incelendi; geniş sağ kart, Hareket/Hata/Aktivite modları ve sürekli açık
  hareket sınıfı alanı kullanıcının tarif ettiği yer kaybını doğruluyor.
- Bu turda test paketi veya self-test çalıştırılmadı; uygulama kodu değişmedi.
  Yalnız metin/kod incelemesi yapıldı. ZED kamera çalıştırılmadı ve GUI
  davranışı uygulanmış olarak doğrulanmadı.
