# Ölçüm ve kabul betikleri

21 Eylül kayıt/takip/GUI onarımının ve 23 Eylül yayın kapısının kanıtını üreten betikler. Scratchpad geçici
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
| `real_export_check.py` | **Yayın kapısı A2.** Gerçek işlenmiş sürümlerin **kopyasını** geçici klasöre alır, kanonik paketi kopyadan üretir ve `tests/release_oracle.py` ile doğrular. Orijinal dosyaların hash'i önce/sonra karşılaştırılır; kopya sonunda silinir (`--keep` yoksa). |
| `scale_dataset.py` | **Yayın kapısı A3.** Sabit tohumla, yalnız geçici klasöre, `ReviewDataset`'in açıp `build_release`'in export ettiği hafif sentetik proje üretir (`--runs`, `--segments`, `--classes`, `--awaiting`). Gerçek konuma yazmayı reddeder. |
| `scale_backend.py` | A3 arka uç ölçümü: her senaryo ayrı süreçte; indeks (ilk okuma / yeniden tarama / önbellek), Veri Seti satırları, özet, `ReviewDataset` açılışı, export ve ölçekte oracle — süre, tepe RSS, sayım denetimi, log-log eğim. |
| `scale_gui.py` | A3 GUI ölçümü: gerçek `StudioWindow` (sandbox tercih/kimlik), 5 ms zamanlayıcıyla GUI thread gecikmesi, >250 ms takılmaların yığın örneği, ekran dolma süresi, bellek, tekrarlı gezinmede widget/RSS büyümesi. `--profile` faz başına cProfile. |

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
