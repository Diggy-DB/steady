import { useState } from "react";
import { Field } from "../ui";
import { ArrowUp, Check, Lock, Moon, Plus, Sun, X } from "../ui/icons";
import { WEEKDAYS, describeCommitment } from "../../lib/onboarding";

// Profile pieces shared by Sign-up and Settings.

// Hobbies & priorities: tap in order of importance (the first tap is #1); tap again to remove.
export function PriorityPicker({ options, value, onChange }) {
  const [custom, setCustom] = useState("");
  const all = [...options, ...value.filter((v) => !options.includes(v))];

  function toggle(option) {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);
  }

  function moveUp(index) {
    const next = [...value];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    onChange(next);
  }

  function addCustom(e) {
    e.preventDefault();
    const text = custom.trim();
    if (text && !value.includes(text)) onChange([...value, text]);
    setCustom("");
  }

  return (
    <div className="priority-picker">
      <div className="bubbles" role="group" aria-label="Hobbies and priorities">
        {all.map((option) => {
          const rank = value.indexOf(option);
          return (
            <button key={option} type="button" className="bubble-btn" aria-pressed={rank >= 0} onClick={() => toggle(option)}>
              {option}
              {rank >= 0 && <span className="rank" aria-label={`priority ${rank + 1}`}>{rank + 1}</span>}
            </button>
          );
        })}
      </div>
      <form className="add-own" onSubmit={addCustom}>
        <Field label="Add your own" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="e.g. Guitar practice" />
        <button type="submit" className="btn surface" disabled={!custom.trim()}>
          <Plus width={18} height={18} /> Add
        </button>
      </form>
      <div className="field">
        <span className="field-label" id="order-label">Your priority order</span>
        {value.length === 0 ? (
          <p className="hint">Nothing picked yet. Tap the bubbles above, most important first.</p>
        ) : (
          <ol className="order-list" aria-labelledby="order-label">
            {value.map((item, i) => (
              <li key={item}>
                <span className="num" aria-hidden="true">{i + 1}</span>
                <span className="grow">{item}</span>
                {i > 0 && (
                  <button type="button" className="ghost-btn" onClick={() => moveUp(i)} aria-label={`Move ${item} up`}>
                    <ArrowUp />
                  </button>
                )}
                <button type="button" className="ghost-btn" onClick={() => toggle(item)} aria-label={`Remove ${item}`}>
                  <X />
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export function WorkTimeChoice({ value, onChange }) {
  const options = [
    { value: "Morning", title: "Morning person", sub: "I do my best work early", icon: <Sun />, fill: "fill-yellow" },
    { value: "Night", title: "Night person", sub: "I focus best in the evening", icon: <Moon />, fill: "fill-purple" },
  ];
  return (
    <div className="choices" role="group" aria-label="When do you work best?">
      {options.map((o) => (
        <button key={o.value} type="button" className="choice" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
          <span className={`tile ${o.fill}`}>{o.icon}</span>
          <span>
            <strong>{o.title}</strong>
            <span className="sub">{o.sub}</span>
          </span>
          {value === o.value && (
            <span className="tick" aria-hidden="true">
              <Check />
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
export const DETECTED_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function TimezoneSelect({ value, onChange, hint }) {
  const zones = ZONES.includes(value) ? ZONES : [value, ...ZONES];
  return (
    <Field label="Timezone" as="select" value={value} onChange={(e) => onChange(e.target.value)} hint={hint}>
      {zones.map((z) => (
        <option key={z} value={z}>
          {z.replaceAll("_", " ")}
          {z === DETECTED_ZONE ? " (detected)" : ""}
        </option>
      ))}
    </Field>
  );
}

export function CommitmentRow({ commitment, onRemove }) {
  return (
    <li className="constraint-row striped">
      <span className="info">
        <span className="on-chip">
          <Lock label="Fixed" width={15} height={15} /> {commitment.name}
        </span>
        <span className="on-chip when">{describeCommitment(commitment)}</span>
      </span>
      <button type="button" className="ghost-btn" onClick={onRemove} aria-label={`Remove ${commitment.name}`}>
        <X />
      </button>
    </li>
  );
}

// "Add a commitment": name, the days it repeats on, and its times.
export function CommitmentForm({ onAdd, busy }) {
  const [name, setName] = useState("");
  const [days, setDays] = useState([]);
  const [start, setStart] = useState("10:00");
  const [end, setEnd] = useState("11:00");
  const [problem, setProblem] = useState("");

  function toggleDay(d) {
    setDays((all) => (all.includes(d) ? all.filter((x) => x !== d) : [...all, d].sort()));
  }

  async function handleAdd() {
    if (!name.trim()) return setProblem("Give it a name, like \"CSE 232 lecture\".");
    if (days.length === 0) return setProblem("Pick at least one day it repeats on.");
    if (end <= start) return setProblem("It has to end after it starts.");
    setProblem("");
    const ok = await onAdd({ name: name.trim(), days, start, end });
    if (ok !== false) {
      setName("");
      setDays([]);
    }
  }

  return (
    <div className="dashed-box">
      <span className="field-label">Add a commitment</span>
      <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. CSE 232 lecture" />
      <div className="field">
        <span className="field-label" id="repeats-label">Repeats on</span>
        <div className="day-toggles" role="group" aria-labelledby="repeats-label">
          {WEEKDAYS.map((d, i) => (
            <button key={d} type="button" aria-pressed={days.includes(i)} onClick={() => toggleDay(i)} aria-label={d}>
              {d.slice(0, 2)}
            </button>
          ))}
        </div>
      </div>
      <div className="row2">
        <Field label="Starts" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
        <Field label="Ends" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      {problem && <p className="hint" role="alert" style={{ color: "var(--ink)" }}>{problem}</p>}
      <button type="button" className="btn" onClick={handleAdd} disabled={busy}>
        <Plus width={18} height={18} /> Add commitment
      </button>
    </div>
  );
}
