"""Tests for propose_delete and propose_journal_entry: what they suggest, what they refuse, and what
accepting does. Fake "now": Monday Oct 5, 2026, 6:30 PM (the alex week, fixtures/week.json)."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from ai.agent import run_tool
from ai.planning import busy, get_journal, propose_delete, propose_journal_entry, propose_move_event, recheck
from ai.schedule import FixtureStore, ToolContext, ToolError

DETROIT = ZoneInfo("America/Detroit")
NOW = datetime(2026, 10, 5, 18, 30, tzinfo=DETROIT)


@pytest.fixture
def ctx() -> ToolContext:
    store = FixtureStore()
    store.data["journals"] = [{"journal_id": "j1", "user_id": "user-1", "date": "2026-10-04",
                               "information": "Quiet Sunday. Read two chapters."}]
    return ToolContext(store, "user-1", NOW)


def accept(ctx, suggestion_id: str) -> list[str]:
    """What the server's Accept does: check again, then apply. Returns the problems (empty if applied)."""
    suggestion = next(s for s in ctx.store.suggestions("user-1") if s["suggestion_id"] == suggestion_id)
    problems = recheck(ctx, suggestion)
    if not problems:
        ctx.store.apply(suggestion)
        ctx.store.set_status(suggestion_id, "ACCEPTED")
    return problems


# ---- delete ----

def test_deleting_an_event_is_only_a_suggestion_until_accepted(ctx):
    result = propose_delete(ctx, "event", "e4", "You said you're skipping the gym.")
    assert "Gym" in result["summary"] and ctx.store.event("user-1", "e4") is not None
    [s] = ctx.store.suggestions("user-1")
    assert s["type"] == "DELETE_EVENT" and s["target_id"] is None
    assert (s["proposed_change"]["id"], s["proposed_change"]["name"]) == ("e4", "Gym")
    assert accept(ctx, s["suggestion_id"]) == [] and ctx.store.event("user-1", "e4") is None


@pytest.mark.parametrize("what,item_id,message", [
    ("event", "e1", "fixed"),  # the CSE 232 lecture
    ("event", "e99", "no event"),
    ("task", "t99", "no task"),
    ("journal", "2026-10-03", "no journal entry"),
    ("journal", "yesterday", "date"),
    ("calendar", "e2", "what must be"),
])
def test_refused_deletes_say_why(ctx, what, item_id, message):
    with pytest.raises(ToolError, match=message):
        propose_delete(ctx, what, item_id, "")
    assert ctx.store.suggestions("user-1") == []


def test_another_users_event_counts_as_missing(ctx):
    other = next(e for e in ctx.store.data["events"] if e["user_id"] != "user-1")
    with pytest.raises(ToolError, match="no event"):
        propose_delete(ctx, "event", other["event_id"], "")


def test_a_task_and_a_journal_entry_can_be_deleted(ctx):
    task = propose_delete(ctx, "task", "t1", "You dropped it.")
    journal = propose_delete(ctx, "journal", "2026-10-04", "As you asked.")
    assert accept(ctx, task["suggestion_id"]) == [] and ctx.store.task("user-1", "t1") is None
    assert accept(ctx, journal["suggestion_id"]) == [] and ctx.store.journal_on("user-1", date(2026, 10, 4)) is None


def test_one_pending_change_per_event(ctx):
    propose_delete(ctx, "event", "e2", "")
    with pytest.raises(ToolError, match="pending delete"):
        propose_move_event(ctx, "e2", "2026-10-05 20:00", "2026-10-05 22:00", "")
    with pytest.raises(ToolError, match="pending delete"):
        propose_delete(ctx, "event", "e2", "")


def test_an_event_with_a_pending_move_cant_also_be_deleted(ctx):
    propose_move_event(ctx, "e2", "2026-10-05 20:00", "2026-10-05 22:00", "")
    with pytest.raises(ToolError, match="pending move"):
        propose_delete(ctx, "event", "e2", "")


def test_a_pending_delete_still_counts_as_busy_until_accepted(ctx):
    propose_delete(ctx, "event", "e2", "")
    names = [b[2] for b in busy(ctx, datetime(2026, 10, 5, 19, tzinfo=DETROIT), datetime(2026, 10, 5, 21, tzinfo=DETROIT))]
    assert names == ["Study session"]


def test_accepting_a_delete_twice_or_after_it_is_gone(ctx):
    s = propose_delete(ctx, "event", "e2", "")
    ctx.store.data["events"] = [e for e in ctx.store.data["events"] if e["event_id"] != "e2"]  # deleted by hand meanwhile
    assert accept(ctx, s["suggestion_id"]) == ["Study session is already gone"]


def test_a_weekly_class_cant_be_deleted_by_the_ai(ctx):
    ctx.store.data["events"].append({"event_id": "w1", "user_id": "user-1", "name": "Seminar", "changeable": True,
                                     "start": "2026-10-06T08:00:00-04:00", "end": "2026-10-06T09:00:00-04:00",
                                     "recurrence_rule": "FREQ=WEEKLY;BYDAY=TU"})
    with pytest.raises(ToolError, match="repeats every week"):
        propose_delete(ctx, "event", "w1", "")


# ---- journal ----

def test_a_journal_entry_starts_a_new_day(ctx):
    result = propose_journal_entry(ctx, "2026-10-05", "Finished the CSE 232 project. Felt proud.")
    [s] = ctx.store.suggestions("user-1")
    assert s["type"] == "ADD_JOURNAL" and s["proposed_change"]["adds_to_existing"] is False
    assert "new entry" in result["summary"]
    assert accept(ctx, s["suggestion_id"]) == []
    assert ctx.store.journal_on("user-1", date(2026, 10, 5))["information"] == "Finished the CSE 232 project. Felt proud."


def test_a_journal_entry_adds_to_the_days_entry(ctx):
    result = propose_journal_entry(ctx, "2026-10-04", "Also called home.")
    assert "added to" in result["summary"]
    accept(ctx, result["suggestion_id"])
    assert ctx.store.journal_on("user-1", date(2026, 10, 4))["information"] == "Quiet Sunday. Read two chapters.\n\nAlso called home."


@pytest.mark.parametrize("day,text,message", [
    ("2026-10-06", "Tomorrow went well.", "hasn't happened yet"),
    ("2026-10-05", "   ", "can't be empty"),
    ("Monday", "Hi", "date"),
    ("2026-10-05", "x" * 2001, "under 2000"),
])
def test_refused_journal_entries(ctx, day, text, message):
    with pytest.raises(ToolError, match=message):
        propose_journal_entry(ctx, day, text)


def test_journal_and_delete_suggestions_dont_break_free_time(ctx):
    propose_journal_entry(ctx, "2026-10-05", "Long day.")
    propose_delete(ctx, "task", "t1", "")
    result = json.loads(run_tool(ctx, "find_free_slots", json.dumps({"start_date": "2026-10-06", "end_date": "2026-10-06",
                                                                      "minutes": 60})))
    assert result["days"][0]["free"]  # still answers


def test_the_model_reaches_both_tools_by_name(ctx):
    out = run_tool(ctx, "propose_delete", json.dumps({"what": "task", "id": "t2", "reason": "Done with it."}))
    assert "Suggested deleting the task CSE 232 project" in out
    out = run_tool(ctx, "propose_journal_entry", json.dumps({"date": "2026-10-05", "text": "Good day."}))
    assert "journal" in out and not out.startswith("Error")


# ---- edit ----

def test_reading_a_journal_entry(ctx):
    assert get_journal(ctx, "2026-10-04")["text"] == "Quiet Sunday. Read two chapters."
    assert get_journal(ctx, "2026-10-03") == {"date": "2026-10-03", "day": "Saturday, October 3", "text": None,
                                               "note": "no journal entry that day"}


def test_an_edit_replaces_the_entry_once_accepted(ctx):
    result = propose_journal_entry(ctx, "2026-10-04", "Quiet Sunday. Read three chapters.", replace=True)
    [s] = ctx.store.suggestions("user-1")
    assert s["type"] == "EDIT_JOURNAL" and "before and after" in result["summary"]
    assert s["proposed_change"]["old"] == "Quiet Sunday. Read two chapters."
    assert ctx.store.journal_on("user-1", date(2026, 10, 4))["information"] == "Quiet Sunday. Read two chapters."
    assert accept(ctx, s["suggestion_id"]) == []
    assert ctx.store.journal_on("user-1", date(2026, 10, 4))["information"] == "Quiet Sunday. Read three chapters."


def test_an_edit_never_overwrites_what_the_user_wrote_since(ctx):
    s = propose_journal_entry(ctx, "2026-10-04", "Quiet Sunday. Read three chapters.", replace=True)
    ctx.store.journal_on("user-1", date(2026, 10, 4))["information"] = "Quiet Sunday. Read two chapters. Then a walk."
    assert "has changed" in accept(ctx, s["suggestion_id"])[0]
    assert ctx.store.journal_on("user-1", date(2026, 10, 4))["information"].endswith("Then a walk.")


@pytest.mark.parametrize("day,text,message", [
    ("2026-10-03", "Something.", "no journal entry"),
    ("2026-10-04", "Quiet Sunday. Read two chapters.", "same as the current entry"),
])
def test_refused_edits(ctx, day, text, message):
    with pytest.raises(ToolError, match=message):
        propose_journal_entry(ctx, day, text, replace=True)


def test_the_model_reads_then_edits(ctx):
    assert "two chapters" in run_tool(ctx, "get_journal", json.dumps({"date": "2026-10-04"}))
    out = run_tool(ctx, "propose_journal_entry", json.dumps({"date": "2026-10-04", "text": "Quiet Sunday.", "replace": True}))
    assert not out.startswith("Error") and ctx.store.suggestions("user-1")[0]["type"] == "EDIT_JOURNAL"


def test_saying_it_suggests_a_delete_without_making_one_gets_a_reminder(ctx, monkeypatch):
    from ai.agent import NUDGE_CHANGE, run_agent
    from test_agent import FakeClient, reply

    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: None)
    client = FakeClient([
        reply("I suggest deleting your gym session tomorrow."),  # claims it, but made nothing
        reply(tool_calls=[("propose_delete", {"what": "event", "id": "e4", "reason": "You're skipping it."})]),
        reply("I suggest deleting tomorrow's gym session; accept it to remove it."),
    ])
    result = run_agent(client, "fake", ctx, "I'm skipping the gym tomorrow, remove it.", verbose=False)
    assert result["nudged"] and client.requests[1]["messages"][-1] == {"role": "system", "content": NUDGE_CHANGE}
    assert [s["type"] for s in ctx.store.suggestions("user-1")] == ["DELETE_EVENT"]


def test_advice_without_a_change_gets_no_reminder(ctx, monkeypatch):
    from ai.agent import run_agent
    from test_agent import FakeClient, reply

    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: None)
    result = run_agent(FakeClient([reply("Try short breaks between study blocks.")]), "fake", ctx, "Any tips?", verbose=False)
    assert not result["nudged"] and result["rounds"] == 1


def test_a_new_entry_for_a_long_gone_day_is_a_date_mistake(ctx):
    with pytest.raises(ToolError, match=r"Today is Monday, October 5, 2026 \(2026-10-05\); yesterday was 2026-10-04"):
        propose_journal_entry(ctx, "2025-10-04", "Wrong year.")
    propose_journal_entry(ctx, "2026-09-29", "Within a week is fine.")


def test_an_old_day_that_has_an_entry_can_still_be_added_to(ctx):
    ctx.store.data["journals"].append({"journal_id": "j9", "user_id": "user-1", "date": "2026-09-01", "information": "Start of term."})
    propose_journal_entry(ctx, "2026-09-01", "Looking back, a good start.")


@pytest.mark.parametrize("asked,allowed", [
    ("I need two hours tomorrow for my BIO lab report. When?", False),  # the real run that added a delete
    ("I'm skipping the gym tomorrow, take it off my calendar.", True),
    ("Cancel movie night.", True),
    ("I don't need the study block on Friday anymore.", True),
    ("Should I delete your gym session?\nyes please", True),  # Steady asked, the user said yes
])
def test_deletes_need_the_user_to_ask(ctx, asked, allowed):
    ctx.asked = asked
    if allowed:
        propose_delete(ctx, "event", "e4", "As you asked.")
    else:
        with pytest.raises(ToolError, match="didn't ask to delete"):
            propose_delete(ctx, "event", "e4", "")


@pytest.mark.parametrize("asked,allowed", [
    ("Ugh, rough day. The CHM lab took forever.", False),
    ("Add to my journal: rough day.", True),
    ("Can you note down that the lab took forever?", True),
])
def test_journal_entries_need_the_user_to_ask(ctx, asked, allowed):
    ctx.asked = asked
    if allowed:
        propose_journal_entry(ctx, "2026-10-05", "Rough day.")
    else:
        with pytest.raises(ToolError, match="didn't ask to write in their journal"):
            propose_journal_entry(ctx, "2026-10-05", "Rough day.")


def test_the_agent_tells_the_tools_what_was_asked(ctx, monkeypatch):
    from ai.agent import run_agent
    from test_agent import FakeClient, reply

    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: None)
    client = FakeClient([reply(tool_calls=[("propose_delete", {"what": "task", "id": "t1", "reason": "x"})]), reply("Done.")])
    run_agent(client, "fake", ctx, "I need two hours tomorrow for my BIO lab report.", verbose=False)
    assert "didn't ask to delete" in client.requests[1]["messages"][-1]["content"] and ctx.store.suggestions("user-1") == []
