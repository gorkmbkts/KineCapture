---
type: guide
status: current
updated: 2026-09-18
aliases:
  - Obsidian Kullanım Rehberi
tags:
  - obsidian
  - workflow
---

# Obsidian başlangıç ve günlük kullanım

## Kasayı bir kez ekle

1. Obsidian'da **Open folder as vault** seç.
2. `C:\Users\gorke\Desktop\KineCapture` klasörünü seç.
3. Sol taraftan `knowledge/index.md` dosyasını aç.

Kasa kökü `knowledge` değil, `KineCapture` olmalıdır. Böylece
`MEMORY_INDEX.md`, bölünmüş hafıza arşivi, proje belgeleri ve kaynak kod aynı bilgi
uzayında kalır.

## Günlük gezinme

- Başlangıç noktası: [KineCapture Wiki](index.md).
- Güncel durum ve en kısa yönlendirme: [MEMORY_INDEX](../MEMORY_INDEX.md).
- `Ctrl+O`: ada göre hızlı not açma.
- Sağ üstte **Backlinks**: açık nota hangi notların bağlandığını görme.
- Sol şeritte **Graph view**: proje kavramları arasındaki bağlantıları görme.
- Arama: bir karar, modül, test veya hata adını bütün kasada bulma.

Graf görünümü bir doğruluk kaynağı değil, gezinme haritasıdır. Bir iddia
için kod, test, değişmez veri ve Git kanıtı wiki notundan daha güçlüdür.

## AI ile çalışma

Codex'e doğal dille “KineCapture wiki hafızasını kullan” denebilir; açıkça
çağırmak istersen `$kinecapture-wiki` yaz. Claude Code'da
`/kinecapture-wiki` kullan. İki ajan da aynı repository içindeki aynı
atomik notları ve [AI hafıza iş akışını](protocols/ai-memory-workflow.md)
okur.

Her görevde bütün kasa prompt'a yüklenmez. Ajan önce `MEMORY_INDEX.md`
okur, sonra yalnız görevle ilgili birkaç notu açar. Eski ayrıntı gerekirse
[bölünmüş tarihsel arşivden](archive/memory/index.md) tek mini not seçilir.

## Kaynak sicilini yenile

Yeni Git commitleri, proje belgeleri veya yerel Claude/Codex oturumları
oluştuğunda repository kökünde şu komut çalıştırılır:

```powershell
C:\Users\gorke\anaconda3\envs\KineSynth\python.exe scripts\update_knowledge_sources.py
```

Bu işlem ham konuşmaları kasaya kopyalamaz. Kaynak yolu, boyut, hash ve
ayıklanmış kullanıcı istemlerini [Konuşma siciline](sources/conversation-registry.md)
yazar. Böylece kayıt izlenebilir kalırken başlangıç bağlamı şişmez.

## Kalıcı bilgi eklerken

- Tek konu için tek küçük not kullan.
- Aynı bilgiyi kopyalamak yerine bağlantı ver.
- Doğrulanmış sonuç ile hipotezi açıkça ayır.
- Yalnız güncel durum veya yönlendirme değiştiyse `MEMORY_INDEX.md`yi güncelle.
- `MEMORY.md` yönlendiricisine yeni günlük/oturum dökümü ekleme.

## Şablonlar

Yeni not açarken kopyalanacak iskeletler. Şablonun kendisi bilgi taşımaz.

- [Karar notu](templates/decision.md) — bilinçli ürün veya mimari tercih
- [Deney notu](templates/experiment.md) — gerçekten çalıştırılmış ölçüm
- [Modül notu](templates/module.md) — bir paketin sorumluluğu ve değişmezleri

## Graf yapısı

Kasa üç yönlü bağlanır; hiçbir not yalnız bir dizine asılı kalmaz.

1. **Dizinler** giriş noktasıdır: [MEMORY_INDEX](../MEMORY_INDEX.md),
   [wiki ana sayfası](index.md), [tarihsel arşiv dizini](archive/memory/index.md).
2. **Konu bağları** tarihsel mini notu güncel notuna bağlar. Her arşiv notunda
   `Güncel karşılığı:` satırı, her güncel notta `Tarihsel kaynaklar` bölümü
   vardır.
3. **Küme bağları** bir bölümün alt notlarını birbirine ve üst nota bağlar
   (`Bölüm:`, `Alt notlar:`, önceki/sonraki).

Görev brifleri ve raporlar sonuçlarına bağlıdır; böylece "bu istenmişti" ile
"bu yapıldı" arasında yürünebilir.

Bağlantılar wiki `[[...]]` biçiminde değil, göreli Markdown biçimindedir;
`.obsidian/app.json` içindeki `useMarkdownLinks` ve `newLinkFormat: relative`
ayarları bununla uyumludur. Yeni not eklerken aynı biçimi kullan.

Nokta ile başlayan klasörler (`.claude`, `.agents`, `.github`) Obsidian
tarafından zaten gizlenir; oradaki dosyalar kasaya ve grafa girmez.
