# Stage 5: the AI service API (for the frontend and backend)

`src/ai/server.py` is a small FastAPI app around the agent. Run it from `ai/`:

```bash
uv run uvicorn ai.server:app --port 8000
# then open http://localhost:8000/docs for an interactive page with every endpoint
```

## Two modes

| | `STORE=fixture` (default, **demo mode**) | `STORE=supabase` (real data) |
|---|---|---|
| Data | the fake week in `fixtures/week.json`, in memory | Supabase tables, through the REST API |
| Who is the user | `X-User-Id` header (default `user-1`) | `Authorization: Bearer <Supabase access token>`, checked with Supabase |
| Clock | fixed at `DEMO_NOW` (Mon Oct 5, 2026, 6:30 PM), to match the fake week | real time in the user's time zone |
| Accept / Decline | done here, in memory (so the frontend can be demoed now) | the backend's job (endpoints return 501) |

In Supabase mode every database request uses the user's own token, so Row Level Security
applies: the AI service can't read another user's rows even if the code had a bug.

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
  `user` or `assistant` (a `system` message is rejected with 422, so callers can't add instructions).
- From the frontend's `ChatWidget`: `sender: "USER"` → `role: "user"`, `sender: "AI"` → `role: "assistant"`.

Response:

```json
{
  "reply": "I suggest moving your study session to 8:00–10:00 PM. It's pending your approval.",
  "suggestions": [
    {
      "suggestion_id": "s1",
      "type": "MOVE_EVENT",
      "target_id": "e2",
      "description": "Move study session to start at 8 PM",
      "proposed_change": {"start": "2026-10-05T20:00:00-04:00", "end": "2026-10-05T22:00:00-04:00"},
      "depends_on": [],
      "status": "PENDING",
      "created_at": "2026-10-05T18:30:00-04:00",
      "expires_at": "2026-10-05T20:00:00-04:00"
    }
  ],
  "run_id": "c65192f2"
}
```

- Show `reply` as the AI's chat bubble.
- Show each item in `suggestions` as a card with **Accept** / **Decline**. Only these buttons
  change anything; the chat text never does.
- Replies are slow on a laptop (30 seconds to several minutes for planning questions); show a
  "thinking…" state. A GPU on RunPod is much faster.

### `GET /suggestions`

The user's pending suggestions (for showing cards on the home page).

### `POST /suggestions/{id}/check`

Re-runs every check against the calendar **as it is now**:

```json
{"valid": false, "problems": ["Wednesday, October 7, 12:30 PM – 1:30 PM overlaps Lunch with Sam (...)"], "accept_first": []}
```

- `accept_first`: suggestions this one depends on that are still pending (see `depends_on` below).

### `POST /suggestions/{id}/accept`, `POST /suggestions/{id}/decline` (demo mode only)

Accept runs the check, refuses with 409 if it fails or if `accept_first` isn't empty, then
applies the change to the in-memory week.

## What the backend does on Accept (Supabase mode)

1. Call `POST /suggestions/{id}/check` with the user's token (or run the same checks).
2. If `valid` is false or `accept_first` isn't empty, don't apply it; show the problem.
3. Apply it in one transaction:
   - `CREATE_EVENT`: insert into `calendar_events` with `created_by = 'AI'`, `changeable = true`.
   - `MOVE_EVENT`: update the event `target_id` to the new times.
4. Set the suggestion's `status` to `ACCEPTED` (or `DECLINED` on Decline) and write the activity log.
5. Suggestions whose `expires_at` has passed can be marked `EXPIRED`.

### `depends_on`

The AI can plan in steps, for example "move the study session to 9 PM, then work on the
assignment 6:30–9 PM in its old time". The second suggestion lists the first in `depends_on`:
it's only valid if the first is accepted too. The check endpoint reports this in `accept_first`.

## What the AI service reads and writes in Supabase

It uses the team's planned schema (meeting notes, and the frontend's `mockData.js`):

| Table | Columns the AI uses |
|---|---|
| `users` | `user_id`, `timezone` (e.g. `America/Detroit`) |
| `calendar_events` | `event_id`, `user_id`, `name`, `start_date`, `start_time`, `end_date`, `end_time`, `changeable` (times are local to the user's time zone) |
| `tasks` | `task_id`, `user_id`, `name`, `description`, `date`, `status`, `changeable` |
| `ai_suggestions` | everything in the suggestion above (it inserts rows and reads them) |

Proposed `ai_suggestions` table (for the backend team to review):

```sql
create table ai_suggestions (
  suggestion_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id),
  type text not null check (type in ('CREATE_EVENT', 'MOVE_EVENT')),
  target_id bigint references calendar_events (event_id),
  description text not null default '',
  proposed_change jsonb not null,
  depends_on jsonb not null default '[]',
  status text not null default 'PENDING' check (status in ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED')),
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

alter table ai_suggestions enable row level security;
create policy "users see and add only their own suggestions" on ai_suggestions
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
```

The other tables need the same kind of policy (`user_id = auth.uid()`). The AI service uses the
project's **anon key plus the user's token**, never the service-role key.

## Not done yet

- **Recurring events** (`recurrence_rule`) are read as single events.
- **Streaming**: replies arrive all at once.
- **The midnight overview** (`AIOverview` on the frontend: `succeeded`, `missed`, `suggestion`,
  `motivation`) is Phase 2.
- Supabase mode is tested against a fake Supabase API (`tests/test_supabase_store.py`), not a
  real project yet, because the backend tables don't exist yet.
