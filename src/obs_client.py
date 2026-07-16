import re

from playwright.sync_api import Browser, Page, sync_playwright

from . import config
from .captcha_solver import solve_sum_captcha

OBS_BASE_URL = "https://obs.balikesir.edu.tr"


def _try_login_once(page: Page) -> bool:
    """Tek bir giris denemesi. Basarili olursa (IFRAME1 goruldu) True doner."""
    page.goto(config.OBS_LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_selector("#txtParamT01", timeout=15000)
    page.fill("#txtParamT01", config.OBS_STUDENT_NO)
    # Sifre alani readonly; onfocus ile duzenlenebilir hale geliyor.
    page.eval_on_selector("#txtParamT02", "el => el.removeAttribute('readonly')")
    page.fill("#txtParamT02", config.OBS_PASSWORD)

    # Captcha resmi tam yuklenmeden ekran goruntusu alinirsa bos cikar.
    page.wait_for_function(
        "() => { const i = document.getElementById('imgCaptchaImg');"
        " return i && i.complete && i.naturalWidth > 10; }",
        timeout=10000,
    )
    png_bytes = page.locator("#imgCaptchaImg").screenshot()
    answer = solve_sum_captcha(png_bytes)
    if answer is None:
        return False

    page.fill("#txtSecCode", answer)
    page.click("#btnLogin")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    if page.locator("#IFRAME1").count() > 0:
        return True

    error_locator = page.locator("#lblSonuclar")
    error = error_locator.inner_text() if error_locator.count() else ""
    if error and "kod" not in error.lower():
        raise RuntimeError(f"OBS giris hatasi: {error}")
    return False


def login(browser: Browser) -> Page:
    """Basarili girisin oldugu Page'i doner. Her denemede taze bir sayfa
    kullanir; boylece renderer cokmesine ve bellek birikimine dayaniklidir."""
    for _ in range(config.MAX_CAPTCHA_RETRY):
        page = browser.new_page()
        try:
            if _try_login_once(page):
                return page
        except Exception:
            pass
        page.close()

    raise RuntimeError("Giris yapilamadi (captcha/deneme sayisi asildi).")


def open_grades_page(page: Page, donem: str | None = None):
    # Sol menu "collapsed" oldugu icin link tiklanabilir degil; onun yerine
    # (tam olarak) "Not Listesi" linkinin onclick'indeki oturuma ozel gkm
    # URL'sini cikariyoruz. "Haz. Not Listesi" (hazirlik) ile karistirmamak
    # icin tam eslesme sart.
    onclicks = page.eval_on_selector_all(
        "#proMenu a",
        "els => els.map(e => ({txt:(e.innerText||'').trim(),"
        " oc:e.getAttribute('onclick')||''}))",
    )
    target = None
    for link in onclicks:
        if link["txt"] == "Not Listesi":
            match = re.search(r"menu_close\(this,'([^']+)'", link["oc"])
            if match:
                target = match.group(1)
                break
    if target is None:
        raise RuntimeError("Menude 'Not Listesi' linki bulunamadi.")

    # URL'i dogrudan acmak oturum korumasina (UniqueTabCheck) takilip login'e
    # geri atiyor; menunun yaptigi gibi IFRAME1 icine yukluyoruz.
    page.evaluate(
        "url => { document.getElementById('IFRAME1').src = url; }",
        OBS_BASE_URL + target,
    )
    frame = page.frame_locator("#IFRAME1")
    # Not tablosu (bos donemde 'Kayitli Ders Bulunamadi' tek hucre olabilir).
    frame.locator("#grd_not_listesi").wait_for(state="attached", timeout=20000)
    page.wait_for_timeout(1500)

    # Belirli bir donem istendiyse sec (postback ile tablo yenilenir).
    # Verilmezse OBS varsayilani = guncel donem.
    if donem:
        frame.locator("#cmbDonemler").select_option(value=donem)
        page.wait_for_timeout(3000)

    return frame


def _parse_exam_notes(text: str) -> dict[str, str]:
    """'Vize : 95 Final : 87' -> {'Vize': '95', 'Final': '87'}."""
    text = " ".join(text.split())
    return {name: value for name, value in re.findall(r"([^\s:]+)\s*:\s*([^\s:]+)", text)}


def parse_grades(frame) -> dict[str, dict]:
    """Secili donemin not tablosunu ders koduna gore yapisal olarak dondurur.
    Her ders: ad, sinav (bilesen->deger), ortalama, harf, durum, sonuc.
    Bu ayrintili yapi, tek tek sinav notlarindaki degisiklikleri (yeni not,
    degistirilen not, sonuclandirma vb.) tespit etmeye izin verir."""
    grades: dict[str, dict] = {}
    table = frame.locator("#grd_not_listesi")
    if table.count() == 0:
        return grades

    rows = table.locator("tr")
    row_count = rows.count()
    for r in range(1, row_count):  # 0. satir baslik
        cells = rows.nth(r).locator("td")
        if cells.count() < 8:  # 'Kayitli Ders Bulunamadi' gibi tek hucreli satir
            continue
        code = cells.nth(1).inner_text().strip()
        if not code:
            continue
        grades[code] = {
            "ad": cells.nth(2).inner_text().strip(),
            "sonuc": cells.nth(3).inner_text().strip(),
            "sinav": _parse_exam_notes(cells.nth(4).inner_text()),
            "ort": cells.nth(5).inner_text().strip(),
            "harf": cells.nth(6).inner_text().strip(),
            "durum": cells.nth(7).inner_text().strip(),
        }

    return grades


def fetch_current_grades() -> dict[str, str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"]
        )
        try:
            page = login(browser)
            frame = open_grades_page(page, donem=config.OBS_DONEM)
            grades = parse_grades(frame)
        finally:
            browser.close()
    return grades
