"""Tests for the syllabus experiments: the scorer (scripts/eval_syllabus.py) and the prototype import
tools (scripts/syllabus_agent.py). No model needed."""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ai.agent import TOOLS, run_tool
from ai.schedule import FixtureStore, ToolContext

SCRIPTS = Path(__file__).parents[1] / "scripts"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "syllabi"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


eval_syllabus = load("eval_syllabus")
syllabus_agent = load("syllabus_agent")
TRUTH = json.loads((FIXTURES / "truth.json").read_text())


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setitem(TOOLS, "propose_syllabus_items",
                        (syllabus_agent.PROPOSE_SYLLABUS_ITEMS_V2_TOOL, syllabus_agent.propose_syllabus_items_v2))
    monkeypatch.setitem(TOOLS, "propose_weekly_class",
                        (syllabus_agent.PROPOSE_WEEKLY_CLASS_TOOL, syllabus_agent.propose_weekly_class))
    return ToolContext(store=FixtureStore(), user_id="user-1",
                       now=datetime(2026, 12, 15, 10, 0, tzinfo=ZoneInfo("America/Detroit")))


@pytest.mark.parametrize("name", list(TRUTH))
def test_the_answer_key_scores_perfectly(name):
    truth = TRUTH[name]
    s = eval_syllabus.score(truth, {"items": truth["items"], "meetings": truth["meetings"]})
    assert (s["found"], s["made_up"], s["right_time"], s["meetings_right"]) == (
        s["items"], 0, s["timed"], s["meetings"])


def test_items_match_by_date_number_and_kind_of_item():
    webwork_3 = TRUTH["c_mth234_photo.jpg"]["items"][2]
    assert eval_syllabus.same_item(webwork_3, {"title": "MTH 234 Homework 3", "date": "2027-02-02T23:59"})
    assert not eval_syllabus.same_item(webwork_3, {"title": "MTH 234 Homework 4", "date": "2027-02-02"})
    assert not eval_syllabus.same_item(webwork_3, {"title": "WebWork 3", "date": "2027-02-03"})


def test_times_are_read_like_app_code_would():
    values = ["9:10", "9:10 AM", "12:45 PM", "12:05 AM", "7:00 PM", "23:59:00", None]
    assert [eval_syllabus.hhmm(v) for v in values] == ["09:10", "09:10", "12:45", "00:05", "19:00", "23:59", None]


def test_json_is_found_in_fences_and_copied_schema_shapes():
    assert eval_syllabus.parse_json('Here:\n```json\n{"items": [1]}\n```') == {"items": [1]}
    assert eval_syllabus.parse_json('{"type": "object", "properties": {"items": []}}') == {"items": []}


def test_batch_tool_adds_everything_in_one_call(ctx):
    items = [{"title": "HW 1", "kind": "deadline", "date": "2027-01-19", "start_time": "11:59 PM"},
             {"title": "Exam 1", "kind": "event", "date": "2027-02-11", "start_time": "7:00 PM", "end_time": "8:20 PM"}]
    result = json.loads(run_tool(ctx, "propose_syllabus_items", json.dumps({"items": items})))
    assert result["created"] == 2 and not result["problems"]
    changes = [s["proposed_change"] for s in ctx.store.suggestions("user-1")]
    assert changes[0]["start"].startswith("2027-01-19T23:59") and changes[0]["kind"] == "deadline"
    assert changes[1]["start"].startswith("2027-02-11T19:00") and changes[1]["end"].startswith("2027-02-11T20:20")


def test_rejected_items_say_what_to_resend_and_resending_skips_duplicates(ctx):
    items = [{"title": "HW 1", "kind": "deadline", "date": "2027-01-19", "start_time": "23:59"},
             {"title": "Exam 1", "kind": "event", "date": "2027-02-11", "start_time": "19:00"}]
    first = json.loads(run_tool(ctx, "propose_syllabus_items", json.dumps({"items": items})))
    assert first["created"] == 1 and "Exam 1" in first["summary"] and "call propose_syllabus_items again" in first["summary"]
    items[1]["end_time"] = "20:20"
    second = json.loads(run_tool(ctx, "propose_syllabus_items", json.dumps({"items": items})))
    assert second["created"] == 1 and len(ctx.store.suggestions("user-1")) == 2  # HW 1 wasn't added twice


def test_items_already_over_are_refused(ctx):
    old = [{"title": "Old quiz", "kind": "deadline", "date": "2026-01-19", "start_time": "23:59"}]
    result = json.loads(run_tool(ctx, "propose_syllabus_items", json.dumps({"items": old})))
    assert result["created"] == 0 and "already over" in result["summary"]


def test_weekly_class_becomes_one_recurring_suggestion(ctx):
    args = {"name": "CSE 260 Lecture", "days": ["Tue", "Thu"], "start": "12:40", "end": "14:00",
            "first_day": "2027-01-11", "last_day": "2027-04-30", "skip_dates": ["2027-03-09", "2027-03-11"]}
    run_tool(ctx, "propose_weekly_class", json.dumps(args))
    change = ctx.store.suggestions("user-1")[0]["proposed_change"]
    assert change["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20270430"
    assert change["start"].startswith("2027-01-12T12:40")  # the first Tuesday, not Monday the 11th


def test_plural_titles_match():
    quiz_3 = TRUTH["b_bs161.pdf"]["items"][2]  # Online Quiz 3
    assert eval_syllabus.same_item(quiz_3, {"title": "BS 161 Online quizzes (weekly) 3", "date": "2027-01-31"})


def test_a_right_date_with_a_different_numbering_still_counts():
    truth = TRUTH["e_anth101_distractors.pdf"]
    guess = [{"title": f"Field notes (Week {w})", "kind": "assignment", "date": i["date"], "time": i["time"]}
             for w, i in zip((1, 4, 8, 11), [x for x in truth["items"] if x["title"].startswith("Field")])]
    s = eval_syllabus.score(truth, {"items": guess, "meetings": []})
    assert s["found"] == 4 and s["made_up"] == 0


def test_numbers_still_decide_between_two_items_on_one_day():
    truth = {"items": [{"title": "Quiz 1", "kind": "quiz", "date": "2027-02-03", "time": None},
                       {"title": "Quiz 2", "kind": "quiz", "date": "2027-02-03", "time": "15:00"}], "meetings": []}
    guess = [{"title": "Quiz 2", "kind": "quiz", "date": "2027-02-03", "time": "15:00"},
             {"title": "Quiz 1", "kind": "quiz", "date": "2027-02-03", "time": None}]
    s = eval_syllabus.score(truth, {"items": guess, "meetings": []})
    assert s["found"] == 2 and s["right_time"] == 1


@pytest.mark.parametrize("truth_title,guess_title", [
    ("Discussion post 1", "ISS 215 Week 1 discussion post"), ("Discussion replies 2", "Replies to classmates 2"),
    ("Project 2", "CSE 335 Project 2"), ("Essay 1", "PSY 101 Essay 1"), ("Reflection journal 3", "Journal 3"),
    ("Field notes 1", "ANTH 101 Field notes (Week 1)"), ("PS3", "Problem Set 3"), ("Lab 4", "Lab exercise 4")])
def test_any_meaningful_shared_word_matches(truth_title, guess_title):
    assert eval_syllabus.same_item({"title": truth_title, "kind": "assignment", "date": "2027-05-19"},
                                   {"title": guess_title, "date": "2027-05-19"})


def test_course_codes_and_numbering_words_alone_dont_match():
    assert not eval_syllabus.same_item({"title": "Discussion post 1", "kind": "assignment", "date": "2027-05-19"},
                                       {"title": "ISS 215 Week 1", "date": "2027-05-19"})
