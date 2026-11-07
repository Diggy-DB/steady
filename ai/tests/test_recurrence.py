"""Tests for src/ai/recurrence.py and repeating events in the planning tools."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from ai import recurrence
from ai.planning import busy, find_free_slots
from ai.schedule import FixtureStore, ToolContext

DETROIT = ZoneInfo("America/Detroit")


def test_weekly_days_skip_the_break_and_stop_at_until():
    days = recurrence.days(date(2027, 3, 2), "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20270318;X-SKIP=20270309,20270311", date(2027, 12, 31))
    assert days == [date(2027, 3, 2), date(2027, 3, 4), date(2027, 3, 16), date(2027, 3, 18)]


@pytest.mark.parametrize("rule,expected", [
    ("FREQ=DAILY;COUNT=3", [date(2027, 1, 4), date(2027, 1, 5), date(2027, 1, 6)]),
    ("FREQ=WEEKLY;INTERVAL=2;COUNT=3", [date(2027, 1, 4), date(2027, 1, 18), date(2027, 2, 1)]),
    ("RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=3", [date(2027, 1, 4), date(2027, 1, 6), date(2027, 1, 11)]),
])
def test_other_rules(rule, expected):
    assert recurrence.days(date(2027, 1, 4), rule, date(2027, 12, 31)) == expected


def test_unknown_rules_are_refused():
    with pytest.raises(ValueError):
        recurrence.parse("FREQ=MONTHLY;BYMONTHDAY=1")


def test_a_class_keeps_its_local_time_after_daylight_saving_ends():
    event = {"event_id": "9", "name": "Lecture", "start": "2026-10-27T09:00:00-04:00", "end": "2026-10-27T10:00:00-04:00",
             "recurrence_rule": "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261110", "changeable": True}
    found = recurrence.occurrences(event, datetime(2026, 10, 26, tzinfo=DETROIT), datetime(2026, 11, 30, tzinfo=DETROIT), DETROIT)
    assert [o["start"] for o in found] == ["2026-10-27T09:00:00-04:00", "2026-11-03T09:00:00-05:00", "2026-11-10T09:00:00-05:00"]
    assert not any(o["changeable"] for o in found)  # one class can't be moved on its own


def test_the_planner_sees_a_weekly_class_every_week():
    store = FixtureStore()
    store.data["events"].append({"event_id": "w1", "user_id": "user-1", "name": "Weekly seminar", "changeable": True,
                                 "start": "2026-09-30T08:00:00-04:00", "end": "2026-09-30T09:00:00-04:00",
                                 "recurrence_rule": "FREQ=WEEKLY;BYDAY=WE"})
    ctx = ToolContext(store, "user-1", datetime(2026, 10, 5, 7, 0, tzinfo=DETROIT))
    wednesday = [b for b in busy(ctx, datetime(2026, 10, 7, tzinfo=DETROIT), datetime(2026, 10, 8, tzinfo=DETROIT))
                 if b[2] == "Weekly seminar"]
    assert [(b[0].hour, b[1].hour) for b in wednesday] == [(8, 9)]
    slots = find_free_slots(ctx, "2026-10-07", "2026-10-07", 30)
    assert slots["days"][0]["free"][0] == "09:00-10:00"  # 8-9 is the seminar
    assert store.event("user-1", "w1")["changeable"] is False


def test_a_pending_weekly_class_blocks_time_each_week():
    store = FixtureStore()
    store.add_suggestion("user-1", {"type": "CREATE_EVENT", "target_id": None, "proposed_change": {
        "name": "CSE 260 Lecture", "start": "2026-10-06T12:40:00-04:00", "end": "2026-10-06T14:00:00-04:00",
        "recurrence_rule": "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261231"}, "depends_on": []})
    ctx = ToolContext(store, "user-1", datetime(2026, 10, 5, 7, 0, tzinfo=DETROIT))
    found = busy(ctx, datetime(2026, 10, 15, tzinfo=DETROIT), datetime(2026, 10, 16, tzinfo=DETROIT))
    assert [(b[0].strftime("%m-%d %H:%M"), b[2]) for b in found if "pending" in b[2]] == [("10-15 12:40", "your pending suggestion s1")]


def test_tasks_never_block_time():
    store = FixtureStore()
    store.add_suggestion("user-1", {"type": "CREATE_TASK", "target_id": None,
                                    "proposed_change": {"name": "HW 1", "due": "2026-10-07T23:59:00-04:00"}, "depends_on": []})
    ctx = ToolContext(store, "user-1", datetime(2026, 10, 5, 7, 0, tzinfo=DETROIT))
    assert not [b for b in busy(ctx, datetime(2026, 10, 7, tzinfo=DETROIT), datetime(2026, 10, 8, tzinfo=DETROIT)) if "pending" in b[2]]
