"""Can the agent turn a whole syllabus into suggestions by itself, over many tool calls?

The user sends a syllabus (its text, or page images) and asks for everything on the calendar. The
agent loop runs as in the app (up to MAX_ROUNDS rounds); afterwards the suggestions it created are
scored against fixtures/syllabi/truth.json like scripts/eval_syllabus.py does.

Designs:
    current  the app's four tools: every item needs its own propose_new_event call, and each one is a
             time block that must not overlap anything (two 11:59 PM deadlines on one day clash)
    batch    adds two prototype tools: propose_syllabus_items (all dated items in one call; deadlines
             don't block time) and propose_weekly_class (one recurring suggestion for a class)
    batch2   the same, with propose_syllabus_items fixed after the first tests: start_time/end_time
             fields, "7:00 PM" accepted, and rejections that say exactly what to resend
    import   one tool, import_syllabus(upload_id): the pipeline in src/ai/syllabus.py reads the file and
             creates the suggestions in code; the agent only decides to call it and tells the user

    uv run --with pymupdf scripts/syllabus_agent.py --model qwen3.5:9b --design batch --syllabus a_cse260.pdf
"""

import argparse
import base64
import importlib.util
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import openai

from ai import agent
from ai.llm import AI_DIR
from ai import syllabus
from ai.planning import parse_local, user_timezone
from ai.schedule import FixtureStore, ToolContext, ToolError

spec = importlib.util.spec_from_file_location("eval_syllabus", Path(__file__).parent / "eval_syllabus.py")
eval_syllabus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_syllabus)

QUESTION = "Here's my syllabus for next semester. Please put all my exams and due dates on my calendar."
LOG = AI_DIR / "logs" / "syllabus_agent.jsonl"
DAY_CODES = {"Mon": "MO", "Tue": "TU", "Wed": "WE", "Thu": "TH", "Fri": "FR", "Sat": "SA", "Sun": "SU"}

PROPOSE_SYLLABUS_ITEMS_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_syllabus_items",
        "description": (
            "Suggest adding many dated course items at once, e.g. everything from a syllabus. Assignments and "
            "quizzes become due dates (they don't block time); exams and presentations become events. Put ALL "
            "the items in one call. Nothing changes until the user accepts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object", "properties": {
                    "title": {"type": "string", "description": "e.g. 'CSE 260 Homework 3'"},
                    "kind": {"type": "string", "enum": ["assignment", "quiz", "exam", "project", "presentation", "other"]},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": ["string", "null"], "description": "due time or start time, HH:MM 24-hour"},
                    "end_time": {"type": ["string", "null"], "description": "end time for exams and events, HH:MM"},
                }, "required": ["title", "kind", "date"]}},
            },
            "required": ["items"],
        },
    },
}

PROPOSE_WEEKLY_CLASS_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_weekly_class",
        "description": "Suggest adding a class that repeats every week (lectures, labs) as one recurring event.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "e.g. 'CSE 260 Lecture'"},
                "days": {"type": "array", "items": {"type": "string", "enum": list(DAY_CODES)}},
                "start": {"type": "string", "description": "HH:MM 24-hour"},
                "end": {"type": "string", "description": "HH:MM 24-hour"},
                "first_day": {"type": "string", "description": "YYYY-MM-DD, first day of classes"},
                "last_day": {"type": "string", "description": "YYYY-MM-DD, last day of classes"},
                "skip_dates": {"type": "array", "items": {"type": "string"}, "description": "YYYY-MM-DD days without class"},
            },
            "required": ["name", "days", "start", "end", "first_day", "last_day"],
        },
    },
}


def propose_syllabus_items(ctx: ToolContext, items: list) -> dict:
    tz = user_timezone(ctx)
    if not isinstance(items, list) or not items:
        raise ToolError("items must be a non-empty list")
    existing = {(s["proposed_change"]["name"].lower(), s["proposed_change"]["start"][:10])
                for s in ctx.store.suggestions(ctx.user_id) if s["status"] == "PENDING"}
    created, problems = [], []
    for n, entry in enumerate(items, 1):
        try:
            title = str(entry.get("title") or "").strip()
            if not title:
                raise ToolError("title can't be empty")
            due = entry.get("time") or "23:59"
            start = parse_local(f"{entry.get('date')} {due}", "date/time", tz)
            end = parse_local(f"{entry['date']} {entry['end_time']}", "end_time", tz) if entry.get("end_time") else start
            if end < start:
                raise ToolError("end_time is before time")
            if start <= ctx.now:
                raise ToolError("that's already over")
            if (title.lower(), start.date().isoformat()) in existing:
                raise ToolError("already suggested")
        except (ToolError, KeyError, AttributeError, TypeError) as error:
            problems.append(f"item {n} ({entry.get('title') if isinstance(entry, dict) else entry}): {error}")
            continue
        kind = "deadline" if end == start else "event"
        suggestion = ctx.store.add_suggestion(ctx.user_id, {
            "type": "CREATE_EVENT", "target_id": None, "description": f"From your syllabus ({entry.get('kind')})",
            "proposed_change": {"name": title, "start": start.isoformat(), "end": end.isoformat(), "kind": kind},
            "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": start.isoformat(),
        })
        existing.add((title.lower(), start.date().isoformat()))
        created.append(suggestion["suggestion_id"])
    return {"created": len(created), "suggestion_ids": created, "problems": problems,
            "summary": f"Suggested {len(created)} items. Nothing changes until the user accepts them."
            + (f" {len(problems)} items were not added: " + "; ".join(problems) if problems else "")}


def propose_weekly_class(ctx: ToolContext, name: str, days: list, start: str, end: str, first_day: str,
                         last_day: str, skip_dates: list | None = None) -> dict:
    tz = user_timezone(ctx)
    if not days or any(d not in DAY_CODES for d in days):
        raise ToolError(f"days must be from {list(DAY_CODES)}")
    begin = parse_local(f"{first_day} {start}", "first_day/start", tz)
    finish = parse_local(f"{first_day} {end}", "end", tz)
    until = parse_local(f"{last_day} 23:59", "last_day", tz)
    if finish <= begin or until < begin:
        raise ToolError("end must be after start, and last_day after first_day")
    weekday = {code: i for i, code in enumerate(DAY_CODES)}
    first = next(begin.date() + timedelta(days=k) for k in range(7) if (begin.date() + timedelta(days=k)).weekday()
                 in {weekday[d] for d in days})
    rule = f"FREQ=WEEKLY;BYDAY={','.join(DAY_CODES[d] for d in days)};UNTIL={until:%Y%m%d}"
    suggestion = ctx.store.add_suggestion(ctx.user_id, {
        "type": "CREATE_EVENT", "target_id": None, "description": "Weekly class from your syllabus",
        "proposed_change": {"name": name, "start": datetime.combine(first, begin.timetz()).isoformat(),
                            "end": datetime.combine(first, finish.timetz()).isoformat(), "recurrence_rule": rule,
                            "days": days, "skip_dates": skip_dates or []},
        "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": until.isoformat(),
    })
    return {"suggestion_id": suggestion["suggestion_id"], "status": "PENDING",
            "summary": f"Suggested '{name}' every {', '.join(days)} {start}-{end}, {first_day} to {last_day}"
            + (f", skipping {len(skip_dates)} days" if skip_dates else "") + ". Nothing changes until the user accepts."}


# --- v2: the lessons from the first batch runs ---------------------------------------------------
# 1. "time" + "end_time" confused the model: it put an exam's 7:00-8:20 PM only into end_time.
#    v2 says start_time and end_time, and an event must have both.
# 2. Times like "7:00 PM" are accepted, as app code would.
# 3. When items are rejected, the result says exactly what to resend, because the model tended to
#    promise "I will correct those" and then stop.
PROPOSE_SYLLABUS_ITEMS_V2_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_syllabus_items",
        "description": (
            "Suggest adding many dated course items at once, e.g. everything from a syllabus. Put ALL the items "
            "in one call. Deadlines (homework, quizzes, papers due) need date and start_time = the due time. "
            "Events (exams, presentations, in-class quizzes) need date, start_time and end_time. "
            "Nothing changes until the user accepts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object", "properties": {
                    "title": {"type": "string", "description": "e.g. 'CSE 260 Homework 3'"},
                    "kind": {"type": "string", "enum": ["deadline", "event"]},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "HH:MM 24-hour: the due time, or when the event starts"},
                    "end_time": {"type": "string", "description": "HH:MM 24-hour, when the event ends (events only)"},
                }, "required": ["title", "kind", "date", "start_time"]}},
            },
            "required": ["items"],
        },
    },
}


def clock(value, name: str) -> str:
    """'7:00 PM' -> '19:00'; '19:00' stays."""
    import re

    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*$", str(value or ""))
    if not match:
        raise ToolError(f"{name} must look like 19:00, not {value!r}")
    hour = int(match.group(1))
    if match.group(3):
        hour = hour % 12 + (12 if match.group(3).lower() == "pm" else 0)
    return f"{hour:02d}:{match.group(2)}"


def propose_syllabus_items_v2(ctx: ToolContext, items: list) -> dict:
    tz = user_timezone(ctx)
    if not isinstance(items, list) or not items:
        raise ToolError("items must be a non-empty list")
    existing = {(s["proposed_change"]["name"].lower(), s["proposed_change"]["start"][:10])
                for s in ctx.store.suggestions(ctx.user_id) if s["status"] == "PENDING"}
    created, problems = [], []
    for entry in items:
        title = str(entry.get("title") or "?") if isinstance(entry, dict) else str(entry)
        try:
            if not isinstance(entry, dict) or not title.strip() or title == "?":
                raise ToolError("title is missing")
            start = parse_local(f"{entry.get('date')} {clock(entry.get('start_time'), 'start_time')}", "date", tz)
            end = start
            if entry.get("kind") == "event":
                if not entry.get("end_time"):
                    raise ToolError("an event needs end_time")
                end = parse_local(f"{entry['date']} {clock(entry['end_time'], 'end_time')}", "end_time", tz)
                if end <= start:
                    raise ToolError(f"end_time {entry['end_time']} isn't after start_time {entry['start_time']}")
            if start <= ctx.now:
                raise ToolError("that's already over")
            if (title.lower(), start.date().isoformat()) in existing:
                continue  # already suggested: skip quietly, so resending everything is harmless
        except ToolError as error:
            problems.append(f"'{title}': {error}")
            continue
        suggestion = ctx.store.add_suggestion(ctx.user_id, {
            "type": "CREATE_EVENT", "target_id": None, "description": "From your syllabus",
            "proposed_change": {"name": title.strip(), "start": start.isoformat(), "end": end.isoformat(),
                                "kind": "deadline" if end == start else "event"},
            "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": start.isoformat(),
        })
        existing.add((title.lower(), start.date().isoformat()))
        created.append(suggestion["suggestion_id"])
    summary = f"Suggested {len(created)} items. Nothing changes until the user accepts them."
    if problems:
        summary += (f" NOT ADDED YET ({len(problems)}): " + "; ".join(problems) + ". Fix these now: call "
                    "propose_syllabus_items again with only these items, corrected. Don't answer the user until "
                    "they're added or you've told the user why they can't be.")
    return {"created": len(created), "problems": problems, "summary": summary}


def as_answer(suggestions: list[dict]) -> dict:
    """The created suggestions in eval_syllabus's answer format, so they can be scored the same way."""
    items, meetings = [], []
    for s in suggestions:
        change = s["proposed_change"]
        if change.get("recurrence_rule"):
            meetings.append({"days": change["days"], "start": change["start"][11:16], "end": change["end"][11:16]})
        else:
            items.append({"title": change["name"], "date": change["start"][:10], "time": change["start"][11:16]})
    return {"items": items, "meetings": meetings}


def content_for(path: Path, route: str, design: str = "") -> str | list:
    if design == "import":  # the app stores the upload and only tells the model its id
        return f"{QUESTION}\n\n[The user attached a file: {path.name} (upload_id: u1)]"
    images, text = eval_syllabus.pages(path, dpi=150)
    if route == "text" and text.strip():
        return f"{QUESTION}\n\nSYLLABUS:\n{text}"
    mime = "image/png" if path.suffix.lower() == ".pdf" else "image/jpeg"
    return [{"type": "text", "text": QUESTION}] + [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(i).decode()}"}} for i in images]


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the agent on importing a whole syllabus.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--design", choices=["current", "batch", "batch2", "import"], default="current")
    parser.add_argument("--ocr", help="for --design import: an OCR model for scans and photos")
    parser.add_argument("--syllabus", default="a_cse260.pdf")
    parser.add_argument("--route", choices=["text", "vision"], default="text")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--no-think", action="store_true", help="turn thinking off (Ollama: reasoning_effort none)")
    args = parser.parse_args()

    if args.no_think:
        agent.EXTRA_SAMPLING = {**agent.EXTRA_SAMPLING, "reasoning_effort": "none"}
    # Ollama otherwise applies the model's chat default (1.5 for Qwen3.5), which fights repeated tool calls
    agent.SAMPLING = {**agent.SAMPLING, "presence_penalty": 0.0}

    if args.design == "batch":
        agent.TOOLS["propose_syllabus_items"] = (PROPOSE_SYLLABUS_ITEMS_TOOL, propose_syllabus_items)
        agent.TOOLS["propose_weekly_class"] = (PROPOSE_WEEKLY_CLASS_TOOL, propose_weekly_class)
    elif args.design == "batch2":
        agent.TOOLS["propose_syllabus_items"] = (PROPOSE_SYLLABUS_ITEMS_V2_TOOL, propose_syllabus_items_v2)
        agent.TOOLS["propose_weekly_class"] = (PROPOSE_WEEKLY_CLASS_TOOL, propose_weekly_class)
    ctx = ToolContext(store=FixtureStore(), user_id="user-1",
                      now=datetime(2026, 12, 15, 10, 0, tzinfo=ZoneInfo("America/Detroit")))
    client = openai.OpenAI(base_url=args.base_url, api_key="ollama", timeout=3600)
    if args.design == "import":
        reader = syllabus.Reader.for_server(client, args.model, ocr_model=args.ocr)
        upload = eval_syllabus.FIXTURES / args.syllabus

        def import_tool(ctx: ToolContext, upload_id: str) -> dict:
            if upload_id != "u1":
                raise ToolError(f"there's no upload {upload_id!r}; the user's file is u1")
            return syllabus.import_syllabus(ctx, reader, upload.read_bytes(), upload.name)

        agent.TOOLS["import_syllabus"] = (syllabus.IMPORT_SYLLABUS_TOOL, import_tool)
    truth = json.loads((eval_syllabus.FIXTURES / "truth.json").read_text())[args.syllabus]

    started = time.perf_counter()
    result = agent.run_agent(client, args.model, ctx, content_for(eval_syllabus.FIXTURES / args.syllabus, args.route, args.design),
                             verbose=True, log_path=LOG)
    seconds = round(time.perf_counter() - started)
    suggestions = ctx.store.suggestions(ctx.user_id)
    s = eval_syllabus.score(truth, as_answer(suggestions))
    calls = [c["function"]["name"] for m in result["messages"] if m["role"] == "assistant" for c in m.get("tool_calls") or []]
    errors = sum(1 for m in result["messages"] if m["role"] == "tool" and m["content"].startswith("Error"))
    print(f"\n{args.model}{' no-think' if args.no_think else ''} {args.design} {args.syllabus} ({args.route}): found {s['found']}/{s['items']} items, "
          f"made up {s['made_up']}, times {s['right_time']}/{s['timed']}, weekly classes {s['meetings_right']}/{s['meetings']}; "
          f"{len(calls)} tool calls in {result['rounds']} rounds ({errors} errors), {result['tokens']} tokens, {seconds}s"
          + ("  [hit the round limit]" if result["rounds"] == agent.MAX_ROUNDS and result["answer"].startswith("Sorry") else ""))
    print("tool calls:", ", ".join(calls))
    if s["missed"]:
        print("missed:", ", ".join(s["missed"]))
    if s["extra"]:
        print("made up:", ", ".join(s["extra"]))
    print("answer:", result["answer"][:400])
    out = AI_DIR / "evals" / f"{datetime.now():%Y-%m-%d-%H%M}-syllabus-agent-{args.model.replace(':', '_')}-{args.design}-{Path(args.syllabus).stem}.json"
    out.write_text(json.dumps({"args": vars(args), "score": s, "rounds": result["rounds"], "tool_calls": calls,
                               "errors": errors, "tokens": result["tokens"], "seconds": seconds,
                               "answer": result["answer"], "suggestions": suggestions}, indent=2, default=str))


if __name__ == "__main__":
    main()
