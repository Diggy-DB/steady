"""Tests for the agent loop. A fake client plays the model, so these are fast and always give the same result."""

import copy
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from openai.types.chat import ChatCompletion

from ai.agent import MAX_ROUNDS, run_agent, run_tool, tool_calls_in_thinking
from ai.schedule import FixtureStore, ToolContext

NOW = datetime(2026, 10, 5, 18, 30, tzinfo=ZoneInfo("America/Detroit"))
TUESDAY = {"start_date": "2026-10-06", "end_date": "2026-10-06"}


def context() -> ToolContext:
    return ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)


def reply(content: str = "", tool_calls: list[tuple[str, dict | str]] = (), reasoning: str = "",
          finish_reason: str | None = None) -> ChatCompletion:
    """Build a response exactly like the OpenAI library would return it."""
    message = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning  # how vLLM sends the thinking
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
            "choices": [{"index": 0, "message": message,
                         "finish_reason": finish_reason or ("tool_calls" if tool_calls else "stop")}],
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
    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: records.append(record))
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


def test_reminds_once_when_times_are_recommended_without_proposals(logged):
    slots = {"start_date": "2026-10-07", "end_date": "2026-10-07", "minutes": 60}
    gym = {"name": "Gym", "start": "2026-10-07 12:00", "end": "2026-10-07 13:00", "reason": "Free after class."}
    client = FakeClient(
        [
            reply(tool_calls=[("find_free_slots", slots)]),
            reply("You could go at 12:00 PM."),  # describes a time but proposes nothing
            reply(tool_calls=[("propose_new_event", gym)]),
            reply("I suggest the gym at 12 PM."),
        ]
    )
    result = run_agent(client, "fake", context(), "When can I go to the gym?", verbose=False)
    assert result["nudged"] and result["answer"] == "I suggest the gym at 12 PM."
    reminder = client.requests[2]["messages"][-1]
    assert reminder["role"] == "system" and "nothing to accept" in reminder["content"]


def test_no_reminder_for_plain_questions(logged):
    client = FakeClient([reply(tool_calls=[("get_schedule", TUESDAY)]), reply("Work 1-5 PM, gym 6-7 PM.")])
    result = run_agent(client, "fake", context(), "What do I have tomorrow?", verbose=False)
    assert not result["nudged"] and result["rounds"] == 2


def call_text(name: str, arguments: dict) -> str:
    return "<tool_call>\n" + json.dumps({"name": name, "arguments": arguments}) + "\n</tool_call>"


def test_tool_calls_written_inside_unclosed_thinking_are_used(logged):
    # The model never wrote </think>, so the server sent everything as thinking: no calls, no answer.
    thinking = "I should look up Tuesday.\n\n" + call_text("get_schedule", TUESDAY) + "\n\nYou work 1-5 PM."
    client = FakeClient([reply(reasoning=thinking), reply("You work 1-5 PM.")])
    result = run_agent(client, "fake", context(), "What do I have tomorrow?", verbose=False)

    assert (result["answer"], result["rounds"]) == ("You work 1-5 PM.", 2)
    *_, call_message, tool_message = client.requests[1]["messages"]
    assert call_message["tool_calls"][0]["function"]["name"] == "get_schedule"
    assert call_message["reasoning_content"] == "I should look up Tuesday."  # the call is cut out of the thinking
    assert "Work shift" in tool_message["content"]
    assert logged[0]["tool_calls_from_thinking"] and "<tool_call>" in logged[0]["reasoning"]  # the log keeps the raw text


def test_drafts_in_thinking_are_ignored_when_the_model_answered(logged):
    thinking = "Maybe " + call_text("get_schedule", TUESDAY) + " but I already know."
    client = FakeClient([reply("Work 1-5 PM.", reasoning=thinking)])
    result = run_agent(client, "fake", context(), "What do I have tomorrow?", verbose=False)
    assert (result["answer"], result["rounds"]) == ("Work 1-5 PM.", 1)
    assert not logged[0]["tool_calls_from_thinking"]


def test_only_the_last_group_of_calls_counts():
    draft = call_text("get_schedule", TUESDAY)
    gym = {"name": "Gym", "start": "2026-10-07 12:00", "end": "2026-10-07 13:00", "reason": "Free."}
    thinking = f"First idea: {draft}\nNo, better:\n{call_text('propose_new_event', gym)}\n{call_text('propose_new_event', gym)}\nDone."
    before, calls = tool_calls_in_thinking(thinking)
    assert [c["function"]["name"] for c in calls] == ["propose_new_event", "propose_new_event"]
    assert json.loads(calls[0]["function"]["arguments"]) == gym
    assert before.endswith("No, better:") and len({c["id"] for c in calls}) == 2


def test_no_calls_from_thinking_without_valid_blocks():
    assert tool_calls_in_thinking("Just thinking.") == ("Just thinking.", [])
    broken = "<tool_call>\n{not json}\n</tool_call>"
    assert tool_calls_in_thinking(broken) == (broken, [])


def test_a_repeated_failing_call_is_refused(logged):
    too_long = {"start_date": "2027-01-11", "end_date": "2027-05-07"}
    client = FakeClient([reply(tool_calls=[("get_schedule", too_long)]), reply(tool_calls=[("get_schedule", too_long)]),
                         reply("I couldn't look that far ahead.")])
    result = run_agent(client, "fake", context(), "What's on my calendar this semester?", verbose=False)
    first, second = [m["content"] for m in result["messages"] if m["role"] == "tool"]
    assert "e.g. start_date 2027-01-11 and end_date 2027-01-24" in first  # the error says what to ask instead
    assert second.startswith("Error: you already made exactly this call")


# ---- Replies the user can read: no thinking, short, no "I've added" ----

THINKING_DUMP = "Thinking Process:\n1. The user wants a routine for tonight. " + "Let me consider the schedule again. " * 200


def test_thinking_that_runs_out_of_tokens_is_redone_without_thinking(logged):
    client = FakeClient([reply(THINKING_DUMP, finish_reason="length"), reply("Try 25 minutes of work, then a 5-minute break.")])
    result = run_agent(client, "fake", context(), "I keep procrastinating. Give me a simple routine for tonight.", verbose=False)
    assert result["answer"] == "Try 25 minutes of work, then a 5-minute break."
    assert client.requests[1]["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert [r["attempt"] for r in logged] == ["thinking", "no thinking"]


def test_an_answer_that_reads_like_thinking_is_rewritten_short(logged):
    client = FakeClient([reply(THINKING_DUMP), reply("Start with your easiest task for 25 minutes, then take a break.")])
    result = run_agent(client, "fake", context(), "I keep procrastinating.", verbose=False)
    assert result["answer"] == "Start with your easiest task for 25 minutes, then take a break."
    assert "Draft reply" in client.requests[1]["messages"][1]["content"]


def test_if_the_rewrite_fails_the_answer_is_cut_at_a_sentence(logged):
    long = "You have a lecture at 10 AM. " * 60
    client = FakeClient([reply(long), reply("")])
    answer = run_agent(client, "fake", context(), "What's on today?", verbose=False)["answer"]
    assert len(answer) <= 600 and answer.endswith(".")


def test_short_answers_are_left_alone(logged):
    client = FakeClient([reply("You work 1-5 PM tomorrow.")])
    assert run_agent(client, "fake", context(), "Tomorrow?", verbose=False)["answer"] == "You work 1-5 PM tomorrow."
    assert len(client.requests) == 1


def test_claims_become_suggestions_when_it_only_suggested(logged):
    gym = {"name": "Gym", "start": "2026-10-07 12:30", "end": "2026-10-07 13:30", "reason": "Free."}
    client = FakeClient([reply(tool_calls=[("propose_new_event", gym)]), reply("I've added a gym session on Wednesday at 12:30.")])
    answer = run_agent(client, "fake", context(), "Find time for the gym.", verbose=False)["answer"]
    assert answer == "I suggest adding a gym session on Wednesday at 12:30."


def test_the_prompt_spells_out_this_week_and_next_week():
    from ai.agent import calendar_text

    wednesday = datetime(2026, 11, 11, 15, 0, tzinfo=ZoneInfo("America/Detroit"))
    text = calendar_text(wednesday)
    assert "This week: Monday 2026-11-09 to Sunday 2026-11-15. Next week: Monday 2026-11-16 to Sunday 2026-11-22." in text
    assert "Thu 2026-11-12" in text and "Wed 2026-11-25" in text
    sunday = calendar_text(datetime(2026, 11, 15, 9, 0, tzinfo=ZoneInfo("America/Detroit")))
    assert "Next week: Monday 2026-11-16" in sunday  # on a Sunday, next week starts tomorrow


def test_running_out_of_rounds_still_lists_the_suggestions_made(logged, monkeypatch):
    import ai.agent

    monkeypatch.setattr(ai.agent, "MAX_ROUNDS", 2)
    gym = {"name": "Gym", "start": "2026-10-07 12:30", "end": "2026-10-07 13:30", "reason": "Free."}
    client = FakeClient([reply(tool_calls=[("propose_new_event", gym)]), reply(tool_calls=[("get_schedule", TUESDAY)])])
    result = run_agent(client, "fake", context(), "Plan my gym sessions.", verbose=False)
    assert result["gave_up"] is True
    assert result["answer"] == ("Here's what I suggest:\n- new event 'Gym' on Wednesday, October 7, 12:30 PM – 1:30 PM\n"
                                "Nothing changes until you accept.")


@pytest.mark.parametrize("asked,extra", [
    ("Plan my week.", []),
    ("Can you add a task for reading my novel?", ["propose_new_task"]),
    ("Cancel movie night.", ["propose_delete"]),
    ("Add to my journal: good day.", ["get_journal", "propose_journal_entry"]),
    ("Should I delete your gym session?\nyes", ["propose_delete"]),  # Steady asked; "yes" answers it
])
def test_only_the_tools_a_request_needs_are_offered(asked, extra):
    from ai.agent import CORE_TOOLS, offered_tools

    assert [t["function"]["name"] for t in offered_tools(asked)] == [*CORE_TOOLS, *extra]


def test_the_model_sees_only_those_tools(logged):
    client = FakeClient([reply("Sure.")])
    run_agent(client, "fake", context(), "Plan my week.", verbose=False)
    assert len(client.requests[0]["tools"]) == 4
