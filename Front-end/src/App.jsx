import { useCallback, useEffect, useState } from "react";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Home from "./pages/Home";
import Settings from "./pages/Settings";
import { Skeleton } from "./components/ui";
import { profileIsEmpty } from "./lib/profile";
import { applyOnboarding, takePending } from "./lib/onboarding";
import { go, useRoute } from "./lib/route";
import { ai } from "./lib/ai";
import { supabase } from "./lib/supabase";
import {
  addEvent,
  addTask,
  deleteEvent,
  deleteJournal,
  deleteTask,
  loadMonth,
  loadPendingSuggestions,
  loadProfile,
  saveJournal,
  updateTask,
} from "./lib/data";

// The app shell: who is signed in, which page (#/login, #/signup, #/, #/settings), and the data and handlers
// the pages share. The handlers are the same as before the redesign; only the pages around them are new.
function App() {
  const today = new Date();
  const route = useRoute();
  const [session, setSession] = useState(undefined); // undefined = still checking
  const [shown, setShown] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [data, setData] = useState({ events: [], tasks: [], journals: [] });
  const [error, setError] = useState("");
  const [profile, setProfile] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [overview, setOverview] = useState(null);
  const [overviewBusy, setOverviewBusy] = useState("loading"); // "loading" | "refreshing" | ""
  const [overviewError, setOverviewError] = useState("");
  const [bannerDismissed, setBannerDismissed] = useState(false);

  // Keep track of who is signed in.
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => setSession(newSession));
    return () => listener.subscription.unsubscribe();
  }, []);

  // Signed in on the log-in or sign-up page: go home. Signed out anywhere else: go to log in.
  useEffect(() => {
    if (session && (route === "login" || route === "signup")) go("home");
    if (session === null && route !== "login" && route !== "signup") go("login");
  }, [session, route]);

  // Load the shown month's events, tasks and journal entries from Supabase.
  const reload = useCallback(async () => {
    try {
      setData(await loadMonth(shown.year, shown.month));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, [shown]);

  const reloadSuggestions = useCallback(async () => {
    try {
      setSuggestions(await loadPendingSuggestions());
    } catch {
      // the suggestions card just stays as it was
    }
  }, []);

  useEffect(() => {
    if (session) reload();
  }, [session, reload]);

  // The profile, once per sign-in. Answers from sign-up that waited for the email confirmation are saved first.
  const userId = session?.user?.id;
  const userEmail = session?.user?.email;
  useEffect(() => {
    if (!userId) return;
    (async () => {
      const pending = takePending(userEmail);
      if (pending) {
        try {
          await applyOnboarding(userId, pending);
          reload();
        } catch (err) {
          setError(`Couldn't save your sign-up answers: ${err.message}`);
        }
      }
      try {
        setProfile(await loadProfile());
      } catch (err) {
        setError(`Couldn't load your profile: ${err.message}`);
      }
      try {
        setBannerDismissed(localStorage.getItem(`steady.profileLater.${userId}`) === "1");
      } catch {
        // storage blocked: just show it again
      }
    })();
    reloadSuggestions();
  }, [userId, userEmail]); // eslint-disable-line react-hooks/exhaustive-deps

  // Today's overview of yesterday (written once a day by the AI service, then saved).
  const loadOverview = useCallback(async (refresh = false) => {
    setOverviewBusy(refresh ? "refreshing" : "loading");
    setOverviewError("");
    try {
      setOverview(refresh ? await ai.refreshOverview() : await ai.overview());
    } catch (err) {
      setOverviewError(err.message);
    } finally {
      setOverviewBusy("");
    }
  }, []);

  useEffect(() => {
    if (userId) loadOverview();
  }, [userId, loadOverview]);

  function dismissBanner() {
    setBannerDismissed(true);
    try {
      localStorage.setItem(`steady.profileLater.${userId}`, "1");
    } catch {
      // storage blocked: fine
    }
  }

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
  }

  // Still checking who is signed in: page-shaped placeholders, no spinner.
  if (session === undefined) {
    return (
      <div className="home" aria-busy="true">
        <Skeleton height={64} />
        <div className="top-row">
          <Skeleton height={320} className="hero" />
          <Skeleton height={320} className="month" />
        </div>
      </div>
    );
  }
  if (!session) return route === "signup" ? <Signup /> : <Login />;

  if (route === "settings") {
    return profile ? (
      <Settings profile={profile} email={session.user.email} onSaved={setProfile} onCalendarChanged={reload} />
    ) : (
      <div className="page" aria-busy="true"><Skeleton height={64} /><Skeleton height={400} /></div>
    );
  }

  return (
    <Home
      profile={profile}
      data={data}
      error={error}
      shown={shown}
      onChangeMonth={changeMonth}
      suggestions={suggestions}
      onSuggestionsChanged={reloadSuggestions}
      reload={() => {
        reload();
        reloadSuggestions();
      }}
      overview={overview}
      overviewBusy={overviewBusy}
      overviewError={overviewError}
      onRefreshOverview={() => loadOverview(true)}
      profileBanner={profile && profileIsEmpty(profile) && !bannerDismissed}
      onDismissBanner={dismissBanner}
      handlers={{
        onAddEvent: handleAddEvent,
        onDeleteEvent: handleDeleteEvent,
        onAddTask: handleAddTask,
        onUpdateTask: handleUpdateTask,
        onDeleteTask: handleDeleteTask,
        onSaveJournal: handleSaveJournal,
        onDeleteJournal: handleDeleteJournal,
      }}
    />
  );
}

export default App;
