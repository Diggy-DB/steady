import { useState } from "react";
import { saveProfile } from "../lib/data";

// The user's profile (public.users): who they are and how they like to work. Steady's AI reads it
// when planning (for example, it suggests evening study times to someone who works best at night).
// Saved straight to Supabase; Row Level Security only lets people change their own row.

const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
const asList = (text) => text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);

// A profile counts as filled in once any of the "about you" fields is set.
export const profileIsEmpty = (p) =>
  !p.priorities?.length && !p.hobbies?.length && !(p.additional_information ?? "").trim();

function ProfilePanel({ profile, firstTime, onSaved, onClose }) {
  const [form, setForm] = useState({
    first_name: profile.first_name ?? "",
    last_name: profile.last_name ?? "",
    timezone: profile.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    preferred_work_time: profile.preferred_work_time ?? "Morning",
    priorities: (profile.priorities ?? []).join("\n"),
    hobbies: (profile.hobbies ?? []).join(", "),
    additional_information: profile.additional_information ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const saved = await saveProfile(profile.user_id, {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        timezone: form.timezone,
        preferred_work_time: form.preferred_work_time,
        priorities: asList(form.priorities).slice(0, 10),
        hobbies: asList(form.hobbies).slice(0, 15),
        additional_information: form.additional_information.trim().slice(0, 1000),
      });
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="popup-overlay" onClick={onClose}>
      <div className="popup" onClick={(e) => e.stopPropagation()}>
        <button className="popup-close" onClick={onClose} aria-label="Close">✕</button>
        <h2>{firstTime ? "Welcome! Tell Steady about you" : "Your profile"}</h2>
        <p>Steady's AI uses this when it plans your week. Only you can see it.</p>
        <form className="profile-form" onSubmit={handleSave}>
          <div className="profile-row">
            <label>
              First name
              <input value={form.first_name} onChange={set("first_name")} required />
            </label>
            <label>
              Last name
              <input value={form.last_name} onChange={set("last_name")} />
            </label>
          </div>
          <label>
            Email
            <input value={profile.email} disabled />
          </label>
          <label>
            Time zone
            <select value={form.timezone} onChange={set("timezone")}>
              {(ZONES.includes(form.timezone) ? ZONES : [form.timezone, ...ZONES]).map((z) => (
                <option key={z} value={z}>{z.replaceAll("_", " ")}</option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>I do my best work in the</legend>
            {["Morning", "Night"].map((t) => (
              <label key={t} className="inline">
                <input
                  type="radio"
                  name="work-time"
                  value={t}
                  checked={form.preferred_work_time === t}
                  onChange={set("preferred_work_time")}
                />
                {t === "Morning" ? "Morning" : "Evening / night"}
              </label>
            ))}
          </fieldset>
          <label>
            Priorities, most important first (one per line)
            <textarea
              value={form.priorities}
              onChange={set("priorities")}
              placeholder={"CSE 260\nSleep 8 hours\nGym 3 times a week"}
              rows={4}
            />
          </label>
          <label>
            Hobbies (separated by commas)
            <input value={form.hobbies} onChange={set("hobbies")} placeholder="Soccer, guitar, cooking" />
          </label>
          <label>
            Anything else Steady should know
            <textarea
              value={form.additional_information}
              onChange={set("additional_information")}
              placeholder="I work at the library Tue/Thu 5-9 PM. I can't focus after 11 PM."
              rows={3}
              maxLength={1000}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <div className="suggestion-buttons">
            <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
            {firstTime && (
              <button type="button" className="secondary" onClick={onClose}>Later</button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

export default ProfilePanel;
