# Steady Planner

An AI-assisted planner: calendar, tasks and journal, with an assistant that can look at your
schedule, find free time and **suggest** changes. The AI never changes anything by itself;
every change is a suggestion you accept or decline, checked again by the backend first.

```
Browser (Front-end/, React)
   ├── sign in, events, tasks, journal ──────────► Supabase (Auth + Postgres with Row Level Security)
   └── chat, Accept / Decline ──► AI service (ai/, FastAPI) ──► Supabase, with the user's own token
                                         │
                                         └──► model server (Ollama on a laptop, or vLLM on RunPod)
```

| Folder | What it is | Details |
|---|---|---|
| `Front-end/` | React + Vite app | `Front-end/README.md` |
| `ai/` | the AI service and backend API (Python) | `ai/README.md`, `ai/notes/stage5_api.md` |
| `supabase/` | the database schema (`migrations/`) and its tests (`tests/`) | `supabase/migrations/*.sql` |

## Running everything locally

1. **Database**: the schema in `supabase/migrations/` must be applied to the Supabase project once.
2. **Models** (for the AI): `OLLAMA_CONTEXT_LENGTH=32768 ollama serve`, plus once
   `ollama pull qwen3:4b-thinking-2507-q8_0` and `ollama pull nomic-embed-text` (see `ai/README.md`),
   or a RunPod server for the chat model (`ai/notes/stage4_runpod.md`).
3. **AI service**: in `ai/.env` set `STORE=supabase` (with `SUPABASE_URL` and `SUPABASE_ANON_KEY`), then

   ```bash
   cd ai && uv sync && uv run uvicorn ai.server:app --port 8000
   ```

4. **Frontend**: copy `Front-end/.env.example` to `Front-end/.env.local` and fill it in, then

   ```bash
   cd Front-end && npm install && npm run dev      # http://localhost:5173
   ```

## Tests

```bash
cd ai && uv run pytest                    # AI service and API (no model or database needed)
cd supabase/tests && npm install && npm test   # the database schema and its security rules
cd Front-end && npm run build && npm run lint
```
