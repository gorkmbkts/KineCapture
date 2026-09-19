---
type: legacy-memory-section
status: archived
title: "ÖLÇÜLEREK DOĞRULANAN GERÇEKLER (varsayım değil)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "602-631"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6D. Ham RGB-D arşivi, kişi kilidi ve sürekli aktivite (2026-08-24)](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · ← [önceki](6d-6d-ham-rgb-d-arsivi-kisi-kilidi-ve-surekli-aktivite-2026-08-24.md) · [sonraki](6d-02-derinlik-saklama-karari-olculerek.md) →

Güncel karşılığı: [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### ÖLÇÜLEREK DOĞRULANAN GERÇEKLER (varsayım değil)

Bu turun en önemli çıktısı bir kod değil, bir ölçüm:

1. **SVO2 replay, ölçülen derinliği geri vermiyor.** Taze bir `capture.svo2`
   yeniden açılıp aynı konumlardan `MEASURE.DEPTH` okunduğunda, kayıt anındaki
   derinlikle **aynı değil**: yer yer 7-14 metre fark, geçersiz piksel maskesi
   bile farklı. Gerçek kayıtta iki kez doğrulandı (3 sn'lik probe ve 20 sn'lik
   canlı kayıt). Derinlik okuma anında yeniden hesaplanır ve depth mode, SDK
   sürümü ve GPU'ya bağlıdır. **Ölçülen derinlik ayrıca arşivlenmezse kalıcı
   olarak kaybolur.**
2. **SVO2 RGB'yi geri veriyor.** Her probe edilen konumdan `(720,1280,4)` RGB
   okundu. Bu yüzden ZED'de renk ikinci kez arşivlenmiyor.
3. **`H264` KAYIPLIDIR.** Ölçülen boyutlar (HD720/30): `H264` 96 MB/dk,
   `H264_LOSSLESS` 1116 MB/dk, `LOSSLESS` 2954 MB/dk. Önceki kod ve docstring
   SVO2'yi "lossless-by-default" diye tanımlıyordu; bu **yanlıştı** ve
   düzeltildi.
4. **Kamera zaman damgası SVO2'ye mikrosaniye çözünürlüğünde yazılıyor**:
   yeniden oynatmada son üç hane sıfırlanmış geliyor (ölçülen fark 300 ns).
5. **SVO kare sayısı canlı kare sayısına eşit olmayabilir**: 601 canlı kareye
   karşı `get_svo_number_of_frames()` 602 döndürdü. 1:1 sıra varsayılmıyor;
   eşleme zaman damgasıyla doğrulanabilsin diye indeks her karede hem konumu
   hem kamera kare numarasını hem zaman damgasını yazıyor.
6. **`get_recording_status()` sayaçları hâlâ güvenilmez**: `ingested=0`,
   `encoded=0` döndürüyor. Tek başarı kanıtı olarak kullanılmıyor.
7. **`store_depth_frames` ölü bir ayardı.** Profilde ve Ayarlar ekranında
   vardı, `TakeWriter` hiç okumuyordu; tooltip'i "SVO2 derinliği yeniden
   üretebildiği için kapalı" diyordu ki bu da yanlıştı. Kaldırıldı, yerine
   zorunlu arşiv politikası ve codec seçimi geldi.
