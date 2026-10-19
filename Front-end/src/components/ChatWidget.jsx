import { useState } from "react";
import { ai } from "../lib/ai";

// Chat with the AI service. Its replies can come with suggestions; each one is a card
// with Accept / Decline. Only those buttons change the calendar, never the chat text.

function formatRange(change) {
  const start = new Date(change.start);
  const end = new Date(change.end);
  const day = start.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  const time = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return `${day}, ${time(start)} – ${time(end)}`;
}

function SuggestionCard({ suggestion, events, onAnswer }) {
  const { type, proposed_change: change, target_id: targetId, description, status, error } = suggestion;
  const target = events.find((e) => String(e.event_id) === String(targetId));
  const title =
    type === "CREATE_EVENT"
      ? `Add "${change.name}"`
      : `Move "${target ? target.name : `event ${targetId}`}"`;

  return (
    <div className="suggestion">
      <strong>{title}</strong>
      <p>{formatRange(change)}</p>
      {description && <p className="suggestion-reason">{description}</p>}
      {status === "PENDING" ? (
        <div className="suggestion-buttons">
          <button onClick={() => onAnswer(suggestion, "accept")}>Accept</button>
          <button className="secondary" onClick={() => onAnswer(suggestion, "decline")}>Decline</button>
        </div>
      ) : (
        <p className="suggestion-status">{status === "ACCEPTED" ? "✓ Accepted" : status === "DECLINED" ? "Declined" : status}</p>
      )}
      {error && <p className="suggestion-error">{error}</p>}
    </div>
  );
}

function ChatWidget({ events = [], onCalendarChanged }) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [messages, setMessages] = useState([
    { id: 1, sender: "AI", text: "Hi! Ask me anything about your schedule.", suggestions: [] },
  ]);

  async function handleSend() {
    const text = input.trim();
    if (text === "" || thinking) return;
    const userMsg = { id: Date.now(), sender: "USER", text, suggestions: [] };
    // Earlier turns go along as history (final answers only), so follow-up questions work.
    const history = messages.slice(1).slice(-10).map((m) => ({
      role: m.sender === "USER" ? "user" : "assistant",
      content: m.text,
    }));
    setMessages((all) => [...all, userMsg]);
    setInput("");
    setThinking(true);
    try {
      const { reply, suggestions } = await ai.chat(text, history);
      setMessages((all) => [...all, { id: Date.now() + 1, sender: "AI", text: reply, suggestions }]);
    } catch (err) {
      setMessages((all) => [...all, { id: Date.now() + 1, sender: "AI", text: `Sorry, something went wrong: ${err.message}`, suggestions: [] }]);
    } finally {
      setThinking(false);
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

  async function handleAnswer(suggestion, answer) {
    try {
      const { status } = answer === "accept" ? await ai.accept(suggestion.suggestion_id) : await ai.decline(suggestion.suggestion_id);
      updateSuggestion(suggestion.suggestion_id, { status, error: null });
      if (status === "ACCEPTED") onCalendarChanged?.();
    } catch (err) {
      // e.g. the time is no longer free, or another suggestion must be accepted first
      updateSuggestion(suggestion.suggestion_id, { error: err.message });
    }
  }

  return (
    <div>
      {isOpen && (
        <div className="chat-window">
          <div className="chat-header">
            <strong>Steady AI</strong>
            <button onClick={() => setIsOpen(false)}>✕</button>
          </div>
          <div className="chat-messages">
            {messages.map((m) => (
              <div key={m.id} className={m.sender === "USER" ? "bubble user" : "bubble ai"}>
                {m.text}
                {m.suggestions.map((s) => (
                  <SuggestionCard key={s.suggestion_id} suggestion={s} events={events} onAnswer={handleAnswer} />
                ))}
              </div>
            ))}
            {thinking && <div className="bubble ai thinking">Thinking… (this can take a minute)</div>}
          </div>
          <div className="chat-input">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Type a message..."
              disabled={thinking}
            />
            <button onClick={handleSend} disabled={thinking}>Send</button>
          </div>
        </div>
      )}
      <button className="chat-fab" onClick={() => setIsOpen(!isOpen)}>💬</button>
    </div>
  );
}

export default ChatWidget;
