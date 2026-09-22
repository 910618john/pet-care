"""
到期提醒判斷邏輯(純函式, 不碰資料庫/推播, 方便測試)。

「到期」判斷用「還剩幾天」而非「今天剛好是到期日」, 因為背景排程是每天跑一次(GitHub Actions cron),
如果只比對「今天=到期日」, 一旦當天排程沒觸發成功(GitHub Actions偶爾delay或失敗), 這個提醒就永久錯過了。
改成「到期日前N天內都算到期範圍」, 只要在範圍內還沒推播過(notified_keys)就會推, 排程晚一兩天跑也不會漏。
"""
from datetime import date, datetime


def _parse_date(d):
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def _reminder_key(kind, record_id, due_date):
    return f"{kind}:{record_id}:{due_date}"


def collect_due_reminders(pets, vaccine_records, deworming_records, custom_reminders, today, notified_keys):
    """
    pets: [{id, name}, ...]
    vaccine_records / deworming_records: [{id, pet_id, item_name, next_due_date}, ...] (next_due_date可為None, 代表不跳過但沒有下次到期日, 略過)
    custom_reminders: [{id, pet_id, title, due_date, remind_days_before}, ...]
    notified_keys: set(str) — 已經推播過的reminder_key, 避免重複通知
    today: date

    回傳: [{key, pet_name, title, due_date, days_left}, ...] 尚未推播過、且落在提醒範圍內的項目
    """
    today = _parse_date(today)
    pet_name_by_id = {p["id"]: p["name"] for p in pets}
    due = []

    def _check(kind, records, title_fmt, default_days_before):
        for r in records:
            due_date_raw = r.get("next_due_date") if kind != "custom" else r.get("due_date")
            if not due_date_raw:
                continue
            due_date = _parse_date(due_date_raw)
            days_left = (due_date - today).days
            days_before = r.get("remind_days_before", default_days_before) if kind == "custom" else default_days_before
            if days_left > days_before:
                continue  # 還沒到提醒範圍
            key = _reminder_key(kind, r["id"], due_date_raw)
            if key in notified_keys:
                continue
            pet_name = pet_name_by_id.get(r["pet_id"], "?")
            title = title_fmt.format(pet=pet_name, item=r.get("item_name") or r.get("title"))
            due.append({
                "key": key,
                "kind": kind,
                "record_id": r["id"],
                "pet_id": r["pet_id"],
                "pet_name": pet_name,
                "title": title,
                "due_date": due_date_raw,
                "days_left": days_left,
                "category": r.get("category"),
                "repeat_days": r.get("repeat_days"),
            })

    _check("vaccine", vaccine_records, "{pet} 的疫苗「{item}」即將到期", 3)
    _check("deworming", deworming_records, "{pet} 的驅蟲「{item}」即將到期", 3)
    _check("custom", custom_reminders, "{pet}：{item}", 3)
    return due
