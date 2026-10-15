import { useState } from "react";
import { mockTasks, mockJournals } from "../data/mockData";

const statusLabels = {
  NOT_STARTED: "Not Started",
  IN_PROGRESS: "In Progress",
  COMPLETED: "Completed",
};

function DayPopup({ date, events: allEvents, onAddEvent, onDeleteEvent, onClose }) {
  const [activeTab, setActiveTab] = useState("calendar");
  const [name, setName] = useState("");
  const [startTime, setStartTime] = useState("9:00");
  const [endTime, setEndTime] = useState("10:00");
  const [isFixed, setIsFixed] = useState(false);

  const events = allEvents.filter((e) => e.start_date === date);
  const tasks = mockTasks.filter((t) => t.date === date);
  const journal = mockJournals.find((j) => j.date === date);
function handleAdd() {
  if (name.trim() === "" || endTime <= startTime) return;
  onAddEvent({
    event_id: Date.now(),
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
                {!event.changeable && <p>🔒 Fixed</p>}
                <button onClick={() => onDeleteEvent(event.event_id)}>Delete</button>
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
                <p>{statusLabels[task.status]}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === "journal" && (
          <div>
            {journal ? <p>{journal.information}</p> : <p>No journal entry yet.</p>}
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
}

export default DayPopup;