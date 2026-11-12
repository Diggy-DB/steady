"""Export every eval case in plain English, for people to check by eye (the review page reads this).

Writes <out>/data.json (the hand-written and generated planning cases, every student week, the
syllabus answer keys, and optionally the latest model results) and <out>/syllabi/*.jpg (every page of
every test syllabus, as pictures). Run again after changing cases or getting new results.

    uv run scripts/export_eval_review.py --out out/review \
        --planning-results evals/<run>.jsonl ... --syllabus-results evals/<run>.json
"""

import argparse
import io
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from ai import syllabus
from ai.eval_generated import GEN_WEEKS, GENERATED_CASES
from ai.eval_suite import CASES, WEEKS, play
from ai.evals import clock_text
from ai.llm import AI_DIR

FIXTURES = AI_DIR / "fixtures" / "syllabi"
WEEK_NOTES = {
    "alex": "Oct 5-11, 2026, Detroit. The original test week: lectures, a work shift (stored in UTC), gym, study sessions.",
    "maya": "Oct 12-18, 2026, Chicago. Packed: two lectures MWF, a library job, a lab, soccer, an evening midterm. Little free time.",
    "chris": "Nov 23-29, 2026, Los Angeles. Thanksgiving week: light, flights home and back, a holiday dinner.",
    "riley": "Mar 8-14, 2027, New York. Clocks spring forward Sunday 2 AM; an overnight shift Sat 10 PM - Sun 6 AM is 7 real hours.",
    "priya": "Dec 7-13, 2026, Kolkata (UTC+5:30). Finals week: two exams, six identical 'Study session's.",
}
SYLLABUS_NOTES = {
    "a_cse260.pdf": "Digital PDF, 3 pages. Schedule table with dates like 1/22; the 11:59 PM rule is on page 1.",
    "b_bs161.pdf": "Digital PDF, 3 pages. Dates inside paragraphs; ten quiz dates in one sentence; distractors (drop dates, office hours).",
    "c_mth234_photo.jpg": "Phone photo of a dense one-page schedule: tilted, shadowed, slightly blurry.",
    "d_phy183_scan.pdf": "Scanned PDF (pictures only, no text), 2 pages, crooked.",
    "a_cse260_scan.pdf": "The CSE 260 syllabus, scanned.",
    "b_bs161_scan.pdf": "The BS 161 syllabus, scanned.",
    "c_mth234_scan.pdf": "The MTH 234 page, scanned.",
    "d_phy183_photo.jpg": "Phone photo of the PHY 183 first page.",
    "e_hst201_fall.pdf": "Fall 2027. Thanksgiving break, December finals; dates like 'Sept. 17'.",
    "e_cse335_fall.pdf": "Fall 2027. Weekly labs due Sundays, projects, a table; no lab on Thanksgiving Friday.",
    "e_stt231_summer.pdf": "Six-week summer session, Mon-Thu; Memorial Day off.",
    "e_iss215_online.pdf": "Online summer course: NO class meetings (a made-up weekly class counts as a mistake).",
    "e_psy101_formats.pdf": "Date formats: '29 January', 'Monday, February 15th', 'the 24th of February'; 'noon', '11:59pm'.",
    "e_ece230_formats.pdf": "ISO dates (2027-01-22), 1/29/2027, 24-hour times.",
    "e_mth132_weeks.pdf": "A week-of table: 'HW 3 (Wed)' means Wednesday of that week; the date must be worked out.",
    "e_phl130_relative.pdf": "Only relative dates: 'Friday of Week 4'; spring break after Week 8 shifts later weeks.",
    "e_anth101_distractors.pdf": "Distractors: an old revision date, a drop deadline, office hours, a holiday, TBA items (not in the key).",
    "e_acc201_every.pdf": "'Quizzes every Friday from January 15 through April 23, except spring break': the dates aren't listed.",
    "e_bs162_long.pdf": "7 pages: policies first, then a daily schedule table split across pages.",
    "e_cem251_long.pdf": "6 pages: deadlines scattered through long policy text.",
    "e_phy231_meetings.pdf": "Three meeting types: lecture, recitation and lab.",
    "v_mth234_sideways.jpg": "The MTH 234 photo, rotated sideways.",
    "v_phy183_lowres.jpg": "The PHY 183 photo at low resolution (650 px).",
    "v_mth234_dark.jpg": "The MTH 234 photo, dark and low contrast.",
    "v_phy183_cropped.jpg": "The PHY 183 photo with the edges cut off.",
    "v_phy183_two_pages.jpg": "Both PHY 183 pages in one photo.",
}


def local(iso: str, tz: ZoneInfo) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(tz)


def span(start: datetime, end: datetime) -> str:
    first = clock_text(start.strftime("%H:%M"))
    last = clock_text(end.strftime("%H:%M"))
    if end.date() != start.date():
        last += f" ({end:%a})"
    return f"{first} - {last}"


def day_text(d: date) -> str:
    return f"{d:%a %b} {d.day}"


def week_note(name: str, data: dict) -> str:
    if name in WEEK_NOTES:
        return WEEK_NOTES[name]
    tz = ZoneInfo(data["users"][0]["timezone"])
    first = min(local(e["start"], tz) for e in data["events"]).date()
    return (f"Generated week, {day_text(first)} - {day_text(first + timedelta(days=6))}, {first.year}, {tz.key}. "
            "Lectures, a lab, a job or rehearsal, and changeable activities; one task is already completed.")


def week_view(name: str, data: dict) -> dict:
    tz = ZoneInfo(data["users"][0]["timezone"])
    mine = sorted((e for e in data["events"] if e["user_id"] == "user-1"), key=lambda e: local(e["start"], tz))
    days = {}
    for e in mine:
        start, end = local(e["start"], tz), local(e["end"], tz)
        days.setdefault(start.date(), []).append({"id": e["event_id"], "name": e["name"], "time": span(start, end),
                                                   "changeable": e["changeable"]})
    others = [f"{e['name']}, {day_text(local(e['start'], tz).date())} {span(local(e['start'], tz), local(e['end'], tz))}"
              for e in data["events"] if e["user_id"] != "user-1"]
    first = min(days)
    return {
        "student": data["users"][0]["first_name"], "timezone": tz.key, "note": week_note(name, data),
        "generated": name not in WEEK_NOTES,
        "days": [{"date": day_text(first + timedelta(days=k)), "events": days.get(first + timedelta(days=k), [])}
                 for k in range(7)],
        "tasks": [{"name": t["name"], "due": day_text(date.fromisoformat(t["due"])), "status": t["status"],
                   "work": t["description"]} for t in data["tasks"] if t["user_id"] == "user-1"],
        "others": others,
    }


def names_for(text: str, data: dict) -> str:
    """'e2' -> 'e2 (Study session, Mon 7:00 PM)' so reviewers needn't look ids up."""
    tz = ZoneInfo(data["users"][0]["timezone"])
    events = {e["event_id"]: e for e in data["events"]}

    def named(match):
        e = events.get(match.group(0))
        if not e:
            return match.group(0)
        start = local(e["start"], tz)
        owner = "" if e["user_id"] == "user-1" else ", ANOTHER user's"
        return f"{match.group(0)} ({e['name']}, {start:%a} {clock_text(start.strftime('%H:%M'))}{owner})"

    if not events:
        return text
    # The week's own ids (longest first): "e2", but also generated ones like "g1e13", which a short pattern missed,
    # so reviewers saw a bare "g1e13" and couldn't tell it was the Swim.
    ids = sorted(events, key=len, reverse=True)
    return re.sub(r"\b(?:" + "|".join(map(re.escape, ids)) + r")\b", named, text)


def step_text(step, data: dict) -> str:
    name, args = step
    if name == "get_schedule":
        a, b = date.fromisoformat(args["start_date"]), date.fromisoformat(args["end_date"])
        return f"Looks up the calendar: {day_text(a)}" + (f" to {day_text(b)}" if b != a else "")
    if name == "find_free_slots":
        a, b = date.fromisoformat(args["start_date"]), date.fromisoformat(args["end_date"])
        return f"Searches free time ({args['minutes']}+ min): {day_text(a)}" + (f" to {day_text(b)}" if b != a else "")
    if name == "propose_new_event":
        s, e = datetime.fromisoformat(args["start"]), datetime.fromisoformat(args["end"])
        return f"Suggests a new event '{args['name']}': {day_text(s.date())}, {span(s, e)}"
    if name == "propose_move_event":
        s, e = datetime.fromisoformat(args["new_start"]), datetime.fromisoformat(args["new_end"])
        return names_for(f"Suggests moving {args['event_id']} to {day_text(s.date())}, {span(s, e)}", data)
    return f"{name}({json.dumps(args)})"


def planning(results: dict) -> list[dict]:
    cases = []
    for c in CASES + GENERATED_CASES:
        s, data = c.scenario, c.scenario.data
        now = datetime.fromisoformat(s.now)
        all_weeks = {**WEEKS, **GEN_WEEKS}
        week = getattr(s, "week", None) or next(n for n, w in WEEKS.items() if w["users"][0]["first_name"] == data["users"][0]["first_name"])
        wrong = []
        for steps in c.wrong:
            t = play(s, steps)
            caught = [problem for check in s.checks if (problem := check(t))]
            wrong.append({"steps": [step_text(x, data) for x in steps[:-1]], "answer": steps[-1],
                          "caught_by": [names_for(x, data) for x in caught]})
        cases.append({
            "id": s.name, "category": s.category, "week": week, "now": f"{day_text(now.date())}, {clock_text(now.strftime('%H:%M'))}",
            "question": s.question, "checks": [names_for(getattr(ch, "text", "?"), data) for ch in s.checks],
            "reference": {"steps": [step_text(x, data) for x in c.reference[:-1]], "answer": c.reference[-1]},
            "wrong": wrong, "doing_nothing_is_right": c.lazy_passes,
            "custom_data": data is not all_weeks[week], "set": "generated" if s.name.startswith("gen/") else "core",
            "runs": results.get(s.name, []),
        })
    return cases


def planning_results(paths: list[Path]) -> tuple[dict, list[str]]:
    """Every saved run per case (later files win for a case), with what the checks said."""
    by_case, sources = {}, []
    for path in paths:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for name in {r["scenario"] for r in rows}:
            by_case[name] = [{"passed": r["passed"], "failures": r["failures"], "answer": r["answer"][:500],
                              "suggestions": [suggestion_text(x) for x in r["suggestions"]], "seconds": r["seconds"]}
                             for r in rows if r["scenario"] == name]
        if rows:
            sources.append(f"{rows[0]['model']}{' (' + rows[0]['label'] + ')' if rows[0].get('label') else ''}: {path.name}")
    return by_case, sources


def suggestion_text(s: dict) -> str:
    change = s["proposed_change"]
    if s["type"].startswith("DELETE_"):
        return f"delete {change['what']} {change['id']}" + (f" ('{change['name']}')" if change.get("name") else "")
    if s["type"] == "ADD_JOURNAL":
        return f"journal for {change['date']}: \"{change['text'][:120]}\""
    start, end = datetime.fromisoformat(change["start"]), datetime.fromisoformat(change["end"])
    what = f"move {s['target_id']}" if s["type"] == "MOVE_EVENT" else f"new '{change.get('name', '')}'"
    return f"{what}: {day_text(start.date())}, {span(start, end)}"


def syllabus_results(path: Path | None) -> tuple[dict, str]:
    if not path:
        return {}, ""
    d = json.loads(path.read_text())
    by_file = {}
    for r in d["results"]:
        by_file.setdefault(r["file"], []).append({k: r.get(k) for k in (
            "found", "items", "made_up", "meetings_right", "meetings", "meetings_made_up", "right_time", "timed",
            "missed", "extra", "read_as", "seconds")})
    return by_file, f"{d['label']}: {path.name}"


def syllabus_pages(name: str, out: Path) -> list[str]:
    raw = (FIXTURES / name).read_bytes()
    images = [Image.open(io.BytesIO(p.image)) for p in syllabus.load_pages(raw, name)]
    paths = []
    for i, image in enumerate(images, 1):
        image = image.convert("RGB")
        image.thumbnail((1100, 1400))
        path = f"syllabi/{Path(name).stem}_p{i}.jpg"
        image.save(out / path, quality=72)
        paths.append(path)
    return paths


def syllabi(out: Path, results: dict) -> list[dict]:
    (out / "syllabi").mkdir(parents=True, exist_ok=True)
    truth = json.loads((FIXTURES / "truth.json").read_text())
    result = []
    for name, t in truth.items():
        items = []
        for i in sorted(t["items"], key=lambda i: (i["date"], i["time"] or "")):
            d = date.fromisoformat(i["date"])
            time = clock_text(i["time"]) if i["time"] else "no time"
            if i.get("end_time"):
                time += f" - {clock_text(i['end_time'])}"
            items.append({"title": i["title"], "kind": i["kind"], "date": f"{day_text(d)}, {d.year}", "time": time,
                          "worked_out": bool(i.get("derived"))})
        result.append({
            "file": name, "category": t.get("category", ""), "note": SYLLABUS_NOTES.get(name, ""), "course": t["course"],
            "term": f"{day_text(date.fromisoformat(t['term_start']))} - {day_text(date.fromisoformat(t['term_end']))}, "
                    f"{date.fromisoformat(t['term_end']).year}",
            "meetings": [f"{m['kind']}: {', '.join(m['days'])} {clock_text(m['start'])} - {clock_text(m['end'])}" for m in t["meetings"]],
            "items": items, "pages": syllabus_pages(name, out), "runs": results.get(name, []),
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the eval cases for review by eye.")
    parser.add_argument("--out", type=Path, default=AI_DIR / "out" / "review")
    parser.add_argument("--planning-results", type=Path, nargs="*", default=[], help="run_evals.py results (.jsonl)")
    parser.add_argument("--syllabus-results", type=Path, help="eval_syllabus_import.py results (.json)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    plan_runs, plan_sources = planning_results(args.planning_results)
    syl_runs, syl_source = syllabus_results(args.syllabus_results)
    data = {"generated": f"{datetime.now():%Y-%m-%d %H:%M}",
            "results": {"planning": plan_sources, "syllabi": syl_source},
            "weeks": {name: week_view(name, w) for name, w in {**WEEKS, **GEN_WEEKS}.items()},
            "planning": planning(plan_runs), "syllabi": syllabi(args.out, syl_runs)}
    (args.out / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    pages = sum(len(s["pages"]) for s in data["syllabi"])
    print(f"{len(data['planning'])} planning cases ({sum(bool(c['runs']) for c in data['planning'])} with results), "
          f"{len(data['weeks'])} weeks, {len(data['syllabi'])} syllabi "
          f"({pages} page images) -> {args.out}")


if __name__ == "__main__":
    main()
