import { useState } from "react";
import DayPopup from "./components/Daypopup";
import MonthCalendar from "./components/MonthCalendar";
import AIOverview from "./components/AIOverview";
import { mockAIOverview } from "./data/mockData";
function App(){
  const[selectedDate, setSelectedDate]= useState(null);
  return(
    <div>
      <h1> Steady Planner </h1>
      <AIOverview overview = {mockAIOverview} />
      <MonthCalendar onDayClick={setSelectedDate} selectedDate={selectedDate} />
      {selectedDate && <DayPopup date = {selectedDate} onClose = {() => setSelectedDate(null)} />}
    </div>
  );
}
export default App;