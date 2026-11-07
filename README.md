# OBS Not Bildirim Botu

Balıkesir Üniversitesi OBS'de herhangi bir not güncellendiğinde Telegram'a bildirim atar.

Not güncellemeleri:
- yeni ders eklenmesi
- vize final bütünleme ödev notlarının girilmesi
- vize final bütünleme ödev notlarının değiştirilmesi
- final ve bütünlemenin(öğrenci girdiyse) sonuçlandırılması
- harf notlarının ilanı


## Kurulum

1. Bağımlılıklar:
   ```
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Windows'ta Tesseract OCR kur (captcha okumak için):
   https://github.com/UB-Mannheim/tesseract/wiki adresinden `.exe` indir, kur.
   Kurulum sonrası `pytesseract.pytesseract.tesseract_cmd` gerekirse
   `src/captcha_solver.py` içine kurulum yolunu ekle
   (örn. `C:\Program Files\Tesseract-OCR\tesseract.exe`).
3. Telegram bot oluştur:
   - Telegram'da `@BotFather`'a yaz, `/newbot` komutuyla bot oluştur, token'ı al.
   - Bota bir mesaj at, sonra `https://api.telegram.org/bot<TOKEN>/getUpdates`
     adresinden kendi `chat_id`'ni öğren.
4. `.env.example` dosyasını `.env` olarak kopyala, kendi bilgilerini gir.

## Çalıştırma (yerel)

- Tek seferlik kontrol (test için): `python -m src.main --once`
- Sürekli döngü (varsayılan 30 dk aralıkla): `python -m src.main`

## Ücretsiz 7/24 (GitHub Actions)

Bilgisayarını açık tutmadan bulutta çalıştırmak için `.github/workflows/check.yml`
hazır. Her ~30 dakikada bir çalışır, notları kontrol eder, değişiklik varsa
Telegram'a atar. Kurulum:

1. **Repoyu GitHub'a PRIVATE (özel) olarak yükle.** Durum dosyası
   (`data/last_grades.json`, notlarını içerir) koşular arası saklanabilmek için
   repoya geri yazılıyor; bu yüzden repo **kesinlikle private olmalı**.
2. GitHub'da repo > **Settings > Secrets and variables > Actions > Secrets**
   altına şu 4 gizli değeri ekle:
   - `OBS_STUDENT_NO`
   - `OBS_PASSWORD`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. (İsteğe bağlı) Aynı yerdeki **Variables** sekmesine `OBS_DONEM` ekleyebilirsin
   (boş bırakılırsa OBS'nin seçili güncel dönemi izlenir). Örneğin
   `20261`, 2026-2027 Güz dönemidir. Yanlış veya eski bir dönem kodu girilirse
   o dönemin dersleri izlenir; yeni dönem dersleri görünmez.
4. **Actions** sekmesinde workflow'ları etkinleştir. İstersen "OBS Not Kontrol"
   workflow'unu **Run workflow** ile elle tetikleyip test et.

Notlar:
- Gizli bilgiler (öğrenci no, şifre, token) yalnızca GitHub Secrets'ta durur,
  koda/loga yazılmaz.
- GitHub zamanlanmış işleri yoğunlukta birkaç dakika–yarım saat geciktirebilir;
  bu bir not botu için sorun değil.
- Uzun süre (60+ gün) repoda hiç aktivite olmazsa GitHub schedule'ı durdurabilir;
  bot her koşuda durum dosyasını commit'lediği için repo aktif kalır.
- Workflow, sabit `ubuntu-24.04` ortamında ve Node.js 24 uyumlu resmi GitHub
  Actions sürümleriyle çalışır.

## Nasıl çalışıyor

- Giriş: `oibs/std/login.aspx`. Şifre alanı `readonly` (onfocus ile açılıyor),
  captcha ise "A + B = ?" toplama sorusu; Tesseract ile birkaç eşik/ölçek
  denenip çoğunluk oyuyla çözülüyor. Captcha gürültülü olduğu için tek deneme
  her zaman tutmayabilir; her denemede taze captcha çekildiğinden `--once` bir
  girişte 15 denemeye kadar tekrar eder (giriş ~30-60 sn sürebilir).
- Not sayfası: sol menü "collapsed" olduğu için "Not Listesi" bağlantısının
  oturuma özel `gkm` adresi, OBS'nin kendi menü olayı çalıştırılarak `IFRAME1`
  içine yüklenir. Adresi yeni sekmede doğrudan açmak oturum korumasına
  takılabilir.
- Bot hem eski `#grd_not_listesi` tablo arayüzünü hem de yeni "Özet Not Durumu"
  kart arayüzünü destekler. Yeni görünümde `BIL4101(2)` gibi ders başlıkları ve
  kimliksiz sınav tabloları okunarak Vize/Final/Bütünleme, ortalama, harf notu
  ve geçti/kaldı bilgileri takip edilir.
- Varsayılan olarak **güncel dönem** izlenir. Belirli bir dönemi izlemek için
  `.env` içinde `OBS_DONEM` doldur (örn. `20261` = 2026-2027 Güz,
  `20252` = 2025-2026 Bahar).
- OBS sayfası açıldığı halde hiçbir ders ayrıştırılamazsa bot boş sonucu yeni
  durum olarak kaydetmez. Böylece geçici OBS veya arayüz hatalarında bütün
  dersler yanlışlıkla "listeden kaldırıldı" bildirimi üretmez; Telegram'a hata
  mesajı gönderilir ve önceki durum korunur.

Eski tablo ve yeni kart ayrıştırması gerçek OBS verisiyle test edilmiştir. OBS
arayüzü ileride tekrar değişirse hata mesajındaki sayfa metni teşhis amacıyla
kullanılabilir ve `src/obs_client.py` içindeki seçicilerin güncellenmesi
gerekebilir.

## Sorun giderme

- Yeni dönem dersleri görünmüyorsa GitHub'daki **Actions Variables** bölümünde
  `OBS_DONEM` değerinin eski bir döneme sabitlenmediğini kontrol et. Güncel
  dönemi otomatik izlemek için değişkeni sil veya boş bırak.
- `OBS'den hic ders okunamadi` hatasında önce OBS'ye tarayıcıdan girip güncel
  dönemde derslerin göründüğünü doğrula. Bot bu durumda mevcut
  `data/last_grades.json` dosyasını değiştirmez.
- GitHub Actions üzerinden uçtan uca kontrol için **Run workflow** ekranında
  `test` seçeneğini aç. Test modu giriş, not okuma ve Telegram gönderimini
  doğrular; kayıtlı not durumunu değiştirmez.
