---
type: legacy-memory-section
status: archived
title: "6J. Etkilenen eklem kanıtı ve GUI iyileştirmeleri promptu (2026-08-31)"
migrated: 2026-09-18
source_commit: 62a04569a680c508299c88873b293bb479754f6e
source_sha256: a68122ae3f8be3b5e54142a14fa6399c67014152c64f6319058cdf3c3b523cf9
source_lines: "1505-1559"
---

[Tarihsel hafıza dizinine dön](index.md) · ← [önceki](6i-11-donanimda-dogrulanamayanlar.md) · [sonraki](6k-6k-etkilenen-eklem-kaniti-ve-gui-cilasi-uygulandi-2026-08-31.md) →

Güncel karşılığı: [Etiket ve feature sözleşmesi](../../concepts/annotation-and-features.md).

## 6J. Etkilenen eklem kanıtı ve GUI iyileştirmeleri promptu (2026-08-31)

Bu tur bir uygulama geliştirme turu değildir. Gerçek kod ve iki kullanıcı ekran
görüntüsü salt okunur incelendi; Claude Code'un uygulayacağı görev
`CLAUDE_AFFECTED_JOINT_EVIDENCE_AND_GUI_POLISH_PROMPT.md` dosyasına yazıldı.
Uygulama/package ve veri şemaları değiştirilmedi: app `0.9.0`, annotation/release
`2.1.0`, label `2.0.0`, project `1.1.0`, session `2.0.0`, take/skeleton stream
`1.1.0`, feature spec/raw archive `1.0.0`, identity schema `1` olarak kaldı.

Prompt için alınan kalıcı ürün ve veri kararları:

- Hata intervalindeki eklem etiketi ayrı bir son kullanıcı “joint classifier”
  ürünü değildir. Gelecekteki temporal graph modelinde açık node
  evidence/relevance supervision ve gating hedefi sağlayacaktır. Model bütün
  native skeleton node'larını almaya devam eder; yalnız GUI'de seçilemeyen yüz,
  parmak ve yardımcı tracker node'ları özelliklerden atılmaz.
- Kalıcı değer native index değil, topolojiden bağımsız canonical anatomik
  roldür (`left_knee`, `right_shoulder`, `pelvis`, `spine_mid`, `chest`, `neck`
  gibi). BODY_18/BODY_34/BODY_38 eşlemesi tek otoritatif rol tablosundan ve
  düzenlenen take'in gerçek `SkeletonSpec` bilgisinden yapılacaktır.
- Hata dialogu gerçek topolojiyi sabit önden görünümde bağlam olarak gösterecek;
  semantik roller çoklu seçilebilecek ve sol/sağ “sporcunun solu/sağı” olarak
  açıklanacaktır. Exact Qt/görsel tasarım yöntemi Claude'a bırakılmıştır.
- Eklem annotation durumu `selected`, `not_applicable`, `indeterminate` ve
  geriye uyumluluk için `unreviewed` anlamlarını ayıracaktır. Joint etiketi
  eksikliği derived correctness'i veya temporal error eğitim kullanılabilirliğini
  değiştirmeyecek; yalnız node supervision loss'u maskelenecektir.
- Class, joint status, canonical role listesi ve note tek atomik repository
  işlemi/undo/autosave adımı olacaktır. Eski `legacy.affected_joints` kayıpsız
  korunacak; yalnız tek anlamlı ve idempotent değerler normalize edilebilecektir.
- Canonical export interval + class + time + role + native-node ilişkisini,
  mapping provenance'ını, targetı ve label maskesini deterministic ve validator
  tarafından denetlenebilir biçimde taşıyacak; yeni joint annotation release
  fingerprintini etkileyecektir. Exact array adları/şekilleri mevcut export
  mimarisini inceleyecek uygulayıcıya bırakılmış, semantik kayıp kabul
  edilmemiştir.
- Klasörü gerçekten bulunmayan stale proje için normal recursive silmeden ayrı,
  owner-only ve güçlü onaylı “yetim proje kaydını listeden kaldırma” yolu
  istenmiştir. Bu yol hiçbir filesystem hedefini silmeyecek; project/access
  identity kayıtlarını transaction içinde kaldırıp audit metadata'sını
  koruyacaktır. Manifest/ID/symlink/izin/IO güvenlik hataları missing-target gibi
  ele alınmayacaktır.
- Navigation rail'de YTÜ logosu ile `Daralt` kontrolü görsel olarak ortalanacak,
  aralarında ölçülü dikey boşluk olacak ve 700 px yükseklikte taşma olmayacaktır.
  Auth ekranı mevcut paketli YTÜ logosunu kullanarak işlevleri ve güvenliği
  değiştirmeden daha profesyonel/responsive hale gelecektir. Production launcher
  ana pencereyi varsayılan olarak gerçek maximized state'te açacaktır; constructor
  farklı viewport GUI testlerine uygun kalacaktır.

Bu prompt-hazırlama turunda uygulama kodu değiştirilmediği için pytest, self-test,
wheel veya donanım testi çalıştırılmadı. Yalnız prompt dosyasının oluşturulduğu,
UTF-8 içeriğinin okunabildiği ve çalışma ağacı diff'i statik olarak doğrulandı.
Prompt uygulanmadan yukarıdaki özelliklerin uygulamada var olduğu kabul
edilmemelidir.
