---
type: decision
status: decision
updated: 2026-09-23
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
- `core/config.py` içindeki depo-göreli varsayılan yapılandırma yolu editable
  olmayan kurulumda kırılabilir (kodda okundu, test edilmedi).

## Durum

- `open`: Hiçbir madde uygulanmadı veya test edilmedi.
  [Görev promptu](../../promts/CLAUDE_RELEASE_GATE_AND_WINDOWS_INSTALLER_PROMPT_2026-09-23.md).
