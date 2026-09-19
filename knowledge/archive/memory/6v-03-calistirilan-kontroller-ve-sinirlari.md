---
type: legacy-memory-section
status: archived
title: "Çalıştırılan kontroller ve sınırları"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2447-2480"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6V. Capture → Verileri Hesapla → Etiketleme backend devamı (2026-09-11)](6v-6v-capture-verileri-hesapla-etiketleme-backend-devami-2026-09-11.md) · ← [önceki](6v-02-surumler.md) · [sonraki](6v-04-testte-kullanici-tercih-sizintisi-ve-onarim.md) →

Güncel karşılığı: [Veri hattı](../../concepts/pipeline.md).

### Çalıştırılan kontroller ve sınırları

Kanıt dizini `C:\Users\gorke\AppData\Local\Temp\kcb_8af98122`:

- Backend/özellik/export/config kapsamı ilk çalışmada 244 passed + 2 eski
  beklenti başarısız (246 toplam, backend10.xml). Bunlar eski BODY_34 default
  ve artık hatalı depth açıklaması beklentisiydi; yeni kararlar için düzeltildi.
  Takip kapsamı **63 passed / 11.87 s** (remaining13.xml).
- Capture/genel GUI **56 passed / 22.18 s** (gui12.xml).
- SDK BODY_18/34/38 → disk → playback eklem/timestamp bütünlüğü, config ve
  offline anchor dahil **38 passed / 5.24 s** (final14.xml).
- Preview/listener bloklanırken kayıt ilerlemesi, eksik SVO2, kayıt sınırları,
  orta-akış iptali dahil **23 passed / 7.18 s** (closure16.xml).
- Modül-fixture tercih izolasyonu ve user-state **6 passed / 3.96 s**
  (isolation15.xml). Önceki ara sonuçlar/başarısız denemeler raporda belirtilir;
  örtüşen test sayıları toplanmaz.
- `python -B -m kinecapture --self-test` exit 0: 66 kare, playback, etiketleme,
  RGB-D arşivi, iki hareket/bir sürekli örnek export doğrulaması geçti.
- Yeni Python sürecinde processing/review import: PySide6/pyzed yüklenmedi.
  `git diff --check` geçti. Tam pytest başladı fakat GUI uzun beklemelerinde
  kesildi; **tam paket geçti denemez**. Wheel/install ve tam GUI matrisi yok.
- Gerçek eski B SVO: yeni RGB/proxy processing yolu 230 declared / 229 decoded,
  bütün okunabilir kareler işlendi; beklenen count/unmatched gerekçeleriyle
  partial. Max timestamp gap 33.424 ms, std 0.05975 ms, büyük gap 0. Kaynak
  immutable kaldı (svo_pipeline/.run_9562dcb98445424a.partial).
- Sınırlı gerçek SDK üç-kare depth kontrolü: üç farklı hash, sonraki okumalar
  önceki depth'i değiştirmedi, owned/read-only (bounded_depth_preview.json).
  Aynı görüntülerde CPU hafif pose 1 kişi ve 153.9/99.3/99.3 ms. Canlı hız veya
  tüm kişileri bulma garantisi değildir.
- Üç gerçek BODY_38/full precision SVO karesi: her karede iki kişi/38 eklem,
  timestamp/is_new integrity sorunu yok (bounded_sdk_body38.json).
- İki saniyelik sentetik diagnostic finalized; ara örnek source 58.55 FPS,
  queue loss 0; preview 14 tamamlanan / 45 atlanan. Bu ZED benchmark'ı değildir.
