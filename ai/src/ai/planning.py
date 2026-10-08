"""Planning tools: find free time, and propose changes that the user must accept.

The model never changes the calendar. The propose_* tools only store a PENDING
suggestion, and only after the same checks the backend will repeat when the
user taps Accept: the event exists and belongs to the user, it may be changed,
the new time isn't already over, and it doesn't overlap anything.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai.schedule import MAX_DAYS, ToolContext, ToolError, format_day, format_time, overlaps, parse_day

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


def machine_time(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M}"  # the format the propose tools accept


def describe_range(start: datetime, end: datetime) -> str:
    return f"{format_day(start)}, {format_time(start)} – {format_time(end)}"


def round_up(moment: datetime) -> datetime:
    """The next quarter hour at or after `moment` (6:30 stays 6:30, 6:37 becomes 6:45)."""
    if moment.second or moment.microsecond:
        moment = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return moment + timedelta(minutes=-moment.minute % SLOT_STEP)


def busy(ctx: ToolContext, start: datetime, end: datetime, ignore_event_id: str | None = None) -> list[tuple]:
    """Everything taking up time between start and end: events, plus suggestions still waiting for an answer.

    Pending suggestions count as busy so that several proposals in one plan can't overlap each other.
    """
    tz = user_timezone(ctx)
    taken = []
    for e in ctx.store.events(ctx.user_id, start, end):
        if e["event_id"] != ignore_event_id:
            e_start = datetime.fromisoformat(e["start"]).astimezone(tz)
            e_end = datetime.fromisoformat(e["end"]).astimezone(tz)
            taken.append((e_start, e_end, e["name"]))
    for s in ctx.store.suggestions(ctx.user_id, status="PENDING"):
        s_start = datetime.fromisoformat(s["proposed_change"]["start"]).astimezone(tz)
        s_end = datetime.fromisoformat(s["proposed_change"]["end"]).astimezone(tz)
        if overlaps(s_start, s_end, start, end):
            taken.append((s_start, s_end, f"your pending suggestion {s['suggestion_id']}"))
    return sorted(taken)


def check_time(ctx: ToolContext, start: datetime, end: datetime, ignore_event_id: str | None = None) -> None:
    """Raise ToolError unless [start, end) is free and in the future.

    The same check must run again when the user accepts, because the calendar may have changed since.
    """
    if end <= start:
        raise ToolError("the end time must be after the start time")
    now = ctx.now.astimezone(start.tzinfo)
    if start < now:
        raise ToolError(f"{describe_range(start, end)} has already started; it is now {format_time(now)} on {format_day(now)}")
    clashes = [f"{name} ({describe_range(s, e)})" for s, e, name in busy(ctx, start, end, ignore_event_id)]
    if clashes:
        raise ToolError(f"{describe_range(start, end)} overlaps " + "; ".join(clashes) + ". Use find_free_slots to pick a free time.")


FIND_FREE_SLOTS_TOOL = {
    "type": "function",
    "function": {
        "name": "find_free_slots",
        "description": (
            "Find free blocks of at least `minutes` between two dates (inclusive), between 8 AM and 10 PM, "
            "never in the past. Use the returned start and end values when proposing an event."
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


def find_free_slots(ctx: ToolContext, start_date: str, end_date: str, minutes: int) -> dict:
    first_day = parse_day(start_date, "start_date")
    last_day = parse_day(end_date, "end_date")
    if last_day < first_day:
        raise ToolError("end_date is before start_date")
    if (last_day - first_day).days >= MAX_DAYS:
        raise ToolError(f"ask for at most {MAX_DAYS} days at a time")
    if not isinstance(minutes, int) or not 15 <= minutes <= 12 * 60:
        raise ToolError("minutes must be a whole number from 15 to 720")

    tz = user_timezone(ctx)
    now = ctx.now.astimezone(tz)
    need = timedelta(minutes=minutes)
    free = []
    day = first_day
    while day <= last_day:
        window_start = max(datetime.combine(day, DAY_START, tzinfo=tz), round_up(now))
        window_end = datetime.combine(day, DAY_END, tzinfo=tz)
        if window_start < window_end:
            # Walk through the busy times in order; every gap big enough is a free block.
            cursor = window_start
            gaps = []
            for b_start, b_end, _ in busy(ctx, window_start, window_end):
                gaps.append((cursor, b_start))
                cursor = max(cursor, b_end)
            gaps.append((cursor, window_end))
            for start, end in gaps:
                if end - start >= need:
                    free.append(
                        {
                            "day": format_day(start),
                            "time": f"{format_time(start)} – {format_time(end)}",
                            "minutes": int((end - start).total_seconds() // 60),
                            "start": machine_time(start),
                            "end": machine_time(end),
                        }
                    )
        day += timedelta(days=1)
    return {"now": machine_time(now), "minutes": minutes, "free": free}


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
    check_time(ctx, start_at, end_at)

    suggestion = ctx.store.add_suggestion(
        ctx.user_id,
        {
            "type": "CREATE_EVENT",
            "target_id": None,
            "description": reason,
            "proposed_change": {"name": name.strip(), "start": start_at.isoformat(), "end": end_at.isoformat()},
            "created_at": ctx.now.isoformat(),
            "expires_at": start_at.isoformat(),  # once it would have started, it's no use
        },
    )
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "status": "PENDING",
        "summary": f"Suggested new event '{name.strip()}' on {describe_range(start_at, end_at)}. "
        "Nothing changes until the user accepts it.",
    }


PROPOSE_MOVE_EVENT_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_move_event",
        "description": (
            "Suggest moving one of the user's events to a new time. Nothing changes until the user accepts. "
            "Fails for fixed events (changeable: false), times already over, and overlaps."
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

    tz = user_timezone(ctx)
    old_start = datetime.fromisoformat(event["start"]).astimezone(tz)
    old_end = datetime.fromisoformat(event["end"]).astimezone(tz)
    if old_end <= ctx.now:
        raise ToolError(f"{event['name']} on {describe_range(old_start, old_end)} is already over")
    start_at = parse_local(new_start, "new_start", tz)
    end_at = parse_local(new_end, "new_end", tz)
    check_time(ctx, start_at, end_at, ignore_event_id=event_id)  # it may overlap its own old time

    suggestion = ctx.store.add_suggestion(
        ctx.user_id,
        {
            "type": "MOVE_EVENT",
            "target_id": event_id,
            "description": reason,
            "proposed_change": {"start": start_at.isoformat(), "end": end_at.isoformat()},
            "created_at": ctx.now.isoformat(),
            "expires_at": start_at.isoformat(),
        },
    )
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "status": "PENDING",
        "summary": f"Suggested moving {event['name']} from {describe_range(old_start, old_end)} "
        f"to {describe_range(start_at, end_at)}. Nothing changes until the user accepts it.",
    }
