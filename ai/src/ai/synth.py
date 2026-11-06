"""Synthetic planning tasks, for collecting TRAINING data.

Everything here is kept apart from the eval scenarios (the test set):
- other weeks (never the eval week of Oct 5-11, 2026) and other time zones,
- other course names, activities and wording,
and tests check that no generated question is the same as an eval question.

Each task is a random week for one fake student, a fake "now", a question, and
checks of the same kind the evals use. A run is only kept as a training example
if it passes every check.
"""

import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai.evals import (
    Scenario,
    calls,
    finishes,
    mentions_all,
    mentions_any,
    moves,
    new_events_named,
    proposes_at_least,
    proposes_nothing,
)
from ai.planning import free_gaps, round_up
from ai.schedule import FixtureStore, ToolContext, format_time, overlaps

USER = "student"
EVAL_WEEK = date(2026, 10, 5)
WEEKS = [date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16),
         date(2026, 11, 30), date(2027, 1, 18), date(2027, 1, 25), date(2027, 2, 1), date(2027, 2, 8)]  # all Mondays
TIMEZONES = ["America/Detroit", "America/Chicago", "America/Denver", "America/Los_Angeles"]
COURSES = ["PHY 183", "CHM 141", "BS 161", "STT 351", "ECN 201", "WRA 101", "CSE 260", "MTH 234", "PSY 101", "LBS 171"]
FIXED_EXTRAS = ["Work shift", "Lab", "Club meeting", "Office hours"]
# Changeable activities: name on the calendar, how a student would say it, and the word a proposal should contain.
ACTIVITIES = {
    "Gym": ("go to the gym", "gym"),
    "Run": ("go for a run", "run"),
    "Reading": ("do some reading", "read"),
    "Piano practice": ("practice piano", "piano"),
    "Study session": ("study", "study"),
}
WORK_TYPES = ["problem set", "essay", "lab report", "project", "quiz prep"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def make_week(rng: random.Random) -> dict:
    """A random, conflict-free week for one student, in the same shape as fixtures/week.json."""
    monday = rng.choice(WEEKS)
    tz = ZoneInfo(rng.choice(TIMEZONES))
    events: list[dict] = []

    def add(name: str, day: int, hour: int, minute: int, minutes: int, changeable: bool) -> None:
        start = datetime.combine(monday + timedelta(days=day), time(hour, minute), tzinfo=tz)
        end = start + timedelta(minutes=minutes)
        for e in events:
            if overlaps(start, end, datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])):
                return  # skip anything that would clash
        events.append(
            {"event_id": f"e{len(events) + 1}", "user_id": USER, "name": name,
             "start": start.isoformat(), "end": end.isoformat(), "changeable": changeable}
        )

    first, second = rng.sample(COURSES, 2)
    hour = rng.choice([9, 10, 11, 13])
    for day in (0, 2, 4):
        add(f"{first} lecture", day, hour, 0, 50, False)
    hour = rng.choice([8, 10, 12, 14])
    for day in (1, 3):
        add(f"{second} lecture", day, hour, 30, 80, False)
    extra, hour, length = rng.choice(FIXED_EXTRAS), rng.choice([15, 16, 17]), rng.choice([60, 120, 180])
    for day in rng.sample(range(5), 2):
        add(extra, day, hour, 0, length, False)
    for _ in range(rng.randint(3, 6)):
        add(rng.choice(list(ACTIVITIES)), rng.randrange(7), rng.choice([7, 12, 14, 18, 19, 20]),
            rng.choice([0, 30]), rng.choice([60, 90, 120]), True)

    tasks = []
    for i, course in enumerate((first, second), start=1):
        hours = rng.randint(2, 4)
        tasks.append(
            {"task_id": f"t{i}", "user_id": USER, "name": f"{course} {rng.choice(WORK_TYPES)}",
             "description": f"About {hours} hours of work.", "due": (monday + timedelta(days=rng.randint(3, 6))).isoformat(),
             "status": rng.choice(["NOT_STARTED", "IN_PROGRESS"]), "changeable": True}
        )
    return {"users": [{"user_id": USER, "first_name": "Jordan", "timezone": tz.key}], "events": events, "tasks": tasks}


# ---- Task types. Each returns (name, question, checks), or None if it doesn't fit this week and time. ----


def upcoming(ctx: ToolContext, day: date) -> list[dict]:
    tz = ctx.now.tzinfo
    start = max(datetime.combine(day, time.min, tzinfo=tz), ctx.now)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return ctx.store.events(USER, start, end) if start < end else []


def short_name(event: dict) -> str:
    """The words an answer should contain to mention this event, e.g. 'phy 183' or 'gym'."""
    name = event["name"].lower()
    return name.removesuffix(" lecture")


def look_up(rng: random.Random, ctx: ToolContext):
    offset = rng.randint(1, 3)
    day = ctx.now.date() + timedelta(days=offset)
    events = upcoming(ctx, day)
    when = "tomorrow" if offset == 1 else DAYS[day.weekday()]
    question = rng.choice(
        [f"What's on my calendar {when}?", f"Anything scheduled for {when}?", f"What does {when} look like for me?"]
    ).replace("for tomorrow", "tomorrow")
    keys = list(dict.fromkeys(short_name(e) for e in events))[:3]
    checks = [calls("get_schedule"), proposes_nothing(), finishes()]
    if keys:
        checks.append(mentions_all(*keys))
    return "look_up", question, checks


def move_flexible(rng: random.Random, ctx: ToolContext):
    today = ctx.now.date()
    for offset in rng.sample(range(0, 4), 4):
        day = today + timedelta(days=offset)
        events = upcoming(ctx, day)
        names = [e["name"] for e in events]
        candidates = [e for e in events if e["changeable"] and names.count(e["name"]) == 1]
        for event in candidates:
            length = datetime.fromisoformat(event["end"]) - datetime.fromisoformat(event["start"])
            # Start on a quarter hour (lectures end at :50), and only where the event still fits.
            gaps = [(round_up(s), e) for s, e in free_gaps(ctx, day, length) if s.hour >= 9]
            gaps = [(s, e) for s, e in gaps if e - s >= length]
            if gaps:
                target = rng.choice(gaps)[0]
                when = "today" if offset == 0 else DAYS[day.weekday()]
                question = f"Can you move my {event['name'].lower()} on {when} to {format_time(target)}?".replace(" on today", " today")
                return "move_flexible", question, [moves(event["event_id"], to=f"{target:%H:%M}"), finishes()]
    return None


def move_fixed(rng: random.Random, ctx: ToolContext):
    lectures = [e for e in ctx.store.data["events"] if not e["changeable"] and "lecture" in e["name"]
                and datetime.fromisoformat(e["start"]) > ctx.now]
    if not lectures:
        return None
    event = rng.choice(lectures)
    later = DAYS[(datetime.fromisoformat(event["start"]).weekday() + 1) % 7]
    question = rng.choice([f"Please move my {event['name']} to {later} evening.", f"Can my {event['name']} go to {later} instead?"])
    return "move_fixed", question, [proposes_nothing(), mentions_any("fixed", "can't", "cannot", "not able", "unable"), finishes()]


def task_time(rng: random.Random, ctx: ToolContext):
    for task in rng.sample(ctx.store.data["tasks"], len(ctx.store.data["tasks"])):
        due = date.fromisoformat(task["due"])
        hours = int(task["description"].split()[1])
        free_minutes = sum(
            (end - start).total_seconds() // 60
            for offset in range((due - ctx.now.date()).days + 1)
            for start, end in free_gaps(ctx, ctx.now.date() + timedelta(days=offset), timedelta(minutes=60))
        )
        if free_minutes >= hours * 60 + 120:  # enough room to plan it comfortably
            course = task["name"].split(" ")[0].lower()  # e.g. "phy"
            question = rng.choice(
                [f"I still need to do my {task['name']}. When should I work on it?",
                 f"Help me find time for my {task['name']} before it's due."]
            )
            return "task_time", question, [proposes_at_least(1), new_events_named((course,), minutes=hours * 60), finishes()]
    return None


def activity_today(rng: random.Random, ctx: ToolContext):
    name = rng.choice(list(ACTIVITIES))
    phrase, word = ACTIVITIES[name]
    if not free_gaps(ctx, ctx.now.date(), timedelta(minutes=60)):
        return None
    question = rng.choice([f"When could I {phrase} today?", f"Is there time to {phrase} today?"])
    return "activity_today", question, [calls("find_free_slots"), proposes_at_least(1), finishes()]


def weekly_goal(rng: random.Random, ctx: ToolContext):
    name = rng.choice(list(ACTIVITIES))
    phrase, word = ACTIVITIES[name]
    week_start = date.fromisoformat(ctx.store.data["events"][0]["start"][:10])
    week_end = week_start + timedelta(days=6)
    # Sessions earlier this week count too ("run 3 times this week" after running this morning: 2 more),
    # the same rule the eval cases use; counting only upcoming ones taught the opposite.
    already = sum(
        1 for e in ctx.store.data["events"]
        if e["name"] == name and week_start <= datetime.fromisoformat(e["start"]).date() <= week_end
    )
    free_days = sum(
        1 for offset in range((week_end - ctx.now.date()).days + 1)
        if free_gaps(ctx, ctx.now.date() + timedelta(days=offset), timedelta(minutes=60))
    )
    goal = already + rng.randint(1, 2)
    if free_days < goal - already:
        return None
    times = {1: "once", 2: "twice"}.get(goal, f"{goal} times")
    question = f"I want to {phrase} {times} this week, an hour each. Can you plan it?"
    return "weekly_goal", question, [new_events_named((word,), count=goal - already), finishes()]


TASK_TYPES = [look_up, move_flexible, move_fixed, task_time, activity_today, weekly_goal]


def make_task(seed: int) -> Scenario:
    """One reproducible training task: the same seed always gives the same task."""
    rng = random.Random(seed)
    while True:
        data = make_week(rng)
        tz = ZoneInfo(data["users"][0]["timezone"])
        monday = date.fromisoformat(data["events"][0]["start"][:10])
        now = datetime.combine(monday + timedelta(days=rng.randint(0, 3)), time(rng.randint(8, 19), rng.choice([0, 30])), tzinfo=tz)
        ctx = ToolContext(FixtureStore(data=data), USER, now)
        for task_type in rng.sample(TASK_TYPES, len(TASK_TYPES)):
            made = task_type(rng, ctx)
            if made:
                name, question, checks = made
                return Scenario(f"{name}-{seed}", question, checks, now=f"{now:%Y-%m-%d %H:%M}", user_id=USER, data=data)
