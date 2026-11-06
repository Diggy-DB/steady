"""Tests for the synthetic training tasks, especially that they stay apart from the eval set."""

from collections import Counter
from datetime import date, datetime

from ai.eval_generated import GEN_WEEKS, GENERATED
from ai.eval_suite import SUITE, WEEKS
from ai.evals import SCENARIOS
from ai.schedule import overlaps
from ai.synth import make_task

TASKS = [make_task(seed) for seed in range(200)]


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
        events = [(datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])) for e in task.data["events"]]
        for i, a in enumerate(events):
            for b in events[i + 1 :]:
                assert not overlaps(*a, *b), task.name


def test_all_task_types_show_up():
    kinds = Counter(t.name.rsplit("-", 1)[0] for t in TASKS)
    assert set(kinds) == {"look_up", "move_flexible", "move_fixed", "task_time", "activity_today", "weekly_goal"}
    assert min(kinds.values()) >= 10  # no type is starved
