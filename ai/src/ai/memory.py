"""Long-term memory: lasting facts about each user, learned from their chats and journal entries.

Built on Mem0 (open source). After a chat reply, or when a journal entry is saved, Mem0
asks the model to pull out lasting facts ("prefers studying at night", "works Tuesdays
1-5") and stores them; it also updates or removes facts that new information contradicts.
Before the agent answers, the facts most related to the question are found by meaning
(semantic search) and added to its system prompt.

Everything stays on this machine: the vectors live in a local Qdrant database under
ai/memory/ (git-ignored, because it holds personal data), and the model and the
embedding model run in Ollama. Mem0's usage telemetry is switched off before import.

Every memory is filed under the user id from the checked login token, never one the
model provides, so one user's memories never reach another user's prompt.
"""

import os

os.environ["MEM0_TELEMETRY"] = "false"  # must be set before mem0 is imported: send no usage data anywhere

import threading
from pathlib import Path

from mem0 import Memory

from ai.llm import AI_DIR, Settings

MEMORY_DIR = AI_DIR / "memory"
EMBED_MODEL = "nomic-embed-text"  # a small embedding model in Ollama: turns text into vectors for searching by meaning
EMBED_DIMS = 768
EMBED_URL = os.getenv("EMBED_BASE_URL", "http://localhost:11434")


def mem0_config(settings: Settings, folder: Path = MEMORY_DIR) -> dict:
    """Mem0 settings: the same model as the chat, a local embedder, and a local vector database."""
    if ":11434" in settings.base_url:  # Ollama: Mem0 talks to its own API, not the OpenAI-style /v1
        llm = {"provider": "ollama", "config": {"ollama_base_url": settings.base_url.removesuffix("/v1")}}
    else:  # e.g. vLLM on RunPod
        llm = {"provider": "vllm", "config": {"vllm_base_url": settings.base_url, "api_key": settings.api_key}}
    # A thinking model spends tokens thinking before it writes the facts, so allow plenty.
    llm["config"].update({"model": settings.model, "temperature": 0.1, "max_tokens": 6000})
    return {
        "llm": llm,
        "embedder": {
            "provider": "ollama",
            "config": {"model": EMBED_MODEL, "ollama_base_url": EMBED_URL, "embedding_dims": EMBED_DIMS},
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": str(folder / "qdrant"),
                "collection_name": "steady_memories",
                "embedding_model_dims": EMBED_DIMS,
                "on_disk": True,
            },
        },
        "history_db_path": str(folder / "history.db"),
    }


class UserMemory:
    """The memory operations the server uses, each scoped to one user.

    `memory` is a Mem0 Memory; tests pass a fake with the same methods. A lock keeps one
    operation at a time: the local database allows one writer, and the model server
    answers one request at a time anyway.
    """

    def __init__(self, memory):
        self.memory = memory
        self.lock = threading.Lock()

    def recall(self, user_id: str, query: str, limit: int = 5) -> list[str]:
        """The facts most related to `query`, by meaning."""
        with self.lock:
            found = self.memory.search(query, top_k=limit, filters={"user_id": user_id})
        return [m["memory"] for m in found["results"]]

    def remember_chat(self, user_id: str, message: str, reply: str) -> None:
        """Learn from one chat turn (the user's message and the final answer, no tool traffic)."""
        turn = [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
        with self.lock:
            self.memory.add(turn, user_id=user_id, metadata={"source": "chat"})

    def remember_journal(self, user_id: str, journal: dict) -> None:
        """Learn from a journal entry. An edited entry replaces what its old version taught."""
        self.forget_journal(user_id, journal["journal_id"])
        entry = [{"role": "user", "content": f"My journal entry for {journal['date']}: {journal['information']}"}]
        with self.lock:
            self.memory.add(
                entry, user_id=user_id, metadata={"source": "journal", "journal_id": str(journal["journal_id"])}
            )

    def forget_journal(self, user_id: str, journal_id) -> int:
        """Delete the memories learned from one journal entry. Returns how many."""
        with self.lock:
            found = self.memory.get_all(filters={"user_id": user_id, "journal_id": str(journal_id)}, top_k=200)
            for m in found["results"]:
                self.memory.delete(m["id"])
        return len(found["results"])

    def list(self, user_id: str) -> list[dict]:
        with self.lock:
            found = self.memory.get_all(filters={"user_id": user_id}, top_k=500)
        return [
            {
                "id": m["id"],
                "memory": m["memory"],
                "source": (m.get("metadata") or {}).get("source"),
                "created_at": m.get("created_at"),
            }
            for m in found["results"]
        ]

    def delete(self, user_id: str, memory_id: str) -> bool:
        """Delete one memory, only if it belongs to this user."""
        with self.lock:
            found = self.memory.get(memory_id)
            if not found or found.get("user_id") != user_id:
                return False
            self.memory.delete(memory_id)
        return True


def build_user_memory(settings: Settings, folder: Path = MEMORY_DIR) -> UserMemory:
    folder.mkdir(parents=True, exist_ok=True)
    return UserMemory(Memory.from_config(mem0_config(settings, folder)))
