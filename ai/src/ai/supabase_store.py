"""Data access through Supabase's REST API, with the same methods as FixtureStore.

Every request carries the logged-in user's access token, so Supabase's Row Level
Security only ever returns that user's rows, on top of the user_id filters here.

Tables and columns follow the team's planned schema (meeting notes, Sept 24, and the
frontend's mockData.js): events store start_date/start_time/end_date/end_time in the
user's local time, tasks have a `date`. Rows are converted to the same shape
FixtureStore returns, so the tools can't tell the two stores apart.

Not handled yet: recurring events (recurrence_rule) are treated as one-off events.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx

from ai.schedule import overlaps


class SupabaseStore:
    def __init__(self, url: str, anon_key: str, access_token: str, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": anon_key, "Authorization": f"Bearer {access_token}"},
            timeout=10,
            transport=transport,  # tests pass a fake transport; normally None
        )
        self._users: dict[str, dict] = {}

    def _get(self, table: str, params: list[tuple[str, str]]) -> list[dict]:
        response = self.client.get(f"/{table}", params=[("select", "*"), *params])
        response.raise_for_status()
        return response.json()

    # ---- Same methods as FixtureStore ----

    def user(self, user_id: str) -> dict:
        if user_id not in self._users:
            rows = self._get("users", [("user_id", f"eq.{user_id}")])
            if not rows:
                raise KeyError(f"no user {user_id!r}")
            self._users[user_id] = rows[0]
        return self._users[user_id]

    def events(self, user_id: str, start: datetime, end: datetime) -> list[dict]:
        """This user's events that overlap [start, end), earliest first."""
        # Ask the database for every event on the days involved, then filter exactly here.
        rows = self._get(
            "calendar_events",
            [
                ("user_id", f"eq.{user_id}"),
                ("start_date", f"lte.{end.date().isoformat()}"),
                ("end_date", f"gte.{start.date().isoformat()}"),
            ],
        )
        tz = ZoneInfo(self.user(user_id)["timezone"])
        found = [self._event(row, tz) for row in rows]
        found = [
            e
            for e in found
            if overlaps(datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]), start, end)
        ]
        return sorted(found, key=lambda e: datetime.fromisoformat(e["start"]))

    def event(self, user_id: str, event_id: str) -> dict | None:
        rows = self._get("calendar_events", [("user_id", f"eq.{user_id}"), ("event_id", f"eq.{event_id}")])
        if not rows:
            return None
        return self._event(rows[0], ZoneInfo(self.user(user_id)["timezone"]))

    def tasks(self, user_id: str, first_day: date, last_day: date) -> list[dict]:
        rows = self._get(
            "tasks",
            [("user_id", f"eq.{user_id}"), ("date", f"gte.{first_day.isoformat()}"), ("date", f"lte.{last_day.isoformat()}")],
        )
        return [
            {
                "task_id": str(row["task_id"]),
                "user_id": row["user_id"],
                "name": row["name"],
                "description": row.get("description") or "",
                "due": row["date"],
                "status": row["status"],
                "changeable": bool(row["changeable"]),
            }
            for row in rows
        ]

    def suggestions(self, user_id: str, status: str | None = None) -> list[dict]:
        params = [("user_id", f"eq.{user_id}"), ("order", "created_at.asc")]
        if status:
            params.append(("status", f"eq.{status}"))
        return [self._suggestion(row) for row in self._get("ai_suggestions", params)]

    def add_suggestion(self, user_id: str, suggestion: dict) -> dict:
        response = self.client.post(
            "/ai_suggestions",
            json={"user_id": user_id, "status": "PENDING", **suggestion},
            headers={"Prefer": "return=representation"},  # send back the new row, with its id
        )
        response.raise_for_status()
        return self._suggestion(response.json()[0])

    # ---- Converting rows to the shape the tools expect ----

    @staticmethod
    def _event(row: dict, tz: ZoneInfo) -> dict:
        start = datetime.combine(date.fromisoformat(row["start_date"]), time.fromisoformat(row["start_time"]), tzinfo=tz)
        end_day = date.fromisoformat(row.get("end_date") or row["start_date"])
        end = datetime.combine(end_day, time.fromisoformat(row["end_time"]), tzinfo=tz)
        return {
            "event_id": str(row["event_id"]),
            "user_id": row["user_id"],
            "name": row["name"],
            "start": start.isoformat(),
            "end": end.isoformat(),
            "changeable": bool(row["changeable"]),
        }

    @staticmethod
    def _suggestion(row: dict) -> dict:
        return {
            **row,
            "suggestion_id": str(row["suggestion_id"]),
            "target_id": None if row.get("target_id") is None else str(row["target_id"]),
            "depends_on": [str(s) for s in row.get("depends_on") or []],
        }
