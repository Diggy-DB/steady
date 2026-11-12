import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { addEvent, deleteEvent, loadCommitments, saveProfile } from "../lib/data";
import { PRIORITY_OPTIONS, commitmentToEvent, eventToCommitment } from "../lib/onboarding";
import { useTheme } from "../lib/theme";
import { Alert, Avatar, Box, Card, Field, Logo, Skeleton, ThemeToggle } from "../components/ui";
import { ArrowLeft, Brain, Check, Lock, LogOut, Moon, Plus, Sun } from "../components/ui/icons";
import { CommitmentForm, CommitmentRow, PriorityPicker, TimezoneSelect, WorkTimeChoice } from "../components/profile";
import MemoryPanel from "../components/MemoryPanel";

// Settings: everything Steady knows about the user. Profile fields save together from the save bar (the same
// single profile update as before); fixed commitments are calendar rows, added and removed straight away;
// the theme applies at once and isn't an unsaved change.

const asList = (text) => text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);

function formFrom(profile) {
  return {
    first_name: profile.first_name ?? "",
    last_name: profile.last_name ?? "",
    timezone: profile.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    preferred_work_time: profile.preferred_work_time ?? "Morning",
    priorities: profile.priorities ?? [],
    hobbies: (profile.hobbies ?? []).join(", "),
    additional_information: profile.additional_information ?? "",
  };
}

function Settings({ profile, email, onSaved, onCalendarChanged }) {
  const [form, setForm] = useState(() => formFrom(profile));
  const [status, setStatus] = useState("saved"); // "saved" | "just-saved" | "dirty"
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [commitments, setCommitments] = useState(null);
  const [commitmentError, setCommitmentError] = useState("");
  const [addingCommitment, setAddingCommitment] = useState(false);
  const [busyCommitment, setBusyCommitment] = useState(false);
  const [showMemories, setShowMemories] = useState(false);
  const [theme, setTheme] = useTheme();

  const set = (field, value) => {
    setForm((f) => ({ ...f, [field]: value }));
    setStatus("dirty");
  };

  async function reloadCommitments() {
    try {
      setCommitments((await loadCommitments()).map(eventToCommitment));
      setCommitmentError("");
    } catch (err) {
      setCommitmentError(err.message);
    }
  }

  useEffect(() => {
    reloadCommitments();
  }, []);

  async function save() {
    if (!form.first_name.trim()) {
      setError("Your first name can't be empty.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      // The same profile update as the old profile panel.
      const saved = await saveProfile(profile.user_id, {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        timezone: form.timezone,
        preferred_work_time: form.preferred_work_time,
        priorities: form.priorities.slice(0, 10),
        hobbies: asList(form.hobbies).slice(0, 15),
        additional_information: form.additional_information.trim().slice(0, 1000),
      });
      onSaved(saved);
      setStatus("just-saved");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function discard() {
    setForm(formFrom(profile));
    setStatus("saved");
    setError("");
  }

  async function addCommitment(c) {
    setBusyCommitment(true);
    try {
      await addEvent(commitmentToEvent(c));
      await reloadCommitments();
      onCalendarChanged();
      setAddingCommitment(false);
      return true;
    } catch (err) {
      setCommitmentError(err.message);
      return false;
    } finally {
      setBusyCommitment(false);
    }
  }

  async function removeCommitment(c) {
    if (!window.confirm(`Remove "${c.name}" from every day it repeats?`)) return;
    try {
      await deleteEvent(c.id);
      await reloadCommitments();
      onCalendarChanged();
    } catch (err) {
      setCommitmentError(err.message);
    }
  }

  return (
    <div className="page settings">
      <header className="box topbar slam">
        <Logo />
        <span className="spacer" />
        <a className="btn surface" href="#/"><ArrowLeft width={18} height={18} /> Back to Home</a>
        <ThemeToggle />
        <Avatar name={form.first_name} />
      </header>

      <div className="settings-title slam slam-1">
        <div>
          <h1 className="hero-title">Settings</h1>
          <p className="lede">Everything Steady knows about you. Change it any time.</p>
        </div>
        <span className={`tag ${status === "dirty" ? "fill-orange" : "fill-green"}`} role="status">
          {status === "dirty" ? "Unsaved changes" : status === "just-saved" ? <><Check /> Saved just now</> : <><Check /> All changes saved</>}
        </span>
      </div>
      {error && <Alert>{error}</Alert>}

      <main className="settings-grid">
        <Card title="Profile" color="yellow" className="slam slam-2">
          <div className="row2">
            <Field label="First name" autoComplete="given-name" value={form.first_name} onChange={(e) => set("first_name", e.target.value)} />
            <Field label="Last name" autoComplete="family-name" value={form.last_name} onChange={(e) => set("last_name", e.target.value)} />
          </div>
          <Field label="Email" value={email ?? ""} readOnly aria-readonly="true" hint="The email you sign in with." />
          <TimezoneSelect value={form.timezone} onChange={(v) => set("timezone", v)}
            hint="Your daily overview and every time Steady suggests use this timezone." />
        </Card>

        <Card title="Preferred working time" color="blue" className="slam slam-2">
          <WorkTimeChoice value={form.preferred_work_time} onChange={(v) => set("preferred_work_time", v)} />
          <p className="hint">A preference, not a rule. Steady tries to follow it.</p>
        </Card>

        <Card title="Hard constraints" color="purple" icon={<Lock />} className="slam slam-3"
          actions={!addingCommitment && (
            <button type="button" className="btn small surface" onClick={() => setAddingCommitment(true)}><Plus width={16} height={16} /> Add</button>
          )}>
          {commitmentError && <Alert action={<button type="button" className="btn small surface" onClick={reloadCommitments}>Try again</button>}>{commitmentError}</Alert>}
          {commitments === null ? (
            <Skeleton height={70} />
          ) : commitments.length === 0 ? (
            <p className="empty">No fixed commitments yet. Add your classes, shifts and appointments.</p>
          ) : (
            <ul className="constraint-list">
              {commitments.map((c) => <CommitmentRow key={c.id} commitment={c} onRemove={() => removeCommitment(c)} />)}
            </ul>
          )}
          {addingCommitment && <CommitmentForm onAdd={addCommitment} busy={busyCommitment} />}
          <p className="hint">Steady never suggests moving these. They're saved as soon as you add or remove them.</p>
        </Card>

        <Card title="Hobbies & priorities" color="pink" className="slam slam-3">
          <PriorityPicker options={PRIORITY_OPTIONS} value={form.priorities} onChange={(v) => set("priorities", v)} />
          <Field label="Other hobbies (separated by commas)" value={form.hobbies} onChange={(e) => set("hobbies", e.target.value)}
            placeholder="Soccer, guitar, cooking" />
        </Card>

        <Card title="About you" color="orange" className="slam slam-4">
          <Field label="Anything Steady should know about you?" as="textarea" maxLength={1000} value={form.additional_information}
            onChange={(e) => set("additional_information", e.target.value)}
            hint="For example, what motivates you to study. Used to personalize feedback." />
        </Card>

        <Card title="Appearance & account" color="green" className="slam slam-4">
          <div className="field">
            <span className="field-label" id="theme-label">Theme</span>
            <div className="segmented" role="group" aria-labelledby="theme-label">
              <button type="button" aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Sun /> Light</button>
              <button type="button" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Moon /> Dark</button>
            </div>
          </div>
          <p className="privacy-note"><Lock /> Your calendar, tasks, journal and AI history are visible only to you.</p>
          <button type="button" className="btn surface" style={{ alignSelf: "flex-start" }} onClick={() => setShowMemories(true)}>
            <Brain width={18} height={18} /> What Steady remembers
          </button>
          <div className="account-row">
            <p>Signed in as <strong>{email}</strong></p>
            <button type="button" className="btn surface" onClick={() => supabase.auth.signOut()}><LogOut width={18} height={18} /> Log out</button>
          </div>
        </Card>
      </main>

      {status === "dirty" && (
        <Box className="savebar" role="region" aria-label="Unsaved changes">
          <span>You have unsaved changes.</span>
          <button type="button" className="btn surface" onClick={discard} disabled={saving}>Discard</button>
          <button type="button" className="btn green" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save changes"}</button>
        </Box>
      )}
      {showMemories && <MemoryPanel onClose={() => setShowMemories(false)} />}
    </div>
  );
}

export default Settings;
