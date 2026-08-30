# Codex kalıcı çalışma talimatı

1. Her geliştirme görevinde önce repository kökündeki `MEMORY.md` dosyasının
   tamamını oku; ardından gerçek kodu doğrula. Kod ile hafıza çelişirse gerçek
   davranışı incele ve çelişkiyi görünür kıl.
2. Yalnız mevcut `KineSynth` conda environment'ını kullan. Yeni environment
   oluşturma veya bilimsel ortamın paketlerini gereksiz yere değiştirme.
3. Kullanıcı verisini ve değişmez ham kaydı koru; mock backend'i ve atomik
   yazım/kapanış ilkelerini çalışır tut.
4. Görev sonunda, son yanıttan önce alınan kalıcı kararları, gerçek schema ve
   uygulama sürümlerini, gerçekten çalıştırılan testleri ve doğrulanamayanları
   `MEMORY.md` içine kaydet. Hafıza güncellenmeden görev tamamlanmış sayılmaz.

Claude için `CLAUDE.md`, Codex için bu dosya aynı otoritatif `MEMORY.md`ye
yönlendirir.
