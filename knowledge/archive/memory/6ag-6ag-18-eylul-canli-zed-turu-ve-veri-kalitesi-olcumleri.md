---
type: legacy-memory-section
status: archived
title: "6AG. 18 Eylül — canlı ZED turu ve veri kalitesi ölçümleri"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "3585-3662"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6af-6af-17-eylul-gercek-zed-kaydindan-etiketlemeye-giden-zincir.md)

Güncel karşılığı: [Canlı ZED doğrulaması](../../experiments/2026-09-18-live-zed.md), [Kişi seçimi ve subject lock](../../concepts/subject-selection.md).

## 6AG. 18 Eylül — canlı ZED turu ve veri kalitesi ölçümleri

Kullanıcı başındayken üç gerçek kayıt alındı. İlk ikisinde kişi seçilmedi,
üçüncüsünde seçildi. Zincir üçüncüsünde uçtan uca çalıştı.

### Kayıt tarafı (gerçek ZED, ilk kez ölçüldü)

| | 19,2 sn | 44,0 sn | 23,0 sn (kişi seçili) |
|---|---|---|---|
| kare | 1139 | 2594 | 1371 |
| ölçülen FPS | 59,17 | 58,88 | 59,60 |
| kuyruk kaybı | 0 | 0 | 0 |
| kamera düşüşü | 21 | 0 | 13 |
| tekrarlı zaman damgası | 0 | 2 | 0 |
| SDK'nın SVO'ya yazmadığı | 1 | 3 | 1 |

**60 FPS H264_LOSSLESS HD720'de tutuyor, kuyruk kaybı sıfır.** SDK her kayıtta
son 1–3 kareyi SVO'ya yazmadığını bildiriyor; gerçek ama sınırlı kayıp, take
PARTIAL kalıyor ve hiçbir aşamayı engellemiyor. 17 Eylül düzeltmesi doğrulandı:
2 tekrarlı zaman damgası tek başına take'i düşürmedi.

### İşleme sonucu (kişi seçili kayıt, `run_61ef0f7cf0fb42e3`)

1370/1370 karede kişi · 38 eklemin hepsi her karede geçerli, tek NaN yok ·
kapsam 1370/1371 (%99,93) · 38 eklemin tamamı %100 karede kadraj içinde ·
Sporcu sekmesinde yanıt bekleyen aralık 0.

### Kalıcı ZED bulguları (ölçüldü)

1. **Uzuv boyları bir model çıktısıdır, ölçüm değil.** Sol/sağ uyluk ortalaması
   0,418 m ve 0,418 m — üç ondalığa kadar aynı. Baldır, üst kol, ön kol da öyle.
   ZED simetrik rijit bir şablon oturtuyor. Bu sayılar antropometri olarak
   kullanılamaz; açılar ve hareket güvenilir.
2. **Güven değeri ısınmayı yakalamaz; kemik uzunluğu kararlılığı yakalar.**
   Kare 0–5 gövde 0,503–0,511 m, kare 6'da 0,477 m ve sonra CV %0,13. Aynı
   aralıkta ortalama güven 0,915 → 0,914, yani hiç değişmiyor. Tracker ısınırken
   **kendinden emin biçimde yanlış**. Etiketlemeye ~10. kareden başlanmalı.
3. **`joint_positions_2d` bağımsız bir ölçüm değil.** 3B eklemler iç
   parametrelerle geri yansıtıldığında hata **0,00 piksel**: 2B, 3B modelin
   izdüşümü. Veri kümesi kendi kendini doğruluyor. Modelden türemeyen tek şey
   RGB video; iskeletin doğru kişide/doğru yerde olduğunun **tek bağımsız
   kontrolü** videoya bindirip bakmak.
4. **Kaliteyi kadraj ve mesafe belirliyor.** Aynı kişi, aynı kamera:

   | | 2,48 m, ayaklar kadrajda değil | 3,02 m, tam kadraj |
   |---|---|---|
   | uyluk CV | %6,91 (0,375–0,520 m) | **%0,21** (0,409–0,420 m) |
   | diz açısı tabanı | 103° | **52°** |
   | kare-kare hareket medyanı | 7,1 mm | 2,5 mm |

   Eski kayıtta pelvis 35 cm alçalmasına rağmen diz 103°'nin altına inmiyor —
   o kaydın diz kinematiği güvenilmez.
5. **Gürültü tabanı** (ayakta, ilk 2 sn): ayak bileği 3 mm, gözler 5 mm,
   **el parmakları 62–72 mm**, diz açısı std **2,95°**. 3°'den küçük açı farkı
   anlamlı sayılmamalı; el eklemleri özellik setinden çıkarılmalı.
6. Squat dibinde tracker kötüleşmiyor: diz güveni 0,939 (genel 0,903), ayak
   bileği 0,942 (0,917). Yalnız ayak başparmağı düşüyor.

### Kişi seçimi artık zorunlu

Çapa dosyası yoksa `_associate_anchor` döngüsü hiç çalışmıyor; 17 Eylül'de
eklenen iki kurtarma da (ön-çapa, tek beden) bir çapa varlığına bağlı. Bu yüzden
`_can_record()` çapa yokken kaydı reddediyor — sessiz devre dışı buton değil,
ne yapılacağını söyleyen bir cümle ile. `_refuse()` hem pencere bildirimini hem
de **görüntü üstündeki** bildirimi gönderiyor.

### GUI

- **Bildirim kartı yeniden düzenlendi.** Başlık "Ayrıntılar" ve "Kapat" ile aynı
  satırdaydı; 400 px kartta başlığa ~120 px kalıyordu, "take_20260916T22465…"
  gibi. İki buton eylem satırına indi, başlık kartın %87'sini alıyor, açıklama
  eliding yerine sarılıyor.
- `preview.PreviewView`: görüntü üstünde **3 sn durup sönen bildirim**
  (`show_notice`, `NOTICE_HOLD_MS/NOTICE_FADE_MS`) ve **seçilen kişinin
  çerçevesi** (`set_subject_box`). Çerçeve etiketi kadraj rozetiyle çakışırsa
  altına iniyor.
- `services/framing.py`: `subject_box()` tıklamanın hangi tespite ait olduğunu
  çözüyor — kapsama, tek kişi varsa o kişi, belirsizse hiçbir şey.
