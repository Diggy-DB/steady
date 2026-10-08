"""Tests for the schedule tool. They use the fixture and a fixed, fake "now"."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ai.schedule import FixtureStore, ToolContext, ToolError, get_schedule, overlaps

DETROIT = ZoneInfo("America/Detroit")


def monday(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=DETROIT)


def context(now: datetime = monday(18, 30), user_id: str = "user-1") -> ToolContext:
    return ToolContext(store=FixtureStore(), user_id=user_id, now=now)


def test_touching_ranges_do_not_overlap():
    assert not overlaps(monday(15), monday(16), monday(16), monday(17))


def test_partial_overlap():
    assert overlaps(monday(15), monday(16), monday(15, 30), monday(16, 30))


def test_one_day_in_order_with_past_and_upcoming():
    result = get_schedule(context(), "2026-10-05", "2026-10-05")
    events = [(e["name"], e["start"], e["when"]) for e in result["events"]]
    assert events == [
        ("CSE 232 lecture", "10:00 AM", "already over"),
        ("Study session", "7:00 PM", "upcoming"),
    ]


def test_happening_now():
    result = get_schedule(context(now=monday(10, 30)), "2026-10-05", "2026-10-05")
    assert result["events"][0]["when"] == "happening now"


def test_utc_times_are_shown_in_local_time():
    result = get_schedule(context(), "2026-10-06", "2026-10-06")
    work = result["events"][0]
    assert (work["name"], work["start"], work["end"]) == ("Work shift", "1:00 PM", "5:00 PM")



def test_never_returns_another_users_data():
    names = [e["name"] for e in get_schedule(context(), "2026-10-05", "2026-10-11")["events"]]
    assert "Dentist appointment" not in names  # user-2's event, during user-1's Monday
    other = get_schedule(context(user_id="user-2"), "2026-10-05", "2026-10-05")
    assert [e["name"] for e in other["events"]] == ["Dentist appointment"]


def test_tasks_due_in_range():
    result = get_schedule(context(), "2026-10-08", "2026-10-09")
    assert [(t["name"], t["due"]) for t in result["tasks"]] == [
        ("MTH 133 problem set", "Thursday, October 8"),
        ("CSE 232 project", "Friday, October 9"),
    ]


@pytest.mark.parametrize(
    ("start", "end"),
    [("tomorrow", "2026-10-06"), ("2026-10-07", "2026-10-06"), ("2026-10-01", "2026-10-31")],
)
def test_bad_requests_become_tool_errors(start, end):
    with pytest.raises(ToolError):
        get_schedule(context(), start, end)
