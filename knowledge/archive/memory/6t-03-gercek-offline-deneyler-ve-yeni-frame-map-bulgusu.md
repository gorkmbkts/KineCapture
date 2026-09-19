---
type: legacy-memory-section
status: archived
title: "Gerçek offline deneyler ve yeni frame-map bulgusu"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "2205-2249"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6T. Squat/offline incelemesi tamamlandı — yeni veri bütünlüğü bulguları (2026-09-10)](6t-6t-squat-offline-incelemesi-tamamlandi-yeni-veri-butunlugu-bulgulari-202.md) · ← [önceki](6t-02-yeni-ve-oncelikli-hata-sdk-depth-tampon-sahipligi.md) · [sonraki](6t-04-diger-dogrulanan-sozlesme-aciklari.md) →

Güncel karşılığı: [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md), [RGB-D ve depth](../../concepts/rgbd-and-depth.md).

### Gerçek offline deneyler ve yeni frame-map bulgusu

Geçici kök:
`C:\Users\gorke\AppData\Local\Temp\kinecapture_offline_audit_3213e217b93146a894135cd5439dca7d`.
Deney öncesi yaklaşık 207 GB alan vardı; tam depth arşivi üretilmedi. Yalnız
3 karelik tampon deneyi yaklaşık 6 MB yazdı. `audit.py`, `followup.py`, JSON
özetleri, partial stream'ler ve test XML'i burada; bunlar geçici/türetilmiş.
Önemli sayılar kalıcı rapora aktarıldı. Aynı betikler aynı dosya adlarını
kullandığından mevcut dizinde körlemesine yeniden çalıştırılmamalı.

İki RGB-only, dört BODY_34/38 sıralı geçişi ve 40 karede bir kooperatif iptal
yapıldı. Kaynak HD720/30; RGB retrieval 640×360; body geçişleri ACCURATE,
NEURAL_PLUS, fitting/tracking açık, confidence 40, reduced precision kapalı,
svo_real_time_mode=False. Eski canlı take profili MEDIUM/NEURAL_LIGHT olduğu
için yeni sonuçlar aynı canlı profilin karşılaştırması değildir.

| Kaynak | SDK kare bildirimi / okunan | RGB decoding FPS | BODY_34 FPS / gövdeli kare | BODY_38 FPS / gövdeli kare |
|---|---|---:|---|---|
| take_20260820T165211_daeb | 668 / 667 | 69.43 | 17.02 / 609 | 14.80 / 615 |
| take_20260821T111845_4ed7 | 230 / 229 | 65.07 | 17.19 / 226 | 13.79 / 229 |

- B'de BODY_38 tüm 229 karede iki kişi buldu; BODY_34 hiç iki kişi bulmadı.
  Proxy'de ana oturan kişi ve sağda kısmen görünen başka kişi var. Daha fazla
  kişi bulmak squat doğruluğu veya doğru katılımcı eşlemesi kanıtı değildir.
- Body geçişleri kaynak 30 FPS'in altında olmasına rağmen RGB geçişinin aynı
  okunabilir konumlarını sıralı, tekrarsız ve ek iç boşluksuz işledi. Bu, yavaş
  offline işlemenin ek kare atlaması gerektirmediğini doğrular.
- A'da 0..666, B'de 0..228 okunuyor; SDK'nin bildirdiği son 667/229 konumuna
  ayrıca seek de EOF dönüyor. Bütün tam geçişler declared count kontrolünü
  geçemediği için partial tutuldu; başarılı publish yolu denenmedi. SDK EOF
  sayımı/eskiden kayıt sınırı/dosya sorunu ayrımı bilinmiyor. Otomatik N−1
  istisnası konmamalı.
- Her iki take'te live[1:] timestamp'leri mikro saniyeye nicemlendiğinde SVO
  0..N−2 ile tam eşleşiyor. Eşleşmeyen **canlı ilk kare**, ilk SVO timestamp'inden
  A'da 66.744899 ms, B'de 66.757700 ms önce. Bu “canlı son kare eksik” değildir.
  Bildirilen son SVO'nun okunamamasıyla nedenselliği kanıtlanmadı. Yeni offline
  skeleton'ı eskisinin üzerine yazmak annotation konumlarını kaydırabilir.
- 40 karede kooperatif iptal kaynak hash'ini değiştirmedi; yalnız partial çıktı
  bıraktı. Süreç kill, elektrik kesintisi, resume ve tracker durum devamlılığı
  test edilmedi.
- Aşama süreleri raporda: grab medyan yaklaşık 48–50 ms; body retrieval ve
  Python dizi hazırlığı BODY_34 yaklaşık 7.5–8 ms, BODY_38 yaklaşık 15–20 ms.
  GPU kernel profiling değil; grab saf depth süresi sayılamaz. Açılış hariç;
  tam proxy/depth yazımı yok. RGB FPS canlı NVENC/capture benchmark değildir.
