// A user's private calendar link, for Apple Calendar, Google Calendar and Outlook.
//
// Calendar apps fetch the link on their own schedule, with no login, so the secret token in the link is the key.
// This reads that one user's events and tasks through the database function calendar_feed, as the public anon
// role (the same key the website uses; no admin key), and answers with an .ics file. It runs on Supabase, so the
// link works around the clock, also while the AI server on RunPod is off.
//
// Deploy (from the repository root, once logged in with `supabase login`):
//   supabase functions deploy calendar-feed --no-verify-jwt --project-ref <project ref>
// --no-verify-jwt: calendar apps can't send a login token; the link's own token is checked below instead.
import { buildCalendar } from "./ics.js";

const TOKEN = /^[0-9a-f]{64}$/;

Deno.serve(async (request: Request) => {
  const url = new URL(request.url);
  const token = (url.searchParams.get("token") ?? "").toLowerCase();
  if (!TOKEN.test(token)) return new Response("Not found", { status: 404 });

  const base = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  if (!base || !anonKey) return new Response("The calendar link isn't set up.", { status: 500 });

  const answer = await fetch(`${base}/rest/v1/rpc/calendar_feed`, {
    method: "POST",
    headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ feed_token: token }),
  });
  if (!answer.ok) return new Response("The calendar is unavailable right now. Try again later.", { status: 503 });
  const feed = await answer.json();
  if (!feed) return new Response("Not found", { status: 404 }); // no such link, or it was turned off

  return new Response(buildCalendar(feed, new Date()), {
    headers: {
      "Content-Type": "text/calendar; charset=utf-8",
      "Content-Disposition": 'inline; filename="steady-planner.ics"',
      "Cache-Control": "private, max-age=300",
    },
  });
});
