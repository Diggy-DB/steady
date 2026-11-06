"""Planning tools: find free time, and propose changes that the user must accept.

The model never changes the calendar. The propose_* tools only store a PENDING
suggestion, and only after the same checks the backend will repeat when the
user taps Accept: the event exists and belongs to the user, it may be changed,
the new time isn't already over, and it doesn't overlap anything.

Suggestions can build on each other: if a pending suggestion moves an event,
its old time counts as free, and anything proposed in that time records the
move in `depends_on` (it only works if the user accepts the move too).
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

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
        if s["suggestion_id"] == ignore_suggestion_id:
            continue
        s_start = datetime.fromisoformat(s["proposed_change"]["start"]).astimezone(tz)
        s_end = datetime.fromisoformat(s["proposed_change"]["end"]).astimezone(tz)
        if overlaps(s_start, s_end, start, end):
            taken.append((s_start, s_end, f"your pending suggestion {s['suggestion_id']}"))
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
        s_start = datetime.fromisoformat(change["start"]).astimezone(tz)
        if s["type"] == "CREATE_EVENT" and monday <= s_start < week_end and key_words(change["name"]) & words:
            s_end = datetime.fromisoformat(change["end"]).astimezone(tz)
            found.append(f"your pending suggestion {s['suggestion_id']}: {change['name']} ({describe_range(s_start, s_end)})")
    return found


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

    tz = user_timezone(ctx)
    old_start = datetime.fromisoformat(event["start"]).astimezone(tz)
    old_end = datetime.fromisoformat(event["end"]).astimezone(tz)
    if old_end <= ctx.now:
        raise ToolError(f"{event['name']} on {describe_range(old_start, old_end)} is already over")
    start_at = parse_local(new_start, "new_start", tz)
    end_at = parse_local(new_end, "new_end", tz)
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


def recheck(ctx: ToolContext, suggestion: dict) -> list[str]:
    """Problems that stop a suggestion from being applied now; an empty list means it's still valid.

    Run this right before applying a suggestion the user accepted: the calendar may have
    changed since the suggestion was made.
    """
    if suggestion["status"] != "PENDING":
        return [f"it is {suggestion['status']}, not PENDING"]
    if suggestion["type"] == "MOVE_EVENT":
        event = ctx.store.event(ctx.user_id, suggestion["target_id"])
        if event is None:
            return ["the event no longer exists"]
        if not event["changeable"]:
            return [f"{event['name']} is now fixed (changeable: false)"]
    tz = user_timezone(ctx)
    start = datetime.fromisoformat(suggestion["proposed_change"]["start"]).astimezone(tz)
    end = datetime.fromisoformat(suggestion["proposed_change"]["end"]).astimezone(tz)
    try:
        check_time(ctx, start, end, suggestion["target_id"], suggestion["suggestion_id"])
    except ToolError as error:
        return [str(error)]
    return []
