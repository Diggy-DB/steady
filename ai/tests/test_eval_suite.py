"""Proof that every eval case is valid, without a model.

For each case:
- its REFERENCE answer (tool calls + final text) runs through the real tools without errors and passes
  every check: the case is solvable, and the checks accept a right answer;
- every WRONG answer fails at least one check: the checks catch that mistake;
- doing nothing ("Sure, done!") fails, except where that is a fine answer (e.g. "thanks").
A failure here means the CASE is broken, not the model.
"""

import json
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ai.agent import run_tool
from ai.eval_generated import GEN_WEEKS, GENERATED_CASES
from ai.eval_suite import CASES as CORE_CASES, CATEGORIES, SUITE, WEEKS, play

CASES = CORE_CASES + GENERATED_CASES  # the 57 hand-written cases and the generated ones
from ai.evals import Transcript
from ai.schedule import FixtureStore, ToolContext, overlaps


def run_steps(scenario, steps) -> Transcript:
    return play(scenario, steps)


def failures(scenario, transcript) -> list[str]:
    return [problem for check in scenario.checks if (problem := check(transcript))]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.scenario.name)
def test_the_reference_answer_is_possible_and_passes(case):
    transcript = run_steps(case.scenario, case.reference)
    errors = [c["result"] for c in transcript.tool_calls if c["result"].startswith("Error")]
    assert not errors, f"the reference's tool calls failed: {errors}"
    assert not failures(case.scenario, transcript)


WRONG = [(c, i) for c in CASES for i in range(len(c.wrong))]


@pytest.mark.parametrize("case,i", WRONG, ids=[f"{c.scenario.name}-wrong{i}" for c, i in WRONG])
def test_each_wrong_answer_is_caught(case, i):
    assert failures(case.scenario, run_steps(case.scenario, case.wrong[i])), "a wrong answer passed every check"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.scenario.name)
def test_doing_nothing_fails_unless_that_is_right(case):
    lazy = run_steps(case.scenario, ["Sure, done!"])
    assert bool(failures(case.scenario, lazy)) != case.lazy_passes


def test_every_category_has_several_cases():
    per_category = Counter(s.category for s in SUITE)
    assert set(per_category) == set(CATEGORIES)
    assert min(per_category.values()) >= 2, per_category
    assert len(SUITE) >= 45


def test_with_the_generated_cases_every_category_has_at_least_ten():
    per_category = Counter(c.scenario.category for c in CASES)
    assert set(per_category) == set(CATEGORIES) and min(per_category.values()) >= 10, per_category
    assert len(CASES) >= 240


def test_most_cases_have_a_known_wrong_answer():
    assert sum(1 for c in CASES if c.wrong) >= 0.9 * len([c for c in CASES if not c.lazy_passes])


def test_names_and_questions_are_unique():
    scenarios = [c.scenario for c in CASES]
    assert len({s.name for s in scenarios}) == len(scenarios)
    assert len({(s.question, s.now, id(s.data)) for s in scenarios}) == len(scenarios)


ALL_WEEKS = {**WEEKS, **GEN_WEEKS}


@pytest.mark.parametrize("week", sorted(ALL_WEEKS))
def test_eval_weeks_are_consistent(week):
    data = ALL_WEEKS[week]
    for user in data["users"]:
        ZoneInfo(user["timezone"])  # a real time zone
        mine = [(datetime.fromisoformat(e["start"].replace("Z", "+00:00")), datetime.fromisoformat(e["end"].replace("Z", "+00:00")))
                for e in data["events"] if e["user_id"] == user["user_id"]]
        assert all(end > start for start, end in mine)
        for i, a in enumerate(mine):
            for b in mine[i + 1 :]:
                assert not overlaps(*a, *b), f"{week}: two of {user['user_id']}'s events overlap"
    assert len({e["event_id"] for e in data["events"]}) == len(data["events"])


def test_the_night_shift_really_is_7_hours():
    # Riley's shift crosses the switch to daylight saving time: 10 PM to 6 AM is 7 real hours
    shift = next(e for e in WEEKS["riley"]["events"] if e["name"].startswith("Night shift"))
    start, end = (datetime.fromisoformat(shift[k].replace("Z", "+00:00")) for k in ("start", "end"))
    assert (end - start).total_seconds() == 7 * 3600


def test_wilson_range_and_sign_test():
    import importlib.util
    from pathlib import Path

    def load(name):
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    low, high = load("run_evals").wilson(10, 12)
    assert round(low, 2) == 0.55 and round(high, 2) == 0.95  # 10/12 could really be anywhere from 55% to 95%
    sign_test = load("compare_evals").sign_test
    assert round(sign_test(6, 0), 3) == 0.031  # 6 fixed, 0 broken: unlikely to be luck
    assert sign_test(8, 2) > 0.05  # 8 fixed, 2 broken: could still be luck
