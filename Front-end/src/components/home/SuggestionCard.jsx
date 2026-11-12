import { describeSuggestion } from "../../lib/suggestions";
import { Check, X } from "../ui/icons";

// One AI suggestion with its two answers. `onAnswer(suggestion, "accept" | "decline")` is the existing flow
// (the AI service checks the suggestion again, then applies it); this only shows what happened.
// variant "chat" words the buttons as replies ("Yes, move it" / "Not now").
function SuggestionCard({ suggestion, events, onAnswer, variant = "card" }) {
  const { status, error, answering, description } = suggestion;
  const d = describeSuggestion(suggestion, events);
  const chat = variant === "chat";
  const yes = chat ? d.yes : d.isDelete ? "Delete" : "Accept";
  const no = chat ? "Not now" : d.isDelete ? "Keep it" : "Decline";

  return (
    <li className="sugg">
      <div className="top">
        <span className={`tag fill-${d.color}`}>{d.kind}</span>
        {suggestion.proposed_change.needs_check && <span className="tag fill-orange">Check this date</span>}
      </div>
      <strong>{d.title}</strong>
      {d.change && <span className="change">{d.change}</span>}
      {d.before && (
        <>
          <span className="field-label">Before</span>
          <p className="sugg-quote before">{d.before}</p>
          <span className="field-label">After</span>
        </>
      )}
      {d.quote && <p className="sugg-quote">{d.quote}</p>}
      {description && <p className="reason">{description}</p>}

      {status === "PENDING" ? (
        <div className="buttons">
          {/* Locked while the answer is on its way: a second tap once added an event twice. */}
          <button type="button" className={`btn small ${d.isDelete ? "orange" : "green"}`} disabled={Boolean(answering)}
            onClick={() => onAnswer(suggestion, "accept")}>
            <Check width={16} height={16} /> {answering === "accept" ? "Checking…" : yes}
          </button>
          <button type="button" className="btn small surface" disabled={Boolean(answering)} onClick={() => onAnswer(suggestion, "decline")}>
            {no}
          </button>
        </div>
      ) : status === "ACCEPTED" ? (
        <p className="result-row fill-green" role="status"><Check /> {d.isDelete ? "Deleted" : "Accepted"} · checked and applied</p>
      ) : (
        <p className="result-row fill-orange" role="status"><X /> {d.isDelete ? "Kept" : "Declined"} · nothing changed</p>
      )}
      {/* The AI service said no (a conflict, a fixed event, already answered): the suggestion stays. */}
      {error && <p className="result-row fill-orange" role="alert"><X /> {error}</p>}
    </li>
  );
}

export default SuggestionCard;
