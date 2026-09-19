---
type: legacy-memory-section
status: archived
title: "Ham arşiv / kişi kilidi / sürekli aktivite doğrulaması (2026-08-24)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3073-3132"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · ← [önceki](9-02-redesign-dogrulamasi-2026-08-21-donanimsiz.md) · [sonraki](9-04-ozellik-katmani-dogrulamasi-2026-08-23.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md), [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md).

### Ham arşiv / kişi kilidi / sürekli aktivite doğrulaması (2026-08-24)

```text
python -m pytest                    528 passed, 160.1 s, 0 warning
python -m kinecapture --self-test   exit 0
  aktivite etiketleme       : OK (3 aralık, kapsam %97, 2 kare etiketsiz)
  ham RGB-D arşivi          : OK (65 derinlik, 65 renk karesi, float32_byteshuffle_zlib)
  export                    : OK (2 hareket örneği, 1 sürekli örnek, doğrulama=geçti)
```

**GERÇEK ZED 2i ile doğrulandı** (kullanıcı kadraja girdi, görüntüde kendi
üzerine tıkladı, 20 sn kayıt aldı; kadrajda zaman zaman birden fazla kişi
vardı):

```text
connect              3.8 s · ZED 2i S/N 31844341 · SDK 5.4.1
ham arşiv tahmini    3.63 GB/dk, boş alan 56 dakikaya yetiyor
KAYIT                601 kare / 20.00 s / 30.0 FPS · durum=finalized
AKIŞ KAYIPLARI       kayıt kuyruğu=0  renk=0  derinlik=0
ARŞİVLENEN           601 derinlik karesi (renk SVO2'de, ikinci kopya yok)

KİŞİ KİLİDİ          kilitli=601  kayıp=0  belirsiz=0  yeniden eşleştirme=0
kapsam               %100.0
ÇOKLU KİŞİ KARESİ    554   (kadrajda başka insanlar vardı)
görülen tracker ID   [1, 2, 3]
DİSKALİFİYE ID       [2, 3]   <- eş-görünürlük kuralı gerçek veride çalıştı
olaylar              yalnız 1 tane: subject_selected

HAM ARŞİV            601 derinlik karesi · chunk sorunu=0 · checksum uyuşmazlığı=0
SVO2                 var · sıkıştırma=H264 · lossless=False
BOYUTLAR             SVO2 34.2 MB · derinlik 1202.0 MB (20 saniye için)
SENKRON İNDEKS       601 satır
  ilk: p=0   i=3603 cam_ns=1787578786176571501 subj=locked
  son: p=600 i=4203 cam_ns=1787578806177876501 subj=locked
     ^ konum 0'dan, kamera kare numarası 3603'ten başlıyor: ikisi AYNI ŞEY DEĞİL

SVO2 YENİDEN OKUMA
  pos   0: RGB (720,1280,4) okundu · saklanan derinlikle aynı mı: HAYIR (max fark 13.22 m, maske farklı)
  pos 301: RGB okundu · aynı mı: HAYIR (max fark 14.36 m, maske farklı)
  pos 599: RGB okundu · aynı mı: HAYIR (max fark  6.85 m, maske farklı)
  SVO2 kare sayısı 602, canlı kare 601  <- 1:1 sıra varsayılamaz

ETİKETLEME           1 hareket + 1 hata aralığı · aktivite kapsamı %100 · sürekli: ready
EXPORT               1 hareket örneği + 1 sürekli örnek · doğrulama GEÇTİ
  sürekli örnek      T=601 · 24 dizi · etiketsiz kare=0
  sınıf dağılımı     {background: 200, target_exercise: 201, other_activity: 200}
  kişi kapsamı       %100 · otoritatif ilişkilendirme=True
  subject_present    601/601
```

Bu çıktının en kritik iki satırı: **554 karede birden fazla kişi vardı ve kilit
hiç kaymadı**, ve **SVO2'den yeniden okunan derinlik saklanan derinlikle aynı
değil**. İkincisi bu turdaki bütün depolama maliyetinin gerekçesidir.

**Donanımda doğrulanamayan:** otomatik yeniden ilişkilendirme (`reassociated`)
bu kayıtta **tetiklenmedi** — seçili kişi hiç kaybolmadı, tracker kimliği hiç
değişmedi. O yol yalnız deterministik stub testleriyle doğrulandı
(`tests/test_subject_lock.py`): yeni kimlikle dönüş, iki benzer aday,
uzun kaybolma, kimlik yeniden kullanımı, antrenör senaryosu.
