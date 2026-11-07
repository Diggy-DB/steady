import { useState } from "react";
import { describeRule } from "../lib/recurrence";

const statusLabels = {
  NOT_STARTED: "Not Started",
  IN_PROGRESS: "In Progress",
  COMPLETED: "Completed",
};

function DayPopup({
  date,
  events: allEvents,
  tasks: allTasks = [],
  journals: allJournals = [],
  onAddEvent,
  onDeleteEvent,
  onAddTask,
  onUpdateTask,
  onDeleteTask,
  onSaveJournal,
  onDeleteJournal,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState("calendar");
  const [name, setName] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("10:00");
  const [isFixed, setIsFixed] = useState(false);
  const [taskName, setTaskName] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [journalText, setJournalText] = useState(
    () => allJournals.find((j) => j.date === date)?.information ?? "",
  );
  const [journalSaved, setJournalSaved] = useState(false);

  const events = allEvents.filter((e) => e.start_date === date);
  const tasks = allTasks.filter((t) => t.date === date);
  const journal = allJournals.find((j) => j.date === date);
function handleAdd() {
  if (name.trim() === "" || endTime <= startTime) return;
  onAddEvent({
    name: name,
    start_time: startTime,
    end_time: endTime,
    start_date: date,
    end_date: date,
    recurrence_rule: null,
    changeable: !isFixed,
    created_by: "USER",
  });
  setName("");
}

  function handleAddTask() {
    if (taskName.trim() === "") return;
    onAddTask({
      name: taskName,
      description: taskDescription,
      date: date,
      status: "NOT_STARTED",
      changeable: true,
      created_by: "USER",
    });
    setTaskName("");
    setTaskDescription("");
  }

  async function handleSaveJournal() {
    if (journalText.trim() === "") return;
    const ok = await onSaveJournal(date, journalText, journal?.journal_id);
    setJournalSaved(ok);
  }

  function handleDeleteJournal() {
    onDeleteJournal(journal.journal_id);
    setJournalText("");
    setJournalSaved(false);
  }
  return (
    <div className="popup-overlay" onClick={onClose}>
      <div className="popup" onClick={(e) => e.stopPropagation()}>
        <button className="popup-close" onClick={onClose}>✕</button>
        <h2>{date}</h2>

        <div className="tabs">
          <button
            className={activeTab === "calendar" ? "tab active" : "tab"}
            onClick={() => setActiveTab("calendar")}
          >
            Calendar
          </button>
          <button
            className={activeTab === "tasks" ? "tab active" : "tab"}
            onClick={() => setActiveTab("tasks")}
          >
            Tasks
          </button>
          <button
            className={activeTab === "journal" ? "tab active" : "tab"}
            onClick={() => setActiveTab("journal")}
          >
            Journal
          </button>
        </div>

        {activeTab === "calendar" && (
          <div>
            {events.length === 0 && <p>No events today.</p>}
            {events.map((event) => (
              <div key={event.event_id} className="item">
                <strong>{event.name}</strong>
                <p>{event.start_time} – {event.end_time}</p>
                {event.repeats && <p>🔁 {describeRule(event.recurrence_rule)}</p>}
                {!event.changeable && <p>🔒 Fixed</p>}
                <button
                  onClick={() =>
                    (!event.repeats || window.confirm(`Delete "${event.name}" on every day it repeats?`)) &&
                    onDeleteEvent(event.event_id)
                  }
                >
                  {event.repeats ? "Delete every week" : "Delete"}
                </button>
              </div>
            ))}
            {newFunction()}            
          </div>
        )}

        {activeTab === "tasks" && (
          <div>
            {tasks.length === 0 && <p>No tasks today.</p>}
            {tasks.map((task) => (
              <div key={task.task_id} className="item">
                <strong>{task.name}</strong>
                <p>{task.description}</p>
                <select
                  value={task.status}
                  onChange={(e) => onUpdateTask(task.task_id, { status: e.target.value })}
                >
                  {Object.entries(statusLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                <button onClick={() => onDeleteTask(task.task_id)}>Delete</button>
              </div>
            ))}
            {addTaskForm()}
          </div>
        )}

        {activeTab === "journal" && (
          <div>
            {!journal && <p>No journal entry yet.</p>}
            {journalForm()}
          </div>
        )}
      </div>
    </div>
  );

  function newFunction() {
    return <div className="add-event">
      <h3>Add event</h3>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Event name" />
      <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
      <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
      <label>
        <input
          type="checkbox"
          checked={isFixed}
          onChange={(e) => setIsFixed(e.target.checked)} />
        Fixed (AI can't move it)
      </label>
      <button onClick={handleAdd}>Add</button>
    </div>;
  }

  function addTaskForm() {
    return <div className="add-event">
      <h3>Add task</h3>
      <input
        value={taskName}
        onChange={(e) => setTaskName(e.target.value)}
        placeholder="Task name" />
      <input
        value={taskDescription}
        onChange={(e) => setTaskDescription(e.target.value)}
        placeholder="Details (e.g. About 3 hours of work)" />
      <button onClick={handleAddTask}>Add</button>
    </div>;
  }

  function journalForm() {
    return <div className="add-event">
      <h3>{journal ? "Edit entry" : "Write entry"}</h3>
      <textarea
        value={journalText}
        onChange={(e) => {
          setJournalText(e.target.value);
          setJournalSaved(false);
        }}
        placeholder="How did today go?" />
      <button onClick={handleSaveJournal}>Save</button>
      {journalSaved && <p>Saved ✓</p>}
      {journal && <button onClick={handleDeleteJournal}>Delete</button>}
    </div>;
  }
}

export default DayPopup;