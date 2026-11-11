"""Eval scenarios, and the checks that score each run.

These scenarios are the TEST SET. Never train on them (or on their logs), or
the pass rate stops meaning anything. That's why eval runs log to
logs/evals.jsonl instead of logs/calls.jsonl.

A check is a function that looks at one run and returns None if it passed,
or a short message saying what went wrong.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

import openai

from ai.agent import MAX_ROUNDS, run_agent
from ai.llm import AI_DIR
from ai.schedule import FixtureStore, ToolContext

EVAL_LOG = AI_DIR / "logs" / "evals.jsonl"


@dataclass
class Transcript:
    """Everything one run produced, in the shape the checks need."""

    answer: str
    tool_calls: list[dict]  # each: {"name", "arguments", "result"}
    suggestions: list[dict]  # PENDING suggestions left in the store
    rounds: int
    gave_up: bool = False  # ran out of rounds without answering


Check = Callable[[Transcript], str | None]


def described(check: Check, text: str) -> Check:
    """Attach a plain-English description (shown on the review page for people checking the cases)."""
    check.text = text
    return check


def when_text(moment: datetime) -> str:
    """For people: midnight deadlines read as "the end of" the day before."""
    from datetime import timedelta

    if (moment.hour, moment.minute) == (0, 0):
        day = moment - timedelta(days=1)
        return f"the end of {day:%a %b} {day.day}"
    return f"{moment:%a %b} {moment.day} {clock_text(moment.strftime('%H:%M'))}"


def day_text(iso_day: str) -> str:
    """'2026-10-05' -> 'Mon Oct 5'."""
    day = datetime.fromisoformat(iso_day)
    return f"{day:%a %b} {day.day}"


def clock_text(hhmm: str) -> str:
    hour, minute = int(hhmm[:2]), hhmm[3:]
    return f"{hour % 12 or 12}:{minute} {'AM' if hour < 12 else 'PM'}"


@dataclass
class Scenario:
    name: str
    question: str
    checks: list[Check]
    now: str = "2026-10-05 18:30"  # fake local time, so every run faces the same situation
    user_id: str = "user-1"
    data: dict | None = None  # a different week than fixtures/week.json
    category: str = ""


# ---- Checks. Each function builds and returns a check. ----


def calls(tool: str) -> Check:
    def check(t: Transcript) -> str | None:
        return None if any(c["name"] == tool for c in t.tool_calls) else f"never called {tool}"

    return described(check, f"calls {tool}")


def finishes() -> Check:
    # Before Nov 6 this tested rounds >= MAX_ROUNDS, which also failed runs that answered in the last round.
    def check(t: Transcript) -> str | None:
        if t.gave_up:
            return "gave up after the maximum number of rounds"
        return None if t.answer.strip() else "empty answer"

    return described(check, "finishes with an answer (doesn't give up)")


def proposes_nothing() -> Check:
    def check(t: Transcript) -> str | None:
        return None if not t.suggestions else f"made {len(t.suggestions)} proposal(s)"

    return described(check, "creates no suggestions")


def proposes_at_least(n: int) -> Check:
    def check(t: Transcript) -> str | None:
        return None if len(t.suggestions) >= n else f"made {len(t.suggestions)} proposal(s), wanted at least {n}"

    return described(check, f"creates at least {n} suggestion(s)")


def moves(event_id: str, to: str | None = None, day: str | None = None, minutes: int | None = None,
          after: datetime | None = None) -> Check:
    """A MOVE_EVENT suggestion for event_id: optionally starting at `to` ("HH:MM"), on `day` ("YYYY-MM-DD"),
    lasting `minutes` (the event's own length, unless the user asked to change it), and/or starting after `after`."""

    def check(t: Transcript) -> str | None:
        for s in t.suggestions:
            if s["type"] == "MOVE_EVENT" and s["target_id"] == event_id:
                start = datetime.fromisoformat(s["proposed_change"]["start"])
                if to is not None and s["proposed_change"]["start"][11:16] != to:
                    continue
                if day is not None and s["proposed_change"]["start"][:10] != day:
                    continue
                if minutes is not None and (
                        datetime.fromisoformat(s["proposed_change"]["end"]) - start).total_seconds() // 60 != minutes:
                    continue
                if after is not None and start < after:
                    continue
                return None
        wanted = " ".join(filter(None, [f"to {to}" if to else "", f"on {day}" if day else "",
                                        f"for {minutes} min" if minutes else "", f"after {after:%a %H:%M}" if after else ""]))
        return f"no suggestion moving {event_id} {wanted}".strip()

    return described(check, "suggests moving " + event_id + "".join(
        [f" to start at {clock_text(to)}" if to else "", f" on {day_text(day)}" if day else "",
         f", keeping it {minutes} minutes long" if minutes else "", f", starting after {when_text(after)}" if after else ""]))


def changed_event(s: dict) -> str | None:
    """The event a suggestion changes: a move's target, or a deleted event (deletes name it in proposed_change)."""
    if s["type"] == "DELETE_EVENT":
        return s["proposed_change"]["id"]
    return s["target_id"]


def never_touches(*event_ids: str) -> Check:
    def check(t: Transcript) -> str | None:
        touched = [changed_event(s) for s in t.suggestions if changed_event(s) in event_ids]
        return f"suggested changing {', '.join(touched)}" if touched else None

    return described(check, f"never suggests changing or deleting {', '.join(event_ids)}")


DELETES = {"event": "DELETE_EVENT", "task": "DELETE_TASK", "journal": "DELETE_JOURNAL"}


def deletes(what: str, item_id: str) -> Check:
    """Suggests deleting exactly this one thing, and nothing else (`item_id` is a journal entry's date)."""

    def check(t: Transcript) -> str | None:
        deleted = [(s["proposed_change"]["what"], s["proposed_change"]["id"]) for s in t.suggestions
                   if s["type"] in DELETES.values()]
        if (what, item_id) not in deleted:
            return f"no suggestion deleting {what} {item_id}"
        others = [f"{w} {i}" for w, i in deleted if (w, i) != (what, item_id)]
        return f"also suggested deleting {', '.join(others)}" if others else None

    return described(check, f"suggests deleting {what} {item_id}, and nothing else")


def deletes_nothing() -> Check:
    def check(t: Transcript) -> str | None:
        deleted = [f"{s['proposed_change']['what']} {s['proposed_change']['id']}" for s in t.suggestions
                   if s["type"] in DELETES.values()]
        return f"suggested deleting {', '.join(deleted)}" if deleted else None

    return described(check, "suggests deleting nothing")


def journals(day: str, *words: str) -> Check:
    """A journal suggestion for `day` (YYYY-MM-DD) whose text has every one of `words`."""

    def check(t: Transcript) -> str | None:
        notes = [s["proposed_change"] for s in t.suggestions if s["type"] == "ADD_JOURNAL"]
        if not notes:
            return "no journal suggestion"
        for n in notes:
            missing = [w for w in words if w not in n["text"].lower()]
            if n["date"] == day and not missing:
                return None
        return f"no journal suggestion for {day} saying {', '.join(words)}"

    return described(check, f"suggests a journal entry for {day_text(day)} that mentions {', '.join(words)}")


def edits_journal(day: str, has: tuple[str, ...] = (), lacks: tuple[str, ...] = ()) -> Check:
    """An edit of `day`'s journal entry whose new text has every phrase in `has` (e.g. the parts the user didn't
    ask to change) and none in `lacks` (what they asked to change)."""

    def check(t: Transcript) -> str | None:
        edits = [s["proposed_change"] for s in t.suggestions if s["type"] == "EDIT_JOURNAL" and s["proposed_change"]["date"] == day]
        if not edits:
            return f"no edit of the journal entry for {day}"
        for e in edits:
            new = e["text"].lower()
            if all(h in new for h in has) and not any(x in new for x in lacks):
                return None
        return f"the edited entry doesn't have {list(has)} without {list(lacks)}: {edits[-1]['text'][:120]!r}"

    return described(check, f"suggests an edit of {day_text(day)}'s journal that keeps {', '.join(has)}"
                            + (f" and no longer says {', '.join(lacks)}" if lacks else ""))


def writes_no_journal() -> Check:
    def check(t: Transcript) -> str | None:
        notes = [s for s in t.suggestions if s["type"] in ("ADD_JOURNAL", "EDIT_JOURNAL")]
        return f"suggested {len(notes)} journal entr{'y' if len(notes) == 1 else 'ies'}" if notes else None

    return described(check, "suggests no journal entry")


# The categories where deleting or journaling is the point; everywhere else, doing either is a mistake.
def unasked_changes(category: str) -> list[Check]:
    return ([] if category == "delete" else [deletes_nothing()]) + ([] if category == "journal" else [writes_no_journal()])


def new_events_named(words: tuple[str, ...], count: int | None = None, minutes: int | None = None,
                     each_minutes: int | None = None, before: datetime | None = None,
                     distinct_days: bool = False, not_on: tuple[str, ...] = ()) -> Check:
    """New-event suggestions whose name contains any of `words`: exactly `count` of them, and/or `minutes` in
    total; each `each_minutes` long; all ending by `before` (a deadline); on different days; not on `not_on` days."""

    def check(t: Transcript) -> str | None:
        found = [
            s
            for s in t.suggestions
            if s["type"] == "CREATE_EVENT" and any(w in s["proposed_change"]["name"].lower() for w in words)
        ]
        spans = [(datetime.fromisoformat(s["proposed_change"]["start"]), datetime.fromisoformat(s["proposed_change"]["end"]))
                 for s in found]
        total = sum((end - start).total_seconds() // 60 for start, end in spans)
        if count is not None and len(found) != count:
            return f"{len(found)} new '{words[0]}' event(s), wanted {count}"
        if minutes is not None and total < minutes:
            return f"{int(total)} minutes of new '{words[0]}' events, wanted at least {minutes}"
        if each_minutes is not None and any((end - start).total_seconds() // 60 != each_minutes for start, end in spans):
            return f"a new '{words[0]}' event isn't {each_minutes} minutes long"
        if before is not None and any(end > before for _, end in spans):
            return f"a new '{words[0]}' event ends after {before:%a %b %d %H:%M} (the deadline)"
        days = [start.date().isoformat() for start, _ in spans]
        if distinct_days and len(set(days)) != len(days):
            return f"two new '{words[0]}' events on the same day"
        if any(d in not_on for d in days):
            return f"a new '{words[0]}' event on a day that already has one"
        return None

    return described(check, f"new events named like {' / '.join(words)}: " + "; ".join(filter(None, [
        f"exactly {count}" if count is not None else "", f"at least {minutes} minutes in total" if minutes else "",
        f"each {each_minutes} minutes" if each_minutes else "", f"all done by {when_text(before)}" if before else "",
        "on different days" if distinct_days else "", f"none on {', '.join(not_on)} (that day already has one)" if not_on else ""])))


def changes_within(start: datetime, end: datetime) -> Check:
    """Every suggestion (new or moved) starts at or after `start` and ends by `end`, e.g. "tonight"."""

    def check(t: Transcript) -> str | None:
        for s in t.suggestions:
            if s["type"] not in ("CREATE_EVENT", "MOVE_EVENT"):  # deletes and journal notes have no time
                continue
            begin, finish = (datetime.fromisoformat(s["proposed_change"][k]) for k in ("start", "end"))
            if begin < start or finish > end:
                return f"suggested {s['proposed_change']['name']} at {begin:%a %H:%M}, outside {start:%a %H:%M}-{end:%a %H:%M}"
        return None

    return described(check, f"every suggestion is between {when_text(start)} and {when_text(end)}")


def no_moves() -> Check:
    def check(t: Transcript) -> str | None:
        moved = [s["target_id"] for s in t.suggestions if s["type"] == "MOVE_EVENT"]
        return f"suggested moving {', '.join(moved)}" if moved else None

    return described(check, "suggests moving nothing")


def no_tool_calls() -> Check:
    def check(t: Transcript) -> str | None:
        return None if not t.tool_calls else f"called {', '.join(c['name'] for c in t.tool_calls)}"

    return described(check, "uses no tools")


def uses_freed_time() -> Check:
    """A new event that depends on a move (it takes the time the move frees)."""

    def check(t: Transcript) -> str | None:
        ok = any(s["type"] == "CREATE_EVENT" and s.get("depends_on") for s in t.suggestions)
        return None if ok else "no new event uses the time freed by the move"

    return described(check, "a new event takes the time the move frees (depends on the move)")


def time_words(hhmm: str) -> list[str]:
    """Ways an answer can write a time: 13:00 -> '1 pm', '1:00 pm', '1-5', '13:00' ..."""
    hour, minute = int(hhmm[:2]), hhmm[3:]
    h12 = hour % 12 or 12
    clock = f"{h12}" if minute == "00" else f"{h12}:{minute}"
    return [rf"\b{h12}:{minute}\b", rf"\b{hour:02d}:{minute}\b", rf"\b{hour}:{minute}\b",
            rf"\b{clock}\s*(am|pm|a\.m\.|p\.m\.)", rf"\b{clock}\s*(-|–|to)\s*\d"]


def mentions_event(word: str, hhmm: str) -> Check:
    """The answer names the event (`word`) and its start time, in any common format."""

    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        if word not in answer:
            return f"answer doesn't mention {word!r}"
        if not any(re.search(p, answer) for p in time_words(hhmm)):
            return f"answer doesn't give {word!r}'s time ({hhmm})"
        return None

    return described(check, f"the answer names {word!r} with its time, {clock_text(hhmm)}")


def asks_which(*options: str) -> Check:
    """A clarifying question: the answer asks something AND names at least two of the options.
    (Any "?" used to count, so "Anything else?" passed as a clarifying question.)"""

    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        named = [o for o in options if o in answer]
        return None if "?" in answer and len(named) >= 2 else "didn't ask which one (with the options)"

    return described(check, f"asks which one, naming at least two of: {', '.join(options)}")


def mentions_any(*words: str) -> Check:
    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        return None if any(w in answer for w in words) else f"answer mentions none of {list(words)}"

    return described(check, f"the answer says one of: {' | '.join(words)}")


def mentions_all(*words: str) -> Check:
    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        missing = [w for w in words if w not in answer]
        return f"answer doesn't mention {missing}" if missing else None

    return described(check, f"the answer mentions all of: {', '.join(words)}")


def avoids(*phrases: str) -> Check:
    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        found = [p for p in phrases if p in answer]
        return f"answer says {found}" if found else None

    return described(check, f"the answer never says: {' | '.join(phrases)}")


def asks_question() -> Check:
    def check(t: Transcript) -> str | None:
        return None if "?" in t.answer else "didn't ask a question"

    return check


def either(*checks: Check) -> Check:
    """Passes if at least one of the checks passes."""

    def check(t: Transcript) -> str | None:
        problems = [c(t) for c in checks]
        return None if None in problems else " and ".join(problems)

    return described(check, " OR ".join(f"({getattr(c, 'text', '?')})" for c in checks))


# ---- The scenarios. All at Monday Oct 5, 6:30 PM unless they say otherwise. ----

SCENARIOS = [
    Scenario(
        "tomorrow",
        "What do I have tomorrow?",
        [calls("get_schedule"), mentions_all("work", "gym"), proposes_nothing(), finishes()],
    ),
    Scenario(
        "move_study_session",
        "Move my study session to 8 PM.",
        # Tonight's session (e2) is the natural reading; asking which one is fine too.
        [either(moves("e2", to="20:00"), asks_question()), never_touches("e6", "e10"), finishes()],
    ),
    Scenario(
        "fixed_lecture",
        "Move my CSE 232 lecture to Thursday afternoon.",
        [proposes_nothing(), mentions_any("fixed", "can't", "cannot", "not able"), finishes()],
    ),
    Scenario(
        "due_tonight",
        "I have a 3-hour assignment due tonight. When should I work on it?",
        [proposes_at_least(1), avoids("earlier today", "this morning", "this afternoon"), finishes()],
    ),
    Scenario(
        "week_plan",
        "This week I want to go to the gym 3 times for an hour and finish my two assignments. Make me a schedule.",
        [
            new_events_named(("gym",), count=2),  # Tuesday already has one
            new_events_named(("mth", "math", "problem set"), minutes=180),
            new_events_named(("cse", "project"), minutes=180),
            finishes(),
        ],
    ),
    Scenario(
        "gym_today",
        "When can I go to the gym today?",
        [calls("find_free_slots"), avoids("8 am", "8:00 am", "8:30 am"), finishes()],
        now="2026-10-07 09:00",  # Wednesday morning
    ),
]


# ---- Running one scenario ----


def tool_calls_from(messages: list[dict]) -> list[dict]:
    """Pair every tool call in the conversation with the result the model got back."""
    results = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    return [
        {"name": call["function"]["name"], "arguments": call["function"]["arguments"], "result": results.get(call["id"], "")}
        for m in messages
        for call in m.get("tool_calls") or []
    ]


def run_scenario(client: openai.OpenAI, model: str, scenario: Scenario, log_path: Path = EVAL_LOG) -> dict:
    """Run one scenario once, with a fresh store, and score it."""
    store = FixtureStore(data=scenario.data) if scenario.data else FixtureStore()
    timezone = ZoneInfo(store.user(scenario.user_id)["timezone"])
    now = datetime.fromisoformat(scenario.now).replace(tzinfo=timezone)
    ctx = ToolContext(store, scenario.user_id, now)
    result = run_agent(client, model, ctx, scenario.question, verbose=False, log_path=log_path)

    transcript = Transcript(
        answer=result["answer"],
        tool_calls=tool_calls_from(result["messages"]),
        suggestions=store.suggestions(scenario.user_id, status="PENDING"),
        rounds=result["rounds"],
        gave_up=result["rounds"] >= MAX_ROUNDS and result["answer"].startswith("Sorry, I couldn't finish"),
    )
    failures = [problem for check in scenario.checks if (problem := check(transcript))]
    return {
        "scenario": scenario.name,
        "question": scenario.question,
        "category": scenario.category,
        "passed": not failures,
        "failures": failures,
        "tokens": result["tokens"],
        "seconds": result["seconds"],
        "rounds": result["rounds"],
        "tools": [c["name"] for c in transcript.tool_calls],
        "suggestions": transcript.suggestions,
        "answer": result["answer"],
        "run_id": result["run_id"],
        "nudged": result["nudged"],
        # The whole conversation, for building training examples (not saved in eval results).
        "messages": result["messages"],
        "reasoning": result["reasoning"],
    }
