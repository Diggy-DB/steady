"""Tests for the agent loop. A fake client plays the model, so these are fast and always give the same result."""

import copy
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from openai.types.chat import ChatCompletion

from ai.agent import MAX_ROUNDS, run_agent, run_tool
from ai.schedule import FixtureStore, ToolContext

NOW = datetime(2026, 10, 5, 18, 30, tzinfo=ZoneInfo("America/Detroit"))
TUESDAY = {"start_date": "2026-10-06", "end_date": "2026-10-06"}


def context() -> ToolContext:
    return ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)


def reply(content: str = "", tool_calls: list[tuple[str, dict | str]] = ()) -> ChatCompletion:
    """Build a response exactly like the OpenAI library would return it."""
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)},
            }
            for i, (name, args) in enumerate(tool_calls)
        ]
    return ChatCompletion.model_validate(
        {
            "id": "fake",
            "object": "chat.completion",
            "created": 0,
            "model": "fake",
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        }
    )


class FakeClient:
    """Stands in for the OpenAI client: hands out scripted replies and records every request."""

    base_url = "http://fake"

    def __init__(self, replies: list[ChatCompletion]):
        self.replies = list(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))  # a copy, because the loop keeps adding messages
        return self.replies.pop(0)


@pytest.fixture
def logged(monkeypatch) -> list[dict]:
    """Capture log records in a list instead of writing to logs/calls.jsonl."""
    records = []
    monkeypatch.setattr("ai.agent.log_call", records.append)
    return records


def test_answers_without_tools(logged):
    client = FakeClient([reply("Hello!")])
    result = run_agent(client, "fake", context(), "Hi", verbose=False)
    assert (result["answer"], result["rounds"]) == ("Hello!", 1)
    assert len(logged) == 1


def test_system_prompt_uses_the_given_time(logged):
    client = FakeClient([reply("Hello!")])
    run_agent(client, "fake", context(), "Hi", verbose=False)
    system = client.requests[0]["messages"][0]["content"]
    assert "Monday, October 5, 2026, 6:30 PM" in system


def test_tool_call_then_answer(logged):
    client = FakeClient([reply(tool_calls=[("get_schedule", TUESDAY)]), reply("You work 1-5 PM.")])
    result = run_agent(client, "fake", context(), "What do I have tomorrow?", verbose=False)

    assert (result["answer"], result["rounds"]) == ("You work 1-5 PM.", 2)
    *_, call_message, tool_message = client.requests[1]["messages"]
    assert call_message["tool_calls"][0]["function"]["name"] == "get_schedule"
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call_0"
    assert "Work shift" in tool_message["content"]
    assert [r["round"] for r in logged] == [1, 2] and len({r["run_id"] for r in logged}) == 1


def test_gives_up_after_max_rounds(logged):
    client = FakeClient([reply(tool_calls=[("get_schedule", TUESDAY)])] * MAX_ROUNDS)
    result = run_agent(client, "fake", context(), "Loop forever", verbose=False)
    assert result["rounds"] == MAX_ROUNDS and result["answer"].startswith("Sorry")
    assert len(client.requests) == MAX_ROUNDS


def test_model_cannot_pass_a_user_id():
    result = run_tool(context(), "get_schedule", json.dumps({**TUESDAY, "user_id": "user-2"}))
    assert result.startswith("Error") and "user_id" in result


def test_unknown_tool():
    assert run_tool(context(), "delete_everything", "{}").startswith("Error: there is no tool")


def test_arguments_that_are_not_json():
    assert run_tool(context(), "get_schedule", "start_date=2026-10-06").startswith("Error: the arguments were not valid JSON")


def test_bad_date_goes_back_to_the_model():
    result = run_tool(context(), "get_schedule", json.dumps({"start_date": "tomorrow", "end_date": "2026-10-06"}))
    assert result.startswith("Error: start_date must be a date")
