import { useEffect, useState } from "react";
import { Field, ProgressBar } from "../ui";
import Modal from "../ui/Modal";
import { Check, Lock, Pencil, Plus, Repeat, Trash } from "../ui/icons";
import { describeRule } from "../../lib/recurrence";
import { describeSuggestion, suggestionDay } from "../../lib/suggestions";

// The selected day's calendar, tasks and journal. Desktop shows them as cards side by side; the phone shows
// them in the day sheet's tabs. Every change goes through the same handlers the old day pop-up used.

const HOUR_PX = 44;
const COLORS = ["blue", "orange", "green", "purple"];
const minutes = (hhmm) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
const clock = (hhmm) => {
  const h = Number(hhmm.slice(0, 2));
  return `${h % 12 || 12}:${hhmm.slice(3, 5)}${h < 12 ? " AM" : " PM"}`;
};
const span = (e) => `${clock(e.start_time)} – ${clock(e.end_time)}`;
// A stable color per event, from its id.
const colorOf = (id) => COLORS[[...String(id)].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % COLORS.length];
const localHHMM = (iso) => {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const pad = (n) => String(n).padStart(2, "0");
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

// The day's events (ending at midnight at the latest), earliest first.
export function eventsOn(events, date) {
  return events
    .filter((e) => e.start_date === date)
    .map((e) => ({ ...e, end_time: e.end_date && e.end_date !== e.start_date ? "24:00" : e.end_time }))
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
}

// Pending calendar suggestions for this day, as ghost blocks ("Proposed: ...").
function ghostsOn(suggestions, date, events) {
  return suggestions
    .filter((s) => s.status === "PENDING" && (s.type === "CREATE_EVENT" || s.type === "MOVE_EVENT") && !s.proposed_change.recurrence_rule
      && suggestionDay(s) === date)
    .map((s) => {
      const target = events.find((e) => String(e.event_id) === String(s.target_id));
      return {
        id: `ghost-${s.suggestion_id}`,
        name: s.type === "MOVE_EVENT" ? (target ? target.name : "moved event") : s.proposed_change.name,
        start_time: localHHMM(s.proposed_change.start),
        end_time: localHHMM(s.proposed_change.end),
      };
    });
}

// Side-by-side lanes for events that overlap.
function lanes(items) {
  const out = [];
  let group = [];
  let groupEnd = -1;
  const flush = () => {
    const ends = [];
    for (const item of group) {
      let lane = ends.findIndex((end) => end <= minutes(item.start_time));
      if (lane === -1) lane = ends.length;
      ends[lane] = minutes(item.end_time);
      out.push({ ...item, lane });
    }
    const count = ends.length;
    for (const o of out.slice(out.length - group.length)) o.lanes = count;
    group = [];
  };
  for (const item of items) {
    if (minutes(item.start_time) >= groupEnd && group.length) flush();
    group.push(item);
    groupEnd = Math.max(groupEnd, minutes(item.end_time));
  }
  if (group.length) flush();
  return out;
}

function EventBlock({ e, style, onOpen }) {
  const fixed = !e.changeable;
  const short = style && style.height < 38;
  return (
    <button type="button" className={`ev ${short ? "short" : ""} ${fixed ? "fixed striped" : `fill-${colorOf(e.event_id)}`}`} style={style}
      onClick={() => onOpen(e)} aria-label={`${e.name}, ${span(e)}${fixed ? ", fixed" : ""}`} title={`${e.name} · ${span(e)}`}>
      <span className="t">{fixed && <Lock label="Fixed" />}{e.name}</span>
      <span className="m">{span(e)}</span>
    </button>
  );
}

export function Timeline({ date, events, suggestions, onOpenEvent }) {
  const items = eventsOn(events, date);
  const ghosts = ghostsOn(suggestions, date, events);
  const all = [...items, ...ghosts];
  const first = Math.min(8, ...all.map((e) => Math.floor(minutes(e.start_time) / 60)));
  const last = Math.max(21, ...all.map((e) => Math.ceil(minutes(e.end_time) / 60)));
  const top = (hhmm) => ((minutes(hhmm) - first * 60) * HOUR_PX) / 60;
  const height = (e) => Math.max(22, ((minutes(e.end_time) - minutes(e.start_time)) * HOUR_PX) / 60);
  const place = (e) => ({
    top: top(e.start_time), height: height(e),
    left: `calc(${(100 / e.lanes) * e.lane}% + 6px)`, width: `calc(${100 / e.lanes}% - 10px)`,
  });

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const showNow = date === todayIso() && nowMin >= first * 60 && nowMin <= last * 60;

  return (
    <div className="timeline" style={{ height: (last - first) * HOUR_PX }}>
      {Array.from({ length: last - first + 1 }, (_, i) => first + i).map((h) => (
        <div key={h} aria-hidden="true">
          <span className="hour" style={{ top: (h - first) * HOUR_PX }}>{`${h % 12 || 12} ${h < 12 || h === 24 ? "AM" : "PM"}`}</span>
          <span className="grid-line" style={{ top: (h - first) * HOUR_PX }} />
        </div>
      ))}
      {lanes(items).map((e) => <EventBlock key={e.event_id} e={e} style={place(e)} onOpen={onOpenEvent} />)}
      {lanes(ghosts).map((g) => (
        <div key={g.id} className={`ev ghost ${place(g).height < 38 ? "short" : ""}`} style={place(g)}>
          <span className="t">Proposed: {g.name}</span>
          <span className="m">{span(g)}</span>
        </div>
      ))}
      {showNow && (
        <div className="now-line" style={{ top: ((nowMin - first * 60) * HOUR_PX) / 60 }}>
          <span className="now-tag">NOW</span>
        </div>
      )}
    </div>
  );
}

// Phone: the day as a list, with a NOW row at the current time.
export function Agenda({ date, events, onOpenEvent }) {
  const items = eventsOn(events, date);
  const now = new Date();
  const nowText = `${now.getHours() % 12 || 12}:${pad(now.getMinutes())}`;
  const nowHHMM = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const isToday = date === todayIso();
  const rows = [];
  let nowShown = !isToday;
  for (const e of items) {
    if (!nowShown && e.start_time > nowHHMM) {
      rows.push(<li key="now" className="now-row"><span className="now-tag">NOW {nowText}</span><span className="bar" /></li>);
      nowShown = true;
    }
    rows.push(
      <li key={e.event_id}>
        <span className="when">{clock(e.start_time)}</span>
        <EventBlock e={e} onOpen={onOpenEvent} />
      </li>,
    );
  }
  if (!nowShown && items.length) rows.push(<li key="now" className="now-row"><span className="now-tag">NOW {nowText}</span><span className="bar" /></li>);
  if (!items.length) return <p className="empty">No events this day. Enjoy the open space.</p>;
  return <ul className="agenda">{rows}</ul>;
}

export function AddEventDialog({ date, onAdd, onClose }) {
  const [name, setName] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("10:00");
  const [isFixed, setIsFixed] = useState(false);
  const [problem, setProblem] = useState("");

  function handleAdd(e) {
    e.preventDefault();
    if (name.trim() === "") return setProblem("Give the event a name.");
    if (endTime <= startTime) return setProblem("It has to end after it starts.");
    // The same new event as the old day pop-up.
    onAdd({
      name, start_time: startTime, end_time: endTime, start_date: date, end_date: date,
      recurrence_rule: null, changeable: !isFixed, created_by: "USER",
    });
    onClose();
  }

  return (
    <Modal title="Add event" color="blue" onClose={onClose}>
      <form className="add-form" style={{ border: "none", padding: 0 }} onSubmit={handleAdd} noValidate>
        <Field label="Event name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Study session" />
        <div className="row2">
          <Field label="Starts" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
          <Field label="Ends" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
        </div>
        <label className="check-label">
          <input type="checkbox" checked={isFixed} onChange={(e) => setIsFixed(e.target.checked)} />
          <span>Fixed (the AI can't move it)</span>
        </label>
        {problem && <p className="alert" role="alert">{problem}</p>}
        <button type="submit" className="btn"><Plus width={18} height={18} /> Add event</button>
      </form>
    </Modal>
  );
}

export function EventDialog({ event, onDelete, onClose }) {
  const fixed = !event.changeable;
  return (
    <Modal title={event.name} color={fixed ? "purple" : colorOf(event.event_id)} onClose={onClose}>
      <p className="mono">{span(event)}</p>
      {event.repeats && <p className="note"><Repeat /> {describeRule(event.recurrence_rule)}</p>}
      {fixed && <p className="note"><Lock /> Fixed. The AI never suggests moving it.</p>}
      <button type="button" className="btn orange"
        onClick={() => {
          if (!event.repeats || window.confirm(`Delete "${event.name}" on every day it repeats?`)) {
            onDelete(event.event_id);
            onClose();
          }
        }}>
        <Trash width={18} height={18} /> {event.repeats ? "Delete every week" : "Delete event"}
      </button>
    </Modal>
  );
}

const NEXT = { NOT_STARTED: "IN_PROGRESS", IN_PROGRESS: "COMPLETED", COMPLETED: "NOT_STARTED" };
const CHIP = { NOT_STARTED: ["To do", ""], IN_PROGRESS: ["Doing", "doing"], COMPLETED: ["Done", "done"] };

export function TaskList({ date, tasks, onUpdateTask, onDeleteTask, onAddTask, adding, setAdding }) {
  const mine = tasks.filter((t) => t.date === date);
  const done = mine.filter((t) => t.status === "COMPLETED").length;
  const [name, setName] = useState("");
  const [details, setDetails] = useState("");

  function handleAdd(e) {
    e.preventDefault();
    if (name.trim() === "") return;
    // The same new task as the old day pop-up.
    onAddTask({ name, description: details, date, status: "NOT_STARTED", changeable: true, created_by: "USER" });
    setName("");
    setDetails("");
    setAdding(false);
  }

  return (
    <>
      {mine.length > 0 && (
        <div className="progress-row">
          <ProgressBar value={done} max={mine.length} label={`${done} of ${mine.length} tasks done`} />
          <span className="mono">{done}/{mine.length} DONE</span>
        </div>
      )}
      {mine.length === 0 ? (
        <p className="empty">No tasks yet. Add one or ask Steady.</p>
      ) : (
        <ul className="task-list">
          {mine.map((t) => {
            const [label, cls] = CHIP[t.status] ?? CHIP.NOT_STARTED;
            return (
              <li key={t.task_id} className={`task-row ${cls}`}>
                <button type="button" className="check-btn" onClick={() => onUpdateTask(t.task_id, { status: NEXT[t.status] ?? "IN_PROGRESS" })}
                  aria-label={`${t.name}: ${label}. Change status`}>
                  <span className={`check ${cls}`}><Check /></span>
                </button>
                <span className="task-main">
                  <span className="task-name">{t.name}</span>
                  {t.description && <span className="task-desc">{t.description}</span>}
                </span>
                <span className="task-side">
                  {t.created_by === "AI" && <span className="tag fill-purple">AI</span>}
                  <span className={`status-chip ${cls}`}>{label}</span>
                  <button type="button" className="ghost-btn" onClick={() => onDeleteTask(t.task_id)} aria-label={`Delete task ${t.name}`}>
                    <Trash />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {adding && (
        <form className="add-form" onSubmit={handleAdd}>
          <Field label="Task name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <Field label="Details" value={details} onChange={(e) => setDetails(e.target.value)} placeholder="e.g. About 3 hours of work" />
          <div className="row">
            <button type="submit" className="btn green" disabled={!name.trim()}><Plus width={18} height={18} /> Add task</button>
            <button type="button" className="btn surface" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </form>
      )}
    </>
  );
}

export function JournalView({ date, journals, onSaveJournal, onDeleteJournal, editing, setEditing }) {
  const journal = journals.find((j) => j.date === date);
  const [text, setText] = useState(journal?.information ?? "");
  const [saved, setSaved] = useState(false);

  // Another day selected, or the entry changed (e.g. a journal note from the AI was accepted).
  useEffect(() => {
    setText(journal?.information ?? "");
    setSaved(false);
  }, [date, journal?.information]);

  async function handleSave() {
    if (text.trim() === "") return;
    const ok = await onSaveJournal(date, text, journal?.journal_id);
    setSaved(ok);
    if (ok) setEditing(false);
  }

  if (editing) {
    return (
      <>
        <Field label="How did today go?" as="textarea" value={text} onChange={(e) => { setText(e.target.value); setSaved(false); }} autoFocus />
        <div className="add-form row" style={{ border: "none", padding: 0, flexDirection: "row", flexWrap: "wrap" }}>
          <button type="button" className="btn green" onClick={handleSave} disabled={!text.trim()}><Check width={18} height={18} /> Save</button>
          <button type="button" className="btn surface" onClick={() => setEditing(false)}>Cancel</button>
          {journal && (
            <button type="button" className="btn orange" onClick={() => { onDeleteJournal(journal.journal_id); setEditing(false); }}>
              <Trash width={18} height={18} /> Delete
            </button>
          )}
        </div>
      </>
    );
  }
  return (
    <>
      {journal ? <p className="entry">{journal.information}</p> : <p className="empty">No journal entry yet. How did today go?</p>}
      {saved && <p className="note" role="status"><Check /> Saved</p>}
      {!journal && (
        <button type="button" className="btn surface" style={{ alignSelf: "flex-start" }} onClick={() => setEditing(true)}>
          <Pencil width={18} height={18} /> Write entry
        </button>
      )}
      <p className="note"><Lock /> Private to you. Used only to personalize your feedback.</p>
    </>
  );
}

// The suggestions on a given day first, then the rest by date.
export function sortSuggestions(suggestions, date) {
  return [...suggestions].sort((a, b) => {
    const da = suggestionDay(a) ?? "9999";
    const db = suggestionDay(b) ?? "9999";
    return (db === date) - (da === date) || da.localeCompare(db);
  });
}

export { describeSuggestion };
