"""Fine-tune the model on the collected examples with LoRA. Runs on a GPU pod (deploy/runpod_train.sh).

LoRA leaves the 4B original numbers frozen and trains small extra matrices next to some of its
layers (about 33M numbers, ~130 MB). That fits on one 24 GB GPU, and the result is a small
"adapter" that vLLM loads on top of the original model (`--enable-lora`).

The model learns only from its own turns: thinking, tool calls and final answers. The system
prompt, the user's question and the tool results are context it reads, not text to imitate.

Run from the ai/ folder. The training libraries aren't project dependencies (they'd add 2 GB
to every laptop install), so they're added for this one run with `--with`:

    uv run --with torch --with peft==0.19.1 scripts/train_lora.py                       # train
    uv run scripts/train_lora.py --check                                               # only count, any computer
    uv run --with torch --with peft==0.19.1 scripts/train_lora.py --base <tiny model> --max-steps 2   # a quick test
"""

import argparse
import glob
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
BASE_MODEL = "Qwen/Qwen3-4B-Thinking-2507"
# The layers LoRA adds its matrices to: attention (q, k, v, o) and the feed-forward part (gate, up, down).
# These are also the ones vLLM can load an adapter for.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

# How Qwen's chat template marks the model's own turns.
ASSISTANT_START = "<|im_start|>assistant\n"
TURN_END = "<|im_end|>"


def load_examples(pattern: str, skip_reminded: bool) -> tuple[list[dict], int]:
    """Read every example from the files matching `pattern`. Returns (examples, how many were skipped)."""
    examples, skipped = [], 0
    for path in sorted(glob.glob(pattern)):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            example = json.loads(line)
            if skip_reminded and example.get("meta", {}).get("reminded"):
                skipped += 1
                continue
            examples.append(example)
    return examples, skipped


def assistant_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges of the model's own turns: from after "<|im_start|>assistant\\n" up to and
    including "<|im_end|>", so the model also learns where to stop."""
    spans, position = [], 0
    while (start := text.find(ASSISTANT_START, position)) != -1:
        start += len(ASSISTANT_START)
        end = text.find(TURN_END, start)
        end = len(text) if end == -1 else end + len(TURN_END)
        spans.append((start, end))
        position = end
    return spans


def tokenize(tokenizer, example: dict) -> tuple[list[int], list[int]]:
    """Turn one conversation into (token ids, labels). A label is the token itself where the model
    should learn it, and -100 ("ignore") everywhere else."""
    text = tokenizer.apply_chat_template(example["messages"], tools=example["tools"], tokenize=False)
    encoded = tokenizer(text, return_offsets_mapping=True, add_special_tokens=False)
    spans = assistant_spans(text)
    labels, k = [], 0
    for token, (start, _) in zip(encoded["input_ids"], encoded["offset_mapping"]):
        while k < len(spans) and start >= spans[k][1]:
            k += 1
        inside = k < len(spans) and spans[k][0] <= start < spans[k][1]
        labels.append(token if inside else -100)
    return encoded["input_ids"], labels


def prepare(tokenizer, examples: list[dict], max_length: int) -> tuple[list[tuple], Counter]:
    """Tokenize every example; drop the ones longer than `max_length` tokens. Also returns statistics."""
    data, stats = [], Counter()
    for example in examples:
        ids, labels = tokenize(tokenizer, example)
        kind = example.get("meta", {}).get("task", "unknown").rsplit("-", 1)[0]
        if len(ids) > max_length:
            stats["too long"] += 1
            continue
        data.append((ids, labels))
        stats[f"type {kind}"] += 1
        stats["tokens"] += len(ids)
        stats["trained tokens"] += sum(label != -100 for label in labels)
        stats["longest"] = max(stats["longest"], len(ids))
    return data, stats


def chunked_loss(lm_head, hidden, labels, chunk: int = 2048):
    """Cross-entropy on the trained tokens only, a chunk at a time.

    The normal way computes a score for each of the 151,936 vocabulary tokens at every position at
    once: for a 16,000-token conversation that's ~10 GB on its own. Here only the trained positions
    get scores, a chunk at a time, and each chunk is recomputed during the backward pass instead of
    being kept (checkpoint), so memory stays small.
    """
    import torch
    import torch.nn.functional as F
    from torch.utils.checkpoint import checkpoint

    hidden = hidden[:, :-1].reshape(-1, hidden.size(-1))  # position t predicts token t + 1
    targets = labels[:, 1:].reshape(-1)
    keep = targets != -100
    hidden, targets = hidden[keep], targets[keep]

    def piece(h, y):
        return F.cross_entropy(lm_head(h).float(), y, reduction="sum")

    total = torch.zeros((), device=hidden.device)
    for i in range(0, len(targets), chunk):
        total = total + checkpoint(piece, hidden[i : i + chunk], targets[i : i + chunk], use_reentrant=False)
    return total / max(len(targets), 1)


def learning_rate_factor(step: int, warmup: int, total: int) -> float:
    """Warm up linearly, then decay along a cosine curve to 10% of the peak learning rate."""
    if step < warmup:
        return (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup)
    return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(progress, 1.0)))


def train(args, data: list[tuple], stats: Counter) -> None:
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading {args.base} on {device}...", flush=True)
    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16).to(device)
    model.config.use_cache = False
    # Keep only each layer's input during the forward pass and recompute the rest when computing
    # gradients: slower (~30%) but needs far less memory for long conversations.
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    config = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
                        target_modules=TARGET_MODULES, task_type="CAUSAL_LM")
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    inner = model.get_base_model()  # the original model, now with LoRA matrices inside its layers

    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=0.0)
    micro_steps = len(data) * args.epochs  # one conversation at a time
    total_steps = math.ceil(micro_steps / args.accum)  # weights update once per `accum` conversations
    if args.max_steps:
        total_steps = min(total_steps, args.max_steps)
    warmup = max(1, round(0.1 * total_steps))
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda s: learning_rate_factor(s, warmup, total_steps))
    print(f"{len(data)} conversations x {args.epochs} epochs = {total_steps} updates "
          f"(each from {args.accum} conversations)", flush=True)

    model.train()
    history, started, step, done, window_loss, window_tokens = [], time.time(), 0, 0, [], 0
    order = [i for _ in range(args.epochs) for i in random.sample(range(len(data)), len(data))]
    for n, index in enumerate(order, 1):
        ids, labels = data[index]
        input_ids = torch.tensor([ids], device=device)
        hidden = inner.model(input_ids=input_ids).last_hidden_state
        loss = chunked_loss(inner.lm_head, hidden, torch.tensor([labels], device=device))
        (loss / args.accum).backward()
        window_loss.append(loss.item())
        window_tokens += len(ids)

        if n % args.accum == 0 or n == len(order):
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            step += 1
            elapsed = time.time() - started
            average = sum(window_loss) / len(window_loss)
            history.append(round(average, 4))
            print(f"update {step}/{total_steps}  loss {average:.3f}  lr {scheduler.get_last_lr()[0]:.1e}  "
                  f"{window_tokens / max(elapsed - done, 1e-6):.0f} tokens/s  "
                  f"{elapsed / 60:.1f} min, about {elapsed / step * (total_steps - step) / 60:.0f} min left", flush=True)
            window_loss, window_tokens, done = [], 0, elapsed
            if step >= total_steps:
                break

    out = Path(args.out)
    model.save_pretrained(out)  # only the LoRA matrices (the adapter), not the 8 GB model
    summary = {
        "base": args.base, "examples": len(data), "epochs": args.epochs, "updates": step, "accum": args.accum,
        "learning_rate": args.lr, "rank": args.rank, "max_length": args.max_length,
        "skip_reminded": args.skip_reminded, "loss_per_update": history,
        "minutes": round((time.time() - started) / 60, 1),
        "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1) if device == "cuda" else None,
        "data": {k: v for k, v in stats.items()},
    }
    (out / "train_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Saved the adapter to {out} ({summary['minutes']} min, loss {history[0]} -> {history[-1]})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune the model on collected examples with LoRA.")
    parser.add_argument("--data", default=str(AI_DIR / "data" / "*.jsonl"), help="files with training examples")
    parser.add_argument("--out", default=str(AI_DIR / "out" / "lora"), help="where to save the adapter")
    parser.add_argument("--base", default=BASE_MODEL, help="the model to fine-tune")
    parser.add_argument("--epochs", type=int, default=2, help="passes over the data")
    parser.add_argument("--lr", type=float, default=1e-4, help="peak learning rate")
    parser.add_argument("--rank", type=int, default=16, help="LoRA rank: size of the extra matrices")
    parser.add_argument("--accum", type=int, default=8, help="conversations per weight update")
    parser.add_argument("--max-length", type=int, default=16384, help="skip longer conversations (tokens)")
    parser.add_argument("--skip-reminded", action="store_true", help="leave out examples that needed the reminder")
    parser.add_argument("--max-steps", type=int, default=0, help="stop after this many updates (for a quick test)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--check", action="store_true", help="only tokenize and print statistics")
    args = parser.parse_args()

    from transformers import AutoTokenizer

    examples, skipped = load_examples(args.data, args.skip_reminded)
    if not examples:
        raise SystemExit(f"No examples in {args.data}. Collect some first: scripts/collect_traces.py")
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    data, stats = prepare(tokenizer, examples, args.max_length)
    print(f"{len(examples) + skipped} examples: {len(data)} used, {stats['too long']} longer than "
          f"{args.max_length} tokens, {skipped} skipped because they needed the reminder")
    print(f"{stats['tokens']:,} tokens, {stats['trained tokens']:,} of them the model's own "
          f"({stats['trained tokens'] / max(stats['tokens'], 1):.0%}); longest {stats['longest']:,}")
    print("by task type: " + ", ".join(f"{k[5:]} {v}" for k, v in sorted(stats.items()) if k.startswith("type ")))
    if not args.check:
        train(args, data, stats)


if __name__ == "__main__":
    main()
