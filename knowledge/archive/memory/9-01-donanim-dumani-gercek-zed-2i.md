---
type: legacy-memory-section
status: archived
title: "Donanım dumanı — GERÇEK ZED 2i"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2993-3047"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · ← [önceki](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · [sonraki](9-02-redesign-dogrulamasi-2026-08-21-donanimsiz.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md), [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md).

### Donanım dumanı — GERÇEK ZED 2i

Gerçek kamerayla, uygulamanın kendi hattı üzerinden (`ZedCameraBackend` →
`CaptureService` → `TakeWriter` → `load_take` → `AnnotationRepository`):

İki kez çalıştırıldı. **İkinci çalıştırmada kameranın önünde bir kişi vardı**,
böylece gövde takibi ve gerçek veriyle export de doğrulandı.

**Çalıştırma 1 — kamera önünde kimse yok:**

```text
connect                4.3 s (model optimizasyonu daha önce yapılmıştı)
KAYIT                  121 kare / 4.03 s / ölçülen 29.8 FPS (hedef 30)
VERİ KAYBI             YOK — dropped=0, missing=0
tracking_coverage      0.00, bodies=0
skeleton.jsonl         12,312 B (yalnız header + boş kare kayıtları)
export                 DOĞRU BİÇİMDE REDDETTİ: no_body_in_interval
```

Boş sürüm yayımlanmaması beklenen ve istenen davranıştır.

**Çalıştırma 2 — kamera önünde bir kişi var (TAM DOĞRULAMA):**

```text
connect                3.7 s
model/serial/firmware  ZED 2i / 31844341 / 1523      sdk 5.4.1
çözünürlük/fps         1280x720 @ 30                 coord right_handed_y_up, unit meter
body format            zed_body_34                   depth=True, body_tracking=True
capabilities           color+depth+body+native_recording+multi_body+enumeration
önizleme karesi        rgb (720,1280,3) uint8, depth (720,1280), camera_ts alındı
KAYIT                  122 kare / 4.03 s / ölçülen 30.0 FPS (hedef 30)
VERİ KAYBI             YOK — dropped=0, missing=0, zaman boşluğu 0
GÖVDE TAKİBİ           tracking_coverage=0.45, mean_joint_conf=0.736,
                       distinct_body_ids=1, tracking id=(0,)
dosyalar               capture.svo2 7,215,771 B · skeleton.jsonl 123,593 B
                       · proxy.mp4 476,068 B
oynatma                122 kare, 4.03 s, proxy seek OK, 2 marker, spec=zed_body_34
etiketleme             1 tekrar oluşturuldu ve etiketlendi
EXPORT (native)        dataset_v001 · 1 örnek · doğrulama GEÇTİ
                       dizi (118, 34, 3) float32, %45 finite,
                       skeleton=zed_body_34, origin=real, camera=ZED 2i
EXPORT (rehab24)       dataset_v002 · dizi (118, 26, 3) · status=partial
                       mapped=23/26
                       tamamı NaN olan eklem indeksleri = [5, 20, 25]
```

Son satır kritik: REHAB24-6 sırasında indeks **5 = `Head_end`**,
**20 = `LeftToeBase_end`**, **25 = `RightToeBase_end`**. Yani eşleştirme
gerçek BODY_34 verisi üzerinde tam olarak beyan ettiği gibi davrandı —
23 eklemi doldurdu, yalnızca ve tam olarak beyan edilen 3 eklemi NaN
bıraktı, başka hiçbir eklemi bozmadı.

`mean_joint_conf=0.736` değeri, SDK'nın 0..100 ölçeğinin 0..1'e doğru
çevrildiğini de kanıtlıyor (ham değer ~73.6 olurdu).
