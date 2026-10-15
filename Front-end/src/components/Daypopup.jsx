import { useState } from "react";
import { mockEvents, mockTasks, mockJournals } from "../data/mockData";

const statusLabels = {
  NOT_STARTED: "Not Started",
  IN_PROGRESS: "In Progress",
  COMPLETED: "Completed",
};

function DayPopup({ date, onClose }) {
  const [activeTab, setActiveTab] = useState("calendar");

  const events = mockEvents.filter((e) => e.start_date === date);
  const tasks = mockTasks.filter((t) => t.date === date);
  const journal = mockJournals.find((j) => j.date === date);

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
              </div>
            ))}
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
}

export default DayPopup;