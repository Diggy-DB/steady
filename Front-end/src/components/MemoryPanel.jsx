import { useEffect, useState } from "react";
import { ai } from "../lib/ai";

// What Steady remembers about the user (long-term memory), with a way to forget each fact.
// The user stays in control of what the AI knows about them.
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
    <div className="popup-overlay" onClick={onClose}>
      <div className="popup" onClick={(e) => e.stopPropagation()}>
        <button className="popup-close" onClick={onClose}>✕</button>
        <h2>What Steady remembers</h2>
        <p>Facts learned from your chats and journal entries. Forget anything you don't want it to use.</p>

        {error && <p className="error">{error}</p>}
        {memories === null && !error && <p>Loading…</p>}
        {memories?.length === 0 && <p>Nothing yet. It learns as you chat and write in your journal.</p>}
        {memories?.map((m) => (
          <div key={m.id} className="item">
            <strong>{m.memory}</strong>
            <p>From your {m.source === "journal" ? "journal" : "chats"}</p>
            <button onClick={() => handleForget(m.id)}>Forget</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default MemoryPanel;
