import { useEffect, useState } from "react";
import { Alert, Box, Card, Marquee } from "../components/ui";
import { Pencil, Plus, Sparkle, Lock } from "../components/ui/icons";
import AppHeader from "../components/home/AppHeader";
import OverviewHero, { overviewMarquee, overviewTiles } from "../components/home/OverviewHero";
import MonthCalendar from "../components/MonthCalendar";
import SuggestionCard from "../components/home/SuggestionCard";
import DaySheet from "../components/home/DaySheet";
import { AddEventDialog, EventDialog, JournalView, TaskList, Timeline, eventsOn, sortSuggestions } from "../components/home/Day";
import ChatWidget from "../components/ChatWidget";
import { ai } from "../lib/ai";
import { dateString } from "../lib/data";
import { suggestionDay } from "../lib/suggestions";
import { useIsPhone } from "../lib/useIsPhone";

const SHOWN = 6; // suggestions listed before "Show all"

function Home({
  profile, data, error, shown, onChangeMonth, suggestions, onSuggestionsChanged, reload, overview, overviewBusy, overviewError,
  onRefreshOverview, profileBanner, onDismissBanner, handlers,
}) {
  const now = new Date();
  const today = dateString(now.getFullYear(), now.getMonth(), now.getDate());
  const [selectedDate, setSelectedDate] = useState(today);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [addingEvent, setAddingEvent] = useState(false);
  const [openEvent, setOpenEvent] = useState(null);
  const [addingTask, setAddingTask] = useState(false);
  const [editingJournal, setEditingJournal] = useState(false);
  const [chatRequest, setChatRequest] = useState(null);
  const [answers, setAnswers] = useState({}); // suggestion id -> {status, error, answering, suggestion}
  const [showAll, setShowAll] = useState(false);
  const phone = useIsPhone();

  // A new month: select today if it's in it, otherwise the 1st.
  useEffect(() => {
    const inMonth = today.startsWith(dateString(shown.year, shown.month, 1).slice(0, 8));
    setSelectedDate(inMonth ? today : dateString(shown.year, shown.month, 1));
  }, [shown, today]);

  useEffect(() => {
    setEditingJournal(false);
    setAddingTask(false);
  }, [selectedDate]);

  // The pending suggestions, with what happened to the ones answered here (shown until the list reloads).
  const pending = suggestions.map((s) => ({ ...s, ...answers[s.suggestion_id] }));
  const answeredGone = Object.values(answers).filter((a) => a.status && a.status !== "PENDING" && !suggestions.some((s) => s.suggestion_id === a.suggestion.suggestion_id))
    .map((a) => ({ ...a.suggestion, ...a }));
  const list = sortSuggestions([...pending, ...answeredGone], selectedDate);
  const waiting = pending.filter((s) => s.status === "PENDING").length;

  async function answer(suggestion, choice) {
    const id = suggestion.suggestion_id;
    setAnswers((a) => ({ ...a, [id]: { ...a[id], suggestion, answering: choice, error: null } }));
    try {
      // The existing endpoints: the AI service checks again, then applies (or refuses with the reason).
      const { status } = choice === "accept" ? await ai.accept(id) : await ai.decline(id);
      setAnswers((a) => ({ ...a, [id]: { suggestion, status, answering: null, error: null } }));
      if (status === "ACCEPTED") reload();
    } catch (err) {
      setAnswers((a) => ({ ...a, [id]: { suggestion, status: "PENDING", answering: null, error: err.message } }));
    }
  }

  const marks = {};
  for (const e of data.events) (marks[e.start_date] ??= { events: 0, tasks: 0 }).events += 1;
  for (const t of data.tasks) (marks[t.date] ??= { events: 0, tasks: 0 }).tasks += 1;

  const selected = new Date(`${selectedDate}T12:00:00`);
  const dayTitle = (selectedDate === today ? "Today, " : "")
    + selected.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }).replace(",", "");
  const ask = (text) => setChatRequest({ id: Date.now(), text });

  const calendar = (
    <MonthCalendar year={shown.year} month={shown.month} today={today} onPrev={() => onChangeMonth(-1)} onNext={() => onChangeMonth(1)}
      onDayClick={(date) => { setSelectedDate(date); if (phone) setSheetOpen(true); }} selectedDate={selectedDate} marks={marks}
      className="slam slam-2" />
  );
  const chat = (
    <ChatWidget events={data.events} request={chatRequest} onCalendarChanged={reload} onSuggestionsMade={onSuggestionsChanged} />
  );
  const dialogs = (
    <>
      {addingEvent && <AddEventDialog date={selectedDate} onAdd={handlers.onAddEvent} onClose={() => setAddingEvent(false)} />}
      {openEvent && <EventDialog event={openEvent} onDelete={handlers.onDeleteEvent} onClose={() => setOpenEvent(null)} />}
    </>
  );
  const banner = profileBanner && (
    <Box className="banner fill-pink slam">
      <p>Tell Steady what matters to you: your priorities, when you work best and your fixed commitments.</p>
      <a className="btn surface" href="#/settings">Open Settings</a>
      <button type="button" className="btn surface" onClick={onDismissBanner}>Later</button>
    </Box>
  );

  // ---- Phone ----
  if (phone) {
    const dayEvents = eventsOn(data.events, selectedDate);
    const dayTasks = data.tasks.filter((t) => t.date === selectedDate);
    const daySuggestions = pending.filter((s) => s.status === "PENDING" && suggestionDay(s) === selectedDate);
    return (
      <div className="home">
        <AppHeader profile={profile} compact />
        <Marquee size="small" className="thin" items={overviewMarquee(overview)} />
        {error && <Alert>{error}</Alert>}
        {banner}
        <OverviewHero compact firstName={profile?.first_name} overview={overview} error={overviewError} busy={overviewBusy}
          onRefresh={onRefreshOverview} onAsk={ask} />
        {calendar}
        <Box className="day-card slam slam-3" aria-labelledby="day-card-title">
          <h2 id="day-card-title">{dayTitle}</h2>
          <div className="chips">
            <span className="tag chip fill-blue">{dayEvents.length} event{dayEvents.length === 1 ? "" : "s"}</span>
            <span className="tag chip fill-green">{dayTasks.filter((t) => t.status === "COMPLETED").length}/{dayTasks.length} tasks done</span>
            {daySuggestions.length > 0 && <span className="tag chip fill-purple">{daySuggestions.length} suggestion{daySuggestions.length === 1 ? "" : "s"}</span>}
          </div>
          <button type="button" className="btn full" onClick={() => setSheetOpen(true)}>Open this day →</button>
        </Box>
        {sheetOpen && (
          <DaySheet date={selectedDate} title={dayTitle} events={data.events} tasks={data.tasks} journals={data.journals}
            suggestions={pending.filter((s) => s.status === "PENDING" || answers[s.suggestion_id])} onAnswer={answer}
            onOpenEvent={setOpenEvent} onAddEvent={() => setAddingEvent(true)} handlers={handlers} onClose={() => setSheetOpen(false)} />
        )}
        {dialogs}
        {chat}
      </div>
    );
  }

  // ---- Desktop and tablet ----
  const visible = showAll ? list : list.slice(0, SHOWN);
  const tiles = overview ? overviewTiles(overview) : null;
  return (
    <div className="home">
      <AppHeader profile={profile} />
      {overview && tiles && <Marquee items={overviewMarquee(overview)} className="slam slam-1" />}
      {error && <Alert action={<button type="button" className="btn small surface" onClick={reload}>Try again</button>}>{error}</Alert>}
      {banner}

      <div className="top-row">
        <OverviewHero firstName={profile?.first_name} overview={overview} error={overviewError} busy={overviewBusy}
          onRefresh={onRefreshOverview} onAsk={ask} />
        {calendar}
      </div>

      <div className="day-head slam slam-3">
        <h2 className="section-title">{dayTitle}</h2>
        {waiting > 0 && <span className="tag fill-pink">{waiting} waiting for you</span>}
      </div>

      <div className="day-cols">
        <Card title="AI suggestions" color="purple" icon={<Sparkle />} className="slam slam-3"
          actions={<span className="count-badge" aria-label={`${waiting} waiting`}>{waiting}</span>}>
          <p className="note"><Lock /> Nothing changes until you accept.</p>
          {list.length === 0 ? (
            <p className="empty">No suggestions right now. Ask Steady in the chat to plan something.</p>
          ) : (
            <ul className="sugg-list">
              {visible.map((s) => <SuggestionCard key={s.suggestion_id} suggestion={s} events={data.events} onAnswer={answer} />)}
            </ul>
          )}
          {list.length > SHOWN && (
            <button type="button" className="btn surface" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `Show all ${list.length}`}
            </button>
          )}
        </Card>

        <Card title="Schedule" color="blue" className="slam slam-4"
          actions={<button type="button" className="btn small surface" onClick={() => setAddingEvent(true)}><Plus width={16} height={16} /> Event</button>}>
          {eventsOn(data.events, selectedDate).length === 0 && <p className="empty">No events this day. Enjoy the open space.</p>}
          <Timeline date={selectedDate} events={data.events} suggestions={pending} onOpenEvent={setOpenEvent} />
          <p className="note"><Lock /> Striped = fixed. The AI never suggests moving it.</p>
        </Card>

        <div className="stack">
          <Card title="Tasks" color="green" className="slam slam-5"
            actions={<button type="button" className="btn small surface" onClick={() => setAddingTask(true)}><Plus width={16} height={16} /> Task</button>}>
            <TaskList date={selectedDate} tasks={data.tasks} adding={addingTask} setAdding={setAddingTask} {...handlers} />
          </Card>
          <Box className="with-header journal-card slam slam-5" aria-labelledby="journal-title">
            <div className="card-header">
              <h2 id="journal-title">Journal</h2>
              {!editingJournal && data.journals.some((j) => j.date === selectedDate) && (
                <button type="button" className="btn small surface" onClick={() => setEditingJournal(true)}><Pencil width={16} height={16} /> Edit</button>
              )}
            </div>
            <div className="card-body">
              <JournalView date={selectedDate} journals={data.journals} editing={editingJournal} setEditing={setEditingJournal} {...handlers} />
            </div>
          </Box>
        </div>
      </div>
      {dialogs}
      {chat}
    </div>
  );
}

export default Home;
