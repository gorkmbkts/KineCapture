---
type: concept
status: verified
updated: 2026-09-18
tags:
  - annotation
  - features
  - export
---

# Etiket ve feature sözleşmesi

## Etiket modeli

- İki seviye ayrıdır: hareket aralığı ve hata aralığı.
- Doğru/hatalı kararı ayrı elle yazılan bayrak değil, hata aralıklarından
  türetilen sonuçtur.
- Etkilenen anatomik roller bir eklem sınıflandırıcısı değildir; koçun hata
  kanıtını zenginleştirir.
- Boş eklem bilgisinin “sorulmadı”, “yanıtsız”, “hiçbiri” ve legacy bilinmeyen
  anlamları birbirinden ayrılır.
- Annotation değişiklikleri tek atomik yazım ve tek undo adımıdır.
- Ham kayıt ve eski sidecar'lar yerinde göç ettirilmez; kayıpsız okunur.

## Feature katmanı

- Sürümlü registry seçilebilir özellik ailelerini tanımlar.
- Ham eklem dizileri korunur; türetilmiş özellikler tekrar üretilebilir.
- Canonical çekirdek, kalite/geçerlilik, koordinat dönüşümleri, geometri,
  zamansal kinematik, açılar, simetri ve sabit uzunluklu özetler ayrı ailelerdir.
- Eksik veri doldurulmaz; maske/NaN semantiği export'a taşınır.
- Feature fingerprint'i sözleşme ve seçimi temsil eder.

Kaynaklar:
[annotation redesign](../../promts/CLAUDE_ANNOTATION_REDESIGN_PROMPT.md),
[feature export görevi](../../promts/CLAUDE_SKELETON_FEATURE_EXPORT_PROMPT.md),
[etkilenen eklem görevi](../../promts/CLAUDE_AFFECTED_JOINT_EVIDENCE_AND_GUI_POLISH_PROMPT.md),
.

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [6B. İki seviyeli etiketleme redesign'ı (2026-08-21)](../archive/memory/6b-6b-iki-seviyeli-etiketleme-redesign-i-2026-08-21.md)
- [6C. Seçilebilir iskelet özellikleri (2026-08-23)](../archive/memory/6c-6c-secilebilir-iskelet-ozellikleri-2026-08-23.md)
- [6F. Capture ve İnceleme/Etiketleme sadeleştirme promptu (2026-08-27)](../archive/memory/6f-6f-capture-ve-inceleme-etiketleme-sadelestirme-promptu-2026-08-27.md)
- [6G. Capture ve İnceleme/Etiketleme sadeleştirmesi — UYGULANDI (2026-08-28)](../archive/memory/6g-6g-capture-ve-inceleme-etiketleme-sadelestirmesi-uygulandi-2026-08-28.md)
- [6H. Sonraki Claude GUI/veri görevi — prompt hazırlığı (2026-08-30)](../archive/memory/6h-6h-sonraki-claude-gui-veri-gorevi-prompt-hazirligi-2026-08-30.md)
- [6I. Proje silme, türetilmiş correctness, timeline önizlemesi ve GUI (2026-08-30)](../archive/memory/6i-6i-proje-silme-turetilmis-correctness-timeline-onizlemesi-ve-gui-2026-08.md)
- [6J. Etkilenen eklem kanıtı ve GUI iyileştirmeleri promptu (2026-08-31)](../archive/memory/6j-6j-etkilenen-eklem-kaniti-ve-gui-iyilestirmeleri-promptu-2026-08-31.md)
- [6K. Etkilenen eklem kanıtı ve GUI cilası — UYGULANDI (2026-08-31)](../archive/memory/6k-6k-etkilenen-eklem-kaniti-ve-gui-cilasi-uygulandi-2026-08-31.md)
- [6L. Yeni sınıfı dialogu yeniden açmadan kaydetme düzeltmesi (2026-08-31)](../archive/memory/6l-6l-yeni-sinifi-dialogu-yeniden-acmadan-kaydetme-duzeltmesi-2026-08-31.md)
- [6AC. Studio F8 — Etiketleme, kanonik sidecar 1.1.0 (2026-09-14)](../archive/memory/6ac-6ac-studio-f8-etiketleme-kanonik-sidecar-1-1-0-2026-09-14.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
