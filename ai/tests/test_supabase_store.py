"""Tests for SupabaseStore against a fake Supabase REST API (no network).

The fake serves the fixture week converted to the team's planned schema
(start_date/start_time columns, tasks with `date`), so we can check that the
tools give exactly the same results with either store.
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from ai.planning import propose_new_event
from ai.schedule import FixtureStore, ToolContext, get_schedule
from ai.supabase_store import SupabaseStore

DETROIT = ZoneInfo("America/Detroit")
NOW = datetime(2026, 10, 5, 18, 30, tzinfo=DETROIT)
TOKEN = "user-1-access-token"


def planned_schema_tables() -> dict[str, list[dict]]:
    """The fixture week as rows in the team's planned tables."""
    data = FixtureStore().data
    zones = {u["user_id"]: ZoneInfo(u["timezone"]) for u in data["users"]}
    events = []
    for e in data["events"]:
        start = datetime.fromisoformat(e["start"]).astimezone(zones[e["user_id"]])
        end = datetime.fromisoformat(e["end"]).astimezone(zones[e["user_id"]])
        events.append(
            {
                "event_id": e["event_id"],
                "user_id": e["user_id"],
                "name": e["name"],
                "start_date": start.date().isoformat(),
                "start_time": f"{start:%H:%M:%S}",
                "end_date": end.date().isoformat(),
                "end_time": f"{end:%H:%M:%S}",
                "recurrence_rule": None,
                "changeable": e["changeable"],
                "created_by": "USER",
            }
        )
    tasks = [{**{k: v for k, v in t.items() if k != "due"}, "date": t["due"]} for t in data["tasks"]]
    return {"users": data["users"], "calendar_events": events, "tasks": tasks, "ai_suggestions": []}


class FakeSupabase:
    """Answers GET and POST requests the way Supabase's REST API would, from in-memory tables."""

    def __init__(self):
        self.tables = planned_schema_tables()
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        table = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            row = {"suggestion_id": len(self.tables[table]) + 1, **json.loads(request.content)}
            self.tables[table].append(row)
            return httpx.Response(201, json=[row])
        rows = self.tables[table]
        for column, condition in request.url.params.multi_items():
            if column in ("select", "order"):
                continue
            op, value = condition.split(".", 1)
            rows = [r for r in rows if self.matches(r.get(column), op, value)]
        return httpx.Response(200, json=rows)

    @staticmethod
    def matches(field, op: str, value: str) -> bool:
        field = "" if field is None else str(field)
        return {"eq": field == value, "lte": field <= value, "gte": field >= value}[op]


@pytest.fixture
def fake() -> FakeSupabase:
    return FakeSupabase()


def store(fake: FakeSupabase) -> SupabaseStore:
    return SupabaseStore("https://example.supabase.co", "anon-key", TOKEN, transport=httpx.MockTransport(fake.handle))


def test_get_schedule_is_the_same_with_either_store(fake):
    from_fixture = get_schedule(ToolContext(FixtureStore(), "user-1", NOW), "2026-10-05", "2026-10-11")
    from_supabase = get_schedule(ToolContext(store(fake), "user-1", NOW), "2026-10-05", "2026-10-11")
    assert from_supabase == from_fixture


def test_every_query_is_limited_to_the_user(fake):
    get_schedule(ToolContext(store(fake), "user-1", NOW), "2026-10-05", "2026-10-05")
    data_queries = [r for r in fake.requests if not r.url.path.endswith("/users")]
    assert data_queries and all(("user_id", "eq.user-1") in r.url.params.multi_items() for r in data_queries)


def test_proposals_are_saved_as_rows(fake):
    ctx = ToolContext(store(fake), "user-1", NOW)
    result = propose_new_event(ctx, "Gym", "2026-10-07 12:30", "2026-10-07 13:30", "Free after class.")
    assert result["suggestion_id"] == "1"
    [row] = fake.tables["ai_suggestions"]
    assert row["status"] == "PENDING" and row["type"] == "CREATE_EVENT" and row["user_id"] == "user-1"
    assert ctx.store.suggestions("user-1", status="PENDING")[0]["proposed_change"]["name"] == "Gym"


def test_unknown_user(fake):
    with pytest.raises(KeyError):
        store(fake).user("nobody")
