import re
from urllib.parse import urljoin

from playwright.sync_api import Browser, Page, sync_playwright

from . import config
from .captcha_solver import solve_sum_captcha

OBS_BASE_URL = "https://obs.balikesir.edu.tr"
GRADES_TABLE_SELECTORS = (
    "#grd_not_listesi",
    "table[id*='grd_not_listesi' i]",
    "table[id*='not_listesi' i]",
    'table:has-text("Ders Kodu"):has-text("Ders Adı")',
    'table:has-text("Ders Kodu"):has-text("Sınav Notları")',
)
MODERN_GRADES_MARKER = "Özet Not Durumu"


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
    target_index = None
    for index, link in enumerate(onclicks):
        if link["txt"] == "Not Listesi":
            match = re.search(r"menu_close\(this,'([^']+)'", link["oc"])
            if match:
                target = match.group(1)
                target_index = index
                break
    if target is None:
        raise RuntimeError("Menude 'Not Listesi' linki bulunamadi.")

    # OBS'nin menu_close fonksiyonu iframe adresini ayarlamanin yaninda oturum/
    # sekme kontrolu icin ek isler de yapabiliyor. Bu nedenle src'yi elle
    # degistirmek yerine gercek menu onclick'ini calistiriyoruz. Link gorunmez
    # (collapsed) olsa bile DOM click'i onclick'i tetikler.
    iframe = page.locator("#IFRAME1")
    page.locator("#proMenu a").nth(target_index).evaluate("el => el.click()")

    expected_url = urljoin(OBS_BASE_URL, target)
    frame = page.frame_locator("#IFRAME1")
    table = frame.locator(", ".join(GRADES_TABLE_SELECTORS)).first
    modern_marker = frame.get_by_text(MODERN_GRADES_MARKER, exact=True).first
    try:
        # Eski arayuz tabloyu, yeni arayuz ise kartlari "Ozet Not Durumu"
        # basligi altinda gosteriyor. Ikisinden biri geldiyse sayfa hazirdir.
        table.or_(modern_marker).first.wait_for(state="attached", timeout=30000)
    except Exception as exc:
        child = iframe.element_handle().content_frame()
        actual_url = child.url if child else iframe.get_attribute("src") or "(bos)"
        body_text = ""
        table_ids = ""
        if child:
            try:
                body_text = " ".join(child.locator("body").inner_text(timeout=2000).split())[:300]
            except Exception:
                pass
            try:
                table_ids = ", ".join(
                    child.locator("table").evaluate_all(
                        "els => els.map(el => el.id || '(idsiz)').slice(0, 20)"
                    )
                )
            except Exception:
                pass
        raise RuntimeError(
            "Not listesi yuklenemedi. "
            f"Beklenen adres: {expected_url}; iframe adresi: {actual_url}; "
            f"sayfa mesaji: {body_text or '(okunamadi)'}; "
            f"bulunan tablolar: {table_ids or '(yok)'}"
        ) from exc

    # Belirli bir donem istendiyse sec (postback ile tablo yenilenir).
    # Verilmezse OBS varsayilani = guncel donem.
    if donem:
        frame.locator("#cmbDonemler").select_option(value=donem)
        table.or_(modern_marker).first.wait_for(state="attached", timeout=30000)

    return frame


def _parse_exam_notes(text: str) -> dict[str, str]:
    """'Vize : 95 Final : 87' -> {'Vize': '95', 'Final': '87'}."""
    text = " ".join(text.split())
    return {name: value for name, value in re.findall(r"([^\s:]+)\s*:\s*([^\s:]+)", text)}


def _parse_modern_summary(text: str) -> list[dict[str, str]]:
    """Yeni kart arayuzundeki ders ozet satirlarini ayristirir."""
    # Responsive arayuz ayni kart basligini ekran genisligine gore birden fazla
    # satira bolebiliyor. Once tum bosluklari normalize ederek ara.
    text = " ".join(text.split())
    pattern = re.compile(
        r"(?P<code>[A-ZÇĞİÖŞÜ]{2,}\s*\d+[A-Z]?)\s*\(\d+\)\s*-\s*"
        r"(?P<name>.*?)\s*\|\s*Ort:\s*(?P<average>\S+)\s+"
        r"Not:\s*(?P<grade>\S+)\s+Durumu:\s*"
        r"(?P<status>--|Başarılı|Başarısız|Geçti|Kaldı|Devamsız)",
        re.IGNORECASE,
    )
    return [match.groupdict() for match in pattern.finditer(text)]


def _parse_modern_grades(frame) -> dict[str, dict]:
    """2026 kart tabanli OBS not sayfasini ayristirir."""
    body_text = frame.locator("body").inner_text()
    courses = _parse_modern_summary(body_text)
    if not courses:
        return {}

    # Her ders kartindaki sinav tablosu DOM'da derslerle ayni sirada geliyor.
    exam_tables = frame.locator('table:has-text("Sınav Adı"):has-text("Not")')
    for index, course in enumerate(courses):
        exams: dict[str, str] = {}
        if index < exam_tables.count():
            rows = exam_tables.nth(index).locator("tr")
            if rows.count():
                headers = [
                    " ".join(value.split())
                    for value in rows.first.locator("th, td").all_inner_texts()
                ]
                try:
                    name_col = headers.index("Sınav Adı")
                    grade_col = headers.index("Not")
                except ValueError:
                    name_col = grade_col = -1
                if name_col >= 0:
                    for row_index in range(1, rows.count()):
                        cells = rows.nth(row_index).locator("th, td").all_inner_texts()
                        if max(name_col, grade_col) >= len(cells):
                            continue
                        name = " ".join(cells[name_col].split())
                        value = " ".join(cells[grade_col].split())
                        if name and value and value != "--":
                            exams[name] = value

        code = course["code"]
        grade = course["grade"]
        grades_status = course["status"]
        result = "" if grade == "--" else grade
        courses[index] = {
            "code": code,
            "ad": course["name"],
            "sonuc": result,
            "sinav": exams,
            "ort": "" if course["average"] == "--" else course["average"],
            "harf": result,
            "durum": "" if grades_status == "--" else grades_status,
        }

    return {course.pop("code"): course for course in courses}


def parse_grades(frame) -> dict[str, dict]:
    """Secili donemin not tablosunu ders koduna gore yapisal olarak dondurur.
    Her ders: ad, sinav (bilesen->deger), ortalama, harf, durum, sonuc.
    Bu ayrintili yapi, tek tek sinav notlarindaki degisiklikleri (yeni not,
    degistirilen not, sonuclandirma vb.) tespit etmeye izin verir."""
    grades: dict[str, dict] = {}
    table = frame.locator(", ".join(GRADES_TABLE_SELECTORS)).first
    if table.count() > 0:
        rows = table.locator("tr")
        row_count = rows.count()
        for r in range(1, row_count):  # 0. satir baslik
            cells = rows.nth(r).locator("td")
            if cells.count() < 8:  # Bos/uyumsuz tablo veya yeni kart tablosu
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

    if grades:
        return grades

    # Yeni OBS arayuzunde sayfada baska tablolar eski secicilere eslesebilir.
    # Eski tablo eslesse bile ders cikmadiysa kart tabanli ayristiriciyi dene.
    modern_grades = _parse_modern_grades(frame)
    if modern_grades:
        return modern_grades

    body_text = " ".join(frame.locator("body").inner_text().split())[:500]
    raise RuntimeError(
        "Not sayfasi acildi ancak ders kartlari ayristirilamadi. "
        f"Sayfa metni: {body_text or '(bos)'}"
    )


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
