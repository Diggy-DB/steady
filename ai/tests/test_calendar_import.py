"""Tests for importing another calendar (ai/src/ai/calendar_import.py): the address checks, the download, reading a
Google-style .ics file into Steady rows, syncing against a fake Supabase, and the two server endpoints. No network."""

import json
import socket
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from ai import calendar_import as ci
from ai.supabase_store import SupabaseStore
from test_supabase_store import TOKEN, FakeSupabase

DETROIT = ZoneInfo("America/Detroit")
CHICAGO = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=DETROIT)
GOOGLE = "https://calendar.google.com/calendar/ical/alex%40gmail.com/private-abc123/basic.ics"

NEW_YORK = """BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
END:VTIMEZONE
"""


def ics(*events: str, name: str = "alex@gmail.com") -> bytes:
    """A calendar the way Google sends one: CRLF lines, its own time zone, the calendar named after the email."""
    text = ("BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Google Inc//Google Calendar 70.9054//EN\n"
            f"X-WR-CALNAME:{name}\nX-WR-TIMEZONE:America/New_York\n" + NEW_YORK + "".join(events) + "END:VCALENDAR\n")
    return text.replace("\n", "\r\n").encode()


def vevent(uid: str, summary: str, start: str, end: str | None = None, *extra: str) -> str:
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{summary}", f"DTSTART{start}"]
    if end:
        lines.append(f"DTEND{end}")
    return "\n".join([*lines, *extra, "END:VEVENT"]) + "\n"


# Monday standups from Oct 26 (before daylight saving ends on Nov 1), skipping Nov 9, Nov 16 moved to 1 PM.
STANDUP = vevent("standup@google.com", "Standup", ";TZID=America/New_York:20261026T090000",
                 ";TZID=America/New_York:20261026T093000", "RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=10",
                 "EXDATE;TZID=America/New_York:20261109T090000")
MOVED = vevent("standup@google.com", "Standup (moved)", ";TZID=America/New_York:20261116T130000",
               ";TZID=America/New_York:20261116T133000", "RECURRENCE-ID;TZID=America/New_York:20261116T090000")
DENTIST = vevent("dentist@google.com", "Dentist", ":20261119T150000Z", ":20261119T160000Z")
HOLIDAY = vevent("holiday@google.com", "Thanksgiving", ";VALUE=DATE:20261126", ";VALUE=DATE:20261127")
CANCELLED = vevent("party@google.com", "Party", ":20261120T230000Z", ":20261121T020000Z", "STATUS:CANCELLED")
REMINDER = vevent("rent@google.com", "Pay rent", ":20261201T140000Z")  # no end
STEADY = vevent("event-4@steady-planner", "From Steady", ":20261120T150000Z", ":20261120T160000Z")
CALENDAR = ics(STANDUP, MOVED, DENTIST, HOLIDAY, CANCELLED, REMINDER, STEADY)


def rows(data: bytes = CALENDAR, tz: ZoneInfo = DETROIT, first: date = date(2026, 11, 1), last: date = date(2026, 12, 31)):
    return ci.read_calendar(ci.parse_calendar(data), tz, first, last)


# ---- The address ----

@pytest.mark.parametrize("given,expected", [
    ("webcal://p52-caldav.icloud.com/published/2/abc", "https://p52-caldav.icloud.com/published/2/abc"),
    ("  http://example.com/cal.ics ", "https://example.com/cal.ics"),
    (GOOGLE, GOOGLE),
])
def test_addresses_become_https(given, expected):
    assert ci.normalize_link(given) == expected


@pytest.mark.parametrize("given", ["ftp://example.com/a.ics", "calendar.google.com/x", "https://example.com:8080/a.ics",
                                   "https://me:secret@example.com/a.ics", "https:///nohost", "file:///etc/passwd"])
def test_other_addresses_are_refused(given):
    with pytest.raises(ci.CalendarLinkError):
        ci.normalize_link(given)


def resolver(table: dict[str, list[str]]):
    def resolve(host, port, type=0):
        if host not in table:
            raise socket.gaierror("not found")
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, type, 6, "", (a, port)) for a in table[host]]
    return resolve


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.20", "169.254.169.254", "100.64.0.1", "::1",
                                     "fd00::1", "fe80::1%en0", "::ffff:10.0.0.1", "64:ff9b::7f00:1", "0.0.0.0"])
def test_private_and_local_addresses_are_refused(address):
    with pytest.raises(ci.CalendarLinkError, match="private network"):
        ci.check_host("sneaky.example", resolver({"sneaky.example": ["142.250.80.46", address]}))


def test_public_addresses_pass_including_ipv6_only_networks():
    ci.check_host("calendar.google.com", resolver({"calendar.google.com": ["142.250.80.46", "2607:f8b0:4009:80b::200e",
                                                                           "64:ff9b::8efa:502e"]}))


def test_an_unknown_host_is_a_clear_error():
    with pytest.raises(ci.CalendarLinkError, match="Couldn't find"):
        ci.check_host("nope.example", resolver({}))


# ---- The download ----

PUBLIC = resolver({"calendar.google.com": ["142.250.80.46"], "p52-caldav.icloud.com": ["17.248.1.1"],
                   "internal.example": ["10.0.0.7"]})


def fetch(handler, url: str = GOOGLE) -> bytes:
    return ci.fetch_calendar(url, transport=httpx.MockTransport(handler), resolve=PUBLIC)


def test_a_calendar_downloads():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=CALENDAR)

    assert fetch(handler) == CALENDAR
    assert seen[0].headers["user-agent"].startswith("SteadyPlanner")


def test_redirects_are_followed_and_checked_every_time():
    def handler(request):
        if request.url.host == "calendar.google.com":
            return httpx.Response(302, headers={"location": "webcal://p52-caldav.icloud.com/published/2/abc"})
        return httpx.Response(200, content=CALENDAR)

    assert fetch(handler) == CALENDAR

    def to_inside(request):
        return httpx.Response(302, headers={"location": "https://internal.example/admin"})

    with pytest.raises(ci.CalendarLinkError, match="private network"):
        fetch(to_inside)

    with pytest.raises(ci.CalendarLinkError, match="too many"):
        fetch(lambda request: httpx.Response(302, headers={"location": GOOGLE}))


@pytest.mark.parametrize("status,message", [(404, "Secret address"), (403, "Secret address"), (500, "error \\(500\\)")])
def test_errors_from_the_calendar_server_are_plain(status, message):
    with pytest.raises(ci.CalendarLinkError, match=message):
        fetch(lambda request: httpx.Response(status, text="nope"))


def test_a_huge_file_is_cut_off(monkeypatch):
    monkeypatch.setattr(ci, "MAX_BYTES", 1000)
    with pytest.raises(ci.CalendarLinkError, match="too big"):
        fetch(lambda request: httpx.Response(200, content=b"BEGIN:VCALENDAR\r\n" + b"X" * 5000))


def test_a_slow_server_is_a_plain_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ci.CalendarLinkError, match="too long"):
        fetch(handler)


# ---- Reading the calendar ----

def test_a_web_page_is_not_a_calendar():
    with pytest.raises(ci.CalendarLinkError, match="Secret address in iCal format"):
        ci.parse_calendar(b"<!doctype html><html>Google Calendar</html>")


def test_a_repeating_event_happens_on_each_day_at_the_same_local_time():
    standups = [r for r in rows() if r["name"].startswith("Standup")]
    # Nov 2, (Nov 9 skipped), Nov 16 moved, Nov 23, 30, Dec 7, 14, 21, 28 (10 in all from Oct 26)
    assert [r["start_date"] for r in standups] == ["2026-11-02", "2026-11-16", "2026-11-23", "2026-11-30", "2026-12-07",
                                                   "2026-12-14", "2026-12-21", "2026-12-28"]
    assert {r["start_time"] for r in standups if r["name"] == "Standup"} == {"09:00:00"}  # after daylight saving ends too


def test_a_moved_time_keeps_its_place_in_the_series():
    moved = next(r for r in rows() if r["name"] == "Standup (moved)")
    assert (moved["start_time"], moved["end_time"]) == ("13:00:00", "13:30:00")
    assert moved["external_id"] == "standup@google.com|20261116T140000Z"  # the 9 AM it replaced


def test_a_one_off_event_is_known_by_its_uid_and_shown_in_the_users_time_zone():
    [dentist] = [r for r in rows(tz=CHICAGO) if r["name"] == "Dentist"]
    assert dentist == {"external_id": "dentist@google.com", "name": "Dentist", "start_date": "2026-11-19",
                       "start_time": "09:00:00", "end_date": "2026-11-19", "end_time": "10:00:00"}


def test_all_day_cancelled_and_steadys_own_events_are_left_out():
    names = {r["name"] for r in rows()}
    assert not names & {"Thanksgiving", "Party", "From Steady"}


def test_an_event_with_no_end_gets_15_minutes():
    [rent] = [r for r in rows() if r["name"] == "Pay rent"]
    assert (rent["start_time"], rent["end_time"]) == ("09:00:00", "09:15:00")


def test_only_the_window_is_read():
    assert {r["start_date"] for r in rows(first=date(2026, 11, 16), last=date(2026, 11, 23))} == {
        "2026-11-16", "2026-11-19", "2026-11-23"}


def test_an_event_that_ends_after_midnight_ends_the_next_day():
    late = ics(vevent("shift@x", "Late shift", ";TZID=America/New_York:20261120T220000",
                      ";TZID=America/New_York:20261121T013000"))
    [row] = rows(late)
    assert (row["start_date"], row["end_date"], row["end_time"]) == ("2026-11-20", "2026-11-21", "01:30:00")


def test_the_calendar_name():
    assert ci.calendar_name(ci.parse_calendar(CALENDAR), GOOGLE) == "Google Calendar"  # not the email address
    assert ci.calendar_name(ci.parse_calendar(ics(name="MSU classes")), GOOGLE) == "MSU classes"
    assert ci.calendar_name(ci.parse_calendar(ics(name="")), "https://p52-caldav.icloud.com/x") == "iCloud Calendar"


# ---- Syncing ----

def test_plan_sync_adds_changes_and_removes_only_what_differs():
    saved = [
        {"event_id": 1, "external_id": "a", "name": "A", "start_date": "2026-11-19", "start_time": "09:00:00",
         "end_date": "2026-11-19", "end_time": "10:00:00", "changeable": False},
        {"event_id": 2, "external_id": "b", "name": "B", "start_date": "2026-11-19", "start_time": "11:00:00",
         "end_date": "2026-11-19", "end_time": "12:00:00", "changeable": False},
        {"event_id": 3, "external_id": "gone", "name": "Gone", "start_date": "2026-11-20", "start_time": "09:00:00",
         "end_date": "2026-11-20", "end_time": "10:00:00", "changeable": False},
    ]
    wanted = [{k: v for k, v in saved[0].items() if k not in ("event_id", "changeable")},
              {**{k: v for k, v in saved[1].items() if k not in ("event_id", "changeable")}, "start_time": "11:30:00"},
              {"external_id": "new", "name": "New", "start_date": "2026-11-21", "start_time": "09:00:00",
               "end_date": "2026-11-21", "end_time": "10:00:00"}]
    write, remove = ci.plan_sync(saved, wanted)
    assert [r["external_id"] for r in write] == ["b", "new"]
    assert remove == [3]


class FakeWithImports(FakeSupabase):
    """FakeSupabase plus calendar_imports, inserts of several rows, upserts and `in.(...)` filters."""

    def __init__(self):
        super().__init__()
        self.tables["calendar_imports"] = []
        self.next_id = 1000

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or not request.url.path.endswith(("/calendar_events", "/calendar_imports")):
            return super().handle(request)
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        self.requests.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        keys = [k for k in (request.url.params.get("on_conflict") or "").split(",") if k]
        written = []
        for row in body if isinstance(body, list) else [body]:
            same = next((r for r in self.tables[table] if keys and all(r.get(k) == row.get(k) for k in keys)), None)
            if same:
                same.update(row)
                written.append(same)
                continue
            if table == "calendar_imports" and any(r["url"] == row["url"] for r in self.tables[table]):
                return httpx.Response(409, json={"message": "duplicate key"})
            self.next_id += 1
            new = {("import_id" if table == "calendar_imports" else "event_id"): self.next_id, **row}
            if table == "calendar_imports":
                new.update(last_checked_at=None, last_synced_at=None, last_error=None)
            self.tables[table].append(new)
            written.append(new)
        return httpx.Response(201, json=written)

    def matches(self, field, op, value):
        if op == "in":
            return str(field) in value.strip("()").split(",")
        return super().matches(field, op, value)

    def imported(self) -> list[dict]:
        return sorted((e for e in self.tables["calendar_events"] if e.get("import_id")), key=lambda e: e["start_date"])


@pytest.fixture
def fake() -> FakeWithImports:
    return FakeWithImports()


def store(fake) -> SupabaseStore:
    return SupabaseStore("https://example.supabase.co", "anon-key", TOKEN, transport=httpx.MockTransport(fake.handle))


def test_importing_saves_fixed_events_tagged_with_the_import(fake):
    result = ci.add_import(store(fake), "user-1", GOOGLE.replace("https", "webcal"), "", NOW, fetch=lambda url: CALENDAR)
    assert result["ok"] and result["name"] == "Google Calendar"
    [imported] = fake.tables["calendar_imports"]
    assert imported["url"] == GOOGLE and imported["last_synced_at"] and imported["last_error"] is None
    events = fake.imported()
    assert len(events) == result["events"] == result["changed"] > 5
    assert all(e["changeable"] is False and e["import_id"] == imported["import_id"] and e["user_id"] == "user-1"
               and e["recurrence_rule"] is None for e in events)
    assert all(e["start_date"] >= "2026-11-11" for e in events)  # a week back, not older
    with pytest.raises(ci.CalendarLinkError, match="already imported"):
        ci.add_import(store(fake), "user-1", GOOGLE, "", NOW, fetch=lambda url: CALENDAR)


def test_a_bad_calendar_is_refused_before_anything_is_saved(fake):
    with pytest.raises(ci.CalendarLinkError, match="isn't a calendar file"):
        ci.add_import(store(fake), "user-1", GOOGLE, "", NOW, fetch=lambda url: b"<html>sign in</html>")
    assert fake.tables["calendar_imports"] == [] and fake.imported() == []


def test_a_sync_moves_adds_and_removes_events_and_leaves_the_rest(fake):
    s = store(fake)
    ci.add_import(s, "user-1", GOOGLE, "Google", NOW, fetch=lambda url: CALENDAR)
    dentist_id = next(e["event_id"] for e in fake.imported() if e["name"] == "Dentist")
    untouched = len([r for r in fake.requests if r.method == "POST"])

    changed = ics(STANDUP, MOVED, REMINDER, vevent("dentist@google.com", "Dentist", ":20261119T170000Z", ":20261119T180000Z"),
                  vevent("gym@google.com", "Gym", ":20261121T150000Z", ":20261121T160000Z"))  # moved, added; no party
    [result] = ci.sync_imports(s, "user-1", NOW + timedelta(hours=2), fetch=lambda url: changed)
    assert result["ok"] and (result["changed"], result["removed"]) == (2, 0)  # dentist moved, gym added
    dentist = next(e for e in fake.imported() if e["name"] == "Dentist")
    assert dentist["event_id"] == dentist_id and dentist["start_time"] == "12:00:00"  # same row, new time
    assert any(e["name"] == "Gym" for e in fake.imported())
    assert len([r for r in fake.requests if r.method == "POST"]) == untouched + 1  # one request for both

    [result] = ci.sync_imports(s, "user-1", NOW + timedelta(hours=4), fetch=lambda url: ics(STANDUP))
    # the moved standup is back at 9 AM in the same row; the rest are gone
    assert result["removed"] == 3 and {e["name"] for e in fake.imported()} == {"Standup"}


def test_a_failed_sync_keeps_the_events_and_says_why(fake):
    s = store(fake)
    ci.add_import(s, "user-1", GOOGLE, "", NOW, fetch=lambda url: CALENDAR)
    before = len(fake.imported())

    def broken(url):
        raise ci.CalendarLinkError(ci.NOT_FOUND)

    [result] = ci.sync_imports(s, "user-1", NOW + timedelta(hours=2), fetch=broken)
    assert not result["ok"] and "Secret address" in result["error"]
    [imported] = fake.tables["calendar_imports"]
    assert imported["last_error"] == ci.NOT_FOUND and imported["last_synced_at"] == NOW.isoformat()
    assert imported["last_checked_at"] == (NOW + timedelta(hours=2)).isoformat()
    assert len(fake.imported()) == before


def test_when_the_app_opens_only_calendars_not_tried_for_an_hour_sync(fake):
    s = store(fake)
    ci.add_import(s, "user-1", GOOGLE, "", NOW, fetch=lambda url: CALENDAR)
    soon = ci.sync_imports(s, "user-1", NOW + timedelta(minutes=30), older_than=timedelta(hours=1), fetch=lambda url: CALENDAR)
    later = ci.sync_imports(s, "user-1", NOW + timedelta(minutes=90), older_than=timedelta(hours=1), fetch=lambda url: CALENDAR)
    assert soon == [] and len(later) == 1 and later[0]["changed"] == 0


def test_imported_events_are_fixed_for_the_ai(fake):
    from ai.planning import propose_delete, propose_move_event
    from ai.schedule import ToolContext, ToolError

    s = store(fake)
    ci.add_import(s, "user-1", GOOGLE, "", NOW, fetch=lambda url: CALENDAR)
    dentist = next(e for e in fake.imported() if e["name"] == "Dentist")
    ctx = ToolContext(s, "user-1", NOW)
    with pytest.raises(ToolError, match="fixed"):
        propose_move_event(ctx, str(dentist["event_id"]), "2026-11-19 13:00", "2026-11-19 14:00", "Later.")
    with pytest.raises(ToolError, match="fixed"):
        propose_delete(ctx, "event", str(dentist["event_id"]), "Not needed.")


# ---- The server ----

def test_the_endpoints_need_a_real_account(monkeypatch):
    import ai.server

    monkeypatch.setattr(ai.server, "STORE", "fixture")
    api = TestClient(ai.server.app)
    response = api.post("/calendars", json={"url": GOOGLE})
    assert response.status_code == 400 and "real account" in response.json()["detail"]


def test_import_and_sync_through_the_server(monkeypatch, fake):
    import ai.server

    monkeypatch.setattr(ai.server, "STORE", "supabase")
    monkeypatch.setattr(ai.server, "SUPABASE_URL", "https://example.supabase.co")

    class AuthReply:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "user-1"}

    monkeypatch.setattr(ai.server.httpx, "get", lambda url, headers, timeout: AuthReply())
    monkeypatch.setattr(ai.server, "SupabaseStore",
                        lambda url, key, token: SupabaseStore(url, key, token, transport=httpx.MockTransport(fake.handle)))
    monkeypatch.setattr(ci, "fetch_calendar", lambda url: CALENDAR)
    api = TestClient(ai.server.app)
    auth = {"Authorization": f"Bearer {TOKEN}"}

    added = api.post("/calendars", json={"url": GOOGLE, "name": "  My   Google "}, headers=auth)
    assert added.status_code == 200 and added.json()["name"] == "My Google" and added.json()["events"] > 5
    again = api.post("/calendars", json={"url": GOOGLE}, headers=auth)
    assert again.status_code == 400 and "already imported" in again.json()["detail"]
    bad = api.post("/calendars", json={"url": "ftp://example.com/a.ics"}, headers=auth)
    assert bad.status_code == 400

    assert api.post("/calendars/sync", json={"older_than_minutes": 60}, headers=auth).json() == []  # just synced
    [result] = api.post("/calendars/sync", json={}, headers=auth).json()
    assert result["ok"] and result["changed"] == 0
    assert api.post("/calendars/sync", json={"import_id": 999}, headers=auth).status_code == 404
