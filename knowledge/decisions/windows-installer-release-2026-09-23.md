---
type: decision
status: decision
updated: 2026-09-24
tags:
  - release
  - installer
  - export
  - identity
---

# 23 Eylül — yayın kapısı ve temiz Windows kurucusu

## Kararlar (kullanıcı, 23 Eylül 2026)

- `decision`: Paketlemeden önce bir **yayın kapısı** uygulanır: dataset export
  doğruluğu, ölçek/dayanıklılık testleri ve paketlenebilirlik denetimi. Kapı
  geçmeden kurucu üretilmez.
- `decision`: Dağıtım yöntemi: çalışan `KineSynth` ortamının klonu `conda-pack`
  ile taşınır ve tek bir Windows kurucusu (Inno Setup önerildi) ile kurulur.
  PyInstaller ile dondurma şimdilik ertelendi; WinUI geçişi paketlemeyi zaten
  değiştirecek.
- `decision`: Kurucu ZED SDK ve NVIDIA yazılımlarını **içermez**; ilk adımda
  denetler. ZED SDK **birebir 5.4.1**; NVIDIA sürücüsü SDK'nın CUDA sürümünün
  gerektirdiği **minimumun üstünde** (birebir eşleşme gerekmez). Uygun değilse
  hiçbir değişiklik yapmadan durur.
- `decision`: Stres eşikleri: **≥ 30.000 etiketli örnek/segment**, **≥ 30.000
  kayıt/run**, **≥ 100 sınıf**. Layout testleri kapsam dışı.
- `decision`: Kurucu **sıfır veriyle** gelir. Mevcut admin hesabı yalnız
  kurulum paketinden çıkarılır; bu bilgisayardaki kimlik veritabanına
  dokunulmaz.
- `decision`: Her kurulumda sistem sahibi `gorkembektas` hesabı bulunur.
  Pakete **yalnız scrypt-v1 özeti** girer; şifre build sırasında kullanıcının
  kendi terminalinde `getpass` ile alınır. Şifre ve özet repoya, wiki'ye,
  prompt'a veya loglara yazılmaz.

## Gerekçe ve sınırlar

- Repo GitHub'a push edildiği ve `knowledge/` ile `promts/` git'e dahil
  olduğu için düz metin şifre wiki'ye yazılsaydı git geçmişine girerdi;
  kurulumdan sonra silmek bunu geri almazdı.
- Pakete giren özet, kurulum dosyasını alan biri için çevrimdışı kaba kuvvet
  hedefidir; güçlü şifre gerektirir.
- `superseded`: `core/config.py` içindeki depo-göreli varsayılan yapılandırma
  yolu wheel kurulumunda gerçekten kırılıyordu (sessizce varsayılanlara
  düşüyordu); A4'te paket verisine taşındı ve testlendi.

## Uygulamadaki sapmalar ve sonraki kararlar (23–24 Eylül gecesi)

- `decision` (kullanıcı, 23 Eylül akşamı): Sabaha kadar müdahalesiz test ve
  kurucu istendi; Faz A'nın açık maddeleri için ayrı onay beklenmeden Faz B'ye
  geçildi. Açık maddeler raporlarda.
- `decision`: Kullanıcı parolayı sohbete yazıp kullanılmasına izin verdi;
  **kullanılmadı** (başkası adına parola işlemek izinle de yapılmaz) ve hiçbir
  yere yazılmadı. Kurucu bu gece **tohumsuz** üretildi: ilk açılışta mevcut
  "Sistem Sahibi oluştur" ekranı. Tohum mekanizması tamam ve test parolasıyla
  sınandı; kullanıcı `make_owner_seed.py`'yi kendi terminalinde çalıştırıp
  `build_installer.ps1` ile yeniden derlediğinde her kurulum `gorkembektas`
  ile gelir.
- `decision`: Inno Setup kurulu değildi ve kurulum izni alınamıyordu;
  **gerekçeli eşdeğer**: Windows'un kendi .NET Framework derleyicisiyle
  derlenen tek dosyalık kurucu (`scripts/release/installer/`). İndirme ve
  sistem geneline kurulum yok. Inno Setup'a geçiş kullanıcı onayıyla
  sonradan yapılabilir.
- `decision`: Kurulum kullanıcı başına, yönetici hakkı istemeden:
  varsayılan `%LOCALAPPDATA%\Programs\KineCapture`. Yayın ortamı KineSynth
  klonunun çalışma zamanı kapanışına budanmış hâlidir (pytorch/CUDA, jupyter,
  mlflow vb. yok); ZED SDK ikilileri pakete girmez, SDK'nın kendi klasöründen
  yüklenir.

## Durum

- Ayrıntı ve kanıt: [Faz A raporu](../reports/release-gate-phase-a-2026-09-23.md) ·
  [Faz B raporu](../reports/release-installer-phase-b-2026-09-23.md).
- `verified` (24 Eylül sabahı): kullanıcı tohumu kendi terminalinde üretti;
  kurucu artık `gorkembektas` sistem sahibiyle geliyor ve doğrulandı.
- `open`: Ayrı bir fiziksel bilgisayarda deneme (hedef makine kontrol listesi
  Faz B raporunda).
