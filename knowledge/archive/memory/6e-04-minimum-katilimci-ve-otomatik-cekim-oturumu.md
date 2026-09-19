---
type: legacy-memory-section
status: archived
title: "Minimum katılımcı ve otomatik çekim oturumu"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "865-891"
---

[Tarihsel hafıza dizinine dön](index.md) · Bölüm: [6E. Kimlik, proje erişimi ve katılımcıdan kayda akış (2026-08-26)](6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · ← [önceki](6e-03-proje-sahipligi-ve-yetki.md) · [sonraki](6e-05-gui.md) →

Güncel karşılığı: [Kimlik ve erişim](../../concepts/identity-and-access.md).

### Minimum katılımcı ve otomatik çekim oturumu

- Yeni `Participant`: `participant_id`, `code`, `created_at`,
  `created_by_user_id`, `schema_version`. Boy, kilo, dominant taraf ve serbest
  not yeni modelden ve Katılımcılar ekranından çıkarıldı.
- `participant_id == code` (`P0001`, `P0002`, ...). Kod proje içinde anonim,
  değişmez ve kompakt kalıcı kimliktir. Kompaktlık Windows'taki derin take
  yollarının üçüncü taraf araç sınırını aşmaması için önemlidir.
- Kod + proje sayacı, proje kökündeki exclusive allocation lock altında
  birlikte güncellenir. Ayrı `ProjectWorkspace` nesnelerinden eşzamanlı 12
  tahsis testi `P0001..P0012` sonucunu verdi.
- Katılımcılar sayfası arama, kod, kayıt sayısı, son kayıt zamanı,
  `Katılımcı Ekle`, `Kayda Başla` ve `Kayıtlarını Gör` içerir. Manuel oturum,
  onam, operatör ve biyometrik form yoktur.
- `Kayda Başla` erişimi yeniden doğrular; tek planı otomatik, plan yoksa
  serbest modu seçer, yalnız birden fazla planda kısa seçim ister. Aynı uygulama
  çalışmasında aynı kullanıcı/proje/katılımcı/plan için uygun açık otomatik
  session yeniden kullanılır.
- Proje/katılımcı değişimi, logout ve güvenli kapanış otomatik session'ı
  `ended_at` + neden ile kapatır. Önceki uygulama çalışmasından açık otomatik
  session yeni çekimde deterministik olarak orphan sayılıp kapatılır; sessizce
  aktif kabul edilmez.
- `Session.operator` okunabilir ad snapshot'ıdır; yeni
  `Session.operator_user_id` kalıcı kullanıcı bağlantısıdır. Aynı alan
  `Take.operator_user_id` içine de kopyalanır; kullanıcı adı değişse bile kayıt
  operatörü kaybolmaz.
