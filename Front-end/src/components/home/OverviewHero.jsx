import { Box, Skeleton, Sticker } from "../ui";
import { Check, Refresh, Sparkle, X } from "../ui/icons";

// The daily overview (GET /overview): the AI's look back at yesterday. The numbers, the tiles and the
// sticker are counted by the AI service in code; the model writes the words. Older saved overviews have no
// tiles, so they're built from what they do have.

export function greeting(date = new Date()) {
  const h = date.getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

const shortDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });

export function overviewTiles(o) {
  if (o.tiles) return o.tiles;
  const schedule = (o.suggestions ?? []).find((s) => s.kind === "schedule");
  return { went_well: [], missed: [], focus: schedule?.text ?? o.suggestions?.[0]?.text ?? "", focus_ask: schedule?.ask ?? "" };
}

// What the marquee scrolls: the wins, today's focus and the nudge (decorative; the same text is in the card).
export function overviewMarquee(o) {
  if (!o) return [];
  const t = overviewTiles(o);
  return [...t.went_well, t.focus && `Focus: ${t.focus}`, o.encouragement];
}

function Tiles({ o, onAsk }) {
  const t = overviewTiles(o);
  return (
    <div className="tiles">
      <div className="tile fill-green">
        <h3>Went well</h3>
        {t.went_well.length ? (
          <ul>{t.went_well.map((w) => <li key={w}><Check /> {w}</li>)}</ul>
        ) : (
          <p>Nothing logged yet.</p>
        )}
      </div>
      <div className="tile fill-orange">
        <h3>Didn't get to</h3>
        {t.missed.length ? (
          <ul>{t.missed.map((m) => <li key={m}><X /> {m}</li>)}</ul>
        ) : (
          <p>Nothing left over.</p>
        )}
      </div>
      <div className="tile fill-blue focus">
        <h3>Focus today</h3>
        <p>{t.focus || "Take it one task at a time."}</p>
        {t.focus_ask && onAsk && (
          <button type="button" className="btn small surface" onClick={() => onAsk(t.focus_ask)}>
            <Sparkle width={16} height={16} /> Ask Steady
          </button>
        )}
      </div>
    </div>
  );
}

function OverviewHero({ firstName, overview, error, busy, onRefresh, onAsk, compact = false }) {
  const name = firstName || "there";
  const heading = (
    <h1 className={compact ? "" : "hero-title"}>
      {greeting()}, <span className="name-hl">{name}</span>.
    </h1>
  );
  const kicker = (
    <div className="kicker-row">
      <span className="tag fill-purple"><Sparkle /> Daily overview{overview ? ` · ${shortDay(overview.looks_back_at)}` : ""}</span>
      {overview?.written_by === "code" && overview.headline !== "Welcome to Steady!" && <span className="tag">Written without the AI today</span>}
    </div>
  );

  if (!overview) {
    return (
      <Box className={compact ? "phone-hero slam slam-1" : "hero slam slam-1"} aria-labelledby="hero-title" aria-busy={busy === "loading"}>
        {kicker}
        <div id="hero-title">{heading}</div>
        {busy === "loading" ? (
          <>
            <p className="lede">Steady is looking back at yesterday…</p>
            <Skeleton height={compact ? 120 : 110} />
          </>
        ) : (
          <div className="alert" role="alert">
            <span>Couldn't load your overview{error ? `: ${error}` : "."}</span>
            <button type="button" className="btn small surface" onClick={onRefresh}><Refresh width={16} height={16} /> Try again</button>
          </div>
        )}
      </Box>
    );
  }

  const done = overview.tasks_yesterday;
  return (
    <Box as="section" className={compact ? "phone-hero slam slam-1" : "hero slam slam-1"} aria-labelledby="hero-title">
      {!compact && done && done.due > 0 && (
        <Sticker ring="YESTERDAY · YESTERDAY · YESTERDAY · YESTERDAY ·" color="yellow">
          {done.done}/{done.due}<small>DONE</small>
        </Sticker>
      )}
      {kicker}
      <div id="hero-title">{heading}</div>
      <p className="lede">{compact ? overview.headline : [overview.headline, overview.yesterday].filter(Boolean).join(" ")}</p>
      {compact && done && done.due > 0 && <p className="mono">{done.done}/{done.due} tasks done yesterday</p>}
      <Tiles o={overview} onAsk={onAsk} />
      {!compact && (
        <div className="overview-foot">
          {overview.compared && <p className="ink2">{overview.compared}</p>}
          {(overview.suggestions ?? []).filter((s) => s.kind === "habit").slice(0, 1).map((s) => (
            <p key={s.text}><span className="tag fill-pink">Habit</span> {s.text}</p>
          ))}
          {overview.quote && (
            <blockquote className="quote">
              “{overview.quote.text}”<cite>— {overview.quote.source}</cite>
            </blockquote>
          )}
          <div className="hero-actions">
            {overview.encouragement && <strong>{overview.encouragement}</strong>}
            <span style={{ flex: 1 }} />
            <button type="button" className="btn small surface" onClick={onRefresh} disabled={busy === "refreshing"}>
              <Refresh width={16} height={16} /> {busy === "refreshing" ? "Updating…" : "Refresh"}
            </button>
          </div>
        </div>
      )}
    </Box>
  );
}

export default OverviewHero;
