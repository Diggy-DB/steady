"""Collect training examples: run the teacher model on synthetic tasks, keep the best passing run.

For each task the model gets several tries. A try is kept only if it passes every check, finished
on its own, and didn't need the "you forgot to propose" reminder. Of the kept tries, the one with
the FEWEST tokens becomes the training example: the model learns from its own shortest correct
answers, which is the "think less" idea in notes/training.md.

Examples go to data/<date>-<model>.jsonl in the chat format fine-tuning tools read (Hugging Face
TRL, Unsloth): one JSON object per line with "messages" and "tools". The model's thinking is in
"reasoning_content", which Qwen's chat template turns back into <think>...</think>.

Examples (run from the ai/ folder):
    uv run scripts/collect_traces.py --tasks 20 --samples 3
    uv run scripts/collect_traces.py --tasks 500 --samples 4 --start 1000     # e.g. on a RunPod GPU
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime

import openai

from ai.agent import TOOLS
from ai.evals import run_scenario
from ai.llm import AI_DIR, load_settings, make_client
from ai.synth import make_task

COLLECT_LOG = AI_DIR / "logs" / "collect.jsonl"


def training_example(run: dict, meta: dict) -> dict:
    """One conversation in the format TRL and Unsloth read, ending with the model's final answer."""
    final = {"role": "assistant", "content": run["answer"], "reasoning_content": run["reasoning"]}
    return {
        "messages": [*run["messages"], final],
        "tools": [definition for definition, _ in TOOLS.values()],
        "meta": meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect training examples from synthetic tasks.")
    parser.add_argument("--tasks", type=int, default=20, help="how many synthetic tasks")
    parser.add_argument("--samples", type=int, default=3, help="tries per task")
    parser.add_argument("--start", type=int, default=0, help="first task seed (use new seeds for new data)")
    parser.add_argument("--model", help="teacher model (default: LLM_MODEL from .env)")
    args = parser.parse_args()

    settings = load_settings()
    client = make_client(settings)
    model = args.model or settings.model
    out = AI_DIR / "data" / f"{datetime.now():%Y-%m-%d-%H%M}-{model.replace('/', '_').replace(':', '_')}.jsonl"
    out.parent.mkdir(exist_ok=True)

    stats: dict[str, Counter] = defaultdict(Counter)
    for seed in range(args.start, args.start + args.tasks):
        task = make_task(seed)
        kind = task.name.rsplit("-", 1)[0]
        tries = []
        for _ in range(args.samples):
            try:
                tries.append(run_scenario(client, model, task, log_path=COLLECT_LOG))
            except openai.APIConnectionError:
                raise SystemExit(f"Can't reach {settings.base_url}. Is the model server running?") from None
        good = [t for t in tries if t["passed"] and not t["nudged"]]
        stats[kind].update(tasks=1, tries=len(tries), passed=len(good), kept=bool(good))

        note = ""
        if good:
            best = min(good, key=lambda t: t["tokens"])
            meta = {"task": task.name, "seed": seed, "question": task.question, "model": model,
                    "tokens": best["tokens"], "tries": len(tries), "passed_tries": len(good)}
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(training_example(best, meta), ensure_ascii=False) + "\n")
            note = f", kept the shortest ({best['tokens']} tokens; longest passing: {max(t['tokens'] for t in good)})"
        failures = Counter(f for t in tries for f in t["failures"]).most_common(1)
        print(f"{task.name}: {len(good)}/{len(tries)} tries passed{note}" + (f"  [{failures[0][0]}]" if failures else ""), flush=True)

    print(f"\n{'task type':<16} {'tasks':>5} {'kept':>5} {'tries passed':>13}")
    for kind, c in sorted(stats.items()):
        print(f"{kind:<16} {c['tasks']:>5} {c['kept']:>5} {c['passed']:>6}/{c['tries']:<6}")
    print(f"\nExamples saved to {out.relative_to(AI_DIR)}")


if __name__ == "__main__":
    main()
