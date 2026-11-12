// Stroke icons (2.6px, currentColor). Decorative by default (aria-hidden); pass a label to make one an image,
// like the lock on fixed events: <Lock label="Fixed" />.

function Icon({ label, children, size, strokeWidth = 2.6, ...props }) {
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round"
      strokeLinejoin="round" width={size} height={size} focusable="false" {...a11y} {...props}>
      {children}
    </svg>
  );
}

export const Sun = (p) => (
  <Icon {...p}><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" /></Icon>
);
export const Moon = (p) => <Icon {...p}><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></Icon>;
export const Gear = (p) => (
  <Icon {...p}><circle cx="12" cy="12" r="3.2" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></Icon>
);
export const Lock = (p) => <Icon {...p}><rect x="4.5" y="10.5" width="15" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></Icon>;
export const Check = (p) => <Icon strokeWidth={3} {...p}><path d="M4.5 12.5l5 5L19.5 7" /></Icon>;
export const X = (p) => <Icon strokeWidth={3} {...p}><path d="M6 6l12 12M18 6L6 18" /></Icon>;
export const Plus = (p) => <Icon strokeWidth={3} {...p}><path d="M12 5v14M5 12h14" /></Icon>;
export const ChevronLeft = (p) => <Icon strokeWidth={3} {...p}><path d="M15 5l-7 7 7 7" /></Icon>;
export const ChevronRight = (p) => <Icon strokeWidth={3} {...p}><path d="M9 5l7 7-7 7" /></Icon>;
export const ArrowUp = (p) => <Icon strokeWidth={3} {...p}><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5" /></Icon>;
export const ArrowRight = (p) => <Icon strokeWidth={3} {...p}><path d="M5 12h14M13 5.5l6.5 6.5-6.5 6.5" /></Icon>;
export const ArrowLeft = (p) => <Icon strokeWidth={3} {...p}><path d="M19 12H5M11 5.5L4.5 12l6.5 6.5" /></Icon>;
export const Sparkle = (p) => (
  <Icon {...p}><path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z" /><path d="M19 3v4M17 5h4" /></Icon>
);
export const Chat = (p) => (
  <Icon {...p}><path d="M4 5.5h13a2 2 0 0 1 2 2V15a2 2 0 0 1-2 2H9l-5 4V7.5a2 2 0 0 1 2-2z" /><path d="M21 3v3.5M19.25 4.75h3.5" /></Icon>
);
export const Eye = (p) => <Icon {...p}><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></Icon>;
export const EyeOff = (p) => (
  <Icon {...p}><path d="M3 3l18 18M10.6 5.1A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7a9.6 9.6 0 0 0 5.3-1.6" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></Icon>
);
export const Trash = (p) => <Icon {...p}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></Icon>;
export const Pencil = (p) => <Icon {...p}><path d="M4 20l4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20z" /><path d="M13.5 6.5l3 3" /></Icon>;
export const Paperclip = (p) => (
  <Icon {...p}><path d="M20 11.5l-8.2 8.2a5 5 0 0 1-7.1-7.1l8.6-8.6a3.4 3.4 0 0 1 4.8 4.8l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.7-7.7" /></Icon>
);
export const Send = (p) => <Icon {...p}><path d="M21 3L10.5 13.5M21 3l-6.5 18-4-7.5L3 9.5 21 3z" /></Icon>;
export const LogOut = (p) => <Icon {...p}><path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H4" /></Icon>;
export const Refresh = (p) => <Icon {...p}><path d="M20 11a8 8 0 0 0-14.6-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5L20 16M20 20v-4h-4" /></Icon>;
export const Calendar = (p) => <Icon {...p}><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></Icon>;
export const Brain = (p) => (
  <Icon {...p}><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3 2.5 2.5 0 0 0 3-2.4V6.4A2.5 2.5 0 0 0 9 4zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3 2.5 2.5 0 0 1-3-2.4" /></Icon>
);
export const Repeat = (p) => <Icon {...p}><path d="M17 2l3 3-3 3M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3M20 13v2a4 4 0 0 1-4 4H4" /></Icon>;
