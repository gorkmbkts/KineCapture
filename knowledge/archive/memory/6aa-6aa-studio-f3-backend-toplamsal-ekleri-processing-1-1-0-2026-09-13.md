---
type: legacy-memory-section
status: archived
title: "6AA. Studio F3 — backend toplamsal ekleri, processing 1.1.0 (2026-09-13)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2748-2857"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6z-6z-studio-arayuzu-f2-katman-token-kabuk-2026-09-13.md) · [sonraki](6ab-6ab-studio-f4f7-ekranlar-ayri-surec-kutuphane-2026-09-13.md) →

Güncel karşılığı: [Studio F0–F15](../../milestones/studio-f0-f15.md), [Veri hattı](../../concepts/pipeline.md).

## 6AA. Studio F3 — backend toplamsal ekleri, processing 1.1.0 (2026-09-13)

Plan: `FAZ_PLANI_PYSIDE6_STUDIO.md`. F1'de ölçülen darboğazların **veri
tarafı** bu fazda kapatıldı; çizim tarafı F8'de.

### Kalıcı kararlar

1. **`PROCESSING_SCHEMA_VERSION` 1.0.0 → 1.1.0.** Bir sürüm artık şunları da
   taşır: `arrays/*.npy` + `arrays/index.json`, `summary/` piramidi,
   `thumbs/`. `job.json` `paused`, `paused_s`, `rate_fps`, `eta_s` kazandı.
2. **`arrays.npz` yeni sürümlerde yazılmıyor.** Sıkıştırılmış arşiv üyesi
   bellek eşlenemez; asıl mesele buydu. Yerine dizi başına sıkıştırılmamış
   `.npy`. **Eski sürümler okunmaya devam ediyor**: `ArrayStore` 1.0.0
   yerleşimine düşer ve `is_memmapped=False` diyerek pencere okumasının ucuz
   **olmadığını** söyler — çağıran tahmin etmez. Testle sabitlendi.
3. **Timeline özeti min/max piramididir**, ses editöründeki dalga formu gibi.
   Ortalama değil: bir saniyelik iyi veri içindeki tek kötü kare ortalamada
   kaybolurdu — oysa annotatörün aradığı tam olarak o karedir. Kapsam için
   `any`/`all`, QC bayrakları için bitwise-or. Ölçülmemiş bin NaN kalır;
   0.0 ile karıştırılmaz.
4. **Thumbnail'ler seek ile alınır, sırayla okunarak değil.** İlk sezgi
   yanlıştı ve ölçüldü: 302 karelik proxy'de sıralı 305 ms, seek 131 ms — ve
   seek maliyeti kayıt uzunluğundan bağımsız. Codec seyrek keyframe'liyse
   birkaç kare kayabilir; indeks **istenen** değil **inilen** konumu yazar.
5. **`DepthReader` chunk başlıklarını bir kez okuyup indeks kurar** ve son
   çözülen chunk'ı tutar. Bunun için `rgbd_archive.read_chunk_header` eklendi
   (toplamsal). Offline derinlik her yerde `reconstructed_offline`
   provenance'ı taşır; kayıt anındaki ölçüm değildir.
6. **Proje indeksi türetilmiştir, otorite değildir.** `cache/take_index.json`
   silinebilir/bozulabilir; sonraki yenilemede `take.json` ve `job.json`
   dosyalarından yeniden üretilir. **Yapısal değişikliği** algılar (kayıt veya
   sürüm eklendi/kalktı), çalışan bir işin ilerlemesini değil — onu isteyen
   ekran `job.json`'u doğrudan okur.
7. **Duraklatma iptal değildir.** Yeni canlı kayıt GPU'yu geri isterse iş kare
   sınırında durur, bütün akışlar açık kalır, kaldığı yerden devam eder.
   Duraklama süresi `paused_s` olarak ayrı tutulur ve hız penceresi sıfırlanır;
   beklenen süre boşta geçen zamanla kirletilmez. İptal duraklamayı yener.
8. **Yüzde uydurulmaz.** Kaynak kare sayısı bildirilmemişse `eta_s` ve oran
   `None` kalır; ilk `_RATE_WARMUP_FRAMES = 20` kare model ısınmasına gittiği
   için orana dahil edilmez.

### Ölçülenler (60 dk / 60 FPS / BODY_38 sentetik, gerçek kod yolları)

| Ölçüm | 1.0.0 | 1.1.0 |
|---|---|---|
| Dizi yazımı (135 MB ham) | 5,05 s → 122,1 MB | **0,13 s** → 135,0 MB |
| 600 karelik pencere okuma | 403,7 ms | **13,5 ms** (soğuk, store açılışı dahil) |
| 100 ardışık pencere | — | **14,5 ms** toplam (0,14 ms/pencere) |
| Timeline özeti üretimi | yok | 0,06 s · 4,8 MB · 11 seviye |
| Lane okuma (60 dk tam görünüm, 1600 px) | yok | ilk 7,9 ms, sonraki **0,007 ms** · 1688 bin |
| Thumbnail (302 kare, 13 adet) | yok | **131 ms** · 7,4 kB |
| `depth.at` rastgele / 40 ardışık | O(chunk) her kare | 24,6 ms / 110,7 ms (2,8 ms/kare) |
| `position_of_anchor` ×1000 | doğrusal tarama | **0,7 ms** |

Proje indeksi (1000 kayıt, aynı koşuda karşılaştırıldı):

| | süre |
|---|---|
| Eski desen (`rglob("*.json")` + stat, **her** yenileme) | 1247 ms |
| Yeni: ilk kurulum (hepsi okunur) | 3932 ms |
| Yeni: önbellekli yenileme (0 yeniden okuma) | **154 ms** |
| 100 kayıtta eski / yeni önbellekli | 126,7 ms / **15,8 ms** |

**Dürüstlük notu:** 154 ms bir UI karesi değildir. İndeks GUI thread'inde
çalıştırılmaz; F4/F7 onu worker thread'e alır. İndeksin kazandırdığı şey işin
*sık* çalıştırılabilecek kadar küçülmesidir, sıfırlanması değil. Ayrıca F1'de
aynı eski desen 650 ms ölçülmüştü; bu turda 1247 ms çıktı — makine/disk önbellek
değişkenliği. Karşılaştırma yalnız aynı koşu içinde geçerlidir.

Windows'ta tek bir `os.stat` yaklaşık **65 µs** sürüyor (Defender dahil); bu
yüzden tarama `Path.glob` yerine `os.scandir` ile yapılıyor — `DirEntry` dizin
listesinin zaten ürettiği stat'ı taşır, glob ise her girdiyi ikinci kez stat'lar.

### Uzun yol tuzağı — `long_path` her yol için ayrı karar verir

F3 testlerini yazarken gerçek bir tuzağa düşüldü ve kalıcı olarak not edilmeli:
`core.paths.long_path` yalnız **kendisine verilen yol** 227 karakteri
(`MAX_PATH 259 − margin 32`) aşarsa `\?\` önekini ekler. Bu yüzden
`derived/processing` dizini eşiğin **altında** kalıp önek almazken, iki seviye
içindeki `job.json` sınırı aşabilir. Sonuç: kısa ebeveynden yapılan
`Path(...).glob(".*.partial/job.json")` **hiçbir şey döndürmez ve hata da
vermez** — arama zaman aşımı gibi görünür.

Kural: derin bir dosyaya erişirken yol **kademeli kurulur** ve `long_path`
yaprakta uygulanır (`read_json(base / name / "job.json")` gibi); kısa bir
ebeveynden özyinelemeli glob edilmez. Uygulama kodu zaten böyle çalışıyor;
hata yalnız test tarafındaydı. Ayrıca pytest'in geçici dizin adı test adını
içerdiği için uzun test adları bu sınırı kolayca aşıyor.

İlgili ikinci gözlem: OpenCV `\?\` önekini kabul etmediği için uzun yolda
proxy video yazılamıyor ve `process_take` bunu `review_proxy_incomplete` ile
işaretleyip sürümü `partial` bırakıyor. Bu **mevcut** bir sözleşme kararıdır
(F3'te değiştirilmedi); ilgili test bu durumu açıkça skip ediyor. Kolaylık
amaçlı bir ürünün (proxy) bilimsel sonucu kullanılamaz yapması ileride ayrıca
tartışılmalı.

### Çalıştırılanlar

- `tests/test_processing_artifacts.py` **23 passed** (yeni).
- `tests/test_summary_index.py` **17 passed** (yeni).
- `tests/test_processing_pipeline.py` **18 passed** (6 yeni: 1.1.0 ürünleri,
  duraklat/devam, duraklamışken iptal, ilerleme alanları, 1.0.0 uyumluluğu).
- `tests/test_environment.py` **11 passed** (yeni: offline katman Qt/SDK'sız
  import ediliyor).
- Gerçek mock take üzerinde uçtan uca: `python -m kinecapture.processing` →
  complete, 302 kare, 13 önizleme, 2 özet seviyesi, 4,9 s.
- Aynı take'in **1.0.0 ile üretilmiş** sürümü yeni `ReviewDataset` ile açıldı:
  diziler, derinlik ve anchor round-trip çalışıyor; özet/thumbnail yok diye
  raporlanıyor.
