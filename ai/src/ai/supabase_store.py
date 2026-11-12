"""Data access through Supabase's REST API, with the same methods as FixtureStore.

Every request carries the logged-in user's access token, so Supabase's Row Level
Security only ever returns that user's rows, on top of the user_id filters here.

Tables and columns follow the team's planned schema (meeting notes, Sept 24, and the
frontend's mockData.js): events store start_date/start_time/end_date/end_time in the
user's local time, tasks have a `date`. Rows are converted to the same shape
FixtureStore returns, so the tools can't tell the two stores apart.

Recurring events (recurrence_rule) are read as one-off events on their first day; the app's calendar
expands them. Accepting a CREATE_TASK suggestion inserts a row in tasks.
The tables are created by supabase/migrations/20261015120000_steady_planner_schema.sql.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx

from ai.recurrence import occurrences
from ai.schedule import journal_text, task_description


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
        # Ask the database for every event on the days involved, plus every repeating event that has
        # started by then, and filter exactly here (repeating events once per time they happen).
        one_off = self._get(
            "calendar_events",
            [
                ("user_id", f"eq.{user_id}"),
                ("recurrence_rule", "is.null"),
                ("start_date", f"lte.{end.date().isoformat()}"),
                ("end_date", f"gte.{start.date().isoformat()}"),
            ],
        )
        repeating = self._get(
            "calendar_events",
            [("user_id", f"eq.{user_id}"), ("recurrence_rule", "not.is.null"), ("start_date", f"lte.{end.date().isoformat()}")],
        )
        tz = ZoneInfo(self.user(user_id)["timezone"])
        found = []
        for row in one_off + repeating:
            try:
                found += occurrences(self._event(row, tz), start, end, tz)
            except ValueError:  # a rule the AI can't follow: count only its first day
                found += occurrences({**self._event(row, tz), "recurrence_rule": None}, start, end, tz)
        return sorted(found, key=lambda e: datetime.fromisoformat(e["start"]))

    def event(self, user_id: str, event_id: str) -> dict | None:
        if not str(event_id).isdigit():  # event ids are numbers in the database; "e2" would be a database error
            return None
        rows = self._get("calendar_events", [("user_id", f"eq.{user_id}"), ("event_id", f"eq.{event_id}")])
        if not rows:
            return None
        event = self._event(rows[0], ZoneInfo(self.user(user_id)["timezone"]))
        return {**event, "changeable": False} if event.get("recurrence_rule") else event  # a series moves as one

    def tasks(self, user_id: str, first_day: date, last_day: date) -> list[dict]:
        rows = self._get(
            "tasks",
            [("user_id", f"eq.{user_id}"), ("date", f"gte.{first_day.isoformat()}"), ("date", f"lte.{last_day.isoformat()}")],
        )
        return [self._task(row) for row in rows]

    def task(self, user_id: str, task_id: str) -> dict | None:
        if not str(task_id).isdigit():  # task ids are numbers in the database; anything else can't exist
            return None
        rows = self._get("tasks", [("user_id", f"eq.{user_id}"), ("task_id", f"eq.{task_id}")])
        return self._task(rows[0]) if rows else None

    def journal(self, user_id: str, journal_id: str) -> dict | None:
        rows = self._get("journals", [("user_id", f"eq.{user_id}"), ("journal_id", f"eq.{journal_id}")])
        return rows[0] if rows else None

    def journal_on(self, user_id: str, day: date) -> dict | None:
        rows = self._get("journals", [("user_id", f"eq.{user_id}"), ("date", f"eq.{day.isoformat()}")])
        return rows[0] if rows else None

    def journals(self, user_id: str, first_day: date, last_day: date) -> list[dict]:
        return self._get("journals", [("user_id", f"eq.{user_id}"), ("date", f"gte.{first_day.isoformat()}"),
                                      ("date", f"lte.{last_day.isoformat()}"), ("order", "date.asc")])

    def overview(self, user_id: str, day: date) -> dict | None:
        rows = self._get("daily_overviews", [("user_id", f"eq.{user_id}"), ("date", f"eq.{day.isoformat()}")])
        return rows[0]["overview"] if rows else None

    def save_overview(self, user_id: str, day: date, overview: dict) -> None:
        """Insert, or replace the day's overview (a refresh), in one request."""
        response = self.client.post(
            "/daily_overviews", params=[("on_conflict", "user_id,date")],
            json={"user_id": user_id, "date": day.isoformat(), "overview": overview},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        response.raise_for_status()

    def suggestions(self, user_id: str, status: str | None = None) -> list[dict]:
        params = [("user_id", f"eq.{user_id}"), ("order", "created_at.asc")]
        if status:
            params.append(("status", f"eq.{status}"))
        return [self._suggestion(row) for row in self._get("ai_suggestions", params)]

    def add_suggestion(self, user_id: str, suggestion: dict) -> dict:
        target = suggestion.get("target_id")
        response = self.client.post(
            "/ai_suggestions",
            json={
                "user_id": user_id,
                "status": "PENDING",
                **suggestion,
                "target_id": int(target) if target is not None else None,  # event ids are numbers in the database
            },
            headers={"Prefer": "return=representation"},  # send back the new row, with its id
        )
        response.raise_for_status()
        return self._suggestion(response.json()[0])

    # ---- Writes used when the user accepts or declines a suggestion ----

    def _write(self, method: str, table: str, params: list[tuple[str, str]] | None, body: dict) -> list[dict]:
        """Insert or update rows; returns the rows written (an empty list means RLS or a filter matched nothing)."""
        response = self.client.request(
            method, f"/{table}", params=params or [], json=body, headers={"Prefer": "return=representation"}
        )
        response.raise_for_status()
        return response.json()

    def _delete(self, table: str, params: list[tuple[str, str]]) -> list[dict]:
        """Delete rows; returns the rows deleted (an empty list means RLS or a filter matched nothing)."""
        response = self.client.request("DELETE", f"/{table}", params=params, headers={"Prefer": "return=representation"})
        response.raise_for_status()
        return response.json()

    def set_status(self, suggestion_id: str, status: str) -> None:
        if not self._write("PATCH", "ai_suggestions", [("suggestion_id", f"eq.{suggestion_id}")], {"status": status}):
            raise LookupError(f"suggestion {suggestion_id} wasn't updated")

    def claim(self, suggestion_id: str, from_status: str, to_status: str) -> bool:
        """Change the status only if it is still `from_status`, in one UPDATE ... WHERE status = from_status, so
        two requests at once (a double tap on Accept) can't both get it. False if another request got there first."""
        params = [("suggestion_id", f"eq.{suggestion_id}"), ("status", f"eq.{from_status}")]
        return bool(self._write("PATCH", "ai_suggestions", params, {"status": to_status}))

    def apply(self, suggestion: dict) -> None:
        """Make an accepted suggestion real (events, tasks, journals), with the user's own token."""
        tz = ZoneInfo(self.user(suggestion["user_id"])["timezone"])
        change = suggestion["proposed_change"]
        user = ("user_id", f"eq.{suggestion['user_id']}")
        if suggestion["type"] in ("DELETE_EVENT", "DELETE_TASK", "DELETE_JOURNAL"):
            table, key = {"DELETE_EVENT": ("calendar_events", "event_id"), "DELETE_TASK": ("tasks", "task_id"),
                          "DELETE_JOURNAL": ("journals", "date")}[suggestion["type"]]
            if not self._delete(table, [user, (key, f"eq.{change['id']}")]):
                raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied: it's already gone")
            return
        if suggestion["type"] == "EDIT_JOURNAL":  # replace the day's text (recheck made sure it's unchanged)
            written = self._write("PATCH", "journals", [user, ("date", f"eq.{change['date']}")], {"information": change["text"]})
            if not written:
                raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied: the entry is gone")
            return
        if suggestion["type"] == "ADD_JOURNAL":  # add to the day's entry, or start one
            entry = self.journal_on(suggestion["user_id"], date.fromisoformat(change["date"]))
            if entry:
                written = self._write("PATCH", "journals", [user, ("journal_id", f"eq.{entry['journal_id']}")],
                                      {"information": journal_text(entry["information"], change["text"])})
            else:
                written = self._write("POST", "journals", None, {"user_id": suggestion["user_id"], "date": change["date"],
                                                                  "information": change["text"]})
            if not written:
                raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied")
            return
        if suggestion["type"] == "CREATE_TASK":  # a deadline: a row in tasks, due that day
            due = datetime.fromisoformat(change["due"]).astimezone(tz)
            body = {"user_id": suggestion["user_id"], "name": change["name"], "description": (change.get("description", "") if change.get("kind") == "task" else task_description(due)),
                    "date": due.date().isoformat(), "status": "NOT_STARTED", "changeable": True, "created_by": "AI"}
            if not self._write("POST", "tasks", None, body):
                raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied")
            return
        start = datetime.fromisoformat(change["start"]).astimezone(tz)
        end = datetime.fromisoformat(change["end"]).astimezone(tz)
        times = {
            "start_date": start.date().isoformat(),
            "start_time": f"{start:%H:%M:%S}",
            "end_date": end.date().isoformat(),
            "end_time": f"{end:%H:%M:%S}",
        }
        if suggestion["type"] == "CREATE_EVENT":
            body = {"user_id": suggestion["user_id"], "name": change["name"], **times, "changeable": True, "created_by": "AI",
                    "recurrence_rule": change.get("recurrence_rule")}
            written = self._write("POST", "calendar_events", None, body)
        else:
            written = self._write("PATCH", "calendar_events", [("event_id", f"eq.{suggestion['target_id']}")], times)
        if not written:
            raise LookupError(f"suggestion {suggestion['suggestion_id']} couldn't be applied")

    def log(self, user_id: str, action: str, target_type: str, target_id: str, performed_by: str, details: dict) -> None:
        body = {"user_id": user_id, "action": action, "target_type": target_type, "target_id": target_id,
                "performed_by": performed_by, "details": details}
        self._write("POST", "activity_log", None, body)

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
            **({"recurrence_rule": row["recurrence_rule"]} if row.get("recurrence_rule") else {}),
        }

    @staticmethod
    def _task(row: dict) -> dict:
        return {
            "task_id": str(row["task_id"]),
            "user_id": row["user_id"],
            "name": row["name"],
            "description": row.get("description") or "",
            "due": row["date"],
            "status": row["status"],
            "changeable": bool(row["changeable"]),
            "updated_at": row.get("updated_at"),  # when it was last changed, e.g. marked done
        }

    @staticmethod
    def _suggestion(row: dict) -> dict:
        return {
            **row,
            "suggestion_id": str(row["suggestion_id"]),
            "target_id": None if row.get("target_id") is None else str(row["target_id"]),
            "depends_on": [str(s) for s in row.get("depends_on") or []],
        }
