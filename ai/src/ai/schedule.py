"""The user's schedule: fake data for now, and the get_schedule tool the model can call.

The model only sees what get_schedule returns. Everything it can't be
trusted with (which user, what time it is, time zone math) is decided here.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ai.llm import AI_DIR

FIXTURE = AI_DIR / "fixtures" / "week.json"
MAX_DAYS = 14  # keeps tool results small enough for a 4B model


class ToolError(Exception):
    """A mistake the model made and can fix, like a badly written date. It gets sent back to the model."""


class FixtureStore:
    """Reads users, events and tasks from a JSON file. A Supabase version will have the same methods.

    Suggestions are kept in memory only: the JSON file is never written, so every run starts fresh.
    """

    def __init__(self, path: Path = FIXTURE):
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self._suggestions: list[dict] = []

    def user(self, user_id: str) -> dict:
        for user in self.data["users"]:
            if user["user_id"] == user_id:
                return user
        raise KeyError(f"no user {user_id!r}")

    def events(self, user_id: str, start: datetime, end: datetime) -> list[dict]:
        """This user's events that overlap the time range [start, end), earliest first."""
        found = [
            e
            for e in self.data["events"]
            if e["user_id"] == user_id
            and overlaps(datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]), start, end)
        ]
        return sorted(found, key=lambda e: datetime.fromisoformat(e["start"]))

    def event(self, user_id: str, event_id: str) -> dict | None:
        """One of this user's events by id, or None. Another user's event counts as not found."""
        for e in self.data["events"]:
            if e["user_id"] == user_id and e["event_id"] == event_id:
                return e
        return None

    def tasks(self, user_id: str, first_day: date, last_day: date) -> list[dict]:
        """This user's tasks due between two days (inclusive)."""
        return [
            t
            for t in self.data["tasks"]
            if t["user_id"] == user_id and first_day <= date.fromisoformat(t["due"]) <= last_day
        ]

    def suggestions(self, user_id: str, status: str | None = None) -> list[dict]:
        """This user's suggestions, optionally only those with one status (e.g. "PENDING")."""
        return [s for s in self._suggestions if s["user_id"] == user_id and status in (None, s["status"])]

    def add_suggestion(self, user_id: str, suggestion: dict) -> dict:
        """Store a new PENDING suggestion (a row in the planned ai_suggestions table) and return it."""
        record = {"suggestion_id": f"s{len(self._suggestions) + 1}", "user_id": user_id, "status": "PENDING", **suggestion}
        self._suggestions.append(record)
        return record


@dataclass
class ToolContext:
    """Facts about the request that come from code, never from the model."""

    store: FixtureStore
    user_id: str
    now: datetime  # must include a time zone


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """True if two time ranges share any time. Touching ranges (3-4 PM and 4-5 PM) don't overlap."""
    return a_start < b_end and b_start < a_end


def format_day(day: date) -> str:
    return f"{day:%A, %B} {day.day}"  # "Monday, October 5"


def format_time(moment: datetime) -> str:
    return f"{moment.hour % 12 or 12}:{moment:%M %p}"  # "6:30 PM"


def describe_now(now: datetime) -> str:
    return f"{format_day(now)}, {now.year}, {format_time(now)} ({now.tzinfo})"


def parse_day(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError(f"{name} must be a date like 2026-10-06, not {value!r}") from None


GET_SCHEDULE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_schedule",
        "description": (
            "Get the user's calendar events and the tasks due between two dates (inclusive). "
            "Times are in the user's time zone, and each event says whether it is already over."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "First day, YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Last day, YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    },
}


def get_schedule(ctx: ToolContext, start_date: str, end_date: str) -> dict:
    first_day = parse_day(start_date, "start_date")
    last_day = parse_day(end_date, "end_date")
    if last_day < first_day:
        raise ToolError("end_date is before start_date")
    if (last_day - first_day).days >= MAX_DAYS:
        raise ToolError(f"ask for at most {MAX_DAYS} days at a time")

    tz = ZoneInfo(ctx.store.user(ctx.user_id)["timezone"])
    now = ctx.now.astimezone(tz)
    # Local midnight at the start of the first day, up to local midnight after the last day.
    window_start = datetime.combine(first_day, time.min, tzinfo=tz)
    window_end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=tz)

    events = []
    for e in ctx.store.events(ctx.user_id, window_start, window_end):
        start = datetime.fromisoformat(e["start"]).astimezone(tz)
        end = datetime.fromisoformat(e["end"]).astimezone(tz)
        if end <= now:
            when = "already over"
        elif start <= now:
            when = "happening now"
        else:
            when = "upcoming"
        events.append(
            {
                "id": e["event_id"],
                "name": e["name"],
                "day": format_day(start),
                "start": format_time(start),
                "end": format_time(end),
                "changeable": e["changeable"],
                "when": when,
            }
        )

    tasks = [
        {
            "id": t["task_id"],
            "name": t["name"],
            "description": t["description"],
            "due": format_day(date.fromisoformat(t["due"])),
            "status": t["status"],
            "changeable": t["changeable"],
        }
        for t in ctx.store.tasks(ctx.user_id, first_day, last_day)
    ]
    return {"now": describe_now(now), "events": events, "tasks": tasks}
