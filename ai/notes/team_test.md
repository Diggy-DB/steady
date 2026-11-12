# Team test: the website on GitHub Pages, the AI on RunPod, the data in Supabase

The four of us use the real app: everyone makes an account, fills in a profile, chats with Steady, and
sends a syllabus (PDF or photo) with the 📎 button. This page is how it's set up and what to test.

## What runs where

| Part | Where | Address |
|---|---|---|
| Website (`Front-end/`) | GitHub Pages, built by `.github/workflows/pages.yml` | https://diggy-db.github.io/steady/ |
| Accounts, profiles, calendars, tasks | Supabase project "Steady Planner" | https://kzvmzeejvmgkwsjoowxn.supabase.co |
| AI API (`ai/src/ai/server.py`, real-data mode) | RunPod pod, port 8000 (public) | `https://<POD_ID>-8000.proxy.runpod.net` |
| The model, Qwen3.5-4B on vLLM | the same pod, `127.0.0.1:18001` (not public) | |

The browser talks to Supabase directly for everyday reads and writes (Row Level Security keeps each
person's rows private), and to the AI API for chat, syllabus import and Accept / Decline. The AI API
checks the person's Supabase login on every request and reads and writes with *their* token, so it can
only ever touch that person's data. No secret keys anywhere: the website and the pod only have Supabase's
public anon key.

## One-time setup

**GitHub** (repository Settings):
1. Pages > Source: **GitHub Actions**. A private repository needs GitHub Pro for Pages (free with the
   GitHub Student Developer Pack), or the repository has to be public. The site itself is public either way.
2. Environments > github-pages > **Environment variables** (or repository variables; not secrets, since
   all three end up in the website anyway): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (same values as
   `Front-end/.env.local`) and `VITE_AI_API_URL` (the pod address).
3. The workflow runs on pushes to `main` and `ai`. GitHub only lets `main` publish until you add the
   branch: Environments > github-pages > Deployment branches > add `ai`.

**Supabase** (dashboard > Authentication):
1. URL Configuration: Site URL `https://diggy-db.github.io/steady/`; Redirect URLs add
   `https://diggy-db.github.io/steady/**` and `http://localhost:5173/**`. The sign-up confirmation email
   links back here.
2. Sign In / Providers > Email > "Confirm email": Supabase's built-in email sender only sends a few
   emails an hour. With it on, sign-ups may wait for the email; turning it off for the test lets people
   sign in right away.

## Each test session

1. Start the pod (RTX 4090, ports 8888 and 8000). A new pod has a new address; a stopped and restarted
   pod keeps its address.
2. On the laptop: `bash ai/deploy/make_pod_bundle.sh` writes `~/Downloads/steady-pod.tar.gz` (the AI code,
   plus `pod.env` with the Supabase URL, anon key and the website's address). Upload it in Jupyter.
3. In the pod's terminal:
   ```bash
   cd /workspace && tar xzf steady-pod.tar.gz && bash steady/ai/deploy/runpod_app.sh
   ```
   The first time: about 30 minutes to install vLLM on a slow pod, then a 9 GB model download. After
   that, about 3 minutes. It ends with a picture check ("Vision check: HW 3 due Feb 12") and the address.
4. If the address changed: update `VITE_AI_API_URL`, then Actions > Publish website > Run workflow.
5. **Stop the pod afterwards**: it bills by the hour while it's on.

Running the script again restarts the API (new code) but leaves a running model alone;
`RESTART_MODEL=1` restarts both. Logs: `/workspace/logs/app.log`, `/workspace/logs/vllm.log`, and every
syllabus import in `/workspace/steady/ai/logs/imports.jsonl` (what was read and suggested, not the file).

Problems we hit setting it up, so they don't come back: port 8001 belongs to RunPod's nginx (the model
uses 18001, and "ready" means vLLM answered with the model's name); vLLM needs its own folder on PATH to
build kernels (`ninja`); and vLLM's default of hundreds of requests at once is resized to 16.

## What to test (everyone)

1. **Account**: sign up at the site, confirm the email if asked, sign in.
2. **Profile**: it opens on first sign-in. Fill in time zone, morning or night, priorities (most important
   first), hobbies, and anything else. Change it later from the header.
3. **Calendar**: add a few events (mark one Fixed) and tasks for this week.
4. **Chat**: ask about your week, ask it to find time for something, move something, plan a goal
   ("gym 3 times this week"). Check that it suggests instead of claiming it changed things, that Accept puts
   it on the calendar, and that it respects Fixed events and your morning/night preference.
5. **Syllabus**: 📎 a real syllabus, as a PDF and as a phone photo. Check the cards against the syllabus:
   deadlines become tasks (with the due time in the description), exams and in-class quizzes become events,
   lectures become one weekly card that skips breaks. Cards with ⚠ are dates the code wasn't sure about.
   Try "Accept all", then look at the calendar (dots mark days with events and tasks).
6. **Daily overview** (top of the page, from the second day on): does it describe yesterday correctly
   (tasks, calendar, your journal)? Are the suggestions sensible? Try "Ask Steady →" on one, and "Refresh"
   after writing yesterday's journal entry. Anything it says that isn't true is the most useful report.
7. **Journal and deletes** in the chat: "Add to my journal: ...", "In yesterday's journal, change X to Y"
   (the card shows before and after), "Delete my gym session on Friday",
   "Remove the X task". It should only ever suggest (red cards for deletes, with Delete / Keep it), refuse
   fixed events, and never delete something when you asked to move it.
8. **Write down** anything wrong: the question or file, what it did, what it should have done. Wrong dates
   from syllabi are the most useful reports.

## Fixed after the first team test (Nov 11)

| Seen | Cause | Fix |
|---|---|---|
| An accepted event appeared twice | two Accepts at once (a double tap, or "Accept all" plus a card) both passed the checks before either finished; the live database had 1 suggestion accepted twice | Accept first claims the suggestion (`PENDING` -> `ACCEPTED` in one `UPDATE ... WHERE status = 'PENDING'`), so only one request applies it; the buttons lock while it's answered |
| A Mon/Wed/Fri lecture added for every weekday | the model misread the meeting days (both weekly classes ever imported were saved as Mon-Fri) | the days are read from the syllabus text on the line with the class time ("MWF", "Mon, Wed, Fri", "Monday through Thursday", ...) and override the model; right for all 19 meetings in the text test syllabi. A syllabus whose semester is over adds no weekly class |
| "Next week's tasks" showed the week after | the 4B miscounts dates | the prompt spells out this week, next week and the next 14 days, worked out in code |
| Study sessions at 11 PM-midnight | "works best at night" taken literally, and nothing stopped late times | night means about 6-10 PM; times before 7 AM or past 11 PM are refused unless the user asks for one ("at 11:30 pm") or a deadline tonight needs it |
| The reply was the model's whole thinking | when thinking runs out of tokens without closing, vLLM returns it all as the answer | such a round is redone without thinking; answers that are long or read like thinking are rewritten into at most 4 short sentences |
| "Can't reach the AI server" for some prompts, every time, with the server up | most likely the leaked thinking: it went back with every later message as history | long history turns are cut (1,500 characters) instead of refused, error messages aren't sent back as history, polling retries short drops, and the API restarts itself if it stops. `scripts/check_pod.py <pod URL>` checks whether long histories get through the proxy |
| "I've added..." for what was only suggested | the 4B ignores the prompt rule | reworded in code to "I suggest adding..." when the turn made suggestions |
| "Add a task" made calendar events | the chat had no task tool | `propose_new_task` (a to-do due on a day), only when the user asks for a task and never a near-copy of one on the list (planning runs used it to copy existing tasks instead of blocking time) |
| "Sorry, I couldn't finish that" above 4 good cards | it ran out of rounds after proposing | it lists the suggestions it made instead |
| (found in the evals) "Cancel my piano lesson" (there was none) suggested deleting the study session | the 4B picked another event | a delete must be for something the user named (a word in common); otherwise the model is told to say it's not there, or ask |
| (found in the evals) planning runs reached for the new task tool 21 times in 17 runs | 8 tools are a lot for a 4B | each request gets the 4 planning tools; the task, delete and journal tools only when the message (or Steady's last reply) is about them |

## Known limits

- iPhone HEIC photos are refused from a computer (phones convert them to JPEG when uploading). Send a screenshot.
- A scan or photo set of more than 12 pages is refused; digital PDFs of any length are read as text.
- Relative dates ("Friday of Week 4", "due the Wednesday after") and patterns ("every Friday except
  break") are the weakest part of syllabus reading (see `syllabus_import.md`).
- Long-term memory is off on the pod (`MEMORY=off`): it needs an embedding model we haven't set up there.
- The model is a 4B: on the hand-written planning cases it passes about 64% (see `evals_suite.md`).
  This test is to find out where it fails for real students.
