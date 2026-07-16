import json

from . import config


def state_file_exists() -> bool:
    return config.GRADES_STATE_FILE.exists()


def load_previous_grades() -> dict[str, dict]:
    if not config.GRADES_STATE_FILE.exists():
        return {}
    return json.loads(config.GRADES_STATE_FILE.read_text(encoding="utf-8"))


def save_grades(grades: dict[str, dict]) -> None:
    config.GRADES_STATE_FILE.write_text(
        json.dumps(grades, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _course_changes(old: dict | None, cur: dict) -> list[str]:
    """Tek bir ders icin, insan-okunur degisiklik satirlari uretir."""
    changes: list[str] = []

    if old is None:
        # Yeni gorulen ders. Varsa mevcut notlarini da ozetle.
        parts = []
        for exam, val in cur.get("sinav", {}).items():
            parts.append(f"{exam}: {val}")
        if cur.get("harf"):
            parts.append(f"harf: {cur['harf']}")
        detail = (" (" + ", ".join(parts) + ")") if parts else ""
        changes.append(f"yeni ders eklendi{detail}")
        return changes

    old_exams = old.get("sinav", {})
    new_exams = cur.get("sinav", {})
    for exam, val in new_exams.items():
        if exam not in old_exams:
            changes.append(f"{exam} notu girildi: {val}")
        elif old_exams[exam] != val:
            changes.append(f"{exam} notu değiştirildi: {old_exams[exam]} → {val}")
    for exam, val in old_exams.items():
        if exam not in new_exams:
            changes.append(f"{exam} notu silindi (önceki: {val})")

    old_ort, new_ort = old.get("ort", ""), cur.get("ort", "")
    if old_ort != new_ort and new_ort:
        if not old_ort:
            changes.append(f"ortalama girildi: {new_ort}")
        else:
            changes.append(f"ortalama değişti: {old_ort} → {new_ort}")

    old_harf, new_harf = old.get("harf", ""), cur.get("harf", "")
    if old_harf != new_harf and new_harf:
        if not old_harf:
            changes.append(f"harf notu girildi: {new_harf}")
        else:
            changes.append(f"harf notu değişti: {old_harf} → {new_harf}")

    old_sonuc, new_sonuc = old.get("sonuc", ""), cur.get("sonuc", "")
    if old_sonuc != new_sonuc and new_sonuc:
        changes.append(f"sonuç durumu: {new_sonuc}")

    old_durum, new_durum = old.get("durum", ""), cur.get("durum", "")
    if old_durum != new_durum and new_durum:
        changes.append(f"durum: {new_durum}")

    return changes


def diff_grades(
    old: dict[str, dict], new: dict[str, dict]
) -> list[tuple[str, list[str]]]:
    """(ders_adi, [degisiklik satirlari]) listesi dondurur. Bos ise degisiklik
    yok demektir."""
    result: list[tuple[str, list[str]]] = []

    for code, cur in new.items():
        changes = _course_changes(old.get(code), cur)
        if changes:
            result.append((cur.get("ad", code), changes))

    for code, prev in old.items():
        if code not in new:
            result.append((prev.get("ad", code), ["ders listeden kaldırıldı"]))

    return result
