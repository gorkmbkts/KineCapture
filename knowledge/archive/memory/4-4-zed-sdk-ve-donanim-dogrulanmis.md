---
type: legacy-memory-section
status: archived
title: "4. ZED SDK ve donanım — DOĞRULANMIŞ"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "126-172"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](3-3-ortam-dogrulanmis.md) · [sonraki](5-5-gercekten-calisan-ozellikler.md) →

Güncel karşılığı: [RGB-D ve depth](../../concepts/rgbd-and-depth.md), [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md).

## 4. ZED SDK ve donanım — DOĞRULANMIŞ

```text
ZED SDK        : 5.4.1
pyzed          : 5.4  (sl.cp311-win_amd64.pyd, KineSynth site-packages içinde)
SDK yolu       : C:\Program Files (x86)\ZED SDK
Kamera         : ZED 2i, S/N 31844341, firmware 1523, state AVAILABLE
CUDA (virtual) : 13.3
```

`pyzed` import ediliyor, kamera açılıyor, RGB + derinlik + vücut takibi +
SVO2 kaydı çalışıyor. **Blocker yok.**

### Ölçülen davranış

- **İlk açılış çok yavaştır**: SDK sinir ağı modellerini optimize eder.
  Ölçüldü: ilk `camera.open()` 157 s, ilk `enable_body_tracking()` 70 s.
  Bu tek seferliktir; sonraki açılışlar **2.6–4.3 s** ve body tracking
  **0.2 s**. GUI bunu bir uyarı mesajıyla bildiriyor.
- RGB `retrieve_image(VIEW.LEFT)` → `(720, 1280, 4)` uint8 **BGRA**.
  Adapter `[:, :, :3][:, :, ::-1]` ile contiguous RGB'ye çeviriyor.
- Derinlik `retrieve_measure(MEASURE.DEPTH)` → `(720, 1280)` float32,
  ölçümsüz pikseller non-finite (~%32 sahnede).
- `keypoint_confidence` **0..100** ölçeğindedir; domain sözleşmesi 0..1
  olduğu için adapter 100'e bölüyor.
- `bodies.body_format` BODY_34 için `1` döner.
- SVO2 (H264) 60 kare / HD720 ≈ 3.3 MB. Yeniden açılıp `set_svo_position`
  ile aranabiliyor.
- `get_recording_status()` sayaçları (`number_frames_ingested/encoded`) bu
  SDK sürümünde 0 dönüyor olsa da dosya büyüyor; **bu sayaçlara
  güvenilmiyor**, uygulama kendi sayaçlarını tutuyor.

### ZED iskelet tabloları — yerel SDK'dan okundu

`sl.BODY_18/34/38_PARTS` value sırasıyla ve `sl.BODY_*_BONES` enumere edilerek
`visualization/skeleton_spec.py` içine yazıldı. **Ezberden yazılmadı.**

BODY_34 doğrulanan sıra (ilk/son birkaçı):
`0 pelvis, 1 naval_spine, 2 chest_spine, 3 neck, 4 left_clavicle,
5 left_shoulder, … 24 right_ankle, 25 right_foot, 26 head, 27 nose,
28 left_eye, 29 left_ear, 30 right_eye, 31 right_ear, 32 left_heel,
33 right_heel`

Regresyon koruması: `python -m kinecapture.tools.verify_zed_topology`
canlı SDK ile bu tabloları karşılaştırır. `scripts/diagnose.ps1` bunu her
tanıda çalıştırır. **Son sonuç: BODY_18/34/38 üçü de birebir uyuşuyor.**
