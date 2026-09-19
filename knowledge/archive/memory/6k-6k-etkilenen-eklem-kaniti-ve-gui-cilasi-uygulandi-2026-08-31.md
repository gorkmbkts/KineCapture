---
type: legacy-memory-section
status: archived
title: "6K. Etkilenen eklem kanıtı ve GUI cilası — UYGULANDI (2026-08-31)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1560-1714"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6j-6j-etkilenen-eklem-kaniti-ve-gui-iyilestirmeleri-promptu-2026-08-31.md) · [sonraki](6l-6l-yeni-sinifi-dialogu-yeniden-acmadan-kaydetme-duzeltmesi-2026-08-31.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6K. Etkilenen eklem kanıtı ve GUI cilası — UYGULANDI (2026-08-31)

`CLAUDE_AFFECTED_JOINT_EVIDENCE_AND_GUI_POLISH_PROMPT.md` uygulandı.

### Ürün kararı: bu bir eklem sınıflandırıcısı DEĞİLDİR

Hata aralığına eklenen eklem bilgisi **node-level evidence/relevance
denetimidir**: ileride eğitilecek graph-temporal modele hatanın iskeletin
neresinde göründüğünü söyler. Modelin girdisinden hiçbir düğüm çıkarılmaz —
`joints_xyz` bütün native topolojiyi taşımaya devam eder. Bu cümle export
manifestine (`label_contract.joint_evidence.purpose`) ve README'ye yazıldı ki
sözleşmeyi okuyan biri alanı yanlış amaçla kullanmasın.

### Topolojiden bağımsız rol sözlüğü — tek otorite

- Depolanan değer eklem indeksi değil **kanonik anatomik roldür**.
- Tek otorite `kinecapture.features.roles` (`ALL_ROLES`, 26 rol). **Taşınmadı,
  kopyalanmadı**: feature katmanı zaten onu kullanıyordu, ikinci bir tablo
  ikisinin sessizce ayrışmasına izin verirdi.
- Sebep karışık dataset: aynı sürümde BODY_18 ve BODY_34 bir arada olabilir ve
  `19` numaralı düğüm ikisinde farklı yerdedir. Rol ile hedef uzayı tek kalır.
- Bir rol o topolojide yoksa **seçilemez** ve repository katmanı yine de gelen
  böyle bir değeri `role_not_in_skeleton` ile reddeder. Doğrulanmış boşluklar:
  `zed_body_18` → pelvis yok; `mock_16` → topuk/el/burun/spine_mid yok.
- Rol listesinde bulunmayan eklemler export'tan **atılmaz**, yalnız hedef
  üretiminde kullanılmaz. `zed_body_38` için hedef dışı düğümler picker'da
  sayıyla anlatılır (uydurma koordinatta çizilmez).

### Boş olmanın dört ayrı anlamı (`JointAnnotationStatus`)

| Durum | Anlam | `supervises_nodes` | `is_reviewed` |
|---|---|---|---|
| `selected` | Bir/daha fazla rol işaretlendi | True | True |
| `not_applicable` | İncelendi; belirli eklem hedefi yok | False | True |
| `indeterminate` | İncelendi; güvenilir belirlenemiyor | False | True |
| `unreviewed` | Hiç incelenmedi (eski veri dahil) | False | False |

Maskelenmek **negatif etiket değildir**. Dördünü tek "boş" değere indirmek
eğitimde sessizce yanlış negatif üretirdi. `selected` boş rol listesiyle,
boş olmayan rol listesi başka bir durumla saklanamaz
(`joint_status_without_roles` / `roles_without_selected_status`).

### Tek atomik yazım ve tek undo adımı

`AnnotationRepository.update_error_interval(...)` sınıf + not + durum + rolleri
**tek** işlemde uygular. Önce `copy.deepcopy` üzerinde doğrular, sonra tek
`_snapshot()` / `_changed()` yapar. Ayrı setter'larla yazmak bir kullanıcı
kararını üç undo adımına bölüyor ve yarısı uygulanmış bir aralık bırakabiliyordu
(yeni sınıf + eski eklemler). Reddedilen düzenleme aralığı hiç değiştirmez.

### Eski dosyalarla uyum — kayıpsız, göç yok

- Eski `affected_joints` **hep korunur** (`legacy.affected_joints`).
- Göç **hep-ya-hiç**: değerlerin tamamı role çevrilebiliyorsa `selected`
  okunur; biri bile çevrilemiyorsa hiçbiri çevrilmez, aralık `unreviewed`
  kalır. Yarım göç tamamlanmış gibi görünürdü.
- Dosya açmak onu **yeniden yazmaz**: test dosyanın baytlarını ve
  `st_mtime_ns` değerini karşılaştırıyor.
- Tanınmayan `joint_status` değeri `unreviewed` sayılır — bilinmeyen bir
  kelime, birinin verdiği karar gibi okunamaz.

### Etiket hazırlığı ile eklem kapsaması AYRI ölçülür

Eklem incelemesi yapılmamış kayıt export'a girer; zamansal hata sınıfı eğitimi
etkilenmez. Kapsama ayrı raporlanır: `joint_annotation_counts()` dört durumu
sayar, timeline ipucu ve inceleme durum satırı seçili aralığın durumunu
**yazıyla** söyler. Birleştirmek ya kullanılabilir veriyi bloklardı ya da node
denetimindeki boşluğu gizlerdi.

### Eklem seçici (`gui/widgets/joint_picker.py`)

- **Sabit şematik önden görünüş**, veriye bağlı yerleşim değil: bir take'e göre
  hesaplanan yerleşim kayıttan kayda oynar ve aynı vücut parçasını farklı yere
  koyardı.
- Önden bakıldığı için **sporcunun solu ekranın sağında** çizilir. Figürün
  üstünde "◀ Sporcunun sağı / Sporcunun solu ▶" bandı bunu yazıyla da söyler.
  Testler merkezden simetriyi ve tıklama-rol eşleşmesini ayrıca doğruluyor.
- Durum yalnız renkle değil, seçili eklemin üzerindeki **işaretle** de belli
  edilir. Vuruş yarıçapı 17 px (trackpad ile kullanılabilir olsun diye).
- Roller `ALL_ROLES` sırasında saklanır: iki annotatör aynı eklemleri farklı
  sırayla tıklarsa dosya yine aynı olur.
- Klavye ile gezinme ve `accessibleName` var.

### Export sözleşmesi (release 2.2.0)

Her zaman yazılan, kayıpsız ve küçük interval dizileri:
`error_interval_joint_multi_hot uint8 [K,R]`,
`error_interval_joint_mask uint8 [K]`,
`error_interval_joint_status int8 [K]` (dört durum maskede kaybolmasın diye).
`store_error_target_arrays` açıkken ek olarak
`error_joint_target uint8 [T,C,J]` (J = **native** düğüm sayısı) ve
`error_joint_label_mask uint8 [T,C]`.

Manifest `label_contract.joint_evidence` bloğu rol listesini, `role_to_index`,
`status_codes`, her durumun eğitimdeki anlamını, sürümde geçen her iskelet
biçimi için `role_to_native_node` tablosunu, `role_mapping_source` ve
`role_mapping_version = "anatomical-roles-1.0.0"` değerini yayınlar. Yoğun
diziler yazılmasa bile `dense_target_recipe` onları interval dizilerinden
birebir yeniden üretmeye yeter (test bunu gerçekten yeniden üretip
karşılaştırıyor).

Doğrulama: `unknown_joint_status`, `unknown_anatomical_role`,
`selected_without_roles`, `roles_without_selected_status`,
`joint_mask_disagrees_with_status`. Fingerprint eklem durumuna ve rol
listesine duyarlı.

### Klasörü kaybolmuş proje kaydı (yetim kayıt)

`DeletionService.forget_orphan(actor, project_id)` **yalnız** ön kontrol
`delete_target_missing` döndüğünde çalışır; başka her guard başarısızlığı
(manifest uyuşmazlığı, symlink, izin) `not_an_orphan_record` ile reddedilir —
"silinemiyor" hatası sessizce "kaydı at" işlemine dönüşemez. Dosya sistemine
**hiç dokunmaz**. Yine owner'a özel, yine proje adı birebir yazılır. Denetim
olayı ayrıdır: `project_record_removed`, metadata'sında `files_deleted: false`.
`DeleteProjectDialog(orphan=True)` başlığı, uyarı metnini ve buton yazısını
değiştirir; klasör yalnızca taşındıysa geri getirilmesi gerektiğini söyler.

### GUI cilası

- Nav rail: `navToggle` rolü ile Daralt düğmesi ortalandı; logo ile düğme
  arasına 10 px sabit boşluk widget'ı kondu ve **logo ile birlikte** gizleniyor.
  Test bunu gizli widget geometrisinden değil `layout().minimumSize()`
  üzerinden ölçüyor (Qt gizli widget'ın son dikdörtgenini bırakır).
- Giriş ekranı: paketlenmiş logo (yeni kopya üretilmedi), 360–520 px ortalanmış
  kolon, `QScrollArea` (kısa ekranda buton aşağı taşmasın), placeholder'lar,
  açık `setTabOrder`, `accessibleName`, kaydırılabilir footer. Logo yüklenmezse
  giriş ekranı tamamen çalışır — dekorasyon taşıyıcı değildir.
- Üretim launcher'ı `window.showMaximized()` çağırır (ekran dikdörtgenine
  resize DEĞİL: task bar, çok monitör ve per-monitor DPI yanlış olurdu).
  Pencere yapıcısı normal boyutta açar, böylece viewport testleri hâlâ
  yeniden boyutlandırabilir.

### Sürümler (bu turda değişen gerçek sabitler)

app **0.10.0**, annotation **2.2.0**, release **2.2.0** (üçü de bu fazda
yükseltildi; eklemeler geriye dönük uyumlu olduğu için minor). Değişmeyenler:
project 1.1.0, session 2.0.0, take 1.1.0, skeleton stream 1.1.0, label 2.0.0,
feature spec 1.0.0, raw archive 1.0.0, identity SQLite schema 1.

### Bu turda bulunan/düzeltilen gerçek hatalar

- `JointAnnotationStatus.parse()` bir str-Enum üyesini `str(value)` ile
  okuyunca `"JointAnnotationStatus.SELECTED"` elde ediyor ve `unreviewed`'a
  düşüyordu → `isinstance(value, cls)` erken dönüşü eklendi.
- `release.py` `resolve_roles` fonksiyonunu import etmeden kullanıyordu
  (`NameError`, 18 teste yayılıyordu).
- Hata penceresi BODY_18'de minimum 862 px yüksekliğe çıkıyordu; 700 px
  ekrana sığmıyordu. Minimum pencere boyutunu büyütmek yerine picker minimumu
  ve yardımcı metin yükseklikleri kısıldı → 591 px. Kesilen topoloji notu
  tooltip ile tam metin olarak erişilebilir.

### Bu turda GERÇEKTEN çalıştırılanlar

(Ayrıntılı sayılar bölüm 9'da.)
