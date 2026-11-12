"""Training and merging, end to end on a tiny random copy of Qwen3.5-4B (same layer types and weight
names, 4 layers instead of 32), plus the label masking on the real tokenizer.

The tokenizer tests run everywhere; the rest needs the training libraries:
    uv run --with torch --with peft==0.21.2 pytest tests/test_train_merge.py
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

AI = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("train_lora", AI / "scripts" / "train_lora.py")
train_lora = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train_lora)

SYSTEM = "You are Steady, a planning assistant."
EXAMPLE = {
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "What do I have tomorrow?"},
        {"role": "assistant", "content": "", "reasoning_content": "Look up Tuesday.",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "get_schedule", "arguments": '{"start_date": "2026-10-06", "end_date": "2026-10-06"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"events": [{"name": "Work"}]}'},
        {"role": "assistant", "content": "Work 1-5 PM.", "reasoning_content": "Only work."},
    ],
    "tools": [{"type": "function", "function": {"name": "get_schedule", "description": "Look up events.",
               "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}}}}}],
    "meta": {"task": "look_up-1"},
}


def snapshot() -> Path:
    try:
        from huggingface_hub import snapshot_download

        return Path(snapshot_download("Qwen/Qwen3.5-4B", allow_patterns=["*.json", "*.jinja"]))
    except Exception:
        pytest.skip("Qwen3.5-4B's tokenizer isn't downloaded and there's no network")


def test_labels_cover_only_the_models_own_turns():
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(snapshot())
    ids, labels = train_lora.tokenize(tokenizer, EXAMPLE)
    learned = tokenizer.decode([t for t, label in zip(ids, labels) if label != -100])
    # both turns, from right after the "<think>\n" the server writes, to the end-of-turn marker
    assert learned.startswith("Look up Tuesday.\n</think>\n\n<tool_call>\n<function=get_schedule>")
    assert "<parameter=start_date>\n2026-10-06\n</parameter>" in learned  # arguments as an object, not JSON text
    assert learned.endswith("Only work.\n</think>\n\nWork 1-5 PM.<|im_end|>")
    assert learned.count("<|im_end|>") == 2
    for context in (SYSTEM, "What do I have tomorrow?", "<tool_response>", '"events"', "<think>"):
        assert context not in learned


def tiny_qwen35(folder: Path) -> None:
    """A random 4-layer Qwen3.5 picture-and-text model saved like the real one: bf16, in several files,
    with an mtp weight vLLM keeps and transformers ignores."""
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import AutoConfig, Qwen3_5ForConditionalGeneration

    real = snapshot()
    config = json.loads((real / "config.json").read_text())
    config["text_config"].update(
        hidden_size=64, intermediate_size=128, num_hidden_layers=4, head_dim=32, num_attention_heads=4,
        num_key_value_heads=2, linear_key_head_dim=16, linear_value_head_dim=16, linear_num_key_heads=2,
        linear_num_value_heads=4, layer_types=["linear_attention"] * 3 + ["full_attention"])
    config["text_config"]["rope_parameters"]["mrope_section"] = [2, 1, 1]  # head_dim 32 x 0.25 = 8 = 2 x 4
    config["vision_config"].update(depth=1, hidden_size=32, intermediate_size=64, num_heads=2, out_hidden_size=64)
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(json.dumps(config))
    torch.manual_seed(0)
    model = Qwen3_5ForConditionalGeneration(AutoConfig.from_pretrained(folder)).to(torch.bfloat16)
    model.save_pretrained(folder, max_shard_size="20MB")
    for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja"):
        shutil.copy(real / name, folder / name)
    index = json.loads((folder / "model.safetensors.index.json").read_text())
    shard = sorted(set(index["weight_map"].values()))[-1]
    tensors = load_file(folder / shard)
    tensors["mtp.fc.weight"] = torch.randn(64, 128).to(torch.bfloat16)
    save_file(tensors, folder / shard, metadata={"format": "pt"})
    index["weight_map"]["mtp.fc.weight"] = shard
    (folder / "model.safetensors.index.json").write_text(json.dumps(index))


def logits(model, ids):
    import torch

    with torch.no_grad():
        return model(input_ids=ids).logits.float()


def test_train_then_merge_gives_the_same_model(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from peft import PeftModel
    from safetensors import safe_open
    from transformers import AutoModelForCausalLM, Qwen3_5ForConditionalGeneration

    base, lora, merged = tmp_path / "base", tmp_path / "lora", tmp_path / "merged"
    tiny_qwen35(base)
    data = tmp_path / "data.jsonl"
    data.write_text("\n".join(json.dumps(EXAMPLE) for _ in range(3)) + "\n")
    run = lambda *args: subprocess.run([sys.executable, *args], cwd=AI, check=True, capture_output=True, text=True)
    trained = run("scripts/train_lora.py", "--base", str(base), "--data", str(data), "--out", str(lora),
                  "--max-steps", "3", "--accum", "1", "--lr", "0.05", "--rank", "4")
    assert "Saved the adapter" in trained.stdout
    merging = run("scripts/merge_lora.py", "--base", str(base), "--adapter", str(lora), "--out", str(merged))
    # every LoRA'd layer changed: 3 linear-attention layers x (5 + 3 feed-forward) + 1 attention layer x (4 + 3)
    assert "Merged 31 weights" in merging.stdout

    ids = torch.tensor([[1, 500, 2000, 30000, 77, 248000, 9]])
    full_base = Qwen3_5ForConditionalGeneration.from_pretrained(base, dtype=torch.float32).eval()
    text_base = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32).eval()
    assert type(text_base).__name__ == "Qwen3_5ForCausalLM"
    assert torch.allclose(logits(full_base, ids), logits(text_base, ids), atol=1e-5)  # every text weight loaded

    trained_model = PeftModel.from_pretrained(text_base, lora).eval()
    full_merged = Qwen3_5ForConditionalGeneration.from_pretrained(merged, dtype=torch.float32).eval()
    before, adapter, after = logits(full_base, ids), logits(trained_model, ids), logits(full_merged, ids)
    change = (adapter - before).abs().max().item()
    assert change > 0.05  # training changed the model...
    assert (after - adapter).abs().max().item() < 0.05 * change  # ...and the merge kept that change (up to bf16 rounding)

    def weights(folder):
        index = json.loads((folder / "model.safetensors.index.json").read_text())["weight_map"]
        out = {}
        for shard in set(index.values()):
            with safe_open(folder / shard, "pt") as f:
                out.update({k: f.get_tensor(k) for k in f.keys()})
        return out

    old, new = weights(base), weights(merged)
    assert set(old) == set(new) and "mtp.fc.weight" in new
    assert all(new[k].dtype == old[k].dtype for k in old)
    changed = {k for k in old if not torch.equal(old[k], new[k])}
    assert len(changed) == 31 and all(k.startswith("model.language_model.layers.") for k in changed)
    assert not any(k.startswith("model.visual") for k in changed)
    for name in ("config.json", "tokenizer.json", "chat_template.jinja"):
        assert (merged / name).read_bytes() == (base / name).read_bytes()
    assert json.loads((merged / "steady_merge.json").read_text())["changed_weights"] == 31
