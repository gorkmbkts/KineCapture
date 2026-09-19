---
type: legacy-memory-section
status: archived
title: "GUI"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "530-540"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6C. Seçilebilir iskelet özellikleri (2026-08-23)](6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md) · ← [önceki](6c-06-fingerprint-duzeltmesi-gercek-hata.md) · [sonraki](6c-08-kendi-arastirmamla-eklediklerim-promptta-yoktu.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

### GUI

Export ekranına "Veri ve özellik seçimi" kartı ve aranabilir bir dialog
eklendi: kategori ağacı, satır başına Türkçe ad + şekil/birim + destek durumu
+ deneysel işareti + devre dışıysa gerekçe, 5 preset, arama, seçim özeti.
Önizleme seçili özellik/dizi sayısını, üretilemeyecek özellik sayısını,
filtrelenen kayıt sayısını ve sıkıştırma öncesi tahmini boyutu gösterir.
Son seçim kullanıcı tercihlerine (`export_feature_ids`) yazılır; testler
izole edilmiş `USER_STATE_PATH` kullandığı için gerçek ayar dosyasına
dokunulmaz. Özellik hesapları export worker thread'inde çalışır.
