import { useEffect, useRef, useState } from "react";
import { ai } from "../lib/ai";
import { describeRule } from "../lib/recurrence";

// Chat with the AI service. Its replies can come with suggestions; each one is a card
// with Accept / Decline. Only those buttons change the calendar or the journal, never the chat text.
// The 📎 button sends a syllabus (PDF or photo): the AI reads it and suggests every deadline,
// exam and weekly class in it, as cards like any other suggestion.
// `request` ({id, text}) opens the chat and sends that message, e.g. "Ask Steady" on the daily overview.

const MAX_UPLOAD_MB = 15;
const FILE_TYPES = "application/pdf,image/jpeg,image/png,image/webp"; // phones turn HEIC photos into JPEG for these
const POLL_MS = 2500;
const GIVE_UP_MS = 6 * 60 * 1000;

// Ask for a background job (a chat answer or a syllabus import) until it's finished.
async function waitFor(job, fetchJob, running, onTick) {
  const started = Date.now();
  while (job.status === running) {
    if (Date.now() - started > GIVE_UP_MS) throw new Error("it's taking too long; try again in a few minutes");
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    onTick(Math.round((Date.now() - started) / 1000));
    job = await fetchJob();
  }
  return job;
}

const dayText = (d) => d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
const timeText = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const dateOnly = (iso) => new Date(`${iso.slice(0, 10)}T12:00:00`); // a YYYY-MM-DD day, without time zone surprises

function when(type, change) {
  if (type === "ADD_JOURNAL" || type === "EDIT_JOURNAL") return `Journal for ${dayText(dateOnly(change.date))}`;
  if (type === "DELETE_JOURNAL") return `Journal entry for ${dayText(dateOnly(change.id))}`;
  if (type === "DELETE_TASK") return `Due ${dayText(dateOnly(change.due))}`;
  if (type === "CREATE_TASK") {
    const due = new Date(change.due);
    return `Due ${dayText(due)}, ${timeText(due)}`;
  }
  const start = new Date(change.start);
  const end = new Date(change.end);
  if (change.recurrence_rule) {
    return `${describeRule(change.recurrence_rule)}, ${timeText(start)} – ${timeText(end)} (from ${dayText(start)})`;
  }
  return `${dayText(start)}, ${timeText(start)} – ${timeText(end)}`;
}

function SuggestionCard({ suggestion, events, onAnswer }) {
  const { type, proposed_change: change, target_id: targetId, description, status, error } = suggestion;
  const target = events.find((e) => String(e.event_id) === String(targetId));
  const isDelete = type.startsWith("DELETE_");
  const titles = {
    CREATE_TASK: `Add task "${change.name}"`,
    CREATE_EVENT: `Add ${change.recurrence_rule ? "weekly " : ""}"${change.name}"`,
    MOVE_EVENT: `Move "${target ? target.name : `event ${targetId}`}"`,
    DELETE_EVENT: `Delete "${change.name}"`,
    DELETE_TASK: `Delete task "${change.name}"`,
    DELETE_JOURNAL: "Delete journal entry",
    ADD_JOURNAL: change.adds_to_existing ? "Add to your journal" : "Start a journal entry",
    EDIT_JOURNAL: "Edit your journal entry",
  };
  const classes = ["suggestion", change.needs_check && "needs-check", isDelete && "delete"].filter(Boolean).join(" ");

  return (
    <div className={classes}>
      <strong>{titles[type] ?? type}</strong>
      <p>{when(type, change)}</p>
      {type === "ADD_JOURNAL" && <blockquote className="suggestion-quote">{change.text}</blockquote>}
      {type === "EDIT_JOURNAL" && (
        <>
          <p className="suggestion-label">Before</p>
          <blockquote className="suggestion-quote before">{change.old}</blockquote>
          <p className="suggestion-label">After</p>
          <blockquote className="suggestion-quote">{change.text}</blockquote>
        </>
      )}
      {type === "DELETE_JOURNAL" && change.preview && <blockquote className="suggestion-quote">{change.preview}</blockquote>}
      {change.needs_check && <p className="suggestion-warning">⚠ Check this date against your syllabus</p>}
      {description && <p className="suggestion-reason">{description}</p>}
      {status === "PENDING" ? (
        <div className="suggestion-buttons">
          <button className={isDelete ? "danger" : ""} onClick={() => onAnswer(suggestion, "accept")}>
            {isDelete ? "Delete" : "Accept"}
          </button>
          <button className="secondary" onClick={() => onAnswer(suggestion, "decline")}>
            {isDelete ? "Keep it" : "Decline"}
          </button>
        </div>
      ) : (
        <p className="suggestion-status">
          {status === "ACCEPTED" ? (isDelete ? "✓ Deleted" : "✓ Accepted") : status === "DECLINED" ? (isDelete ? "Kept" : "Declined") : status}
        </p>
      )}
      {error && <p className="suggestion-error">{error}</p>}
    </div>
  );
}

function ChatWidget({ events = [], onCalendarChanged, request }) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(""); // "" = idle, otherwise what the AI is doing
  const [acceptingAll, setAcceptingAll] = useState(null); // id of the message whose cards are being accepted
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: "AI",
      text: "Hi! Ask me anything about your schedule, or tap 📎 to send a syllabus (PDF or photo) and I'll suggest its deadlines, exams and classes.",
      suggestions: [],
    },
  ]);
  const fileInput = useRef(null);
  const bottom = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const addMessage = (sender, text, suggestions = []) =>
    setMessages((all) => [...all, { id: crypto.randomUUID(), sender, text, suggestions }]);

  // A message from elsewhere in the app (the overview's "Ask Steady"): open the chat and send it.
  const lastRequest = useRef(null);
  useEffect(() => {
    if (!request || request.id === lastRequest.current) return;
    lastRequest.current = request.id;
    setIsOpen(true);
    send(request.text);
  }, [request]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSend() {
    send(input.trim());
  }

  async function send(text) {
    if (text === "" || busy) return;
    // Earlier turns go along as history (final answers only), so follow-up questions work.
    const history = messages.slice(1).slice(-10).map((m) => ({
      role: m.sender === "USER" ? "user" : "assistant",
      content: m.text,
    }));
    addMessage("USER", text);
    setInput("");
    setBusy("Thinking…");
    try {
      const first = await ai.startChat(text, history);
      const job = await waitFor(first, () => ai.chatJob(first.chat_id), "thinking", (s) =>
        setBusy(`Thinking… ${s}s`),
      );
      addMessage("AI", job.reply, job.suggestions);
    } catch (err) {
      addMessage("AI", `Sorry, something went wrong: ${err.message}`);
    } finally {
      setBusy("");
    }
  }

  async function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = ""; // so choosing the same file again still works
    if (!file || busy) return;
    addMessage("USER", `📎 ${file.name}`);
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      addMessage("AI", `That file is over ${MAX_UPLOAD_MB} MB. Try a smaller photo, or the PDF.`);
      return;
    }
    setBusy("Reading your syllabus…");
    try {
      const first = await ai.uploadSyllabus(file);
      const job = await waitFor(first, () => ai.syllabusImport(first.import_id), "reading", (s) =>
        setBusy(`Reading your syllabus… ${s}s (photos take longer)`),
      );
      addMessage("AI", job.reply, job.suggestions);
    } catch (err) {
      addMessage("AI", `Sorry, I couldn't read that file: ${err.message}`);
    } finally {
      setBusy("");
    }
  }

  function updateSuggestion(id, changes) {
    setMessages((all) =>
      all.map((m) => ({
        ...m,
        suggestions: m.suggestions.map((s) => (s.suggestion_id === id ? { ...s, ...changes } : s)),
      })),
    );
  }

  // Accept or decline one card. Returns true if the calendar changed.
  async function answer(suggestion, choice) {
    try {
      const { status } =
        choice === "accept" ? await ai.accept(suggestion.suggestion_id) : await ai.decline(suggestion.suggestion_id);
      updateSuggestion(suggestion.suggestion_id, { status, error: null });
      return status === "ACCEPTED";
    } catch (err) {
      // e.g. the time is no longer free, or another suggestion must be accepted first
      updateSuggestion(suggestion.suggestion_id, { error: err.message });
      return false;
    }
  }

  async function handleAnswer(suggestion, choice) {
    if (await answer(suggestion, choice)) onCalendarChanged?.();
  }

  async function handleAcceptAll(message) {
    setAcceptingAll(message.id);
    let changed = false;
    for (const s of message.suggestions.filter((s) => s.status === "PENDING")) {
      changed = (await answer(s, "accept")) || changed; // one at a time, so each is checked against the last
    }
    setAcceptingAll(null);
    if (changed) onCalendarChanged?.();
  }

  return (
    <div>
      {isOpen && (
        <div className="chat-window">
          <div className="chat-header">
            <strong>Steady AI</strong>
            <button onClick={() => setIsOpen(false)} aria-label="Close chat">✕</button>
          </div>
          <div className="chat-messages">
            {messages.map((m) => {
              const pending = m.suggestions.filter((s) => s.status === "PENDING").length;
              return (
                <div key={m.id} className={m.sender === "USER" ? "bubble user" : "bubble ai"}>
                  {m.text}
                  {pending > 1 && (
                    <button className="accept-all" onClick={() => handleAcceptAll(m)} disabled={acceptingAll !== null}>
                      {acceptingAll === m.id ? "Accepting…" : `Accept all ${pending}`}
                    </button>
                  )}
                  {m.suggestions.map((s) => (
                    <SuggestionCard key={s.suggestion_id} suggestion={s} events={events} onAnswer={handleAnswer} />
                  ))}
                </div>
              );
            })}
            {busy && <div className="bubble ai thinking">{busy}</div>}
            <div ref={bottom} />
          </div>
          <div className="chat-input">
            <input ref={fileInput} type="file" accept={FILE_TYPES} onChange={handleFile} hidden />
            <button
              className="attach"
              onClick={() => fileInput.current?.click()}
              disabled={Boolean(busy)}
              title="Send a syllabus (PDF or photo)"
              aria-label="Send a syllabus (PDF or photo)"
            >
              📎
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Type a message..."
              disabled={Boolean(busy)}
            />
            <button onClick={handleSend} disabled={Boolean(busy)}>Send</button>
          </div>
        </div>
      )}
      <button className="chat-fab" onClick={() => setIsOpen(!isOpen)} aria-label="Open chat">💬</button>
    </div>
  );
}

export default ChatWidget;
