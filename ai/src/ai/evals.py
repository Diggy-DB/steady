"""Eval scenarios, and the checks that score each run.

These scenarios are the TEST SET. Never train on them (or on their logs), or
the pass rate stops meaning anything. That's why eval runs log to
logs/evals.jsonl instead of logs/calls.jsonl.

A check is a function that looks at one run and returns None if it passed,
or a short message saying what went wrong.
"""

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


Check = Callable[[Transcript], str | None]


@dataclass
class Scenario:
    name: str
    question: str
    checks: list[Check]
    now: str = "2026-10-05 18:30"  # fake local time, so every run faces the same situation
    user_id: str = "user-1"
    data: dict | None = None  # a different week than fixtures/week.json (used for training tasks)


# ---- Checks. Each function builds and returns a check. ----


def calls(tool: str) -> Check:
    def check(t: Transcript) -> str | None:
        return None if any(c["name"] == tool for c in t.tool_calls) else f"never called {tool}"

    return check


def finishes() -> Check:
    def check(t: Transcript) -> str | None:
        if t.rounds >= MAX_ROUNDS:
            return "gave up after the maximum number of rounds"
        return None if t.answer.strip() else "empty answer"

    return check


def proposes_nothing() -> Check:
    def check(t: Transcript) -> str | None:
        return None if not t.suggestions else f"made {len(t.suggestions)} proposal(s)"

    return check


def proposes_at_least(n: int) -> Check:
    def check(t: Transcript) -> str | None:
        return None if len(t.suggestions) >= n else f"made {len(t.suggestions)} proposal(s), wanted at least {n}"

    return check


def moves(event_id: str, to: str | None = None) -> Check:
    """A MOVE_EVENT suggestion for event_id, optionally starting at `to` ("HH:MM")."""

    def check(t: Transcript) -> str | None:
        for s in t.suggestions:
            if s["type"] == "MOVE_EVENT" and s["target_id"] == event_id:
                if to is None or s["proposed_change"]["start"][11:16] == to:
                    return None
        return f"no suggestion moving {event_id}" + (f" to {to}" if to else "")

    return check


def never_touches(*event_ids: str) -> Check:
    def check(t: Transcript) -> str | None:
        touched = [s["target_id"] for s in t.suggestions if s["target_id"] in event_ids]
        return f"suggested changing {', '.join(touched)}" if touched else None

    return check


def new_events_named(words: tuple[str, ...], count: int | None = None, minutes: int | None = None) -> Check:
    """New-event suggestions whose name contains any of `words`: exactly `count` of them, and/or `minutes` in total."""

    def check(t: Transcript) -> str | None:
        found = [
            s
            for s in t.suggestions
            if s["type"] == "CREATE_EVENT" and any(w in s["proposed_change"]["name"].lower() for w in words)
        ]
        total = sum(
            (datetime.fromisoformat(s["proposed_change"]["end"]) - datetime.fromisoformat(s["proposed_change"]["start"]))
            .total_seconds() // 60
            for s in found
        )
        if count is not None and len(found) != count:
            return f"{len(found)} new '{words[0]}' event(s), wanted {count}"
        if minutes is not None and total < minutes:
            return f"{int(total)} minutes of new '{words[0]}' events, wanted at least {minutes}"
        return None

    return check


def mentions_any(*words: str) -> Check:
    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        return None if any(w in answer for w in words) else f"answer mentions none of {list(words)}"

    return check


def mentions_all(*words: str) -> Check:
    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        missing = [w for w in words if w not in answer]
        return f"answer doesn't mention {missing}" if missing else None

    return check


def avoids(*phrases: str) -> Check:
    def check(t: Transcript) -> str | None:
        answer = t.answer.lower()
        found = [p for p in phrases if p in answer]
        return f"answer says {found}" if found else None

    return check


def asks_question() -> Check:
    def check(t: Transcript) -> str | None:
        return None if "?" in t.answer else "didn't ask a question"

    return check


def either(*checks: Check) -> Check:
    """Passes if at least one of the checks passes."""

    def check(t: Transcript) -> str | None:
        problems = [c(t) for c in checks]
        return None if None in problems else " and ".join(problems)

    return check


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
    )
    failures = [problem for check in scenario.checks if (problem := check(transcript))]
    return {
        "scenario": scenario.name,
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
