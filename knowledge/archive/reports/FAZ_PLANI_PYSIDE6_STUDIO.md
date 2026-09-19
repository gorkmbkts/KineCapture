# KineCapture Studio — PySide6 arayüz yeniden yapımı, faz planı

> **Bu raporun izi:** [F1 durum tespiti](F1_MEVCUT_DURUM_TESPITI_2026-09-13.md) · [Studio F0–F15](../../milestones/studio-f0-f15.md) · [kaynak görev promptu](../../../promts/CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md)
>
> Tarihsel rapor. Güncel durum için [MEMORY_INDEX](../../../MEMORY_INDEX.md) kullanılır.


> **Bu dosya çalışan plandır.** Yeni bir oturum açıldığında sıra buradan
> alınır. Giriş noktası her zaman `MEMORY_INDEX.md`, sonra bu dosya.
> Kaynak görev: `CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md`.
> Mevcut durum tespiti: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

Oluşturuldu: 2026-09-13 · **F0–F7 tamamlandı, F8 sırada (onay bekliyor).**
Güncel durum için bölüm 7 (İlerleme kaydı).

---

## 1. Bu planın dayandığı kullanıcı kararları

**2026-09-13, kullanıcı:**

1. Faz sırası serbest; uygun görülen sıra uygulanır, fakat **yazılı plan
   şart** — bu dosya odur.
2. **Geriye dönük veri uyumluluğu aranmıyor.** Bugüne kadar toplanan veri test
   amaçlıydı; yeni arayüzde görünmesi gerekmiyor.
3. **Mevcut veri silinmeyecek.** İleride test amacıyla kullanılabilir.
   Dokunulmaz, taşınmaz, dönüştürülmez.

Bu üç karar planı kökten sadeleştirir: göç kodu, çift okuma yolu, legacy
dönüştürücü ve "eski etiket yeni sürüme nasıl taşınır" sorusu **kapsam
dışıdır**.

---

## 2. Bu planın mimari kararları

### K-1 · Yeni arayüz ayrı bir pakettir: `kinecapture/studio/`

Mevcut `kinecapture/gui/` **silinmez ve bozulmaz.** Yeni arayüz yanına
kurulur:

```
src/kinecapture/studio/
    services/     saf Python · backend'e tek giriş · Qt import ETMEZ
    viewmodels/   saf Python · durum, komut, biçimlendirme · Qt import ETMEZ
    views/        PySide6 · yalnız çizim ve olay yönlendirme
    theme/        tokens.json + QSS üretici
    app.py        yeni kabuk
```

**Neden yeni paket, yerinde yeniden yazım değil:**

- Eski uygulama çalışır kalır; kullanıcı geliştirme boyunca eski verisine
  eski ekrandan bakabilir. Karar 3'ün pratik karşılığı budur.
- `gui/` içindeki 12 874 satır sayfa/widget kodu yeni katman ayrımına
  uymuyor; yerinde dönüştürmek her fazda yarı-taşınmış bir ağaç bırakırdı.
- WinUI 3'e geçilirse taşınacak şey tam olarak `services/` + `viewmodels/`
  olur; sınır fiziksel olarak görünür kalır.

Çalıştırma: `python -m kinecapture` **yeni** arayüzü açar (F2'den itibaren),
`python -m kinecapture --legacy-gui` eskisini açar. F15'te eski arayüz
"eski veri görüntüleyici" olarak belgelenir; **silinmez**.

### K-2 · Yeni arayüz yalnız yeni veri sözleşmesini okur

| Okunan | Okunmayan |
|---|---|
| `raw/` + `take.json` (capture policy ≥ 2) | eski canlı `skeleton.jsonl` |
| `derived/processing/run_<id>/` | `annotations/segments.json` |
| `annotations/processing/run_<id>.json` | eski `releases/` |
| `identity.sqlite3`, `project.json`, `label_schema.json` | eski `activity_intervals` |

Bir take'in yeni arayüzde görünme şartı: `raw/` altında işlenebilir bir kaynak
olması. Eski take'ler listede **"eski biçim · yeni arayüz desteklemiyor"**
satırı olarak görünür, açılmaz, silinmez. Uydurma dönüştürme yok.

`identity/`, `dataset/workspace.py`, `domain/`, `features/`, `core/` olduğu
gibi kullanılır — hepsi zaten Qt'siz.

### K-3 · Etiket sözleşmesi tek: canonical sidecar

Yeni arayüzün yazdığı tek etiket dosyası
`annotations/processing/run_<id>.json` (schema 1.0.0, kaynak fingerprint +
SVO pozisyonu + kamera timestamp, **inclusive** aralık). `segments.json` ne
okunur ne yazılır ne dönüştürülür.

Sidecar'ın bugünkü şeması yalnız `samples[].start/end` + `errors[]` taşıyor.
Hareket sınıfı, hata sınıfı, eklem rolleri ve `reviewed_at` alanları F8'de
**toplamsal olarak** eklenecek → canonical annotation **1.1.0**.

### K-4 · Dışa aktarım yeni yoldan üretilir

Mevcut `export/release.py` eski modele (stream konumu + `segments.json`)
bağlı; **değiştirilmez**, eski arayüzde kalır. Yeni arayüz için
`export/canonical.py` yazılır: girdisi `ReviewDataset` + canonical sidecar,
çıktısı staging → atomik yayın, manifestte `run_<id>` + anotasyon revizyonu.
`features/` katmanı aynen yeniden kullanılır.

### K-5 · Performans bütçeleri kabul kapısıdır

Her fazın sonunda ilgili bütçe **ölçülür**; ölçüm raporlanmadan faz kapanmaz.
Bütçeler promptun Bölüm 5 tablosudur. F1'de ölçülen başlangıç değerleri
karşılaştırma taban çizgisidir.

### K-6 · Ölçüm ve kanıt kuralı

Her faz sonunda: gerçekten çalıştırılan komut + sonucu, ekran görüntüsü,
ölçüm tablosu. Çalıştırılmamış test "geçti" yazılmaz. Donanım gerektiren
doğrulama ayrıca işaretlenir.

---

## 3. Faz sırası ve gerekçesi

F1'de ölçülen darboğazlar sırayı belirledi. **Kritik yol:**
kabuk → backend eklentileri → etiketleme → işleme → yakalama → kütüphane.

Promptun orijinal sırasından iki sapma var ve ikisi de ölçüme dayanıyor:

1. **Backend toplamsal ekleri öne alındı (yeni F3).** Timeline'ın 292 ms'ten
   16 ms'e inmesi için çok çözünürlüklü özete, 3B görünümün offline veriye,
   kütüphanenin thumbnail'e ihtiyacı var. Bunlar sonra yapılırsa F8/F9/F7
   iki kez yazılır.
2. **Etiketleme (F8), Yakalama (F5) ve Kütüphane (F7) ile birlikte ortaya
   alındı** ama sırası Verileri Hesapla'dan (F6) *sonra*: etiketlenecek
   sürümü üreten ekran önce gelmeli, yoksa F8 elle üretilmiş fixture'larla
   test edilir.

| Faz | İçerik | Bitti sayılma ölçütü | Bağımlılık |
|---|---|---|---|
| ~~F0~~ | Hafıza politikası + `MEMORY_INDEX.md` | ✅ 2026-09-13 (`314eb8b`) | — |
| ~~F1~~ | Mevcut durum tespiti ve ölçüm | ✅ 2026-09-13 (`62b04b8`) | — |
| ~~F2~~ ✅ | Temel: `studio/` katmanları, `tokens.json` + QSS üretici, kabuk, gezinme, tema, pencere durumu; `test_raw_capture_fields.py` onarımı | Uygulama açılıyor, 8 sekme geziliyor, iki tema tutarlı, Qt-bağımsızlık testi geçiyor, 5 kırmızı test yeşil, ekran görüntüsü | — |
| ~~F3~~ ✅ | Backend toplamsal ekleri (processing **1.1.0**) | Headless testler geçiyor, memmap/özet/thumbnail ölçüldü, eski `run_` dizinleri hâlâ okunabiliyor | F2 |
| ~~F4~~ ✅ | Projeler · Katılımcılar · Ayarlar | Sanallaştırılmış listeler, 1000 kayıtla takılma yok (ölçüm), ayarlar atomik, geçersiz değer kilitlemiyor | F2 |
| ~~F5~~ ✅ | Yakalama | Mock ile tam tur; hafif 2B pose kaplaması; anchor gösterilen kareye yazılıyor; önizleme/kayıt kaybı ayrı | F3 |
| ~~F6~~ ✅ | Verileri Hesapla | İşleme ayrı süreçte, ilerleme gerçek, iptal/duraklat/restart çalışıyor, GUI bloklanmıyor | F3 |
| ~~F7~~ ✅ | İşlenen Videolar | Kütüphane, thumbnail önbelleği, sürüm karşılaştırma, filtreler | F3, F6 |
| **F8** | Etiketleme — timeline, senkron, canonical sidecar 1.1.0 | **Bütçeler ölçülüp raporlandı** (≤8 ms boşta, ≤16 ms timeline, ≤50 ms scrub, ≤1,5 GB) | F3, F7 |
| **F9** | Etiketleme — 3B iskelet (`QOpenGLWidget`, offline veri) | OpenGL çizim, timestamp senkronu, kamera kalıcı, 60 Hz korunuyor | F8 |
| **F10** | Sporcu seçimi ve belirsiz aralık onayı | Sessiz fallback yok, onay revizyonu yazılıyor | F8 |
| **F11** | Veri Seti + Dışa Aktarım (`export/canonical.py`) | Sürüm ve onay bağı manifestte, onaysız veri sessizce çıkmıyor | F8, F10 |
| **F12** | Yardımcı pencereler (6 adet) | Altısı da çalışıyor, ayrılabiliyor, ana akışı engellemiyor | F2 |
| **F13** | Dayanıklılık: çöküş/kurtarma, disk dolu, süreç ölümü, hata dili | Kurtarma senaryoları testte geçiyor | F6, F8 |
| **F14** | Cila: klavye, DPI 125/150/200, erişilebilirlik, boş/hata/yükleniyor | Kontrol listesi tamam, üç DPI'da kırpılma yok | tümü |
| **F15** | Uçtan uca deneme + final performans raporu | Tam tur çalıştı, bütçe tablosu gerçek ölçümle doldu | tümü |

Her faz kendi commit'ini alır. `pyside6-yeni-backend-arayuzu` dalında
çalışılır.

---

## 4. Faz ayrıntıları

### F2 — Temel

**Yapılacak**
- `studio/` paket iskeleti; `services/` ve `viewmodels/` Qt'siz.
- `studio/theme/tokens.json`: tek gerçek kaynak. Ad biçimi WinUI kaynak adı
  gibi: `KcSurfaceBase`, `KcSurfaceRaised`, `KcAccentPrimary`,
  `KcStatusRecording/Warning/Live/Selection`, `KcSpacing*`, `KcRadiusControl`,
  `KcFontMono`. Koyu birincil, açık ikinci değer kümesi.
- `studio/theme/generator.py`: `tokens.json` → QSS. Widget içinde literal
  renk/ölçü **yasak**; bunu doğrulayan test.
- Kabuk: altta gezinme şeridi (**Projeler · Yakalama · Verileri Hesapla ·
  İşlenen Videolar · Etiketleme · Veri Seti · Dışa Aktarım · Ayarlar**),
  üstte ince bağlam şeridi, sağda kapanabilir inceleme paneli.
- Pencere durumu kalıcı: `QSettings` yerine mevcut atomik JSON yolu
  (`core/jsonio`) ile `~/.kinecapture/window_state.json`.
- İkon seti: Lucide (ISC lisanslı) SVG'leri paket verisi olarak; tek çizgi
  kalınlığı, tema rengine boyanır. Lisans dosyası taşınır.
- Hata dili altyapısı: `KineCaptureError.code/remedy/details` zaten var;
  görünen katman + "Ayrıntılar" bileşeni yazılır.
- **K4a onarımı**: `tests/test_raw_capture_fields.py` stub'ı `sl.ERROR_CODE`
  sağlayacak biçimde düzeltilir (uygulama kodu değişmez).

**Ölçüt** · soğuk açılış ≤3 s (taban 0,96 s), Qt-bağımsızlık testi geçiyor,
8 sekme geziliyor, koyu/açık tema, 1120×700 ve 1600×980'de kırpılma yok.

### F3 — Backend toplamsal ekleri · processing 1.1.0

Hepsi **toplamsal**; ham veri değişmez, mevcut dosya adları korunur, eski
`run_` dizinleri okunmaya devam eder.

| Ek | Nerede | Neden |
|---|---|---|
| `arrays/*.npy` (memmap) + mevcut `arrays.npz` | `processing/jobs.py` | F1: 135 MB tam yükleme yerine 0,27 MB pencere |
| `summary.npz` çok çözünürlüklü min/max decimation | yeni `processing/summary.py` | F1: timeline 292 ms → hedef ≤16 ms |
| `thumbs/` (başlangıç/orta/son + N ara kare, WebP) | `processing/jobs.py` | F7 kütüphanesi, liste kaydırırken üretim yapılmaz |
| `ReviewDataset.depth_at()` | `processing/review.py` | F9 3B görünüm; `depth/*.kcd` yazılıyor ama okuyucu yok |
| `ReviewDataset` anchor sözlük indeksi | `processing/review.py` | `position_of_anchor` doğrusal tarama |
| `job.json`: `paused`, `eta_s`, `rate_fps` | `processing/jobs.py` | F6 duraklat + gerçek tahmini süre |
| Türetilmiş özet indeksi `derived/_index.json` | yeni `dataset/summary_index.py` | F1: 1000 kayıtta 650 ms klasör taraması |

Özet indeksi **türetilmiştir**: bozulursa/silinirse taramadan yeniden
üretilir, hiçbir zaman tek doğruluk kaynağı değildir.

**Ölçüt** · `processing/` ve `dataset/` testleri geçiyor; memmap penceresi,
özet çizim süresi ve indeks okuma süresi ölçülüp raporlandı;
`PROCESSING_SCHEMA_VERSION` 1.1.0 ve `MEMORY.md`'ye yazıldı.

### F4 — Projeler · Katılımcılar · Ayarlar

`QAbstractItemModel` + `QTableView`/`QListView`. Arama ve filtre modelde.
Ayarlar altı grup (Kayıt · Önizleme · İşleme · Veri · Görünüm · Gelişmiş),
her ayarın yanında bir cümlelik açıklama, atomik yazım, geçersiz değer
uygulamayı kilitlemez. **İşleme** grubu `ProcessingConfig` varsayılanlarını
yüzeye çıkarır.

**Ölçüt** · 1000 kayıtla kaydırmada takılma yok (kare süresi ölçülür),
model dolumu ≤10 ms, ayarlar diske atomik.

### F5 — Yakalama

Büyük RGB önizleme + hafif 2B pose kaplaması (`preview.pose.CpuPosePreview`),
"tanılama amaçlı, metrik iskelet değil" notu. Kayıt modu seçimi. **Kişi
seçimi `set_subject_anchor` ile**, gösterilen karenin timestamp/ordinal/
çözünürlük/nokta/bbox bilgisiyle. Taşıma çubuğu, disk kalan süre, üç ayrı
yerde kayıt göstergesi. Metrikler saniyede 2–4 kez; **önizleme kaybı ile
kayıt kaybı ayrı**. Kayıt bitişi: "Ham kayıt kaydedildi · İskelet bekliyor" +
`Şimdi işle` / `Kuyruğa ekle`.

**Ölçüt** · mock ile tam tur; anchor dosyası doğru yazılıyor (test);
GUI açıkken kayıt kuyruğu kaybı 0 (ölçüm).

### F6 — Verileri Hesapla

İş kuyruğu ekranı. İşleme `QProcess` ile **ayrı süreç** (`python -m
kinecapture.processing`); GUI hiç bloklanmaz. İlerleme `job.json`'dan;
toplam bilinmiyorsa yüzde uydurulmaz. Tahmini süre ısınmadan sonraki gerçek
hızdan. Başlat / duraklat / iptal / yeniden dene. **"İptal ham kaydı silmez"**
ekranda yazılı. Yeni kayıt başlayınca çalışan iş güvenli sınırda duraklar.
Kapsam uyuşmazlığı açıkça bildirilir.

**Ölçüt** · mock take'te başlat→duraklat→devam→iptal→restart turu;
GUI kare süresi işleme sırasında ≤8 ms (ölçüm).

### F7 — İşlenen Videolar

Tamamlanmış `run_<id>` kütüphanesi; satır başına katılımcı, tarih, süre,
kaynak kapsamı, kişi sayısı, sporcu durumu, QC işaretleri, model özeti.
Thumbnail'ler F3'te üretilmiş; liste yalnız okur. Aynı take'in sürümleri yan
yana karşılaştırılır. Buradan etiketlemeye geçilir.

**Ölçüt** · 500 sürümle kaydırmada düşen kare yok (ölçüm), thumbnail
üretimi liste kaydırırken tetiklenmiyor (test).

### F8 — Etiketleme: timeline ve senkron · **en kritik faz**

- Timeline sıfırdan yazılır: tek `paintEvent`, yalnız görünür aralık,
  F3'teki çok çözünürlüklü özetten çizim, statik katmanlar pixmap
  önbelleğinde, üstte yalnız playhead + seçim.
- Şeritler: video · iskelet güvenilirliği · QC · belirsiz kişi · anotasyon ·
  olay. Başlıklar solda sabit.
- Senkron **kare indeksi üzerinden değil, kaynak timestamp'i üzerinden**.
- Video proxy'den, önceden ayrılmış tamponla; kare başına yeniden alokasyon
  yok.
- Diziler memmap; yalnız görünür aralık okunur.
- Etkileşim: sürükleme, Ctrl+tekerlek zoom (playhead çapa), orta tuş pan,
  `,`/`.` kare adımı, aralık seçip etiketleme, snap.
- Sürüm bağı görünür; sürüm değiştirilebilir; yeni sonuç gelince uyarı,
  otomatik taşıma yok.
- Etiketler canonical sidecar **1.1.0**'a yazılır (sınıf, eklem rolleri,
  `reviewed_at` eklenir).

**Ölçüt (kabul kapısı)** · boşta kare süresi ≤8 ms · timeline yeniden çizimi
≤16 ms (60 dk tam görünüm) · scrub ≤50 ms · zoom/pan'da düşen kare yok ·
60 dk oturumda bellek artışı ≤1,5 GB. Hepsi ölçülüp tabloya yazılır.

### F9 — Etiketleme: 3B iskelet

`QOpenGLWidget`, VBO'ya yüklenen köşe verisi, kare başına sahne yeniden
kurulmuyor. Offline iskelet + (varsa) offline derinlik. Döndürme/zoom/pan,
kamera açısı kalıcı, sıfırlama kısayolu. Video · 2B · 3B · timeline **her
zaman aynı karede**.

### F10 — Sporcu seçimi ve belirsiz aralık onayı

Aday kişi kartları (başlangıç/orta/son görüntü, görünme süresi, kopma
sayısı), başlıklar "Kişi 1/2", teknik tracker kimliği küçük ayrıntı.
**Yalnız belirsiz aralıklar sorulur**: "Aynı sporcu" / "Diğer kişi" /
"Bu bölümde sporcu yok". Sessiz en-yakın-kişi fallback'i yok. Onay
`subject association` revizyonu olarak yazılır.

### F11 — Veri Seti + Dışa Aktarım

Yeni `export/canonical.py`. Kişi onayı eksik veya kapsamı doğrulanmamış veri
sessizce dışa aktarılmaz. Her paket `run_<id>` + anotasyon revizyonunu taşır.
`features/` katmanı aynen kullanılır.

### F12 — Yardımcı pencereler

Log Konsolu · Tanılama · Cihaz Bilgisi · Kaynak Denetimi · Köken · Ham
Parametreler. Modeless, ikinci monitöre taşınabilir, ana akışı engellemez.
Veri kaynakları `core/diagnostics.py`, `job.json`, `checksums.json`,
`raw_capture_manifest.json` içinde zaten var.

### F13 — Dayanıklılık

Beklenmeyen istisna arayüzü çökertmez. Kapanışta çalışan iş güvenli
sonlanır, yarım çıktı yayımlanmaz. Çöküş sonrası: yarım işler
`failed`/`partial`, ham kayıtlar sağlam, etiketler kayıpsız. Backend süreci
ölürse yeniden başlatma sunulur. Kamera koparsa kayıt güvenli kapanır. Uzun
yol (WinError 3) yüzeye çıkmadan ele alınır. Otomatik kurtarma testleri.

### F14 — Cila

Klavye ile tam erişim, görünür odak, DPI 125/150/200, renk+ikon+metin üçlüsü,
boş/hata/yükleniyor durumları, kontrast kontrolü.

### F15 — Uçtan uca + final rapor

Yakalama → işleme → kütüphane → etiketleme → dışa aktarım tam turu mock ile;
bütçe tablosu gerçek ölçümlerle doldurulur; donanım gerektiren maddeler
ayrıca işaretlenir.

---

## 5. Kapsam dışı (açıkça)

- Eski `segments.json`, eski `releases/`, eski `activity_intervals` için göç
  veya dönüştürme. **Kullanıcı kararı 2.**
- Mevcut verinin silinmesi, taşınması, yeniden yazılması. **Kullanıcı
  kararı 3.**
- Eski `gui/` paketinin silinmesi veya yeniden yazılması.
- Gerçek ZED donanımıyla doğrulama (ayrı, kullanıcı eşliğinde yapılacak).
- Kurulum paketi / installer.
- WinUI 3 geçişinin kendisi.

## 6. Değişmez kurallar (her fazda geçerli)

- Kullanıcı verisi silinmez, üzerine yazılmaz; ham kayıt değişmezdir.
- `viewmodels/` ve `services/` Qt import etmez; bunu doğrulayan test her
  fazda çalışır.
- Token dışında literal renk/ölçü yazılmaz.
- GUI thread'inde disk ve hesaplama yok.
- Önizleme kaybı ile kayıt kaybı ayrı sayılır.
- Ölçülmemiş performans iddia edilmez.
- Test edilmemiş özellik tamamlanmış sayılmaz.
- Yalnız `KineSynth` environment'ı; yeni paket kurulmaz (F2'deki Lucide SVG
  dosyaları paket verisidir, bağımlılık değildir).

## 7. İlerleme kaydı

| Faz | Durum | Tarih | Commit |
|---|---|---|---|
| F0 | ✅ | 2026-09-13 | `314eb8b` |
| F1 | ✅ | 2026-09-13 | `62b04b8` |
| F2 | ✅ | 2026-09-13 | `2f7108c` |
| F3 | ✅ | 2026-09-13 | `add23cd` |
| F4 | ✅ | 2026-09-13 | `f869940` |
| F5 | ✅ | 2026-09-13 | `1cc99ce` |
| F6 | ✅ | 2026-09-13 | `1b2db3f` |
| F7 | ✅ | 2026-09-13 | `3278c87` |
| F8 | ⏳ sırada | | |
| F9–F15 | — | | |

### F2 sonucu (2026-09-13)

**Teslim edilen**

- `kinecapture/studio/` üç katmanlı olarak kuruldu: `services/`, `viewmodels/`,
  `views/`, `theme/`. Eski `gui/` paketine dokunulmadı.
- `theme/tokens.json` (tek gerçek kaynak) + `theme/studio.qss.tmpl` +
  `theme/generator.py`. 41 token, iki tema, aynı renk token kümesi.
- Kabuk: üstte bağlam şeridi, ortada tembel kurulan sayfa yığını, sağda
  kapalıyken **0 piksel** yer kaplayan inceleme paneli, altta 8 adımlı gezinme
  şeridi. Ctrl+1…8, Ctrl+PgUp/PgDn, F9.
- İki katmanlı hata dili: görünen `Message` + "Ayrıntılar" altında kod ve
  teknik alanlar. `sys.excepthook` istisnayı mesaja çeviriyor, arayüz ayakta
  kalıyor.
- Pencere durumu (boyut, tema, açık sekme, panel) `core/jsonio` ile atomik
  yazılıyor; bozuk dosya varsayılana düşüyor, açılışı engellemiyor.
- İkonlar: **Lucide 0.462.0 (ISC)**, 25 SVG + lisans metni paket verisi olarak.
  Tek çizgi kalınlığı, tema rengine boyanıyor, DPI'ya göre render ediliyor.
- Launcher: `python -m kinecapture` **Studio**'yu açar, `--legacy-gui` eskisini.
- F1'de bulunan 5 kırmızı test (`test_raw_capture_fields.py`) onarıldı; stub
  artık gerçek SDK sözleşmesini taklit ediyor ve başarısız retrieval için yeni
  bir regresyon testi eklendi.

**Ölçülen**

| Ölçüm | Hedef | Sonuç |
|---|---|---|
| Soğuk açılış (gerçek süreç, `windows` platformu, 3 koşu) | ≤ 3 s | **1,29 / 1,34 / 1,29 s** ✓ |
| Kabuk kurulumu + `show()` (süreç içi) | — | 806 ms |
| 1120×700 · 1366×768 · 1600×980, iki tema | kırpılma yok | `minimumSizeHint` hepsinde sığıyor ✓ |
| Sayfa kurulumu | tembel | açılışta 1 sayfa, gezildikçe artıyor ✓ |
| Qt-bağımsızlık | geçmeli | alt süreçte PySide6 import'u engelli, `services`/`viewmodels`/`theme` çalışıyor ✓ |

**Bilinçli sapmalar**

- `offscreen` Qt platformu **sıfır font ailesi** bildiriyor; oradaki her metin
  ölçümü anlamsız (tofu kutuları gerçek metinden geniş). Yerleşim testleri
  offscreen'de atlanıyor, `windows` platformunda çalıştırılıyor. Yeşil ama
  hiçbir şey ölçmemiş bir test yerine dürüst bir skip tercih edildi.
- Gezinme şeridi dar ekranda etiketleri bırakıp yalnız ikona düşüyor; adımı
  kaydırmanın arkasına gizlemek iş akışını kısa gösterirdi.

### F3 sonucu (2026-09-13) — processing **1.1.0**

**Teslim edilen** (hepsi toplamsal; ham veri değişmedi, eski sürümler okunuyor)

| Ek | Modül |
|---|---|
| Bellek eşlemeli diziler (`arrays/*.npy` + `index.json`) | `processing/arrays.py` |
| Çok çözünürlüklü timeline özeti (min/max piramidi) | `processing/summary.py` |
| Önizleme görüntüleri (WebP, seek ile) | `processing/thumbnails.py` |
| İndeksli + önbellekli offline derinlik erişimi | `processing/depth.py` |
| `job.json`: duraklat / `paused_s` / `rate_fps` / `eta_s` | `processing/jobs.py` |
| Anchor sözlük indeksi, `window()`, tembel açıcılar | `processing/review.py` |
| Türetilmiş proje indeksi (`cache/take_index.json`) | `dataset/summary_index.py` |
| Başlık-yalnız chunk okuma | `recording/rgbd_archive.py` |

**Ölçülen** (60 dk / 60 FPS / BODY_38; ayrıntı `MEMORY.md` 6AA)

| Ölçüm | Önce | Sonra |
|---|---|---|
| Dizi yazımı | 5,05 s | **0,13 s** |
| 600 karelik pencere | 403,7 ms | **13,5 ms** (sonraki 0,14 ms) |
| Timeline lane okuma | yok | **0,007 ms** (ilk 7,9 ms) |
| Thumbnail (13 adet) | yok | **131 ms**, uzunluktan bağımsız |
| `position_of_anchor` ×1000 | doğrusal | **0,7 ms** |
| Proje indeksi, 1000 kayıt | 1247 ms/yenileme | **154 ms** (0 yeniden okuma) |

**Dürüstlük notları**

- 154 ms bir UI karesi değildir; indeks F4/F7'de worker thread'de çalışacak.
  İndeks işi *sık çalıştırılabilecek kadar* küçültür, sıfırlamaz.
- İlk sezgim yanlıştı: thumbnail için sıralı okuma seek'ten **yavaş** çıktı
  (305 ms / 131 ms) ve uzunlukla büyüyordu. Ölçüm sonrası seek'e geçildi.
- İndeks yapısal değişikliği algılar, çalışan işin ilerlemesini değil.
- Yeni sürümlerde `arrays.npz` yazılmıyor; 1.0.0 sürümleri `ArrayStore`
  üzerinden okunmaya devam ediyor ve pencere okumasının ucuz olmadığı
  `is_memmapped=False` ile söyleniyor.
- `long_path` her yol için ayrı karar verir: kısa bir ebeveynden özyinelemeli
  glob, sınırı aşan çocuğu **sessizce** bulamaz. Yol kademeli kurulmalı
  (ayrıntı `MEMORY.md` 6AA). Testlerde bu tuzağa düşüldü ve düzeltildi.
- Uzun yolda proxy video yazılamadığı için o durumda önizleme testi açıkça
  skip ediliyor; kısa yolda tam çalışıyor.


### F4 sonucu (2026-09-13)

**Teslim edilen**

- **Giriş kapısı**: ilk kurulum (tek Sistem Sahibi), giriş, self-registration,
  zorunlu parola değişimi. Çalışma alanı kapının arkasında; giriş yapılmadan
  hiçbir sayfa kurulmuyor. Parola hiçbir yerde saklanmıyor, kullanıldığı anda
  alandan siliniyor; yalnız kullanıcı adı hatırlanıyor.
- **Projeler ekranı**: üç sanallaştırılmış liste (proje → katılımcı → oturum),
  arama, sıralama, yeni proje, katılımcı ekle. Sayımlar F3'teki türetilmiş
  indeksten geliyor ve indeks **worker thread'de** yenileniyor.
- **Ayarlar ekranı**: altı grup, her ayarın yanında ne işe yaradığını söyleyen
  bir cümle, pahalı seçeneklerde ölçülmüş maliyet notu. Doğrulama alan bazlı;
  **bir alan geçersizse hiçbiri yazılmıyor**; eski değer yürürlükte kalıyor.
- `viewmodels/tasks.py` `TaskRunner` arayüzü + `views/tasks.py` `QtTaskRunner`:
  viewmodel Qt'yi görmeden iş parçacığı kullanabiliyor, testler `InlineRunner`
  ile senkron çalışıyor.
- `views/models.py`: tek `QAbstractTableModel` + arama proxy'si, tüm listeler
  için.

**Ölçülen** (1400×800 tablo, 9 sütun, `windows` platformu)

| Ölçüm | F1 tabanı (QTableWidget) | F4 |
|---|---|---|
| 1000 satır doldurma | 36 ms | **43 ms** |
| 5000 satır doldurma | 183 ms | **48 ms** (kare sayısından bağımsız) |
| 1000 satırda arama | — | 14 ms |
| 5000 satırda arama | — | 74 ms |
| Kaydırmada viewport çizimi (1000 satır) | 15 ms | **21 ms** |
| Soğuk açılış | — | değişmedi |
| 1120×700 · 1366×768 · iki tema | — | `minimumSizeHint` 880×393, sığıyor |

**Dürüstlük notu:** Python model, C++ `QTableWidget`'tan **çizimde daha
pahalı** (21 ms / 15 ms): her hücre için Qt Python'a giriyor. Karşılığında
doldurma maliyeti satır sayısından bağımsız ve hücre başına nesne
üretilmiyor. "1000 kayıtta takılma yok" ölçütü karşılanıyor, fakat sayı
budur — 21 ms tam viewport çizimi, sürükleme sırasında ~45 Hz.

**Ölçüm sonrası düzeltilen üç şey**

1. `view.setSortingEnabled(True)` proxy'yi her veri sıfırlamasında yeniden
   sıralatıyordu ve sıralama her karşılaştırmada Python'a giriyordu: 1000
   satır doldurma **224 ms**. Sıralama modelin içine alındı (önbelleklenmiş
   anahtarlar üzerinde tek `list.sort`) → **42 ms**.
2. Arama hücre başına `data()` çağırıyordu: 5000 satırda **308 ms**. Satır
   başına birleştirilmiş küçük harfli metin önbelleğe alındı → **74 ms**.
3. Yanıtlanmayan roller tek bir küme aramasıyla erkenden elenince çizim
   24 ms → 21 ms.

**Not:** F2'de yazılan kabuk GUI testleri giriş kapısından önce yazılmıştı ve
kapı eklenince kırıldı (çalışma alanı görünmüyor). Fixture giriş yapacak
şekilde güncellendi; kapının kendisi ayrı testlerle kapsanıyor.


### F5 sonucu (2026-09-13)

**Teslim edilen**

- Büyük RGB önizleme (`views/preview.py`): kare başına yeniden alokasyon yok —
  çözünürlük başına bir tampon ayrılıp içine yazılıyor, `QImage` o tamponun
  kopyasız görünümü. Köşe yuvarlatma, gölge, çerçeve efekti yok.
- Hafif 2B pose kaplaması ve **ne olmadığını söyleyen not**: kadraj kontrolü
  içindir, metrik iskelet değildir, katılımcı kimliği taşımaz.
- **Kişi seçimi gösterilen kareye bağlanıyor**: tıklama kaynak görüntü
  pikseline çevriliyor, anchor kamera timestamp'i + kaynak çözünürlüğü + nokta
  + bbox ile ham kaydın yanına yazılıyor. İki kişi örtüşüyorsa **seçim
  yapılmıyor** — yanlış kişi, tekrar sormaktan kötüdür.
- İki kayıt modu, ikincisi maliyetiyle birlikte işaretli.
- Taşıma çubuğu, uyarı şeridi (en acili üstte), ve **ayrı** sayaçlar:
  `Kayıt kaybı` ile `Önizleme kaybı` hiçbir yerde toplanmıyor.
- Kayıt durumu üç yerde birden: düğme, görüntü kenarındaki ince kırmızı
  çerçeve, pencere başlığı.
- Kayıt bitişi: *"Ham kayıt kaydedildi · İskelet bekliyor"*. Kişi bulunamadı
  diye kayıt başarısız gösterilmiyor.

**Ölçülen** (mock kaynak, 4 sn kayıt, `windows` platformu)

| | GUI kapalı | GUI açık |
|---|---|---|
| 60 FPS · kaydedilen / **kayıt kaybı** | 242 / **0** | 241 / **0** |
| 200 FPS · kaydedilen / **kayıt kaybı** | 749 / **0** | 764 / **0** |
| GUI kare işleme süresi | — | **medyan 0,09 ms · p95 3,7 ms** |
| Önizleme kaybı (veri kaybı değil) | 55 | 1–3 |

GUI kare maliyeti 8 ms bütçesinin çok altında ve kayıt kaybı GUI açıkken de
kapalıyken de **sıfır**.

**Ölçüm sırasında bulunan iki gerçek hata**

1. **Mock backend hız sınırlaması olmadan çalışıyordu.** Studio onu
   `real_time=False` ile kuruyordu; kaynak istenen 60 FPS yerine ~350 FPS
   üretip 120 karelik yazıcı kuyruğunu taşırıyor ve **45–96 kare kaybına**
   yol açıyordu. Take doğru biçimde `partial` kalıyordu — yani sistem doğru
   davranıyordu, ölçüm ortamı yanlıştı. `real_time=True` verildi; kayıp sıfıra
   indi. İlk ölçümüm "GUI kayıt kaybına yol açıyor" gibi okunabilirdi; A/B
   yapılınca kaybın GUI'siz de aynı olduğu görüldü.
2. **Ayarlar `backend`'i düz metin olarak saklıyordu** (F4'te benim
   eklediğim hata). Değer kaydedilirken görünür bir sorun çıkmıyor, fakat
   tercih dosyası yazılırken `'str' object has no attribute 'value'` ile
   sessizce başarısız oluyordu. Tip dönüşümü eklendi, regresyon testi yazıldı.

**Ayrıca:** radyo/onay kutusu göstergeleri platformun açık palet için
çizdiği hâliyle koyu temada görünmüyordu; token tabanlı gösterge stili eklendi.

**Kapsam dışı kalan:** gerçek ZED ile 60 FPS ölçümü. Buradaki sayılar mock
kaynakla alınmıştır ve donanım doğrulaması yerine geçmez.


### F6 sonucu (2026-09-13)

**Teslim edilen**

- İşleme **ayrı süreçte**: `python -m kinecapture.processing` bir alt süreç
  olarak başlatılıyor. Gerekçe sırayla: SDK orada açılıyor (orada bir çökme
  işi kaybeder, burada uygulamayı kaybederdi), hiçbir davranışı bir çizimi
  bloklayamaz, ve işletim sistemi onu duraklatıp sonlandırabilir — "iptal"in
  yirmi dakikadır süren bir iş için anlamı budur.
- İlerleme **`job.json`'dan okunuyor**. Ekranla diskteki kayıt birbirinden
  ayrılamaz; ikinci bir kopya tutulmuyor.
- **Yüzde uydurulmuyor**: kaynak kare sayısı bildirilmemişse
  *"İşlenen 412 kare"*, bildirilmişse *"İşlenen 412 / doğrulanmış 900 kare"*.
  Model ısınmadan tahmini süre verilmiyor (*"süre hesaplanıyor"*).
- Başlat · duraklat · devam · iptal · yeniden dene. **Duraklatma** alt süreci
  askıya alıyor (psutil ortamda mevcut); desteklenmeyen bir makinede bunu
  söyleyip iptali öneriyor.
- **"İptal ham kaydı silmez"** düğmenin yanında yazılı ve testle sabit.
- Kapsam uyuşmazlığı **"tamamlandı" denmiyor**: `partial` ayrı bir durum ve
  her bulgu kod yerine cümleyle gösteriliyor.
- Canlı kayıt başlayınca çalışan işler duraklıyor, kayıt bitince devam
  ediyor (`take_finished` → `resume_all`).
- Kapanışta her alt süreç sonlandırılıyor; yarım çıktı yayımlanmıyor.

**Ölçülen** (mock kaynak, 363 karelik kayıt, `windows` platformu)

| Ölçüm | Sonuç |
|---|---|
| Kayıt → işleme → tamamlandı | ✓ `complete`, 363/363 kare, bulgu yok |
| Duraklat → ilerleme durdu mu | ✓ sayaç hareket etmedi |
| Devam → tamamlandı | ✓ baştan başlamadan bitti |
| **İşleme sürerken GUI kare süresi** | **medyan 2,88 ms · p95 7,72 ms** (bütçe 8 ms) |
| İptal sonrası ham kayıt | ✓ dosya listesi değişmedi |

**Not:** `psutil` ortamda zaten kurulu ve duraklatma onu kullanıyor; bağımlılık
olarak **eklenmedi**, yokluğunda arayüz bunu söyleyip iptali öneriyor.


### F7 sonucu (2026-09-13)

**Teslim edilen**

- Tamamlanmış `run_<id>` sürümlerinin kütüphanesi. Her satır: katılımcı, tarih,
  süre, kare, model, durum, sürüm sayısı, etiket var mı.
- **Bir satır hiçbir şey açmıyor.** Sürümü açmak içindeki her dosyanın
  checksum'ını doğrulamak demek — etiketlemeden önce doğru bir bedel, liste
  kaydırırken yanlış. Satırlar yalnız türetilmiş indeksten ve her `run`'ın
  kendi `job.json`'undan kuruluyor.
- Önizleme görüntüleri F3'te işleme anında üretilmişti; ekran yalnız dosya
  okuyor. Liste kaydırırken **hiç** üretim yapılmıyor (ölçüldü).
- Aynı kaydın birden fazla sürümü varsa **yan yana** gösteriliyor: kapak
  görüntüsü, model, kare sayısı, kapsam durumu.
- Altı filtre: tümü · etiketlemeye hazır · kişi seçilmemiş · kapsam
  doğrulanamadı · etiketlenmiş · birden fazla sürüm. Filtre değişimi projeyi
  **yeniden okumuyor** (testle sabit).
- "Etiketle" seçili sürümü F8'e taşıyor. Kapsamı doğrulanamamış bir sürüm
  etiketlenebilir, fakat **önce uyarı çıkıyor** — bir saatlik iş, uyarıyı hak
  eder.

**Ölçülen** (1200×700 tablo, `windows` platformu)

| Ölçüm | 100 sürüm | 500 sürüm |
|---|---|---|
| Liste doldurma | 29,4 ms | **30,7 ms** |
| Kaydırmada viewport çizimi | medyan 20,6 ms · p95 22,4 ms | medyan 20,6 ms · p95 22,8 ms |
| Arama | 4,4 ms | 8,9 ms |
| **Kaydırırken `thumbnail()` çağrısı** | **0** | **0** |

Uçtan uca: kayıt → iki kez işleme (aynı take, iki sürüm) → kütüphanede
3 sürüm, karşılaştırma şeridinde 2 kapak, "Etiketle" ile Etiketleme ekranına
geçiş — hepsi gerçekten çalıştırıldı.

**Not:** F2'de yazılan "yapılmamış ekran yer tutucu gösterir" testi her fazda
kırılıyordu; artık hangi ekranların yapılmadığını kayıttan soruyor ve bir
sonraki fazda güncellenmesi gerekmeyecek.

### F8 sonucu (2026-09-14)

**Teslim edilen — kanonik etiket katmanı (backend)**

- `processing/annotations.py`: kanonik şema **1.1.0**. Bir etiketin zamanı
  `(source_fingerprint, source_position, camera_timestamp_ns)` üçlüsüyle
  çapalanır; sınırlar **kapsayıcı**. `Correctness` türetilir, seçilmez:
  incelenmemişse `unreviewed`, sınıflı hata varsa `incorrect`, yoksa `correct`.
- `studio/services/annotation_store.py`: tek yazıcı. **Bir karar = bir geri
  alma adımı** ve doğrulama **bütün belge** üzerinde çalışır; reddedilen bir
  düzenleme hiçbir iz bırakmaz (geri alma yığınından da düşer).
- `studio/services/review.py`: bir sürümü etiketlemeye hazır açar. Hiçbir şey
  bütün kaydı belleğe almaz — kareler proxy'den tek tek, eklemler `.npy`
  bellek haritasından pencere pencere okunur.

**Teslim edilen — Etiketleme ekranı**

- Video editörü düzeni: üstte görüntü + 2B iskelet, altta zaman çizelgesi,
  yanda seçime göre değişen denetçi. Sürükleyerek aralık çiz, kenarından
  tut ve kırp, tekerlekle yakınlaş.
- **Canlı kırpma önizlemesi**: bir kenar sürüklenirken görüntü o kareye
  gider, oynatma çizgisi yerinde kalır, köşede "kare N" rozeti çıkar.
- **1–9 sayı tuşları** ilk dokuz hareket sınıfını atar; "Sınıfsızların hepsine
  uygula" bir seansın tekrarlarını tek tuşla etiketler ve **sınıfı olanı asla
  değiştirmez**.
- **"Sonraki eksik"** hâlâ bir şeyi eksik olan ilk harekete atlar ve neyin
  eksik olduğunu söyler.
- Seçili hata aralığının işaretlediği eklemler görüntüde kırmızı vurgulanır;
  düşük güvenli eklem içi boş çizilir; **tracker'ın üretmediği eklem hiç
  çizilmez** (orijine sabitlenmiş sahte iskelet yok).

**GUI geliştirirken kapatılan backend açıkları**

| Açık | Neydi | Ne yapıldı |
|---|---|---|
| 2B eklemler hiç üretilmiyordu | `FeatureContext.raw` işleme tarafında **hiç doldurulmuyordu**; `tracker_joint_positions_2d` gerçekte veri varken bile NaN çıkıyordu | `jobs.py` seçili bedenlerin bütün opsiyonel tracker alanlarını istifliyor; 2B eklemler varsayılan özellik setine girdi |
| Kaynak haritası 222 MB | 216000 karelik harita dict listesi + tuple anahtarlı indeks olarak tutuluyordu | İki `int64` dizi + sıralıysa ikili arama → **4,8 MB** |
| Tekrarlanan kare kimliği sessizce çözülüyordu | Aynı `(pozisyon, zaman)` iki kez geçerse dict'te **son satır kazanıyordu** | Belirsizlik tespit ediliyor ve çözüm **reddediliyor** |
| Hata aralığı sessizce kırpılıyordu | Hareketin tamamen dışına çizilen aralık sınır karesine sıfır uzunlukta yapıştırılıyordu | Örtüşen aralık kırpılır, **örtüşmeyen reddedilir** |
| Eklem durumu sessizce yükseltiliyordu | Eklem işaretlenince `joint_status` kendiliğinden `selected` oluyordu — yapılmamış bir inceleme kaydı | Çelişkili bileşim **reddediliyor** |
| Kütüphane var olmayan sürüm listeliyordu | İşleme önce `complete` yazıp sonra klasörü yeniden adlandırıyor; okuyucu aradaki anı görüyordu | "Tamamlandı" artık **terfi etmiş** demek; satır terfiye kadar çalışıyor görünüyor |
| İskelet akışı boşuna okunuyordu | `ReviewDataset` açılışta bütün `skeleton.jsonl`'i ayrıştırıyordu | Tembel özellik; etiketleme ekranı ona hiç dokunmuyor |

**Ölçülen** (60 dk / 60 FPS / BODY_38 = 216000 kare, 1600 px çizelge, `windows`)

| Ölçüm | Bütçe | Sonuç |
|---|---|---|
| Boşta kare (çizelge + görüntü) | ≤ 8 ms | medyan **0,38 ms** · p95 0,74 ms |
| Tarama (veri okuma + iki çizim) | ≤ 50 ms | medyan **0,64 ms** · p95 1,20 ms |
| Çizelge çizimi, 600 aralık | ≤ 16 ms | medyan **12,13 ms** · p95 14,56 ms |
| Çizelge, oynatma çizgisi hareketi | ≤ 16 ms | medyan **0,11 ms** |
| 600 karelik 3B pencere okuma | ≤ 50 ms | medyan **0,12 ms** |
| 60 dakikalık oturumda zirve RSS | ≤ 1,5 GB | **139 MB** |

Çizelge çizimi F1 tabanında 292–323 ms idi; per-bin `fillRect` döngüleri
numpy ile kurulup tek `drawImage` ile basılan şerit görüntülerine dönüştü.

**Uçtan uca gerçekten çalıştırıldı**: kayıt → işleme (`complete`, sorun yok) →
kütüphane → Etiketleme. 4 hareket çizildi, biri tek tek diğerleri toplu
etiketlendi, bir hata aralığı sınıf + eklem ile işaretlendi, sınıfsız bırakılan
bir hata aralığı hareketi **hazır olmaktan çıkardı** (4/4 → 3/4) ve "Sonraki
eksik" tam o harekete gitti. Sidecar yazıldı, yeniden okundu, bütün çapalar
aynı karelere çözüldü.

**Ekran boyutu**: denetçi kaydırma alanına alındı; ekranın istediği en küçük
pencere 880×923'ten **880×672**'ye indi — 1366×768 bir dizüstüne sığıyor.

**Testler**: `test_studio_review.py` (22) + `test_studio_review_gui.py` (9).
Ağırlık doğruluk tarafında: çapa gidiş-dönüşü, kapsayıcı sınır, yabancı
kayda ait sidecar reddi, en yakın kareye kaydırmama, belirsiz kimlik reddi,
bir karar = bir geri alma, türetilmiş doğruluk, sınıfsız hatanın hareketi
bloklaması, reddedilen düzenlemenin iz bırakmaması.

**Yapılmadı (F9'a kalan)**: 3B iskelet görünümü. `joints_3d_window()` hazır ve
ölçüldü; görünümü F9 kuracak.

### F9 sonucu (2026-09-14) — F8 ile aynı commit'te

3B iskelet görünümü Etiketleme ekranının içinde yaşadığı için F8 ile birlikte
commit edildi; ayırmak import edilemeyen bir ara commit bırakırdı.

- `studio/services/skeleton3d.py` (Qt'siz): yörünge kamerası, çerçeveleme,
  kemik parçaları, zemin ızgarası. Ölçülebilir olan her şey burada.
- `studio/views/skeleton3d.py`: `QOpenGLWidget`. Köşe verisi **VBO'ya** bir kez
  ayrılıp sonra içine yazılıyor; sahne kare başına yeniden kurulmuyor.
- Video ve 3B **yan yana**: antrenörün sorduğu asıl soru "izlenen iskelet
  kameranın gördüğüyle uyuşuyor mu", ve bu ancak ikisi aynı karedeyken
  yanıtlanabilir. Aynı kare indeksi ikisini de sürüyor.
- Sürükle: döndür · orta düğme: kaydır · tekerlek: yakınlaş · R: sıfırla.
  Kamera açısı sürüm değiştirince korunuyor.
- **Yukarı ekseni kayıttan okunuyor** (`right_handed_y_up` / `..._z_up`);
  varsayılsaydı bir z-up kaydı yan yatardı ve eğilme hakkındaki her yargı
  yanlış olurdu.
- Tracker'ın üretmediği eklem çizilmez; ucu eksik kemik **atılır**, orijine
  çekilmez.

**PyOpenGL tuzağı**: ortamda kurulu ama hızlandırıcısı numpy 2.x ile ikili
uyumsuz (`numpy.dtype size changed`) ve ilk dizide patlıyor. 3B görünüm yalnız
Qt'nin kendi GL sınıflarını kullanıyor — bir bağımlılık eksildi, bir kırılma
noktası da.

**Ölçüm**: 3B çizim medyan **2,07 ms** (16 ms bütçesinin içinde).
**Testler**: `test_studio_skeleton3d.py` (17 geometri + 1 GL widget).

### F10 sonucu (2026-09-14)

Sporcu seçimi ve belirsiz aralık onayı.

**Teslim edilen**

- `processing/subject_review.py`: kanonik **kişi kararı** kaydı 1.0.0.
  Adaylar (`scan_candidates`) ve tracker'ın kararsız kaldığı aralıklar
  (`scan_unsettled`) sürümün kendi iskelet akışından çıkarılıyor.
- `studio/services/subject_store.py`: tek yazıcı, bir karar = bir geri alma,
  bütün belge doğrulanmadan hiçbir şey uygulanmıyor.
- Aday kartları: her kişinin **kendi** aralığından üç kare, ne kadar görüldüğü,
  kaç kez koptuğu. Başlık "Kişi 1"; tracker kimliği en küçük yazı, çünkü o
  kimlik yalnız bu kaydın içinde bir şey ifade eder.
- Her belirsiz aralık için üç yanıt ve **varsayılan yok**: "Aynı sporcu" /
  "Diğer kişi…" / "Bu bölümde sporcu yok". "Diğer kişi" hangi kişi olduğunu
  sorar — kim olduğu söylenmeyen bir "başkası" o kareleri kimseye ait bırakır.
- Toplu yanıt yalnız "aynı sporcu" ve "sporcu yok" için var; "diğer kişi"
  toplu verilemez, çünkü kimsenin bakmadığı kareleri bir kişiye atfederdi.
- Yeniden tarama, karşılığı kalmayan yanıtları **düşürür**: eski bir yanıt asla
  başka bir zaman aralığının üstüne oturmaz.

**GUI yazarken bulunan açık**

`subject_status == "needs_subject_selection"` olan bir sürümde bütün diziler
NaN'dır ve etiketleme ekranında sporcu seçmek bunu **düzeltemez** — diziler
işleme anında yazıldı ve yalnız seçili bedenin eklemlerini taşıyor. Ekran artık
bunu bir soru listesi gibi göstermek yerine açıkça söylüyor: *"Bu sürüm
işlenirken hiçbir kişi seçilmemiş; eklem dizileri boş. Kaydı, sporcu
işaretlenmiş hâlde yeniden işleyin."* Böyle bir sürüm sporcu seçilse bile
`settled` olmuyor.

**Testler**: `test_studio_subject.py` (24) + `test_studio_subject_gui.py` (10).
Ağırlık reddetme tarafında: kimse önceden seçilmiyor, "diğer kişi" kimsiz
kabul edilmiyor, sürümde olmayan kişi seçilemiyor, reddedilen karar geri alma
adımı tüketmiyor, yeniden tarama eski yanıtı taşımıyor.

**Yapılamayan**: iki kişinin gerçekten karıştığı bir kayıt mock backend ile
üretilemedi (iki beden temiz izleniyor, tracker hiç kararsız kalmıyor), bu
yüzden belirsiz aralık akışı sentetik akışlarla test edildi. Gerçek ZED
kaydıyla iki kişili doğrulama hâlâ açık.

### F11 sonucu (2026-09-14)

Veri Seti + Dışa Aktarım. Bu, bir etiket hatasının kalıcı hâle geldiği son
nokta: paket yazıldıktan sonra model onunla eğitiliyor ve etiketlere bir daha
bakan olmuyor.

**`export/canonical.py` — dört kapı**

1. İşleme sürümü tamamlanmış **ve terfi etmiş** olmalı; türetilmiş dosyalar
   kendi checksum'ına uymalı.
2. Sürümün sporcusu seçilmiş ve **her belirsiz aralık yanıtlanmış** olmalı.
3. Etiket belgesi o sürüme karşı doğrulanmalı — her çapa gerçek bir kareye
   çözülmeli, her hata aralığı kendi hareketinin içinde olmalı.
4. Her hareket hazır olmalı: sınıflı, onaylı, yarım hata aralığı olmadan.

**Sessizce hiçbir şey dışa aktarılmaz.** Reddedilen sürüm pakete
`refused_versions` olarak nedeniyle birlikte yazılıyor — "bu sporcu veri
setinde neden yok" sorusu paketin kendisinden yanıtlanabilmeli.

Diziler **dilimleniyor, yeniden hesaplanmıyor**; sürüm özellikleri bütün kayıt
üzerinde hesaplamıştı ve pencereyi yalıtılmış hâlde yeniden hesaplamak aynı
şey değil. Manifest hangisinin olduğunu yazıyor. Hata aralıkları örneğin
kendi başlangıcına **göreli** ve iki ucu da dahil; mutlak çapalar da girdide
duruyor, böylece ikisi her zaman karşılaştırılabilir.

Paket atomik: staging dizinine yazılıp sonuncu adımda yeniden adlandırılıyor.
Yarıda kalan bir dışa aktarım, üzerinde eğitim yapılabilecek yarım bir sürüm
bırakmıyor (testle sabit).

**Ekranlar**

- **Veri Seti**: her sürüm için hareket/hazır sayısı, hata aralığı, sporcu
  durumu ve **neyi beklediği**. Sürüm açmıyor, sidecar okuyor — bu yüzden
  "hazır" değil **"hazır görünüyor"** diyor. Yetkili kontrol Dışa Aktarım'da.
- **Dışa Aktarım**: önce kontrol, sonra yazma. Kontrol her sürümü gerçekten
  açıp checksum ve etiket doğrulaması yapıyor; kullanıcı **yazmadan önce**
  hangi sürümün girip hangisinin girmediğini ve nedenini görüyor. Reddedilen
  satır listeden düşmüyor.

**Testler**: `test_export_canonical.py` (14) + `test_studio_export_gui.py` (7).
Ağırlık yine reddetme ve içerik doğruluğunda: sporcusu seçilmemiş sürüm pakete
giremiyor, sınıfsız hata aralığı bütün sürümü bloke ediyor, örnek tam olarak
işaretlenen kareleri taşıyor (5..20 → 16 kare), hata aralığı göreli indeksleri
kapsayıcı, yoğun hedef aralıkla birebir örtüşüyor, sınıf indeksleri iki ayrı
derlemede aynı, başarısız derleme hiçbir iz bırakmıyor.

**Not**: F2'den beri koşan "yapılmamış ekran yer tutucu gösterir" testi artık
ters çevrildi — bütün destinasyonların gerçek bir ekranı olduğunu doğruluyor.

### F12 sonucu (2026-09-14)

Altı yardımcı pencere: **Log Konsolu · Tanılama · Cihaz Bilgisi · Kaynak
Denetimi · Köken · Ham Parametreler.**

- Hepsi **modeless ve üst düzey pencere** (parent'sız): ikinci monitöre
  taşınabiliyor, ana akışı engellemiyor, hiçbiri bir şey değiştirmiyor.
- İçerik `studio/services/inspectors.py` içinde **Qt'siz** toplanıyor; pencere
  yalnız satırları gösteriyor. Bu yüzden testler Qt açmadan içeriği
  doğrulayabiliyor.
- Her pencere tek tıkla **panoya metin** olarak kopyalanıyor — bu pencereleri
  açmanın olağan sebebi, içindekini birine göndermek.
- Eksik değer `—` ile işaretleniyor; makul görünen bir varsayılanla
  doldurulmuyor. Bu pencerelerin bütün değeri inanılabilir olmalarında.

**Öne çıkanlar**

- **Köken**: etiketlerin bağlı olduğu ham parmak izi, sürümün sorunları ve —
  derinlik varsa — `reconstructed_offline` uyarısı. SVO tekrar oynatıldığında
  kayıt anındaki derinlik geri gelmiyor; pencere bunu ölçüm gibi göstermiyor.
- **Kaynak Denetimi**: `checksums.json` yeniden hesaplanıyor; değişen dosya
  adıyla listeleniyor. Manifest yoksa "doğrulanamaz" diyor.
- **Log Konsolu**: uygulamanın kendi kaydedicisinden okuyor (dosya olmasa da
  çalışır), halka tampon 2000 satırda sabit, seviye ve metin filtresi var.
  **Uygulamanın kayıt seviyesini pencerenin kendisi değiştirmiyor**; bunun
  yerine hangi seviyede olduğunu yazıyor, böylece boş bir konsol gizemli
  olmuyor.

**Testler**: `test_studio_windows.py` (19).

### F13 sonucu (2026-09-14)

Dayanıklılık. Bu projede pahalı olan arızalar sessiz olanlar: bir saatlik
etiketleme çalışmasının çökmede kaybolması, yarım yazılmış bir paketin
bitmiş görünmesi, ekran "kaydedildi" derken yazamamış olmak.

**Etiketler kayıpsız**

- **Otomatik kayıt**: son değişiklikten 4 sn sonra sidecar yazılıyor. Önceden
  etiketler yalnız ekrandan çıkarken diske gidiyordu; arada gelen bir çöküş
  bütün oturumu götürürdü. Ctrl+S hemen yazar.
- Zaman çizelgesi çubuğunda **kaydedildi / kaydedilmedi** göstergesi var ve
  mağazanın gerçek durumunu izliyor, son kullanıcı eylemini değil.
- **Başarısız yazma işi kaybetmiyor**: `flush()` hata durumunda `False`
  dönüyor, kayıt "kirli" kalıyor, otomatik kayıt yeniden deniyor ve kullanıcı
  nedenini görüyor. Diskin dolduğu senaryo testle sabit.
- Bozuk (ayrıştırılamayan) bir sidecar ekranı açılmaktan alıkoymuyor ama
  **sessizce boş başlamıyor**: kullanıcıya söyleniyor. Sessiz bir boş başlangıç
  "henüz etiket yok" ile karıştırılabilirdi.

**Beklenmeyen istisna arayüzü çökertmiyor**

`install_exception_hook` istisnayı kullanıcıya okunur bir mesaja ve günlüğe
çeviriyor, sonra önceki hook'u çağırıyor — traceback yutulmuyor. Raporlayıcının
kendisi patlarsa bu da yutuluyor: son savunma hattı, çökme sebebi olamaz.

**Uzun yol**

260 karakteri aşan bir yolda `Path.exists()` sessizce `False` dönüyor;
uygulamanın hiçbir yerde bunu sormamasının sebebi bu. Test bunu açıkça
gösteriyor: aynı dosya için `path_exists()` `True`, `Path.exists()` `False`.

**Testler**: `test_studio_robustness.py` (9).

### F14 sonucu (2026-09-14)

Cila. Üç tür denetim, hepsi testle sabit (`test_studio_polish.py`, 68 test).

**Hiçbir şey yokken de çizilir.** Yeni parçaların hepsi boş kayıt, tek karelik
kayıt, tamamı NaN iskelet ve kullanılamayacak kadar küçük bir alanla
çiziliyor — bunlar gerçek bir oturumun kötü gününde ulaştığı durumlar. Boş
kalan yer boş bırakılmıyor, **nedeni yazılıyor**.

**Renk asla tek sinyal değil.** `READINESS_TEXT`, `VERDICT_TEXT`, `REFUSAL_TEXT`
sözlükleri kendi enum'larıyla birebir eşleşiyor ve hepsi dolu; bir durumu
yalnız renkle anlatan yer kalmadı. Hareket satırı da durumunu kelimeyle
taşıyor ("Squat · hatalı").

**Klavye ve okunabilirlik.** Her ekrandaki her denetim klavyeyle erişilebilir
ve kendini tanıtıyor (metin, ipucu veya erişilebilir ad). Bu test iki gerçek
açık buldu: Etiketleme'deki sınıf açılır kutuları proje sözlüğü yüklenene
kadar boş oldukları için **hiçbir şey duyurmuyorlardı**; İşlenen Videolar ve
Veri Seti filtreleri de adsızdı. Hepsine erişilebilir ad verildi.

**Ölçek** (gerçek fontlarla, `QT_QPA_PLATFORM=windows`):

| Ekran | En küçük | %100 | %125 | %150 | %200 (1366×768) |
|---|---|---|---|---|---|
| Yakalama | 802×406 | ✓ | ✓ | ✓ | taşar |
| Etiketleme | 822×500 | ✓ | ✓ | ✓ | taşar |
| İşlenen Videolar | 359×417 | ✓ | ✓ | ✓ | taşar |
| Diğer beş ekran | ≤541×352 | ✓ | ✓ | ✓ | ✓ |

1366×768 bir dizüstünde %100/%125/%150 hepsi sığıyor. %200 o panelde
683×384 mantıksal alan bırakıyor ve üç ekran sığmıyor; %200 normalde yüksek
çözünürlüklü bir ekranda kullanılır ve orada (4K'da 1920×1080 mantıksal alan)
**hepsi sığıyor** — ayrı bir testle sabit. Bu sınır gizlenmiyor, yazılıyor.

**Kontrast** (WCAG): her temada `KcTextPrimary` üç yüzeyin hepsinde ≥ 4,5;
ikincil metin, üç durum rengi ve odak halkası ≥ 3,0. Stil şablonunda `:focus`
kuralı olduğu da doğrulanıyor — klavyeyle çalışmak, nerede olduğunu görmeyi
gerektirir.

### F15 sonucu (2026-09-14) — uçtan uca tur ve final rapor

**Tam tur, gerçek uygulama penceresi üzerinden, mock backend ile.** Betik:
proje aç → iki kayıt al → ikisini de işle → kütüphanede gör → birini etiketle
→ sporcuyu seç → veri setinde gör → kontrol et → paketi yaz → paketi dışarıdan
oku ve etiketlerle karşılaştır → altı yardımcı pencereyi aç.

**Her adım doğrulandı** (32 kontrol, hepsi geçti). Kritik olanlar:

| Kontrol | Sonuç |
|---|---|
| Kayıt sırasında kare kaybı | **0** (önizlemede atlanan 38 — ayrı sayılır) |
| İki sürüm de `complete` | ✓ |
| Etiketleme: video · 2B iskelet · 3B görünüm | üçü de açıldı |
| Hatalı tekrar "hatalı" diyor (türetilmiş) | ✓ |
| Sporcu önceden seçilmemiş | ✓ (seçimi insan yaptı) |
| Sidecar yeniden okundu, çapalar aynı karelere çözüldü | (5,51) (55,101) (105,151) |
| Veri Seti: biri hazır, diğeri değil | ✓ |
| Kontrol iki sürümü de gösterdi, reddedilen nedenini söyledi | "Sürümün sporcusu seçilmemiş" |
| **Etiketlenen kareler pakete birebir taşındı** | ✓ aynı üç aralık |
| Bir örnek hatalı, ikisi doğru | ✓ |
| Hata aralığı göreli ve kapsayıcı | 2..7 |
| Dizi örnek uzunluğunda | (47, 16, 3) / 47 kare |
| Paket kökeni taşıyor (run, parmak izi, revizyonlar) | ✓ |
| Altı pencere açıldı, hiçbiri modal değil | ✓ |

**Uçtan uca turun bulduğu açık**: Dışa Aktarım ekranında "Sürümleri kontrol et"
düğmesine kütüphane hâlâ okunurken basılınca boş liste kontrol ediliyor ve
"dışa aktarılacak bir şey yok" deniyordu — bu ekranın söyleyebileceği en
yanıltıcı şey. Artık liste hazır olana kadar bekliyor, gerçekten sürüm yoksa
bunu ayrı bir mesajla söylüyor.

## 8. Final bütçe tablosu

60 dk / 60 FPS / BODY_38 = 216000 kare. `QT_QPA_PLATFORM=windows`,
RTX 2060 / i7-10750H / 16 GB.

| Ölçüm | Bütçe | Sonuç | Durum |
|---|---|---|---|
| Boşta kare (çizelge + görüntü) | ≤ 8 ms | medyan 0,72 · p95 1,51 ms | ✓ |
| Zaman çizelgesi, 100 aralık | ≤ 16 ms | medyan 5,6 · p95 8,3 ms | ✓ |
| Zaman çizelgesi, 600 aralık | ≤ 16 ms | medyan 13,9 ms · p95 20,5 ms | medyan ✓, **p95 aşıyor** |
| Oynatma çizgisi hareketi | ≤ 16 ms | medyan 0,11 ms | ✓ |
| Tarama (veri okuma + iki çizim) | ≤ 50 ms | medyan 0,84 · p95 1,73 ms | ✓ |
| 600 karelik 3B pencere okuma | ≤ 50 ms | medyan 0,17 ms | ✓ |
| 3B iskelet çizimi | ≤ 16 ms | medyan 2,1–2,3 ms | ✓ |
| 60 dk oturumda zirve RSS | ≤ 1,5 GB | **144 MB** | ✓ |
| Sürüm açma (arka planda) | — | 1,1 s (216000 satırlık kaynak haritası) | GUI bloklanmıyor |

**600 aralık uyarısı dürüstçe**: tek görünümde 300 hareket + 300 hata aralığı,
yani bir saatlik seansın tamamı etiketlenmiş ve hepsi aynı anda ekranda.
Medyan bütçe içinde, p95 makine meşgulken 20 ms'e çıkıyor. Tipik kullanım
(100 aralık) 5,6/8,3 ms. Bunu bir "geçti" satırı gibi yazmak yanlış olurdu.

**Ekran boyutu** (gerçek fontlarla): Etiketleme 822×500, Yakalama 802×406,
İşlenen Videolar 359×417, diğerleri daha küçük. 1366×768'de %100/%125/%150
hepsi sığıyor; %200'de o panelde üç ekran taşıyor, yüksek çözünürlüklü bir
ekranda (%200'ün normal kullanıldığı yer) hepsi sığıyor.

## 9. Donanım gerektirdiği için yapılamayanlar

Bunların hiçbiri mock ile doğrulanamaz ve hiçbiri "çalışıyor" diye yazılmadı.

1. **Gerçek ZED ile tam tur.** Kamera bağlıydı ama karanlık bir odada ve
   önünde kimse yoktu; bağlantı ve FPS ötesinde bir şey ölçülemezdi.
2. **60 FPS sürdürülebilirliği ve gerçek kayıtta kare kaybı.** Mock ile 0
   kayıp ölçüldü; bu ZED hakkında bir şey söylemez.
3. **Canlı iskeletin 2B/3B görünümdeki doğruluğu.** Sentetik iskelet doğru
   çiziliyor; gerçek bir insanın üzerine oturması ayrı bir doğrulama.
4. **Gerçek derinlik.** `reconstructed_offline` yolu yazıldı ve işaretlendi,
   gerçek SVO ile karşılaştırılmadı.
5. **İki kişinin gerçekten karıştığı kayıt.** Mock iki bedeni temiz izliyor,
   tracker hiç kararsız kalmıyor; belirsiz aralık akışı yalnız sentetik
   akışlarla test edildi. F10'un en önemli yolu gerçek kayıt bekliyor.
6. **Yakalama ekranının tıkla-seç kişi akışı.** `select_subject` viewmodel'de
   var ama uçtan uca betikte tetiklenemedi; çapa dosyası elle yazıldı.
   Gerçek kamerayla önizlemede birine tıklayarak sınanmalı.

### Uçtan uca turun bulduğu ikinci açık (F15 sırasında düzeltildi)

**Dışa Aktarım ve Veri Seti tablolarına kaynak model hiç verilmemişti.**
İkisi de `SearchProxy(self.model)` yazıyordu; `SearchProxy.__init__`'in ilk
parametresi *parent*, kaynak model değil. Proxy'nin kaynağı boş kaldığı için
tablo **her zaman boş çiziliyordu** — model doluyken, model seviyesindeki
bütün testler geçerken. Ekran görüntüsünde fark edildi.

Neden testler yakalamadı: hepsi `page.model.rowCount()` soruyordu, yani
verinin modelde olup olmadığını. Ekranda görünüp görünmediğini soran yoktu.
Artık var: `test_a_table_shows_what_its_model_holds` her tablo sayfası için
görünüme model verilmiş mi ve proxy'nin kaynağı var mı diye soruyor.

Aynı turda düzeltilen üçüncü küçük hata: özet etiketi (`1/2 sürüm hazır · 3
hareket · 1 sürüm dışarıda`) esnek boşluğun artığına sıkışıp `1/…` diye
kırpılıyordu; artık kalan genişliği o alıyor.

## 10. Kapanış

**F0–F15 tamamlandı.** Sekiz ekranın hepsi gerçek, yer tutucu kalmadı. Tam tur
(yakalama → işleme → kütüphane → etiketleme → veri seti → dışa aktarım →
yardımcı pencereler) mock backend ile gerçek uygulama penceresi üzerinden
çalıştırıldı ve 32 kontrolün hepsi geçti.

**Testler**: 59 dosya, 0 başarısız (dosya dosya çalıştırıldı). Bu çalışmada
eklenenler: `test_studio_review.py` (22), `test_studio_review_gui.py` (9),
`test_studio_skeleton3d.py` (18), `test_studio_subject.py` (24),
`test_studio_subject_gui.py` (10), `test_export_canonical.py` (14),
`test_studio_export_gui.py` (7), `test_studio_windows.py` (19),
`test_studio_robustness.py` (9), `test_studio_polish.py` (68).

**GUI yazarken kapatılan backend açıkları** — toplam on bir tanesi bu
çalışmada bulundu ve kapatıldı; hepsi §7'de F8, F10 ve F15 başlıkları altında
tek tek yazılı. Üçü doğrudan yanlış etiket üretebilecek cinstendi:
tekrarlanan kare kimliğinin sessizce çözülmesi, hata aralığının sessizce
kırpılması ve eklem durumunun sessizce "seçildi"ye yükseltilmesi.

**Sırada**: gerçek ZED ile doğrulama (§9). Mock'un söyleyemeyeceği her şey
orada ölçülecek.
