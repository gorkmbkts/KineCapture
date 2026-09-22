---
type: plan
status: in-progress
created: 2026-09-19
updated: 2026-09-19
tags:
  - studio
  - gui
  - plan
  - phased-implementation
---

# Studio GUI iyileştirmesi — faz planı ve ilerleme

> 20 Eylül: Faz uygulama geçmişi korunuyor; tüm GUI'nin kabul edildiği yorumu
> `superseded`. [Yeni denetim](../audits/studio-gui-acceptance-audit-2026-09-20.md)
> ve [düzeltme görevi](../../promts/CLAUDE_STUDIO_GUI_ACCEPTANCE_REPAIR_PROMPT_2026-09-20.md)
> açıkların devam kaydıdır.

Bu dosya [Claude görev promptunun](../../promts/CLAUDE_STUDIO_GUI_FINAL_REFINEMENT_PROMPT_2026-09-19.md)
`PLAN-01` ve `PLAN-02` maddelerinin çıktısıdır. Kaynak kararlar:
[onaylı tasarım](../decisions/studio-gui-refinement-2026-09-19.md) ·
[fikir haritası](../decisions/studio-gui-design-map-2026-09-19.md).
Çalıştırılan doğrulamalar ayrı dosyada:
[doğrulama raporu](../reports/studio-gui-refinement-validation.md).

Kapsam yalnız `src/kinecapture/studio/` arayüzüdür. Eski `src/kinecapture/gui/`
arayüzüne aynı tasarım uygulanmaz; ortak servis/şema değişirse uyumluluk aynı
fazda ele alınır.

## 1. Koddan çıkarılan mevcut durum

Aşağıdakiler bu oturumda gerçekten okunan koddan ve çalıştırılan ölçümden
çıkarıldı. Kanıt düzeyi her maddede belirtilidir.

### 1.1 Mimari sınırlar

- `verified`: Katmanlar `services/` (Qt'siz) → `viewmodels/` (Qt'siz) →
  `views/` biçiminde ayrılmış; `tests/test_studio_layers.py` alt katmanlarda
  Qt importunu ve `views/` içinde literal renk yazımını reddediyor.
- `verified`: Bütün renk/ölçü/tipografi değerleri
  `studio/theme/tokens.json` (`schema_version 1.1.0`) içinde; QSS
  `studio.qss.tmpl` şablonundan üretiliyor. `KcWindowMinWidth=1120`,
  `KcWindowMinHeight=700` desteklenen asgari pencere ölçüsüdür
  (`UI-04` için istenen değer).
- `verified`: Sayfalar `StudioWindow.page()` içinde ilk ziyarette kurulup
  saklanıyor (`views/shell.py`), `QStackedWidget` içine ekleniyor.
- `verified`: İkonlar `views/icons/` altındaki Lucide SVG'leri;
  `iconset.ICON_NAMES` ürün sözlüğünü dosya adına bağlayan tek tablo.
  Paket içinde font dosyası **yok** (`LOGIN-01` için yerel paketleme gerekir).

### 1.2 Ölçülen teşhisler

| Ölçüm | Sonuç | Kanıt |
|---|---|---|
| Etiketleme'ye ilk geçişte native pencere yeniden oluşturuluyor mu? | **Evet.** `winId` 330866 → 396402 | `QT_QPA_PLATFORM=windows`, gerçek pencere, 2026-09-19 |
| Tekrarlanan geçişlerde? | **Hayır.** `winId` sabit, geçiş ~0 ms | aynı koşu |
| İlk geçiş süresi | 1563 ms (sayfa kurulumu + GL) | aynı koşu |
| Sayfa değişiminden sonra toast katmanı üstte mi? | **Hayır.** Toast merkezinde `childAt` sayfayı döndürüyor | aynı koşu |
| `ReviewSession.open` (gerçek 1370 karelik sürüm, 2.7 GB) | **6793 ms** | okuma-yalnız ölçüm, 2026-09-19 |
| Bunun içinde `verify_checksum_manifest` | **6772 ms** (yani tamamı) | aynı koşu |
| `_after_open` GUI thread maliyeti | ~165 ms (video açma 133 ms + ilk kare 24 ms) | aynı koşu |

Çıkarımlar:

- `LOAD-01` kök nedeni `verified`: **İlk `QOpenGLWidget`'in (Skeleton3DView)
  zaten gösterilmiş bir üst pencereye sonradan eklenmesi native pencereyi
  yeniden oluşturuyor.** Belirti kullanıcıya "pencere kayboldu ve geri geldi"
  olarak görünür. Tekrarlanan geçişlerde oluşmuyor; kullanıcının "her
  seferinde" tarifi ilk girişle sınırlıdır ve ayrıca ölçülecek.
- `LOAD-02` kök nedeni `verified`: Yükleme süresinin tamamına yakını
  türetilmiş dosyaların checksum doğrulaması. Bu ölçülebilir bir iştir
  (hash'lenen bayt / toplam bayt), dolayısıyla **gerçek yüzde ve ETA
  üretilebilir**; uydurmaya gerek yok.
- `NOTICE-01` kök nedeni `verified`: `ToastLayer`, `QStackedWidget`'in
  çocuğudur. `QStackedLayout::setCurrentIndex` yeni sayfayı `raise()` ederek
  kardeşlerin üstüne çıkarır; bu, daha önce `raise_()` edilmiş toast katmanını
  sayfanın altında bırakır. Mevcut `raise_()` çağrısı yalnız mesaj
  oluşturulurken çalıştığı için sonraki sayfa geçişinde etkisiz kalır.

### 1.3 Ekran bazlı mevcut durum

- **Giriş** (`views/auth.py`): `QFormLayout` + sağa hizalı etiketler; logonun
  altında ayrı `CREST_NAME` etiketi; `CREST_SIZE=168`; parola göster/gizle
  kontrolü yok; birincil/ikincil buton yan yana.
- **Yakalama** (`views/pages/capture.py`): `Bağlan` alt transport satırında
  (`_build_transport`); telemetri ayrı ikinci satırda (`_build_metrics`),
  `_Metric` dikey etiket/değer; kayıt butonu `kcVariant=primary` (mavi).
  Sıra `Bağlan → Kayda başla → süre → geri sayım → İşaret koy`, telemetri
  `FPS → Kaydedilen kare → Kayıt kaybı → Önizleme kaybı → Diskte kalan`.
- **Verileri Hesapla** (`pages/processing.py`): İki tablo dikey olarak üst
  üste (`body_layout.addWidget(view, 1)` ×2); arama/filtre yok; seçili kayıt
  özeti yok; iş eylemleri alttaki tek satırda.
- **İşlenen Videolar** (`pages/library.py`): `QSplitter` 1180/420
  (≈%74/%26); sürüm grupları yok, `sibling_versions` yalnız sütun; boyut
  bilgisi hiç yok; önizleme `_COVER_WIDTH=240`.
- **Etiketleme** (`pages/review.py`): Sayfa başlığı + `run_id · N kare` alt
  satırı `StudioPage` tarafından çiziliyor; dikey `QSplitter` (üst 3 / alt 2);
  üstte yatay `QSplitter` (sol 3 / sağ 1); sol içinde `stage` splitter
  (viewer 3 / skeleton 2 — oran serbest, iskelet kare değil); transport ayrı
  satır, çizim araçları timeline üstünde ayrı satır (iki satır);
  sağ panel `QTabWidget` yatay yazılı sekmeler (`Etiket`, `Sporcu`).
- **3B** (`views/skeleton3d.py`): `GL_POINTS` (point_size 6/11) ve `GL_LINES`,
  tek renk (`KcAccentPrimary`); `QSurfaceFormat.setSamples(4)` isteniyor
  (gerçekte kullanılan format doğrulanmadı); sol sürükleme `orbit(azimuth,
  elevation)`, orta **ve** sağ tuş `pan`; preset yok; zemin `height=0.0`
  sabit düzlem, `frame_subject` yalnız `_after_open` içinde bir kez.
- **Etiket paneli**: `QComboBox` + `Yeni…` `QInputDialog`; eklem seçimi
  checkbox listesi (`role_list`); `JointStatus` dört değerli ve korunmalı.
- **Sınıf kütüphanesi**: `domain/labels.py::LabelSchema` (`LABEL_SCHEMA_VERSION
  = 2.0.0`), proje kökünde `label_schema.json`; `LabelOption(code, label,
  description)`. Eklem varsayılanı için alan **yok**.
- **Veri Seti / Dışa Aktarım**: tek tablo + altta ince ayrıntı satırı;
  `EXPORT-01`'in istediği sol/sağ ayrımı yok.

## 2. Ortak kurallar (bütün fazlar)

- Ortam: yalnız `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`.
- Yeni renk/ölçü **yalnız** `tokens.json` içine; `views/` içinde literal renk
  yasak (test bunu zorluyor).
- Ham SVO, ölçülmüş eklem dizileri ve mevcut sidecar'lar değişmez. Kamera,
  çizim ve kadraj dönüşümleri ölçüm verisine yazılmaz. Eksik ölçüm NaN kalır.
- Şema değişikliği olursa: sürüm artır, eski belgeyi kayıpsız oku, yazımı
  atomik tut, okuyucu/export aynı fazda güncellensin.
- Test koşusu **dosya dosya**; yerleşim/görsel kabul `QT_QPA_PLATFORM=windows`
  ile gerçek pencerede (`knowledge/protocols/test-and-measurement.md`).
- Kullanıcının gerçek projesi (`C:\kc15\ry8kajfjq\datasets`) yalnız **okunur**;
  test ve geçici çıktı ayrı geçici dizinlere yazılır.

### Performans bütçesi (önceden ilan)

| Metrik | Başlangıç ölçümü | Kabul sınırı |
|---|---|---|
| Uygulama kurulumu (`build_window`) | 1304 ms | ≤ %10 artış |
| İlk `show()` | 742 ms | ≤ %10 artış |
| Etiketleme'ye ilk geçiş | 1564 ms | ≤ 400 ms (pencere yeniden oluşturma kalkacak) |
| Etiketleme'ye tekrar geçiş | ~0 ms (153 ms ölçüm beklemesi dahil) | ≤ 50 ms |
| Sürüm açma (2.7 GB, 1370 kare) | 6793 ms, ilerleme yok | Süre aynı kalabilir; **gerçek ilerleme** zorunlu, GUI donmayacak |
| `_after_open` GUI thread | 165 ms | ≤ 200 ms |
| 3B kare çizimi | F10'da ölçülecek | ≤ 8 ms/kare (125 FPS başı) |
| Kayıt kaybı (canlı) | ölçülemedi (donanım gerekir) | Ölçülemezse "doğrulanmadı" yazılır |

## 3. Fazlar

### F1 — Ortak görsel dil: token, ikon, üst çubuk
**Karşılanan:** `UI-01`, `UI-02`, `UI-03`, `UI-04`
**Bağımlılık:** yok. Sonraki bütün fazlar buna dayanır.
**Modüller:** `theme/tokens.json`, `theme/studio.qss.tmpl`, `views/iconset.py`,
`views/icons/*`, `views/widgets.py`, `views/contextbar.py`,
`services/context.py`.
**Çıktı:** ortak yükseklik/boşluk token'ları; anatomik ve araç ikonları;
semantik renk sözleşmesi (kayıt kırmızı, hareket mavi, hata mercan, eksik
kehribar, tamam yeşil, nötr); üst çubuktaki dekoratif yeşil onay işaretinin
kalkması (uyarı/hata ikonları kalır).
**Kapanış kontrolü:** `test_studio_theme.py`, `test_studio_layers.py`
yeşil; üst çubukta `ContextState.OK` için ikon çizilmediğini doğrulayan yeni
test; gerçek pencerede 1120×700 ve 1920×1080'de kırpılma yok.
**Geri dönüş:** `tokens.json` ve `iconset.py` tek dosya; git ile geri alınır.

### F2 — Bildirim katmanı kök nedeni
**Karşılanan:** `NOTICE-01`, `NOTICE-02`
**Bağımlılık:** F1 (token).
**Modüller:** `views/toasts.py`, `views/shell.py`.
**Çıktı:** toast katmanı `QStackedWidget` kardeşi olmaktan çıkarılır; sayfa
yığınının **üstündeki** bir kapsayıcıya taşınır (veya her sayfa değişiminde
yeniden `raise_()` edilir). Katman yalnız kartların kapladığı alan kadar
büyük kalır; geri kalan yerde tıklamalar sayfaya gider.
**Kapanış kontrolü:** `test_studio_toasts.py` + yeni test: sayfa değişiminden
sonra toast merkezinde `childAt` hâlâ `Toast`; toast gösterilirken timeline
geometrisi değişmiyor. Gerçek pencerede her sayfada Kapat/Ayrıntılar tıklanır.
**Geri dönüş:** iki dosya, git ile geri alınır.

### F3 — Giriş ekranı
**Karşılanan:** `LOGIN-01`, `LOGIN-02`
**Bağımlılık:** F1.
**Modüller:** `views/auth.py`, `views/brand.py`, yeni `views/fonts/`
(Space Grotesk + `OFL.txt`), `theme/tokens.json` (marka fontu token'ı).
**Çıktı:** logonun altındaki ayrı üniversite yazısı kalkar, logo ~%12 büyür;
"KineCapture Studio" marka fontuyla; kullanıcı adı/parola yer tutucu olarak
kutunun içinde; eşit genişlikli simetrik form; parola göster/gizle kutunun
içinde; giriş butonu form genişliğinde, ikincil bağlantı altta ortalı.
**Şema/uyumluluk:** yok. Font yüklenemezse mevcut `KcFontFamily`'ye düşer;
erişilebilir alan adları yer tutucudan bağımsız kalır.
**Kapanış kontrolü:** `test_auth_gui.py`, `test_studio_brand.py`; yeni test:
Türkçe glifler (`ğüşıöçĞÜŞİÖÇ`) fontta var; font yokken de form kurulur;
Enter/Tab sırası ve hatalı parola davranışı değişmedi.
**Geri dönüş:** font dosyası eklenmesi geri alınabilir; `auth.py` tek dosya.

### F4 — Yakalama
**Karşılanan:** `CAP-01`, `CAP-02`, `CAP-03`
**Bağımlılık:** F1.
**Modüller:** `views/pages/capture.py` (gerekirse `viewmodels/capture.py`
salt-okuma eklentileri).
**Çıktı:** `Bağlan` başlık hizasında sağ üstte; tek kontrol satırı
`Kayıt → Süre → FPS → Kayıt kaybı → Önizleme kaybı → Diskte kalan → İşaret koy`;
telemetri yatay etiket/değer, mono sayı; kayıt butonu kırmızı;
STOPPING/devre dışı durumları ayrı.
**Kapanış kontrolü:** `test_studio_capture.py`, `test_studio_capture_target.py`,
`test_capture_subject_gui.py`; yeni test: satır sırası ve tek satırda olma;
sayaç kaynaklarının karışmaması. Kazanılan yükseklik ölçülür.
**Geri dönüş:** tek dosya.

### F5 — Verileri Hesapla
**Karşılanan:** `PROC-01`, `PROC-02`
**Bağımlılık:** F1.
**Modüller:** `views/pages/processing.py`, `viewmodels/processing.py`,
`services/processing.py` (yalnız okunan sayımlar).
**Çıktı:** yan yana iki dikey panel (~%40 / %60); bekleyenlerde arama +
katılımcı filtresi + çoklu seçim; seçili kayıt özeti (katılımcı, süre, profil);
kuyrukta durum sayımları, gerçek aşama/ilerleme/hız/ETA; eylemler doğru işe
bağlı.
**Kapanış kontrolü:** `test_studio_processing.py`; yeni test: çok kayıt/çok işle
oranlar ve filtre; ETA yalnız gerçek toplam varken.
**Geri dönüş:** tek sayfa dosyası + viewmodel eklentisi.

### F6 — İşlenen Videolar
**Karşılanan:** `LIB-01`, `LIB-02`
**Bağımlılık:** F1.
**Modüller:** `views/pages/library.py`, `viewmodels/library.py`,
`services/library.py`.
**Çıktı:** ~%55/%45 bölünme; aynı kaydın sürümleri gruplu ama ayrı seçilebilir;
önizleme büyür ve kaynağın oranını korur; ham kayıt boyutu ile türetilmiş sürüm
boyutu **ayrı**; bilinmeyen değer `—`; uyarılar özet + açılabilir ayrıntı;
boyut/metadata asenkron ve önbellekli, geç sonuç yeni seçimin üstüne yazmaz.
**Kapanış kontrolü:** `test_studio_library.py`; yeni test: boyut ayrımı, geç
gelen metadata sonucunun düşürülmesi, eksik thumbnail'da 0 yazılmaması.
**Geri dönüş:** üç dosya; `VersionRow` alanları additive.

### F7 — Etiketlemeye giriş: pencere kaybolması ve gerçek hazırlık
**Karşılanan:** `LOAD-01`, `LOAD-02`, `LOAD-03`, `LOAD-04`
**Bağımlılık:** F1, F2.
**Modüller:** `views/shell.py`, `views/pages/review.py`,
`viewmodels/review.py`, `services/review.py`, `processing/review.py`,
`core/fingerprint.py` (ilerleme geri çağrısı).
**Çıktı:**
1. Pencere yeniden oluşturulmasını önlemek için GL yüzeyi pencere
   gösterilmeden **önce** hazırlanır (ölçülecek iki seçenek: ReviewPage'i
   `show()` öncesi kurmak, veya paylaşılan küçük bir `QOpenGLWidget` ile üst
   pencereyi baştan RHI destekli yapmak). Seçim ölçümle yapılır; hide/show
   hilesi kullanılmaz.
2. Sayfa içi tek hazırlık yüzeyi: `kayıt doğrulama → video hazırlama →
   iskelet hazırlama` aşamaları; checksum doğrulaması bayt temelli gerçek
   yüzde ve ETA verir; bilinmeyen toplamda belirsiz ilerleme.
3. İlk RGB karesi, ilk 3B kare, timeline ve paneller hazır olunca editöre
   birlikte geçiş; video ve iskelet aynı kareyi gösterir.
4. İptal/yeniden dene/sayfa değiştirme/A→B yarışları; geç sonuç düşürülür;
   worker, video okuyucu ve GL kaynakları kapanır.
**Şema/uyumluluk:** `verify_checksum_manifest` isteğe bağlı `progress`
geri çağrısı alır (additive, mevcut çağıranlar etkilenmez).
**Kapanış kontrolü:** `test_studio_review_open.py`, `test_studio_review_gui.py`,
`test_review_flow.py`; yeni testler: `winId` geçişte değişmiyor; busy yalnız
sayfa hazırken kapanıyor; A yüklenirken B açınca A'nın sonucu düşüyor.
Gerçek pencerede önce/sonra ölçüm.
**Geri dönüş:** GL ön hazırlığı tek satırlık bir anahtarla kapatılabilir
tutulur; ilerleme geri çağrısı opsiyoneldir.

### F8 — Etiketleme yerleşimi: üç bant
**Karşılanan:** `LAYOUT-01`, `LAYOUT-02`
**Bağımlılık:** F1, F7.
**Modüller:** `views/pages/review.py`, `views/viewer.py`, yeni yerleşim
yardımcısı (Qt'siz geometri `services/` içine).
**Çıktı:** sayfa başlığı ve run satırı kalkar, kayıt kimliği sağ panele taşınır;
üç bant; RGB oranı gerçek metadata'dan (`processing_camera.resolution`);
3B viewport 1:1; ortak dış çerçeve + ince ayırıcılar; sağ panele okunabilir
asgari genişlik; `H` pencereden ve timeline asgari yüksekliğinden hesaplanır.
**Kapanış kontrolü:** Qt'siz geometri testi (r, H, panel min genişlik →
RGB/iskelet/panel genişlikleri); gerçek pencerede 1120×700, 1600×900,
1920×1080 ve %100/%125/%150 ölçekte kırpılma/esneme yok.
**Geri dönüş:** geometri yardımcısı ayrı modül; sayfa eski splitter'a döner.

### F9 — Tek araç satırı ve timeline
**Karşılanan:** `TOOL-01`, `TOOL-02`, `TOOL-03`
**Bağımlılık:** F1, F8.
**Modüller:** `views/pages/review.py`, `views/timeline.py`.
**Çıktı:** oynatma + çizim + timeline araçları tek satırda, gruplu, ikonlu;
aralık çizimi bitince otomatik `Gez`; yeni aralık seçili ve doğru düzenleyici
açık; Esc iptali de `Gez`'e döner; seçili aralığı döngüde oynatma ve hız
seçimi; dar alanda taşma menüsü; tür renkleri `UI-02` kaynağından.
**Kapanış kontrolü:** `test_studio_review_gui.py`,
`test_studio_timeline_language.py`, `test_timeline_preview.py`; yeni test:
çizim sonrası araç `SCRUB`, sonraki tıklama yeni aralık çizmiyor; Esc sonrası
yarım interval kalmıyor.
**Geri dönüş:** iki dosya.

### F10 — 3B iskeletin görünümü
**Karşılanan:** `SKEL-01`, `SKEL-02`, `SKEL-03`
**Bağımlılık:** F1, F8.
**Modüller:** `views/skeleton3d.py`, `services/skeleton3d.py`,
`features/roles.py` (okuma), `theme/tokens.json`.
**Çıktı:** küresel düğümler (ölçümle seçilen yöntem: instanced küre mesh veya
impostor/billboard shader); yumuşatılmış kalın bağlantılar; anatomik renk
haritası (sağ kol kehribar, sağ bacak mercan, sol kol turkuaz, sol bacak
indigo, gövde nötr) **rol tablosundan** eşlenir, indeks varsayılmaz;
seçim halkası + boyut farkı, anatomik renk korunur; hover'da eklem adı;
NaN çizilmez, eksik uçlu edge orijine çekilmez; GL yoksa temiz durum.
**Şema/uyumluluk:** yok; yalnız görsel. Ham veri filtrelenmez.
**Kapanış kontrolü:** `test_studio_skeleton3d.py`; yeni Qt'siz testler: renk
eşlemesi rol tablosundan geliyor, bilinmeyen rol nötr; gerçek pencerede kare
süresi ölçümü (bütçe ≤ 8 ms). Gerçekte kullanılan `QSurfaceFormat.samples()`
raporlanır.
**Geri dönüş:** küresel düğüm yöntemi bütçeyi aşarsa impostor'a düşülür;
karar ve ölçüm rapora yazılır.

### F11 — Kamera etkileşimi, presetler, sabit zemin
**Karşılanan:** `CAM-01`–`CAM-04`, `PRESET-01`–`PRESET-03`, `FLOOR-01`
**Bağımlılık:** F10.
**Modüller:** `services/skeleton3d.py` (Qt'siz kamera matematiği),
`views/skeleton3d.py`.
**Çıktı:** sol sürükleme = ayakların zemin izdüşümünden geçen düşey eksen
etrafında yatay tur (elevation değişmez); orta tuş = gövde merkezli üst/alt
inceleme; tekerlek zoom; sağ sürükleme pan; merkezle/sığdır; kararlı referans
(ilk güvenilir duruştan kurulan pivot, her kare ayak gürültüsüne bağlanmaz);
7 preset + kayıt yönü + kişisel görünüm + önceki bakış; ~1,5 s zaman temelli,
en kısa yol, ease-in-out geçiş; elle giriş animasyonu anında devralır;
hareket azaltma ayarı; grid sabit fiziksel zemin.
**Şema/uyumluluk:** kamera durumu zaten `OrbitCamera.to_dict`; additive alanlar
eklenirse `from_dict` eskisini kayıpsız okur.
**Kapanış kontrolü:** Qt'siz testler: 350°→10° geçişi 20°; süre kare sayısına
bağlı değil; kutup kilitlenmesi yok; iki mod arasında sıçrama yok; pan/zoom
ham diziyi değiştirmiyor. Gerçek pencerede oynatma sırasında grid sabit.
**Geri dönüş:** kamera matematiği ayrı modülde; eski `orbit/pan` korunur.

### F12 — Offline zemin tespiti
**Karşılanan:** `FLOOR-02`, `FLOOR-03`, `FLOOR-04`
**Bağımlılık:** F11.
**Modüller:** `camera/zed.py`, `processing/jobs.py`, `processing/review.py`,
`studio/services/review.py`, `views/skeleton3d.py`, `export/`.
**Ön doğrulama (yapıldı):** `pyzed` 5.4'te `sl.Camera.find_floor_plane`,
`sl.Plane.get_plane_equation`, `get_normal`, `get_pose` mevcut; işleme hattı
zaten `enable_positional_tracking` çağırıyor (`camera/zed.py:351`), yani SVO
replay sırasında düzlem tespiti için gereken koşul sağlanıyor.
**Çıktı:** offline işleme sırasında düzlem normal + offset + referans dönüşümü
sürümlü türetilmiş çıktıya yazılır (yeni `floor_plane` bloğu, `job.json`
şeması artırılır); etiketlemede SDK **çalıştırılmaz**; grid bu düzlemden
çizilir; tespit başarısızsa gerekçeli "zemin bulunamadı"; eski sürümler
metadata'sız açılır ve "görsel referans" olarak işaretlenir.
**Şema/uyumluluk:** `PROCESSING_SCHEMA_VERSION` artar; okuyucu eksik bloğu
`None` sayar; ham koordinatlar ve eski sürümler yerinde değiştirilmez.
**Kanıt sınırı:** Gerçek SVO ile çalıştırılamazsa "doğrulanmadı" yazılır ve
tamamlandı iddia edilmez.
**Kapanış kontrolü:** `test_processing_artifacts.py`; yeni test: eksik
metadata'lı eski sürüm açılıyor; üç durum (`detected` / `visual_reference` /
`not_found`) ayrı; mümkünse gerçek SVO üstünde okuma-yalnız deneme.
**Geri dönüş:** blok additive; yazılmazsa eski davranış aynen sürer.

### F13 — Sağ panel: dikey ikon şeridi ve kamera araçları
**Karşılanan:** `PANEL-01`, `PANEL-02`
**Bağımlılık:** F8, F11.
**Modüller:** `views/pages/review.py`, yeni `views/iconstrip.py`.
**Çıktı:** panelin en sağında kamera/etiket/kişi kare ikonları; yatay yazılı
sekmeler kalkar; panel iskelete bitişik ve üst bandın ortak yüksekliğinde;
sekme değişimi paneli zıplatmaz; kamera sekmesinde preset butonları + hafif
pusula/küp + merkezle/sığdır/zemin/kaplama/kişisel görünüm/önceki bakış.
**Kapanış kontrolü:** yeni test: sekme değişiminde panel genişliği sabit;
ikon şeridi viewport'a taşmıyor; pusula ikinci bir 3B sahne kurmuyor.
**Geri dönüş:** `QTabWidget`'e dönüş tek commit.

### F14 — Etiket sekmesinin üç görünümü
**Karşılanan:** `LABEL-01`, `LABEL-02`, `LABEL-03`, `LABEL-04`
**Bağımlılık:** F9, F13.
**Modüller:** `views/pages/review.py`, `viewmodels/review.py`.
**Çıktı:** etiket ikonu → özet; timeline'da hareket kutusuna tek tıklama →
hareket düzenleyicisi; hata kutusuna tek tıklama → hata düzenleyicisi; doğru
aralık ilk tıklamada seçili; ikon bağlamı nötr/mavi/mercan; özet kompakt
hareket kartları (sınıf, aralık, süre, hata sayısı, hazır/eksik) + açılabilir
hatalar; sınıflar buton olarak, arama/kaydırma ile; "Hareket sınıfı ekle"
yer tutuculu kutu + Ekle; yeni sınıf anında listede ve açık aralığa atanır,
panel açık kalır.
**Veri sözleşmesi:** mevcut türetilmiş `Correctness`/`Readiness` modeline
ikinci boolean eklenmez. İncelenmemiş hareket yeşil olmaz.
**Kapanış kontrolü:** `test_studio_review.py`, `test_studio_review_gui.py`,
`test_label_dialog_class_creation.py`; yeni test: tek tıklama davranışları;
`Readiness.UNREVIEWED` yeşil değil.
**Geri dönüş:** panel görünümleri `QStackedWidget` içinde; eski sayfalar kalır.

### F15 — Hata sınıfı eklem kalıcılığı ve 3B eklem seçimi
**Karşılanan:** `JOINT-01`, `JOINT-02`, `JOINT-03`, `JOINT-04`, `EXPORT-02`
**Bağımlılık:** F10, F14.
**Modüller:** `domain/labels.py`, `dataset/workspace.py`,
`annotations/repository.py`, `studio/services/annotation_store.py`,
`viewmodels/review.py`, `views/pages/review.py`, `views/skeleton3d.py`,
`export/` okuyucuları.
**Çıktı:**
- `LabelOption` additive alanlar: `default_roles: tuple[str, ...]`,
  `roles_revision: int`. `LABEL_SCHEMA_VERSION` → `2.1.0`.
- Yeni hata sınıfı akışı: ad → taslak → 3B seçim modu → çift tıklama ile
  çoklu seçim → geçerli ad + ≥1 eklem ile Ekle → sınıf kaydedilir ve açık
  aralığa atanır; panel açık kalır, normal moda döner.
- Aralığa yazılan `affected_roles` **snapshot**'tır; sınıfın sonradan
  değişmesi eski aralıkları değiştirmez. Köken ayrımı için `ErrorInterval`'a
  additive `roles_origin` (`class_default` | `reviewed`) ve
  `roles_revision` alanları; `CANONICAL_ANNOTATION_SCHEMA_VERSION` → `1.2.0`,
  `ANNOTATION_SCHEMA_VERSION` → `2.3.0`.
- `JointStatus.SELECTED` anlamı korunur; sınıf varsayılanından aktarılan
  ilişki "bu aralıkta incelendi" sayılmaz.
- Picking: gerçek projeksiyon + DPI + derinlik; sürükleme eşiği ile çift
  tıklama ayrımı; boşluğa çift tıklama hiçbir eklem seçmez; mod yalnız sınıf
  oluşturma/eklem düzenleme sırasında etkin.
**Şema/uyumluluk:** üç şema sürümü artar; eksik alanlar eski anlamına düşer
(`roles_origin` yoksa `reviewed` **değil**, `unknown` sayılır ve öyle
raporlanır). Export eşlemeleri aynı fazda güncellenir. Yazım atomik: sınıf
kaydı + aralık ataması tek kullanıcı eylemi, hata durumunda ikisi de geri alınır.
**Kapanış kontrolü:** `test_annotations.py`, `test_export_joint_evidence.py`,
`test_export_canonical.py`, `test_joint_annotation_gui.py`,
`test_joint_evidence.py`; yeni testler: sınıf eklemleri değişince eski aralık
değişmiyor; eski (alan içermeyen) belge kayıpsız okunuyor; farklı skeleton
modelinde rol eşlemesi kayıpsız; picking/kamera ayrımı.
**Geri dönüş:** alanlar additive; yazmayı kapatmak eski davranışa döndürür.

### F16 — Kişi sekmesi, Veri Seti, Dışa Aktarım
**Karşılanan:** `PERSON-01`, `DATA-01`, `EXPORT-01`, `EXPORT-02` (UI tarafı)
**Bağımlılık:** F13, F15.
**Modüller:** `views/subject.py`, `views/pages/dataset.py`,
`views/pages/export.py`, ilgili viewmodel'ler.
**Çıktı:** kişi sekmesi mevcut aday/önizleme/belirsiz aralık akışını korur;
Veri Seti'nde kompakt kapsam sayımları + sağ ayrıntı + "düzeltmeye git"
(doğru sürüm/aralık/sekme); Dışa Aktarım solda doğrulama, sağda paket
seçenekleri/hedef/özet/yazma; boş/yükleniyor/hazır/uyarı/engel durumları açık;
son kontrol ile yazım arasında değişiklik olursa bayat "hazır" kullanılmaz.
**Kapanış kontrolü:** `test_studio_subject_gui.py`, `test_studio_export_gui.py`,
`test_export_gui.py`; yeni test: bayat preflight reddi; "düzeltmeye git"
doğru kaydı açıyor.
**Geri dönüş:** sayfa dosyaları bağımsız.

### F17 — Performans, görsel kabul ve doğrulama raporu
**Karşılanan:** `PERF-01`, `PERF-02`, `VERIFY-01`, `VERIFY-02`, `VERIFY-03`
**Bağımlılık:** bütün fazlar.
**Çıktı:** önce/sonra karşılaştırması (yukarıdaki bütçe tablosu);
görünmeyen sayfada timer/render yok; kamera geçişi bitince timer durur;
sızıntı kontrolü (tekrarlı aç/kapat/iptal); gerçek pencerede 1120×700,
1600×900, 1920×1080 ve %100/%125/%150 ölçek, iki tema; boş/yükleniyor/dolu/
uzun isim/çok öğe/seçili/devre dışı/hata durumlarının görsel incelemesi;
canlı/offline/mock kanıtın ayrı raporlanması.
**Çıktı dosyası:** [doğrulama raporu](../reports/studio-gui-refinement-validation.md).

## 4. Kapsam tablosu

Durum sözlüğü: `planlandı` · `uygulandı` · `doğrulandı` · `kısmi` · `engelli`.
`doğrulandı` = bu ortamda **çalıştırılmış** bir kontrol veya ölçüm var.
`uygulandı` = kod yerinde, ama iddiayı kapatan koşu yapılmadı.

| Gereksinim | Faz | Uygulama durumu | Doğrulama kanıtı | Açık sınır |
|---|---|---|---|---|
| UI-01 | F1 | uygulandı | token testleri + gerçek pencere | — |
| UI-02 | F1 | doğrulandı | palet/kontrast testleri + 3B üstünde anatomik renk turu | — |
| UI-03 | F1 | uygulandı | 42 ikon render testi | — |
| UI-04 | F1 | doğrulandı | ContextField testi + ekran görüntüsü | — |
| LOGIN-01 | F3 | doğrulandı | font/glif/ölçü testleri + gerçek pencere | — |
| LOGIN-02 | F3 | doğrulandı | 23 test + 1366×768 ölçüm | — |
| CAP-01 | F4 | doğrulandı | konum testleri + ekran görüntüsü | — |
| CAP-02 | F4 | doğrulandı | sıra/tek satır/kayma testleri | — |
| CAP-03 | F4 | uygulandı | dört durum + sayaç testleri | canlı kayıt ölçümü donanım gerektirir |
| PROC-01 | F5 | doğrulandı | yan yana + %40/60 testleri | — |
| PROC-02 | F5 | doğrulandı | filtre/sayım/ilerleme testleri | — |
| LIB-01 | F6 | doğrulandı | %55/45 + gruplama testleri | — |
| LIB-02 | F6 | doğrulandı | boyut ayrımı + geç sonuç testleri | — |
| LOAD-01 | F7 | doğrulandı | izole deney + gerçek pencerede winId sabit | — |
| LOAD-02 | F7 | doğrulandı | 2.7 GB gerçek sürümde 210 ölçüm, ETA hatası ~%1.5 | — |
| LOAD-03 | F7 | doğrulandı | gerçek sürüm 0.57 s'de açıldı, ilk kullanılabilir ekran 0.64 s | — |
| LOAD-04 | F7 | doğrulandı | iptal/yarış testleri | — |
| LAYOUT-01 | F8 | doğrulandı | üç bant + başlık testleri | — |
| LAYOUT-02 | F8 | doğrulandı | 21 geometri testi + %100/%125/%150 turu | — |
| SKEL-01 | F10 | doğrulandı | point-sprite ölçümü 0→10484 px; 1.0 ms/kare | — |
| SKEL-02 | F10 | doğrulandı | rol tablosu testleri + görsel | — |
| SKEL-03 | F10 | doğrulandı | seçim halkası + picking 200/200 isabet | — |
| CAM-01 | F11 | doğrulandı | turn() testleri + gerçek pencerede preset turu | fare sürükleme el ile denenmedi |
| CAM-02 | F11 | doğrulandı | inspect() testleri | — |
| CAM-03 | F11 | uygulandı | zoom/pan/merkezle | — |
| CAM-04 | F11 | doğrulandı | pivot/hedef testleri | — |
| FLOOR-01 | F11 | doğrulandı | grid ayak altında + merkezli, görsel | — |
| FLOOR-02 | F12 | doğrulandı | gerçek SVO'da 0.02 s'de detected | — |
| FLOOR-03 | F12 | doğrulandı | şema + referans uzayı testleri | hareketli kamera doğrulanmadı |
| FLOOR-04 | F12 | doğrulandı | dört durum ayrımı testleri | — |
| PRESET-01 | F11 | doğrulandı | sabit referans testleri | — |
| PRESET-02 | F11 | doğrulandı | en kısa yol + 1.51 s ölçümü | — |
| PRESET-03 | F11 | uygulandı | kesme/kuyruk testleri | — |
| PANEL-01 | F13 | doğrulandı | ikon şeridi testleri + gerçek pencere | — |
| PANEL-02 | F13 | doğrulandı | görünüm değişince panel genişliği sabit | — |
| LABEL-01 | F14 | doğrulandı | tek tık + bağlam testleri; bulunan gerçek hata düzeltildi | — |
| LABEL-02 | F14 | doğrulandı | kart/sayım/hazırlık testleri | 40 kart üstü sayılıyor |
| LABEL-03 | F14 | doğrulandı | buton picker + kısayol testleri | — |
| LABEL-04 | F14 | doğrulandı | diyalogsuz sınıf oluşturma testleri | — |
| JOINT-01 | F15 | doğrulandı | eklemsiz sınıf reddediliyor (şema + GUI) | — |
| JOINT-02 | F15 | doğrulandı | picking yalnız taslak sırasında açık | — |
| JOINT-03 | F15 | doğrulandı | çift tık çoklu seçim, panel açık kalıyor | — |
| JOINT-04 | F15 | doğrulandı | miras eklemler `class_default`, `reviewed` değil | canonical annotation 1.2.0, release 1.1.0 |
| PERSON-01 | F16 | uygulandı | panel içerik olarak korundu, export kapısı şeritte görünür | bilinen kişi eşleştirme açığı ayrı takip |
| TOOL-01 | F9 | doğrulandı | tek satır + ikon/ad testleri | — |
| TOOL-02 | F9 | doğrulandı | çizim sonrası Gez testleri | — |
| TOOL-03 | F9 | doğrulandı | hız/döngü/taşma testleri + gerçek aralıkta 4 döngü testi | — |
| DATA-01 | F16 | doğrulandı | 11 test: eylem sürümü taşıyor, hedefi olmayan engelleyici buton almıyor | — |
| EXPORT-01 | F16 | doğrulandı | iki sütun + altı durum testleri | — |
| EXPORT-02 | F15+F16 | doğrulandı | bayat sonuç yazmayı reddediyor; `build_release` zaten yeniden denetliyor | — |
| NOTICE-01 | F2 | doğrulandı | sayfa geçişi regresyon testleri | — |
| NOTICE-02 | F2 | doğrulandı | iki tema × dört ekran, merkez isabeti toast içinde | — |
| PERF-01 | F17 | doğrulandı | gerçek pencerede önce/sonra tablosu | GPU ve canlı kayıt kaybı **ölçülemedi** |
| PERF-02 | F17 | doğrulandı | timer/sızıntı/mesh testleri + gerçek pencere ölçümü | — |
| VERIFY-01 | her faz + F17 | doğrulandı | offscreen 83/84 + windows 18/18; tek düşüş bilinen aralıklı yarış (izole 3/3) | tam pytest tek süreçte hâlâ bitmiyor (`open`) |
| VERIFY-02 | fazlara dağıtıldı | doğrulandı | 6 ekran × 3 boyut × 3 ölçek, kırpılma yok | 3 tabloda 1–2 px yatay kayma |
| VERIFY-03 | F17 | doğrulandı | iki tema × dört ekran, bildirim merkezinde isabet 8/8 | — |

## 5. İlerleme günlüğü

Her faz bittiğinde bu bölüme yazılır: yapılan iş, gerçekten çalıştırılan
kontroller ve sonuçları, açık noktalar, sıradaki adım.

### F1 — Ortak görsel dil · tamamlandı

**Yapılan.** `tokens.json` 1.2.0'a çıkarıldı: 16 yeni ölçü (eşit kontrol
yükseklikleri, kare ikon butonu, ikon şeridi, panel/timeline asgari ölçüleri,
timeline dolgu alfaları, düğüm/kemik ölçüleri, kamera geçiş süresi), marka
fontu ve display punto token'ı, iki temada 13 yeni renk (anatomik palet, panel
bağlam renkleri, ortak sahne yüzeyi, zemin grid'i). 39 Lucide ikonu eklendi
(ISC, mevcut lisans dosyası kapsıyor) ve `iconset.ICON_NAMES` ürün sözlüğüyle
eşlendi; `record` destinasyon ikonu korunarak eylem ikonları `record-start` /
`record-stop` olarak ayrıldı. QSS'e `iconButton`, `stripButton`, `record`
varyantı, `stage` yüzeyi, `brandMark` ve üç bağlam rengi kuralı eklendi.
Timeline aralık dolguları token'lı alfaya taşındı (opak blok yerine saydam
dolgu + tam güçte kenar; seçili aralık daha güçlü dolgu ve 2 px kenar), statik
katman anahtarına `_selected` eklendi.

**Üst çubuk.** `ContextState.OK` artık ikon çizmiyor (`UI-04`): kullanıcı,
proje, veri klasörü ve disk yanındaki dekoratif yeşil onay işaretleri kalktı,
uyarı/hata/bilinmiyor ikonları durdu. Erişilebilir ad hâlâ "tamam" diyor.

**Çalıştırılan kontroller.** `test_studio_theme.py` (40), `test_studio_layers.py`
(11), `test_studio_polish.py` + `test_shell_chrome_gui.py`, `test_studio_shell_gui.py`
+ `test_studio_timeline_language.py`, `test_studio_toasts.py`,
`test_gui_painting.py` — hepsi yeşil. Yeni `tests/test_studio_visual_language.py`
(72 test) yeşil. Gerçek pencerede 1600×900 koyu ve 1120×700 açık temada görsel
inceleme yapıldı; yeşil onay işaretlerinin kalktığı görüntüyle doğrulandı.

**Açık nokta.** Anatomik palet ilk denemede kehribar/mercan ayrımı 54 birimdi;
ölçüm sonucu tonlar ayrıldı (koyu temada en kötü uzaklık 87, açıkta 66).

### F2 — Bildirim katmanı · tamamlandı

**Kök neden (verified).** `ToastLayer`, `QStackedWidget`'in çocuğuydu.
`QStackedLayout::setCurrentIndex` geçilen sayfayı `raise()` ederek kardeşlerin
üstüne çıkarıyor; mesaj gösterilirken yapılan tek seferlik `raise_()` sonraki
sayfa geçişinde geçersiz kalıyordu. Ölçüm: sayfa değişiminden sonra toast'ın
kendi merkezinde `childAt` sayfayı döndürüyordu.

**Yapılan.** Sayfa yığını `page_area` adlı bir kapsayıcıya alındı; toast
katmanı artık sayfaların değil bu kapsayıcının çocuğu. Sayfa geçişinde
ayrıca `toasts.raise_()` çağrılıyor (native çocuk büyüten sayfalar için
emniyet). Katman yine yalnız kartların kapladığı alan kadar; boş yerdeki
tıklamalar sayfaya gidiyor.

**Çalıştırılan kontroller.** `test_studio_toasts.py` 20 test yeşil; içlerinde
yeni olanlar: dört ayrı sayfaya geçtikten sonra kartın merkezindeki widget
hâlâ kart; art arda 12 sayfa geçişinden sonra da öyle; sayfa değiştikten sonra
Kapat gerçekten kapatıyor; mesaj gösterimi RGB/iskelet/timeline geometrisini
değiştirmiyor. Gerçek pencerede 1120×700 açık temada bildirim tam görünür,
metni okunur, üç eylemi de erişilebilir.

### F3 — Giriş ekranı · tamamlandı

**Yapılan.** Space Grotesk değişken fontu (`SpaceGrotesk[wght].ttf`, 136 676
bayt, SHA-256 `acad6de1…`) ve `OFL.txt` lisansı
`studio/views/fonts/` altına paketlendi; `pyproject.toml` package-data'ya
eklendi. `views/fonts/__init__.py` fontu süreç başına bir kez Qt'ye kaydediyor,
yüklenemezse sessizce token'daki fallback zincirine düşüyor. Tema uygulanırken
(`theming.apply_application_theme`) kaydediliyor.

Giriş ekranı yeniden yazıldı: logonun altındaki ayrı "Yıldız Teknik
Üniversitesi" yazısı kaldırıldı (ad artık yalnız markanın kendisinde ve
erişilebilir adda), logo 168 → 190 px (%13), "KineCapture Studio" marka
fontuyla 34 px, `QFormLayout` yerine tek sütunlu kutu listesi, etiketler yer
tutucuya taşındı, erişilebilir adlar ayrı tutuldu, parola göster/gizle kutunun
içinde trailing action olarak, giriş butonu form genişliğinde, ikincil bağlantı
altta ortalı, arka planda statik (animasyonsuz) ışık geçişi.

**Ölçülen sonuç (gerçek pencere, 1366×768).** Marka yazısı `Space Grotesk`
34 px; logo 190×190; altı kutunun hepsi 360×38; birincil buton 360 geniş;
logo/kutular/buton merkez ekseni 677 px'te aynı.

**İki gerçek hata bulundu ve düzeltildi.**
1. `QRawFont.supportsCharacter` PySide6 6.10.1'de bu font için on iki Türkçe
   harfin tamamına `False` dedi; `glyphIndexesForString` gerçek (sıfır olmayan)
   glif indeksleri döndürüyor ve fontun kendi cmap'i on ikisini de içeriyor.
   Glif kontrolü indeks temelli yeniden yazıldı.
2. Giriş formu hatalı alanı `kcStatus="error"` ile işaretliyordu; stil sayfası
   `kcState="error"` kuralını arıyor. Reddedilen alan hiç kırmızıya dönmüyormuş;
   `kcState`'e çevrildi.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_auth_gui.py` 23 test yeşil
(font paketi + lisans, Qt kaydı, Türkçe glifler, font yokken çökmeme, fallback
zinciri, yer tutucu davranışı, ortak genişlik/yükseklik, ortak merkez ekseni,
buton genişliği, ikincil bağlantının konumu, kutu içi göster/gizle, Tab sırası,
Enter ile giriş, parolanın temizlenmesi, hata işareti, tema geçişi, statik arka
plan). `test_studio_brand.py` 21 test yeşil (ayrı üniversite yazısının
kalkışını doğrulayacak biçimde güncellendi).

### F4 — Yakalama · tamamlandı

**Yapılan.** `StudioPage` içine `add_header_action` eklendi (başlık satırının
sağ ucu). `Bağlan` oraya taşındı: artık "Yakalama" başlığıyla aynı hizada,
kayıt hedefi panelinin üzerinde. Transport ve telemetri tek satırda birleşti;
sıra `Kayıt → Süre → FPS → Kayıt kaybı → Önizleme kaybı → Diskte kalan →
İşaret koy`. `_Metric` dikeyden yataya çevrildi ve mono değerine en geniş
okumanın genişliği ayrıldı. Kaydedilen kare sayısı ayrı sütun olmaktan çıkıp
Süre'nin ipucuna taşındı. Kayıt butonu `kcVariant="record"` (kırmızı) ve dört
durumu ayrı ikon + ayrı cümle ile veriyor: idle (daire), counting (kare),
recording (kare), stopping (spinner); devre dışı hâli gri.

**İki gerçek hata bulundu ve düzeltildi.**

1. Sağ konsol 900 px yükseklikte kendi asgarisinden dar kalıyordu; QVBoxLayout
   bu durumda kırpmıyor, **üst üste biniyor** — ekran görüntüsünde
   "Süre sonunda dur" yazısı "Önizlemeyi aynala" üzerine basılıyordu. Konsol
   yalnız gerektiğinde kayan bir `QScrollArea` içine alındı.
2. Geri sayım başlayınca FPS ve iki kayıp sayacı sağa kayıyordu. Geri sayıma
   sabit genişlikte bir yuva verildi; satır artık hiç oynamıyor. Ayrıca
   telemetri değerindeki `kcStatus="error"` pill'i iki karakterlik bir sayının
   etrafında kırpılmış kontrol gibi görünüyordu; mono değerler için pill'i
   nötrleyip yalnız renklendiren QSS kuralı eklendi.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_capture_row.py` 20 test
yeşil (satır sırası gerçek koordinatlardan ölçülüyor; tek bant; dikey ortalama;
sayı büyüyünce satır kaymıyor; geri sayım satırı kaydırmıyor; dört kayıt
durumu ayrı; STOPPING'de buton kapalı; iki kayıp sayacı ayrı kaynaklardan;
tekrarlı repaint sayacı sıfırlamıyor; konsol kontrolleri üst üste binmiyor).
`test_studio_capture.py`, `test_studio_capture_target.py`,
`test_capture_subject_gui.py`, `test_studio_recording_visible.py` yeşil.
Gerçek pencerede beş durumun şerit görüntüsü alındı.

### F5 — Verileri Hesapla · tamamlandı

**Yapılan.** İki tablo üst üste yerine `QSplitter` ile yan yana; oran %40/%60
ve pencere yeniden boyutlanırken korunuyor (kullanıcı kolu tutana kadar).
Solda arama + katılımcı filtresi (ikisi birlikte daraltıyor), çoklu seçim,
seçili kayıt özeti (katılımcı, süre, kare, önceki deneme, etkin profil) ve
başlatma eylemleri. Sağda dört durum sayımı (sırada/çalışıyor/tamamlandı/
sorunlu), iş tablosu, ilerleme çubuğu ve iş eylemleri. `SearchProxy` içine
`set_required` eklendi; arama ile filtre birbirini silmiyor.

**Pre-existing bir hata bulundu ve düzeltildi (kapsam dışı ama engelleyiciydi).**
`tests/test_studio_processing.py` içindeki `recorded` fixture'ı **dokuz testi
setup'ta düşürüyordu** ve bu benim değişikliklerimden önce de böyleydi (temiz
ağaçta `git stash` ile doğrulandı). Neden: 17 Eylül'de eklenen kişi seçimi
kapısı kişi işaretlenmeden kayıt başlatmayı reddediyor; fixture
güncellenmemişti. `tests/conftest.py` zaten tam bu iş için `choose_subject`
yardımcısı taşıyordu; fixture onu kullanacak biçimde düzeltildi. İkinci bir
uyarlama: kişi işareti kayıt açılmadan **önceki** önizleme karesinden geldiği
için işleme `subject_anchor_before_recording` notu bırakıyor — gerçek ZED
kayıtlarında da aynı not var — bu yüzden testin "temiz bitti" ölçütüne tolere
edilen not olarak eklendi.

Ara bir yanlış yol not edilmeye değer: fixture'ı `live_skeleton` moduna almak
kaydı `processing_status == "live"` yapıyor, yani **legacy** sayılıp kuyruktan
tamamen düşüyor. O yol "düzeltir" gibi görünüp başka türde bir kaydı test
ederdi.

**Çalıştırılan kontroller.** `test_studio_processing.py` 17 test yeşil (daha
önce 9'u setup'ta düşüyordu). Yeni `tests/test_studio_processing_layout.py`
15 test yeşil (yan yana; %40/60; çok satırda okunabilirlik; arama; filtre;
ikisinin birlikte daralması; çoklu seçim; seçim özeti; kuyruk sayımları;
sorunlu sayımının işaretlenmesi; toplam bildirilmemişken yüzde yok;
bildirilmişken gerçek yüzde; eylemlerin seçili işe bağlanması; uzun profil
ayrıntısının katlı kalması). Gerçek pencerede görsel inceleme yapıldı.

### F6 — İşlenen Videolar · tamamlandı

**Yapılan.** Bölünme %55/%45 ve resize boyunca korunuyor. Önizleme 240 → 420 px
ve kaynağın kendi en-boy oranını koruyor (sabit 16:9 kutu yok); panel
genişledikçe yeniden ölçekleniyor. Aynı kaydın sürümleri listede gruplu
(`LibraryService.grouped`), her biri hâlâ ayrı seçilebilir/etiketlenebilir;
"Sürüm" sütunu `2 / 3` diyor. Ayrıntı paneli katılımcı, tarih, süre, kare,
model, derinlik, fitting, şema, **sürüm boyutu**, **ham kayıt boyutu**, sporcu
ve etiket durumunu hizalı çiftler hâlinde veriyor. Uyarılar tek satır özet +
açılabilir tam liste.

**Boyut sözleşmesi.** `LibraryService.sizes_for` iki ayrı sayı döndürüyor:
türetilmiş sürümün klasörü ve **kaydın** `raw/` klasörü. Ham kayıt sürüme
eklenmiyor; üç kez işlenmiş bir kaydın 2 GB SVO'su üç kez sayılmıyor.
Okunamayan klasör `None` (`—`) döner, asla `0 B` değil.

**Asenkron ve yarış güvenliği.** Ölçüm worker'da; her seçim bir token artırıyor,
geç gelen sonuç yeni seçimin üstüne yazmıyor ama önbelleğe alınıyor. Ölçüm
sürerken panel "ölçülüyor…" diyor, önceki sürümün sayısını bırakmıyor.

**Çalıştırılan kontroller.** `test_studio_library.py` 33 test yeşil. Yeni
`tests/test_studio_library_layout.py` 15 test yeşil (%55/45; gruplama; grup içi
sıra; `2 / 3`; her sürümün ayrı seçilebilirliği; `None` ≠ `0 B`; birim
biçimlendirme; ham kaydın sürüm başına sayılmaması; okunamayan klasör; iki
boyutun ayrı gösterilmesi; A→B sırasında geç ölçümün düşmesi; ölçülürken
uydurma sayı olmaması; uyarı özeti + katlama; temiz sürümde uyarı satırı yok;
sayfada video çözücü kullanılmadığının kaynak denetimi).

### F7 — Etiketlemeye giriş · tamamlandı

**`LOAD-01` — kök neden giderildi ve ölçüldü.** İzole deneyle üç düzenek
karşılaştırıldı (gerçek pencere):

| Düzenek | winId | Sonuç |
|---|---|---|
| primer yok | 983812 → 1049348 | **yeniden oluşturuldu** |
| `show()` öncesi 1×1 gizli `QOpenGLWidget` | 2754504 → 2754504 | değişmedi |
| aynı widget görünür | 1245956 → 1245956 | değişmedi |

Shell içine `_prime_gl_surface` eklendi: merkezi widget'ın çocuğu olarak 1×1,
`WA_DontShowOnScreen`, hiç gösterilmeyen bir `QOpenGLWidget`. Üst pencere
baştan RHI destekli oluşuyor. Gerçek uygulamada yeniden ölçüldü:
**`native_window_recreated=False`**, ilk geçiş 1564 → 1069 ms. Bu bir hide/show
örtmesi değil; native pencere hiç değişmiyor.

**`LOAD-02` — gerçek ilerleme.** `verify_checksum_manifest` isteğe bağlı
`progress(done, total)` ve `cancelled()` aldı (additive; mevcut çağıranlar
etkilenmedi). `ReviewDataset` → `ReviewSession.open` → `ReviewViewModel`
zinciri aşama bildiriyor: `job → verify → map → video → skeleton → ready`.
Yalnız `verify` ölçülebilir olduğu için yüzde ve ETA **yalnız orada** var;
diğerleri adım olarak belirsiz çubukla gösteriliyor. ETA ancak %8'den sonra ve
yalnız bu makinede gözlenen hızdan hesaplanıyor.

Gerçek ölçüm (kullanıcının 2.7 GB'lık sürümü, okuma-yalnız, iki koşu):

| | |
|---|---|
| Bildirilen toplam | 2 703 157 059 bayt (gerçek) |
| İlerleme okuması | 210 adet, monoton |
| %50'de ETA tahmini | 7.10 s / 7.07 s |
| Gerçek açılma | 7.19 s / 7.19 s (hata yaklaşık %1.5) |
| `prepare_video` (artık worker'da) | 48 ms |
| `prime` (ilk 3B pencere, worker'da) | 1.3 ms |

**`LOAD-03` — birlikte açılış.** Sayfa artık `editor`/`loading` yığını. `busy`
worker döndüğünde **kapanmıyor**; ekran timeline'ı, panelleri ve ilk senkron
kareyi kurduktan sonra `viewmodel.ready()` çağırıyor. Video ve iskelet aynı
`position` değerinden aynı anda çiziliyor. `busy` kapandığında sürüm açık
değilse editör değil boş durum gösteriliyor.

**`LOAD-04` — iptal ve yarışlar.** `cancel_open()` token'ı artırıp busy'yi
kapatıyor; checksum yürüyüşü dosya sınırında duruyor ve `Cancelled` fırlatıyor,
geç gelen sonuç token uyuşmazlığından düşüyor. Boş durum ve hata durumu tek
hazırlık yüzeyinde, "Vazgeç" / "Yeniden dene" ile.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_review_loading.py` 17 test
yeşil (primer var ve gizli; ilk girişte winId değişmiyor; 12 tekrarlı geçişte
de değişmiyor; pencere boyutu korunuyor; checksum gerçek bayt bildiriyor ve
monoton; iptal yürüyüşü durduruyor; denominatörsüz aşamada yüzde yok; ölçülen
aşamada yüzde ve süre; her aşamanın cümlesi var; belirsiz çubuk; gerçek sayı;
editör hazır olmadan görünmüyor; busy yalnız ekran tarafından kapanıyor;
`ready()` idempotent; iptal temiz boş durum bırakıyor; boşta iptal etkisiz;
iptal kendi sonucunu geçersizleştiriyor). `test_studio_review_open.py` (7),
`test_studio_review.py` + `test_studio_review_gui.py` (31),
`test_review_flow.py` + `test_processing_artifacts.py` + `test_storage.py` (79)
yeşil.

### F8 — Etiketleme yerleşimi · tamamlandı

**Yapılan.** Sayfa başlığı ve `run_id · N kare` satırı kaldırıldı
(`StudioPage._header` gizlendi); kayıt kimliği sağ panelin ilk satırına taşındı.
Sayfa üç yatay bant: ortak çerçeveli çalışma yüzeyi, tek araç satırı, timeline.
Splitter yerine çözülen geometri kullanılıyor — bir splitter kolu, görüntünün
kırpılması gereken bir yere sürüklenebilirdi.

**Geometri.** Yeni Qt'siz `services/stage_layout.py`. RGB oranı sürümün kendi
metadata'sından (`processing_camera.resolution`); 16:9 yalnız hiçbir şey
bildirilmediğinde kullanılan, tek yerde geçen fallback. 3B viewport kare
(`skeleton_width == height`). Panel önce rahat genişliğini istiyor, bandı
kendi tabanının altına itecekse geri veriyor; asla asgarisinin altına inmiyor.
Pencerenin kullanamadığı genişlik `spare_width` olarak bildiriliyor ve bant
ortalanıyor — hiçbir şey esnetilmiyor.

Ölçülen (1850×760, 16:9): **884 / 497 / 465** — brifingin örnek olarak verdiği
890/500/460'a aritmetiğin kendiliğinden vardığı yer. Gerçek pencerede
1600×900'de 693/390/465 ölçüldü.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_stage_layout.py` 21 test
yeşil (kare viewport; altı farklı kaynak oranında esneme/kırpma yok; portre
kaynak; fallback'in tek yerde olması; panel asgarisi; timeline'ın kendi
yüksekliği; pencereyle büyüme; genişleyen pencerede panelin de büyümesi;
panelin rahat genişlikte durması; kullanılamayan genişliğin bildirilmesi;
çok küçük pencerede tutarlı yanıt; NaN oran). Yeni
`tests/test_studio_review_bands.py` 18 test yeşil.

### F9 — Tek araç satırı · tamamlandı

**Yapılan.** Video altındaki transport şeridi ile timeline üstündeki çizim
şeridi tek satırda birleşti. Sıra: transport · konum · döngü/hız · Gez/hareket/
hata · yapışma/zoom · geri al/yinele · sonraki eksik · ilerleme · kaydetme
durumu. Bütün butonlar aynı kare ölçüde (`kcRole="iconButton"`), gruplar ince
ayırıcılarla. Hareket çiz ve hata çiz iki ayrı ikon.

`TOOL-02`: bir aralık çizilip bırakıldığında araç kendiliğinden `Gez`'e
dönüyor; yeni aralık seçili kalıyor ve düzenleyicisi açılıyor. Esc/odak
kaybı/çok kısa sürükleme de `Gez`'e dönüyor — reddedilen bir çizim gizli
silahlı araç bırakmıyor.

`TOOL-03`: seçili aralığı döngüde oynatma ve 0.25×/0.5×/1×/2× hız. Hız yalnız
saati değiştiriyor; kare indeksi, zaman damgası ve ölçüm dizileri
dokunulmuyor. Dar pencerede ikincil kontroller taşma menüsüne giriyor;
oynatma ve üç araç asla katlanmıyor.

**Çalıştırılan kontroller.** `test_studio_review_bands.py` içindeki TOOL
testleri yeşil; ayrıca boş timeline'da çizim aracının reddedilmesi kuralının
korunduğu ayrı testle sabitlendi.

### F10 — 3B iskeletin görünümü · tamamlandı

**İki sürücü gerçeği ölçüldü — ikisi de koddan görünmüyordu.**

1. `QSurfaceFormat.setSamples(4)` *isteniyor*, sürücü **0** veriyor
   (canlı context'ten okundu, istekten değil). Brifingin "kodda 4x sample
   isteği var" gözlemi doğru ama istek hiç karşılanmıyormuş; kenarların
   merdivenli görünmesinin sebebi bu. Bu yüzden yumuşatma MSAA'ya değil,
   shader'da `fwidth` tabanlı analitik kenar solmasına bağlandı.
2. Qt burada **OpenGL 4.6 Compatibility** profili veriyor. O profilde
   `gl_PointCoord`, `GL_POINT_SPRITE` etkin değilse tanımsızdır ve küre
   shader'ı her fragmanı atıyordu. Ölçüm: eklemler **0 piksel** çiziyordu;
   aynı noktalar düz shader'dan 10482 piksel çiziyordu. `GL_POINT_SPRITE`
   etkinleştirildikten sonra küre shader'ı 10484 piksel çiziyor.

**Yapılan.** Eklemler tek vertex'lik point sprite olarak küre gibi gölgeleniyor
(mesh yok, vertex maliyeti yok). Kemikler `GL_LINES` yerine kameraya dönen
iki üçgenlik şeritler; uçtan bakıldığında bile alanı var, her açıda aynı
kalınlıkta. Renkler `services/skeleton_palette.py` üzerinden **rol tablosundan**
geliyor: sağ kol kehribar, sağ bacak mercan, sol kol turkuaz, sol bacak indigo,
gövde nötr, bilinmeyen rol nötr ve "unknown" olarak adlandırılıyor. RGB
kaplaması aynı semantiği kullanıyor. Seçili düğüm anatomik rengini koruyarak
halka ve boyut farkı alıyor; hover eklem adını gösteriyor; NaN çizilmiyor,
eksik uçlu kemik orijine çekilmiyor.

**Ölçülen performans** (gerçek 1370 karelik sürüm, 390×388 viewport,
take boyunca 63 kare): medyan **0.95–1.07 ms**, p95 **1.41–1.66 ms**,
maks **1.89–2.56 ms**. Bütçe 8 ms idi.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_skeleton_view.py` 41 test
yeşil (rol→uzuv eşlemesi; indeks yerine rol tablosu — aynı indeks iki formatta
farklı eklem; üç ZED formatında sol/sağ karışmaması; gövde-uzuv kemiği;
bilinmeyen eklemli kemik; etiketler; kemik şeridi geometrisi; eksik uçlu
kemiğin düşmesi; uçtan bakışta alan; sabit genişlik; projeksiyon; kameranın
arkasındaki nokta; üst üste düğümde yakının seçilmesi; boşluğa tıklamada
seçim olmaması).

### F11 — Kamera ve sabit zemin · tamamlandı

**Yapılan.** `CAM-01` sol sürükleme yalnız yatay tur (`turn`); elevation
değişmiyor, dikey fare hareketi üstten/alttan dönüşe çevrilmiyor. `CAM-02`
orta tuş gövde merkezi etrafında üstten/alttan inceleme (`inspect`).
`CAM-03` tekerlek zoom, sağ sürükleme pan, merkezle/sığdır.
`CAM-04` tur ekseni ve bakış hedefi **ayrı kavramlar** ve ikisi de bir kare
yerine bir pencere üzerinden bir kez kuruluyor: eksen ayakların zemin
üzerindeki ortasından, hedef kalçalardan. Ayak bulunamazsa son geçerli değer
korunuyor — ölçüm doldurma değil, görüntüleme kararı.

`PRESET-01` yedi yön + kaydın kendi yönü; referans bir kez kuruluyor,
"mevcut bakışı ön yap" var. `PRESET-02` yeni `services/camera_presets.py`:
en kısa yol (350°→10° = 20°), smoothstep, **zamana bağlı** ~1.5 s.
`PRESET-03` elle giriş animasyonu anında kesiyor; yeni preset o anki gerçek
konumdan başlıyor (kuyruk yok); hareket azaltma seçeneği var; geçiş bitince
timer duruyor.

`FLOOR-01` grid sporcunun ayaklarının altında ve yatayda merkezinde; referans
penceresinden bir kez kuruluyor, her karede yeniden hesaplanmıyor, zıplamada
yükselmiyor.

**Ölçülen (gerçek pencere).** Preset yolculuğu **1.51 s**; varışta
`timer running: False`.

### F12 — Offline zemin tespiti · tamamlandı, gerçek SVO ile doğrulandı

**Ön doğrulama.** `pyzed` 5.4'te `find_floor_plane` ve `sl.Plane` API'si var;
işleme hattı zaten `enable_positional_tracking` çağırıyor.

**Gerçek SVO ölçümü** (`take_20260917T220755_c97c/raw/capture.svo2`,
okuma-yalnız): düzlem **ilk karede** bulundu, `PLANE_TYPE.HORIZONTAL`,
denklem `(-0.0180, 0.9976, 0.0672, 1.1880)`, normal birim,
nokta `(-0.524, -0.971, -3.399)`. Düzlemin sporcunun ayakları altındaki
yüksekliği **-1.00 m**; aynı pencerede ölçülen en alçak ayak **-1.01 m**.
Bağımsız iki kaynak 2 cm içinde uyuşuyor.

**Bulunan gerçek hata.** `detect_floor` ilk olarak kare okunmadan önce
çağrılıyordu ve SDK konum takibi OK olmadan yanıt vermediği için gerçek bir
kayıtta `not_found` dönüyordu. Çağrı ilk grab'den sonraya alındı
(`FLOOR_AFTER_FRAMES = 30` pencereli); aynı kayıtta **0.02 s**'de `detected`.

**Şema.** Yeni `processing/floor.py`; `job.json` içine additive `floor_plane`
bloğu (`FLOOR_SCHEMA_VERSION 1.0.0`), `PROCESSING_SCHEMA_VERSION` → **1.2.0**.
Blok düzlem denklemi, normal, düzlem üstünde bir nokta, hangi kaynak karesinde
bulunduğu, koordinat sistemi, birim, **referans uzayı** ve kamera hareket etti
mi bilgisini taşıyor. Nokta bulutu veya mesh saklanmıyor. Ham koordinatlar ve
eski sürümler yerinde değiştirilmedi.

**Üç durum ayrı.** `detected` (ölçüm) · `visual_reference` (en alçak ayağa
çizilen grid, görsel yardım olarak adlandırılıyor, `Skeleton3DView.floor_source`
ile okunuyor) · `not_found` (denendi, olmadı, nedeni saklandı) ve
`not_attempted` (blok yok — 1.1.0 sürümleri). Ayakların anlık minimumu asla
"algılanmış zemin" diye sunulmuyor.

**Bulunan ikinci hata.** `getattr(backend, "_camera", None)` yalnız
`AttributeError`'ı yutar; başka bir istisna fırlatan bir property işlemeyi
düşürebilirdi. Sarmalandı.

**Çalıştırılan kontroller.** Yeni `tests/test_processing_floor.py` 17 test
yeşil (gerçek ölçülen düzlemle aritmetik; nokta denklemi sağlıyor; normal
birim; referans uzayı düzlemle birlikte gidiyor; duvar için yükseklik
üretilmiyor; round-trip; eski sürüm `not_attempted`; bozuk blok sıfır zemine
dönüşmüyor; başarısızlık nedenini koruyor; ZED olmayan kaynak; istisna
sızdırmama; hareketli kamera). `test_processing_artifacts.py` ve
`test_studio_review_open.py` yeşil.

**Kanıt sınırı.** Hareketli kamerayla çekilmiş bir SVO bu ortamda yok; kamera
hareketi durumundaki dönüşüm yolu **doğrulanmadı**, yalnız bloğun bunu
`camera_moved` ile ayrı tuttuğu test edildi.

### F13 — Sağ panel: dikey ikon şeridi · tamamlandı

**Neden.** Kelime sekmeleri (`Etiket` · `Sporcu`) panelin genişliğinde
`Etik…` / `Spor…` diye kısalıyordu ve tüm panel boyunca bir satır yükseklik
harcıyordu.

**Yapılan.** Yeni `views/iconstrip.py` · `IconStripPanel`: sağ kenarda kare
ikon sütunu, arkasında tek genişlikte `QStackedWidget`. Üç yer: **kamera**
(`camerapanel.CameraPanel`), **etiketler** (kaydırılabilir denetçi),
**kişi** (`SubjectPanel`). Panel genişliği görünüm değişince değişmiyor
(PANEL-02) çünkü üçü de aynı yığının sayfaları.

**Bulunan gerçek hata.** `QTabWidget` → `IconStripPanel` geçişi
`_show_subject_status` içinde bir `indexOf`/`setTabText` çağrısı bırakmıştı.
Modül hatasız import oluyordu; yalnız gerçek bir `attach` sırasında sporcu
durumu yayınlandığında `AttributeError` ile patlıyordu. Yeni
`tests/test_studio_label_panel.py` fikstürü bunu ilk çalıştırmada yakaladı.
Yerine `IconStripPanel.set_attention(key, reason)` kondu: uyarı rengi **ve**
tooltip/erişilebilir ad birlikte değişiyor — ikonun etiketi olmadığı için
yalnız renk değiştirmek aranıp bulunamayacak bir işaret olurdu.

### F14 — Etiket görünümünün üç hâli · tamamlandı

**LABEL-01.** Timeline'da bir kutuya tek tık doğru düzenleyiciyi açıyor.
Şerit ikonu bağlam rengini alıyor (`KcContextSummary/Movement/Fault`) **ve**
`_label_button` erişilebilir açıklaması hangi düzenleyicinin açık olduğunu
kelimeyle söylüyor; renk tek başına sinyal değil.

**Bulunan gerçek hata.** `select_movement` yalnız *başka* bir harekete ait
seçili hatayı düşürüyordu. Aynı hareketin bir hatası seçiliyken o hareketin
kutusuna tıklamak hata düzenleyicisini ekranda bırakıyordu; tık hiçbir şey
yapmamış gibi görünüyordu. `_timeline_selected` artık hareket kutusu için
seçili hatayı önce düşürüyor (ara durum `_suppress` ile çizilmiyor).

**LABEL-02.** `_build_summary_inspector`: hareket başına kart (sınıf, aralık,
süre, hata sayısı, hazırlık); hatalar ait oldukları kartın altında katlanıyor.
Hazırlık üç durumlu okunuyor (`Readiness`), `len(errors) == 0` değil — kimsenin
bakmadığı hareket **amber**, yeşil değil. Kart sayısı `SUMMARY_CARDS = 40` ile
sınırlı; gerisi sayılıyor.

**LABEL-03/04.** `QComboBox` + `QInputDialog` çiftleri `ClassPicker` ile
değişti: sınıflar buton, sınıfın kendi rengi butonun üstünde, sekiz sınıftan
sonra arama kutusu açılıyor, yeni sınıf satırı panelin içinde — diyalog
etiketlenen aralığın üstünü kapatıp yeri kaybediyordu. İlk dokuz hareket
sınıfının kısayolu butonun üstünde yazıyor.

### F15 — Hata sınıfı eklem kalıcılığı ve 3B seçim · tamamlandı

**JOINT-01.** `LabelSchema.add_error_type_with_roles` tek işlem: eklemsiz bir
sınıf `ValidationError` ile reddediliyor. Yeni
`ReviewViewModel.create_error_class_with_roles` bunu şemaya yazıp kaydediyor.

**JOINT-02.** `Skeleton3DView.set_picking` yalnız sınıf tanımlanırken açık:
ad kutusuna yazı girince açılıyor, ad silinince kapanıyor. Sürekli açık
bırakmak kameraya yönelik bir çift tıkın sessizce anatomi düzenlemesi
olmasına yol açardı.

**JOINT-03.** Çift tık çoklu seçim (ikinci tık düzeltme, kopya değil).
`Ekle` yalnız geçerli ad **ve** ≥1 eklemle etkin. Sınıf kaydedilince aralığa
uygulanıyor, panel açık kalıyor, taslak kapanıyor.

**JOINT-04.** Bilinen bir sınıfa basmak sınıfı **ve** ilan ettiği eklemleri
uyguluyor (`apply_error_class`). Kayıt, eklemlerin miras mı yoksa bu tekrar
için mi seçildiğini `RolesOrigin` ile ayırıyor; `CLASS_DEFAULT` asla
`REVIEWED` sayılmıyor.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_label_panel.py` **22
test yeşil** — gerçek işlenmiş bir sürüm açılarak, gerçek pencerede.

### F16 — Kişi, Veri Seti, Dışa Aktarım · tamamlandı

**PERSON-01.** Kişi paneli içerik olarak korundu (adaylar, sorular, seçili
sporcu, belirsiz aralıklar); yalnız yeri kelime sekmesinden ikon şeridine
taşındı. Export kapısı görünür kaldı: yanıtsız soru varken şeritteki kişi
ikonu uyarı rengi **ve** "yanıtlanmamış soru var" açıklaması taşıyor, yani
kamera görünümü açıkken de görülüyor.

**DATA-01.** `DatasetPage` ikiye ayrıldı: solda arama + filtre + tablo,
sağda seçili kaydın ayrıntısı ve **bekleyen her şey için bir eylem**.
Eylem sürümü de taşıyor (`pending_review` + yeni `pending_review_focus`);
yalnız sayfa değiştirmek okuyucuyu yanlış kaydın üstünde bırakırdı.
`ReviewPage._apply_focus` hedefi sürüm açıldıktan **sonra** uyguluyor:
`subject` kişi görünümünü, `open_error` ilk sınıfsız hata aralığını,
`no_exercise` ilk sınıfsız hareketi seçiyor. Hedefi olmayan engelleyici
(`no_subject_data` — yeniden işlemek gerekiyor) buton değil cümle alıyor.

**EXPORT-01.** Solda sürümler + doğrulama, sağda paket seçenekleri, hedef
konum, içerik özeti ve yazma eylemi. Seçili sürümün ayrıntısı artık altta
kaybolan tek satır değil, kendi alanında satır satır.

**EXPORT-02.** Yeni `CheckState` (`not_checked` · `checking` · `empty` ·
`ready` · `warning` · `blocked` · `stale`) ve her biri için ayrı cümle.
Yeni `export.canonical.current_revisions` — yalnız `job.json` + iki sidecar'ın
`revision` sayacı, üç küçük JSON okuması; dataset açmıyor. Kontrolden sonra
etiket değiştiyse sonuç `stale` oluyor, yazma reddediliyor. Veri sözleşmesi
zaten güvendeydi (`build_release` her sürümü yeniden denetliyor); düzeltilen
şey **ekranın** bayat bir "Hazır" göstermesiydi.

**Bulunan gerçek hata.** İlk `current_requisions` uygulamasında sidecar
yoksa `0` dönülüyordu; oysa hem `AnnotationDocument` hem `SubjectReview`
`revision = 1` ile başlıyor. Hiç etiketlenmemiş bir sürüm kontrol edilir
edilmez "değişmiş" görünüyordu ve `tests/test_studio_export_gui.py` iki testi
bunu anında yakaladı.

**Çalıştırılan kontroller.** Yeni `tests/test_studio_export_layout.py` **10
test**, yeni `tests/test_studio_dataset_actions.py` **11 test** yeşil;
`test_studio_export_gui.py`, `test_export_canonical.py`, `test_export_gui.py`
yeşil.

### F17 — Performans, görsel kabul, doğrulama raporu · tamamlandı

Ayrıntı ve bütün tablolar
[doğrulama raporunda](../reports/studio-gui-refinement-validation.md).
Özet:

**PERF-01 önce/sonra.** Etiketleme'ye ilk geçiş 1563.7 → **1069 ms**.
İlk `show()` 741.8 → 653.9 ms. 88 MB'lık gerçek sürüm 0.57 s'de açılıyor,
ilk kullanılabilir ekran 0.64 s. 3B çizim medyan **0.78 ms** / p95 1.06 ms
(bütçe 8 ms). Kare arama 9.71 ms (60 FPS bütçesi 16.7 ms). Preset yolculuğu
1.50 s; hareket azaltılmışta **anında**. Eklem seçme testi 0.161 ms.

**PERF-02 iş yükü.** Gizli sayfada oynatma ve kamera timer'ı **durmuş**;
kamera varışta timer'ı durduruyor; 8 sayfa döngüsünde widget artışı **0** ve
RSS **−0.1 MB**; sürüm yeniden açılmıyor; eklem seçme varsayılan kapalı;
zemin tespiti arayüz modülünde hiç geçmiyor.

**VERIFY-02/03 yerleşim.** Gerçek pencerede (251 font ailesi), 6 ekran ×
3 boyut × 3 ölçek (%100/%125/%150): **hiçbir denetim kırpılmıyor**. Üç
`QTableView` 1–2 px yatay kayıyor (`ResizeToContents` + `stretchLastSection`
yuvarlaması); kusur sayılmadı, ölçüm not edildi. 1120×700'de görüntü, 3B,
panel ve timeline dördü de görünür; araç çubuğu taşmıyor.

**NOTICE-01/02.** İki tema × dört ekranda, sürüm açıkken ve 3B çizimden
sonra, kartın **kendi merkezinde** `childAt` toast katmanının içine düşüyor
(8/8). Ölçüt bu; "bir `raise_` çağrısı var" kanıt sayılmadı.

**VERIFY-01 kabul koşusu.** Dosya dosya, proje kuralı gereği.
Son turda `offscreen` 84 dosyada **83/84** (2146 s); yerleşime duyarlı
18 dosya `QT_QPA_PLATFORM=windows` ile **18/18** (1399 s). Tek düşüş
`test_cancelling_a_paused_job_does_not_wait_for_a_resume` — test notunda bu
çalışmalardan önce kayıtlı aralıklı yarış; izole koşuda **3/3 geçti**.

**Bulunan gerçek hata.** İlk turda `test_processing_pipeline.py` düştü:
`job["schema_version"] == "1.1.0"` sabitine bağlıydı, F12 şemayı 1.2.0'a
taşımıştı. Test `PROCESSING_SCHEMA_VERSION` **sabitine** bağlandı ve
`floor_plane` bloğunun varlığı da doğrulandı — sürümü değiştiren şey buydu.

**Gerçek platformun bulduğu iki hata.** İkisi de `offscreen`'de yeşildi.
(1) `_Metric` genişlik tabanı `__init__`'te, tema fontu gelmeden ölçülüyordu;
`preview_loss` tabanı 24 px çıkıyor, dört mono rakam 28 px istiyordu, sayaç
dört haneye çıkınca yanındaki okuma 4 px kayıyordu. Taban artık font
değişiminde yeniden ölçülüyor; aynı tuzak geri sayım yuvasında da vardı ve
orada `setFixedWidth` olduğu için kaydırmak yerine **kırpıyordu**.
(2) Yakalama ekranı %150'de dizüstüne sığmıyordu: 1053 px gerekiyor, 911 px
var. Satırdaki tek kontrol-olmayan öge — klavye hatırlatması — eliding'e
alındı; **1053 → 892 px**.

**Ölçüm tuzağı, kaydedildi.** İlk performans koşusu hiç boya örneği
üretmedi: kabuk giriş ekranında açılıyor, arkasındaki her sayfa haritalanmamış
kalıyor, 3B widget 640×480 varsayılan boyutunda hiç `paintGL` çalıştırmıyor.
Ölçümden **önce oturum açmak** şart. Aynı şekilde widget sayımı, `library`
sayfası döngü içinde ilk kez kurulduğunda 63 widget'lık tek seferlik yapımı
"sızıntı" gibi gösteriyor; taban ölçüm iki sayfa da kurulduktan sonra alınmalı.

### Devam noktası

**Sıradaki faz:** yok — F1–F17 tamamlandı.
**Son tamamlanan:** F17.
