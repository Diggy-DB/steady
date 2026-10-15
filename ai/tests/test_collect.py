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
