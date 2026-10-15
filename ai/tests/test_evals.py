"""Tests for the eval checks and runner. No real model: hand-made transcripts and the fake client."""

import pytest

from ai.evals import Scenario, Transcript, asks_question, calls, either, moves, new_events_named, run_scenario
from test_agent import FakeClient, reply  # reuse the fake model from the agent tests


def transcript(answer: str = "", tool_calls: list | None = None, suggestions: list | None = None) -> Transcript:
    return Transcript(answer=answer, tool_calls=tool_calls or [], suggestions=suggestions or [], rounds=2)


def new_event(name: str, start: str, end: str) -> dict:
    return {"type": "CREATE_EVENT", "target_id": None, "proposed_change": {"name": name, "start": start, "end": end}}


def test_calls():
    check = calls("get_schedule")
    assert check(transcript(tool_calls=[{"name": "get_schedule"}])) is None
    assert check(transcript()) == "never called get_schedule"


def test_moves_checks_target_and_time():
    move = {"type": "MOVE_EVENT", "target_id": "e2", "proposed_change": {"start": "2026-10-05T20:00:00-04:00"}}
    assert moves("e2", to="20:00")(transcript(suggestions=[move])) is None
    assert moves("e2", to="21:00")(transcript(suggestions=[move])) is not None


def test_either_passes_if_one_passes():
    check = either(moves("e2"), asks_question())
    assert check(transcript(answer="Which study session do you mean?")) is None
    assert check(transcript(answer="Done.")) is not None


def test_new_events_named_counts_and_adds_minutes():
    events = [
        new_event("Gym", "2026-10-07T12:00:00-04:00", "2026-10-07T13:00:00-04:00"),
        new_event("Work on MTH 133", "2026-10-07T16:00:00-04:00", "2026-10-07T18:00:00-04:00"),
        new_event("MTH 133 again", "2026-10-08T08:00:00-04:00", "2026-10-08T09:00:00-04:00"),
    ]
    assert new_events_named(("gym",), count=1)(transcript(suggestions=events)) is None
    assert new_events_named(("mth",), minutes=180)(transcript(suggestions=events)) is None
    assert new_events_named(("mth",), minutes=240)(transcript(suggestions=events)) == (
        "180 minutes of new 'mth' events, wanted at least 240"
    )


@pytest.fixture(autouse=True)
def no_logging(monkeypatch):
    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: None)


def test_run_scenario_scores_a_run():
    scenario = Scenario("tomorrow", "What do I have tomorrow?", [calls("get_schedule")])
    tuesday = {"start_date": "2026-10-06", "end_date": "2026-10-06"}

    good = FakeClient([reply(tool_calls=[("get_schedule", tuesday)]), reply("Work 1-5, gym 6-7.")])
    result = run_scenario(good, "fake", scenario)
    assert result["passed"] and result["tools"] == ["get_schedule"] and result["rounds"] == 2

    lazy = FakeClient([reply("Probably nothing.")])  # answers without looking
    result = run_scenario(lazy, "fake", scenario)
    assert not result["passed"] and result["failures"] == ["never called get_schedule"]
