---
type: legacy-memory-section
status: archived
title: "6. Bu görevde alınan kalıcı teknik kararlar"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "222-293"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](5-5-gercekten-calisan-ozellikler.md) · [sonraki](6b-6b-iki-seviyeli-etiketleme-redesign-i-2026-08-21.md) →

Güncel karşılığı: [Sistem haritası](../../architecture/system-map.md), [Veri bütünlüğü ve kanıt](../../concepts/data-integrity.md).

## 6. Bu görevde alınan kalıcı teknik kararlar

1. **Environment `KineSynth`.** Önceki scaffold `KineCaptureStudio` adlı yeni
   bir environment öngörüyordu; PROMPT bunu iptal etti. `setup_env.ps1`
   silindi, üç betik `scripts/_common.ps1` üzerinden yalnız `KineSynth`
   arıyor ve bulamazsa **başka ortama düşmeden** duruyor.
2. **Python 3.10 pini kaldırıldı.** Gerçek ortam 3.11.14 ve `pyzed` 5.4 bu
   sürüm için derlenmiş (`cp311`). `environment.yml` silindi; environment
   artık bu proje tarafından yönetilmiyor.
3. **ZED backend gerçekten yazıldı.** Her SDK çağrısı yazılmadan önce bu
   makinede çalıştırıldı. Önceki scaffold'un "not_implemented" stub'ı gitti.
4. **Ham kayıt = SVO2, oynatma = proxy MP4, poz = JSONL.** Üçlü bölüm
   bilinçli: SVO2 değişmez ham kayıt ve derinliği yeniden üretebilir; proxy
   yalnızca hızlı tarama içindir; JSONL append-safe ve poz için
   otoritatiftir. Derinlik kareleri ikinci kez saklanmıyor.
5. **İskelet akışı JSONL.** Chunked binary yerine seçildi: kare başına flush
   ile kurtarılabilir, yarım son satır tolere edilebilir, dış araçlarla
   okunabilir. HD720/34 eklem ≈ 100 byte/kare — 5 dakikalık kayıt ~1 MB.
6. **Etiket aralıkları AKIŞ KONUMUDUR, kamera kare numarası değil.**
   `MovementSample` ve `ErrorInterval` içindeki `start_frame`/`end_frame` =
   `skeleton.jsonl` kare listesindeki 0-tabanlı indeks, **her iki uç dahil**. Kamera kimliği kaybolmuyor: segmentte
   timestamp, exportta `frame_indices` ve `camera_timestamps_ns` dizileri ve
   manifestte `start_camera_frame`/`end_camera_frame` var. Bu ayrım
   geliştirme sırasında gerçek bir hata olarak yakalandı (kare düşünce
   ikisi ayrışıyor).
7. **Windows uzun yol desteği.** Dizin yapısı derin olduğu için 260 karakter
   sınırı gerçekten aşılabiliyor (testlerde aşıldı). `core/paths.py`
   `\\?\` öneki ekliyor; jsonio, workspace, take_writer, take_reader,
   fingerprint ve export bunu kullanıyor. OpenCV bu öneki kabul etmediği
   için proxy video "kullanılamıyor" olarak işaretlenip nedeni yazılıyor —
   veri kaybı değil, özellik kaybı.
8. **3B görünüm QPainter ile.** pyqtgraph kurulu değil; PyOpenGL/VTK entegre
   etmek risk. Birkaç düzine eklemli çubuk figür için açık perspektif
   projeksiyonu yeterli, bağımlılıksız, DPI ölçeklemesinde tutarlı ve
   test edilebilir. Orbit/zoom/pan + 4 hazır görünüm var.
9. **Zaman çizelgesi elle yazıldı.** Katmanlı, sürüklenebilir, zoom'lanabilir
   ve iç içe iki seviyeli bir aralık editörü sunan hazır bir Qt bileşeni yok.
10. **İkonlar SVG path + QPainter.** Tema rengine göre boyanıyor, DPI'ya göre
    render ediliyor, repository'de binary asset yok. Emoji kullanılmadı.
11. **Etiket ontolojisi veridir.** `label_schema.json` proje başına.
    Varsayılan şema **boş** egzersiz ve **boş** hata türü listesiyle gelir;
    kod içinde uydurma hata sınıfı yok. Kullanıcı hata türlerini etiketleme
    sırasında ekler ve şemaya atomik yazılır (bkz. bölüm 6B).
12. **26-eklem eşleştirmesi kısmi ve öyle raporlanıyor.**
    `zed_body_34__to__rehab24_6_mocap` v0.1.0-partial: 23/26 eklem eşleşiyor.
    `Head_end`, `LeftToeBase_end`, `RightToeBase_end` mocap uç işaretçileridir
    ve ZED'de karşılığı yoktur → **NaN yazılıyor**, gerekçeleriyle birlikte
    manifeste giriyor ve Export ekranında uyarı olarak gösteriliyor.
    Kaynak: KineSynthV3 `colab/dataset/processed/kinesynth_rehab24_v1/
    skeleton_spec.json` ile yerel SDK BODY_34 sırası karşılaştırıldı.
13. **Export normalize etmiyor.** Root centering, ölçekleme, interpolasyon,
    augmentation yok; manifest bunu `normalisation: none` olarak yazıyor.
14. **Önizleme kaybı ≠ kayıt kaybı.** İki ayrı sayaç, iki ayrı gösterge.
    Önizleme "son kare kazanır" tek yuvalı; kayıt kuyruğu 120 karelik ve
    taşması veri kaybı olarak kırmızı gösteriliyor.
15. **Kod ve arayüz dili.** Kod, tanımlayıcılar, docstring'ler ve schema
    alanları İngilizce; kullanıcıya görünen bütün metinler ve hata mesajları
    Türkçe. `MEMORY.md` ve `CLAUDE.md` Türkçe.
16. **`--self-test`.** GUI'siz uçtan uca akış, geçici klasöre yazıp siler.
    Hem CLI hem test paketi kullanıyor.

### Önceki scaffold'dan değişen kararlar (geçersiz kalanlar)

| Eski karar | Yeni durum | Neden |
|---|---|---|
| `KineCaptureStudio` environment oluştur | `KineSynth` kullan | PROMPT bölüm 2 |
| Python 3.10 pinle | 3.11.14 kullan | gerçek ortam; pyzed cp311 |
| ZED backend yazma (`not_implemented`) | Tam yazıldı | SDK ve kamera doğrulandı |
| `SessionWriter.write_frame` → `NotImplementedError` | `TakeWriter` çalışıyor | format kararlaştırıldı |
| Yalnız `mock_16` iskelet kayıtlı | + BODY_18/34/38 | yerel SDK'dan okundu |
| Tek düz `RecordingSession` modeli | Project→…→Repetition hiyerarşisi | PROMPT bölüm 4.1 |
