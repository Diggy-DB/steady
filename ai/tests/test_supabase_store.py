"""Tests for SupabaseStore against a fake Supabase REST API (no network).

The fake serves the fixture week converted to the real tables (supabase/migrations/):
numeric ids, start_date/start_time columns in local time, tasks with `date`. So we can
check that the tools give the same results with either store, and that accepting a
suggestion writes the right rows.
"""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from ai.planning import propose_move_event, propose_new_event
from ai.schedule import FixtureStore, ToolContext, get_schedule
from ai.supabase_store import SupabaseStore

DETROIT = ZoneInfo("America/Detroit")
NOW = datetime(2026, 10, 5, 18, 30, tzinfo=DETROIT)
TOKEN = "user-1-access-token"
ID_COLUMNS = {"calendar_events": "event_id", "tasks": "task_id", "ai_suggestions": "suggestion_id", "activity_log": "log_id"}


def number(fixture_id: str) -> int:
    return int(fixture_id[1:])  # "e2" -> 2, "t1" -> 1


def database_tables() -> dict[str, list[dict]]:
    """The fixture week as rows in the real tables."""
    data = FixtureStore().data
    zones = {u["user_id"]: ZoneInfo(u["timezone"]) for u in data["users"]}
    events = []
    for e in data["events"]:
        start = datetime.fromisoformat(e["start"]).astimezone(zones[e["user_id"]])
        end = datetime.fromisoformat(e["end"]).astimezone(zones[e["user_id"]])
        events.append(
            {"event_id": number(e["event_id"]), "user_id": e["user_id"], "name": e["name"],
             "start_date": start.date().isoformat(), "start_time": f"{start:%H:%M:%S}",
             "end_date": end.date().isoformat(), "end_time": f"{end:%H:%M:%S}",
             "recurrence_rule": None, "changeable": e["changeable"], "created_by": "USER"}
        )
    tasks = [
        {"task_id": number(t["task_id"]), "user_id": t["user_id"], "name": t["name"], "description": t["description"],
         "date": t["due"], "status": t["status"], "changeable": t["changeable"]}
        for t in data["tasks"]
    ]
    return {"users": data["users"], "calendar_events": events, "tasks": tasks, "ai_suggestions": [], "activity_log": []}


class FakeSupabase:
    """Answers GET, POST and PATCH the way Supabase's REST API would, from in-memory tables."""

    def __init__(self):
        self.tables = database_tables()
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        table = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            row = {ID_COLUMNS[table]: 100 + len(self.tables[table]), **json.loads(request.content)}
            self.tables[table].append(row)
            return httpx.Response(201, json=[row])
        rows = self.tables[table]
        for column, condition in request.url.params.multi_items():
            if column in ("select", "order"):
                continue
            op, value = condition.split(".", 1)
            rows = [r for r in rows if self.matches(r.get(column), op, value)]
        if request.method == "PATCH":
            for r in rows:
                r.update(json.loads(request.content))
        return httpx.Response(200, json=rows)

    @staticmethod
    def matches(field, op: str, value: str) -> bool:
        if op == "not":  # e.g. not.is.null
            return not FakeSupabase.matches(field, *value.split(".", 1))
        if op == "is":
            return field is None if value == "null" else str(field).lower() == value
        field = "" if field is None else str(field)
        return {"eq": field == value, "lte": field <= value, "gte": field >= value}[op]


@pytest.fixture
def fake() -> FakeSupabase:
    return FakeSupabase()


def store(fake: FakeSupabase) -> SupabaseStore:
    return SupabaseStore("https://example.supabase.co", "anon-key", TOKEN, transport=httpx.MockTransport(fake.handle))


def without_ids(schedule: dict) -> dict:
    return {**schedule, "events": [{**e, "id": None} for e in schedule["events"]],
            "tasks": [{**t, "id": None} for t in schedule["tasks"]]}


def test_get_schedule_is_the_same_with_either_store(fake):
    from_fixture = get_schedule(ToolContext(FixtureStore(), "user-1", NOW), "2026-10-05", "2026-10-11")
    from_supabase = get_schedule(ToolContext(store(fake), "user-1", NOW), "2026-10-05", "2026-10-11")
    assert without_ids(from_supabase) == without_ids(from_fixture)
    assert from_supabase["events"][0]["id"] == "1"  # database ids reach the model as text


def test_every_query_is_limited_to_the_user(fake):
    get_schedule(ToolContext(store(fake), "user-1", NOW), "2026-10-05", "2026-10-05")
    data_queries = [r for r in fake.requests if not r.url.path.endswith("/users")]
    assert data_queries and all(("user_id", "eq.user-1") in r.url.params.multi_items() for r in data_queries)


def test_proposals_are_saved_as_rows(fake):
    ctx = ToolContext(store(fake), "user-1", NOW)
    result = propose_new_event(ctx, "Gym", "2026-10-07 12:30", "2026-10-07 13:30", "Free after class.")
    assert result["suggestion_id"] == "100"
    [row] = fake.tables["ai_suggestions"]
    assert row["status"] == "PENDING" and row["type"] == "CREATE_EVENT" and row["user_id"] == "user-1"
    assert ctx.store.suggestions("user-1", status="PENDING")[0]["proposed_change"]["name"] == "Gym"


def test_move_suggestion_stores_the_numeric_event_id(fake):
    ctx = ToolContext(store(fake), "user-1", NOW)
    propose_move_event(ctx, "2", "2026-10-05 21:00", "2026-10-05 23:00", "Later.")
    assert fake.tables["ai_suggestions"][0]["target_id"] == 2


def test_applying_a_move_updates_the_event_in_local_time(fake):
    s = store(fake)
    ctx = ToolContext(s, "user-1", NOW)
    propose_move_event(ctx, "2", "2026-10-05 21:00", "2026-10-05 23:00", "Later.")
    [suggestion] = s.suggestions("user-1", status="PENDING")
    s.apply(suggestion)
    s.set_status(suggestion["suggestion_id"], "ACCEPTED")
    event = next(e for e in fake.tables["calendar_events"] if e["event_id"] == 2)
    assert (event["start_date"], event["start_time"], event["end_time"]) == ("2026-10-05", "21:00:00", "23:00:00")
    assert fake.tables["ai_suggestions"][0]["status"] == "ACCEPTED"


def test_applying_a_new_event_marks_it_as_made_by_the_ai(fake):
    s = store(fake)
    propose_new_event(ToolContext(s, "user-1", NOW), "Gym", "2026-10-07 12:30", "2026-10-07 13:30", "")
    s.apply(s.suggestions("user-1")[0])
    new = fake.tables["calendar_events"][-1]
    assert (new["name"], new["created_by"], new["start_time"]) == ("Gym", "AI", "12:30:00")


def test_a_write_that_reaches_no_row_is_an_error(fake):
    with pytest.raises(LookupError):
        store(fake).set_status("999", "ACCEPTED")


def test_activity_is_logged(fake):
    store(fake).log("user-1", "SUGGESTION_ACCEPTED", "ai_suggestion", "100", "USER", {"type": "CREATE_EVENT"})
    assert fake.tables["activity_log"][0]["action"] == "SUGGESTION_ACCEPTED"


def test_unknown_user(fake):
    with pytest.raises(KeyError):
        store(fake).user("nobody")


def test_accepting_a_deadline_adds_a_task_row(fake):
    s = store(fake)
    s.add_suggestion("user-1", {"type": "CREATE_TASK", "target_id": None, "description": "From your syllabus",
                                "proposed_change": {"name": "CSE 260 Homework 1", "due": "2026-10-09T23:59:00-04:00",
                                                    "kind": "deadline", "source": "syllabus"}, "depends_on": []})
    s.apply(s.suggestions("user-1")[0])
    task = fake.tables["tasks"][-1]
    assert (task["name"], task["date"], task["created_by"]) == ("CSE 260 Homework 1", "2026-10-09", "AI")
    assert task["description"] == "Due 11:59 PM. Added from your syllabus."
    assert any(t["name"] == "CSE 260 Homework 1" for t in s.tasks("user-1", date(2026, 10, 5), date(2026, 10, 11)))


def test_a_weekly_class_is_saved_with_its_rule_and_read_back_every_week(fake):
    s = store(fake)
    s.add_suggestion("user-1", {"type": "CREATE_EVENT", "target_id": None, "description": "Weekly class from your syllabus",
                                "proposed_change": {"name": "CSE 260 Lecture", "start": "2026-09-29T12:40:00-04:00",
                                                    "end": "2026-09-29T14:00:00-04:00", "source": "syllabus",
                                                    "recurrence_rule": "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261211"}, "depends_on": []})
    s.apply(s.suggestions("user-1")[0])
    assert fake.tables["calendar_events"][-1]["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20261211"
    week = s.events("user-1", datetime(2026, 10, 5, tzinfo=DETROIT), datetime(2026, 10, 12, tzinfo=DETROIT))
    lectures = [e["start"][:16] for e in week if e["name"] == "CSE 260 Lecture"]
    assert lectures == ["2026-10-06T12:40", "2026-10-08T12:40"]
