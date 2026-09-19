---
type: audit
status: current
date: 2026-09-18
scope: claude-code-local-sessions
tags:
  - audit
  - memory
  - coverage
---

# Claude Code hafıza aktarım denetimi — 18 Eylül 2026

Yerel Claude Code kayıtlarındaki kalıcı bilginin repository wiki'sine eksiksiz
aktarıldığını doğrulayan kapsama defteri. Ham JSONL kopyalanmadı, taşınmadı ve
silinmedi; yalnız akış halinde okunup tur sonu metinleri çıkarıldı.

Yöntem: her oturumun yalnız kullanıcı istemleri ve **tur sonu** assistant
metinleri ayıklandı; araç çağrıları, araç sonuçları, düşünme blokları ve gömülü
görseller atlandı. Aday bilgi önce `MEMORY_INDEX.md` ve ilgili atomik notla,
sonra koda veya teste karşı denetlendi.

## 1. Kaynak envanteri (18 Eylül 2026, denetim anı)

`C:\Users\gorke\.claude\projects\C--Users-gorke-Desktop-KineCapture`

| Dosya | Bayt | Değişiklik | SHA-256 | Durum |
|---|---:|---|---|---|
| `4a7f5ab8-e86f-409f-898b-ac8e26114929.jsonl` | 25.733.829 | 2026-09-13 22:45 | `d7c2002ebad0ede1640ce9772687b08e5e0cb17c370ed4418662a40a214701df` | ayrı konuşma |
| `f52972b3-47e1-4e62-aa02-07d429288173.jsonl` | 15.511.591 | 2026-09-17 02:07 | `620da70d9ed707f98d60ccb32bf92b5facae9cd67294db45487d68cc762a95a3` | ayrı konuşma |
| `c34f9bc5-0045-48a2-910a-2020a18c4034.jsonl` | 26.622.762 | 2026-09-18 21:04 | `7e55796d47f1a0fefd073f69351def8535b02a23a3be28fbfaa156500644d1ba` | ayrı konuşma, en güncel |
| `3dba63b8-4c6b-455f-8682-a04ed8c689d2.jsonl` | 21.948.684 | 2026-09-18 01:29 | `4dcf4f4c291ac2a9b45d4996e81823a8b994851ea0ac71223ff0ee4558eb096d` | `c34f9bc5` çatal kopyası |
| `a4d65117-6563-4bc8-84bf-ca98d4948698.jsonl` | 21.948.684 | 2026-09-18 01:29 | `0433df48693ae284fb28d006ac67b4745078bc0864ba4a88834453e065d3c0e6` | `c34f9bc5` çatal kopyası |
| `e488727e-a7ca-464d-b773-e1e048164b46.jsonl` | 388.985 | 2026-09-18 21:54 | `147977013123a31bd0869bafac96d9aef397d0a6834aaf0001ec1b39b1953f87` | bu denetim oturumu, canlı |

### Dosya sayısı ile konuşma sayısı aynı değil

`3dba63b8` ve `a4d65117` dosyalarının her satırı
`"sessionId": "c34f9bc5-0045-48a2-910a-2020a18c4034"` taşıyor. İkisinden
çıkarılan konuşma metni birbiriyle bayt bayt aynı ve `c34f9bc5` metninin ilk 21
bloğuyla birebir örtüşüyor; `c34f9bc5` aynı konuşmayı 27 blokla sürdürüyor. Her
ikisinin yanında `.desktop-released.json` var ve `reason: "delete"` yazıyor.
Bunlar masaüstü uygulamasının bıraktığı çatal anlık görüntüleridir, bağımsız
konuşma değildir.

Sonuç: **6 JSONL dosyası, 3 tarihsel konuşma ve 1 canlı denetim oturumu.**
`c34f9bc5` denetlendiğinde `3dba63b8` ve `a4d65117` tam olarak kapsanır.

### Auto-memory ve yan kaynaklar

| Kaynak | Durum |
|---|---|
| `memory/` (Claude auto-memory) | **Boş** — 0 dosya, 0 alt klasör; klasör 20 Ağustos'tan beri değişmemiş. Aktarılacak auto-memory kaydı yok. |
| `*/tool-results/` | 4 klasör, toplam 5 dosya, yaklaşık 240 KB. Taşan araç çıktısının taşma dosyaları; kalıcı bilgi taşımıyor, topluca alınmadı. |
| `*.desktop-released.json` | 2 dosya, yalnız çatal serbest bırakma kaydı. `historical-only`. |

### Kaynak sicili

`scripts/update_knowledge_sources.py` denetim sonunda yeniden çalıştırıldı.
Sicildeki "Claude Code oturumları" sayısı **dosya** sayısıdır; yukarıdaki çatal
ayrımı için bu denetim notu otoritedir.

## 2. Kapsama ve karar defteri

Karar kodları: `already-represented`, `added`, `corrected`, `superseded`,
`duplicate`, `historical-only`, `unverified`, `sensitive-excluded`.

### Oturum `4a7f5ab8` — 20 Ağustos – 13 Eylül, scaffold'dan GUI cilasına

Kapsam: ilk teslim ve gerçek ZED dumanı, iki seviyeli etiketleme redesign'ı,
seçilebilir iskelet özellikleri, sürekli aktivite ile RGB-D ve kişi kilidi,
capture-inceleme sadeleştirmesi, proje silme, etkilenen eklem kanıtı. Oturum
`MEMORY.md` güncellenerek kapandığı için içeriği yapısal olarak tarihsel arşive
girmiştir.

| Kalıcı aday | Kanıt | Karar | Hedef |
|---|---|---|---|
| Ortam, SDK ve donanım doğrulaması (KineSynth, Python 3.11.14, SDK 5.4.1, ZED 2i S/N 31844341) | arşiv 3, 4 ve `MEMORY_INDEX.md` | already-represented | [Güncel durum](../../MEMORY_INDEX.md) |
| İki seviyeli etiket modeli, `SampleReadiness`, tek kare sınırı sözleşmesi | arşiv 6b | already-represented | [Etiket ve feature sözleşmesi](../concepts/annotation-and-features.md) |
| 31 özellik ve 64 dizi anahtarı, feature registry, `mapping_support` | arşiv 6c-01…6c-10 | already-represented | [Etiket ve feature sözleşmesi](../concepts/annotation-and-features.md) |
| Ham RGB-D arşivi, kişi kilidi 1.0.0, sürekli export sözleşmesi | arşiv 6d-01…6d-08 | already-represented | [RGB-D ve depth](../concepts/rgbd-and-depth.md) |
| Kalıcı proje silme yalnız sistem sahibi; yol koruyucuları | arşiv 6i-04 | already-represented | [Kimlik ve erişim](../concepts/identity-and-access.md) |
| Türetilmiş doğru/hatalı kararı ve `LEGACY_CONFLICT` politikası | arşiv 6i-01, 6i-02 | already-represented | [Etiket ve feature sözleşmesi](../concepts/annotation-and-features.md) |
| Bindirme hizası kök nedeni, ofis ofseti değil | arşiv 6g-03 | already-represented | [RGB-D ve depth](../concepts/rgbd-and-depth.md) |
| Segfault: `QPainter.drawPolygon` aşırı yüklemesi; çizim testi olmadığı için kaçmıştı | arşiv 10 | already-represented | tarihsel arşiv |
| `test_participant_codes_are_unique_under_concurrent_allocation` tam suite yükünde Windows kilit yarışıyla aralıklı düşüyor, izole koşuda geçiyor | oturumda iki kez ayrı ayrı raporlandı; test `tests/test_identity.py:269` hâlâ mevcut | **added** | [Test ve ölçüm ortamı](../protocols/test-and-measurement.md) |
| Staj raporu ve defter turları (6m, 6n, 6o, 6q, 6r, 6u, 6w) | arşiv | historical-only | ürün bilgisi değil, taşınmadı |

### Oturum `f52972b3` — 13–17 Eylül, Studio F0–F15

| Kalıcı aday | Kanıt | Karar | Hedef |
|---|---|---|---|
| F0–F15 faz sonuçları ve commitleri | arşiv 6y, 6z, 6aa, 6ab, 6ac, 6ad | already-represented | [Studio F0–F15](../milestones/studio-f0-f15.md) |
| `PROCESSING_SCHEMA_VERSION` 1.0.0 → 1.1.0 toplamsal; 1.0.0 sürümleri hâlâ açılıyor | arşiv 6aa | already-represented | [Veri hattı](../concepts/pipeline.md) |
| Üç katman; `services/`, `viewmodels/`, `theme/` Qt import etmiyor; `tokens.json` tek renk kaynağı | arşiv 6z | already-represented | [Sistem haritası](../architecture/system-map.md) |
| Eski `gui/` korunuyor ve `--legacy-gui` ile açılıyor; göç kodu yazılmadı, bu kullanıcı kararıdır | arşiv 6z, `system-map.md` | already-represented | [Sistem haritası](../architecture/system-map.md) |
| `long_path` her yolu ayrı değerlendirir; kısa ebeveynden özyinelemeli glob sessizce boş döner | arşiv 6aa | already-represented | tarihsel arşiv |
| **`QT_QPA_PLATFORM=offscreen` altında font ailesi yok; yerleşim ölçümü geçersiz** | bu denetimde yeniden ölçüldü: `QFontDatabase.families()` → `0` | **added**, arşiv 8'i **superseded** yapar | [Test ve ölçüm ortamı](../protocols/test-and-measurement.md) |
| **Tam `pytest` tek süreçte bitmiyor; dosya dosya koşu proje kuralı oldu** | oturumda F1, F2 ve F13'te ayrı ayrı; `c34f9bc5` bunu "proje kuralı" diye anıyor | **added** | [Test ve ölçüm ortamı](../protocols/test-and-measurement.md) |
| Mock backend hız sınırı olmadan yaklaşık 350 FPS üretip kuyruğu taşırıyordu; `real_time=True` | arşiv 6ab | already-represented | tarihsel arşiv |
| `setSortingEnabled` 1000 satır doldurmayı 224 ms'e çıkarıyordu | arşiv 6ab | already-represented | tarihsel arşiv |
| GUI yazarken bulunan 11 backend açığı; üçü yanlış etiket üretebilirdi | arşiv 6ac, 6ad | already-represented | [Etiket ve feature sözleşmesi](../concepts/annotation-and-features.md) |
| F1 performans temel ölçümleri, örneğin timeline 292 ms | arşiv 6y | historical-only | sonraki fazlarda geçersizleşti |

### Oturum `c34f9bc5` ve çatalları `3dba63b8`, `a4d65117` — 15–18 Eylül

| Kalıcı aday | Kanıt | Karar | Hedef |
|---|---|---|---|
| Yayımlama kapısı ikiye ayrıldı; yalnız üç engelleyici kod | arşiv 6af, `pipeline.md` | already-represented | [Veri hattı](../concepts/pipeline.md) |
| Kayıt öncesi anchor ilk kareye uygulanıyor, `offset_ms` ile | arşiv 6af | already-represented | [Kişi seçimi](../concepts/subject-selection.md) |
| İmza yalnız `tracking_state == ok` karelerinden; veto yalnız çok bedenli karede; `ASSOCIATION_ALGORITHM_VERSION` 1.2.0 | arşiv 6af | already-represented | [Kişi seçimi](../concepts/subject-selection.md) |
| Tekrarlı mikrosaniye: `< 0` geriye gidiş, `== 0` tekrar | arşiv 6af | already-represented | [Veri hattı](../concepts/pipeline.md) |
| Gerçek ZED ile uçtan uca zincir; `run_61ef0f7cf0fb42e3`, 1370/1370 kare | arşiv 6ag, deney notu | already-represented | [Canlı ZED doğrulaması](../experiments/2026-09-18-live-zed.md) |
| Kalıcı ZED veri kalitesi bulguları: rijit şablon, ısınma, 2B izdüşüm, kadraj etkisi, gürültü tabanı | arşiv 6ag, deney notu | already-represented | [Canlı ZED doğrulaması](../experiments/2026-09-18-live-zed.md) |
| Kişi seçimi kayıt için zorunlu; red sebebi açıkça söyleniyor | arşiv 6ag, `subject-selection.md` | already-represented | [Kişi seçimi](../concepts/subject-selection.md) |
| Ölçülen kayıtların take kimlikleri ve gerçek saatleri | `take_20260917T215647_502a` ve `take_20260917T220755_c97c`; işleme 18 Eylül 01:11 ve 01:15'te bitti | **corrected** | [Canlı ZED doğrulaması](../experiments/2026-09-18-live-zed.md) |
| **Sporcu seçimi ile işlemede kilitlenen kişi arasındaki uyuşmazlık engellenmiyor** | kodda doğrulandı: `processing/subject_review.py:391-407` yalnız `unknown_athlete_tracker` bakıyor, `export/canonical.py:246` yalnız "seçilmedi" diyor; kilitlenen kimlik `features.json` içindeki `subject_association` alanında zaten yazılı (`processing/jobs.py:534`) | **added** | [Açık sorular](../open-questions.md) |
| Etiketleme ekranında sonradan kişi seçimi yok | `open-questions.md` madde 1 | already-represented | [Açık sorular](../open-questions.md) |
| `WA_TransparentForMouseEvents` bütün alt ağacı hit-test dışına çıkarıyordu | oturum; bildirim katmanı artık yalnız kart alanını kaplıyor | historical-only | uygulanmış düzeltme, kalıcı sözleşme üretmiyor |
| **Studio stil sayfası uygulama geneli; aynı süreçte eski GUI ölçümlerini bozuyor** | kodda doğrulandı: `studio/views/theming.py:44` → `QApplication.setStyleSheet` | **added** | [Test ve ölçüm ortamı](../protocols/test-and-measurement.md) |
| `ProjectDeletionService` arayüzü ve proje adı yazma şartı | servis zaten arşiv 6i-04'te; bu turda yalnız GUI eklendi | already-represented | [Kimlik ve erişim](../concepts/identity-and-access.md) |
| Kadraj rozeti, `FramingWatch` son 15 saniye en kötüsü, `subject_box()` | arşiv 6ag | already-represented | tarihsel arşiv |
| Bildirim kartı yerleşimi ve `bottom_reserve()` | arşiv 6af, 6ag | already-represented | tarihsel arşiv |
| Eski sürüm projeleri otomatik gizlenmedi; kullanıcı verisi sessizce saklanmaz | `data-integrity.md` değişmezi | already-represented | [Veri bütünlüğü](../concepts/data-integrity.md) |
| Hata ayıklama sırasında oluşan üç zayıf ara sürüm | oturum | historical-only | geçici çıktı, kalıcı değil |
| Kullanıcının kayıt yolları, proje kimlikleri ve ekran görüntüleri | oturum | sensitive-excluded | wiki'ye kopyalanmadı |

### Oturum `e488727e` — bu denetim

Kalıcı ürün bilgisi üretmedi; çıktısı bu defter ve bağlı notlardır.

## 3. Bu denetimde çalıştırılan doğrulamalar

| Doğrulama | Sonuç |
|---|---|
| Altı JSONL dosyasının SHA-256'sı | alındı, tablo 1'de |
| `memory/` klasörü sayımı | 0 dosya |
| `3dba63b8`, `a4d65117` ve `c34f9bc5` konuşma karşılaştırması | çatal ilişkisi kanıtlandı |
| `QFontDatabase.families()` offscreen altında | `0` aile; yerleşim ölçümü geçersiz |
| `subject_review.validate_subject_review` uyuşmazlık kapısı | yok, açık |
| `tests/test_identity.py:269` | test mevcut |
| `tests/conftest.py:200` `choose_subject` | mevcut |
| `studio/views/theming.py:44` | `QApplication.setStyleSheet`, süreç geneli |
| `scripts/update_knowledge_sources.py` | yeniden çalıştırıldı |
| `git diff --check` | temiz |
| Yerel Markdown bağlantıları | denetlendi, kırık bağlantı yok |

## 4. Kapatılmayan noktalar

- Kişi kilidi uyuşmazlık kapısı kodda açık. Bu denetim yalnız kaydetti,
  düzeltmedi; denetim görevi üretim kodunu değiştirmez.
- `test_identity` aralıklı düşmesi yalnız `observed`; kök neden ölçülmedi.
- `scripts/run_tests.ps1` hâlâ `QT_QPA_PLATFORM=offscreen` ayarlıyor ve tek
  süreçte `pytest` çağırıyor. Betik araç kodu olduğu için bu görevde
  değiştirilmedi; çelişki
  [Test ve ölçüm ortamı](../protocols/test-and-measurement.md) notunda açık
  madde olarak duruyor.

İlgili: [AI hafıza iş akışı](../protocols/ai-memory-workflow.md),
[Konuşma sicili](../sources/conversation-registry.md).
