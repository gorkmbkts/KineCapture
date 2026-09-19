---
type: legacy-memory-section
status: archived
title: "7. Mimari sınırlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2937-2963"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6ab-6ab-studio-f4f7-ekranlar-ayri-surec-kutuphane-2026-09-13.md) · [sonraki](8-8-test-komutlari.md) →

Güncel karşılığı: [Sistem haritası](../../architecture/system-map.md).

## 7. Mimari sınırlar

```text
gui/            PySide6; kameraya ve diske dokunmaz
gui/state.py    authenticated AppState; user/proje/katılımcı/auto-session
identity/       SQLite schema + repository + scrypt + auth/access service
capture/        CaptureService: acquisition thread + writer thread
camera/         base (sözleşme) · mock · zed  ← pyzed yalnız burada, gecikmeli
recording/      TakeWriter, ProxyVideoWriter, kalite akümülatörü
playback/       skeleton stream okuma, proxy video okuma, kurtarma
annotations/    AnnotationRepository (undo/redo, autosave)
dataset/        ProjectWorkspace (disk), DatasetIndex (sorgu/özet/QA)
export/         ReleaseBuilder (staging → atomik yayın) + continuous.py
features/       sürümlü seçilebilir özellik katmanı ← Qt ve pyzed içermez
capture/subject_lock.py   kişi kilidi durum makinesi ← Qt ve pyzed içermez
recording/rgbd_archive.py chunk'lı ham RGB-D arşivi, worker havuzu
domain/         enums, models, project, labels, activity  ← Qt ve pyzed içermez
visualization/  skeleton_spec (veri), mapping (sürümlü adapter)
core/           errors, ids, jsonio, paths, config, logging, diagnostics,
                state_machine, fingerprint
tools/          verify_zed_topology
```

Durum makinesi: `DISCONNECTED → READY → PREVIEWING → RECORDING → STOPPING →
REVIEWING`, `ERROR` her yerden erişilebilir ve kurtarma `DISCONNECTED`
üzerinden döner. Geçersiz geçişler `InvalidStateTransition` fırlatır.
