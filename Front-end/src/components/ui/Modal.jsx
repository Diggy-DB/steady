import { useEffect, useId, useRef } from "react";
import { Card } from ".";
import { X } from "./icons";

// A small dialog (add an event, an event's details): a card over a scrim. Escape or the scrim closes it,
// and focus moves into it and back to where it was.
function Modal({ title, color = "yellow", onClose, children }) {
  const titleId = useId();
  const ref = useRef(null);

  useEffect(() => {
    const before = document.activeElement;
    ref.current?.querySelector("input, textarea, select, button:not(.close)")?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="modal-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal">
        <Card
          title={<span id={titleId}>{title}</span>}
          color={color}
          actions={
            <button type="button" className="btn icon-btn surface close" onClick={onClose} aria-label="Close">
              <X />
            </button>
          }
        >
          {children}
        </Card>
      </div>
    </div>
  );
}

export default Modal;
