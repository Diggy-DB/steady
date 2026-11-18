"""Tests for the synthetic training tasks, especially that they stay apart from the eval set."""

from collections import Counter
from datetime import date, datetime

from ai.eval_generated import GEN_WEEKS, GENERATED
from ai.eval_suite import SUITE, WEEKS
from ai.evals import SCENARIOS
from ai.schedule import overlaps
from ai.synth import make_task

TASKS = [make_task(seed) for seed in range(300)]


def test_same_seed_gives_the_same_task():
    a, b = make_task(7), make_task(7)
    assert (a.question, a.now, a.data) == (b.question, b.now, b.data)


def test_never_uses_an_eval_week():
    # every day that has an event in any of the five eval weeks, plus the days around them
    eval_days = {date.fromisoformat(e["start"][:10]) for week in [*WEEKS.values(), *GEN_WEEKS.values()] for e in week["events"]}
    for task in TASKS:
        days = {date.fromisoformat(e["start"][:10]) for e in task.data["events"]}
        assert not days & eval_days, task.name


def test_never_asks_an_eval_question():
    eval_questions = {s.question.lower() for s in [*SCENARIOS, *SUITE, *GENERATED]}
    assert not {t.question.lower() for t in TASKS} & eval_questions


def test_generated_weeks_have_no_overlapping_events():
    for task in TASKS:
        events = [(datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])) for e in task.data["events"]
                  if e["user_id"] == "student"]  # another person's event (missing_event) may overlap
        for i, a in enumerate(events):
            for b in events[i + 1 :]:
                assert not overlaps(*a, *b), task.name


def test_all_task_types_show_up():
    kinds = Counter(t.name.rsplit("-", 1)[0] for t in TASKS)
    assert set(kinds) == {"look_up", "move_flexible", "move_fixed", "task_time", "activity_today", "weekly_goal", "multi_goal",
                          "delete_event", "delete_task", "delete_fixed", "journal_add", "journal_edit", "new_task", "next_week",
                          "conflict", "not_enough", "missing_event", "time_over"}
    assert min(kinds.values()) >= 5  # no type is starved


def test_every_task_forbids_unasked_deletes_and_journal_entries():
    for task in TASKS:
        described = [c.text for c in task.checks]
        if task.category != "delete":
            assert "suggests deleting nothing" in described, task.name
        if task.category != "journal":
            assert "suggests no journal entry" in described, task.name
        assert any("finish" in d for d in described), task.name


def test_next_week_is_asked_the_week_before():
    for task in TASKS:
        if task.name.startswith("next_week"):
            monday = date.fromisoformat(task.data["events"][0]["start"][:10])
            asked = date.fromisoformat(task.now[:10])
            assert 2 <= (monday - asked).days <= 6, task.name


def test_journal_edit_has_an_entry_to_edit():
    for task in TASKS:
        if task.name.startswith("journal_edit"):
            (entry,) = task.data["journals"]
            assert entry["date"] < task.now[:10]



def first(kind: str, where=lambda t: True):
    return next(t for t in TASKS if t.name.startswith(kind + "-") and where(t))


def passes(task, answer: str, suggestions=()) -> list[str]:
    from ai.evals import Transcript
    t = Transcript(answer=answer, tool_calls=[], suggestions=list(suggestions), rounds=2, gave_up=False)
    return [p for check in task.checks if (p := check(t))]


def test_new_round_2_types_reward_saying_no():
    tight = first("not_enough")
    assert passes(tight, "Only about 3 hours are free today, so it won't all fit. I suggest the longest block.") == []
    assert passes(tight, "Sure, I planned all of it for you.") != []

    missing = first("missing_event", lambda t: "event x" not in t.question)
    assert passes(missing, "I don't see that on your calendar this week.") == []
    assert passes(missing, "Done, I suggest moving it.") != []

    foreign = first("missing_event", lambda t: "event x" in t.question)
    other = next(e for e in foreign.data["events"] if e["user_id"] != "student")
    assert passes(foreign, f"I couldn't find an event called {other['event_id']} on your calendar.") == []
    moved = {"type": "MOVE_EVENT", "target_id": other["event_id"], "proposed_change": {"start": other["start"], "end": other["end"]}}
    assert passes(foreign, "I couldn't find it.", [moved]) != []  # touching someone else's event fails

    tonight = first("time_over", lambda t: "tonight" in t.question)
    assert passes(tonight, "It's already 11:20 PM, so your day is mostly over; maybe plan reading for another night.") == []
    assert passes(tonight, "Sure, you have plenty of time tonight!") != []

    over = first("time_over", lambda t: "tonight" not in t.question)
    assert passes(over, "That time has already passed today. Want a later time?") == []
    assert passes(over, "Done, it's on your calendar.") != []


def test_round_2_weights_favor_the_weak_types():
    kinds = Counter(t.name.rsplit("-", 1)[0] for t in TASKS)
    assert kinds["multi_goal"] > kinds["look_up"] and kinds["missing_event"] > kinds["move_flexible"]
