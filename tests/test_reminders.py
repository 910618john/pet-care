import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reminders

PETS = [{"id": 1, "name": "小白"}]


def test_vaccine_due_within_window_is_returned():
    today = date(2026, 9, 22)
    vaccines = [{"id": 1, "pet_id": 1, "item_name": "狂犬病疫苗", "next_due_date": "2026-09-24"}]
    due = reminders.collect_due_reminders(PETS, vaccines, [], [], today, notified_keys=set())
    assert len(due) == 1
    assert due[0]["pet_name"] == "小白"
    assert due[0]["days_left"] == 2


def test_vaccine_far_in_future_not_returned():
    today = date(2026, 9, 22)
    vaccines = [{"id": 1, "pet_id": 1, "item_name": "狂犬病疫苗", "next_due_date": "2026-12-01"}]
    due = reminders.collect_due_reminders(PETS, vaccines, [], [], today, notified_keys=set())
    assert due == []


def test_overdue_item_still_returned_once():
    today = date(2026, 9, 22)
    vaccines = [{"id": 1, "pet_id": 1, "item_name": "狂犬病疫苗", "next_due_date": "2026-08-01"}]
    due = reminders.collect_due_reminders(PETS, vaccines, [], [], today, notified_keys=set())
    assert len(due) == 1
    assert due[0]["days_left"] < 0


def test_already_notified_key_is_skipped():
    today = date(2026, 9, 22)
    vaccines = [{"id": 1, "pet_id": 1, "item_name": "狂犬病疫苗", "next_due_date": "2026-09-24"}]
    key = "vaccine:1:2026-09-24"
    due = reminders.collect_due_reminders(PETS, vaccines, [], [], today, notified_keys={key})
    assert due == []


def test_deworming_and_custom_reminders_both_checked():
    today = date(2026, 9, 22)
    deworming = [{"id": 5, "pet_id": 1, "item_name": "心絲蟲藥", "next_due_date": "2026-09-23"}]
    custom = [{"id": 9, "pet_id": 1, "title": "洗牙回診", "due_date": "2026-09-25", "remind_days_before": 5}]
    due = reminders.collect_due_reminders(PETS, [], deworming, custom, today, notified_keys=set())
    keys = {d["key"] for d in due}
    assert "deworming:5:2026-09-23" in keys
    assert "custom:9:2026-09-25" in keys


def test_record_without_due_date_is_ignored():
    today = date(2026, 9, 22)
    vaccines = [{"id": 1, "pet_id": 1, "item_name": "狂犬病疫苗", "next_due_date": None}]
    due = reminders.collect_due_reminders(PETS, vaccines, [], [], today, notified_keys=set())
    assert due == []


def test_custom_reminder_passes_through_category_and_repeat_days():
    today = date(2026, 9, 22)
    custom = [{
        "id": 9, "pet_id": 1, "title": "除蚤", "due_date": "2026-09-23",
        "remind_days_before": 3, "category": "除蚤", "repeat_days": 30,
    }]
    due = reminders.collect_due_reminders(PETS, [], [], custom, today, notified_keys=set())
    assert len(due) == 1
    assert due[0]["kind"] == "custom"
    assert due[0]["record_id"] == 9
    assert due[0]["category"] == "除蚤"
    assert due[0]["repeat_days"] == 30


def test_vaccine_reminder_has_no_repeat_days():
    today = date(2026, 9, 22)
    vaccines = [{"id": 1, "pet_id": 1, "item_name": "狂犬病疫苗", "next_due_date": "2026-09-24"}]
    due = reminders.collect_due_reminders(PETS, vaccines, [], [], today, notified_keys=set())
    assert due[0]["kind"] == "vaccine"
    assert due[0]["repeat_days"] is None
