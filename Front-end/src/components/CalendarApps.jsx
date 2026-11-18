import { useEffect, useRef, useState } from "react";
import { ai } from "../lib/ai";
import { linkGoogle, loadIdentities, unlinkGoogle } from "../lib/auth";
import {
  calendarLinkUrl,
  createCalendarLink,
  deleteCalendarImport,
  deleteCalendarLink,
  loadCalendarImports,
  loadCalendarLink,
} from "../lib/data";
import { Alert, Skeleton } from "./ui";
import { Calendar, Check, GoogleG } from "./ui/icons";

// Settings › Calendar apps, three parts:
// - Import a calendar: Google Calendar, iCloud or Outlook into Steady, through its private iCal address (the AI
//   server downloads it; the events come in fixed, and follow the other calendar).
// - Your calendar link: the other way, Steady's events and due dates in Apple Calendar, Google Calendar or Outlook.
// - Google account: log in with Google (connect or disconnect it). It doesn't read the calendar.

function ago(when) {
  const minutes = Math.round((Date.now() - new Date(when).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / 1440)} days ago`;
}

function importStatus(i) {
  if (i.last_error) return `Couldn't update ${i.last_checked_at ? ago(i.last_checked_at) : ""}: ${i.last_error}`;
  return i.last_synced_at ? `Updated ${ago(i.last_synced_at)}` : "Not updated yet";
}

function CalendarApps({ userId, onCalendarChanged = () => {} }) {
  const [identities, setIdentities] = useState(null); // null = loading
  const [link, setLink] = useState(undefined); // undefined = loading, null = none
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [imports, setImports] = useState(undefined); // undefined = loading
  const [address, setAddress] = useState("");
  const [done, setDone] = useState("");
  const input = useRef(null);

  const reloadImports = () => loadCalendarImports().then(setImports);

  useEffect(() => {
    reloadImports().catch((err) => {
      setImports([]);
      setError(err.message);
    });
    loadIdentities().then(setIdentities).catch((err) => {
      setIdentities([]);
      setError(err.message);
    });
    loadCalendarLink().then(setLink).catch((err) => {
      setLink(null);
      setError(err.message);
    });
  }, []);

  const google = identities?.find((i) => i.provider === "google");
  const canDisconnect = Boolean(google) && identities.length > 1; // never remove someone's only way to sign in
  const url = link ? calendarLinkUrl(link.token) : "";
  const webcal = url.replace(/^https?:/, "webcal:");
  const addToGoogle = `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal)}`;

  async function run(what, action) {
    setBusy(what);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  const connect = () => run("google", linkGoogle); // leaves for Google; the app reopens Settings afterwards
  const disconnect = () => {
    if (!window.confirm("Disconnect Google? You'll log in with your email and password.")) return;
    run("google", async () => {
      await unlinkGoogle(google);
      setIdentities(await loadIdentities());
    });
  };
  const create = () => run("link", async () => setLink(await createCalendarLink(userId)));
  const renew = () => {
    if (!window.confirm("Make a new link? The old one stops working, so calendars that use it stop updating.")) return;
    run("link", async () => {
      await deleteCalendarLink(userId);
      setLink(await createCalendarLink(userId));
      setCopied(false);
    });
  };
  const turnOff = () => {
    if (!window.confirm("Turn off your calendar link? Calendars that use it stop updating.")) return;
    run("link", async () => {
      await deleteCalendarLink(userId);
      setLink(null);
      setCopied(false);
    });
  };

  const addImport = (e) => {
    e.preventDefault();
    setDone("");
    run("import", async () => {
      const result = await ai.importCalendar(address.trim());
      setAddress("");
      await reloadImports();
      onCalendarChanged();
      setDone(`Imported ${result.events} event${result.events === 1 ? "" : "s"} from ${result.name}.`);
    });
  };
  const syncOne = (i) => {
    setDone("");
    run(`sync-${i.import_id}`, async () => {
      const [result] = await ai.syncCalendars({ import_id: i.import_id });
      await reloadImports();
      if (result?.changed || result?.removed) onCalendarChanged();
      if (result?.ok) setDone(`${i.name} is up to date.`);
    });
  };
  const removeImport = (i) => {
    if (!window.confirm(`Remove ${i.name}? Its events leave Steady. Nothing changes in the calendar itself.`)) return;
    setDone("");
    run(`sync-${i.import_id}`, async () => {
      await deleteCalendarImport(i.import_id);
      await reloadImports();
      onCalendarChanged();
    });
  };

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      input.current?.select(); // copying was refused: select it so they can copy it themselves
    }
  }

  return (
    <>
      {error && <Alert>{error}</Alert>}
      {done && <p className="cal-done" role="status"><Check width={16} height={16} /> {done}</p>}

      <div className="cal-part">
        <h3 className="cal-h">Import a calendar</h3>
        <p>
          See your Google, Apple or Outlook calendar in Steady. The AI plans around those events and never moves them;
          change them in the calendar they come from, and Steady follows (it checks every hour while you use it).
        </p>
        {imports === undefined ? (
          <Skeleton height={44} />
        ) : imports.length > 0 && (
          <ul className="import-list">
            {imports.map((i) => (
              <li key={i.import_id} className="import-row">
                <span className="import-info">
                  <strong>{i.name}</strong>
                  <span className={`hint ${i.last_error ? "import-error" : ""}`}>{importStatus(i)}</span>
                </span>
                <span className="btn-row">
                  <button type="button" className="btn small surface" onClick={() => syncOne(i)} disabled={busy !== ""}>
                    {busy === `sync-${i.import_id}` ? "Updating…" : "Update now"}
                  </button>
                  <button type="button" className="btn small surface" onClick={() => removeImport(i)} disabled={busy !== ""}>Remove</button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <form className="link-row" onSubmit={addImport}>
          <input className="inp mono" type="url" inputMode="url" autoComplete="off" autoCapitalize="none" spellCheck={false}
            placeholder="Paste the calendar's iCal address" aria-label="The calendar's private iCal address"
            value={address} onChange={(e) => setAddress(e.target.value)} required />
          <button type="submit" className="btn small" disabled={busy !== "" || !address.trim()}>
            {busy === "import" ? "Importing…" : "Import"}
          </button>
        </form>
        <details className="how-to">
          <summary>Where do I find the address?</summary>
          <ul>
            <li>
              <strong>Google Calendar</strong>, on a computer: calendar.google.com › Settings (the gear) › under
              {" "}<em>Settings for my calendars</em>, click your calendar › <em>Integrate calendar</em> › copy
              {" "}<em>Secret address in iCal format</em>. Not there? A school or work account may have it turned off.
            </li>
            <li>
              <strong>Apple iCloud</strong>: in the Calendar app, tap Calendars › the ⓘ next to the calendar › turn on
              {" "}<em>Public Calendar</em> › <em>Share Link</em> › Copy.
            </li>
            <li>
              <strong>Outlook</strong>: Settings › Calendar › Shared calendars › <em>Publish a calendar</em> (can view
              all details) › copy the ICS link.
            </li>
          </ul>
          <p className="hint">Keep the address to yourself: anyone who has it can see that calendar.</p>
        </details>
      </div>

      <div className="cal-part">
        <h3 className="cal-h">Your calendar link</h3>
        <p>See your Steady events and due dates in Apple Calendar, Google Calendar or Outlook. They update by themselves.</p>
        {link === undefined ? (
          <Skeleton height={44} />
        ) : link ? (
          <>
            <div className="link-row">
              <input ref={input} className="inp mono" readOnly value={url} aria-label="Your calendar link"
                onFocus={(e) => e.target.select()} />
              <button type="button" className="btn small" onClick={copy}>
                {copied ? <><Check width={16} height={16} /> Copied</> : "Copy"}
              </button>
            </div>
            <div className="btn-row">
              <a className="btn small surface" href={webcal}>Add to Apple Calendar</a>
              <a className="btn small surface" href={addToGoogle} target="_blank" rel="noreferrer">Add to Google Calendar</a>
            </div>
            <p className="hint">
              Anyone with this link can see your events and due dates, so keep it to yourself. Apple Calendar checks for
              changes about every hour; Google Calendar can take up to a day.
            </p>
            <div className="btn-row">
              <button type="button" className="btn small surface" onClick={renew} disabled={busy === "link"}>Make a new link</button>
              <button type="button" className="btn small surface" onClick={turnOff} disabled={busy === "link"}>Turn off</button>
            </div>
          </>
        ) : (
          <button type="button" className="btn surface" style={{ alignSelf: "flex-start" }} onClick={create} disabled={busy === "link"}>
            <Calendar width={18} height={18} /> {busy === "link" ? "Making your link…" : "Create my calendar link"}
          </button>
        )}
      </div>

      <div className="cal-part">
        <h3 className="cal-h">Google account</h3>
        {identities === null ? (
          <Skeleton height={44} />
        ) : google ? (
          <>
            <div className="account-line">
              <span className="who"><GoogleG size={20} /> Connected as <strong>{google.identity_data?.email ?? "your Google account"}</strong></span>
              {canDisconnect && (
                <button type="button" className="btn small surface" onClick={disconnect} disabled={busy === "google"}>Disconnect</button>
              )}
            </div>
            <p className="hint">
              {canDisconnect ? "You can log in with Google or with your email and password." : "You sign in with Google, so it stays connected."}
            </p>
          </>
        ) : (
          <>
            <div className="account-line">
              <span className="who">Not connected.</span>
              <button type="button" className="btn small surface google-btn" onClick={connect} disabled={busy === "google"}>
                <GoogleG size={16} /> {busy === "google" ? "Opening Google…" : "Connect Google"}
              </button>
            </div>
            <p className="hint">Only for logging in with Google. To see your Google Calendar in Steady, import it above.</p>
          </>
        )}
      </div>
    </>
  );
}

export default CalendarApps;
