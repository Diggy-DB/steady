import { useState } from "react";

function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    { id: 1, sender: "AI", text: "Hi! Ask me anything about your schedule." },
  ]);

  function handleSend() {
    if (input.trim() === "") return;
    const userMsg = { id: Date.now(), sender: "USER", text: input };
    const aiMsg = {
      id: Date.now() + 1,
      sender: "AI",
      text: "I found your Study Session from 6–7 PM. Would you like me to move it to 8–9 PM?",
    };
    setMessages([...messages, userMsg, aiMsg]);
    setInput("");
  }

  return (
    <div>
      {isOpen && (
        <div className="chat-window">
          <div className="chat-header">
            <strong>Steady AI</strong>
            <button onClick={() => setIsOpen(false)}>✕</button>
          </div>
          <div className="chat-messages">
            {messages.map((m) => (
              <div key={m.id} className={m.sender === "USER" ? "bubble user" : "bubble ai"}>
                {m.text}
              </div>
            ))}
          </div>
          <div className="chat-input">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
            />
            <button onClick={handleSend}>Send</button>
          </div>
        </div>
      )}
      <button className="chat-fab" onClick={() => setIsOpen(!isOpen)}>💬</button>
    </div>
  );
}

export default ChatWidget;