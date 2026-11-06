"""Proof that the syllabus answer key (fixtures/syllabi/truth.json) is right, without a model.

- every date is a real date inside its semester, every time a real time, every exam ends after it starts;
- in digital PDFs, every date in the key is written in the document (in some format);
- dates the document only implies ("Friday of Week 4", "every Friday") fall on the weekday it implies;
- photos and scans have the same key as the digital syllabus they were made from.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from ai import syllabus

FIXTURES = Path(__file__).parents[1] / "fixtures" / "syllabi"
TRUTH = json.loads((FIXTURES / "truth.json").read_text())
DIGITAL = [name for name in TRUTH if name.endswith(".pdf")
           and syllabus.has_text(syllabus.load_pages((FIXTURES / name).read_bytes(), name))]


def test_the_test_set_is_big_enough():
    assert len(TRUTH) >= 26 and sum(len(t["items"]) for t in TRUTH.values()) >= 300
    categories = [t.get("category") for t in TRUTH.values()]
    for category in ("fall", "formats", "relative", "distractors", "long", "hard photos"):
        assert sum(category in (c or "") for c in categories) >= 2, category


@pytest.mark.parametrize("name", sorted(TRUTH))
def test_dates_and_times_are_possible(name):
    t = TRUTH[name]
    first, last = date.fromisoformat(t["term_start"]), date.fromisoformat(t["term_end"])
    for i in t["items"]:
        day = date.fromisoformat(i["date"])
        assert first - timedelta(days=7) <= day <= last + timedelta(days=10), (name, i)  # finals come after classes
        for key in ("time", "end_time"):
            if i.get(key):
                datetime.strptime(i[key], "%H:%M")
        if i.get("end_time"):
            assert i["end_time"] > i["time"], (name, i)
    for m in t["meetings"]:
        assert set(m["days"]) <= set(syllabus.DAYS) and m["end"] > m["start"]


@pytest.mark.parametrize("name", DIGITAL)
def test_every_written_date_is_in_the_document(name):
    text = "\n".join(p.text for p in syllabus.load_pages((FIXTURES / name).read_bytes(), name))
    missing = [i["title"] for i in TRUTH[name]["items"]
               if not i.get("derived") and not syllabus.mentions_date(text, date.fromisoformat(i["date"]))]
    assert not missing, f"in the key but not in {name}: {missing}"


def test_implied_dates_fall_on_the_weekday_the_document_implies():
    derived = [(name, i) for name, t in TRUTH.items() for i in t["items"] if i.get("derived")]
    assert len(derived) >= 30
    for name, i in derived:
        assert date.fromisoformat(i["date"]).strftime("%a") == i["derived"], (name, i)


def test_photos_and_scans_have_their_sources_key():
    pairs = {"a_cse260_scan.pdf": "a_cse260.pdf", "b_bs161_scan.pdf": "b_bs161.pdf", "c_mth234_scan.pdf": "c_mth234_photo.jpg",
             "d_phy183_photo.jpg": "d_phy183_scan.pdf", "v_mth234_dark.jpg": "c_mth234_photo.jpg",
             "v_phy183_two_pages.jpg": "d_phy183_scan.pdf"}
    for copy, source in pairs.items():
        assert TRUTH[copy]["items"] == TRUTH[source]["items"], copy
