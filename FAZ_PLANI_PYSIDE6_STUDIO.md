# KineCapture Studio — PySide6 arayüz yeniden yapımı, faz planı

> **Bu dosya çalışan plandır.** Yeni bir oturum açıldığında sıra buradan
> alınır. Giriş noktası her zaman `MEMORY_INDEX.md`, sonra bu dosya.
> Kaynak görev: `CLAUDE_PYSIDE6_YENI_BACKEND_ENTEGRASYON_PROMPT.md`.
> Mevcut durum tespiti: `F1_MEVCUT_DURUM_TESPITI_2026-09-13.md`.

Oluşturuldu: 2026-09-13 · **F0–F4 tamamlandı, F5 sırada.**
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
| **F5** | Yakalama | Mock ile tam tur; hafif 2B pose kaplaması; anchor gösterilen kareye yazılıyor; önizleme/kayıt kaybı ayrı | F3 |
| **F6** | Verileri Hesapla | İşleme ayrı süreçte, ilerleme gerçek, iptal/duraklat/restart çalışıyor, GUI bloklanmıyor | F3 |
| **F7** | İşlenen Videolar | Kütüphane, thumbnail önbelleği, sürüm karşılaştırma, filtreler | F3, F6 |
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
| F4 | ✅ | 2026-09-13 | aşağıda |
| F5 | ⏳ sırada | | |
| F6–F15 | — | | |

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
