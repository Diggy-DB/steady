"""The user's schedule: fake data for now, and the get_schedule tool the model can call.

The model only sees what get_schedule returns. Everything it can't be
trusted with (which user, what time it is, time zone math) is decided here.
"""

import copy
import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ai.llm import AI_DIR
from ai.recurrence import occurrences

FIXTURE = AI_DIR / "fixtures" / "week.json"
MAX_DAYS = 14  # keeps tool results small enough for a 4B model


class ToolError(Exception):
    """A mistake the model made and can fix, like a badly written date. It gets sent back to the model."""


class FixtureStore:
    """Reads users, events and tasks from a JSON file. A Supabase version will have the same methods.

    Suggestions are kept in memory only: the JSON file is never written, so every run starts fresh.
    """

    def __init__(self, path: Path = FIXTURE, data: dict | None = None):
        """Load the week from `path`, or use `data` (a dict in the same shape) if given."""
        self.data = copy.deepcopy(data) if data is not None else json.loads(path.read_text(encoding="utf-8"))
        self._suggestions: list[dict] = []
        self.activity: list[dict] = []
        self._overviews: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()  # the demo server answers requests on several threads

    def user(self, user_id: str) -> dict:
        for user in self.data["users"]:
            if user["user_id"] == user_id:
                return user
        raise KeyError(f"no user {user_id!r}")

    def events(self, user_id: str, start: datetime, end: datetime) -> list[dict]:
        """This user's events that overlap the time range [start, end), earliest first (each time a repeating one happens)."""
        tz = ZoneInfo(self.user(user_id)["timezone"])
        found = [o for e in self.data["events"] if e["user_id"] == user_id for o in occurrences(e, start, end, tz)]
        return sorted(found, key=lambda e: datetime.fromisoformat(e["start"]))

    def event(self, user_id: str, event_id: str) -> dict | None:
        """One of this user's events by id, or None. Another user's event counts as not found."""
        for e in self.data["events"]:
            if e["user_id"] == user_id and e["event_id"] == event_id:
                return {**e, "changeable": False} if e.get("recurrence_rule") else e  # a series can't be moved as one event
        return None

    def tasks(self, user_id: str, first_day: date, last_day: date) -> list[dict]:
        """This user's tasks due between two days (inclusive)."""
        return [
            t
            for t in self.data["tasks"]
            if t["user_id"] == user_id and first_day <= date.fromisoformat(t["due"]) <= last_day
        ]

    def task(self, user_id: str, task_id: str) -> dict | None:
        """One of this user's tasks by id, or None."""
        return next((t for t in self.data["tasks"] if t["user_id"] == user_id and t["task_id"] == task_id), None)

    def journal(self, user_id: str, journal_id: str) -> dict | None:
        """One of this user's journal entries by id, or None (the fake week has none unless a test adds them)."""
        for j in self.data.get("journals", []):
            if j["user_id"] == user_id and str(j["journal_id"]) == str(journal_id):
                return j
        return None

    def journal_on(self, user_id: str, day: date) -> dict | None:
        """This user's journal entry for one day (there's at most one), or None."""
        return next((j for j in self.data.get("journals", []) if j["user_id"] == user_id and j["date"] == day.isoformat()), None)

    def journals(self, user_id: str, first_day: date, last_day: date) -> list[dict]:
        """This user's journal entries between two days (inclusive), earliest first."""
        return sorted((j for j in self.data.get("journals", []) if j["user_id"] == user_id
                       and first_day.isoformat() <= j["date"] <= last_day.isoformat()), key=lambda j: j["date"])

    def overview(self, user_id: str, day: date) -> dict | None:
        """The daily overview already written for this day, or None."""
        return self._overviews.get((user_id, day.isoformat()))

    def save_overview(self, user_id: str, day: date, overview: dict) -> None:
        self._overviews[(user_id, day.isoformat())] = overview

    def suggestions(self, user_id: str, status: str | None = None) -> list[dict]:
        """This user's suggestions, optionally only those with one status (e.g. "PENDING")."""
        return [s for s in self._suggestions if s["user_id"] == user_id and status in (None, s["status"])]

    def add_suggestion(self, user_id: str, suggestion: dict) -> dict:
        """Store a new PENDING suggestion (a row in the planned ai_suggestions table) and return it."""
        record = {"suggestion_id": f"s{len(self._suggestions) + 1}", "user_id": user_id, "status": "PENDING", **suggestion}
        self._suggestions.append(record)
        return record

    def set_status(self, suggestion_id: str, status: str) -> None:
        for s in self._suggestions:
            if s["suggestion_id"] == suggestion_id:
                s["status"] = status

    def claim(self, suggestion_id: str, from_status: str, to_status: str) -> bool:
        """Change the status only if it is still `from_status`; False if another request got there first."""
        with self._lock:
            for s in self._suggestions:
                if s["suggestion_id"] == suggestion_id and s["status"] == from_status:
                    s["status"] = to_status
                    return True
            return False

    def log(self, user_id: str, action: str, target_type: str, target_id: str, performed_by: str, details: dict) -> None:
        self.activity.append(
            {"user_id": user_id, "action": action, "target_type": target_type, "target_id": target_id,
             "performed_by": performed_by, "details": details}
        )

    def apply(self, suggestion: dict) -> None:
        """Make an accepted suggestion real, in memory only (Supabase mode writes to the database)."""
        change = suggestion["proposed_change"]
        if suggestion["type"] == "CREATE_TASK":
            due = datetime.fromisoformat(change["due"])
            self.data["tasks"].append(
                {"task_id": f"ai-{suggestion['suggestion_id']}", "user_id": suggestion["user_id"], "name": change["name"],
                 "description": (change.get("description", "") if change.get("kind") == "task" else task_description(due)), "due": due.date().isoformat(), "status": "NOT_STARTED",
                 "changeable": True}
            )
        elif suggestion["type"] == "CREATE_EVENT":
            self.data["events"].append(
                {
                    "event_id": f"ai-{suggestion['suggestion_id']}",
                    "user_id": suggestion["user_id"],
                    "name": change["name"],
                    "start": change["start"],
                    "end": change["end"],
                    "changeable": True,
                    "created_by": "AI",
                    **({"recurrence_rule": change["recurrence_rule"]} if change.get("recurrence_rule") else {}),
                }
            )
        elif suggestion["type"] == "MOVE_EVENT":
            event = self.event(suggestion["user_id"], suggestion["target_id"])
            event["start"], event["end"] = change["start"], change["end"]
        elif suggestion["type"] in ("DELETE_EVENT", "DELETE_TASK", "DELETE_JOURNAL"):
            table, key = {"DELETE_EVENT": ("events", "event_id"), "DELETE_TASK": ("tasks", "task_id"),
                          "DELETE_JOURNAL": ("journals", "date")}[suggestion["type"]]
            rows = self.data.get(table, [])
            keep = [r for r in rows if not (r["user_id"] == suggestion["user_id"] and str(r[key]) == change["id"])]
            if len(keep) == len(rows):
                raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied: it's already gone")
            self.data[table] = keep
        elif suggestion["type"] == "EDIT_JOURNAL":
            entry = self.journal_on(suggestion["user_id"], date.fromisoformat(change["date"]))
            if entry is None:
                raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied: the entry is gone")
            entry["information"] = change["text"]
        elif suggestion["type"] == "ADD_JOURNAL":
            entry = self.journal_on(suggestion["user_id"], date.fromisoformat(change["date"]))
            if entry:
                entry["information"] = journal_text(entry["information"], change["text"])
            else:
                journals = self.data.setdefault("journals", [])
                journals.append({"journal_id": f"ai-{suggestion['suggestion_id']}", "user_id": suggestion["user_id"],
                                 "date": change["date"], "information": change["text"]})


def journal_text(existing: str, addition: str) -> str:
    """A journal entry with the AI's text added at the end, as its own paragraph."""
    return f"{existing.rstrip()}\n\n{addition}" if existing.strip() else addition


def task_description(due: datetime) -> str:
    """The note on a task made from a deadline: the due time, since a task only has a date."""
    return f"Due {due.hour % 12 or 12}:{due:%M} {'AM' if due.hour < 12 else 'PM'}. Added from your syllabus."


@dataclass
class ToolContext:
    """Facts about the request that come from code, never from the model."""

    store: FixtureStore
    user_id: str
    now: datetime  # must include a time zone
    # What the user asked (plus Steady's previous reply, for "yes, do it"): deleting and journaling need the
    # user to have asked for it in so many words. None means no such check (code calling tools directly).
    asked: str | None = None


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


def too_many_days(first_day: date) -> str:
    """The error for a too-long date range, with a range that works, because a small model often
    can't work one out by itself (it retried 15- and 25-day ranges until it ran out of rounds)."""
    last = first_day + timedelta(days=MAX_DAYS - 1)
    return (f"ask for at most {MAX_DAYS} days at a time, e.g. start_date {first_day.isoformat()} and "
            f"end_date {last.isoformat()}; call again for the next {MAX_DAYS} days if you need them")


def get_schedule(ctx: ToolContext, start_date: str, end_date: str) -> dict:
    first_day = parse_day(start_date, "start_date")
    last_day = parse_day(end_date, "end_date")
    if last_day < first_day:
        raise ToolError("end_date is before start_date")
    if (last_day - first_day).days >= MAX_DAYS:
        raise ToolError(too_many_days(first_day))

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
