---
type: hub
status: current
updated: 2026-09-21
aliases:
  - KineCapture Wiki
tags:
  - kinecapture
  - hub
---

# KineCapture Wiki

KineCapture'ın karar, doğrulama, mimari ve tarih bilgisinin insan tarafından
gezilebilen ana sayfasıdır. Kod ve testler gerçek davranışın birincil
kaynağıdır; bu wiki kanıtı bulmayı ve bağlamı küçük tutmayı sağlar.

## Şimdi

- **21 Eylül güncel kapsam:** [Kullanıcı GUI kararları](decisions/studio-gui-user-revision-2026-09-21.md) · [Claude görev promptu](../promts/CLAUDE_STUDIO_GUI_USER_REVISION_PROMPT_2026-09-21.md). Prompt hazır; uygulama ve görsel kabul açık. Eski açık işlere otomatik dönülmeyecek.

- [Kayıt hatası, kişi kaybı ve yeni GUI kararları](audits/capture-tracking-gui-issues-2026-09-20.md)
- [Önceki Claude kayıt/takip/GUI görevi](../promts/CLAUDE_CAPTURE_TRACKING_GUI_REPAIR_PROMPT_2026-09-20.md)
- [GUI kabulü yeniden açık — denetim ve nedenler](audits/studio-gui-acceptance-audit-2026-09-20.md)
- [GUI düzeltmesi — yeni karar ve fikir haritası](decisions/studio-gui-repair-2026-09-20.md)
- [Önceki Claude düzeltme görevi](../promts/CLAUDE_STUDIO_GUI_ACCEPTANCE_REPAIR_PROMPT_2026-09-20.md)
- [Güncel durum](../MEMORY_INDEX.md)
- [Açık sorular](open-questions.md)
- [18 Eylül canlı ZED doğrulaması](experiments/2026-09-18-live-zed.md)
- [Studio GUI — onaylı tasarım](decisions/studio-gui-refinement-2026-09-19.md)
- [Studio GUI — fikir haritası ve gerekçeler](decisions/studio-gui-design-map-2026-09-19.md)
- [Claude GUI faz planı ve uygulama görevi](../promts/CLAUDE_STUDIO_GUI_FINAL_REFINEMENT_PROMPT_2026-09-19.md)

## Sistemi anla

- [Sistem haritası](architecture/system-map.md)
- [Hafıza ve token mimarisi](architecture/memory-system.md)
- [Veri hattı](concepts/pipeline.md)
- [Etiket ve feature sözleşmesi](concepts/annotation-and-features.md)
- [RGB-D ve depth](concepts/rgbd-and-depth.md)
- [Kimlik ve erişim](concepts/identity-and-access.md)
- [Kişi seçimi ve subject lock](concepts/subject-selection.md)
- [Veri bütünlüğü ve kanıt](concepts/data-integrity.md)
- [Test ve ölçüm ortamı](protocols/test-and-measurement.md)

## Tarih ve kaynaklar

- [Git kilometre taşları](milestones/git-history.md)
- [Studio F0–F15](milestones/studio-f0-f15.md)
- [Kaynak sicili](sources/source-registry.md)
- [Belge sicili](sources/document-registry.md)
- [Konuşma sicili](sources/conversation-registry.md)
- [Hafıza aktarım denetimi (18 Eylül 2026)](audits/claude-memory-migration-audit-2026-09-18.md)
- [Tarihsel MEMORY arşivi](archive/memory/index.md)
- [Prompt arşivi](../promts/index.md)
- [Plan ve rapor arşivi](archive/reports/index.md)

## AI çalışma yolu

1. `MEMORY_INDEX.md` ile başla.
2. Bu hub'dan yalnız ilgili atomik notu aç.
3. Gerekirse kodu, testi, Git'i veya hedefli eski kaynağı doğrula.
4. Kalıcı bir bilgi oluştuysa [AI hafıza iş akışını](protocols/ai-memory-workflow.md)
   uygula.

## Obsidian ile kullan

- [Obsidian başlangıç ve günlük kullanım rehberi](obsidian-usage.md)
- Kasa olarak repository kökünü (`KineCapture`) aç; yalnız `knowledge`
  klasörünü açma. Böylece `MEMORY_INDEX.md`, kaynak belgeler ve wiki
  bağlantıları birlikte çalışır.
