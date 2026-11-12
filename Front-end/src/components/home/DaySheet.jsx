import { useEffect, useRef, useState } from "react";
import { Box } from "../ui";
import { Pencil, Plus, X } from "../ui/icons";
import SuggestionCard from "./SuggestionCard";
import { Agenda, JournalView, TaskList } from "./Day";
import { suggestionDay } from "../../lib/suggestions";

// Phone: the selected day in a bottom sheet with Calendar / Tasks / Journal tabs (the old day pop-up's tabs).
function DaySheet({ date, title, events, tasks, journals, suggestions, onAnswer, onOpenEvent, onAddEvent, handlers, onClose }) {
  const [tab, setTab] = useState("calendar");
  const [addingTask, setAddingTask] = useState(false);
  const [editing, setEditing] = useState(false);
  const ref = useRef(null);
  const daySuggestions = suggestions.filter((s) => suggestionDay(s) === date);

  useEffect(() => {
    const before = document.activeElement;
    ref.current?.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [onClose]);

  const tabs = [["calendar", "Calendar"], ["tasks", "Tasks"], ["journal", "Journal"]];
  return (
    <>
      <button type="button" className="sheet-scrim" onClick={onClose} aria-label="Close the day" tabIndex={-1} />
      <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <div className="grab" aria-hidden="true" />
        <div className="sheet-head">
          <div style={{ flex: 1 }}>
            <span className="eyebrow muted">Selected day</span>
            <h2 id="sheet-title">{title}</h2>
          </div>
          <button type="button" className="btn icon-btn surface" onClick={onClose} aria-label="Close"><X /></button>
        </div>
        <div className="segmented sheet-tabs" role="tablist" aria-label="Day">
          {tabs.map(([id, label]) => (
            <button key={id} type="button" role="tab" id={`tab-${id}`} aria-selected={tab === id} aria-controls={`panel-${id}`}
              tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
        <div className="sheet-body" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === "calendar" && (
            <>
              {daySuggestions.length > 0 && (
                <ul className="sugg-list">
                  {daySuggestions.map((s) => <SuggestionCard key={s.suggestion_id} suggestion={s} events={events} onAnswer={onAnswer} />)}
                </ul>
              )}
              <Agenda date={date} events={events} onOpenEvent={onOpenEvent} />
              <button type="button" className="btn full" onClick={onAddEvent}><Plus width={18} height={18} /> Add event</button>
            </>
          )}
          {tab === "tasks" && (
            <>
              <TaskList date={date} tasks={tasks} adding={addingTask} setAdding={setAddingTask} {...handlers} />
              {!addingTask && <button type="button" className="btn green full" onClick={() => setAddingTask(true)}><Plus width={18} height={18} /> Add task</button>}
            </>
          )}
          {tab === "journal" && (
            <Box className="with-header journal-card">
              <div className="card-header">
                <h3>Journal</h3>
                {!editing && journals.some((j) => j.date === date) && (
                  <button type="button" className="btn small surface" onClick={() => setEditing(true)}><Pencil width={16} height={16} /> Edit entry</button>
                )}
              </div>
              <div className="card-body">
                <JournalView date={date} journals={journals} editing={editing} setEditing={setEditing} {...handlers} />
              </div>
            </Box>
          )}
        </div>
      </div>
    </>
  );
}

export default DaySheet;
