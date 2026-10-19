import { dateString } from "../lib/data";

// One month as a grid. The month to show and "today" now come from App (they used to be
// fixed to October 2026), with buttons to move between months.
function MonthCalendar({ year, month, today, onPrev, onNext, onDayClick, selectedDate }) {
  const firstDayOfweek = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const cells = [];
  for (let i = 0; i < firstDayOfweek; i++) {
    cells.push(null);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(d);
  }
  const title = new Date(year, month, 1).toLocaleDateString([], { month: "long", year: "numeric" });

  return (
    <div className="month-calendar">
      <div className="month-header">
        <button onClick={onPrev} aria-label="Previous month">‹</button>
        <h2>{title}</h2>
        <button onClick={onNext} aria-label="Next month">›</button>
      </div>
      <div className="calendar-grid">
        {weekdays.map((day) => (
          <div key={day} className="weekday">{day}</div>
        ))}
        {cells.map((day, index) => {
          const date = day ? dateString(year, month, day) : null;
          let className = day ? "day-cell" : "day-cell empty";
          if (date === today) className += " today";
          if (date === selectedDate) className += " selected";

          return (
            <div key={index} className={className} onClick={() => day && onDayClick(date)}>
              {day}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default MonthCalendar;
