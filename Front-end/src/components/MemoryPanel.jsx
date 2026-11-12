import { useEffect, useState } from "react";
import { ai } from "../lib/ai";
import Modal from "./ui/Modal";
import { Skeleton } from "./ui";
import { X } from "./ui/icons";

// What Steady remembers about the user (long-term memory), with a way to forget each fact.
// The user stays in control of what the AI knows about them. (Restyled; same calls as before.)
function MemoryPanel({ onClose }) {
  const [memories, setMemories] = useState(null); // null = still loading
  const [error, setError] = useState("");

  useEffect(() => {
    ai.memories().then(setMemories).catch((err) => setError(err.message));
  }, []);

  async function handleForget(id) {
    try {
      await ai.forgetMemory(id);
      setMemories(memories.filter((m) => m.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Modal title="What Steady remembers" color="purple" onClose={onClose}>
      <p>Facts learned from your chats and journal entries. Forget anything you don't want it to use.</p>
      {error && <p className="alert" role="alert">{error}</p>}
      {memories === null && !error && <Skeleton height={60} />}
      {memories?.length === 0 && <p className="empty">Nothing yet. It learns as you chat and write in your journal.</p>}
      {memories?.length > 0 && (
        <ul className="constraint-list">
          {memories.map((m) => (
            <li key={m.id} className="task-row">
              <span className="task-main" style={{ paddingLeft: 10 }}>
                <span className="task-name">{m.memory}</span>
                <span className="task-desc">From your {m.source === "journal" ? "journal" : "chats"}</span>
              </span>
              <button type="button" className="ghost-btn" onClick={() => handleForget(m.id)} aria-label={`Forget: ${m.memory}`}><X /></button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

export default MemoryPanel;
