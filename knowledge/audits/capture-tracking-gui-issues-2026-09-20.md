---
type: audit
status: open
updated: 2026-09-20
tags: [capture, subject-tracking, studio, gui, decision]
---

# Kayıt başlangıcı, kişi kapsamı ve son GUI talepleri

## Durum ve yeni kararlar

`observed`: Kullanıcı son Claude onarımı sonrasında kayıt başlatma hatası ve
donmuş önizleme, videonun ikinci bölümünde iskelet kaybı, kaybolan sağ yardımcı
panel ve kırpılan bildirim eylemleri bildirdi; altı ekran görüntüsü sağladı.
Bu not salt okunur inceleme ve görev brifidir; bu turda ürün kodu/ayar/veri
değiştirilmedi, kamera veya yeniden işleme testi yapılmadı.

`decision`: Her açılış Projeler; bu oturumda proje seçilmeden diğer sayfalar
açılmaz. Proje seçilince yalnız Yakalama ayrıca katılımcı gerektirir; eksikse
tek uyarıyla Projeler'e yönlendirilir. Otomatik katılımcı oluşturma kaldırılır.
Kamera görüntüsünde seçilen beden ile proje katılımcısı ayrı kavramdır.

`decision`: Etiketleme sağ paneli kamera/özet/kişi içerikleriyle görünür,
kaydırmasız geri gelecek; temel preset sayısı azaltılabilir. Alt hareket/hata
editörü korunacak. Yakalama sağ panelindeki durum bölgesi sabit yer kaplayacak;
uyarı değişince denetimler zıplamayacak. RGB gerçek oranıyla gösterilecek;
kazanılan yatay alan sabit çekim bilgilerine ayrılabilir. Canlı RGB'deki büyük
kişi/kadraj yönlendirmeleri kaldırılıp tek kişi seçimi popup'ı korunacak.
Bildirim metni/butonları kesilmeyecek. Tam ekran kararı geçerlidir.

`decision`: Claude fazları planlayıp onay beklemeden uygular; sonuçları her
fazda Obsidian'a kaydeder; kullanıcıya sonda tek rapor verir.

## Salt okunur doğrulanan bulgular

### Etkin veri kökü

`verified`: `load_config().dataset_root`, 20 Eylül incelemesinde Claude
scratchpad test alanına işaret ediyor:

`C:\Users\gorke\AppData\Local\Temp\claude\C--Users-gorke-Desktop-KineCapture\669f5dfe-dadd-45eb-8c6b-5d3a0a82e402\scratchpad\waste_home\datasets`

`last_project_path` ise `C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4`.
Bunlar ayrı kavramlardır. Kullanıcı ayarında test yolu bulunduğu kesin;
hangi işlem yazdı, SDK başlangıç hatasını uzun yol mu yoksa başka etken mi
tetikledi henüz `open`. Otomatik ayar düzeltmesi veya dosya taşıması yapılmadı.

`verified`: `C:\Users\gorke\KineCapture\logs\kinecapture.log` içinde
20 Eylül 22:23:03, 22:24:08 ve 22:59:27'de `zed_recording_failed` /
`SVO RECORDING ERROR`. `camera/zed.py::start_native_recording`, SDK başarısız
olunca genel disk/izin önerisi döndürüyor; mesaj disk/izin kök nedenini kanıtlamaz.

### Sorunlu gerçek kayıt

GUI TEST projesinin yukarıdaki kökünde:

`participants/P0001/sessions/ses_20260916T151622_57a9/takes/take_20260920T195059_c183/derived/processing/run_4b8fd122e2c44eee`

`verified` (metadata ve mmap dizileri salt okunur):

- İşlenmiş 1473 kare; state `partial`, published true; BODY_38.
- Capture 1475; SVO başlığı 1474; okunan 1473; eşleşen 1473; eşleşmeyen 2.
- Beş issue: `capture_frames_unmatched`, `capture_timestamp_duplicated`,
  `source_frame_count_mismatch`, `source_timestamp_gap`,
  `subject_anchor_before_recording`.
- `subject_present.npy`: 622 true, son true sıfır tabanlı indeks 623.
  624'ten itibaren tüm eklem değerleri NaN; başlangıca göre 10,600615 saniye.
- Subject association: locked 622, lost 4, ambiguous 847; reassociations 0.
  `same_id_evidence_conflict` olayı frame_index 626'da. Olay indeksi ile dizi
  indeksinin farklı semantiği source map üzerinden ayrıca çözülmeli.
- Kaydedilmiş timestamp ve source-position dizilerinde geriye gidiş 0.
  Bu kontrol bütün kaynak eşlemesinin doğruluğu anlamına gelmez.
- `job.subject_status=associated`; association son state `ambiguous`.

`hypothesis`: Aynı tracker kimliğinde kanıt çatışması ve yeniden kazanım
akışı uzun süreli kişi kaybını açıklayabilir. SDK adayları, çatışma metriği,
ayna etkisi ve eşleme yolu yeniden incelenmeden kesin kök neden sayılmaz.
Bu bulgu yalnız render arızasından farklıdır: kaydedilmiş diziler de eksiktir.

### Kaynak kapsamı uyarısının anlamı

`verified`: `studio/services/library.py::VersionRow.coverage_verified` şu an
`not self.issues` döndürüyor. Library viewmodel bunun false oluşunda
`coverage_unverified` mesajını çıkarıyor. Bu nedenle mesaj genel bir bulgu
işaretidir; tek başına kişinin kaybolduğu veya tüm kaydın bozuk olduğu anlamına
gelmez. Burada gerçekten 2 eşleşmeyen kare vardır. Çok daha geniş kişi kaybı
ayrı bir eksendir; iki sorun aynı isim altında anlatılmamalı.

`verified`: Log 22:51:25'te kamera 11 kare düşürdü / SDK 2 kareyi SVO'ya
yazmadı bildiriyor. Bu sayaçların paydaları ve anlamları farklıdır; toplanıp
“13 eşleşmeyen kare” diye yorumlanamaz. Yeniden işleme hamda bulunmayan kareyi
geri getiremez; kişi ilişkilendirme kusurunun giderilmesi başka bir olasılıktır.

### Görünmeyen sağ panel

`verified`: Panel sınıfı kodda var. `ReviewPage.set_inspector_visible` doğrudan
`side_tabs.setVisible` çağırıyor; shell genel inspector tercihini sayfaya
aktarabiliyor. `observed`: Kullanıcı görüntüsünde panel/ikonlar yok. Tam
neden görünürlük/yaşam döngüsü/geometri incelemesine kadar `open`.

## Kanıt konumu ve görev

Görseller wiki içine kopyalanmadı. Kullanıcı dosyalarının değişmemiş kopyaları:
`C:\Users\gorke\.codex\visualizations\2026\09\20\capture-tracking-input-evidence`.
`input-01` ve `02`: iskelet önce/sonra; `03`: kapsam; `04`: sürüm;
`05`: kayıt hatası; `06`: kırpılan bildirim. Uzantıları `.png`.

- [Claude uygulama promptu](../../promts/CLAUDE_CAPTURE_TRACKING_GUI_REPAIR_PROMPT_2026-09-20.md)
- [Önceki onarım raporu](../reports/studio-gui-acceptance-repair-validation.md)
- [Önceki kabul denetimi](studio-gui-acceptance-audit-2026-09-20.md)

Önceki P1–P7 uygulama/ölçüm geçmişi korunur. Kullanıcının bu yeni gerçek
kullanım bulguları çözülmeden kapsamın tümü kabul edilmiş sayılmaz.
