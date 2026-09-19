---
type: legacy-memory-section
status: archived
title: "Ham arşiv mimarisi"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "651-678"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-02-derinlik-saklama-karari-olculerek.md) · [sonraki](6d-04-kisi-kilidi-capture-subject-lock-py-algoritma-surumu-1-0-0.md) →

Güncel karşılığı: [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Ham arşiv mimarisi

```text
raw/capture.svo2                  ZED stereo görüntüleri (H264, kayıplı)
raw/raw_capture_manifest.json     biçim, codec, provenance, senkron sözleşmesi
raw/rgbd/depth_%06d.kcd           ölçülen derinlik, chunk'lı, bağımsız çözülür
raw/rgbd/color_%06d.kcc           yalnız native kayıt yoksa (mock backend)
raw/rgbd/index.jsonl              kare başına senkron indeksi
```

- Chunk = 15 kare (30 fps'te yarım saniye). Her chunk kendi JSON başlığını ve
  payload uzunluğunu taşır; yarım kalan chunk **okurken tespit edilir** ve
  yalnız o chunk kaybolur.
- Her chunk ayrı checksum'lanıyor (`checksum_targets` genişletildi).
- Kuyruk **bounded**; taşarsa kare kaybı sayılır ve gizlenmez.
- `TakeQualityMetrics` beş ayrı sayaç taşıyor: preview, kayıt kuyruğu, renk
  arşivi, derinlik arşivi, backend.
- **Ham arşivi eksik take `FINALIZED` olmaz**, `PARTIAL` kalır ve hiçbir dosya
  silinmez.
- Native kayıt durdurulamazsa hata yutulmuyor; `note_raw_failure` ile take'e
  taşınıyor ve finalize'ı düşürüyor.
- Kayıttan önce disk ön kontrolü: GB/dakika ve kaç dakikaya yettiği gösteriliyor,
  yetmiyorsa `insufficient_disk_space`. Çözünürlük/FPS **sessizce düşürülmüyor**.
- `python -m kinecapture.tools.extract_raw <take> --verify | --out <dir>`
  doğrulama ve çıkarım yapıyor, ham veriye dokunmuyor.

`RAW_ARCHIVE_SCHEMA_VERSION = 1.0.0` eklendi, `APP_VERSION` 0.6.0.
