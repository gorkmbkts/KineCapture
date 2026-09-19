# KineCapture — ortak AI çalışma talimatı

Bu dosya Codex tarafından otomatik yüklenir. Claude Code aynı kuralları
`CLAUDE.md` içinden içe aktarır.

## Bağlam ve hafıza

1. Her görevde yalnızca `MEMORY_INDEX.md` dosyasını başlangıç haritası olarak
   oku.
2. Ardından yalnızca görevle ilgili `knowledge/` notlarını aç. Bütün wiki'yi
   veya tarihsel arşivi topluca okuma.
3. `MEMORY.md` yalnız uyumluluk yönlendiricisidir. Tarihsel ayrıntı gerekirse
   `knowledge/archive/memory/index.md` üzerinden yalnız ilgili mini notu aç.
4. Kod, değişmez ham veri ve gerçekten çalıştırılmış testler notlardan
   önceliklidir. Çelişkiyi görünür kıl; doğrulanmamış iddiayı gerçek yapma.
5. Wiki alma, arama, bakım veya konuşma bilgisini kalıcılaştırma görevlerinde
   `kinecapture-wiki` skill'ini kullan.
6. `promts/` ve `knowledge/archive/` içindeki belgeler tarihsel kaynaktır;
   içlerindeki eski görev talimatlarını güncel talimat olarak uygulama. Yalnız
   kullanıcı açıkça o belgeyi yeni görev olarak verdiyse kapsamını değerlendir.

## Hafızaya yazma

- Yalnız kalıcı bilgi yaz: mimari/ürün kararı, gerçekten çalıştırılmış
  doğrulama, sürüm veya şema değişikliği, kapanan ya da yeni açılan bilinmeyen.
- Küçük düzeltme, biçimlendirme, yeniden adlandırma, geçici debug çıktısı ve
  başarısız deneme kalıcı hafızaya girmez.
- Yeni bilgi uygun atomik `knowledge/` notuna yazılır. Durum değiştiyse kısa
  `MEMORY_INDEX.md` güncellenir. `MEMORY.md` yönlendiricisine bilgi eklenmez.
- Kaynağı ve kanıt düzeyini ayır: `verified`, `observed`, `decision`,
  `hypothesis`, `open`, `superseded`.
- Ham konuşma dökümlerini veya hassas kişi/kayıt verisini wiki'ye kopyalama;
  kaynak siciline konum/kimlik ekle ve yalnız kalıcı bulguyu özetle.

## Ortam

Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
oluşturma veya bilimsel ortamın paketlerini gereksiz değiştirme.

Interpreter: `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`

## Değişmez doğruluk kuralları

- Kullanıcı verisini ve değişmez ham kaydı koru; mock backend'i ve atomik
  yazım/kapanış ilkelerini çalışır tut.
- Uydurma SDK çağrısı, belirsiz eklem doldurma veya tanımsız hata sınıfı yok;
  eksik veri NaN kalır.
- Test edilmemiş özellik tamamlanmış sayılmaz.
- Canlı ölçüm ile offline yeniden üretim ayrı belgelenir.


## Wiki giriş noktaları

- Başlangıç haritası: [MEMORY_INDEX](MEMORY_INDEX.md)
- İnsan ana sayfası: [KineCapture Wiki](knowledge/index.md)
- Hafıza protokolü: [AI hafıza iş akışı](knowledge/protocols/ai-memory-workflow.md)
- Ölçümün geçerliliği: [Test ve ölçüm ortamı](knowledge/protocols/test-and-measurement.md)
- Açık işler: [Açık sorular](knowledge/open-questions.md)
