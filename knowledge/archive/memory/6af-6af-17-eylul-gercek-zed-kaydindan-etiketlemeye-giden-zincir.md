---
type: legacy-memory-section
status: archived
title: "6AF. 17 Eylül — gerçek ZED kaydından etiketlemeye giden zincir"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3463-3584"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6ad-6ad-studio-f9f15-3b-sporcu-disa-aktarim-cila-2026-09-14.md) · [sonraki](6ag-6ag-18-eylul-canli-zed-turu-ve-veri-kalitesi-olcumleri.md) →

Güncel karşılığı: [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md), [Kişi seçimi ve subject lock](../../concepts/subject-selection.md).

## 6AF. 17 Eylül — gerçek ZED kaydından etiketlemeye giden zincir

İki gerçek kayıt üzerinde teşhis edildi ve düzeltildi (dosya okundu, kameraya
bağlanılmadı). `C:\kc15\ry8kajfjq\datasets\.../prj_20260916T141947_23b4`:

| take | süre | kare | SVO |
|---|---|---|---|
| `take_20260916T151622_ce18` | 27,55 sn | 1648 | 1,67 GB |
| `take_20260916T224651_d41e` | 8,72 sn | 524 | 455 MB |

Kullanıcı "işledim ama kapsam doğrulanamadı dedi, sonra İşlenen Videolar boştu,
etiketleyemedim" dedi. Beş ayrı kusur üst üste binmişti.

### 1. Yayımlama, kusursuzluğun değil kullanılabilirliğin sorusu

`jobs.py` `state = "partial" if issues else "complete"` yazıyor, sonra **yalnız
`complete` olanı** `.run_x.partial` klasöründen `run_x`'e taşıyordu. Her ikisi de
tam üretilmişti (proxy.mp4, skeleton.jsonl, arrays, thumbs, checksums) ve
kareleri %99,6 / %99,8 eşleşmişti; ikisi de nokta ile başlayan klasörde kaldı,
hiçbir ekran listelemez.

Artık `BLOCKING_ISSUES` var ve yalnız üç kod yayımı engelliyor: `source_empty`,
`source_position_discontinuity`, `review_proxy_desynchronised` — yani
etiketlemeyi *yanlış* yapacak olanlar. Diğer her şey ölçülüp `job.json`'a
yazılıyor, satırda gösteriliyor, sürüm yayımlanıyor. `job["published"]`,
`job["blocking_issues"]`, `job["coverage"]` eklendi. CLI çıkış kodu: 0 notsuz,
1 notlarla yayımlandı, 2 yayımlanmadı. `is_complete` → `is_published`
(`state in (complete, partial) and promoted`), `complete_runs` →
`published_runs`. `ReviewDataset` `partial`'ı açıyor, `blocking_issues`
olanı açmıyor. `review_proxy_incomplete` ikiye ayrıldı: `_unavailable`
(video yok, sürüm kullanılır) / `_desynchronised` (kare sayısı uyuşmuyor, açma).

### 2. Kayıt öncesi seçilen kişi

`raw/subject_anchors.json` çapası **kayıt başlamadan önce** alınmış:
`camera_timestamp_ns` ilk kareden 3850 ms ve 1600 ms *önce*, `frame_index` 762
(kayıt 986'dan başlıyor — backend grab ordinali, take'e göre değil). Kesin
zaman eşleşmesi tutmayınca `subject_anchor_outside_source` yazılıp çapa
düşürülüyordu; sonuç: **joints dizisi baştan sona NaN**.

Artık ilk kareden önceye düşen çapa **ilk kareye** uygulanıyor, aynı bbox
testinden geçmek zorunda, `subject_anchor_before_recording` notu ve
`job["subject_anchors"] = [{position, method, offset_ms}]` yazılıyor. Kareye tek
beden varsa kapsama testi tutmasa da o beden seçiliyor (`sole_body_in_frame`).

### 3. Vücut imzası, tracker ısınırken ölçülüyordu

ZED gövde fitter'ı ilk karelerde yakınsamıyor ve **parça iskelet** veriyor.
Ölçüldü: squat kaydında p=0..5 `tracking_state=off`, 27 geçerli eklem, 7 segment,
boy **0,877 m**; p=6 `ok`, 38 eklem, 11 segment, boy **1,740 m** — 17 ms sonra,
aynı kişi, aynı `id`. `SubjectLock` ilk ölçümü kimlik olarak benimseyip
yedinciyi 0,0 benzerlikle reddediyor, `same_id_evidence_conflict` → AMBIGUOUS →
`update()` bir daha karar vermiyordu. 1638 kare kişisiz.

İmza artık yalnız `tracking_state == ok` karelerinden ölçülüp harmanlanıyor
(`_is_resolved`), ve `is_usable` en az 6 segment + sonlu boy istiyor.

### 4. ZED'in bildirdiği uzuv boyları duruşla değişiyor

Aynı kayıtta aynı kişi: ayakta eklem yayılımı 1,709 m, squat dibinde **1,064 m**;
uyluk 0,510 → 0,385 m (%25). `stature` eklem bulutunun dikey yayılımı olduğu
için **duruş ölçüsü**, kimlik ölçüsü değil; uzuv boyları da her karede yeniden
fit edildiği için sabit değil. Bu yüzden imza vetosu artık **yalnız karede
birden fazla beden varken** çalışıyor: aynı `id`'yi taşıyan tek beden varken
ortada karıştırılacak başka kimse yoktur. Ayrıca tek karelik çelişki artık
ilişkiyi bitirmiyor — `policy.contradiction_frames = 3`, aradaki kareler
`evidence_conflict_pending` olarak kişisiz yazılıyor. `ASSOCIATION_ALGORITHM_VERSION`
**1.2.0**.

Sonuç (gerçek kayıtlar, yeniden işlendi): squat 1641/1645 karede kişi,
capture 522/522; ikisi de yayımlandı ve `İşlenen Videolar`'da listeleniyor.

### 5. Kayıt tarafı: ölçülen kusur ile kayıp veri ayrıldı

- Kamera iki ardışık kareye **aynı mikrosaniyeyi** veriyor (524'te 1, 1648'de 2).
  `gap <= 0` testi bunu `camera_timestamp_non_monotonic` sayıp take'i PARTIAL
  yapıyordu. Artık `< 0` geriye gidiş, `== 0` `camera_timestamp_repeated` ve
  sayılıyor (`timestamp_repeats`); take'i düşürmüyor.
- SDK kayıt sonunda birkaç kareyi SVO'ya yazmıyor (`RecordingStatus.status`
  False). Sayılıyor (`native_frames_unwritten`), gerçek kayıp olduğu için hâlâ
  PARTIAL yapıyor, ama not artık ne olduğunu söylüyor — eskiden kapalı olan bir
  arşiv için "Ham RGB-D arşivi eksik" yazıyordu.
- `finalize()` eskiden **herhangi bir** integrity kodunu kayıp sayıyordu;
  artık `_raw_source_loss()` yalnız gerçekten eksik kareyi cümleye çeviriyor,
  gerisi `_integrity_summary()` ile nota yazılıyor.
- İşlemede aynı mikrosaniyeyi paylaşan kayıt satırları artık **geliş sırasıyla**
  eşleştiriliyor (`capture_timestamp_duplicated` notuyla); eşleşmeyen kare
  sayısı 3 → 2 ve 5 → 3'e indi.

### 6. Sürüm sıralaması

Bir take'in bütün sürümleri take'in `started_at`'ini paylaşıyor; liste bu yüzden
klasör adındaki rastgele hex'e göre sıralanıyordu, "en yeni sürüm" yanlış
sürümü açıyordu. `job.json`'a `created_at` eklendi; indeks ve kütüphane
`(started_at, created_at, job_mtime_ns, run_id)` ile sıralıyor.

### 7. GUI

`QTabWidget::pane`, `QFrame[kcSurface=raised|sunken]` ve `[kcSurface=header]`
artık `padding` taşıyor — etiketleme denetçisinin başlığı ve yardım metni pane
çizgisinin üstüne basılıyordu. Ayarlar formu dört kenardan içeri alındı.
Bildirim katmanı sayfanın kendi alt eylem çubuğunu (`bottom_reserve()`) boş
bırakıyor: Ayarlar'da "Kaydet" bildirimin altında kalıyordu.

### 8. Aşağı akış

- `LibraryService.matches(row, "ready")` artık yalnız `subject_chosen`'a
  bakıyor: listelenen sürüm zaten etiketlenebilir olduğu için "kapsam notu"
  hazır olmamak demek değil. Filtre adı "Kapsam notu olan".
- Kanonik paket her örneğe `processing_state`, `processing_issues`,
  `processing_coverage` yazıyor; notlar pakete taşınıyor.
- `ReviewDataset` kapısı ile export kapısı aynı kuralı paylaşıyor.

### Testler

`tests/test_recording_reaches_labelling.py` (7 — yayım kümesi, ısınma karesi,
imza kaynağı, duruş vetosu, algoritma sürümü, tekrarlı zaman damgası),
`test_processing_pipeline.py` içinde yayımlama/ön-çapa testleri,
`test_studio_theme.py` container padding, `test_studio_toasts.py` alt çubuk,
`test_studio_processing.py` bildirim bağlantısı, `test_capture_architecture.py`
çelişki sözleşmesi, `test_export_canonical.py` manifest notları.
