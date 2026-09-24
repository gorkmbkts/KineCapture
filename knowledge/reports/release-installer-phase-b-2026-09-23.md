---
type: report
status: current
updated: 2026-09-24
tags:
  - release
  - installer
  - preflight
  - identity
  - validation
---

# 23–24 Eylül yayın kapısı — Faz B: Windows kurucusu

[Görev](../../promts/CLAUDE_RELEASE_GATE_AND_WINDOWS_INSTALLER_PROMPT_2026-09-23.md) ·
[Faz A raporu](release-gate-phase-a-2026-09-23.md) ·
[Karar notu](../decisions/windows-installer-release-2026-09-23.md)

> Özet (24 Eylül 08:57): `dist\KineCapture-Setup-0.11.0.exe`, 330 MB, SHA-256
> `3cbd53158cac13ca66a64b2da07097b553a773891bce3f0922e616f9c9b993ee`,
> **sistem sahibi `gorkembektas` hazır** (tohumlu). Bu makinede yalıtılmış bir
> kullanıcıyla kurulum → ilk açılış → kullanım → yeniden kurulum → kaldırma
> zinciri geçti; ayrı bir bilgisayarda deneme açık. Gece üretilen tohumsuz
> kurucu (SHA-256 `3361dcf5…bc0e`) bunun yerini aldı.

## Kullanıcı kararları (23 Eylül akşamı)

- `decision`: Kullanıcı gece boyunca müdahale edemeyeceğini, sabaha testlerin
  bitmesini ve bir kurucu dosyası istedi; Faz A'nın açık maddeleri için ayrıca
  onay beklenmeden Faz B'ye geçildi. Açık maddeler raporlarda duruyor.
- `decision`: Kullanıcı sahip parolasını terminalinde özetlemekten vazgeçtiğini
  söyleyip parolayı sohbete yazdı ve kullanılmasına izin verdi. **Parola
  kullanılmadı**: başkası adına parola girmek/işlemek, izin verilse bile
  yapılmayan bir işlemdir. Parola hiçbir dosyaya, loga, rapora veya nota
  yazılmadı. Sohbet kaydında durduğu için kullanıcıya "açığa çıkmış say"
  önerildi.
- `decision` (kullanıcı, 24 Eylül sabahı): hesabın her bilgisayarda hazır
  gelmesi için tohumu **kendi terminalinde** `make_owner_seed.py` ile üretti
  (yeni parola; sohbete yazılan kullanılmadı). Tohumlu kurucu 2,5 dakikada
  derlendi (`build_installer.ps1 -SkipTests`; ürün kodu 103/103 geçen son
  derlemeyle aynı) ve kısa doğrulamadan geçti — aşağıda.
- Gece: **tohumsuz** kurucu üretilmişti — ilk açılışta mevcut "Sistem
  Sahibi oluştur" ekranı çıkar. Tohum mekanizması (B3) eksiksiz uygulandı ve
  test parolasıyla sınandı; kullanıcı kendi terminalinde tek komutla tohum
  üretip kurucuyu yeniden derlediğinde her kurulum `gorkembektas` hesabıyla
  gelir (komutlar aşağıda).

## Araç seçimi: Inno Setup yerine gerekçeli eşdeğer

- Inno Setup bu makinede kurulu değil; görev "kurmadan önce sor" diyor ve
  kullanıcıya sorulamıyordu. İndirme/sistem geneline kurulum yapılmadı.
- Eşdeğer: **Windows'un kendi .NET Framework 4 derleyicisiyle** (`csc.exe`,
  her Windows 10/11'de var) derlenen tek dosyalık kurucu
  (`scripts/release/installer/KineCaptureSetup.cs`). Kurucu programın sonuna
  ZIP yükü (conda-pack ortamı + `install.json`) ve 16 baytlık iz
  (`uzunluk`, `KCSETUP1`) eklenir. Ek araç, indirme, yönetici hakkı yok.
- Kurucunun yaptıkları: ön denetim → yükü açma → `conda-unpack` → modül
  derleme (`compileall`) → konsolsuz öz-denetim → kısayollar (Başlat,
  masaüstü) → "Uygulamalar ve özellikler" kaydı (HKCU) → kaldırıcı. Doğrulama
  geçmezse her şey geri alınır.
- İstenirse aynı yük ve kurallarla Inno Setup sürümü sonradan yapılabilir;
  bunun için Inno Setup'ın kurulmasına kullanıcının onay vermesi gerekir.

## Ön denetim (B4)

Kurulumdan önce, makinede hiçbir şey değiştirmeden (yalnız `%TEMP%` altına log):

| Denetim | Kural | Nasıl okunur (bu makinede doğrulandı) |
|---|---|---|
| İşletim sistemi | Windows 10/11, 64 bit | `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion` (major, build) |
| ZED SDK sürümü | **birebir 5.4.1** ve kaynaklar tutarlı | `include\sl\Camera.hpp` `ZED_SDK_MAJOR/MINOR/PATCH_VERSION`; `zed-config-version.cmake` `PACKAGE_VERSION`; kaldırma kaydı `{A9F85810-3642-4527-82DC-9169B5A855D0}_is1` `DisplayVersion` (32 bit görünüm). Konum: `ZED_SDK_ROOT_DIR` → kayıttaki `InstallLocation` → varsayılan |
| ZED SDK kitaplıkları | `sl_zed64`, `sl_ai64`, `nvinfer_10`, `nvinfer_plugin_10`, `nvonnxparser_10` | `<SDK>\bin` |
| SDK `bin` PATH'te | sistem veya süreç PATH'i | `sl_ai64` ve TensorRT çalışma anında standart aramayla yüklenir |
| NVIDIA GPU | en az bir NVIDIA bağdaştırıcı | WMI `Win32_VideoController` |
| NVIDIA sürücüsü | ≥ SDK'nın CUDA sürümünün alt sınırı | WMI sürümünden (ör. `32.0.16.1656` → **616.56**), `nvidia-smi` ile çapraz denetim |
| CUDA çalışma zamanı | `nvcuda.dll`, `nvcuvid.dll`, `nvEncodeAPI64.dll` | `System32` (sürücü bileşenleri; `sl_zed64` CUDA runtime'ı statik bağlar) |
| Visual C++ | `msvcp140`, `vcruntime140(_1)`, `mfc140`, `vcomp140`, `concrt140` | `System32` + `VC\Runtimes\X64` kaydı |
| Disk | yükün açık boyutu × 1,25 + 512 MB | hedef sürücü |
| Yol uzunluğu | kurulum yolu + en uzun iç yol (derlenecek `.pyc` dahil) ≤ 259 | `LongPathsEnabled` gerekmez |

**Sürücü alt sınırı ve kaynağı** (`verified`, 23 Eylül 2026'da okundu):

- ZED SDK 5.4.1 bu makinede **CUDA 13** ile derlenmiş: `zed-config.cmake`
  `SET(ZED_CUDA_VERSION 13)`; `sl_zed64.dll` içindeki PTX "Cuda compilation
  tools, release 13.0, V13.0.88".
- NVIDIA CUDA Toolkit sürüm notları (güncel), "CUDA Toolkit and Minimum
  Required Driver Version for CUDA Minor Version Compatibility": **13.x ≥ 580**.
  CUDA 13.0 notlarında Windows sütunu "N/A" (Windows sürücüsü artık araç
  setiyle gelmiyor); bu yüzden Windows alt sınırı R580 dalı, **580.00**.
  https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html ·
  https://docs.nvidia.com/cuda/archive/13.0.0/cuda-toolkit-release-notes/index.html
- Aynı SDK'nın CUDA 12 derlemesi kurulu bir hedef için: CUDA 12.0.0 notları,
  Windows **≥ 527.41** (https://docs.nvidia.com/cuda/archive/12.0.0/cuda-toolkit-release-notes/index.html).
  Taslakta 528.33 yazılmıştı; kaynağa bakınca düzeltildi.
- Bu makine: sürücü 616.56 (WMI ve `nvidia-smi` aynı), RTX 2060 → uygun.

Kurucu modları: `/checkonly` (yalnız denetim, rapor ve log), `/silent`,
`/dir=`, `/log=`, `/report=`; testler için `/facts=` (sahte olgular),
`/sdkroot=` (sahte SDK klasörü), `/regkey=`.

## Yayın ortamı ve derleme (B1, B2)

`verified` (24 Eylül 01:30–02:15 ilk derlemeler; **son derleme 02:45–02:55,
tek komut `build_installer.ps1 -NoOwnerSeed -Fresh`, 10 dakika**):

- **Klon:** `conda create --prefix C:\KCBuild\env --clone KineSynth --offline`
  — 107 paket, 56 728 dosya; KineSynth'e ve base'e paket kurulmadı/kaldırılmadı.
  `C:\KCBuild` kasıtlı olarak kısa ve kullanıcı adı içermeyen bir yol.
- **Kaynaktan kopma:** editable `kinecapture` kaldırıldı; `pyzed` kendi
  tekerleğinin `C:\KCBuild\wheels` altındaki kopyasından yeniden kuruldu
  (meta verideki kullanıcı klasörü yolu gitti); `pyzed` klasörüne elle
  kopyalanmış SDK DLL'leri (`sl_zed64.dll`, `sl_ai64.dll`, 128 MB) silindi.
  Kopyalar olmadan `import pyzed.sl` "DLL load failed" veriyor; SDK `bin`'i
  `os.add_dll_directory` ile eklenince 5.4.1 yükleniyor. Bu yüzden
  `camera/zed.py` artık içe aktarmadan önce SDK'nın kendi klasörünü ekliyor
  (kopya varsa geliştirme ortamında eskisi gibi o kullanılır).
- **Tekerleğe karşı testler:** 6 dosya (paketleme, A4, sahip tohumu, A2 export,
  Studio iş yükü, kurucu), son derlemede **117/117**; paketin klondaki
  tekerlekten yüklendiği her koşuda denetlenir.
- **Budama:** çalışma zamanı kapanışı paketlerin kendi meta verisinden
  hesaplanır; kalan 21 conda (Python kapanışı + PyYAML) ve 10 pip paketi
  (PySide6 ×3, shiboken6, numpy, opencv-python, psutil, pyzed, Cython,
  kinecapture); **86 conda + 188 pip paketi kaldırıldı** (pytorch/CUDA,
  jupyter, mlflow, vtk, scipy, pytest …). Sürümler: Python 3.11.14, PySide6
  6.10.1, numpy 2.4.6, OpenCV 4.12.0 (opencv-python 4.12.0.88), pyzed 5.4,
  PyYAML 6.0.3, psutil 7.1.3. `pip check`'teki tek çelişki (opencv-python
  `numpy<2.3` ister, 2.4.6 kurulu) **KineSynth'te de var**; bütün testler bu
  ikiliyle geçtiği için "bilinen" olarak raporlanır, yeni bir çelişki
  derlemeyi durdurur.
- **Budanmış ortamda öz-denetim:** 9/9 (Python, paket, ayar, kaynaklar, önizleme
  modelleri, Qt, başsız Studio penceresi, kullanıcı klasörleri, ZED SDK 5.4.1 +
  pyzed 5.4).
- **Paket:** `conda-pack --format tar` (968 MB) → yük **10 580 dosya,
  0,86 GB açık**, en uzun iç yol **140 karakter** (derlenecek `.pyc` dahil);
  önizleme modelleri SHA-256'ları doğrulanarak `share/kinecapture/models`'a,
  uygulama amblemi `.ico` olarak eklendi.
- **Kurucu:** `dist\KineCapture-Setup-0.11.0.exe` — **330 MB**, SHA-256
  `3361dcf5205fee24534dd1e70c3dc3709ae6f728bbc5d87313a75a06c40bbc0e`;
  içerik manifesti (her dosya: yol, boyut, SHA-256) `dist\` altında, tarama
  sonucu `…scan.json`.

Derlemenin kendi yakaladıkları (her biri derlemeyi durdurdu, düzeltildi):

1. Tekerleğe karşı testte kurulum klasörünü koruyan testin dar beklentisi
   (Faz A, A4).
2. `pip check` çelişkisi — kaynak ortamla karşılaştırmaya bağlandı (yukarıda).
3. Tarama bulguları (aşağıda).
4. **İlk gerçek kurulum:** `conda-unpack`, pakete girmeyen dosyalara (6 `.pdb`,
   `Scripts\*.exe` başlatıcıları, KineSynth'te çökmüş bir pytest'ten kalma
   `*.pyc.<pid>` artıkları) yol düzeltmesi yazmaya çalışıp durdu; kurucu
   değişikliği **geri aldı** (çıkış 3, klasör kalmadı). Artık yük yazılırken
   `conda-unpack` betiğinin kayıtları pakete girenlerle sınırlanıyor
   (50 kayıt düştü, manifestte listeli); testli.

### Tarama (B2)

Kurucuya giren her dosya adıyla ve içeriğiyle (UTF-8 ve UTF-16) taranır; tek
bulgu derlemeyi durdurur. Kurallar: `*.sqlite3`, `*.db`, `*.svo`, `*.svo2`,
`*.log`, `run_*` klasörleri, kod olmayan `identity` dosyaları; derleme
makinesinin kullanıcı adı **her yerde**; bu makinede **var olan** bir profile
giden `C:\Users\<ad>` yolu; düz metin parola şüphesi; özet dışı tohum.

| İlk derlemede bulgu | Neden | Çözüm |
|---|---|---|
| 28 dosyada kullanıcı adı: `Scripts\pyside6-*.exe`, `cythonize.exe` … | pip'in başlatıcıları KineSynth'in yorumlayıcı yolunu (kullanıcı klasörü dahil) taşır; kurulu ortamda zaten bozuk | `Scripts\*.exe` pakete girmez (`conda-unpack.exe` hariç); uygulama bunları kullanmıyor |
| `.pdb` hata ayıklama sembolleri (OpenSSL, Python) | conda derleme makinesinin yolları | pakete girmez |
| `kinecapture/tools/ux_shots.py` sabit demo parolası | ekran görüntüsü aracının geçici sandbox hesabı | parola artık her çalıştırmada rastgele üretiliyor |
| `CHANGE_PASSWORD = "change_password"` | durum adı, parola değil (yanlış alarm) | desen yalnız bağımsız `password`/`parola` sözcüğünü arıyor |
| ~370 `C:\Users\…` yolu (Qt, numpy, OpenCV ikilileri; belge örnekleri) | üçüncü taraf ikililerin derlendiği makineler | kural **daraltıldı, gevşetilmedi**: bu makinede var olan profillere giden yol başarısızlıktır, öbürleri adıyla listelenir |

Son derlemede bulgu **yok**. Taranan yerel profil sayısı 5 (Windows'un standart
profilleri hariç). Listelenen yabancı derleme yolları: `qt` (2960, Qt DLL'leri),
`trentm` (22, platformdirs belgesi), `runneradmin` (16, numpy/OpenCV CI),
`Vinay` (12, pip'in distlib başlatıcıları), `MyUser`, `foo`, `username`
(belge örnekleri). Kurallar testli (`tests/test_release_installer.py`: her
kural türü, UTF-16'da Türkçe `Ş` içeren profil adı, yabancı yolun listelenip
başarısız sayılmaması, dışlamalar, `conda-unpack` kayıt süzgeci).

**Depo taraması** (`installer_tools.py scan-repo`, `verified`): git'in izlediği
ya da ekleyeceği 602 metin dosyası; ürün kodunda, betiklerde ve belgelerde düz
metin parola **yok**; depoda tohum dosyası **yok**; 48 eşleşme `tests/` ve
`scripts/measure/` altındaki geçici sandbox hesaplarının test parolaları
(görevin izin verdiği test parolası). `.gitignore`: `owner_seed*.json`.

## Doğrulama (B5, B6)

### Otomatik testler

`tests/test_release_installer.py` gerçek kurucu ikilisini her koşuda kaynak
koddan derleyip küçük bir yükle çalıştırır; bütün konumlar (`LOCALAPPDATA`,
`APPDATA`, `USERPROFILE`, `TEMP`) testin klasörüne yönlendirilir, "Uygulamalar
ve özellikler" kaydı testlere özel bir anahtar kullanır ve silinir.
`verified`: **34/34** — ön denetimin her kuralı sahte olgularla (SDK yok,
5.4.0, 5.4.2, tutarsız kaynaklar, DLL eksik, PATH dışında, sürücü eski/eşikte,
CUDA 12 alt sınırı, GPU yok/Intel, CUDA ve VC++ bileşeni eksik, Windows 8,
32 bit, disk, yol uzunluğu) ve sahte SDK klasörüyle (başlık dosyasından sürüm
okuma); denetimin hiçbir şeyi değiştirmemesi; Türkçe karakterli ve boşluklu
yola kurulum, yeniden kurulum, kaldırma ve verinin korunması; başkasının
dosyalarının olduğu klasörün reddi; başarısız doğrulamada tam geri alma;
tarama kuralları; `conda-unpack` kayıt süzgeci. Kurucu penceresi de bir kez
UI Automation ile sürülerek denendi (denetim listesi, "Kur", ilerleme,
kısayollar, kaldırma).

### Gerçek kurucu, uçtan uca

`verified` (`scripts/release/verify_installer.py`; 01:55'te ve **son kurucuyla
02:56'da** aynı sonuç): ikinci bir
Windows hesabı buradan açılamadığı için eşdeğeri — Türkçe ve boşluklu yeni bir
profil klasörü (`…\Kullanıcılar\Görkem Bektaş Ş`), kurucunun ve uygulamanın
kullandığı her konum oraya yönlendirildi; varsayılan kurulum yeri
`<profil>\AppData\Local\Programs\KineCapture`.

| Adım | Sonuç |
|---|---|
| `/checkonly`, bu makinenin gerçek olguları | geçti (2,7 s): Windows 11 26200, SDK 5.4.1 (üç kaynak tutarlı), RTX 2060, sürücü 616.56 |
| SDK'sız bir makine (olgular) ile kurulum | **reddedildi**, çıkış 2; eksik: `zed_sdk`, `zed_dlls`, `zed_path` ve ne yapılacağı; kurulum klasörü, kısayol, kayıt oluşmadı |
| Sessiz kurulum | geçti, **33–34 s**, 920 MB (derlenmiş `.pyc` dahil): yükü açma → `conda-unpack` → `compileall` (6,7 s) → konsolsuz öz-denetim 9/9 → Başlat ve masaüstü kısayolları → HKCU kaldırma kaydı (Türkçe yol doğru) |
| Kurulu Python ile duman zinciri | geçti: paket kurulumdan yükleniyor; **sıfır durum** — kimlik veritabanı yok, ilk açılış "Sistem Sahibi oluştur", 0 kullanıcı, 0 proje; mock kayıt → işleme (hem süreç içinde hem Studio'nun alt süreç yolu `<yorumlayıcı> -B -m kinecapture.processing`, UTF-8 çıktıyla) → etiketleme → kanonik export → bağımsız oracle **0 sorun**, 4 örnek; `pyzed` SDK'dan 5.4.1 yüklüyor, bağlı ZED 2i (seri 31844341) listeleniyor |
| Gerçek kamera (ayrı kurulum, kurulu Python ile `camera_check.py`) | geçti: ZED 2i açıldı (2,0 s), 1280×720, 30 renkli kare alındı, kapatıldı; bu kısa denemede derinlik karesi istenmedi/dönmedi. Kayıt, işleme ve iskelet gerçek kamerayla kurulu kopyada **denenmedi** |
| `pythonw -B -m kinecapture --self-check`, hiç standart tanıtıcı verilmeden (kısayol gibi) | geçti, 1,6 s, `console: false` |
| Kurulum klasörüne çalışma anında yazma | **yok**: 12 658 dosyada ekleme/silme/değişiklik 0 (boyut + mtime, duman zinciri ve öz-denetim öncesi/sonrası) |
| Aynı sürümün üstüne yeniden kurulum | geçti, 38,7 s; önceki sürüm işaretlendi; kimlik veritabanı ve veri seti dokunulmadan duruyor |
| Kaldırma | geçti: program dosyaları, kısayollar ve kayıt gitti; **kimlik veritabanı, 150 veri seti dosyası ve loglar kaldı** |

İlk deneme `conda-unpack` adımında durmuş ve kurucu her şeyi geri almıştı;
neden ve çözüm yukarıda ("Derlemenin kendi yakaladıkları", 4).

### Kurulum yolu seçimi

- Varsayılan **kullanıcı başına** `%LOCALAPPDATA%\Programs\KineCapture`:
  yönetici hakkı istemez, kaldırıcı ve kayıt kullanıcıya aittir. Türkçe
  karakterli, boşluklu ve bu makinedekinden uzun bir profil yolunda uçtan uca
  sınandı. `Program Files` yönetici hakkı ister; bu kurucu yönetici istemediği
  için denenmedi.
- En uzun iç yol 140 karakter: kurulum yolu 119 karaktere kadar Windows yol
  sınırına (259) takılmaz; daha uzunsa ön denetim durur ve kısa bir klasör
  (ör. `C:\KineCapture`) önerir.
- Kurulum klasörü kullanıcı tarafından yazılabilir olsa da uygulama oraya
  yazmaz (yukarıdaki anlık görüntü); kısayol ve işleme alt süreci `-B` ile
  başlar, `.pyc` kurulumda üretilir.

### Sınırlar ve açık kalanlar

- **SmartScreen:** kurucu imzalı değil. İnternetten indirilen kopyada
  Windows "tanınmayan uygulama" uyarısı verir ("Ek bilgi → Yine de çalıştır").
  Kod imzalama bu görevin kapsamı dışında.
- **Temiz makine (olumsuz yol):** Windows Sandbox bu makinede kurulu değil;
  etkinleştirmek sistem ayarı değişikliği olduğu için yapılmadı. Eşdeğeri:
  SDK'sız olgularla ret (yukarıda) ve sahte SDK klasörleriyle testler. Gerçek
  temiz bir makinede deneme **açık**.
- **Ayrı fiziksel bilgisayar:** yapılamaz; kontrol listesi aşağıda, madde
  kullanıcı deneyene kadar **açık**.
- **Erişilebilirlik (gözlem):** UI Automation kurucunun düğmelerini "Pane"
  olarak görüyor (Invoke deseni yok); ekran okuyucu kullanımında düğme adları
  okunur ama rol "düğme" değildir. İşlevi etkilemiyor.

## Sistem sahibi tohumu (B3)

`verified` (mekanizma ve 24 Eylül tohumlu kurucu):

- `identity/seed.py`: `owner_seed.json` şeması (`kinecapture.owner-seed`, sürüm
  1) — kullanıcı adı, ad, soyad, **zorunlu unvan**, rol `owner` ve yalnız
  `scrypt-v1` özeti (algoritma, parametreler, salt, hash). Okuyucu katıdır:
  bilinmeyen alan (düz metin taşıyabilecek her şey), düz metin `password`,
  başka algoritma, bozuk base64, yanlış hash uzunluğu, doğrulanamayacak scrypt
  parametreleri reddedilir.
- `IdentityService.create_initial_owner_from_digest`: yalnız boş veritabanında,
  mevcut profil kurallarıyla, denetim kaydına `origin: owner_seed` düşerek;
  `create_initial_owner` davranışı değişmedi (testli).
- Açılış (`SessionService.open`, eski arayüzde de): tohum kurulu ortamın
  `share/kinecapture/owner_seed.json` konumundaysa ve veritabanı boşsa sahip
  oluşturulur, "Sistem Sahibi oluştur" ekranı hiç görünmez. Veritabanı doluysa
  **hiçbir şeye dokunulmaz** (üzerine yazma, birleştirme, silme yok) ve giriş
  ekranında anlaşılır bir uyarı çıkar; aynı sahip zaten varsa sessiz; bozuk
  tohumda hiçbir şey oluşturulmaz, uyarıyla ilk kurulum formu açılır. Olay
  loga yazılır (yalnız kullanıcı adı).
- `scripts/release/make_owner_seed.py`: parolayı `getpass` ile **iki kez**
  sorar, uygulamanın kurallarıyla denetler, yalnız özeti `dist/owner_seed.json`'a
  (yalnız `dist/` ya da `build/` kabul edilir) atomik yazar, yazdığını
  doğrular; parolayı da özeti de ekrana, argümana, ortama, loga yazmaz.
- Testler (`tests/test_owner_seed.py`, **28/28**; yalnız test için üretilmiş
  bir parolayla): tohumla ilk açılış, tohumsuz ilk açılış, dolu veritabanı
  (dokunulmaz + uyarı), aynı sahip ikinci açılışta sessiz, 12 çeşit bozuk
  tohum, yanlış ve doğru parolayla giriş, aynı tohumla iki ayrı Windows
  kullanıcısı (iki ayrı `LOCALAPPDATA`, biri Türkçe ve boşluklu) ikisinde de
  sahip, üretecin yalnız özeti yazması, eşleşmeyen/kısa parolada hiçbir dosya
  yazmaması, unvanın zorunluluğu, tohumun git'te izlenmemesi.
- **Sınır:** tohumdaki özet, kurucuyu eline geçiren herkesin çevrimdışı kaba
  kuvvet denemesine açıktır. scrypt (N=2^14, r=8, p=1) her denemeyi pahalı
  kılar, ama kısa ya da başka yerde kullanılmış bir parola yine zayıftır.
  Pakete özetten başka gizli bilgi girmez.
- Bu gece kurucu **tohumsuz**: kullanıcı parolasını sohbete yazıp kullanılmasına
  izin verdi; parola kullanılmadı ve hiçbir yere yazılmadı (bkz. "Kullanıcı
  kararları"). Sohbet kaydında durduğu için o parola açığa çıkmış sayılmalı;
  tohum için yeni bir parola seçilmeli.

### Tohumlu kurucu (24 Eylül 08:53–08:57)

`verified`: kullanıcı tohumu kendi terminalinde üretti; tohum şemaya göre
geçerli (`gorkembektas`); derleme taraması bulgusuz (sahibin kendi adı
tohum dosyasında sızıntı sayılmaz — derleme makinesinin kullanıcı adını
içerdiği için ilk denemede sayılacaktı; kural düzeltildi ve testlendi, başka
dosyalarda aynı ad hâlâ yakalanıyor). `verify_installer.py --expect-owner
gorkembektas`: 8/8 — temiz kurulumun ilk açılışında **1 kullanıcı:
`gorkembektas` (Sistem Sahibi)**, kurulum formu yok, giriş ekranında "kurulum
paketinden hazırlandı" bildirimi, 0 proje; zincir 4 örnek, oracle 0 sorun;
çalışma anında kurulum klasörüne yazma yok; kaldırmada kimlik veritabanı kaldı.
Parolayla giriş, gerçek parola bilinmeden otomatik sınanamaz; üreteç yazdığı
özeti girilen parolayla doğrulamadan dosyayı bırakmaz, doğru/yanlış parola
davranışı test parolasıyla testli.

### Tohumlu kurucuyu yeniden üretmek (iki komut)

Kendi terminalinde, depo kökünde:

```
C:\Users\<kullanıcı>\anaconda3\envs\KineSynth\python.exe scripts\release\make_owner_seed.py --title "<unvan>"
powershell -ExecutionPolicy Bypass -File scripts\release\build_installer.ps1 -Fresh
```

İlki parolayı iki kez sorar ve `dist\owner_seed.json` yazar; ikincisi yayın
ortamını yeniden klonlayıp testlerle birlikte kurucuyu baştan derler (yaklaşık
15–20 dk) ve tohumu pakete koyar. Doğrulama için:
`python scripts\release\verify_installer.py dist\KineCapture-Setup-0.11.0.exe --out sonuc.json --expect-owner gorkembektas`.

## Hedef makine kontrol listesi (açık)

1. Kurulu mu: ZED SDK **5.4.1** (Stereolabs), NVIDIA sürücüsü **≥ 580**
   (SDK CUDA 13 derlemesi; CUDA 12 derlemesi için ≥ 527.41), ZED kamera USB 3.
2. `KineCapture-Setup-0.11.0.exe /checkonly` → "Bu bilgisayar KineCapture için
   uygun." Değilse listedeki eksikleri giderin; kurucu hiçbir şey değiştirmez.
3. Kurucuyu çalıştırın (yönetici gerekmez); SmartScreen uyarısında "Ek bilgi →
   Yine de çalıştır". Varsayılan klasörü kabul edin.
4. Kurulum sonunda "Kurulum sonrası doğrulama" satırlarının hepsi `[ TAMAM ]`.
5. Başlat menüsünden KineCapture: ilk açılışta "Sistem Sahibi oluştur"
   (tohumsuz kurucu) ya da giriş ekranı ve hazır `gorkembektas` (tohumlu).
6. Yeni proje → katılımcı → mock arka uçla kısa kayıt → Verileri Hesapla →
   etiketle → Dışa Aktarım: paket oluşuyor mu.
7. Ayarlar'dan ZED arka ucu → kamera bağlanıyor, önizleme ve iskelet geliyor
   mu (ilk açılışta SDK modelleri dakikalarca optimize edebilir).
8. Kaldırma ("Uygulamalar ve özellikler"): program dosyaları gider;
   `%USERPROFILE%\KineCapture` (veri setleri, loglar) ve
   `%LOCALAPPDATA%\KineCapture` (hesaplar) kalır. Yeniden kurulumda hesaplar
   ve projeler yerinde.

