import { useCallback, useEffect, useState } from "react";
import DayPopup from "./components/Daypopup";
import MonthCalendar from "./components/MonthCalendar";
import AIOverview from "./components/AIOverview";
import ChatWidget from "./components/ChatWidget";
import AuthForm from "./components/AuthForm";
import MemoryPanel from "./components/MemoryPanel";
import ProfilePanel, { profileIsEmpty } from "./components/ProfilePanel";
import { ai } from "./lib/ai";
import { supabase } from "./lib/supabase";
import {
  addEvent,
  addTask,
  dateString,
  deleteEvent,
  deleteJournal,
  deleteTask,
  loadMonth,
  loadProfile,
  saveJournal,
  updateTask,
} from "./lib/data";

function App() {
  const today = new Date();
  const [session, setSession] = useState(undefined); // undefined = still checking
  const [shown, setShown] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [data, setData] = useState({ events: [], tasks: [], journals: [] });
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState(null);
  const [showMemories, setShowMemories] = useState(false);
  const [profile, setProfile] = useState(null);
  const [chatRequest, setChatRequest] = useState(null); // a message for the chat to send, e.g. from the overview
  const [showProfile, setShowProfile] = useState(false);

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

  // The profile, once per sign-in. A new account is asked to fill it in (once; "Later" is remembered).
  const userId = session?.user?.id;
  useEffect(() => {
    if (!userId) return;
    loadProfile()
      .then((p) => {
        setProfile(p);
        let later = false;
        try {
          later = localStorage.getItem(`steady.profileLater.${userId}`) === "1";
        } catch {
          // storage blocked: just ask again next time
        }
        if (profileIsEmpty(p) && !later) setShowProfile(true);
      })
      .catch((err) => setError(`Couldn't load your profile: ${err.message}`));
  }, [userId]);

  function closeProfile() {
    setShowProfile(false);
    try {
      localStorage.setItem(`steady.profileLater.${userId}`, "1");
    } catch {
      // storage blocked: fine
    }
  }

  // How many events and tasks each day has, for the dots on the month grid.
  const marks = {};
  for (const e of data.events) (marks[e.start_date] ??= { events: 0, tasks: 0 }).events += 1;
  for (const t of data.tasks) (marks[t.date] ??= { events: 0, tasks: 0 }).tasks += 1;

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

  async function handleAddTask(newTask) {
    try {
      const saved = await addTask(newTask);
      setData((d) => ({ ...d, tasks: [...d.tasks, saved] }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleUpdateTask(id, changes) {
    try {
      const saved = await updateTask(id, changes);
      setData((d) => ({ ...d, tasks: d.tasks.map((t) => (t.task_id === id ? saved : t)) }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteTask(id) {
    try {
      await deleteTask(id);
      setData((d) => ({ ...d, tasks: d.tasks.filter((t) => t.task_id !== id) }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSaveJournal(date, information, journalId) {
    try {
      const saved = await saveJournal(date, information, journalId);
      setData((d) => ({ ...d, journals: [...d.journals.filter((j) => j.journal_id !== saved.journal_id), saved] }));
      ai.rememberJournal(saved.journal_id).catch(() => {}); // let Steady learn from it, in the background
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    }
  }

  async function handleDeleteJournal(id) {
    try {
      await deleteJournal(id);
      setData((d) => ({ ...d, journals: d.journals.filter((j) => j.journal_id !== id) }));
      ai.forgetJournal(id).catch(() => {}); // and forget what it taught
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
        <div>
          <button className="link" onClick={() => setShowProfile(true)} disabled={!profile}>
            {profile?.first_name ? `${profile.first_name}'s profile` : "Profile"}
          </button>
          {" · "}
          <button className="link" onClick={() => setShowMemories(true)}>What Steady remembers</button>
          {" · "}
          <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <AIOverview onAsk={(text) => setChatRequest({ id: Date.now(), text })} />
      <MonthCalendar
        year={shown.year}
        month={shown.month}
        today={dateString(today.getFullYear(), today.getMonth(), today.getDate())}
        onPrev={() => changeMonth(-1)}
        onNext={() => changeMonth(1)}
        onDayClick={setSelectedDate}
        selectedDate={selectedDate}
        marks={marks}
      />
      {selectedDate && (
        <DayPopup
          date={selectedDate}
          events={data.events}
          tasks={data.tasks}
          journals={data.journals}
          onDeleteEvent={handleDeleteEvent}
          onAddEvent={handleAddEvent}
          onAddTask={handleAddTask}
          onUpdateTask={handleUpdateTask}
          onDeleteTask={handleDeleteTask}
          onSaveJournal={handleSaveJournal}
          onDeleteJournal={handleDeleteJournal}
          onClose={() => setSelectedDate(null)}
        />
      )}
      {showMemories && <MemoryPanel onClose={() => setShowMemories(false)} />}
      {showProfile && profile && (
        <ProfilePanel
          profile={profile}
          firstTime={profileIsEmpty(profile)}
          onSaved={(saved) => {
            setProfile(saved);
            setShowProfile(false);
          }}
          onClose={closeProfile}
        />
      )}
      <ChatWidget events={data.events} onCalendarChanged={reload} request={chatRequest} />
    </div>
  );
}

export default App;
