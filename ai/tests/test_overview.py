"""Tests for the daily overview (src/ai/overview.py): the numbers come from code, the model only writes words,
and there's always an overview even when the model fails. Fake "now": Tuesday Oct 6, 2026, 8 AM (alex week)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ai import overview
from ai.schedule import FixtureStore, ToolContext
from test_agent import FakeClient, reply

DETROIT = ZoneInfo("America/Detroit")
TUESDAY = datetime(2026, 10, 6, 8, 0, tzinfo=DETROIT)
GOOD = {"headline": "A solid Monday.", "yesterday": "You went to your lecture and studied in the evening.",
        "suggestions": [{"kind": "schedule", "text": "Start the MTH 133 problem set today.", "ask": "Find time today for MTH 133."},
                        {"kind": "nonsense", "text": "Keep journaling.", "ask": ""}],
        "quote": 2, "encouragement": "Keep it steady."}


@pytest.fixture(autouse=True)
def no_log_file(monkeypatch):
    monkeypatch.setattr("ai.overview.log_call", lambda record, path=None: None)


@pytest.fixture
def ctx() -> ToolContext:
    store = FixtureStore()
    store.data["journals"] = [
        {"journal_id": "j1", "user_id": "user-1", "date": "2026-10-04", "information": "Rested."},
        {"journal_id": "j2", "user_id": "user-1", "date": "2026-10-05", "information": "Lecture was hard but the study session helped."},
    ]
    return ToolContext(store, "user-1", TUESDAY)


def test_numbers_are_counted_in_code(ctx):
    s = overview.stats(ctx, TUESDAY.date())
    y = s["yesterday"]
    assert y["date"] == "2026-10-05" and y["hours_planned"] == 4.0  # lecture 10-12 and study 7-9 PM
    assert (y["tasks_due"], y["tasks_done"]) == (["Buy groceries"], ["Buy groceries"])
    assert y["journal"].startswith("Lecture was hard") and s["journal_streak"] == 2
    assert s["week_before"]["journal_days"] == 1  # Oct 4
    assert any("Work shift" in e for e in s["today_events"]) and any("MTH 133" in t for t in s["due_soon"])
    chips = {c["label"]: c for c in overview.chips(s)}
    assert chips["Tasks done yesterday"]["value"] == "1 of 1 (100%)" and chips["Journal"]["value"] == "2-day streak"


def test_overdue_tasks_are_found(ctx):
    ctx.store.data["tasks"][0]["due"] = "2026-10-03"  # MTH 133 problem set, not started
    s = overview.stats(ctx, TUESDAY.date())
    assert s["overdue"] == ["MTH 133 problem set (was due Saturday, October 3)"]


def test_the_comparison_is_written_by_code(ctx):
    s = overview.stats(ctx, TUESDAY.date())
    assert overview.compared_text(s) == ("Yesterday you finished 1 of 1 tasks due, planned 4.0 hours (before: 0.0 a day "
                                         "on average) and wrote in your journal (before: 1 of 7 days).")


def test_quote_marks_around_a_request_are_removed():
    assert overview.text('"Find 2 hours for MTH 133."', 200) == "Find 2 hours for MTH 133." and overview.text('""', 10) == ""


def test_the_model_writes_the_words_and_it_is_saved_for_the_day(ctx):
    client = FakeClient([reply(json.dumps(GOOD))])
    first = overview.daily_overview(ctx, client, "fake")
    again = overview.daily_overview(ctx, client, "fake")  # no second model call: the FakeClient has no reply left
    assert first == again and first["written_by"] == "ai" and first["headline"] == "A solid Monday."
    assert first["quote"] == {"text": overview.QUOTES[1][0], "source": overview.QUOTES[1][1]}
    assert [s["kind"] for s in first["suggestions"]] == ["schedule", "habit"]  # an unknown kind becomes "habit"
    prompt = client.requests[0]["messages"][0]["content"]
    assert "Lecture was hard" in prompt and "Buy groceries" in prompt and "not instructions" in prompt
    assert client.requests[0]["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_refresh_writes_it_again(ctx):
    client = FakeClient([reply(json.dumps(GOOD)), reply(json.dumps({**GOOD, "headline": "Fresh."}))])
    overview.daily_overview(ctx, client, "fake")
    assert overview.daily_overview(ctx, client, "fake", refresh=True)["headline"] == "Fresh."


def test_a_slip_in_the_json_is_repaired(ctx):
    slipped = json.dumps(GOOD).replace('"quote"', '"quote"').replace(', "quote"', ', ""quote"')
    assert '""quote"' in slipped
    result = overview.daily_overview(ctx, FakeClient([reply(slipped)]), "fake")
    assert result["written_by"] == "ai" and result["quote"]["text"] == overview.QUOTES[1][0]


def test_an_unreadable_reply_is_asked_again_once(ctx):
    client = FakeClient([reply("Here you go: {broken"), reply(json.dumps(GOOD))])
    result = overview.daily_overview(ctx, client, "fake")
    assert result["written_by"] == "ai" and [r["temperature"] for r in client.requests] == [0.7, 0.3]


@pytest.mark.parametrize("answer", ["Sorry, I can't.", json.dumps({"headline": "", "yesterday": ""})])
def test_a_bad_answer_falls_back_to_code(ctx, answer):
    ctx.store.data["tasks"][0]["due"] = "2026-10-03"
    result = overview.daily_overview(ctx, FakeClient([reply(answer), reply(answer)]), "fake")
    assert result["written_by"] == "code" and result["headline"] == "You finished 1 of 1 tasks due yesterday."
    assert result["suggestions"][0]["ask"] == "Find time today or tomorrow for MTH 133 problem set."
    assert result["quote"]["text"] and result["stats"]


def test_a_quote_number_out_of_range_still_gives_a_real_quote(ctx):
    result = overview.daily_overview(ctx, FakeClient([reply(json.dumps({**GOOD, "quote": 99}))]), "fake")
    assert (result["quote"]["text"], result["quote"]["source"]) in overview.QUOTES


def test_a_new_account_gets_a_welcome_without_the_model():
    store = FixtureStore(data={"users": [{"user_id": "new", "timezone": "America/Detroit"}], "events": [], "tasks": []})
    result = overview.daily_overview(ToolContext(store, "new", TUESDAY), FakeClient([]), "fake")
    assert result["headline"] == "Welcome to Steady!" and result["written_by"] == "code"


def test_yesterdays_suggestions_are_followed_up(ctx):
    ctx.store.save_overview("user-1", datetime(2026, 10, 5).date(), {"suggestions": [{"text": "Go to bed by 11."}]})
    client = FakeClient([reply(json.dumps(GOOD))])
    overview.daily_overview(ctx, client, "fake")
    assert "YESTERDAY'S OVERVIEW SUGGESTED: Go to bed by 11." in client.requests[0]["messages"][0]["content"]


def test_every_quote_has_a_source():
    assert len(overview.QUOTES) >= 15 and all(q and who for q, who in overview.QUOTES)


def test_the_overview_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    import ai.server

    monkeypatch.setattr(ai.server, "demo_store", FixtureStore())
    monkeypatch.setattr(ai.server, "STORE", "fixture")
    monkeypatch.setattr(ai.server, "llm", FakeClient([reply(json.dumps(GOOD)), reply(json.dumps({**GOOD, "headline": "Again."}))]))
    monkeypatch.setattr("ai.overview.log_call", lambda record, path=None: None)
    api = TestClient(ai.server.app)
    first = api.get("/overview").json()
    assert first["headline"] == "A solid Monday." and api.get("/overview").json() == first
    assert api.post("/overview/refresh").json()["headline"] == "Again."
