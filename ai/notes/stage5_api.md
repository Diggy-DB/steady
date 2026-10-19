# Stage 5: the backend API (AI chat + suggestions)

`src/ai/server.py` is the backend: a FastAPI app around the agent. Everyday reading and
writing of events, tasks and journal entries goes straight from the frontend to Supabase
(protected by Row Level Security); this API handles everything that needs server-side logic:
the AI chat, and accepting or declining the AI's suggestions with every rule checked again.

Run it from `ai/`:

```bash
uv run uvicorn ai.server:app --port 8000
# interactive docs for every endpoint: http://localhost:8000/docs
```

## Two modes (`STORE` in `ai/.env`)

| | `STORE=fixture` (default, **demo mode**) | `STORE=supabase` (real data) |
|---|---|---|
| Data | the fake week in `fixtures/week.json`, in memory | the Supabase tables in `supabase/migrations/` |
| Who is the user | `X-User-Id` header (default `user-1`) | `Authorization: Bearer <Supabase access token>`, checked with Supabase |
| Clock | fixed at `DEMO_NOW` (Mon Oct 5, 2026, 6:30 PM), to match the fake week | real time in the user's time zone |

In Supabase mode every database request uses the user's own token, so Row Level Security
applies: the API can't read or change another user's rows even if the code had a bug. It
uses the project's anon key, never the service-role key. The server refuses to start in
Supabase mode without `SUPABASE_URL` and `SUPABASE_ANON_KEY`.

## Endpoints

### `POST /chat`

```json
{
  "message": "Move my study session to 8 PM.",
  "history": [
    {"role": "user", "content": "What do I have tonight?"},
    {"role": "assistant", "content": "A study session from 7 to 9 PM."}
  ]
}
```

- `history`: earlier turns, **final answers only**, oldest first, at most 20. Roles can only be
  `user` or `assistant`; a `system` message is rejected (422), so callers can't add instructions.

Response:

```json
{
  "reply": "I suggest moving your study session to 8:00–10:00 PM. It's pending your approval.",
  "suggestions": [
    {
      "suggestion_id": "12",
      "type": "MOVE_EVENT",
      "target_id": "7",
      "description": "Move study session to start at 8 PM",
      "proposed_change": {"start": "2026-10-19T20:00:00-04:00", "end": "2026-10-19T22:00:00-04:00"},
      "depends_on": [],
      "status": "PENDING",
      "created_at": "2026-10-19T18:30:00-04:00",
      "expires_at": "2026-10-19T20:00:00-04:00"
    }
  ],
  "run_id": "c65192f2"
}
```

The frontend's `ChatWidget` shows `reply` as a bubble and each suggestion as a card with
**Accept** / **Decline**. Only those buttons change anything.

### `GET /suggestions`

The user's pending suggestions.

### `POST /suggestions/{id}/check`

Re-runs every check against the calendar as it is now:

```json
{"valid": false, "problems": ["... overlaps Lunch with Sam (...)"], "accept_first": []}
```

### `POST /suggestions/{id}/accept`

1. Re-runs the checks; refuses with **409** if a problem was found (e.g. the time is no longer
   free) or if a suggestion in `depends_on` is still pending ("accept 11 first").
2. Applies the change: `MOVE_EVENT` updates the event's times; `CREATE_EVENT` inserts an event
   with `created_by = 'AI'`.
3. Marks the suggestion `ACCEPTED` and writes an `activity_log` entry.

### `POST /suggestions/{id}/decline`

Marks it `DECLINED` and writes an `activity_log` entry.

## `depends_on`

The AI can plan in steps, for example "move the study session to 9 PM, then work on the
assignment 6:30–9 PM in its old time". The second suggestion lists the first in `depends_on`;
Accept refuses it until the first is accepted.

## Not done yet

- **Recurring events** (`recurrence_rule`) are read as single events.
- **Old pending suggestions** keep their time blocked for new proposals until they're
  answered or their time passes. The team should decide when to mark them `EXPIRED`.
- **Streaming**: replies arrive all at once (30 s to several minutes on a laptop).
- **The midnight overview** (`AIOverview`: `succeeded`, `missed`, `suggestion`, `motivation`)
  is Phase 2; the frontend still shows mock text there.
