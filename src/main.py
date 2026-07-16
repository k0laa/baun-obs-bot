import sys
import time
import traceback

from . import config, state
from .notifier import send_telegram_message
from .obs_client import fetch_current_grades


def _format_message(changes: list[tuple[str, list[str]]]) -> str:
    lines = ["📢 OBS not güncellemesi", ""]
    for course, items in changes:
        lines.append(f"📚 {course}")
        for item in items:
            lines.append(f"  • {item}")
        lines.append("")
    return "\n".join(lines).strip()


def run_test() -> None:
    """Zinciri dogrular: giris + not okuma + Telegram. Durumu degistirmez."""
    grades = fetch_current_grades()
    donem = config.OBS_DONEM or "guncel donem"
    if grades:
        ders_listesi = "\n".join(f"  • {g['ad']}" for g in grades.values())
        body = f"{len(grades)} ders bulundu ({donem}):\n{ders_listesi}"
    else:
        body = f"{donem} icin kayitli ders/not gorunmuyor (dönem henüz boş olabilir)."
    message = f"✅ OBS bot testi: calisiyor.\n{body}"
    send_telegram_message(message)
    print(message)


def check_once() -> None:
    new_grades = fetch_current_grades()

    # Ilk calistirma (kayit yok): mevcut durumu referans al, bildirim gonderme.
    if not state.state_file_exists():
        state.save_grades(new_grades)
        print(f"Ilk calistirma: {len(new_grades)} ders referans olarak kaydedildi.")
        return

    old_grades = state.load_previous_grades()
    changes = state.diff_grades(old_grades, new_grades)

    if changes:
        message = _format_message(changes)
        send_telegram_message(message)
        print(message)
    else:
        print("Degisiklik yok.")

    state.save_grades(new_grades)


def main() -> None:
    if "--test" in sys.argv:
        run_test()
        return

    run_once = "--once" in sys.argv

    while True:
        try:
            check_once()
        except Exception as exc:
            print(f"Hata: {exc}")
            traceback.print_exc()
            try:
                send_telegram_message(f"⚠️ OBS bot hatası: {exc}")
            except Exception:
                pass

        if run_once:
            break
        time.sleep(config.CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
