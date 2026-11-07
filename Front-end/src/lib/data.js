import { supabase } from "./supabase";
import { expandEvent } from "./recurrence";

// Everyday reads and writes go straight to Supabase. Row Level Security makes sure
// each user only ever gets their own rows, so no user id is needed in these queries.

const pad = (n) => String(n).padStart(2, "0");
export const dateString = (year, month, day) => `${year}-${pad(month + 1)}-${pad(day)}`; // month is 0-11

function check({ data, error }) {
  if (error) throw new Error(error.message);
  return data;
}

// Postgres returns times as "10:00:00"; the screens show "10:00".
const shortTimes = (event) => ({
  ...event,
  start_time: event.start_time.slice(0, 5),
  end_time: event.end_time.slice(0, 5),
});

export async function loadMonth(year, month) {
  const first = dateString(year, month, 1);
  const last = dateString(year, month, new Date(year, month + 1, 0).getDate());
  const [events, repeating, tasks, journals] = await Promise.all([
    supabase.from("calendar_events").select("*").is("recurrence_rule", null)
      .gte("start_date", first).lte("start_date", last).order("start_date").order("start_time"),
    // Weekly classes and other repeating events that started by the end of the month: shown on each day they happen.
    supabase.from("calendar_events").select("*").not("recurrence_rule", "is", null).lte("start_date", last),
    supabase.from("tasks").select("*").gte("date", first).lte("date", last).order("date"),
    supabase.from("journals").select("*").gte("date", first).lte("date", last),
  ]);
  const all = [...check(events), ...check(repeating).flatMap((row) => expandEvent(row, first, last))]
    .map(shortTimes)
    .sort((a, b) => (a.start_date + a.start_time).localeCompare(b.start_date + b.start_time));
  return { events: all, tasks: check(tasks), journals: check(journals) };
}

// The signed-in user's profile (public.users). The database made it at sign-up, from the sign-up form.
export async function loadProfile() {
  const { data: { user } } = await supabase.auth.getUser();
  return check(await supabase.from("users").select("*").eq("user_id", user.id).single());
}

export async function saveProfile(userId, changes) {
  return check(await supabase.from("users").update(changes).eq("user_id", userId).select().single());
}

export async function addEvent(event) {
  const row = check(await supabase.from("calendar_events").insert(event).select().single());
  return shortTimes(row);
}

export async function deleteEvent(eventId) {
  check(await supabase.from("calendar_events").delete().eq("event_id", eventId));
}

export async function addTask(task) {
  return check(await supabase.from("tasks").insert(task).select().single());
}

export async function updateTask(taskId, changes) {
  return check(await supabase.from("tasks").update(changes).eq("task_id", taskId).select().single());
}

export async function deleteTask(taskId) {
  check(await supabase.from("tasks").delete().eq("task_id", taskId));
}

// One journal entry per day (the database enforces it): edit the day's entry if it
// exists, otherwise create it.
export async function saveJournal(date, information, journalId) {
  const query = journalId
    ? supabase.from("journals").update({ information }).eq("journal_id", journalId)
    : supabase.from("journals").insert({ date, information });
  return check(await query.select().single());
}

export async function deleteJournal(journalId) {
  check(await supabase.from("journals").delete().eq("journal_id", journalId));
}
