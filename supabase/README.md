# Supabase: database, Edge Function and sign-in

- `migrations/`: the database schema, applied in order. Never edit an applied one; add a new file.
- `functions/calendar-feed/`: the Edge Function behind each user's private calendar link.
- `tests/`: runs every migration in a throwaway Postgres (PGlite) with Supabase's roles, and tests the calendar
  link's `.ics` file against an independent iCalendar parser. No Docker, no live database:

  ```bash
  cd supabase/tests && npm install && npm test
  ```

## Sign in with Google and the calendar link (Nov 16, 2026)

Migration `20261116120000_google_sign_in_and_calendar_link.sql`:

- Google sign-ups get their profile name from Google (`given_name` / `family_name`, or the full name).
- `calendar_feeds`: one secret link per user. The database makes the 64-character token; a user can read and
  delete their own row and can't choose a token.
- `calendar_feed(token)`: returns one user's events and tasks for a valid token, and nothing else (no journal,
  profile or suggestions). Only the public `anon` role may call it: the Edge Function uses it, with no admin key.

The website: "Continue with Google" on log-in and sign-up, and Settings › Calendar apps (connect or disconnect
Google; create, copy, renew or turn off the calendar link, with Add to Apple Calendar / Google Calendar buttons).
The link is one-way: Steady's events and due dates show in the person's calendar app, read-only.

### One-time setup

1. **Google Cloud Console** (console.cloud.google.com), a project for Steady:
   - APIs & Services › OAuth consent screen: External; app name Steady Planner; your email. Scopes: only the
     basic ones (email, profile, openid), so Google needs no review. While it's in Testing, add the team as test
     users, or publish it.
   - Credentials › Create credentials › OAuth client ID › Web application.
     Authorized JavaScript origins: `https://diggy-db.github.io` and `http://localhost:5173`.
     Authorized redirect URI: `https://<project ref>.supabase.co/auth/v1/callback`.
     Keep the client ID and client secret.
2. **Supabase dashboard** for the project:
   - Authentication › Sign In / Providers › Google: turn it on and paste the client ID and secret.
   - Authentication › URL Configuration: Site URL `https://diggy-db.github.io/steady/`; Redirect URLs
     `https://diggy-db.github.io/steady/` and `http://localhost:5173/`.
   - Authentication › Sign In / Providers (or Settings): turn on **Allow manual linking**, for Connect Google in Settings.
3. **The migration**: run the SQL file in the dashboard's SQL Editor (or `npx supabase db push` from a linked checkout).
4. **The Edge Function** (from the repository root):

   ```bash
   npx supabase login
   npx supabase functions deploy calendar-feed --no-verify-jwt --project-ref <project ref>
   ```

   `--no-verify-jwt` because calendar apps can't send a login token: the function checks the link's own token.
   Supabase gives the function `SUPABASE_URL` and `SUPABASE_ANON_KEY` itself; nothing else to set.

Check it: in Settings, create a calendar link and open it in a browser. It downloads `steady-planner.ics`.
A wrong token answers 404.

## Importing other calendars (Nov 18, 2026)

Migration `20261118120000_calendar_imports.sql` (apply it after the Nov 16 one):

- `calendar_imports`: the calendars a person imports (name, private `https://` address, when it last worked or why
  not). Own rows only; signed-out visitors get nothing.
- `calendar_events.import_id` / `external_id`: which import an event came from, and its id there. The foreign key
  includes `user_id`, so nobody can attach events to someone else's import. Removing an import removes its events.
- `calendar_feed` now leaves imported events out, so a Google Calendar that is both imported into Steady and
  subscribed to Steady's link doesn't show them twice.

The AI server does the downloading (`ai/src/ai/calendar_import.py`, `POST /calendars` and `POST /calendars/sync`):
https only, public internet addresses only, at most 10 MB. It copies each timed event from a week ago to about four
months ahead as a fixed event, in the person's time zone; all-day and cancelled events are skipped. The website
(Settings › Calendar apps › Import a calendar) syncs, at most hourly, when the app opens. Nothing is written back.

### Limits

- The calendar link is one-way and read-only. Apple Calendar refreshes a subscription as often as hourly; Google Calendar every 12-24
  hours, on its own schedule.
- Imports are one-way too (their calendar → Steady) and only as fresh as the last sync, which needs the AI server.
- Apple Reminders and Apple's Journal app have no web API; Google Calendar two-way sync and Google Tasks are later
  steps (they need a decision on storing Google tokens).
- Anyone with a link can read that person's events and due dates. Make a new link to cut off an old one.
