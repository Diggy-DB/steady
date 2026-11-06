"""Checks that collected runs become valid training examples for Qwen's chat template."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ai.evals import Scenario, calls, run_scenario
from test_agent import FakeClient, reply

# scripts/ isn't a package, so load collect_traces.py by its path.
spec = importlib.util.spec_from_file_location("collect_traces", Path(__file__).parents[1] / "scripts" / "collect_traces.py")
collect_traces = importlib.util.module_from_spec(spec)
sys.modules["collect_traces"] = collect_traces
spec.loader.exec_module(collect_traces)


@pytest.fixture(autouse=True)
def no_logging(monkeypatch):
    monkeypatch.setattr("ai.agent.log_call", lambda record, path=None: None)


def example() -> dict:
    tuesday = {"start_date": "2026-10-06", "end_date": "2026-10-06"}
    client = FakeClient([reply(tool_calls=[("get_schedule", tuesday)]), reply("Work 1-5 PM, gym 6-7 PM.")])
    run = run_scenario(client, "fake", Scenario("tomorrow", "What do I have tomorrow?", [calls("get_schedule")]))
    return collect_traces.training_example(run, {"task": "tomorrow"})


def test_example_is_a_complete_conversation():
    ex = example()
    assert [m["role"] for m in ex["messages"]] == ["system", "user", "assistant", "tool", "assistant"]
    assert ex["messages"][-1]["content"] == "Work 1-5 PM, gym 6-7 PM."
    assert {t["function"]["name"] for t in ex["tools"]} >= {"get_schedule", "propose_new_event"}
    json.dumps(ex)  # must be plain JSON


def test_example_renders_with_qwens_chat_template():
    transformers = pytest.importorskip("transformers")
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained("Qwen/Qwen3-4B-Thinking-2507")
    except OSError:
        pytest.skip("tokenizer not downloaded and no network")
    ex = example()
    text = tokenizer.apply_chat_template(ex["messages"], tools=ex["tools"], tokenize=False)
    assert "<tool_call>" in text and "<tool_response>" in text and text.rstrip().endswith("<|im_end|>")



def reminded_run(later_thinking: str) -> dict:
    from ai.agent import NUDGE

    return {
        "messages": [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "When can I go to the gym?"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}], "reasoning_content": "look up"},
            {"role": "tool", "tool_call_id": "c1", "content": "{}"},
            {"role": "assistant", "content": "You could go at 12 PM."},  # described, didn't propose
            {"role": "system", "content": NUDGE},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c2"}], "reasoning_content": later_thinking},
            {"role": "tool", "tool_call_id": "c2", "content": "{}"},
        ],
        "answer": "I suggest the gym at 12 PM.",
        "reasoning": "Done.",
    }


def test_reminder_is_cut_out():
    cut = collect_traces.without_reminder(reminded_run("Propose the gym slot at noon."))
    roles = [m["role"] for m in cut["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool"]
    assert "You could go at 12 PM." not in [m["content"] for m in cut["messages"]]


def test_run_whose_thinking_mentions_the_reminder_is_skipped():
    assert collect_traces.without_reminder(reminded_run("The system reminded me to create suggestions.")) is None


def test_collection_runs_tasks_in_parallel_and_keeps_only_passing_runs(monkeypatch, tmp_path, capsys):
    class LazyModel:  # answers without ever using a tool, so every task fails its checks
        base_url = "http://fake"

        class chat:
            class completions:
                @staticmethod
                def create(**request):
                    return reply("I'm not sure.")

    monkeypatch.setattr(collect_traces, "make_client", lambda settings: LazyModel)
    monkeypatch.setattr(collect_traces, "AI_DIR", tmp_path)
    monkeypatch.setattr(collect_traces, "COLLECT_LOG", tmp_path / "collect.jsonl")
    monkeypatch.setattr("sys.argv", ["collect_traces.py", "--tasks", "6", "--samples", "2", "--workers", "3"])
    collect_traces.main()

    printed = capsys.readouterr().out
    assert printed.count("0/2 tries passed") == 6
    assert not list((tmp_path / "data").glob("*.jsonl"))  # nothing passed, so nothing was kept


def test_time_limit_stops_starting_new_tasks():
    assert collect_traces.try_task(None, "fake", seed=1, samples=1, deadline=1.0) is None  # 1970: long past
