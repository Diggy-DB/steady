"""Tests for free time, the shared checks and the propose tools. Fake "now": Monday Oct 5, 6:30 PM."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ai.agent import TOOLS
from ai.planning import find_free_slots, propose_move_event, propose_new_event, round_up
from ai.schedule import FixtureStore, ToolContext, ToolError

DETROIT = ZoneInfo("America/Detroit")
MONDAY_EVENING = datetime(2026, 10, 5, 18, 30, tzinfo=DETROIT)


def context(user_id: str = "user-1") -> ToolContext:
    return ToolContext(store=FixtureStore(), user_id=user_id, now=MONDAY_EVENING)


def free_times(result: dict) -> list[str]:
    """Flatten the per-day result into "YYYY-MM-DD HH:MM-HH:MM" strings."""
    return [f"{day['date']} {slot}" for day in result["days"] for slot in day["free"]]


def test_round_up_to_quarter_hour():
    assert round_up(datetime(2026, 10, 5, 18, 30, tzinfo=DETROIT)).minute == 30
    assert round_up(datetime(2026, 10, 5, 18, 37, tzinfo=DETROIT)).minute == 45


def test_free_slots_skip_busy_times():
    # Wednesday: lecture 10-12 and study session 2-4 PM; the day runs 8 AM to 10 PM.
    result = find_free_slots(context(), "2026-10-07", "2026-10-07", 60)
    assert free_times(result) == ["2026-10-07 08:00-10:00", "2026-10-07 12:00-14:00", "2026-10-07 16:00-22:00"]


def test_free_slots_never_in_the_past():
    # Monday at 6:30 PM: only 6:30-7 PM (30 min) and 9-10 PM (60 min) are left.
    assert free_times(find_free_slots(context(), "2026-10-05", "2026-10-05", 30)) == [
        "2026-10-05 18:30-19:00",
        "2026-10-05 21:00-22:00",
    ]
    assert free_times(find_free_slots(context(), "2026-10-05", "2026-10-05", 60)) == ["2026-10-05 21:00-22:00"]


def test_free_slots_rejects_bad_minutes():
    with pytest.raises(ToolError):
        find_free_slots(context(), "2026-10-07", "2026-10-07", "an hour")


def test_propose_new_event_stores_a_pending_suggestion():
    ctx = context()
    result = propose_new_event(ctx, "Gym", "2026-10-07 12:30", "2026-10-07 13:30", "Free after class.")
    assert result["status"] == "PENDING"
    [suggestion] = ctx.store.suggestions("user-1")
    assert suggestion["type"] == "CREATE_EVENT" and suggestion["status"] == "PENDING"
    assert suggestion["proposed_change"] == {
        "name": "Gym",
        "start": "2026-10-07T12:30:00-04:00",
        "end": "2026-10-07T13:30:00-04:00",
    }


def test_proposal_overlapping_class_is_rejected():
    with pytest.raises(ToolError, match="CSE 232 lecture"):
        propose_new_event(context(), "Gym", "2026-10-07 11:00", "2026-10-07 12:00", "")


def test_proposal_in_the_past_is_rejected():
    with pytest.raises(ToolError, match="already started"):
        propose_new_event(context(), "Gym", "2026-10-05 17:00", "2026-10-05 18:00", "")


def test_bad_time_format_is_rejected():
    with pytest.raises(ToolError, match="must look like"):
        propose_new_event(context(), "Gym", "Wednesday noon", "2026-10-07 13:00", "")


def test_proposals_cannot_overlap_each_other():
    ctx = context()
    propose_new_event(ctx, "Gym", "2026-10-07 12:30", "2026-10-07 13:30", "")
    with pytest.raises(ToolError, match="pending suggestion s1"):
        propose_new_event(ctx, "Reading", "2026-10-07 13:00", "2026-10-07 14:00", "")
    assert "2026-10-07 12:00-14:00" not in free_times(find_free_slots(ctx, "2026-10-07", "2026-10-07", 30))


def test_fixed_event_cannot_be_moved():
    with pytest.raises(ToolError, match="can't be moved"):
        propose_move_event(context(), "e5", "2026-10-07 16:00", "2026-10-07 18:00", "")


def test_move_may_overlap_its_own_old_time():
    ctx = context()
    # Study session e6 is Wednesday 2-4 PM; moving it one hour later overlaps only itself.
    result = propose_move_event(ctx, "e6", "2026-10-07 15:00", "2026-10-07 17:00", "Later start.")
    assert result["status"] == "PENDING"
    assert ctx.store.suggestions("user-1")[0]["target_id"] == "e6"


def test_cannot_move_another_users_event():
    with pytest.raises(ToolError, match="no event with id 'e11'"):
        propose_move_event(context(), "e11", "2026-10-07 16:00", "2026-10-07 17:00", "")


def test_cannot_move_an_event_that_is_over():
    # On Tuesday morning, Monday's 7-9 PM study session (e2) is over.
    ctx = ToolContext(store=FixtureStore(), user_id="user-1", now=datetime(2026, 10, 6, 9, 0, tzinfo=DETROIT))
    with pytest.raises(ToolError, match="already over"):
        propose_move_event(ctx, "e2", "2026-10-07 16:00", "2026-10-07 18:00", "")


def test_agent_offers_all_four_tools():
    assert set(TOOLS) == {"get_schedule", "find_free_slots", "propose_new_event", "propose_move_event"}


def test_free_slots_leave_out_full_days():
    # Thursday from 8 AM: work 1-5 PM and club 6-7:30 PM leave 8 AM-1 PM, 5-6 PM, 7:30-10 PM; nothing is 6 hours.
    assert find_free_slots(context(), "2026-10-08", "2026-10-08", 360)["days"] == []


def test_new_event_in_a_moved_events_old_time_depends_on_the_move():
    ctx = context()
    # Move tonight's study session (7-9 PM) later; its old time becomes usable, but only together with the move.
    propose_move_event(ctx, "e2", "2026-10-05 21:00", "2026-10-05 23:00", "Make room for the assignment.")
    assert "2026-10-05 18:30-21:00" in free_times(find_free_slots(ctx, "2026-10-05", "2026-10-05", 60))
    result = propose_new_event(ctx, "Assignment", "2026-10-05 18:30", "2026-10-05 21:00", "Due tonight.")
    assert "s1" in result["summary"]
    assert ctx.store.suggestions("user-1")[1]["depends_on"] == ["s1"]


def test_independent_proposal_has_no_dependencies():
    ctx = context()
    propose_new_event(ctx, "Gym", "2026-10-07 12:30", "2026-10-07 13:30", "")
    assert ctx.store.suggestions("user-1")[0]["depends_on"] == []


def test_an_event_can_only_have_one_pending_move():
    ctx = context()
    propose_move_event(ctx, "e6", "2026-10-07 16:00", "2026-10-07 18:00", "")
    with pytest.raises(ToolError, match="already has a pending move"):
        propose_move_event(ctx, "e6", "2026-10-07 18:00", "2026-10-07 20:00", "")


def test_proposing_mentions_similar_events_already_planned_that_week():
    ctx = context()
    # Tuesday already has "Gym" 6-7 PM; "Gym session" is similar ("session" is a generic word).
    result = propose_new_event(ctx, "Gym session", "2026-10-07 12:30", "2026-10-07 13:30", "")
    assert "Already planned this week" in result["summary"] and "Gym (Tuesday, October 6" in result["summary"]
    # A second one also lists the first suggestion.
    second = propose_new_event(ctx, "Gym", "2026-10-09 17:00", "2026-10-09 18:00", "")
    assert "pending suggestion s1: Gym session" in second["summary"]


def test_no_note_for_unrelated_events():
    result = propose_new_event(context(), "Work on MTH 133 problem set", "2026-10-07 18:00", "2026-10-07 21:00", "")
    assert "Already planned" not in result["summary"]


def test_events_already_over_dont_count():
    # On Wednesday evening, Monday's and Wednesday's study sessions are over; Friday's is still ahead.
    late = ToolContext(store=FixtureStore(), user_id="user-1", now=datetime(2026, 10, 7, 18, 0, tzinfo=DETROIT))
    result = propose_new_event(late, "Study session", "2026-10-08 20:00", "2026-10-08 21:00", "")
    assert "Friday, October 9" in result["summary"]
    assert "Monday, October 5" not in result["summary"] and "Wednesday, October 7" not in result["summary"]
