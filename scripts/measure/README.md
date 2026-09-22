# Ölçüm ve kabul betikleri

21 Eylül kayıt/takip/GUI onarımının kanıtını üreten betikler. Scratchpad geçici
olduğu için buraya taşındılar; **repo kökünden** çalıştırılırlar.

Yorumlayıcı: `C:\Users\gorke\anaconda3\envs\KineSynth\python.exe`.

| betik | ne yapar |
|---|---|
| `run_suite.py` | Bütün testi **dosya dosya** koşar (tek süreçte koşmak proje kuralına aykırı). `python scripts/measure/run_suite.py suite.json`; tam çıktılar `suite_logs/` altına yazılır, bir dosya başarısızsa betik sıfırdan farklı kodla çıkar. |
| `evidence.py` | Gerçek tam ekran pencerede bütün kabul ölçümlerini alır ve ekran görüntüsü yazar. `python scripts/measure/evidence.py <çıktı-klasörü>` |
| `real_window.py` | Yukarıdakinin yardımcıları: sandbox'lı tam ekran pencere, gerçek sürüm açma. Tek başına çalıştırılmaz. |
| `diag_lock.py` | Gerçek SVO'yu gerçek `SubjectLock` ile yeniden oynatır; her karede durum, sebep ve benzerlik skorlarını JSONL'e yazar. |
| `diag_subject.py` | Aynı SVO'yu oynatıp her karedeki bedenleri (kimlik, durum, kök konum, boy) döker. |
| `reprocess.py` | Gerçek GUI TEST take'ini aynı ham kayıttan **yeni bir sürüme** işler. Mevcut sürümü değiştirmez. |
| `user_state_before.json` | Kullanıcının tercih/pencere/kimlik dosyalarının koşulardan **önceki** hash'leri. Sonrasında karşılaştırmak için. |

Hepsi kullanıcı verisini yalnız okur. Uygulamanın kendi durumu
`AppConfig.sandboxed(...)` ile ayrılır; gerçek `~/.kinecapture` dosyalarına
yazılmaz.

`evidence.py` her koşuda yeni geçici sandbox açar. Kayıt düzenini **mock
kamera ve sentetik kişi seçim kutusuyla** ölçer; eksik eklemler NaN kalır.
Kişi seçimi, kayıt durumu ve gerçekten yazılan kareler doğrulanmadan kayıt
ölçümü üretmez. Bu, canlı kamera veya CPU kişi tespiti kanıtı değildir.
Yerleşim için `QT_QPA_PLATFORM=windows`; `%100`/`%150` için sırasıyla
`QT_SCALE_FACTOR=1`/`1.5` kullanılır. Regresyon süpürmesi `offscreen` koşar;
onun piksel ölçüleri görsel kabul yerine geçmez.

Bağlam: [Codex'e devir](../../knowledge/plans/capture-tracking-gui-repair-handoff-codex.md)
