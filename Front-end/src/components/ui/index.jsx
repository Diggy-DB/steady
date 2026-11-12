import { useId } from "react";
import { useTheme } from "../../lib/theme";
import { Moon, Sun } from "./icons";

// Shared building blocks of the "Neo-Brutal Pop" design (styles in src/styles/ui.css).

export function Box({ as: Tag = "section", className = "", hoverable, children, ...props }) {
  return (
    <Tag className={`box ${hoverable ? "hoverable" : ""} ${className}`} {...props}>
      {children}
    </Tag>
  );
}

// A card with a colored header bar: <Card title="Tasks" color="green" icon={...} actions={<button/>}>
export function Card({ title, color, icon, actions, className = "", bodyClass = "", headingLevel = 2, children, ...props }) {
  const H = `h${headingLevel}`;
  return (
    <Box className={`with-header ${className}`} {...props}>
      <div className={`card-header fill-${color}`}>
        <H>
          {icon}
          {title}
        </H>
        {actions}
      </div>
      <div className={`card-body ${bodyClass}`}>{children}</div>
    </Box>
  );
}

export function Logo({ short = false, href = "#/" }) {
  return (
    <a className="logo" href={href} aria-label="Steady Planner, home">
      <LogoMark />
      <span className={`logo-word ${short ? "" : "long"}`}>{short ? "Steady" : "Steady Planner"}</span>
    </a>
  );
}

// The mark: a yellow rounded square with a sunrise (arc over a horizon) and a dot.
export function LogoMark() {
  return (
    <svg className="logo-mark" viewBox="0 0 38 38" aria-hidden="true" focusable="false">
      <rect x="1.5" y="1.5" width="35" height="35" rx="9" fill="var(--yellow)" stroke="var(--line)" strokeWidth="3" />
      <path d="M9 25a10 10 0 0 1 20 0" fill="none" stroke="var(--line)" strokeWidth="3.2" strokeLinecap="round" />
      <path d="M7 29h24" stroke="var(--line)" strokeWidth="3.2" strokeLinecap="round" />
      <circle cx="19" cy="11" r="2.8" fill="var(--line)" />
    </svg>
  );
}

export function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      className="btn icon-btn theme-toggle"
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? <Sun key="sun" /> : <Moon key="moon" />}
    </button>
  );
}

// Decorative scrolling strip (aria-hidden): its content must also be readable elsewhere on the page.
export function Marquee({ items, size = "", className = "" }) {
  const text = items.filter(Boolean).join("  ✦  ");
  if (!text) return null;
  return (
    <div className={`marquee ${size} ${className}`} aria-hidden="true">
      <div className="marquee-track">
        <span>{text}  ✦</span>
        <span>{text}  ✦</span>
      </div>
    </div>
  );
}

// A round sticker with spinning circular text and bold content in the middle (decorative).
export function Sticker({ ring, color = "yellow", className = "", children }) {
  const id = useId().replace(/:/g, "");
  return (
    <div className={`sticker fill-${color} ${className}`} aria-hidden="true">
      <svg className="ring" viewBox="0 0 128 128">
        <defs>
          <path id={`ring-${id}`} d="M64,64 m-48,0 a48,48 0 1,1 96,0 a48,48 0 1,1 -96,0" />
        </defs>
        <text>
          <textPath href={`#ring-${id}`}>{ring}</textPath>
        </text>
      </svg>
      <div className="center">{children}</div>
    </div>
  );
}

export function ProgressBar({ value, max, label }) {
  const percent = max ? Math.round((100 * value) / max) : 0;
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max || 0}
      aria-valuenow={value}
      aria-label={label}
    >
      <span style={{ width: `${percent}%` }} />
    </div>
  );
}

export function Alert({ children, action }) {
  return (
    <div className="alert" role="alert">
      <span>{children}</span>
      {action}
    </div>
  );
}

// A labelled input, select or textarea. `as` picks the element; everything else goes on it.
export function Field({ label, hint, as: Tag = "input", id, children, className = "", ...props }) {
  const auto = useId();
  const fieldId = id ?? `f${auto.replace(/:/g, "")}`;
  return (
    <div className={`field ${className}`}>
      <label htmlFor={fieldId}>{label}</label>
      <Tag id={fieldId} className="inp" aria-describedby={hint ? `${fieldId}-hint` : undefined} {...props}>
        {children}
      </Tag>
      {hint && (
        <p className="hint" id={`${fieldId}-hint`}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function Skeleton({ height = 120, className = "" }) {
  return <div className={`skeleton ${className}`} style={{ height }} aria-hidden="true" />;
}

export function Avatar({ name }) {
  return (
    <span className="avatar" aria-hidden="true">
      {(name || "?").trim().charAt(0)}
    </span>
  );
}
