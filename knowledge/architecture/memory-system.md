---
type: architecture-decision
status: decision
updated: 2026-09-18
tags:
  - memory
  - obsidian
  - tokens
---

# Hafıza ve token mimarisi

## Karar

Obsidian repository kökünü vault olarak açar. Paylaşılan gerçek `knowledge/`
altındaki küçük Markdown notlarıdır. `MEMORY.md` yalnız eski araçlar için kısa
bir yönlendiricidir; eski içerik küçük tarihsel notlara bölünmüştür.

## Bağlantı topolojisi

Dizin yapısı gezinme içindir, **anlam taşımaz**. Anlamı bağlantılar taşır ve üç
yönlüdür; bu sayede hiçbir not yalnız bir dizine asılı kalmaz:

1. **Dizin bağı** — giriş noktası (`MEMORY_INDEX`, wiki ana sayfası, arşiv
   dizini).
2. **Konu bağı** — tarihsel mini not ⇄ güncel konu notu. Arşiv tarafında
   `Güncel karşılığı:`, güncel not tarafında `Tarihsel kaynaklar`.
3. **Küme bağı** — bir bölümün alt notları birbirine ve üst nota
   (`Bölüm:`, `Alt notlar:`, önceki/sonraki).

Görev brifleri ve raporlar sonuç notlarına bağlanır, böylece "istenen" ile
"yapılan" arasında yürünebilir. Ayrıntı ve biçim kuralı:
[Obsidian kullanımı](../obsidian-usage.md).

## Yükleme bütçesi

```text
AGENTS.md / CLAUDE.md
        ↓
MEMORY_INDEX.md          birkaç KB, her görevde
        ↓
1–3 ilgili wiki notu     yalnız gerektiğinde
        ↓
hedefli kod/test/Git     doğrulama gerektiğinde
        ↓
archive/memory / konuşma yalnız hedefli kaynak araştırmasında
```

Bu yapı büyük arşivi, eski sohbetleri veya bütün wiki'yi her oturuma eklemez.

## Paylaşım

- Codex `AGENTS.md` ve `.agents/skills/kinecapture-wiki` kullanır.
- Claude Code `CLAUDE.md` üzerinden `AGENTS.md` içe aktarır ve
  `.claude/skills/kinecapture-wiki` kullanır.
- Her iki skill aynı [ortak protokole](../protocols/ai-memory-workflow.md)
  yönelir.
- Claude auto-memory veya ürün içi kişisel hafıza ikincildir; repository
  gerçeğini sessizce geçersiz kılamaz.

## Yazma ilkesi

Yeni bilgi atomik nota yazılır. Durum değiştiyse `MEMORY_INDEX.md` düzeltilir.
`MEMORY.md` yönlendiricisine bilgi eklenmez. Ham sohbetler kopyalanmaz; konumları ve özetleri
[konuşma sicilinde](../sources/conversation-registry.md) tutulur.

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [KineCapture Studio — Proje Hafızası](../archive/memory/00-kinecapture-studio-proje-hafizasi.md)
- [1. Bu belge nasıl kullanılmalı?](../archive/memory/1-1-bu-belge-nasil-kullanilmali.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
