# Steady Planner frontend

React + Vite. Sign-in and the calendar, tasks and journal talk to Supabase directly
(Row Level Security keeps each user's data private). The chat and the Accept / Decline
buttons on AI suggestions talk to the AI service in `../ai`.

## Run it

```bash
cp .env.example .env.local    # then fill in the Supabase URL and anon key
npm install
npm run dev                   # http://localhost:5173
```

The AI service must be running for the chat (`cd ../ai && uv run uvicorn ai.server:app --port 8000`).

## Where things are

| File | What it does |
|---|---|
| `src/lib/supabase.js` | the Supabase client |
| `src/lib/data.js` | loading the month's events/tasks/journal, adding and deleting events |
| `src/lib/ai.js` | calls to the AI service (chat, accept, decline) |
| `src/components/AuthForm.jsx` | sign in / sign up (Supabase Auth) |
| `src/components/ChatWidget.jsx` | the chat, with Accept / Decline cards for suggestions |
| `src/components/MemoryPanel.jsx` | "What Steady remembers": the user's long-term memories, with Forget |
| `src/data/mockData.js` | only the AI overview still uses mock data (the nightly overview isn't built yet) |
