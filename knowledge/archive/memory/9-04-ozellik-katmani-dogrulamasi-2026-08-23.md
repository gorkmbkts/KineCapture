---
type: legacy-memory-section
status: archived
title: "Özellik katmanı doğrulaması (2026-08-23)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3133-3180"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [9. Çalıştırılan doğrulamalar ve GERÇEK sonuçlar](9-9-calistirilan-dogrulamalar-ve-gercek-sonuclar.md) · ← [önceki](9-03-ham-arsiv-kisi-kilidi-surekli-aktivite-dogrulamasi-2026-08-24.md) · [sonraki](9-05-ek-olarak-donanimsiz-govde-donusumu-testleri.md) →

Güncel karşılığı: [Test ve ölçüm ortamı](../../protocols/test-and-measurement.md), [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md).

### Özellik katmanı doğrulaması (2026-08-23)

```text
python -m pytest                    438 passed, 121.9 s
python -m kinecapture --self-test   exit 0, export doğrulama=geçti
```

**GERÇEK ZED 2i ile doğrulandı** (kullanıcı kameranın önünde, canlı önizleme
penceresiyle kadraj kontrol edilerek):

```text
connect                3.8 s
model/serial/sdk       ZED 2i / 31844341 / 5.4.1
sol kamera intrinsics  fx=949.9 fy=949.9 cx=635.8 cy=350.7  1280x720  PINHOLE
KAYIT                  362 kare / 12.07 s / 29.9 FPS
VERİ KAYBI             YOK — dropped=0, missing=0, max_gap=66.6 ms
GÖVDE TAKİBİ           coverage=1.00, mean_joint_conf=0.888, distinct_ids=1

OPSİYONEL TRACKER ALANLARI (hepsi %100 sonlu, 362 kare x 34 eklem):
  joint_orientations          (362,34,4)  aralık [-0.763, 1]
  joint_positions_2d          (362,34,2)  aralık [34.5, 1311] piksel
  joint_position_covariances  (362,34,6)  aralık [-0.084, 0.120]
  local_joint_positions_xyz   (362,34,3)  aralık [-0.417, 0.264]
  root_position               (362,3)
  root_orientation            (362,4)
  tracker_root_velocity_xyz   (362,3)     aralık [-0.436, 0.439] m/s
  root_position_covariance    (362,6)
  action_state_code           idle=310, moving=52   (tracker gerçekten ikisini de veriyor)
  tracking_state_code         ok=362

EXPORT                 dataset_v001 · 2 örnek · doğrulama GEÇTİ
                       61 dizi / örnek, örnek şekli (120, 34, 3) float32
ÖLÇÜLEN DEĞERLER       joint_speed mean=0.381 max=3.867 m/s
                       sağ diz açısı 130.0°..180.0°, sol diz 172.1°..180.0°
                       gövde eğimi 0.2°..7.5°, body_scale 1.289 m
                       summary vector 307/307 eleman sonlu
                       quaternion normları mean=1.0000 (4080 örnek)
```

Son satır kritik: quaternion normlarının tam 1.0000 çıkması, `xyzw` okumasının
ve birim quaternion varsayımının gerçek veride doğrulandığını gösteriyor.
`joint_positions_2d` aralığının 1280 pikseli birkaç piksel aşması, kadrajın
kenarındaki eklemler için beklenen davranıştır.

`frame_timing`, `joint_displacement` ve `joint_acceleration` "kısmi"
raporlanıyor — tasarım gereği: ilk karede dt/yer değiştirme, ilk ve son karede
ivme NaN'dır.
