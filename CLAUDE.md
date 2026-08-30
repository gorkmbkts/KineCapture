# CLAUDE.md — kalıcı çalışma talimatları

Bu dosya kısa tutulmalıdır. Ayrıntılı ve Claude/Codex tarafından paylaşılan
otoritatif proje bağlamı `MEMORY.md` içindedir. Codex'in kısa eşleniği
`AGENTS.md` dosyasıdır.

## Her görevde

1. **Önce `MEMORY.md` dosyasının tamamını oku.** Kod ile hafıza çelişiyorsa
   kodu doğrula ve çelişkiyi bildir.
2. **Yalnızca mevcut `KineSynth` conda environment'ını kullan.**
   - Yeni environment oluşturma, `base` veya başka bir environment kullanma.
   - Interpreter: `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`
   - Doğrulama: `conda run -n KineSynth python -c "import sys; print(sys.executable)"`
   - Betikler `KineSynth` yoksa başka ortama düşmez, anlaşılır hata verir.
3. **Görev sonunda, son yanıttan önce `MEMORY.md` dosyasını güncelle.**
   Memory güncellenmeden görev tamamlanmış sayılmaz.

## Değişmez kurallar

- **Kullanıcı verisi silinmez veya üzerine yazılmaz.** Bütün JSON yazımı
  `kinecapture.core.jsonio` üzerinden atomik yapılır ve `overwrite=True`
  verilmedikçe mevcut dosyayı reddeder. Tek yıkıcı işlem
  `ProjectWorkspace.discard_take` olup çağıranın kayıt kimliğini tekrar
  yazmasını şart koşar.
- **Ham kayıt değişmezdir.** Etiketleme `take.json` dosyasına dokunmaz;
  insan kararları `annotations/segments.json` sidecar'ında durur.
- **Sentetik veri her yerde işaretlenir.** `DataOrigin.SYNTHETIC` GUI'ye,
  take metadata'sına ve export manifestine kadar taşınır.
- **Mock backend çalışır durumda tutulur.** Donanımsız geliştirme ve bütün
  otomatik testler onun üzerinden yürür.
- **Uydurma yok.** Doğrulanmamış SDK çağrısı yazma, eşleşmesi belirsiz eklemi
  doldurma, tanımlanmamış hata sınıfı ekleme. Eksik veri NaN kalır.
- **Test edilmemiş özellik tamamlanmış sayılmaz.** Çalıştırılmamış testi
  "geçti" diye yazma; yapılamayan donanım testinin nedenini açıkça belirt.
- **GUI thread bloklanmaz.** Kamera okuma ve disk yazımı ayrı thread'lerde;
  playback `QTimer` ile, bloklayan döngü yok.
- **Önizleme kaybı ile kayıt kaybı ayrı sayılır.** Bunlar tek bir sayıya
  toplanmaz.

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
```
