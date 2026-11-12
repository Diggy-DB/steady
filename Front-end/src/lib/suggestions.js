import { describeRule } from "./recurrence";

// How a suggestion reads on a card (the Home suggestions card and the chat use the same words).

const day = (d) => d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
const time = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
const dateOnly = (iso) => new Date(`${iso.slice(0, 10)}T12:00:00`);
const span = (start, end) => `${time(start)}–${time(end)}`;

// An event row's start and end as Dates (rows keep a date and a "HH:MM" time).
export function eventTimes(e) {
  return [new Date(`${e.start_date}T${e.start_time}`), new Date(`${e.end_date || e.start_date}T${e.end_time}`)];
}

// The local "YYYY-MM-DD" a suggestion is about, or null (for the timeline and the selected day).
export function suggestionDay(s) {
  const c = s.proposed_change;
  const when = c.start || c.due || c.date || (s.type === "DELETE_JOURNAL" ? c.id : null);
  if (!when) return null;
  if (when.length <= 10) return when;
  const d = new Date(when);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function describeSuggestion(s, events = []) {
  const c = s.proposed_change;
  const isDelete = s.type.startsWith("DELETE_");
  switch (s.type) {
    case "CREATE_EVENT": {
      const start = new Date(c.start);
      const end = new Date(c.end);
      return {
        kind: "Calendar", color: "blue", title: `Add "${c.name}"`,
        change: c.recurrence_rule
          ? `${describeRule(c.recurrence_rule)} · ${span(start, end)}`
          : `${day(start)} · ${span(start, end)}`,
        yes: "Yes, add it", isDelete,
      };
    }
    case "MOVE_EVENT": {
      const target = events.find((e) => String(e.event_id) === String(s.target_id));
      const start = new Date(c.start);
      const end = new Date(c.end);
      const before = target ? eventTimes(target) : null;
      const sameDay = before && before[0].toDateString() === start.toDateString();
      return {
        kind: "Calendar", color: "blue", title: `Move "${target ? target.name : "an event"}"`,
        change: before
          ? `${sameDay ? "" : `${day(before[0])} `}${span(...before)} → ${sameDay ? "" : `${day(start)} `}${span(start, end)}`
          : `→ ${day(start)} · ${span(start, end)}`,
        yes: "Yes, move it", isDelete,
      };
    }
    case "CREATE_TASK": {
      const due = c.kind === "task" ? dateOnly(c.due) : new Date(c.due);
      return {
        kind: "New task", color: "green", title: `Add task "${c.name}"`,
        change: c.kind === "task" ? `Due ${day(due)}` : `Due ${day(due)} · ${time(due)}`,
        yes: "Yes, add it", isDelete,
      };
    }
    case "DELETE_EVENT":
      return {
        kind: "Calendar", color: "blue", title: `Delete "${c.name}"`,
        change: c.start ? `${day(new Date(c.start))} · ${span(new Date(c.start), new Date(c.end))}` : "",
        yes: "Yes, delete it", isDelete,
      };
    case "DELETE_TASK":
      return { kind: "Task", color: "orange", title: `Delete task "${c.name}"`, change: c.due ? `Due ${day(dateOnly(c.due))}` : "",
        yes: "Yes, delete it", isDelete };
    case "DELETE_JOURNAL":
      return { kind: "Journal", color: "pink", title: "Delete a journal entry", change: day(dateOnly(c.id)),
        quote: c.preview, yes: "Yes, delete it", isDelete };
    case "ADD_JOURNAL":
      return { kind: "Journal", color: "pink", title: c.adds_to_existing ? "Add to your journal" : "Start a journal entry",
        change: day(dateOnly(c.date)), quote: c.text, yes: "Yes, add it", isDelete };
    case "EDIT_JOURNAL":
      return { kind: "Journal", color: "pink", title: "Edit your journal entry", change: day(dateOnly(c.date)),
        quote: c.text, before: c.old, yes: "Yes, save it", isDelete };
    default:
      return { kind: "Suggestion", color: "purple", title: s.type, change: "", yes: "Accept", isDelete };
  }
}
