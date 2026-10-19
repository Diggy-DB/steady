import { useState } from "react";
import DayPopup from "./components/Daypopup";
import MonthCalendar from "./components/MonthCalendar";
import AIOverview from "./components/AIOverview";
import ChatWidget from "./components/ChatWidget";
import { mockAIOverview, mockEvents } from "./data/mockData";

function App() {
  const [selectedDate, setSelectedDate] = useState(null);
  const [events, setEvents] = useState(mockEvents);

  function handleDeleteEvent(id) {
    setEvents(events.filter((e) => e.event_id !== id));
  }
  function handleAddEvent(newEvent){
    setEvents([...events, newEvent]);
  }

  return (
    <div>
      <h1>Steady Planner</h1>
      <AIOverview overview={mockAIOverview} />
      <MonthCalendar onDayClick={setSelectedDate} selectedDate={selectedDate} />
      {selectedDate && (
        <DayPopup
          date={selectedDate}
          events={events}
          onDeleteEvent={handleDeleteEvent}
          onAddEvent = {handleAddEvent}
          onClose={() => setSelectedDate(null)}
        />
      )}
      <ChatWidget />
    </div>
  );
}

export default App;