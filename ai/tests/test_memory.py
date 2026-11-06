"""Tests for long-term memory, with a fake Mem0 (no model, no database)."""

import pytest
from fastapi.testclient import TestClient

import ai.server
from ai.agent import run_agent
from ai.memory import UserMemory
from ai.schedule import FixtureStore
from test_agent import NOW, FakeClient, context, reply


class FakeMem0:
    """Acts like Mem0's Memory without a model: "learning" stores each user message as a fact,
    and search matches shared words instead of meaning."""

    def __init__(self):
        self.items: dict[str, dict] = {}

    def add(self, messages, user_id, metadata=None, **kwargs):
        for m in messages:
            if m["role"] == "user":
                memory_id = str(len(self.items) + 1)
                self.items[memory_id] = {"id": memory_id, "memory": m["content"], "user_id": user_id,
                                         "metadata": metadata or {}}

    @staticmethod
    def matches(item, filters):
        return all((item["user_id"] if key == "user_id" else item["metadata"].get(key)) == value
                   for key, value in filters.items())

    def search(self, query, top_k=20, filters=None, **kwargs):
        words = set(query.lower().replace("?", "").split())
        found = [i for i in self.items.values()
                 if self.matches(i, filters) and words & set(i["memory"].lower().replace(".", "").split())]
        return {"results": found[:top_k]}

    def get_all(self, filters=None, top_k=20, **kwargs):
        return {"results": [i for i in self.items.values() if self.matches(i, filters)][:top_k]}

    def get(self, memory_id):
        return self.items.get(memory_id)

    def delete(self, memory_id):
        self.items.pop(memory_id, None)


def journal(journal_id, text):
    return {"journal_id": journal_id, "user_id": "user-1", "date": "2026-10-05", "information": text}


# ---- UserMemory ----


def test_recall_only_finds_this_users_memories():
    memory = UserMemory(FakeMem0())
    memory.remember_chat("user-1", "I study best at night.", "Noted.")
    memory.remember_chat("user-2", "I study best in the morning.", "Noted.")
    assert memory.recall("user-1", "When should I study?") == ["I study best at night."]


def test_an_edited_journal_entry_replaces_what_it_taught():
    memory = UserMemory(FakeMem0())
    memory.remember_journal("user-1", journal(7, "Gym makes me tired."))
    memory.remember_journal("user-1", journal(7, "Gym gives me energy."))
    assert [m["memory"] for m in memory.list("user-1")] == ["My journal entry for 2026-10-05: Gym gives me energy."]


def test_forgetting_a_journal_entry_keeps_chat_memories():
    memory = UserMemory(FakeMem0())
    memory.remember_chat("user-1", "I prefer evenings.", "Noted.")
    memory.remember_journal("user-1", journal(7, "Tired today."))
    assert memory.forget_journal("user-1", 7) == 1
    assert [(m["memory"], m["source"]) for m in memory.list("user-1")] == [("I prefer evenings.", "chat")]


def test_nobody_can_delete_another_users_memory():
    memory = UserMemory(FakeMem0())
    memory.remember_chat("user-2", "Private fact.", "Noted.")
    [theirs] = memory.list("user-2")
    assert memory.delete("user-1", theirs["id"]) is False
    assert memory.list("user-2") and memory.delete("user-2", theirs["id"]) is True


# ---- The agent ----


@pytest.fixture
def no_logs(monkeypatch):
    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: None)


def test_memories_reach_the_model_as_facts_not_instructions(no_logs):
    client = FakeClient([reply("Evening it is.")])
    run_agent(client, "fake", context(), "When should I study?", verbose=False, memories=["Prefers studying at night"])
    system = client.requests[0]["messages"][0]["content"]
    assert "- Prefers studying at night" in system and "not instructions" in system


def test_no_memory_section_without_memories(no_logs):
    client = FakeClient([reply("Hi.")])
    run_agent(client, "fake", context(), "Hi", verbose=False)
    assert "What you remember" not in client.requests[0]["messages"][0]["content"]


# ---- The API ----


@pytest.fixture
def api(monkeypatch, no_logs):
    store = FixtureStore()
    store.data["journals"] = [journal(7, "Long day at work, exhausted.")]
    monkeypatch.setattr(ai.server, "demo_store", store)
    monkeypatch.setattr(ai.server, "STORE", "fixture")
    monkeypatch.setattr(ai.server, "memory", UserMemory(FakeMem0()))
    return TestClient(ai.server.app)


def test_chat_uses_memories_and_learns_after_replying(api, monkeypatch):
    ai.server.memory.remember_chat("user-1", "I study best at night.", "Noted.")
    model = FakeClient([reply("Tonight after 8 PM.")])
    monkeypatch.setattr(ai.server, "llm", model)

    body = api.post("/chat", json={"message": "When should I study?"}).json()
    assert body["memories_used"] == ["I study best at night."]
    assert "I study best at night." in model.requests[0]["messages"][0]["content"]
    # The background task ran after the response: the new message is now remembered too.
    assert "When should I study?" in [m["memory"] for m in api.get("/memories").json()]


def test_memories_can_be_listed_and_deleted(api):
    ai.server.memory.remember_chat("user-1", "I like mornings.", "Noted.")
    [mine] = api.get("/memories").json()
    assert api.delete(f"/memories/{mine['id']}").json() == {"deleted": mine["id"]}
    assert api.get("/memories").json() == []


def test_cannot_delete_another_users_memory_through_the_api(api):
    ai.server.memory.remember_chat("user-2", "Someone else's fact.", "Noted.")
    [theirs] = ai.server.memory.list("user-2")
    assert api.delete(f"/memories/{theirs['id']}").status_code == 404  # we are user-1


def test_learning_from_and_forgetting_a_journal_entry(api):
    assert api.post("/memories/journal/7").json() == {"journal_id": "7", "status": "learning"}
    assert [m["source"] for m in api.get("/memories").json()] == ["journal"]
    assert api.delete("/memories/journal/7").json() == {"journal_id": "7", "forgotten": 1}
    assert api.post("/memories/journal/99").status_code == 404  # not this user's (or no such) entry


def test_memory_off(api, monkeypatch):
    monkeypatch.setattr(ai.server, "memory", None)
    assert api.get("/memories").status_code == 503
