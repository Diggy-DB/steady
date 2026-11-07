"""Repeating events: the recurrence_rule column, read the same way here and in the app's calendar.

A rule is a small subset of iCalendar's RRULE, e.g. "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20270430".
Supported parts: FREQ (DAILY or WEEKLY), INTERVAL, BYDAY, UNTIL (a date, inclusive), COUNT, and
X-SKIP, a list of days with no occurrence (breaks), e.g. "X-SKIP=20270309,20270311".
Front-end/src/lib/recurrence.js is the same logic for the calendar.
"""

from datetime import date, datetime, timedelta, tzinfo

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
LIMIT = 1000  # never expand more than this many occurrences of one rule


def parse(rule: str) -> dict:
    """The rule's parts as a dict; raises ValueError for a rule this module can't follow."""
    parts = dict(p.split("=", 1) for p in rule.strip().removeprefix("RRULE:").split(";") if "=" in p)
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        raise ValueError(f"unsupported recurrence {rule!r}")
    days = [d[-2:] for d in parts["BYDAY"].split(",")] if parts.get("BYDAY") else []
    if any(d not in WEEKDAYS for d in days):
        raise ValueError(f"unsupported BYDAY in {rule!r}")
    return {
        "freq": freq,
        "interval": max(1, int(parts.get("INTERVAL", "1"))),
        "days": [WEEKDAYS.index(d) for d in days],
        "until": datetime.strptime(parts["UNTIL"][:8], "%Y%m%d").date() if parts.get("UNTIL") else None,
        "count": int(parts["COUNT"]) if parts.get("COUNT") else None,
        "skip": {datetime.strptime(d, "%Y%m%d").date() for d in parts["X-SKIP"].split(",") if d} if parts.get("X-SKIP") else set(),
    }


def days(first: date, rule: str, last: date) -> list[date]:
    """Every day the event happens, from its first day up to `last` (inclusive)."""
    r = parse(rule)
    weekdays = r["days"] or [first.weekday()]
    end = min(last, r["until"]) if r["until"] else last
    found, counted = [], 0
    week_start = first - timedelta(days=first.weekday())
    day = first
    while day <= end and counted < LIMIT and (r["count"] is None or counted < r["count"]):
        if r["freq"] == "DAILY":
            happens = (day - first).days % r["interval"] == 0
        else:
            happens = day.weekday() in weekdays and ((day - week_start).days // 7) % r["interval"] == 0
        if happens:
            counted += 1  # COUNT counts skipped days too, as EXDATE does in iCalendar
            if day not in r["skip"]:
                found.append(day)
        day += timedelta(days=1)
    return found


def occurrences(event: dict, start: datetime, end: datetime, tz: tzinfo | None = None) -> list[dict]:
    """Copies of a repeating event (with "start"/"end" ISO strings) for each time it overlaps [start, end).

    `tz` is the user's time zone: a 9:00 class stays at 9:00 local time after a daylight saving change.
    A one-off event comes back as itself if it overlaps. Each copy keeps the series' event_id and is
    marked not changeable: moving one class would move the whole series.
    """
    first_start = datetime.fromisoformat(event["start"])
    first_end = datetime.fromisoformat(event["end"])
    if not event.get("recurrence_rule"):
        return [event] if first_start < end and start < first_end else []
    tz = tz or first_start.tzinfo
    local = first_start.astimezone(tz)
    length = first_end - first_start
    found = []
    for day in days(local.date(), event["recurrence_rule"], end.astimezone(tz).date()):
        s = datetime.combine(day, local.time(), tzinfo=tz)
        e = s + length
        if s < end and start < e:
            found.append({**event, "start": s.isoformat(), "end": e.isoformat(), "changeable": False})
    return found


def last_day(rule: str) -> date | None:
    """The rule's UNTIL day, or None if it has none."""
    return parse(rule)["until"]
