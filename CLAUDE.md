# CLAUDE.md — kalıcı çalışma talimatları

Bu dosya kısa tutulmalıdır. Proje bağlamı `MEMORY_INDEX.md` (kısa özet) ve
`MEMORY.md` (ayrıntılı arşiv) içindedir. Codex/GPT'nin eşleniği `AGENTS.md`.

## Hafıza kullanımı — bağlam bütçesi kuralı

`MEMORY.md` büyük bir arşivdir. **Tamamını okumak yasaktır.** Her görevde baştan
sona okunması ciddi bağlam israfıdır ve bu projede açıkça kaldırılmıştır.

### Okuma

1. **Her görevde yalnızca `MEMORY_INDEX.md` dosyasını oku.** Bu dosya 6 KB'yi
   aşmaz ve şunları içerir: güncel faz, sürüm numaraları, modül haritası,
   `MEMORY.md` bölüm dizini, bilinen açıklar, anlaşılan sonraki adım.
2. **`MEMORY.md`'den yalnızca ilgili bölümü oku.** İndeks hangi bölümün nerede
   olduğunu söyler; o bölümü hedefli olarak aç (grep veya satır aralığı).
   Görevin dokunmadığı bölümleri açma.
3. **Kod hafızadan önceliklidir.** Çelişki varsa gerçek kodu doğrula ve
   çelişkiyi bildir.

### Yazma

4. `MEMORY.md`'ye **yalnızca kalıcı bir şey öğrenildiğinde** yaz:
   mimari karar, gerçekten çalıştırılmış doğrulama sonucu, sürüm/şema
   değişikliği, kapanmış veya yeni açılmış bir bilinmeyen.
5. Küçük düzeltmeler, biçimlendirme, yeniden adlandırma, başarısız deneme
   **hafızaya yazılmaz.** "Her görev sonunda hafıza güncellenir" kuralı
   kaldırılmıştır; yerine "kalıcı bilgi üretildiğinde yazılır" geçmiştir.
6. Durum değiştiyse `MEMORY_INDEX.md`'yi güncelle — bu kısa dosyanın güncel
   kalması, arşivin güncel kalmasından daha önemlidir.
7. `MEMORY.md` sonsuza kadar büyümez. Bir bölüm şişmişse eski ayrıntıyı
   özetleyerek sıkıştır; aynı bilgiyi iki yere yazma.

## Ortam

**Yalnızca mevcut `KineSynth` conda environment'ını kullan.**

- Yeni environment oluşturma; `base` veya başka bir environment kullanma.
- Interpreter: `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`
- Doğrulama: `conda run -n KineSynth python -c "import sys; print(sys.executable)"`
- Betikler `KineSynth` yoksa başka ortama düşmez, anlaşılır hata verir.

## Değişmez kurallar

- **Kullanıcı verisi silinmez veya üzerine yazılmaz.** Bütün JSON yazımı
  `kinecapture.core.jsonio` üzerinden atomik yapılır ve `overwrite=True`
  verilmedikçe mevcut dosyayı reddeder. Tek yıkıcı işlem
  `ProjectWorkspace.discard_take` olup çağıranın kayıt kimliğini tekrar
  yazmasını şart koşar.
- **Ham kayıt değişmezdir.** Etiketleme ham varlık manifestine dokunmaz;
  insan kararları ayrı sidecar dosyalarında durur.
- **Sentetik veri her yerde işaretlenir.** `DataOrigin.SYNTHETIC` GUI'ye,
  take metadata'sına ve export manifestine kadar taşınır.
- **Mock backend çalışır durumda tutulur.** Donanımsız geliştirme ve bütün
  otomatik testler onun üzerinden yürür.
- **Uydurma yok.** Doğrulanmamış SDK çağrısı yazma, eşleşmesi belirsiz eklemi
  doldurma, tanımlanmamış hata sınıfı ekleme. Eksik veri NaN kalır.
- **Test edilmemiş özellik tamamlanmış sayılmaz.** Çalıştırılmamış testi
  "geçti" diye yazma; yapılamayan donanım testinin nedenini açıkça belirt.
- **GUI thread bloklanmaz.** Kamera okuma, disk yazımı ve offline işleme ayrı
  thread veya ayrı süreçte; playback `QTimer` ile, bloklayan döngü yok.
- **Önizleme kaybı ile kayıt kaybı ayrı sayılır.** Bunlar tek bir sayıya
  toplanmaz.
- **Canlı ölçüm ile offline yeniden üretim ayrı belgelenir.** Biri diğerinin
  yerine geçmez.

## ZED SDK

- `pyzed` asla modül seviyesinde import edilmez; `kinecapture/camera/zed.py`
  içinde gecikmeli import edilir. SDK olmadan uygulama açılır ve testler geçer.
- `visualization/skeleton_spec.py` içindeki ZED eklem sıraları yerel SDK'dan
  okunmuştur. SDK yükseltilirse `python -m kinecapture.tools.verify_zed_topology`
  ile karşılaştır; fark varsa tablolar düzeltilmeden gerçek kayıt alınmamalıdır.

## Komutlar

```powershell
.\scripts\run_app.ps1              # uygulama
.\scripts\run_tests.ps1            # testler
.\scripts\diagnose.ps1             # ortam + SDK + kamera + iskelet tablosu
conda run -n KineSynth python -m kinecapture --self-test

# offline işleme
& C:\Users\gorke\anaconda3\envs\KineSynth\python.exe -B -m kinecapture.processing <take-directory>
& C:\Users\gorke\anaconda3\envs\KineSynth\python.exe -B -m kinecapture.processing --restart <partial-job-directory>

# capture diagnostic (donanımsız)
& C:\Users\gorke\anaconda3\envs\KineSynth\python.exe -B -m kinecapture.tools.capture_diagnostic --backend mock --output C:\temp\kc-diagnostic --seconds 10 --no-display
```
