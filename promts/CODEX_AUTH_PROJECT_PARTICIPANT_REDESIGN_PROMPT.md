# KineCapture Studio — Codex Uygulama Promptu

> **Bu görevin izi:** [6E uygulama kaydı](../knowledge/archive/memory/6e-6e-kimlik-proje-erisimi-ve-katilimcidan-kayda-akis-2026-08-26.md) · [Kimlik ve erişim](../knowledge/concepts/identity-and-access.md)
>
> Tarihsel görev brifi. Güncel talimat değildir; yalnız kullanıcı açıkça görevlendirirse yürütülür.


## Görev

KineCapture Studio'nun giriş, kullanıcı yönetimi, proje erişimi, kayıt planı ve
katılımcıdan kayda geçiş akışlarını yeniden tasarla ve uçtan uca uygula.

Ana ürün hedefi şudur: Teknik bilgisi sınırlı bir spor antrenörü uygulamayı
kullanıcı adı ve şifresiyle açabilmeli, erişebildiği projeyi seçebilmeli,
katılımcıyı seçip tek bir **Kayda Başla** eylemiyle mevcut Capture ekranına
geçebilmelidir.

Hedef kullanıcı akışı:

```text
Uygulamayı aç
    -> Kullanıcı adı ve şifreyle giriş yap
    -> Erişilebilir projeyi seç
    -> Katılımcıyı seç veya ekle
    -> Kayda Başla
    -> Capture ekranı
```

Kullanıcıdan operatör adı, teknik oturum seçimi veya her kayıt öncesinde
protokol seçimi istenmemelidir. Bunlar giriş yapan kullanıcı ve proje bağlamı
üzerinden mümkün olduğunca otomatik yönetilmelidir.

---

## 1. Çalışmaya başlamadan önce zorunlu inceleme

1. Repository kökündeki `MEMORY.md` dosyasının **tamamını** oku.
2. `CLAUDE.md`, `README.md`, `pyproject.toml`, `configs/default.yaml` ve ilgili
   gerçek uygulama kodlarını incele.
3. En azından aşağıdaki alanların mevcut davranışını doğrula:
   - `src/kinecapture/gui/main_window.py`
   - `src/kinecapture/gui/state.py`
   - `src/kinecapture/gui/pages/projects.py`
   - `src/kinecapture/gui/pages/participants.py`
   - `src/kinecapture/gui/pages/capture.py`
   - `src/kinecapture/dataset/workspace.py`
   - `src/kinecapture/domain/project.py`
   - `src/kinecapture/core/config.py`
   - ilgili testler
4. Hafıza ile kod çelişirse gerçek kodu doğrula; çelişkiyi sessizce varsayma.
5. Değişiklik yapmadan önce kısa bir uygulama planı hazırla, fakat kullanıcıdan
   burada açıkça kararlaştırılmış ürün ayrıntılarını yeniden sorma.

Yalnızca mevcut `KineSynth` conda environment'ını kullan. Yeni environment
oluşturma ve mevcut bilimsel ortamın paketlerini gereksiz yere yükseltme.

---

## 2. Kesin ürün kararları

### 2.1 Kullanıcı türleri

İlk sürümde yalnızca iki kullanıcı türü bulunacak:

1. **Sistem Sahibi / Admin**
   - Sistemde yalnızca bir tane olabilir.
   - İlk kurulumda oluşturulan ilk hesap bu hesaptır.
   - Silinemez, pasif yapılamaz ve normal kullanıcıya dönüştürülemez.
   - Bütün projeleri görebilir ve bütün yetkilere sahiptir.
   - Kullanıcı oluşturabilir, kullanıcıları aktif/pasif yapabilir, şifre
     sıfırlayabilir ve proje erişimlerini yönetebilir.

2. **Kullanıcı**
   - Giriş ekranındaki **Yeni Kullanıcı Oluştur** akışıyla oluşturulabilir.
   - Bu akış asla ikinci bir admin hesabı oluşturamaz.
   - Hesap oluşturulduktan sonra aktif normal kullanıcı olarak giriş yapabilir.
   - Kendisine atanmış projeleri ve kendisinin oluşturduğu projeleri görebilir.
   - Kendi projesini oluşturabilir.
   - Başka kullanıcıların hesaplarını veya erişimlerini yönetemez.

Karmaşık rol matrisi, editör/izleyici gibi ek roller veya ikinci admin bu
görevin kapsamında değildir.

### 2.2 Eski veriler

Şimdiye kadar üretilen katılımcı, oturum ve kayıt verileri yalnızca test
verisidir. Bunlar için geriye dönük veri migrasyonu zorunlu değildir. Temiz bir
başlangıç yapılabilir ve eski test datasetleri silinebilir.

Ancak silme işlemi sırasında:

- Önce gerçek `dataset_root` ve silinecek KineCapture proje dizinlerini kesin
  olarak çözümle ve doğrula.
- Repository kökünü, kullanıcı profilini, disk kökünü veya geniş/belirsiz bir
  klasörü hedefleme.
- Yalnızca doğrulanmış KineCapture test datasetlerini temizle.
- Kaynak kodu, promptları, `MEMORY.md` veya repository içeriğini silme.
- Sonuçta neyin temizlendiğini açıkça raporla.

Eski test verilerini korumak adına yeni mimariyi karmaşıklaştırma. Buna rağmen
ham kayıt değişmezliği, atomik yazım ve güvenli kapanış gibi projenin temel
veri güvenliği ilkelerini yeni veriler için koru.

---

## 3. SQLite kimlik ve erişim mimarisi

SQLite uygulama düzeyindeki şu bilgilerin otoritatif kaynağı olmalıdır:

- Kullanıcı hesapları
- Güvenli parola doğrulama bilgileri
- Tek sistem sahibi/admin kaydı
- Kullanıcı aktif/pasif durumu
- Son giriş zamanı
- Proje sahipliği
- Kullanıcı-proje erişim atamaları
- Gerekli küçük uygulama/audit metadata'sı

RGB, derinlik, SVO2, MP4, JSONL ve diğer büyük çekim dosyalarını SQLite içine
koyma. Mevcut dosya tabanlı kayıt mimarisi devam etmelidir. SQLite kimlik,
yetki ve proje erişim katmanını yönetmelidir; büyük bilimsel veri dosya
sisteminde kalmalıdır.

### 3.1 Veritabanı konumu ve servis katmanı

- Veritabanı için tek, deterministik ve kullanıcı tarafından yanlışlıkla proje
  sanılmayacak bir uygulama veri konumu belirle. Windows üzerinde tercihen
  uygulamanın yerel veri klasörü altında kullan; yolu config/path yardımcıları
  üzerinden çözümle ve testlerde geçici yol enjekte edilebilir yap.
- GUI bileşenleri doğrudan SQL çalıştırmamalıdır.
- Ayrı bir repository/service katmanı oluştur. Örneğin `auth` veya `identity`
  paketi altında bağlantı, schema, kullanıcı repository'si, parola işlemleri
  ve yetki servisini ayır.
- Bütün sorgularda parametreli SQL kullan.
- `PRAGMA foreign_keys = ON`, uygun `busy_timeout`, açık transaction sınırları
  ve güvenilir kapanış uygula. WAL seçilecekse test ederek ve gerekçesiyle seç.
- Schema sürümünü veritabanında sakla. İlk kurulum ve sonraki açılış idempotent
  olmalıdır.
- GUI thread'ini uzun veritabanı işlemleriyle bloklama; mevcut Qt mimarisiyle
  uyumlu hareket et.

### 3.2 Asgari tablo modeli

Adlar uygulama koduna göre değişebilir, fakat model en az şu kavramları
karşılamalıdır:

#### `users`

- `user_id`: kalıcı ve kullanıcı adından bağımsız kimlik
- `username`: kullanıcıya gösterilen ad
- `username_normalized`: büyük/küçük harf duyarsız benzersiz karşılaştırma
- `password_hash`
- parola algoritması için gereken `salt` ve parametre/sürüm bilgileri
- `first_name`
- `last_name`
- `title`
- `role`: yalnızca `owner` veya `user`
- `is_active`
- `must_change_password`
- `created_at`
- `updated_at`
- `last_login_at`

Veritabanı düzeyinde de ikinci bir `owner` oluşmasını engelleyen bir kısıt veya
partial unique index kullan.

#### Proje kayıt ve erişimleri

En azından şu ilişkileri sakla:

- Proje kimliği ile doğrulanmış proje klasörü arasındaki kayıt
- Projeyi oluşturan/sahip kullanıcı
- Kullanıcı-proje erişim ataması
- Atamayı yapan kullanıcı ve zaman damgası

Bir normal kullanıcı yeni proje oluşturduğunda otomatik olarak o projenin
sahibi ve erişim sahibi olmalıdır. Sistem sahibi bütün projelere örtük olarak
erişebilmelidir; her proje için ayrıca satır oluşturulmasına bağımlı olmasın.

Dosya sistemi ve SQLite arasında proje oluşturma sırasında yarım durum kalırsa
telafi/rollback veya açık onarım yolu sağla. Aynı proje kimliğinin iki farklı
klasöre sessizce bağlanmasına izin verme.

### 3.3 Parola güvenliği

- Parolaları hiçbir zaman açık metin saklama veya loglama.
- Standart ve incelenebilir bir parola türetme yöntemi kullan. Mevcut ortamda
  güvenilir bir parola hashing kütüphanesi zaten varsa sürümünü doğrula;
  gereksiz bağımlılık kurmak yerine gerekirse Python standart
  kütüphanesindeki `hashlib.scrypt` + kriptografik rastgele salt kullan.
- Karşılaştırmayı zamanlama saldırılarına dayanıklı biçimde yap.
- Parola formatına algoritma/sürüm/parametre bilgisi ekle ki ileride yeniden
  hash edilebilsin.
- En az 8 karakter iste; parola doğrulama alanı zorunlu olsun.
- Başarısız giriş mesajı kullanıcı adı veya paroladan hangisinin yanlış
  olduğunu ifşa etmesin.
- Pasif kullanıcı giriş yapamasın.
- Uygulama tercihleri yalnızca son kullanıcı adını hatırlayabilir; parolayı
  düz metin olarak hatırlama veya config'e yazma.

---

## 4. İlk açılış, giriş ve yeni kullanıcı ekranları

Ana `MainWindow` ve çalışma sayfaları kimlik doğrulaması tamamlanmadan aktif
hale gelmemelidir. Son proje otomatik açma işlemi de girişten ve erişim
kontrolünden önce çalışmamalıdır.

### 4.1 İlk kurulum

Veritabanında hiç kullanıcı yoksa normal giriş formu yerine şu ekranı göster:

```text
KineCapture Studio
İlk Kurulum — Sistem Sahibi Hesabı

Ad              [________________]
Soyad           [________________]
Unvan           [________________]
Kullanıcı adı   [________________]
Şifre           [________________]
Şifre tekrar    [________________]

[ Sistem Sahibi Hesabını Oluştur ]
```

İlk hesap atomik biçimde tek `owner` olarak oluşturulmalıdır. İki eşzamanlı
ilk kurulum denemesi ikinci owner üretememelidir.

### 4.2 Normal giriş ekranı

```text
KineCapture Studio

Kullanıcı adı  [________________]
Şifre          [________________]  [Göster]

[ Oturum Aç ]

Yeni misiniz? [Yeni Kullanıcı Oluştur]
```

Beklenen davranışlar:

- Enter ile giriş yapılabilsin.
- Parola varsayılan olarak gizli olsun.
- Caps Lock veya hatalı giriş için anlaşılır fakat bilgi sızdırmayan mesaj
  gösterilsin.
- Başarılı girişten sonra parola alanı temizlensin.
- `last_login_at` güncellensin.
- `must_change_password` işaretliyse çalışma alanına geçmeden parola değiştirme
  ekranı açılsın.

### 4.3 Yeni kullanıcı oluşturma

Giriş ekranındaki düğme şu formu açmalıdır:

```text
Yeni Kullanıcı Oluştur

Ad              [________________]
Soyad           [________________]
Unvan           [________________]
Kullanıcı adı   [________________]
Şifre           [________________]
Şifre tekrar    [________________]

[Vazgeç] [Hesap Oluştur]
```

- Ad, soyad, kullanıcı adı, parola ve parola tekrarı zorunludur.
- Unvan görünür bir alan olmalı, fakat boş bırakılabilsin.
- Kullanıcı adı boşluklardan arındırılmalı, izin verilen karakterler açıkça
  doğrulanmalı ve büyük/küçük harf farkına rağmen benzersiz olmalıdır.
- Form alanlarının hataları ilgili alanın altında gösterilmelidir.
- Bu ekran yalnızca normal `user` oluşturabilir.
- Başarılı oluşturma sonrası giriş ekranına dön ve yeni kullanıcı adını giriş
  alanında hazır göster; parolayı taşıma.

---

## 5. Oturum açmış kullanıcı bağlamı ve çıkış

`AppState` veya uygun bir üst seviye servis içinde doğrulanmış `current_user`
bağlamı bulunmalıdır. Sayfalar güvenlik kararlarını yalnızca buton gizleyerek
değil servis katmanında da uygulamalıdır.

Üst bağlam çubuğunu şu kavramlarla güncelle:

```text
Kullanıcı | Proje | Katılımcı | Kamera | Disk
```

Mevcut görünür `Oturum` chip'ini kaldır. Oturum teknik olarak arka planda
korunabilir fakat antrenörün sürekli yönetmesi gereken bir üst bağlam olarak
gösterilmemelidir.

Kullanıcı adı/ad-soyad chip'i veya menüsü en az şu işlemleri sunmalıdır:

- Şifre Değiştir
- Oturumu Kapat
- Yalnız owner için: Kullanıcıları Yönet

Çıkış sırasında:

- Kayıt sürüyorsa mevcut güvenli durdurma/onay davranışını koru.
- Aktif otomatik çekim oturumunu güvenli biçimde kapat.
- Aktif proje, katılımcı ve kullanıcı bağlamını temizle.
- Parola veya hassas bilgi bellekte/görsel alanda bırakılmadan giriş ekranına
  dön.

---

## 6. Admin kullanıcı ve erişim yönetimi

Yalnız sistem sahibinin erişebildiği modern bir **Kullanıcılar ve Erişimler**
ekranı veya modal çalışma alanı oluştur.

Liste en az şunları göstermeli:

- Ad soyad
- Unvan
- Kullanıcı adı
- Aktif/pasif durum
- Erişebildiği proje sayısı
- Son giriş zamanı

İşlemler:

- Yeni normal kullanıcı oluştur
- Kullanıcı bilgilerini düzenle
- Aktif/pasif yap
- Geçici parola belirleyerek parola sıfırla
- Sıfırlama sonrası ilk girişte parola değişimini zorunlu kıl
- Kullanıcıya proje ata veya erişimini kaldır

Kurallar:

- Owner hesabı listede açıkça “Sistem Sahibi” olarak görünmeli.
- Owner silme, pasifleştirme, rol değiştirme ve proje erişimini kısıtlama
  kontrolleri hem GUI hem servis katmanında reddedilmelidir.
- Kullanıcıları fiziksel olarak silme; eski kayıtların operatör bağlantısı için
  pasifleştirme kullan.
- Proje erişimi kaldırmak proje verisini silmemelidir.

---

## 7. Projeler ve Kayıt Planı arayüzü

### 7.1 Projeler sayfası

Sayfa başlığını **Projeler** olarak sadeleştir. Normal kullanıcı yalnızca:

- Kendisine atanmış projeleri
- Kendisinin oluşturduğu projeleri

görmelidir. Owner bütün projeleri görür.

Normal kullanıcı arayüzünde teknik `Klasörden aç`, dataset kökü değiştirme ve
benzeri dosya sistemi kontrollerini gösterme. Gerekliyse owner/gelişmiş ayarlar
altında tut.

Yeni proje oluşturma en az proje adı ve isteğe bağlı kısa açıklamayla mümkün
olsun. Projeyi oluşturan normal kullanıcı otomatik sahip/erişim sahibi olsun.

Giriş sonrası yönlendirme:

- Kullanıcının erişebildiği son proje hâlâ geçerliyse açılabilir.
- Tek erişilebilir proje varsa otomatik açıp Katılımcılar sayfasına geç.
- Birden fazla proje varsa Projeler sayfasını göster.
- Hiç proje yoksa “Henüz erişebildiğiniz bir proje yok” boş durumu ve
  **Yeni Proje** eylemi göster.
- Yetkisiz bir `last_project_path` asla otomatik açılmamalıdır.

### 7.2 Protokol terminolojisi

Kullanıcıya görünen `Protokol` ifadesini **Kayıt Planı** olarak değiştir.
Domain sınıfları ve dosya şeması teknik olarak `CaptureProtocol` adını
koruyabilir; gereksiz toplu rename yapma.

Kayıt planı oluşturmayı antrenör için sadeleştir:

1. Plan adı
2. Kaydedilecek hareketlerin sıralı listesi
3. Özet ve kaydet

Mevcut doğru/hatalı kayıt hedefi, hata türü, taraf, kamera yönü, tekrar sayısı,
operatör talimatı ve güvenlik notu gibi ayrıntıları silmek zorunda değilsin;
bunları varsayılan olarak kapalı **Gelişmiş hedefler** bölümünde göster.

- Tek kayıt planı varsa otomatik seç.
- Plan yoksa serbest kayıt kullan.
- Birden fazla uygun plan varsa ancak o zaman kısa bir plan seçim adımı göster.

---

## 8. Katılımcılar ekranının yeniden tasarımı

Sayfanın adı yalnızca **Katılımcılar** olmalıdır.

Boy, kilo, dominant taraf, katılımcı ayrıntı formu, katılımcı notu, operatör
alanı, onam seçici, görünür yeni oturum formu, oturum kapatma ve oturum geçmişi
bu sayfadan kaldırılmalıdır.

Yeni katılımcı modeli ve arayüzü için minimum bilgi:

- Kalıcı `participant_id`
- Proje içinde anonim ve benzersiz katılımcı kodu (`P0001`, `P0002`, ...)
- Oluşturulma zamanı
- Oluşturan kullanıcı kimliği

Katılımcı listesi en az şunları göstermeli:

- Katılımcı kodu
- Toplam kayıt sayısı
- Son kayıt zamanı veya “Henüz kayıt yok”

Arama alanı ekle. Liste büyük olduğunda kullanılabilir kalmalıdır.

Ana eylemler:

- **Katılımcı Ekle**
- Seçili katılımcı için belirgin birincil **Kayda Başla**
- Gerekliyse ikincil **Kayıtlarını Gör**; mevcut sayfalara yönlendirebilir

Yeni katılımcı penceresi yalnızca otomatik üretilecek kodu göstermelidir:

```text
Yeni katılımcı

Katılımcı kodu: P0004
Kod otomatik oluşturulacaktır.

[Vazgeç] [Ekle] [Ekle ve Kayda Başla]
```

Kod tahsisi yarış durumunda aynı kodu iki kez üretmemelidir. Katılımcı
oluşturma ve proje sayacını güncelleme atomik/güvenilir olmalıdır.

---

## 9. Otomatik çekim oturumu ve Capture entegrasyonu

Mevcut `Session` kavramını veri düzeni ve kayıt ilişkileri için arka planda
koru; kullanıcıdan elle oluşturmasını veya kapatmasını isteme.

**Kayda Başla** eylemi atomik/öngörülebilir biçimde:

1. Seçilen projeye erişimi tekrar doğrular.
2. Seçilen katılımcıyı aktif yapar.
3. Giriş yapan kullanıcının kalıcı kimliğini ve kullanıcı adını operatör olarak
   bağlar.
4. Tek plan varsa onu, plan yoksa serbest kayıt modunu seçer.
5. Gerekirse arka planda bir çekim oturumu oluşturur.
6. Mevcut Capture sayfasına yönlendirir.

Aynı uygulama çalışması içinde aynı kullanıcı + proje + katılımcı için açık ve
uygun bir otomatik oturum varsa tekrar kullanılabilir. Katılımcı değişimi,
proje değişimi, çıkış veya güvenli uygulama kapanışında oturumu kapat. Çökme
sonrası sahipsiz açık oturumları sessizce aktif kabul etme; deterministik bir
onarım/kapatma politikası uygula.

`Session.operator` gibi mevcut okunabilir alanları koruyabilirsin fakat ayrıca
kalıcı `operator_user_id` bağlantısı ekle. Kullanıcı adı daha sonra değişse bile
kaydın kimin tarafından alındığı kaybolmamalıdır.

Capture sayfasının ana yerleşimini bu görevde yeniden tasarlama. Yalnızca yeni
akış için gerekli bağlam, boş durum mesajı ve yönlendirme entegrasyonlarını
değiştir. Dashboard, İnceleme, Dataset, Export ve Ayarlar sayfalarının ana
işlevlerini ve tasarımını değiştirme.

---

## 10. Yetkilendirme kuralları

GUI'de bir düğmeyi gizlemek yetkilendirme değildir. Aşağıdaki her işlem servis
katmanında da doğrulanmalıdır:

- Proje açma
- Proje listeleme
- Proje oluşturma/sahiplik kaydı
- Katılımcı listeleme ve oluşturma
- Otomatik oturum oluşturma
- Kayıt başlatma
- Projeye kullanıcı atama/kaldırma
- Kullanıcı yönetimi ve parola sıfırlama

Aktif kullanıcı pasif yapılırsa bir sonraki korunan işlemde veya en geç sonraki
girişte erişimi reddedilmelidir. SQL injection, path traversal ve yetkisiz
`last_project_path` senaryolarını test et.

---

## 11. Hata mesajları ve Türkçe arayüz

- Kod, sınıf adları, schema alanları ve docstring'ler İngilizce kalmalıdır.
- Kullanıcıya görünen bütün yeni metinler Türkçe olmalıdır.
- Hataları alanın yanında veya mevcut hata bandında anlaşılır biçimde göster.
- Ham SQLite hatasını, dosya yolunu, parola hash'ini veya traceback'i son
  kullanıcıya gösterme; ayrıntıyı güvenli loga yaz.
- Loglarda parola, geçici parola veya hash bulunmamalıdır.

---

## 12. Test ve doğrulama zorunlulukları

Mevcut testleri yeni ürün kararlarına göre güncelle ve yeni regresyon testleri
ekle. En az aşağıdakileri doğrula:

### Kimlik ve SQLite

- Boş veritabanında ilk kurulum
- İlk hesabın tek owner olması
- İkinci owner oluşturmanın GUI dışında servis/DB düzeyinde de reddi
- Yeni kullanıcı ekranının yalnız normal kullanıcı oluşturması
- Kullanıcı adının büyük/küçük harf duyarsız benzersizliği
- Parolanın hiçbir yerde açık metin saklanmaması
- Doğru ve yanlış parola davranışı
- Pasif kullanıcının giriş yapamaması
- Son giriş zamanının güncellenmesi
- Admin parola sıfırlama ve zorunlu parola değiştirme
- Owner'ın pasifleştirilememesi/silinememesi
- Schema kurulumunun tekrar çalıştırılınca bozulmaması

### Yetki ve proje

- Normal kullanıcının yalnız atanmış veya sahip olduğu projeleri görmesi
- Owner'ın bütün projeleri görmesi
- Normal kullanıcının oluşturduğu projeye otomatik sahip olması
- Yetkisiz son proje yolunun açılmaması
- Erişim kaldırmanın proje dosyasını silmemesi

### Katılımcı ve otomatik oturum

- Katılımcının yalnız minimum yeni alanlarla oluşturulması
- Katılımcı kodlarının proje içinde benzersiz ve sıralı olması
- Ekle ve Kayda Başla akışı
- Operatörün giriş yapan kullanıcıdan otomatik gelmesi
- `operator_user_id` kalıcılığı
- Proje/katılımcı/kullanıcı değişiminde otomatik oturum davranışı
- Çıkış ve uygulama kapanışında güvenli temizlik

### GUI

- İlk kurulum, giriş ve yeni kullanıcı formlarının çizdirilmesi
- Alan bazlı validasyon
- Owner yönetim ekranının yalnız owner için görünmesi
- Katılımcılar sayfasında boy/kilo/oturum formlarının bulunmaması
- Bağlam çubuğunda kullanıcı/proje/katılımcı/kamera/disk görünümü
- Minimum desteklenen pencere boyutunda kontrollerin kırpılmaması
- Açık ve koyu temada yeni ekranların kullanılabilir olması

Mock backend'i çalışır tut. Kamera donanımı gerektirmeyen bütün testler mock ile
çalışmalıdır. GUI thread bloklanmamalı ve mevcut kayıt güvenliği regresyona
uğramamalıdır.

Doğrulama için en az:

```powershell
.\scripts\run_tests.ps1
conda run -n KineSynth python -m kinecapture --self-test
```

komutlarını çalıştır. Uygun GUI smoke/paint testlerini de çalıştır. Test
edemediğin gerçek kamera davranışını test edilmiş gibi raporlama.

---

## 13. MEMORY.md ve Codex kalıcı hafızası — zorunlu

Bu görevde `MEMORY.md` yalnız Claude'a ait bir dosya olarak ele alınmamalıdır.
Claude ve Codex için ortak, otoritatif proje hafızasıdır.

Uygulama tamamlandıktan ve testler çalıştırıldıktan sonra, son yanıtı vermeden
önce:

1. `MEMORY.md` başındaki kullanım talimatını açıkça **“Claude veya Codex yeni
   bir geliştirme oturumunda önce bu dosyanın tamamını okur”** anlamına gelecek
   şekilde güncelle.
2. Bu görevde alınan ürün ve mimari kararları ekle:
   - Tek owner/admin modeli
   - Normal kullanıcı self-registration akışı
   - SQLite kimlik ve proje erişim katmanı
   - Parola güvenliği ve DB konumu
   - Proje sahipliği/atama kuralları
   - Katılımcıların minimum modeli
   - Kullanıcıdan gizlenen otomatik çekim oturumu
   - Operatörün giriş yapan kullanıcıdan gelmesi
   - Protokolün kullanıcıya “Kayıt Planı” olarak sunulması
   - Eski test verileri için migrasyon yapılmadığı/temiz başlangıç kararı
3. Değiştirilen schema ve uygulama sürümlerini, gerçekten çalıştırılan testleri
   ve sonuçlarını kaydet.
4. Yapılmayan veya doğrulanamayan şeyleri açıkça belirt.
5. Repository kökünde Codex'e özel kalıcı talimat dosyası yoksa kısa bir
   `AGENTS.md` oluştur. Bu dosya `MEMORY.md`'nin önce okunmasını ve görev
   sonunda güncellenmesini Codex için zorunlu kılsın. Mevcut `CLAUDE.md`
   dosyasını silme; iki dosya ortak hafızaya yönlendirsin.

`MEMORY.md` güncellenmeden görev tamamlanmış sayılmaz.

---

## 14. Tamamlanma ölçütü

Görev ancak aşağıdakilerin tümü sağlandığında tamamlanmıştır:

- İlk açılışta tek owner hesabı güvenli biçimde oluşturulabiliyor.
- Sonraki açılışlarda kullanıcı adı ve şifreyle giriş yapılabiliyor.
- Giriş ekranından ad, soyad, unvan, kullanıcı adı ve parolayla normal kullanıcı
  oluşturulabiliyor.
- Parolalar güvenli hash dışında hiçbir yerde saklanmıyor.
- Owner kullanıcıları, şifre sıfırlamayı ve proje atamalarını yönetebiliyor.
- Normal kullanıcı yalnızca kendi veya atanmış projelerini görüyor.
- Protokol kullanıcıya Kayıt Planı olarak ve sade biçimde sunuluyor.
- Katılımcılar sayfasında katılımcı eklenip seçilerek doğrudan kayda
  başlanabiliyor.
- Boy, kilo ve görünür manuel oturum yönetimi kaldırılmış durumda.
- Oturum arka planda doğru kullanıcı/proje/katılımcıyla otomatik yönetiliyor.
- Mevcut Capture, Review, Dataset ve Export ana işlevleri bozulmamış durumda.
- İlgili otomatik testler geçiyor.
- `MEMORY.md` ortak Claude/Codex hafızası olarak güncellenmiş durumda.
- Gerekli Codex talimatı `AGENTS.md` içinde kalıcı hale getirilmiş durumda.

Son raporda değişen dosyaları, kullanıcı akışını, SQLite konumunu ve schema
sürümünü, temizlenen test verilerini, çalıştırılan testleri ve varsa kalan
riskleri kısa ve somut biçimde belirt.
