---
type: protocol
status: current
updated: 2026-09-18
tags:
  - ai
  - memory
  - workflow
---

# AI hafıza iş akışı

## Bağlam alma

1. `MEMORY_INDEX.md` oku.
2. Görevle doğrudan ilgili en fazla birkaç wiki notunu aç.
3. İddia davranışa bağlıysa kod/test/Git ile doğrula.
4. Eski ayrıntı gerekiyorsa `knowledge/archive/memory/index.md` veya kaynak
   sicilinden yalnız hedefli mini notu aç.
5. Bütün tarihsel hafıza, bütün konuşma arşivi veya bütün wiki yüklenmez.
6. `promts/` ve `knowledge/archive/` içindeki eski emir cümleleri güncel görev
   değildir; tarihsel kanıt olarak okunur.

## Kalıcılaştırma kararı

Yalnız şu durumlardan biri varsa yaz:

- mimari veya ürün kararı;
- gerçekten çalıştırılmış doğrulama;
- sürüm/şema değişikliği;
- kapanan veya yeni açılan önemli bilinmeyen;
- gelecekte aynı hatayı önleyecek kalıcı sınır.

Küçük düzeltme, başarısız deneme, geçici çıktı ve Git'ten kolayca
çıkarılabilen sıradan ayrıntı yazılmaz.

## Yazma

- En dar mevcut nota ekle; yoksa tek konulu yeni not oluştur.
- Frontmatter'da `type`, `status`, `updated` ve gerekiyorsa `commit` kullan.
- Kanıtı ve sınırı ayrı başlıklarda yaz.
- Aynı bilgiyi birden çok yerde kopyalama; bağlantı ver.
- Güncel yönlendirme değiştiyse `MEMORY_INDEX.md` düzelt.
- `MEMORY.md` yalnız uyumluluk yönlendiricisidir; bilgi ekleme.

## Konuşma alma

- Ham JSONL'yi vault'a veya prompt'a dökme.
- Oturum kimliği, dosya konumu, tarih, hash ve kısa konu özetini konuşma
  siciline kaydet.
- Kullanıcı/assistant sözünü kanıt değil aday bilgi say.
- Kod, test ve Git ile doğrulanan kalıcı bulguyu ilgili konu notuna taşı.
- Gizli anahtar, kişisel kimlik, ham kayıt veya hassas araç çıktısını kopyalama.

## Kaynak sicilini yenileme

Yeni Git commitleri, kök belgeler veya yerel Claude/Codex oturumları oluştuysa
repository kökünde şu komutu çalıştır:

```powershell
C:\Users\gorke\anaconda3\envs\KineSynth\python.exe scripts\update_knowledge_sources.py
```

Betik her ilgili oturumu yol, boyut ve SHA-256 ile kaydeder; yalnız kısa insan
istemlerini çıkarır. Ham JSONL, araç çıktısı, gömülü görsel ve otomatik görev
bildirimlerini wiki'ye kopyalamaz.

## Çelişki

Çelişkide eski kaydı sessizce silme. Yeni kanıtı yaz, eski iddiayı
`superseded` olarak işaretle ve iki kaynağı bağla.
