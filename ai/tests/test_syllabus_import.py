"""Tests for src/ai/syllabus.py: the code that turns a syllabus into suggestions. A fake client plays the
model, so these test what code does with the model's (sometimes wrong) answers."""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ai import syllabus
from ai.schedule import FixtureStore, ToolContext, ToolError
from test_agent import FakeClient, reply

FIXTURES = Path(__file__).parents[1] / "fixtures" / "syllabi"
NOW = datetime(2026, 12, 15, 10, 0, tzinfo=ZoneInfo("America/Detroit"))
TEXT = "CSE 260 Spring 2027. Lectures Tue/Thu 12:40-2:00 PM. HW 1 (Fri 1/22) due 11:59 PM. MIDTERM 1 in class (Thu 2/18)."


def answer(**overrides) -> dict:
    data = {"course": "CSE 260: Discrete Structures", "term": "Spring 2027", "term_start": "2027-01-11",
            "term_end": "2027-04-30",
            "meetings": [{"kind": "lecture", "days": ["Tue", "Thu"], "start": "12:40 PM", "end": "2:00 PM"}],
            "no_class": [{"start": "2027-03-08", "end": "2027-03-12", "reason": "spring break"}],
            "items": [{"title": "Homework 1", "kind": "assignment", "date": "2027-01-22", "time": "11:59 PM"},
                      {"title": "Midterm Exam 1", "kind": "exam", "date": "2027-02-18", "time": "12:40 PM", "end_time": "2:00 PM"}]}
    return {**data, **overrides}


def item(checked, title) -> dict:
    return next(i for i in checked.items if title in i["title"])


def test_a_good_answer_passes_unchanged():
    checked = syllabus.check(answer(), NOW, TEXT)
    hw, exam = item(checked, "Homework 1"), item(checked, "Midterm")
    assert (hw["title"], hw["kind"], hw["start"].strftime("%Y-%m-%d %H:%M")) == ("CSE 260 Homework 1", "deadline", "2027-01-22 23:59")
    assert (exam["kind"], exam["start"].hour, exam["end"].strftime("%H:%M")) == ("event", 12, "14:00")
    assert not checked.dropped and not hw["notes"] and not exam["notes"]


def test_wrong_year_is_set_to_the_semesters():
    # the 4B read a photo's dates as 2026, so everything was "already over"
    data = answer(items=[{"title": "WebWork 1", "kind": "assignment", "date": "2026-01-19", "time": "11:59 PM"}])
    checked = syllabus.check(data, NOW, "MTH 234 Spring 2027 Schedule ... WW1 Tue 1/19")
    assert item(checked, "WebWork 1")["start"].date() == date(2027, 1, 19)
    assert any("2027" in n for n in checked.notes)


def test_without_any_year_a_past_date_moves_to_next_year():
    data = answer(term=None, term_start=None, term_end=None, course="Physics",
                  items=[{"title": "PS 1", "kind": "assignment", "date": "2026-01-20", "time": "11:30 AM"}])
    assert item(syllabus.check(data, NOW, None), "PS 1")["start"].date() == date(2027, 1, 20)


def test_eleven_fifty_nine_without_pm_becomes_pm():
    data = answer(items=[{"title": "HW 1", "kind": "assignment", "date": "2027-01-22", "time": "11:59"}])
    assert item(syllabus.check(data, NOW, TEXT), "HW 1")["start"].strftime("%H:%M") == "23:59"  # the text says PM
    assert item(syllabus.check(data, NOW, None), "HW 1")["start"].strftime("%H:%M") == "23:59"  # a photo: assumed


def test_an_exam_without_times_gets_the_class_time():
    data = answer(items=[{"title": "Midterm 1", "kind": "exam", "date": "2027-02-18", "time": None}])
    exam = item(syllabus.check(data, NOW, TEXT), "Midterm 1")
    assert (exam["start"].strftime("%H:%M"), exam["end"].strftime("%H:%M")) == ("12:40", "14:00")
    assert "class schedule" in exam["notes"][0]


def test_an_exam_with_only_a_start_gets_a_guessed_end():
    data = answer(items=[{"title": "Final Exam", "kind": "exam", "date": "2027-05-04", "time": "10:00 AM"}])
    final = item(syllabus.check(data, NOW, "Final 5/4"), "Final")
    assert final["end"].strftime("%H:%M") == "12:00" and "guessed" in final["notes"][0]


def test_twelve_hour_end_without_pm_is_fixed():
    data = answer(items=[{"title": "Final Exam", "kind": "exam", "date": "2027-05-05", "time": "12:45", "end_time": "2:45"}])
    assert item(syllabus.check(data, NOW, "5/5"), "Final")["end"].strftime("%H:%M") == "14:45"


def test_impossible_past_and_duplicate_items_are_left_out():
    data = answer(items=[{"title": "Quiz", "kind": "quiz", "date": "2027-02-29", "time": "9:00 AM"},
                         {"title": "HW 0", "kind": "assignment", "date": "2026-12-01", "time": "11:59 PM"},
                         {"title": "HW 1", "kind": "assignment", "date": "2027-01-22", "time": "11:59 PM"},
                         {"title": "HW 1", "kind": "assignment", "date": "2027-01-22", "time": "11:59 PM"}])
    checked = syllabus.check(data, NOW, "1/22")
    assert [i["title"] for i in checked.items] == ["CSE 260 HW 1"]
    assert any("isn't a real date" in d for d in checked.dropped)


def test_dates_missing_from_the_text_are_flagged_not_dropped():
    data = answer(items=[{"title": "HW 9", "kind": "assignment", "date": "2027-04-09", "time": "11:59 PM"}])
    hw = item(syllabus.check(data, NOW, TEXT), "HW 9")
    assert "please check" in hw["notes"][0]


def test_weekly_class_skips_the_break():
    checked = syllabus.check(answer(), NOW, TEXT)
    lecture = checked.meetings[0]
    assert lecture["name"] == "CSE 260 Lecture" and lecture["skip_dates"] == ["2027-03-09", "2027-03-11"]


def test_suggestions_are_created_for_items_and_classes():
    ctx = ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)
    ids = syllabus.suggest(ctx, syllabus.check(answer(), NOW, TEXT))
    changes = [s["proposed_change"] for s in ctx.store.suggestions("user-1")]
    assert len(ids) == 3
    assert changes[2]["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20270430"
    assert changes[2]["start"].startswith("2027-01-12T12:40")  # the first Tuesday


def test_digital_pdf_is_read_as_text():
    pages = syllabus.load_pages((FIXTURES / "a_cse260.pdf").read_bytes(), "a_cse260.pdf")
    assert len(pages) == 3 and syllabus.has_text(pages) and "MIDTERM 1" in pages[2].text


def test_scans_and_photos_are_read_as_images():
    scan = syllabus.load_pages((FIXTURES / "d_phy183_scan.pdf").read_bytes(), "d_phy183_scan.pdf")
    photo = syllabus.load_pages((FIXTURES / "c_mth234_photo.jpg").read_bytes(), "c_mth234_photo.jpg")
    assert not syllabus.has_text(scan) and not syllabus.has_text(photo) and photo[0].mime == "image/jpeg"


def test_import_runs_the_whole_pipeline():
    client = FakeClient([reply("Here it is:\n```json\n" + json.dumps(answer()) + "\n```")])
    ctx = ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)
    result = syllabus.import_syllabus(ctx, syllabus.Reader(client, "fake"), (FIXTURES / "a_cse260.pdf").read_bytes(), "a.pdf")
    assert result["read_as"] == "text" and len(result["suggestion_ids"]) == 3
    assert "MIDTERM 1" in client.requests[0]["messages"][0]["content"][0]["text"]  # the text layer went to the model
    assert result["items"][1] == "CSE 260 Midterm Exam 1 (Thu Feb 18, 12:40 PM-2:00 PM)"


def test_photos_go_to_the_ocr_model_first_when_there_is_one():
    client = FakeClient([reply("MTH 234 Spring 2027 ... WW1 Tue 1/19"), reply(json.dumps(answer()))])
    ctx = ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)
    reader = syllabus.Reader(client, "reader", ocr_model="ocr")
    result = syllabus.import_syllabus(ctx, reader, (FIXTURES / "c_mth234_photo.jpg").read_bytes(), "c.jpg")
    assert [r["model"] for r in client.requests] == ["ocr", "reader"] and result["read_as"] == "ocr"


def test_an_unreadable_answer_is_a_tool_error():
    ctx = ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)
    with pytest.raises(ToolError, match="couldn't read"):
        syllabus.import_syllabus(ctx, syllabus.Reader(FakeClient([reply("Sorry, I can't.")]), "fake"),
                                 (FIXTURES / "c_mth234_photo.jpg").read_bytes(), "c.jpg")


def test_reader_settings_match_the_server():
    ollama = syllabus.Reader.for_server(type("C", (), {"base_url": "http://localhost:11434/v1"})(), "m")
    vllm = syllabus.Reader.for_server(type("C", (), {"base_url": "https://pod-8000.proxy.runpod.net/v1"})(), "m")
    assert ollama.extra_body["reasoning_effort"] == "none"
    assert vllm.extra_body["chat_template_kwargs"] == {"enable_thinking": False}


def test_a_quiz_without_a_time_on_a_class_day_is_held_in_class():
    data = answer(meetings=[{"kind": "recitation", "days": ["Wed"], "start": "3:00 PM", "end": "3:50 PM"}],
                  items=[{"title": "Quiz 1", "kind": "quiz", "date": "2027-02-03", "time": None},
                         {"title": "Online quiz", "kind": "quiz", "date": "2027-02-07", "time": None}])
    checked = syllabus.check(data, NOW, "Quiz 1 in recitation (Wed 2/3), online quiz 2/7")
    assert item(checked, "Quiz 1")["start"].strftime("%H:%M") == "15:00" and item(checked, "Quiz 1")["kind"] == "event"
    assert item(checked, "Online quiz")["start"].strftime("%H:%M") == "23:59"  # a Sunday: no class, so a deadline


def test_a_series_is_numbered_by_code():
    data = answer(items=[{"title": "Online quiz", "kind": "quiz", "dates": ["2027-01-17", "2027-01-24", "2027-01-31"],
                          "time": "11:59 PM"}])
    checked = syllabus.check(data, NOW, "quizzes due January 17, January 24, January 31")
    assert [(i["title"], i["start"].day) for i in checked.items] == [
        ("CSE 260 Online quiz 1", 17), ("CSE 260 Online quiz 2", 24), ("CSE 260 Online quiz 3", 31)]


def test_dates_in_the_text_that_were_not_imported_are_reported():
    text = "Spring 2027. Quizzes due January 17, January 24 and 1/31. Break March 8-12. Drop deadline Feb. 3."
    data = answer(items=[{"title": "Quiz 1", "kind": "quiz", "date": "2027-01-17", "time": "11:59 PM"}],
                  no_class=[{"start": "2027-03-08", "end": "2027-03-12"}])
    checked = syllabus.check(data, NOW, text)
    assert syllabus.not_imported(text, data, checked, NOW) == ["Sun Jan 24", "Sun Jan 31", "Wed Feb 3"]


def test_a_series_named_after_its_first_item_is_renumbered():
    raw = [{"title": "Online quiz 1", "kind": "quiz", "dates": ["2027-01-17", "2027-01-24"], "time": "11:59 PM"},
           {"title": "Final", "kind": "exam", "dates": ["2027-05-03"], "time": "7:45 AM", "end_time": "9:45 AM"}]
    assert [(i["title"], i["date"]) for i in syllabus.expand_series(raw)] == [
        ("Online quiz 1", "2027-01-17"), ("Online quiz 2", "2027-01-24"), ("Final", "2027-05-03")]


@pytest.mark.parametrize("written", ["2/18", "02/18/2027", "2027-02-18", "February 18", "Feb. 18th", "18 February",
                                     "the 18th of February", "Feb 18"])
def test_dates_are_recognized_however_they_are_written(written):
    assert syllabus.mentions_date(f"Exam on {written}.", date(2027, 2, 18))
    assert date(2027, 2, 18) in syllabus.dates_in_text(f"Exam on {written}.", (date(2027, 1, 1), date(2027, 6, 30)))


def test_a_different_date_is_not_recognized():
    assert not syllabus.mentions_date("Exam on 2/19 and February 28.", date(2027, 2, 18))
