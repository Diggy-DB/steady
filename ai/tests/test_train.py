"""Tests for scripts/train_lora.py: which tokens the model learns from, and the memory-saving loss.

The loss test needs PyTorch, which isn't a project dependency. Run it with:
    uv run --with torch --with peft==0.21.2 pytest tests/test_train.py
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from test_collect import example

# scripts/ isn't a package, so load train_lora.py by its path.
spec = importlib.util.spec_from_file_location("train_lora", Path(__file__).parents[1] / "scripts" / "train_lora.py")
train_lora = importlib.util.module_from_spec(spec)
sys.modules["train_lora"] = train_lora
spec.loader.exec_module(train_lora)


def test_assistant_spans_cover_the_models_turns_and_their_end():
    text = "<|im_start|>user\nHi<|im_end|>\n<|im_start|>assistant\nHello!<|im_end|>\n<|im_start|>assistant\nBye<|im_end|>"
    spans = train_lora.assistant_spans(text)
    assert [text[a:b] for a, b in spans] == ["Hello!<|im_end|>", "Bye<|im_end|>"]


def test_load_examples_can_skip_reminded_ones(tmp_path):
    lines = [{"messages": [], "tools": [], "meta": {"reminded": r}} for r in (False, True, False)]
    (tmp_path / "a.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    assert len(train_lora.load_examples(str(tmp_path / "*.jsonl"), skip_reminded=False)[0]) == 3
    assert train_lora.load_examples(str(tmp_path / "*.jsonl"), skip_reminded=True)[1] == 1


def test_learning_rate_warms_up_then_decays():
    factors = [train_lora.learning_rate_factor(s, warmup=2, total=10) for s in range(10)]
    assert factors[0] < factors[1] == 1.0 and factors[-1] < factors[3] and min(factors[2:]) >= 0.1


def test_only_the_models_own_turns_are_learned():
    transformers = pytest.importorskip("transformers")
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(train_lora.BASE_MODEL)
    except OSError:
        pytest.skip("tokenizer not downloaded and no network")
    ex = example()  # system, user, assistant (tool call), tool, assistant (answer)
    ids, labels = train_lora.tokenize(tokenizer, ex)
    runs, current = [], []
    for i, label in enumerate(labels):
        if label != -100:
            current.append(ids[i])
        elif current:
            runs.append(current)
            current = []
    runs += [current] if current else []
    texts = [tokenizer.decode(run) for run in runs]
    assert len(texts) == 2  # the two assistant turns, nothing else
    assert "<tool_call>" in texts[0] and texts[0].endswith("<|im_end|>")
    assert "Work 1-5 PM, gym 6-7 PM." in texts[1] and texts[1].endswith("<|im_end|>")
    assert not any("What do I have tomorrow?" in t or "<tool_response>" in t for t in texts)


def test_chunked_loss_equals_the_usual_loss():
    torch = pytest.importorskip("torch")
    from transformers import Qwen3Config, Qwen3ForCausalLM

    config = Qwen3Config(vocab_size=500, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                         num_attention_heads=4, num_key_value_heads=2, head_dim=8)
    torch.manual_seed(0)
    model = Qwen3ForCausalLM(config).eval()
    input_ids = torch.randint(0, 500, (1, 300))
    labels = input_ids.clone()
    labels[:, :120] = -100  # the context part
    labels[:, 200:230] = -100  # a tool result in the middle

    usual = model(input_ids=input_ids, labels=labels).loss
    hidden = model.model(input_ids=input_ids).last_hidden_state
    chunked = train_lora.chunked_loss(model.lm_head, hidden, labels, chunk=37)  # an odd size, to test the edges
    assert torch.allclose(usual, chunked, atol=1e-5)
