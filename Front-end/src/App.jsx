import { useCallback, useEffect, useState } from "react";
import DayPopup from "./components/Daypopup";
import MonthCalendar from "./components/MonthCalendar";
import AIOverview from "./components/AIOverview";
import ChatWidget from "./components/ChatWidget";
import AuthForm from "./components/AuthForm";
import { mockAIOverview } from "./data/mockData";
import { supabase } from "./lib/supabase";
import { addEvent, dateString, deleteEvent, loadMonth } from "./lib/data";

function App() {
  const today = new Date();
  const [session, setSession] = useState(undefined); // undefined = still checking
  const [shown, setShown] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [data, setData] = useState({ events: [], tasks: [], journals: [] });
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState(null);

  // Keep track of who is signed in.
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => setSession(newSession));
    return () => listener.subscription.unsubscribe();
  }, []);

  // Load the shown month's events, tasks and journal entries from Supabase.
  const reload = useCallback(async () => {
    try {
      setData(await loadMonth(shown.year, shown.month));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, [shown]);

  useEffect(() => {
    if (session) reload();
  }, [session, reload]);

  async function handleAddEvent(newEvent) {
    try {
      const saved = await addEvent(newEvent);
      setData((d) => ({ ...d, events: [...d.events, saved] }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteEvent(id) {
    try {
      await deleteEvent(id);
      setData((d) => ({ ...d, events: d.events.filter((e) => e.event_id !== id) }));
    } catch (err) {
      setError(err.message);
    }
  }

  function changeMonth(step) {
    setShown(({ year, month }) => {
      const first = new Date(year, month + step, 1);
      return { year: first.getFullYear(), month: first.getMonth() };
    });
    setSelectedDate(null);
  }

  if (session === undefined) return <p>Loading…</p>;
  if (!session) {
    return (
      <div>
        <h1>Steady Planner</h1>
        <AuthForm />
      </div>
    );
  }

  return (
    <div>
      <div className="app-header">
        <h1>Steady Planner</h1>
        <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </div>
      {error && <p className="error">{error}</p>}
      <AIOverview overview={mockAIOverview} />
      <MonthCalendar
        year={shown.year}
        month={shown.month}
        today={dateString(today.getFullYear(), today.getMonth(), today.getDate())}
        onPrev={() => changeMonth(-1)}
        onNext={() => changeMonth(1)}
        onDayClick={setSelectedDate}
        selectedDate={selectedDate}
      />
      {selectedDate && (
        <DayPopup
          date={selectedDate}
          events={data.events}
          tasks={data.tasks}
          journals={data.journals}
          onDeleteEvent={handleDeleteEvent}
          onAddEvent={handleAddEvent}
          onClose={() => setSelectedDate(null)}
        />
      )}
      <ChatWidget events={data.events} onCalendarChanged={reload} />
    </div>
  );
}

export default App;
