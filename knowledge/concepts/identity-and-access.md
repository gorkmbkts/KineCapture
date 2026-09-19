---
type: concept
status: verified
updated: 2026-09-18
tags:
  - identity
  - authorization
  - projects
---

# Kimlik ve proje erişimi

## Model

- Yerel-first kimlik katmanı SQLite kullanır; parolalar açık metin tutulmaz,
  scrypt ile türetilir.
- Sistem sahibi/admin korumalıdır; normal kullanıcı yalnız yetkili projeleri
  görür.
- Kullanıcı hesabı operatör kimliğinin kaynağıdır; serbest metin operatör adı
  yeni akışta gerekli değildir.
- Katılımcı minimum anonim kodla temsil edilir.
- Kullanıcı yolculuğu giriş → proje → katılımcı → kayda başla şeklindedir.
- Capture session veri modelinde korunur fakat kullanıcı için otomatik yönetilir.
- Kalıcı proje silme yalnız yetkili sistem sahibi tarafından, yol güvenliği ve
  açık onayla yapılır.

## Veri koruma

Eski operatör, katılımcı ve session alanları silinmez. Yeni sade arayüz eski
veriyi yok etmeden daha az alan ister. Kimlik veritabanı ile değişmez capture
varlıkları ayrı sorumluluklardır.

Kaynaklar:
[auth uygulama promptu](../../promts/CODEX_AUTH_PROJECT_PARTICIPANT_REDESIGN_PROMPT.md),
[proje silme görevi](../../promts/CLAUDE_PROJECT_DELETE_LABELING_EXPORT_GUI_PROMPT.md),
.

## Tarihsel kaynaklar

Bu notun dayandığı bölünmüş eski hafıza kayıtları. Tarihsel ayrıntı
gerekmedikçe açılmaz.

- [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](../archive/memory/6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md)
- [Kalıcı proje silme (yalnız Sistem Sahibi)](../archive/memory/6i-04-kalici-proje-silme-yalniz-sistem-sahibi.md)

Tam liste: [Tarihsel MEMORY arşivi](../archive/memory/index.md).
