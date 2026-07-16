import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

OBS_LOGIN_URL = "https://obs.balikesir.edu.tr/oibs/std/login.aspx"

OBS_STUDENT_NO = os.environ["OBS_STUDENT_NO"]
OBS_PASSWORD = os.environ["OBS_PASSWORD"]

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))
# Bos birakilirsa OBS varsayilani (guncel donem) izlenir. Belirli bir donemi
# izlemek icin donem kodu girilebilir (orn. 20261 = 2026-2027 Guz).
OBS_DONEM = os.environ.get("OBS_DONEM", "").strip() or None
MAX_CAPTCHA_RETRY = int(os.environ.get("MAX_CAPTCHA_RETRY", "15"))

GRADES_STATE_FILE = DATA_DIR / "last_grades.json"
