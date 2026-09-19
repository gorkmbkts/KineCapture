---
type: legacy-memory-section
status: archived
title: "6B. İki seviyeli etiketleme redesign'ı (2026-08-21)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "294-392"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6-6-bu-gorevde-alinan-kalici-teknik-kararlar.md) · [sonraki](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6B. İki seviyeli etiketleme redesign'ı (2026-08-21)

### Ürün kararları

1. **Bir hata aralığı = tek hata sınıfı.** Aynı anda görülen farklı sınıflar
   *çakışan aralıklarla* ifade edilir. Böylece her aralık temiz bir
   `(sınıf, başlangıç, bitiş)` üçlüsü olur ve zamansal hedef belirsizleşmez.
   Aynı sınıf bir hareket içinde tekrar edebilir.
2. **Doğru/yanlış ikili.** `Correctness` artık `correct | incorrect |
   unlabelled`. `unlabelled` bir hareket sınıfı değil, "henüz karar verilmedi"
   çalışma durumudur ve asla export edilmez. Eski `uncertain`/`unknown`
   **kesin karara çevrilmez**; `unlabelled` olur ve orijinal değer `legacy`
   içinde saklanır.
3. **`AnnotationStatus` kaldırıldı.** Draft/reviewed/approved yerine
   **türetilmiş** `SampleReadiness` var: `evaluate_sample()` tek kuraldır ve
   hem ekranın "hazır" tanımını hem exportun "uygun" tanımını besler. İkisi
   ayrışamaz. `SegmentStatus.EXCLUDED` kullanıcının açık "datasetten çıkar"
   eylemi olarak korundu.
4. **Tutarlılık kuralları**: doğru + hata aralığı = `contradiction`;
   hatalı + aralık yok = `needs_error_interval` (çalışılabilir, hazır değil);
   ters/boş/dışarı taşan/bilinmeyen sınıflı aralık = `invalid_interval`.
   Hiçbiri export edilmez.
5. **Hareket fazı kaldırıldı** (UI, yeni model, yeni export). Eski değerler
   `legacy.movement_phase` içinde korunur. `severity`, `affected_joints`,
   `annotator_confidence` da aynı şekilde saklanır — kullanılmıyor fakat
   silinmiyor.
6. **Kare sınırı sözleşmesi tek ve belgeli**: konumlar `skeleton.jsonl` kare
   listesindeki 0 tabanlı indekstir ve **her iki uç dahildir**. Arayüz, sidecar
   ve export aynı anlamı kullanır. Export ayrıca göreli konumları
   (`relative_start/end`), kamera kare numaralarını ve zaman damgalarını yazar.
7. **Undo kapsamı**: undo bu kaydın etiketlerini geri alır, **proje çapındaki
   hata sınıfı sözlüğünü değil**. Sınıf oluşturma bir *proje* düzenlemesidir;
   picker "listeye ekler" ve bir aralık fikri değişti diye liste küçülmez.
   Bu davranış hem docstring'de hem arayüz ipucunda yazılı.
8. **Birleştirme kayıp yaratmaz**: farklı etiketli iki hareket birleşirse
   kaybeden etiket `legacy.merged_from` içine yazılır ve kullanıcıya bildirilir.
   Bölme, sınırı aşan hata aralığını ikiye böler; hiçbiri düşmez.
9. **Ana sınır daralması**: kesişen aralıklar kırpılır, tamamen dışarıda kalan
   kaldırılır; ikisi de rapor edilir (`BoundsChangeReport`) ve Ctrl+Z ile geri
   alınabilir.
10. **İskelet-only mod 3B metrik görünüm kaldı** (döndürme + merkezleme).
    Gerekçe: bindirilmiş mod zaten "kamera ile hizalı mı" sorusunu yanıtlıyor;
    derinlik hatası kameranın kendi bakışından görünmez. Sabit projeksiyon
    eklemek yeni bilgi vermezdi.

### Şema ve uyumluluk

- `ANNOTATION_SCHEMA_VERSION` 1.0.0 → **2.0.0**, `LABEL_SCHEMA_VERSION` → 2.0.0.
- Sidecar dosya adı **değişmedi** (`annotations/segments.json`), böylece mevcut
  kayıtlar bulunmaya devam ediyor. v2 `samples` anahtarını yazar; okuma hem
  `samples` hem eski `segments` anahtarını kabul eder.
- **Okuma dosyayı yeniden yazmaz.** v1 belge yalnızca kullanıcı bir düzenlemeyi
  kaydettiğinde v2'ye dönüşür. Projeyi açmak eski etiketi bozamaz.
- `RepetitionSegment` adı `MovementSample`'a taşındı; eski ad alias olarak
  duruyor. `load_segments`/`save_segments` de alias.
- Eski `EvidenceInterval` değerlendirildi ve **yerini `ErrorInterval` aldı**:
  aynı fikir, fakat tek sınıf + kaynak + zaman damgası taşıyor ve ana hareketin
  içinde olması garanti ediliyor. Eski `evidence_intervals` kayıpsız okunuyor.
- Hareket seviyesindeki eski `error_types` listesi zamansız olduğu için
  aralığa **çevrilmiyor**; `legacy.unlocalised_error_types` olarak saklanıyor.
  Sınır uydurmak, veriyi kaybetmekten daha kötü olurdu.

### Export sözleşmesi

- Her hareket sample'ı bir örnek; zaman boyutu hareketin sınırlarından gelir.
- Manifest örneği: `exercise`, ikili `correctness`, `error_intervals[]`
  (sınıf + mutlak + göreli + kamera karesi + zaman damgası), `error_classes`,
  `has_error_localisation`.
- `.npz` içinde ayrıca: `error_intervals` `int32 [K,3]`
  `(class_index, relative_start, relative_end)` ve `error_multi_hot`
  `uint8 [T,C]` (sütun sırası `label_mapping` ile aynı; çakışma aynı karede
  birden çok sütunu 1 yapar). İkisi birlikte yazılıyor: liste otoriter ve
  okunabilir, dizi doğrudan eğitilebilir.
- `label_mapping.error_types.code_to_index` sıralı koddan üretilir → sürümler
  arası kararlı.
- Doğrulama: yetim aralık, dizi dışına taşma, bilinmeyen kod, ters/boş aralık,
  doğruluk-hata çelişkisi, manifest-dizi uzunluk uyuşmazlığı, göreli-mutlak
  tutarsızlığı.
- Fingerprint hata sınıfı ve aralık sınırlarına duyarlı (test edildi).
- **Dışlanan her şey nedeniyle yazılır**: hazır olmayan hareket, kullanıcı
  tarafından dışlanan hareket, filtrelenen kayıt. "Hareketim neden yok?"
  sorusunun cevabı `excluded.json` içinde.
- Geçersiz bir aralık, sample'ın **tamamını** dışlar. Yalnız o aralığı atmak
  modele "burada hata yok" demek olurdu; bu yanlış etiketlemedir.

### Bu turda bulunan gerçek hatalar

1. **v2 round-trip kaybı**: ikinci okumada üst düzey `status` (sample'ın
   active/excluded durumu) eski *annotation review status* sanılıp `legacy`'ye
   yazılıyordu. Yalnız v1 belgede toplanacak şekilde düzeltildi.
2. **Sessiz dışlama**: hazır olmayan hareketler `excluded.json`'a hiç
   yazılmadan eleniyordu. `_partition_samples` + `_rejected_takes` eklendi.
3. **`projects.py` eski sayaç anahtarını okuyordu** (`repetitions`), sayfa her
   açılışta `KeyError` veriyordu.
4. **Zaman çizelgesi şerit başlığı çakışması**: frame 0'da başlayan bir aralık
   "HAREKET" yazısının üstüne biniyordu. Sol gutter (`_GUTTER = 58`) eklendi.
5. 1366x768'de yan panel taşıyordu; aktif modun kartı öne alınıyor, pasif modun
   kartı özet satırına daraltılıyor, transport zaman çizelgesi kartına taşındı.
