# Codex / GPT kalıcı çalışma talimatı

## 1. Hafıza kullanımı — bağlam bütçesi kuralı

`MEMORY.md` büyük bir arşivdir. **Tamamını okuma.** Her görevde baştan sona
okunması ciddi bağlam israfıdır ve bu projede açıkça kaldırılmıştır.

- Her görevde yalnızca **`MEMORY_INDEX.md`** dosyasını oku (≤6 KB): güncel faz,
  sürümler, modül haritası, `MEMORY.md` bölüm dizini, bilinen açıklar, sonraki
  adım.
- `MEMORY.md`'den **yalnızca göreve ilişkin bölümü** hedefli olarak aç.
  İndeks hangi bölümün nerede olduğunu söyler.
- Kod hafızadan önceliklidir. Çelişki varsa gerçek davranışı incele ve
  çelişkiyi görünür kıl.

## 2. Hafızaya yazma

- `MEMORY.md`'ye **yalnızca kalıcı bilgi** yaz: mimari karar, gerçekten
  çalıştırılmış doğrulama sonucu, sürüm/şema değişikliği, kapanan veya yeni
  açılan bilinmeyen.
- Küçük düzeltme, biçimlendirme, yeniden adlandırma ve başarısız deneme
  hafızaya yazılmaz. **"Her görev sonunda hafıza güncellenir" kuralı
  kaldırılmıştır.**
- Durum değiştiyse `MEMORY_INDEX.md`'yi güncelle; kısa dosyanın güncel kalması
  arşivin güncel kalmasından önemlidir.
- Arşiv sonsuza kadar büyümez; şişen bölümü özetleyerek sıkıştır.

## 3. Ortam

Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
oluşturma veya bilimsel ortamın paketlerini gereksiz yere değiştirme.
Interpreter: `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`

## 4. Veri ve doğruluk

- Kullanıcı verisini ve değişmez ham kaydı koru; mock backend'i ve atomik
  yazım/kapanış ilkelerini çalışır tut.
- Uydurma yok: doğrulanmamış SDK çağrısı, belirsiz eklem doldurma,
  tanımlanmamış hata sınıfı yok. Eksik veri NaN kalır.
- Test edilmemiş özellik tamamlanmış sayılmaz.
- Canlı ölçüm ile offline yeniden üretim ayrı belgelenir.

Claude için `CLAUDE.md`, Codex/GPT için bu dosya aynı hafıza politikasını
izler.
