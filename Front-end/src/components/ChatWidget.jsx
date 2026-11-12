import { useEffect, useRef, useState } from "react";
import { ai } from "../lib/ai";
import SuggestionCard from "./home/SuggestionCard";
import { Chat, Paperclip, Send, Sparkle, X } from "./ui/icons";

// Chat with the AI service. Its replies can come with suggestions; each one is a card with
// "Yes" / "Not now". Only those buttons change the calendar or the journal, never the chat text.
// The paperclip sends a syllabus (PDF or photo): the AI reads it and suggests every deadline,
// exam and weekly class in it, as cards like any other suggestion.
// `request` ({id, text}) opens the chat and sends that message, e.g. "Ask Steady" on the daily overview.
// (Restyled for the redesign; the logic is the same as before.)

const MAX_UPLOAD_MB = 15;
const FILE_TYPES = "application/pdf,image/jpeg,image/png,image/webp"; // phones turn HEIC photos into JPEG for these
const POLL_MS = 2500;
const GIVE_UP_MS = 6 * 60 * 1000;
const HISTORY_CHARS = 1500; // of each earlier message sent along (one very long reply mustn't break the chat)
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Ask for a background job (a chat answer or a syllabus import) until it's finished. A failed check (a blip
// in the connection, the server restarting) is tried again a few times before giving up: the job goes on.
async function waitFor(job, fetchJob, running, onTick) {
  const started = Date.now();
  let misses = 0;
  while (job.status === running) {
    if (Date.now() - started > GIVE_UP_MS) throw new Error("it's taking too long; try again in a few minutes");
    await sleep(POLL_MS);
    onTick(Math.round((Date.now() - started) / 1000));
    try {
      job = await fetchJob();
      misses = 0;
    } catch (err) {
      if (++misses >= 4) throw err;
    }
  }
  return job;
}

function ChatWidget({ events = [], onCalendarChanged, request, onSuggestionsMade }) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(""); // "" = idle, otherwise what the AI is doing
  const [acceptingAll, setAcceptingAll] = useState(null); // id of the message whose cards are being accepted
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: "AI",
      text: "Hi! Ask me anything about your schedule, or tap the paperclip to send a syllabus (PDF or photo) and I'll suggest its deadlines, exams and classes.",
      suggestions: [],
    },
  ]);
  const fileInput = useRef(null);
  const bottom = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // `error`: a "Sorry, something went wrong" message, which isn't sent back to the AI as part of the chat.
  const addMessage = (sender, text, suggestions = [], error = false) =>
    setMessages((all) => [...all, { id: crypto.randomUUID(), sender, text, suggestions, error }]);

  // A message from elsewhere in the app (the overview's "Ask Steady"): open the chat and send it.
  const lastRequest = useRef(null);
  useEffect(() => {
    if (!request || request.id === lastRequest.current) return;
    lastRequest.current = request.id;
    setIsOpen(true);
    send(request.text);
  }, [request]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSend(e) {
    e?.preventDefault();
    send(input.trim());
  }

  async function send(text) {
    if (text === "" || busy) return;
    // Earlier turns go along as history (final answers only), so follow-up questions work.
    const history = messages
      .slice(1)
      .filter((m) => !m.error)
      .slice(-10)
      .map((m) => ({ role: m.sender === "USER" ? "user" : "assistant", content: m.text.slice(0, HISTORY_CHARS) }));
    addMessage("USER", text);
    setInput("");
    setBusy("Thinking…");
    try {
      const first = await ai.startChat(text, history);
      const job = await waitFor(first, () => ai.chatJob(first.chat_id), "thinking", (s) =>
        setBusy(`Thinking… ${s}s`),
      );
      addMessage("AI", job.reply, job.suggestions);
      if (job.suggestions?.length) onSuggestionsMade?.();
    } catch (err) {
      addMessage("AI", `Sorry, something went wrong: ${err.message}`, [], true);
    } finally {
      setBusy("");
    }
  }

  async function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = ""; // so choosing the same file again still works
    if (!file || busy) return;
    addMessage("USER", `Attached: ${file.name}`);
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
      if (job.suggestions?.length) onSuggestionsMade?.();
    } catch (err) {
      addMessage("AI", `Sorry, I couldn't read that file: ${err.message}`, [], true);
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
    updateSuggestion(suggestion.suggestion_id, { answering: choice, error: null });
    try {
      const { status } =
        choice === "accept" ? await ai.accept(suggestion.suggestion_id) : await ai.decline(suggestion.suggestion_id);
      updateSuggestion(suggestion.suggestion_id, { status, error: null, answering: null });
      return status === "ACCEPTED";
    } catch (err) {
      // e.g. the time is no longer free, or another suggestion must be accepted first
      updateSuggestion(suggestion.suggestion_id, { error: err.message, answering: null });
      return false;
    }
  }

  async function handleAnswer(suggestion, choice) {
    if (await answer(suggestion, choice)) onCalendarChanged?.();
    onSuggestionsMade?.(); // the Home suggestions card shows the same suggestion
  }

  async function handleAcceptAll(message) {
    setAcceptingAll(message.id);
    let changed = false;
    for (const s of message.suggestions.filter((s) => s.status === "PENDING" && !s.answering)) {
      changed = (await answer(s, "accept")) || changed; // one at a time, so each is checked against the last
    }
    setAcceptingAll(null);
    if (changed) onCalendarChanged?.();
    onSuggestionsMade?.();
  }

  return (
    <>
      {isOpen && (
        <section className="chat-panel box" aria-labelledby="chat-title">
          <div className="card-header fill-purple">
            <h2 id="chat-title"><Sparkle /> Steady AI</h2>
            <button type="button" className="btn icon-btn surface" onClick={() => setIsOpen(false)} aria-label="Close chat"><X /></button>
          </div>
          <div className="chat-messages" aria-live="polite">
            {messages.map((m) => {
              const pending = m.suggestions.filter((s) => s.status === "PENDING").length;
              return (
                <div key={m.id} className={`chat-msg ${m.sender === "USER" ? "user" : "ai"}`}>
                  <p className="chat-bubble">{m.text}</p>
                  {pending > 1 && (
                    <button type="button" className="btn small green" onClick={() => handleAcceptAll(m)} disabled={acceptingAll !== null}>
                      {acceptingAll === m.id ? "Accepting…" : `Accept all ${pending}`}
                    </button>
                  )}
                  {m.suggestions.length > 0 && (
                    <ul className="sugg-list">
                      {m.suggestions.map((s) => (
                        <SuggestionCard key={s.suggestion_id} suggestion={s} events={events} onAnswer={handleAnswer} variant="chat" />
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
            {busy && (
              <div className="chat-msg ai">
                <p className="chat-bubble thinking" role="status">{busy}</p>
              </div>
            )}
            <div ref={bottom} />
          </div>
          <form className="chat-composer" onSubmit={handleSend}>
            <input ref={fileInput} type="file" accept={FILE_TYPES} onChange={handleFile} hidden />
            <button type="button" className="btn icon-btn surface" onClick={() => fileInput.current?.click()} disabled={Boolean(busy)}
              title="Send a syllabus (PDF or photo)" aria-label="Send a syllabus (PDF or photo)">
              <Paperclip />
            </button>
            <label htmlFor="chat-input" className="sr-only">Message Steady</label>
            <input id="chat-input" ref={inputRef} className="inp" value={input} onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Steady…" disabled={Boolean(busy)} autoComplete="off" />
            <button type="submit" className="btn icon-btn" disabled={Boolean(busy) || !input.trim()} aria-label="Send">
              <Send />
            </button>
          </form>
        </section>
      )}
      <button type="button" className="chat-fab" onClick={() => setIsOpen(!isOpen)} aria-label={isOpen ? "Close chat" : "Open chat with Steady"}
        aria-expanded={isOpen}>
        <Chat />
      </button>
    </>
  );
}

export default ChatWidget;
