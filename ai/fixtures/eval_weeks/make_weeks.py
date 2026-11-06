"""Build the eval weeks: four students' weeks, chosen to hit edge cases. EVAL ONLY: synth.py (training
data) never uses these dates, and tests/test_synth.py checks that.

    maya.json    Oct 12-18 2026, America/Chicago    packed week: classes, a lab, a job, an evening midterm,
                                                    sports; little free time; several similar events
    chris.json   Nov 23-29 2026, America/Los_Angeles  Thanksgiving week: light, travel, a holiday dinner
    riley.json   Mar 8-14 2027, America/New_York    daylight saving starts Sun Mar 14 at 2 AM; an overnight
                                                    shift crosses midnight and the time change; some events
                                                    stored in UTC
    priya.json   Dec 7-13 2026, Asia/Kolkata (UTC+5:30)  finals week: exams, six "Study session"s, a
                                                    half-hour time zone

Each file also has a second user whose events must never show up (user isolation).
fixtures/week.json (Alex, Oct 5-11 2026) stays the fifth week.

    uv run python fixtures/eval_weeks/make_weeks.py
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent


class Week:
    def __init__(self, name: str, tz: str, monday: date):
        self.name, self.tz, self.monday = name, ZoneInfo(tz), monday
        self.events, self.tasks = [], []
        self.users = [{"user_id": "user-1", "first_name": name.title(), "timezone": tz},
                      {"user_id": "user-2", "first_name": "Other", "timezone": "America/Detroit"}]

    def at(self, day: int, hhmm: str) -> datetime:
        """Local time on the week's day (0 = Monday; 7 = the next Monday)."""
        h, m = map(int, hhmm.split(":"))
        return datetime.combine(self.monday + timedelta(days=day), datetime.min.time(), tzinfo=self.tz).replace(hour=h, minute=m)

    def event(self, eid: str, name: str, day: int, start: str, end: str, changeable: bool, end_day: int | None = None,
              utc: bool = False, user: str = "user-1") -> None:
        begin, finish = self.at(day, start), self.at(day if end_day is None else end_day, end)
        if utc:  # some calendars store times in UTC; the tools must still show local times
            begin, finish = begin.astimezone(timezone.utc), finish.astimezone(timezone.utc)
        self.events.append({"event_id": eid, "user_id": user, "name": name,
                            "start": begin.isoformat().replace("+00:00", "Z") if utc else begin.isoformat(),
                            "end": finish.isoformat().replace("+00:00", "Z") if utc else finish.isoformat(),
                            "changeable": changeable})

    def task(self, tid: str, name: str, due_day: int, hours: float | None, status: str = "NOT_STARTED") -> None:
        description = f"About {hours:g} hour{'' if hours == 1 else 's'} of work." if hours else ""
        self.tasks.append({"task_id": tid, "user_id": "user-1", "name": name, "description": description,
                           "due": (self.monday + timedelta(days=due_day)).isoformat(), "status": status,
                           "changeable": True})

    def check(self) -> None:
        mine = sorted((datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]), e["name"])
                      for e in self.events if e["user_id"] == "user-1")
        for (s1, e1, n1), (s2, e2, n2) in zip(mine, mine[1:]):
            assert e1 <= s2, f"{self.name}: {n1} overlaps {n2}"
        assert all(datetime.fromisoformat(e["end"]) > datetime.fromisoformat(e["start"]) for e in self.events)
        assert len({e["event_id"] for e in self.events}) == len(self.events)

    def save(self) -> None:
        self.check()
        data = {"users": self.users, "events": self.events, "tasks": self.tasks}
        (HERE / f"{self.name}.json").write_text(json.dumps(data, indent=2) + "\n")


def maya() -> Week:
    w = Week("maya", "America/Chicago", date(2026, 10, 12))
    n = 0

    def ev(*args, **kw):
        nonlocal n
        n += 1
        w.event(f"m{n}", *args, **kw)

    for d in (0, 2, 4):
        ev("Gym", d, "06:30", "07:30", True) if d in (0, 4) else None
        ev("BIO 201 lecture", d, "08:00", "08:50", False)
        ev("CHM 141 lecture", d, "09:10", "10:00", False)
    for d in (0, 2):
        ev("Library job", d, "13:00", "17:00", False)
    for d in (1, 3):
        ev("STT 200 lecture", d, "10:20", "11:40", False)
        ev("Soccer practice", d, "18:00", "19:30", True)
    ev("CHM 141 lab", 1, "14:00", "16:50", False)
    ev("Study session", 0, "19:00", "21:00", True)
    ev("Study group", 2, "19:00", "21:00", True)
    ev("STT 200 midterm", 3, "19:30", "21:00", False, utc=True)
    ev("Study session", 4, "15:00", "17:00", True)
    ev("Dinner with family", 6, "17:00", "19:00", True)
    w.event("x1", "Gym", 1, "07:00", "08:00", True, user="user-2")
    w.task("mt1", "CHM 141 problem set", 2, 3)
    w.task("mt2", "BIO 201 lab report", 4, 2)
    w.task("mt3", "WRA 101 essay draft", 7, 4)
    w.task("mt4", "Pay rent", 0, None, status="COMPLETED")
    return w


def chris() -> Week:
    w = Week("chris", "America/Los_Angeles", date(2026, 11, 23))
    w.event("c1", "Morning run", 0, "07:00", "07:45", True)
    w.event("c2", "ECON 101 lecture", 0, "11:00", "12:20", False)
    w.event("c3", "Work shift", 1, "16:00", "20:00", False)
    w.event("c4", "ECON 101 lecture", 2, "11:00", "12:20", False)
    w.event("c5", "Flight home (SFO to SEA)", 2, "18:00", "20:15", False)
    w.event("c6", "Thanksgiving dinner", 3, "15:00", "19:00", False)
    w.event("c7", "Movie night with friends", 5, "20:00", "22:30", True)
    w.event("c8", "Flight back (SEA to SFO)", 6, "13:00", "15:15", False)
    w.event("x1", "Thanksgiving dinner", 3, "12:00", "14:00", False, user="user-2")
    w.task("ct1", "ECON 101 reading", 7, 2)
    w.task("ct2", "Holiday shopping list", 2, 0.5)
    return w


def riley() -> Week:
    w = Week("riley", "America/New_York", date(2027, 3, 8))
    for d in (0, 2, 4):
        w.event(f"r{d + 1}", "MTH 235 lecture", d, "12:40", "13:30", False)
    for i, d in enumerate((1, 3)):
        w.event(f"r{10 + i}", "PHY 184 lecture", d, "15:00", "16:20", False, utc=True)
    w.event("r20", "Study session", 1, "19:00", "21:00", True)
    w.event("r21", "Band rehearsal", 2, "20:00", "22:00", True)
    w.event("r22", "Gym", 3, "07:00", "08:00", True)
    # Saturday 10 PM to Sunday 6 AM local: only 7 hours, because clocks skip 2-3 AM on Sunday
    w.event("r23", "Night shift at the hospital", 5, "22:00", "06:00", False, end_day=6, utc=True)
    w.event("r24", "Brunch with roommates", 6, "11:00", "12:30", True)
    w.event("x1", "Study session", 1, "19:00", "21:00", True, user="user-2")
    w.task("rt1", "MTH 235 homework", 4, 2)
    w.task("rt2", "PHY 184 lab writeup", 7, 3)
    return w


def priya() -> Week:
    w = Week("priya", "Asia/Kolkata", date(2026, 12, 7))
    for d in range(6):
        w.event(f"p{d + 1}", "Study session", d, "10:00", "12:00", True)
    w.event("p10", "Remote work", 0, "15:00", "18:00", False)
    w.event("p11", "Remote work", 2, "15:00", "18:00", False)
    w.event("p12", "CSE 331 final exam", 1, "19:45", "21:45", False)
    w.event("p13", "MTH 309 final exam", 3, "12:45", "14:45", False)
    w.event("p14", "Call with family", 6, "09:00", "10:00", True)
    w.event("x1", "CSE 331 final exam", 1, "19:45", "21:45", False, user="user-2")
    w.task("pt1", "CSE 331 final review", 1, 4)
    w.task("pt2", "MTH 309 practice exam", 3, 2)
    w.task("pt3", "Pack for winter break", 5, 1)
    return w


if __name__ == "__main__":
    for week in (maya(), chris(), riley(), priya()):
        week.save()
        print(f"{week.name}: {sum(e['user_id'] == 'user-1' for e in week.events)} events, {len(week.tasks)} tasks")
