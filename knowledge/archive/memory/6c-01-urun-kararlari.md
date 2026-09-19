---
type: legacy-memory-section
status: archived
title: "Ürün kararları"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "395-446"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · [sonraki](6c-02-ham-kayit-zenginlestirmesi.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### Ürün kararları

1. **Canonical veri dokunulmazdır.** `joints_xyz`, `frame_indices`,
   `camera_timestamps_ns` her sürümde yazılır, kapatılamaz ve hiçbir özellik
   onların yerine geçmez. Türetilen her şey ayrı, açık isimli dizi olarak
   *yanına* yazılır. Tek bir belirsiz `[T,J,C]` tensoruna concat yok.
2. **Varsayılan export değişmedi.** Hiçbir özellik seçilmezse üretilen sürüm,
   özellik katmanı yokken üretilenle birebir aynıdır (test edildi).
3. **Kare farkı ile fiziksel hız ayrı kanallardır.**
   `joint_displacement_xyz` = `x[t]-x[t-1]` (FPS'e bağlı), `joint_velocity_xyz`
   = kamera zaman damgasına göre türev (`length_unit/saniye`). KineSynthV3'ün
   mevcut "velocity" kanalı birincisidir; `KineSynth temel uyumluluk` preseti
   bu nedenle fiziksel hızı içermez. Tracker'ın kendi kök hızı
   (`tracker_root_velocity_xyz`) ile türetilen kök hızı
   (`root_velocity_derived_xyz`) de ayrı dizilerdir.
4. **Türev politikası tek yerde**: adım ancak `0 < dt <= 2.5/hedef_fps` ise
   kullanılır; boşluk üzerinden türev alınmaz. Birinci türev iç noktalarda
   merkezi fark, uçlarda tek yanlı; ikinci türevin uçları NaN. Filtre yok.
   İlk hız karesi sahte sıfırla doldurulmaz.
5. **Eksik veri uydurulmaz.** NaN sıfıra çevrilmez, önceki kareyle
   doldurulmaz. Her özellik mümkünse kendi `*_valid_mask` dizisini yazar ve
   doğrulama maske ile NaN düzenini karşılaştırır.
6. **Rol tabloları** (`features/roles.py`) açı/mesafe/simetri tanımlarını
   iskelet biçiminden ayırır. `zed_body_18`'de pelvis yok, `zed_body_38`'de tek
   bir kafa eklemi yok, `mock_16`'da ayak yok — bunlar doldurulmaz, ilgili
   sütun NaN kalır. Rol tabloları sürüm dosyasına yazılır.
7. **Açı, mesafe ve oran tanımları sürümlüdür** (`ANGLE_SET_VERSION` vb.) ve
   sütun sırasını sabitler. 11 açı, 14 mesafe, 3 oran, 10 bilateral çift.
   Üç noktalı açı `atan2(|u x v|, u.v)` ile hesaplanır (0 ve pi civarında
   arccos'tan daha kararlı); sıfıra yakın vektörde NaN.
8. **Simetri gövde uzayında ölçülür.** Kamera koordinatında `sol - sağ` almak,
   kişinin kameraya göre dönmesini asimetri gibi gösterirdi. Sagittal düzlem,
   pelvisten kurulan gövde çerçevesinin `x = 0` düzlemidir. Sonuçlar
   "asimetri teşhisi" olarak adlandırılmaz.
9. **Gövde çerçevesinin ön ekseni sekans başına bir kez** belirlenir (varsa
   boyun→burun/kafa referansıyla, yoksa yalnız sağ el kuralıyla ve bunu
   `forward_source` alanında yazarak). Kare başına karar verilseydi tracker
   gürültüsünde işaret değiştirebilirdi.
10. **Quaternion sırası `xyzw`**, yerel SDK üzerinde doğrulandı: `sl.Rotation`
    ile Y ekseninde +90 derece döndürülünce `[0, 0.7071, 0, 0.7071]` geliyor.
    Quaternion kaynaklı açısal hız `2*arccos(|<qa,qb>|)/dt` ile hesaplanır;
    mutlak iç çarpım `q`/`-q` çift örtüsünü doğrudan çözer, Euler açıları
    hiçbir yerde farklanmaz.
11. **Sabit uzunluklu özet vektörü (307 eleman)** rol/açı/mesafe listelerinden
    üretilir, iskelet biçiminden bağımsızdır; hesaplanamayan eleman NaN kalır,
    uzunluk değişmez. Template mesafesi, sınıf ortalaması, DTW ve dataset
    scaler'ı **bilinçli olarak yoktur** — split leakage yaratırlar.
12. **Klinik iddia yok.** Çıktılar "kinematik özellik" veya proxy olarak
    adlandırılır. `joint_centroid_proxy_xyz` bir kütle merkezi DEĞİLDİR ve öyle
    adlandırılmamıştır. Zemin yüksekliği / ayak teması doğrulanmış world-floor
    kalibrasyonu gerektirdiği için hiç üretilmez.
