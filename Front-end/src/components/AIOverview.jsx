import { useEffect, useState } from "react";
import { ai } from "../lib/ai";

// The daily overview: Steady's look back at yesterday, compared with the week before, with suggestions
// for today and a quote. The AI service counts the numbers in code and the model writes the words; it's
// written once a day and saved. "Ask Steady" sends a suggestion to the chat, where Steady can turn it into
// changes to accept. (This box first showed sample text from mockData.js.)

const dayName = (iso) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });

function AIOverview({ onAsk }) {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("loading"); // "loading", "refreshing" or ""

  useEffect(() => {
    let current = true;
    ai.overview()
      .then((o) => current && setOverview(o))
      .catch((err) => current && setError(err.message))
      .finally(() => current && setBusy(""));
    return () => {
      current = false;
    };
  }, []);

  async function refresh() {
    setBusy("refreshing");
    setError("");
    try {
      setOverview(await ai.refreshOverview());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  if (!overview) {
    return (
      <div className="ai-overview">
        <h2>Your Daily Overview</h2>
        {busy ? (
          <p className="overview-muted">Steady is looking back at yesterday…</p>
        ) : (
          <>
            <p className="error">Couldn't load your overview: {error}</p>
            <button className="link" onClick={refresh}>Try again</button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="ai-overview">
      <div className="overview-header">
        <h2>Your Daily Overview</h2>
        <button className="link" onClick={refresh} disabled={Boolean(busy)} title="Write it again, e.g. after a journal entry">
          {busy === "refreshing" ? "Updating…" : "Refresh"}
        </button>
      </div>
      <p className="overview-muted">Looking back at {dayName(overview.looks_back_at)}</p>
      <p className="overview-headline">{overview.headline}</p>
      <p>{overview.yesterday}</p>

      <div className="overview-stats">
        {overview.stats.map((s) => (
          <div className="stat" key={s.label}>
            <span className="stat-value">{s.value}</span>
            <span className="stat-label">{s.label}</span>
            {s.before && <span className="stat-before">{s.before}</span>}
          </div>
        ))}
      </div>
      {overview.compared && <p>{overview.compared}</p>}

      {overview.suggestions.length > 0 && (
        <>
          <h3>For today</h3>
          <ul className="overview-suggestions">
            {overview.suggestions.map((s) => (
              <li key={s.text}>
                <span className={`tag ${s.kind}`}>{s.kind === "schedule" ? "Schedule" : "Habit"}</span>
                <span>{s.text}</span>
                {s.ask && onAsk && (
                  <button className="link ask" onClick={() => onAsk(s.ask)}>
                    Ask Steady →
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <blockquote className="overview-quote">
        “{overview.quote.text}”<cite>— {overview.quote.source}</cite>
      </blockquote>
      {overview.encouragement && <p className="overview-encouragement">{overview.encouragement}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default AIOverview;
