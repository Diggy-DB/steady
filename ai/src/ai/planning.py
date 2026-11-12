"""Planning tools: find free time, and propose changes that the user must accept.

The model never changes the calendar. The propose_* tools only store a PENDING
suggestion, and only after the same checks the backend will repeat when the
user taps Accept: the event exists and belongs to the user, it may be changed,
the new time isn't already over, and it doesn't overlap anything.

Suggestions can build on each other: if a pending suggestion moves an event,
its old time counts as free, and anything proposed in that time records the
move in `depends_on` (it only works if the user accepts the move too).
"""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai.recurrence import last_day, occurrences
from ai.schedule import MAX_DAYS, ToolContext, ToolError, format_day, format_time, overlaps, parse_day, too_many_days

# Free time is only looked for between these hours. Later this comes from the user's preferences.
DAY_START = time(8, 0)
DAY_END = time(22, 0)
SLOT_STEP = 15  # minutes: free time starts on a quarter hour


def user_timezone(ctx: ToolContext) -> ZoneInfo:
    return ZoneInfo(ctx.store.user(ctx.user_id)["timezone"])


def parse_local(value: str, name: str, tz: ZoneInfo) -> datetime:
    """Read "YYYY-MM-DD HH:MM" as a time in the user's time zone."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError(f"{name} must look like 2026-10-07 14:30, not {value!r}") from None
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment.astimezone(tz)


def describe_range(start: datetime, end: datetime) -> str:
    return f"{format_day(start)}, {format_time(start)} – {format_time(end)}"


def round_up(moment: datetime) -> datetime:
    """The next quarter hour at or after `moment` (6:30 stays 6:30, 6:37 becomes 6:45)."""
    if moment.second or moment.microsecond:
        moment = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return moment + timedelta(minutes=-moment.minute % SLOT_STEP)


def pending_moves(ctx: ToolContext) -> dict[str, str]:
    """Event id -> id of the pending suggestion that moves it."""
    return {
        s["target_id"]: s["suggestion_id"]
        for s in ctx.store.suggestions(ctx.user_id, status="PENDING")
        if s["type"] == "MOVE_EVENT"
    }


def pending_deletes(ctx: ToolContext) -> dict[tuple[str, str], str]:
    """(what, id) -> id of the pending suggestion that deletes it, e.g. ("event", "e2") -> "s3"."""
    return {
        (s["proposed_change"]["what"], s["proposed_change"]["id"]): s["suggestion_id"]
        for s in ctx.store.suggestions(ctx.user_id, status="PENDING")
        if s["type"] in DELETE_TYPES.values()
    }


def busy(
    ctx: ToolContext,
    start: datetime,
    end: datetime,
    ignore_event_id: str | None = None,
    ignore_suggestion_id: str | None = None,
) -> list[tuple]:
    """Everything taking up time between start and end, as (start, end, label), earliest first.

    Pending suggestions count as busy, so proposals in one plan can't overlap each other.
    An event with a pending move is counted at its new time, not its old one.
    """
    tz = user_timezone(ctx)
    moving = pending_moves(ctx)
    taken = []
    for e in ctx.store.events(ctx.user_id, start, end):
        if e["event_id"] != ignore_event_id and e["event_id"] not in moving:
            e_start = datetime.fromisoformat(e["start"]).astimezone(tz)
            e_end = datetime.fromisoformat(e["end"]).astimezone(tz)
            taken.append((e_start, e_end, e["name"]))
    for s in ctx.store.suggestions(ctx.user_id, status="PENDING"):
        # Only new and moved events take time (tasks, deletes and journal notes don't). An event with a
        # pending delete still counts as busy until the user accepts the delete.
        if s["suggestion_id"] == ignore_suggestion_id or s["type"] not in ("CREATE_EVENT", "MOVE_EVENT"):
            continue
        for o in occurrences(s["proposed_change"], start, end, tz):  # a weekly class, each week
            o_start = datetime.fromisoformat(o["start"]).astimezone(tz)
            o_end = datetime.fromisoformat(o["end"]).astimezone(tz)
            taken.append((o_start, o_end, f"your pending suggestion {s['suggestion_id']}"))
    return sorted(taken)


def freed_by(ctx: ToolContext, start: datetime, end: datetime) -> list[str]:
    """Ids of pending moves whose event's OLD time overlaps [start, end): the new proposal depends on them."""
    moving = pending_moves(ctx)
    return [
        moving[e["event_id"]]
        for e in ctx.store.events(ctx.user_id, start, end)
        if e["event_id"] in moving
    ]


def check_time(
    ctx: ToolContext,
    start: datetime,
    end: datetime,
    ignore_event_id: str | None = None,
    ignore_suggestion_id: str | None = None,
) -> list[str]:
    """Raise ToolError unless [start, end) is free and in the future. Returns the suggestions it depends on.

    The same check must run again when the user accepts, because the calendar may have changed since.
    """
    if end <= start:
        raise ToolError("the end time must be after the start time")
    now = ctx.now.astimezone(start.tzinfo)
    if start < now:
        raise ToolError(f"{describe_range(start, end)} has already started; it is now {format_time(now)} on {format_day(now)}")
    clashes = [
        f"{name} ({describe_range(s, e)})"
        for s, e, name in busy(ctx, start, end, ignore_event_id, ignore_suggestion_id)
    ]
    if clashes:
        raise ToolError(f"{describe_range(start, end)} overlaps " + "; ".join(clashes) + ". Use find_free_slots to pick a free time.")
    return freed_by(ctx, start, end)


FIND_FREE_SLOTS_TOOL = {
    "type": "function",
    "function": {
        "name": "find_free_slots",
        "description": (
            "Find free blocks of at least `minutes` between two dates (inclusive), 8 AM to 10 PM, never in the past. "
            "Returns free times per day as 'HH:MM-HH:MM' (24-hour). To propose, combine the date and a time, "
            "e.g. start '2026-10-07 12:00'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "First day, YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Last day, YYYY-MM-DD"},
                "minutes": {"type": "integer", "description": "Shortest useful block, in minutes"},
            },
            "required": ["start_date", "end_date", "minutes"],
        },
    },
}


def free_gaps(ctx: ToolContext, day: date, need: timedelta) -> list[tuple[datetime, datetime]]:
    """Free (start, end) gaps of at least `need` on one day, between DAY_START and DAY_END, not in the past."""
    tz = user_timezone(ctx)
    window_start = max(datetime.combine(day, DAY_START, tzinfo=tz), round_up(ctx.now.astimezone(tz)))
    window_end = datetime.combine(day, DAY_END, tzinfo=tz)
    if window_start >= window_end:
        return []
    # Walk through the busy times in order; every gap between them is free.
    cursor = window_start
    gaps = []
    for b_start, b_end, _ in busy(ctx, window_start, window_end):
        gaps.append((cursor, b_start))
        cursor = max(cursor, b_end)
    gaps.append((cursor, window_end))
    return [(start, end) for start, end in gaps if end - start >= need]


def find_free_slots(ctx: ToolContext, start_date: str, end_date: str, minutes: int) -> dict:
    first_day = parse_day(start_date, "start_date")
    last_day = parse_day(end_date, "end_date")
    if last_day < first_day:
        raise ToolError("end_date is before start_date")
    if (last_day - first_day).days >= MAX_DAYS:
        raise ToolError(too_many_days(first_day))
    if not isinstance(minutes, int) or not 15 <= minutes <= 12 * 60:
        raise ToolError("minutes must be a whole number from 15 to 720")

    days = []
    day = first_day
    while day <= last_day:
        gaps = free_gaps(ctx, day, timedelta(minutes=minutes))
        if gaps:  # days with no free time are left out, to keep the result short
            days.append(
                {"date": day.isoformat(), "day": format_day(day), "free": [f"{s:%H:%M}-{e:%H:%M}" for s, e in gaps]}
            )
        day += timedelta(days=1)
    now = ctx.now.astimezone(user_timezone(ctx))
    return {"now": f"{now:%Y-%m-%d %H:%M}", "minutes": minutes, "days": days}


# Words that say nothing about what an event is ("Work on ...", "... session").
GENERIC_WORDS = {"a", "an", "and", "block", "event", "for", "my", "of", "on", "session", "sessions", "the", "time", "to", "work"}


def key_words(name: str) -> set[str]:
    words = {w.strip(".,:;!?()").lower() for w in name.split()}
    return {w for w in words if w and w not in GENERIC_WORDS}


def similar_this_week(ctx: ToolContext, name: str, start: datetime) -> list[str]:
    """Events (not over yet) and pending suggestions in the same Monday-Sunday week with a similar name.

    Small models forget to count what's already planned ("gym 3 times" when one gym session
    exists), so the propose tool tells them right when it matters.
    """
    words = key_words(name)
    if not words:
        return []
    tz = start.tzinfo
    monday = datetime.combine((start - timedelta(days=start.weekday())).date(), time.min, tzinfo=tz)
    week_end = monday + timedelta(days=7)
    found = [
        f"{e['name']} ({describe_range(datetime.fromisoformat(e['start']).astimezone(tz), datetime.fromisoformat(e['end']).astimezone(tz))})"
        for e in ctx.store.events(ctx.user_id, monday, week_end)
        if key_words(e["name"]) & words and datetime.fromisoformat(e["end"]) > ctx.now
    ]
    for s in ctx.store.suggestions(ctx.user_id, status="PENDING"):
        change = s["proposed_change"]
        if s["type"] != "CREATE_EVENT":
            continue
        s_start = datetime.fromisoformat(change["start"]).astimezone(tz)
        if monday <= s_start < week_end and key_words(change["name"]) & words:
            s_end = datetime.fromisoformat(change["end"]).astimezone(tz)
            found.append(f"your pending suggestion {s['suggestion_id']}: {change['name']} ({describe_range(s_start, s_end)})")
    return found


EARLIEST, LATEST = time(7, 0), time(23, 0)  # suggested times stay inside these unless the user asks otherwise
CLOCK_TIME = re.compile(r"\b(\d{1,2})(?::\d{2})?\s*(a\.?m\.?|p\.?m\.?)|\b(\d{1,2}):\d{2}\b|\bmidnight\b", re.IGNORECASE)
# Late is fine when the user asks for it, or when a deadline tonight needs it ("absolutely needed").
LATE_WORDS = re.compile(r"\b(?:late at night|late night|all[- ]nighter|overnight|early morning|before sunrise|"
                        r"due tonight|due at midnight|due by midnight|tonight at midnight)\b", re.IGNORECASE)
# "I don't prefer studying after 11pm", "not past 10", "avoid late nights": a time they DON'T want.
NOT_WANTED = re.compile(r"\b(?:don'?t|do not|not|never|avoid|rather not|prefer not|no)\b[^.!?]{0,40}"
                        r"\b(?:after|past|later than|late|before|earlier than|early)\b", re.IGNORECASE)


def asked_for_odd_hours(text: str) -> bool:
    """True if the user asked for a time before 7 AM or from 11 PM on ("at 11:30 pm", "6am", "midnight", "late
    at night"), and didn't say they don't want one ("I don't prefer studying after 11pm")."""
    if NOT_WANTED.search(text):
        return False
    if LATE_WORDS.search(text):
        return True
    for match in CLOCK_TIME.finditer(text):
        if match.group(0).lower() == "midnight":
            return True
        hour = int(match.group(1) or match.group(3))
        if match.group(2):  # 12-hour: "11 pm" -> 23
            hour = hour % 12 + (12 if match.group(2).lower().startswith("p") else 0)
        if hour < EARLIEST.hour or hour >= LATEST.hour:
            return True
    return False


def check_hours(ctx: ToolContext, start: datetime, end: datetime) -> None:
    """Refuse very late or very early times the user didn't ask for. The 4B suggested 11 PM-midnight study
    sessions every night for someone who "works best at night"."""
    if start.time() >= EARLIEST and (end.date() == start.date() and end.time() <= LATEST):
        return
    if ctx.asked is not None and asked_for_odd_hours(ctx.asked):
        return
    raise ToolError(f"{describe_range(start, end)} is very late at night or very early. Suggest times between "
                    "7 AM and 11 PM (find_free_slots lists them) unless the user asks for a late or early time")


def dependency_note(depends_on: list[str]) -> str:
    if not depends_on:
        return ""
    return f" It only works if the user also accepts {', '.join(depends_on)}, which frees this time."


PROPOSE_NEW_EVENT_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_new_event",
        "description": (
            "Suggest adding an event to the user's calendar, such as a block of time to work on a task. "
            "Nothing changes until the user accepts. Fails if the time is already over or overlaps something."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Event name, e.g. 'Work on MTH 133 problem set'"},
                "start": {"type": "string", "description": "YYYY-MM-DD HH:MM (24-hour, user's time zone)"},
                "end": {"type": "string", "description": "YYYY-MM-DD HH:MM (24-hour, user's time zone)"},
                "reason": {"type": "string", "description": "One short sentence shown to the user"},
            },
            "required": ["name", "start", "end", "reason"],
        },
    },
}


def propose_new_event(ctx: ToolContext, name: str, start: str, end: str, reason: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ToolError("name can't be empty")
    tz = user_timezone(ctx)
    start_at = parse_local(start, "start", tz)
    end_at = parse_local(end, "end", tz)
    check_hours(ctx, start_at, end_at)
    depends_on = check_time(ctx, start_at, end_at)
    similar = similar_this_week(ctx, name, start_at)  # before adding, so it doesn't list itself

    suggestion = ctx.store.add_suggestion(
        ctx.user_id,
        {
            "type": "CREATE_EVENT",
            "target_id": None,
            "description": reason,
            "proposed_change": {"name": name.strip(), "start": start_at.isoformat(), "end": end_at.isoformat()},
            "depends_on": depends_on,
            "created_at": ctx.now.isoformat(),
            "expires_at": start_at.isoformat(),  # once it would have started, it's no use
        },
    )
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "status": "PENDING",
        "summary": f"Suggested new event '{name.strip()}' on {describe_range(start_at, end_at)}. "
        "Nothing changes until the user accepts it." + dependency_note(depends_on) + similar_note(similar),
    }


def similar_note(similar: list[str]) -> str:
    if not similar:
        return ""
    return (
        " Already planned this week with a similar name: " + "; ".join(similar)
        + ". Count these toward the user's goal before suggesting more."
    )


PROPOSE_MOVE_EVENT_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_move_event",
        "description": (
            "Suggest moving one of the user's events to a new time. Nothing changes until the user accepts. "
            "Fails for fixed events (changeable: false), times already over, and overlaps. "
            "Once proposed, the event's old time counts as free for further proposals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event's id from get_schedule, e.g. 'e2'"},
                "new_start": {"type": "string", "description": "YYYY-MM-DD HH:MM (24-hour, user's time zone)"},
                "new_end": {"type": "string", "description": "YYYY-MM-DD HH:MM (24-hour, user's time zone)"},
                "reason": {"type": "string", "description": "One short sentence shown to the user"},
            },
            "required": ["event_id", "new_start", "new_end", "reason"],
        },
    },
}


def propose_move_event(ctx: ToolContext, event_id: str, new_start: str, new_end: str, reason: str) -> dict:
    event = ctx.store.event(ctx.user_id, event_id)
    if event is None:
        raise ToolError(f"there is no event with id {event_id!r}; use get_schedule to find event ids")
    if not event["changeable"]:
        raise ToolError(f"{event['name']} is fixed (changeable: false) and can't be moved")
    if event_id in pending_moves(ctx):
        raise ToolError(f"{event['name']} already has a pending move ({pending_moves(ctx)[event_id]})")
    if ("event", event_id) in pending_deletes(ctx):
        raise ToolError(f"{event['name']} already has a pending delete ({pending_deletes(ctx)[('event', event_id)]})")

    tz = user_timezone(ctx)
    old_start = datetime.fromisoformat(event["start"]).astimezone(tz)
    old_end = datetime.fromisoformat(event["end"]).astimezone(tz)
    if old_end <= ctx.now:
        raise ToolError(f"{event['name']} on {describe_range(old_start, old_end)} is already over")
    start_at = parse_local(new_start, "new_start", tz)
    end_at = parse_local(new_end, "new_end", tz)
    check_hours(ctx, start_at, end_at)
    depends_on = check_time(ctx, start_at, end_at, ignore_event_id=event_id)  # it may overlap its own old time

    suggestion = ctx.store.add_suggestion(
        ctx.user_id,
        {
            "type": "MOVE_EVENT",
            "target_id": event_id,
            "description": reason,
            "proposed_change": {"start": start_at.isoformat(), "end": end_at.isoformat()},
            "depends_on": depends_on,
            "created_at": ctx.now.isoformat(),
            "expires_at": start_at.isoformat(),
        },
    )
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "status": "PENDING",
        "summary": f"Suggested moving {event['name']} from {describe_range(old_start, old_end)} "
        f"to {describe_range(start_at, end_at)}. Nothing changes until the user accepts it." + dependency_note(depends_on),
    }


PROPOSE_NEW_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_new_task",
        "description": (
            "Suggest adding a task to the user's task list: something to get done by a day, like an assignment, "
            "reading or an errand. Use it when the user asks to add a task or a to-do. For a block of time on the "
            "calendar, use propose_new_event instead. Nothing changes until the user accepts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The task, e.g. 'Read 2 chapters of the novel'"},
                "due_date": {"type": "string", "description": "The day it's for, YYYY-MM-DD (today or later)"},
                "details": {"type": "string", "description": "Optional short note, e.g. 'About 1 hour'"},
            },
            "required": ["name", "due_date"],
        },
    },
}


TASK_WORDS = re.compile(r"\b(?:tasks?|to-?dos?|to do list|todo list|checklist|to my list)\b", re.IGNORECASE)


def propose_new_task(ctx: ToolContext, name: str, due_date: str, details: str = "") -> dict:
    # Asked to plan time, the 4B sometimes added a copy of a task already on the list ("Finish MTH 133 problem set")
    # instead of blocking time for it: new tasks only when the user asks for one, and never a near-copy.
    require_asked(ctx, TASK_WORDS, "add a task (to plan time for something, use propose_new_event)")
    if not isinstance(name, str) or not name.strip():
        raise ToolError("name can't be empty")
    name = name.strip()
    tz = user_timezone(ctx)
    day = parse_day(due_date, "due_date")
    today = ctx.now.astimezone(tz).date()
    if day < today:
        raise ToolError(f"{format_day(day)} is already over; a new task needs a day from today ({today.isoformat()}) on")
    for t in ctx.store.tasks(ctx.user_id, today - timedelta(days=14), today + timedelta(days=60)):
        shared = key_words(t["name"]) & key_words(name)
        if t["status"] != "COMPLETED" and len(shared) >= 2 and t["name"].lower() != name.lower():
            raise ToolError(f"there's already a task like this: '{t['name']}' (due {format_day(date.fromisoformat(t['due']))}). "
                            "To make time for it, use propose_new_event instead of adding it again")
    same = [t for t in ctx.store.tasks(ctx.user_id, day, day) if t["name"].lower() == name.lower()]
    same += [s for s in ctx.store.suggestions(ctx.user_id, status="PENDING") if s["type"] == "CREATE_TASK"
             and s["proposed_change"]["name"].lower() == name.lower() and s["proposed_change"]["due"][:10] == day.isoformat()]
    if same:
        raise ToolError(f"there's already a task '{name}' on {format_day(day)}")
    due = datetime.combine(day, time(23, 59), tzinfo=tz)
    suggestion = ctx.store.add_suggestion(ctx.user_id, {
        "type": "CREATE_TASK", "target_id": None, "description": "Add to your tasks",
        "proposed_change": {"name": name, "due": due.isoformat(), "kind": "task", "description": str(details or "").strip()[:300]},
        "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": due.isoformat(),
    })
    return {"suggestion_id": suggestion["suggestion_id"], "status": "PENDING",
            "summary": f"Suggested the task '{name}' for {format_day(day)}. Nothing changes until the user accepts it."}


DELETE_TYPES = {"event": "DELETE_EVENT", "task": "DELETE_TASK", "journal": "DELETE_JOURNAL"}

# Words that ask to delete something. A small model sometimes adds a delete nobody asked for (asked for time
# for a lab report, it also suggested deleting a problem set), so the tools check the request itself.
DELETE_WORDS = re.compile(
    r"\b(?:delet\w*|remov\w*|cancel\w*|drop\w*|get rid|rid of|off (?:my|the) (?:calendar|list|task list|schedule|tasks)|"
    r"take (?:it|that|them|this) off|clear\w*|skip\w*|not going|won'?t (?:go|make|need|be going)|don'?t need|"
    r"no longer|erase|scrap|ditch|called off)\b", re.IGNORECASE)
JOURNAL_WORDS = re.compile(r"\b(?:journal\w*|diary|note (?:down|that|in|it)|write (?:down|in|that|it)|log (?:that|it))\b",
                           re.IGNORECASE)


def require_asked(ctx: ToolContext, words: re.Pattern, what: str) -> None:
    if ctx.asked is not None and not words.search(ctx.asked):
        raise ToolError(f"the user didn't ask to {what}, so don't suggest it; do only what they asked")


def require_named(ctx: ToolContext, name: str) -> None:
    """A delete must be for something the user named. Asked to cancel a piano lesson that wasn't on the calendar,
    the 4B suggested deleting that day's study session instead."""
    if ctx.asked is not None and not key_words(name) & key_words(ctx.asked):
        raise ToolError(f"the user didn't mention '{name}'. If what they asked about isn't on the calendar, tell them; "
                        "if they meant this one some other way (by its time, say), ask them to confirm it first")

PROPOSE_DELETE_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_delete",
        "description": (
            "Suggest deleting one event, task or journal entry. Use it only when the user asks to delete, "
            "remove or cancel it, or agrees to. Never delete something to make room: suggest a move instead. "
            "Nothing changes until the user accepts. Fails for fixed items (changeable: false)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "enum": ["event", "task", "journal"]},
                "id": {"type": "string",
                       "description": "The event's or task's id from get_schedule, e.g. 'e2'; for a journal entry, its date YYYY-MM-DD"},
                "reason": {"type": "string", "description": "One short sentence shown to the user"},
            },
            "required": ["what", "id", "reason"],
        },
    },
}


def propose_delete(ctx: ToolContext, what: str, id: str, reason: str) -> dict:  # noqa: A002 (the model's name for it)
    require_asked(ctx, DELETE_WORDS, "delete or remove anything")
    tz = user_timezone(ctx)
    if what not in DELETE_TYPES:
        raise ToolError("what must be 'event', 'task' or 'journal'")
    if (what, str(id)) in pending_deletes(ctx):
        raise ToolError(f"that {what} already has a pending delete ({pending_deletes(ctx)[(what, str(id))]})")
    if what == "event":
        event = ctx.store.event(ctx.user_id, id)
        if event is None:
            raise ToolError(f"there is no event with id {id!r}; use get_schedule to find event ids")
        if event.get("recurrence_rule"):
            raise ToolError(f"{event['name']} repeats every week; the user can delete it from their calendar themselves")
        if not event["changeable"]:
            raise ToolError(f"{event['name']} is fixed (changeable: false) and can't be deleted")
        if id in pending_moves(ctx):
            raise ToolError(f"{event['name']} has a pending move ({pending_moves(ctx)[id]}); it can't also be deleted")
        require_named(ctx, event["name"])
        start = datetime.fromisoformat(event["start"]).astimezone(tz)
        end = datetime.fromisoformat(event["end"]).astimezone(tz)
        change = {"what": "event", "id": id, "name": event["name"], "start": start.isoformat(), "end": end.isoformat()}
        described = f"{event['name']} ({describe_range(start, end)})"
    elif what == "task":
        task = ctx.store.task(ctx.user_id, id)
        if task is None:
            raise ToolError(f"there is no task with id {id!r}; use get_schedule to find task ids")
        if not task["changeable"]:
            raise ToolError(f"{task['name']} is fixed (changeable: false) and can't be deleted")
        require_named(ctx, task["name"])
        change = {"what": "task", "id": id, "name": task["name"], "due": task["due"]}
        described = f"the task {task['name']} (due {format_day(date.fromisoformat(task['due']))})"
    else:
        day = parse_day(id, "id (the journal entry's date)")
        entry = ctx.store.journal_on(ctx.user_id, day)
        if entry is None:
            raise ToolError(f"there is no journal entry on {format_day(day)}")
        change = {"what": "journal", "id": day.isoformat(), "journal_id": str(entry["journal_id"]),
                  "preview": entry["information"][:200]}
        described = f"your journal entry for {format_day(day)}"
    suggestion = ctx.store.add_suggestion(ctx.user_id, {
        "type": DELETE_TYPES[what], "target_id": None, "description": reason, "proposed_change": change,
        "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": None,
    })
    return {"suggestion_id": suggestion["suggestion_id"], "status": "PENDING",
            "summary": f"Suggested deleting {described}. Nothing changes until the user accepts it."}


GET_JOURNAL_TOOL = {
    "type": "function",
    "function": {
        "name": "get_journal",
        "description": "Read the user's journal entry for one day, to answer a question about it or before editing it.",
        "parameters": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "The day, YYYY-MM-DD"}},
            "required": ["date"],
        },
    },
}


def get_journal(ctx: ToolContext, date: str) -> dict:  # noqa: A002 ("date" is the model's word)
    day = parse_day(date, "date")
    entry = ctx.store.journal_on(ctx.user_id, day)
    if entry is None:
        return {"date": day.isoformat(), "day": format_day(day), "text": None, "note": "no journal entry that day"}
    return {"date": day.isoformat(), "day": format_day(day), "text": entry["information"]}


PROPOSE_JOURNAL_ENTRY_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_journal_entry",
        "description": (
            "Suggest adding text to the user's journal for one day (added to that day's entry, or starting one), "
            "or, with replace: true, suggest an edited version of the whole entry. Use it when the user asks you "
            "to write in their journal, note how their day went, or change what they wrote. Write in the first "
            "person, as the user, using only what they told you. Nothing changes until the user accepts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "The day the entry is for, YYYY-MM-DD (today or earlier)"},
                "text": {"type": "string", "description": "What to add; with replace: true, the full corrected entry"},
                "replace": {"type": "boolean",
                            "description": "true to replace the whole entry (to edit or correct it; read it with "
                                           "get_journal first and keep everything the user didn't ask to change); "
                                           "false (the default) to add to it"},
            },
            "required": ["date", "text"],
        },
    },
}

OLD_JOURNAL_DAYS = 7  # a new entry further back than this is refused as a probable date mistake
MAX_JOURNAL_TEXT = 2000  # what the AI may add at once
MAX_EDITED_TEXT = 8000  # a whole edited entry


def propose_journal_entry(ctx: ToolContext, date: str, text: str, replace: bool = False) -> dict:  # noqa: A002
    require_asked(ctx, JOURNAL_WORDS, "write in their journal")
    tz = user_timezone(ctx)
    day = parse_day(date, "date")
    today = ctx.now.astimezone(tz).date()
    if day > today:
        raise ToolError(f"{format_day(day)} hasn't happened yet; a journal entry can only be for today or earlier")
    if (today - day).days > OLD_JOURNAL_DAYS and ctx.store.journal_on(ctx.user_id, day) is None:
        # Small models get dates wrong (the wrong year, "Friday" read as last Friday). An entry for a long-gone
        # day with nothing in it is almost always that mistake, so say what today and yesterday are.
        yesterday = today - timedelta(days=1)
        raise ToolError(f"{format_day(day)}, {day.year} was {(today - day).days} days ago. Today is {format_day(today)}, "
                        f"{today.year} ({today.isoformat()}); yesterday was {yesterday.isoformat()}. Use the day the "
                        "user meant; if it really is that old day, ask the user to confirm it first")
    if not isinstance(text, str) or not text.strip():
        raise ToolError("text can't be empty")
    text = text.strip()
    if len(text) > (MAX_EDITED_TEXT if replace else MAX_JOURNAL_TEXT):
        raise ToolError(f"keep it under {MAX_EDITED_TEXT if replace else MAX_JOURNAL_TEXT} characters")
    existing = ctx.store.journal_on(ctx.user_id, day)
    if replace is True:
        if existing is None:
            raise ToolError(f"there's no journal entry on {format_day(day)} to edit; to start one, leave out replace")
        if text == existing["information"].strip():
            raise ToolError("that's the same as the current entry; nothing to change")
        suggestion = ctx.store.add_suggestion(ctx.user_id, {
            "type": "EDIT_JOURNAL", "target_id": None, "description": "Edit your journal entry",
            # "old" is the entry this edit was written from: Accept refuses if the user has changed it since.
            "proposed_change": {"date": day.isoformat(), "text": text, "old": existing["information"]},
            "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": None,
        })
        return {"suggestion_id": suggestion["suggestion_id"], "status": "PENDING",
                "summary": f"Suggested an edited journal entry for {format_day(day)}; the user sees it before and "
                           "after. Nothing changes until the user accepts it."}
    suggestion = ctx.store.add_suggestion(ctx.user_id, {
        "type": "ADD_JOURNAL", "target_id": None,
        "description": "Add to your journal" if existing else "Start your journal entry",
        "proposed_change": {"date": day.isoformat(), "text": text, "adds_to_existing": existing is not None},
        "depends_on": [], "created_at": ctx.now.isoformat(), "expires_at": None,
    })
    where = "added to" if existing else "a new entry in"
    return {"suggestion_id": suggestion["suggestion_id"], "status": "PENDING",
            "summary": f"Suggested text {where} the journal for {format_day(day)}. Nothing changes until the user accepts it."}


def recheck(ctx: ToolContext, suggestion: dict) -> list[str]:
    """Problems that stop a suggestion from being applied now; an empty list means it's still valid.

    Run this right before applying a suggestion the user accepted: the calendar may have
    changed since the suggestion was made.
    """
    if suggestion["status"] != "PENDING":
        return [f"it is {suggestion['status']}, not PENDING"]
    change = suggestion["proposed_change"]
    tz = user_timezone(ctx)
    if suggestion["type"] == "ADD_JOURNAL":
        return []  # adding to a journal is always possible
    if suggestion["type"] == "EDIT_JOURNAL":
        entry = ctx.store.journal_on(ctx.user_id, date.fromisoformat(change["date"]))
        if entry is None:
            return ["that journal entry is gone"]
        if entry["information"] != change["old"]:  # never overwrite what the user wrote after the suggestion
            return ["the journal entry has changed since this edit was suggested; ask Steady again"]
        return []
    if suggestion["type"] == "DELETE_EVENT":
        event = ctx.store.event(ctx.user_id, change["id"])
        if event is None:
            return [f"{change['name']} is already gone"]
        return [] if event["changeable"] else [f"{event['name']} is now fixed (changeable: false)"]
    if suggestion["type"] == "DELETE_TASK":
        task = ctx.store.task(ctx.user_id, change["id"])
        if task is None:
            return [f"{change['name']} is already gone"]
        return [] if task["changeable"] else [f"{task['name']} is now fixed (changeable: false)"]
    if suggestion["type"] == "DELETE_JOURNAL":
        found = ctx.store.journal_on(ctx.user_id, date.fromisoformat(change["id"]))
        return [] if found else ["that journal entry is already gone"]
    if suggestion["type"] == "CREATE_TASK":
        due = datetime.fromisoformat(change["due"]).astimezone(tz)
        return [f"it was due {format_day(due)} at {format_time(due)}, which has passed"] if due < ctx.now else []
    if change.get("recurrence_rule"):  # a weekly class: fine while the semester lasts
        last = last_day(change["recurrence_rule"])
        return [f"the class ended on {format_day(datetime.combine(last, time.min, tzinfo=tz))}"] \
            if last and last < ctx.now.astimezone(tz).date() else []
    if change.get("source") == "syllabus":  # an exam or class session: its time is set by the course, so clashes are fine
        end = datetime.fromisoformat(change["end"]).astimezone(tz)
        return [f"{change['name']} is already over"] if end < ctx.now else []
    if suggestion["type"] == "MOVE_EVENT":
        event = ctx.store.event(ctx.user_id, suggestion["target_id"])
        if event is None:
            return ["the event no longer exists"]
        if not event["changeable"]:
            return [f"{event['name']} is now fixed (changeable: false)"]
    start = datetime.fromisoformat(change["start"]).astimezone(tz)
    end = datetime.fromisoformat(change["end"]).astimezone(tz)
    try:
        check_time(ctx, start, end, suggestion["target_id"], suggestion["suggestion_id"])
    except ToolError as error:
        return [str(error)]
    return []
