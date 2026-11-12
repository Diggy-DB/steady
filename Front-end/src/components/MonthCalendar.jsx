import { Box } from "./ui";
import { ChevronLeft, ChevronRight } from "./ui/icons";
import { dateString } from "../lib/data";

// One month as a grid (same props as before). Day buttons are 44px; today is yellow, the selected day is
// ink with a pink shadow, days with events or tasks get a small square dot. Days from the months around
// it are shown muted and can't be picked (the app loads one month at a time).
function MonthCalendar({ year, month, today, onPrev, onNext, onDayClick, selectedDate, marks = {}, className = "" }) {
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysBefore = new Date(year, month, 0).getDate();
  const cells = [];
  for (let i = firstWeekday - 1; i >= 0; i--) cells.push({ day: daysBefore - i, out: true });
  for (let d = 1; d <= daysInMonth; d++) cells.push({ day: d, out: false });
  while (cells.length % 7) cells.push({ day: cells.length - daysInMonth - firstWeekday + 1, out: true });
  const title = new Date(year, month, 1).toLocaleDateString([], { month: "short", year: "numeric" }).toUpperCase();
  const longTitle = new Date(year, month, 1).toLocaleDateString([], { month: "long", year: "numeric" });

  return (
    <Box className={`month ${className}`} aria-labelledby="month-title">
      <div className="month-head">
        <h2 id="month-title" aria-label={longTitle}>{title}</h2>
        <button type="button" className="btn icon-btn surface" onClick={onPrev} aria-label="Previous month"><ChevronLeft /></button>
        <button type="button" className="btn icon-btn surface" onClick={onNext} aria-label="Next month"><ChevronRight /></button>
      </div>
      <div className="month-grid" role="group" aria-label={longTitle}>
        {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
          <span key={i} className="wd" aria-hidden="true">{d}</span>
        ))}
        {cells.map((cell, i) => {
          if (cell.out) {
            return <span key={i} className="day-btn out" aria-hidden="true">{cell.day}</span>;
          }
          const date = dateString(year, month, cell.day);
          const mark = marks[date];
          const label = new Date(year, month, cell.day).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })
            + (date === today ? ", today" : "")
            + (mark ? `, ${mark.events} event${mark.events === 1 ? "" : "s"}, ${mark.tasks} task${mark.tasks === 1 ? "" : "s"}` : "");
          return (
            <button key={i} type="button" className={`day-btn ${date === today ? "today" : ""}`}
              aria-pressed={date === selectedDate} aria-label={label} onClick={() => onDayClick(date)}>
              {cell.day}
              {mark && <span className="dot" aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    </Box>
  );
}

export default MonthCalendar;
