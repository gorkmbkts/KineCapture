---
type: plan
status: delivered-partial-validation
created: 2026-09-21
updated: 2026-09-21
tags:
  - handoff
  - codex
  - capture
  - subject-tracking
  - studio
  - gui
---

# Codex'e devir — kayıt/takip/GUI onarımının kalan kısmı

## Codex teslimi · 21 Eylül 2026

Devir alındı; kişi kilidindeki güvenilir konum regresyonu, mod etiketi
genişliği, kayıt düğmesi yüksekliği ve eski şema/test beklentileri düzeltildi.
Gerçek SVO tekrarında **1473/1473** kare kilitli. `%100` yakalama
geometrisinde bütün geçişler sabit; `%150`'de yalnız kabul edilen yatay
**1 px** işaret düğmesi farkı kaldı.

Ek denetim `%150` etiketleme sahnesinin editöre **83 px** bindiğini ortaya
çıkardı; önceki "binme yok" ifadesi yanlıştı. Yükseklik bütçesi ve kısa sağ
panel için kamera/kişi araçlarının ayrı pencereye açılması kodlandı.
**Bu son GUI düzenlemesi yeniden doğrulanmadı.**

**Kullanıcı daha fazla test istemedi.** Çalışan koşu durduruldu: 95 dosyanın
47'si sonuçlandı, 45 yeşil / 2 başarısız; tamamlanan dosyalar toplam 784,7 sn.
Başarısızlıkların açıklaması ve son doğrulama sınırı
[raporda](../reports/capture-tracking-gui-repair-validation.md).
Kullanıcı ayarları ve kimlik veritabanı SHA-256 ile değişmeden kaldı.

Sonraki iş **kullanıcıyla GUI görünümü düzenlemeleri**. Aşağıdaki tam test
koşusunu tekrar başlatma talimatı, bu oturumdaki son kullanıcı kararıyla
geçersiz kılındı; görsel kabul ve canlı kamera doğrulaması açık.

## Tarihsel devir içeriği

Bu belge, 21 Eylül'de Claude'un yaptığı işin **nerede kaldığını** ve
Codex'in **tam olarak neyi yapması gerektiğini** anlatır. Görev tanımı
[Claude promptunda](../../promts/CLAUDE_CAPTURE_TRACKING_GUI_REPAIR_PROMPT_2026-09-20.md);
kök nedenler ve fazlar
[uygulama planında](capture-tracking-gui-repair-implementation.md);
ölçümler [doğrulama raporunda](../reports/capture-tracking-gui-repair-validation.md).

> **Kısaca:** C-01…C-07 kodu **yazıldı ve gerçek pencerede ölçüldü**. Kalan iş
> tek bir şey: **bütün testin dosya dosya son koşusu** ve çıkan olursa
> düzeltilmesi. Sonra rapor/wiki'deki iki sayıyı doldurup bitirmek.

## Ortam ve değişmez kurallar

- Yalnız `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`. Yeni
  environment yok, paket yükseltmesi yok.
- Bütün pytest'i **tek süreçte** koşma; proje kuralı gereği **dosya dosya**
  koş (aşağıda hazır betik var).
- Kullanıcının ham kaydını, etiketlerini, kimlik veritabanını ve ayarlarını
  **değiştirme**. Ölçüm betikleri `AppConfig.sandboxed(...)` kullanır.
- Uygulama **yalnız tam ekran** çalışır; farklı pencere boyutu hedefi yok.

## Şu anda ne durumda

### Kod — tamam (28 kaynak dosyası, 1'i yeni)

C-01…C-07 ve iki ek bulgu uygulandı. Ayrıntı ve gerekçe
[uygulama planında](capture-tracking-gui-repair-implementation.md) faz faz
yazılı. Özet:

| # | Konu | Durum |
|---|---|---|
| C-01a | Ayar sızıntısı (`AppConfig.user_state_path`, `sandboxed`, yazma reddi) | bitti |
| C-01b | Kayıt hedefi ön kontrolü, kurtarılabilir başlangıç, nedene özgü hata | bitti |
| C-02 | Kişi kaybı: duruş vetosu + terminal `AMBIGUOUS` + donan `gap` | bitti |
| C-03 | `IssueAxis`/`IssueWeight`, `subject_coverage`, sayılı ileti | bitti |
| C-04 | Kalıcı sağ panel, preset sadeleştirme, bant binmesi | bitti |
| C-05 | Her açılış Projeler, proje/katılımcı kapıları, otomatik katılımcı yok | bitti |
| C-06 | Sabit yakalama geometrisi, RGB oranı, iki sütun, merkez metinler | bitti |
| C-07 | Saran eylem satırı, düğme genişliği, ayrı ayrıntı penceresi | bitti |
| C-08 | 2B kaplamada `(-1,-1)` sentinel'i (bu turda bulundu) | bitti |

### Gerçek kayıt — yeniden işlendi

GUI TEST take'i **aynı ham SVO'dan** yeni sürüme işlendi:

```text
C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4
  \participants\P0001\sessions\ses_20260916T151622_57a9
  \takes\take_20260920T195059_c183\derived\processing\
      run_4b8fd122e2c44eee   ← kullanıcının orijinali, DOKUNULMADI (622/1473)
      run_dca7a1ce797546a7   ← Claude'un ara sürümü, şema 1.2.0 (1473/1473)
      run_a79158c706454edc   ← nihai sürüm, şema 1.3.0 (1473/1473)
```

`run_dca7a1ce797546a7` gereksizdir (nihai sürüm onu kapsar) ama **silinmedi**:
kullanıcının projesindedir, kararı onundur. Raporda da böyle yazılı.

### Ölçümler — alındı

Gerçek tam ekran pencere, gerçek yazı tipleri, gerçek GL, `QTest` olayları:

- `C:\Users\gorke\.codex\visualizations\2026\09\21\capture-tracking-after`
  (%100 · 1920×1009) — 17 ekran görüntüsü + `manifest.json`
- `C:\Users\gorke\.codex\visualizations\2026\09\21\capture-tracking-after-150`
  (%150 · 1280×673 mantıksal) — aynı set

Ölçüm betikleri **repoya taşındı** (scratchpad geçicidir):
[`scripts/measure/`](../../scripts/measure/README.md) — `run_suite.py`,
`evidence.py`, `real_window.py`, `diag_lock.py`, `diag_subject.py`,
`reprocess.py` ve koşulardan önceki hash'ler.

### Kullanıcı verisi — dokunulmadı (hash ile doğrulandı)

Tam bir test süpürmesi ve üç gerçek pencere koşusundan sonra:

| dosya | sha256 (ilk 16) | aynı mı |
|---|---|---|
| `~/.kinecapture/user_state.yaml` | `247f706f86560c22` | evet |
| `~/.kinecapture/window_state.json` | `9af8bc2771ffc49a` | evet |
| `%LOCALAPPDATA%\KineCapture\identity.sqlite3` | `9baf7bf7d315a34b` | evet |

"Önce" değerleri `scratchpad/user_state_before.json` içinde.

---

## Kalan iş

### 1. Bütün testin son koşusu — **asıl kalan iş**

Claude son kod değişikliklerinden (yakalama ekranındaki üç yükseklik/genişlik
ayırma düzeltmesi) **sonra** tam koşuyu bitiremedi. Arka planda başlatılan
koşu 13/95'te kaldı ve o koşu bile bir önceki koddan.

```bash
cd C:/Users/gorke/Desktop/KineCapture
QT_QPA_PLATFORM=offscreen "C:/Users/gorke/anaconda3/envs/KineSynth/python.exe" scripts/measure/run_suite.py suite_final.json
```

Yaklaşık 40 dakika sürer; her dosyanın sonucunu ekrana ve `suite_final.json`
dosyasına yazar. Beklenen: **95/95 yeşil**.

**Bilinen aralıklı düşüş:** `test_processing_pipeline.py` içindeki
duraklat/sürdür ailesi, bu çalışmalardan **önce** kayıtlı bir yarıştır
([test ve ölçüm notu](../protocols/test-and-measurement.md)). Düşerse izole
koşuda üç kez tekrarla; geçiyorsa aynı yarış olarak raporla, yeni hata sayma.

Bir dosya düşerse: önce o dosyayı tek başına koş, sonra hatayı gerçekten
düzelt. Aşağıdaki testler bu turda **kuralı değiştiği için** yeniden yazıldı;
bunlar düşerse kuralın kendisine bak, testi gevşetme:

`test_studio_shell.py` · `test_studio_capture.py` ·
`test_studio_capture_target.py` · `test_studio_library.py` ·
`test_studio_toasts.py` · `test_studio_shell_gui.py` ·
`test_studio_capture_row.py` · `test_studio_review_bands.py` ·
`test_studio_projects_gui.py` · `test_studio_dataset_actions.py` ·
`test_studio_library_layout.py` · `test_studio_processing_layout.py` ·
`test_studio_review_loading.py` · `test_studio_label_panel.py`

Bu turda eklenen yeni dosyalar (hepsi tek tek yeşil görüldü):

`test_user_state_isolation.py` (6) · `test_recording_target.py` (6) ·
`test_subject_lock_recovery.py` (11) · `test_studio_capture_layout.py` (15) ·
`test_studio_toast_actions.py` (13) · `test_studio_review_overlay.py` (4)

### 2. Ölçümü bir kez daha al (kod değiştiyse)

Son üç düzeltme (`_Metric` yükseklik ayırma, `connect_button` sabit ölçü,
`mode_state` genişlik tabanı) sonrası %150 ölçümü alındı, %100 alınmadı.

```bash
cd C:/Users/gorke/Desktop/KineCapture
"C:/Users/gorke/anaconda3/envs/KineSynth/python.exe" scripts/measure/evidence.py "C:/Users/gorke/.codex/visualizations/2026/09/21/capture-tracking-after"
```

Beklenen (`manifest.json` içinde):

- `capture_moves`: kadraj/uyarı/kişi geçişlerinin hepsinde **0**
- `capture_scroll`, `capture_overlaps`, `capture_clipped`, `review_overlaps`,
  `review_scroll`: **boş**
- `capture_stage.ratio` ≈ **1.778** ve `console_columns` = **1** (%100'de)
- `inspector_visible` ve üç tıklamadan sonra hâlâ **true**
- `skeleton_at`: 8,12 / 10,60 / 11,25 / 20 / 24 saniyede **present: true**
- `toast.clipped`: **boş**

**Bilinen ve kabul edilen kalan hareket** (%150'de, bağlanma anında):
`mode_state` yalnız **genişliğini** değiştirir (konumu sabit), `marker_button`
**1 piksel** kayar. İkisi de ölçekleme yuvarlamasıdır; raporda böyle yazılı.
0'a indirilebilirse iyi olur, zorunlu değil.

### 3. Raporun iki boşluğunu doldur

[Doğrulama raporunda](../reports/capture-tracking-gui-repair-validation.md)
"Testler" bölümüne son koşunun sonucunu ekle: kaç dosya yeşil, kaç saniye,
düşen varsa hangisi ve neden. Sonra
[uygulama planındaki](capture-tracking-gui-repair-implementation.md)
"Devam noktası"nı kapat.

### 4. `MEMORY_INDEX.md` yalnız gerçek duruma göre

Zaten güncellendi. Test koşusu bittiğinde tek eklenecek şey, koşunun sonucudur.
**"GUI kapsamı kapandı" yazma**: görsel kabul kullanıcıdadır.

---

## Yapılmaması gerekenler

- Gerçek kamerayla kayıt **denenmedi** (kamera bağlı değil). Sentetik
  backend'le alınan sonucu canlı başarı diye raporlama.
- `run_4b8fd122e2c44eee` (kullanıcının orijinal sürümü), ham SVO ve
  `~/.kinecapture/user_state.yaml.bak-2026-09-20-leak` yedeği **silinmesin**.
- Identity veritabanındaki kırık üç proje kaydı (ikisi eski pytest geçici
  dizinlerinden, biri 20 Eylül'de sızan kökten) **temizlenmedi**; kullanıcının
  kararı olmadan silinmesin.
- Testleri geçirmek için kuralı gevşetme. Bu turda değişen kurallar:
  proje/katılımcı kapısı, otomatik katılımcı yok, kalıcı etiketleme paneli,
  yalnız uzuv oranının veto edebilmesi, `AMBIGUOUS`'un kurtarılabilir olması.

## Kalan doğrulanmamış sınırlar (raporda da yazılı)

- Gerçek kamerayla kayıt; uzun yol reddinin SDK'nın **kendi** hatasıyla
  görülmesi.
- Kişi kilidinin kurtarma yolu gerçek kayıtta tetiklenmedi (yanlış veto
  kaldırıldığı için ihtiyaç kalmadı); yalnız sentetik regresyonla sınandı.
- Canlı kamera, GPU ve kayıt kaybı ölçülmedi.
- İki kişili **gerçek** kadraj yok; GUI TEST kaydındaki ikinci beden aynadaki
  yansımadır.
