"""Collect training examples: run the teacher model on synthetic tasks, keep the best passing run.

For each task the model gets several tries. A try is kept only if it passes every check and
finished on its own. Of the kept tries, the one with the FEWEST tokens becomes the training
example: the model learns from its own shortest correct answers (the "think less" idea).

Tries that passed only after the code reminder ("you recommended times but created no
suggestions") are used when no try passed without it: the text-only answer and the reminder
are cut out, so the example shows the model proposing directly. If its later thinking mentions
the reminder, the try is skipped, so the model doesn't learn to expect a reminder. Such examples
are marked "reminded": true in their meta, so they can be filtered out later.

Examples go to data/<date>-<model>.jsonl in the chat format fine-tuning tools read (Hugging Face
TRL, Unsloth): one JSON object per line with "messages" and "tools". The model's thinking is in
"reasoning_content", which Qwen's chat template turns back into <think>...</think>.

Examples (run from the ai/ folder):
    uv run scripts/collect_traces.py --tasks 20 --samples 3
    uv run scripts/collect_traces.py --tasks 500 --samples 4 --start 1000     # e.g. on a RunPod GPU
"""

import argparse
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import openai

from ai.agent import NUDGE, TOOLS
from ai.evals import run_scenario
from ai.llm import AI_DIR, load_settings, make_client
from ai.synth import make_task

COLLECT_LOG = AI_DIR / "logs" / "collect.jsonl"
# Signs that the model's thinking refers to the reminder it got.
REMINDER_HINTS = ("remind", "system message", "didn't create", "did not create", "nothing to accept", "forgot to")


def without_reminder(run: dict) -> dict | None:
    """A reminded run with the text-only answer and the reminder cut out, or None if the
    model's later thinking refers to the reminder."""
    messages = run["messages"]
    i = next(k for k, m in enumerate(messages) if m["role"] == "system" and m["content"] == NUDGE)
    later = messages[i + 1 :]
    thinking = " ".join(m.get("reasoning_content") or "" for m in later) + " " + run["reasoning"]
    if any(hint in thinking.lower() for hint in REMINDER_HINTS):
        return None
    return {**run, "messages": messages[: i - 1] + later}  # i - 1 is the answer that got reminded


def training_example(run: dict, meta: dict) -> dict:
    """One conversation in the format TRL and Unsloth read, ending with the model's final answer."""
    final = {"role": "assistant", "content": run["answer"], "reasoning_content": run["reasoning"]}
    return {
        "messages": [*run["messages"], final],
        "tools": [definition for definition, _ in TOOLS.values()],
        "meta": meta,
    }


def try_task(client, model: str, seed: int, samples: int, deadline: float = 0) -> tuple | None:
    """Run one synthetic task `samples` times. Returns (task, tries), or None if the time is up."""
    if deadline and time.time() > deadline:
        return None
    task = make_task(seed)
    tries = [run_scenario(client, model, task, log_path=COLLECT_LOG) for _ in range(samples)]
    return task, tries


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect training examples from synthetic tasks.")
    parser.add_argument("--tasks", type=int, default=20, help="how many synthetic tasks")
    parser.add_argument("--samples", type=int, default=3, help="tries per task")
    parser.add_argument("--start", type=int, default=0, help="first task seed (use new seeds for new data)")
    parser.add_argument("--model", help="teacher model (default: LLM_MODEL from .env)")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="tasks run at the same time (vLLM on a GPU handles many at once, e.g. 8; Ollama on a laptop: 1)",
    )
    parser.add_argument(
        "--minutes", type=float, default=0,
        help="stop starting new tasks after this many minutes (0 = no limit); keeps a paid GPU session bounded",
    )
    args = parser.parse_args()

    settings = load_settings()
    client = make_client(settings)
    model = args.model or settings.model
    out = AI_DIR / "data" / f"{datetime.now():%Y-%m-%d-%H%M}-{model.replace('/', '_').replace(':', '_')}.jsonl"
    out.parent.mkdir(exist_ok=True)

    stats: dict[str, Counter] = defaultdict(Counter)
    seeds = range(args.start, args.start + args.tasks)
    deadline = time.time() + args.minutes * 60 if args.minutes else 0
    not_started = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(try_task, client, model, seed, args.samples, deadline) for seed in seeds]
        for future in as_completed(futures):
            try:
                result = future.result()
            except openai.APIConnectionError:
                raise SystemExit(f"Can't reach {settings.base_url}. Is the model server running?") from None
            if result is None:
                not_started += 1
                continue
            task, tries = result
            kind = task.name.rsplit("-", 1)[0]
            passed = sum(t["passed"] for t in tries)
            plain = [t for t in tries if t["passed"] and not t["nudged"]]
            reminded = [cut for t in tries if t["passed"] and t["nudged"] if (cut := without_reminder(t))]
            good = plain or reminded
            stats[kind].update(tasks=1, tries=len(tries), passed=passed, kept=bool(good),
                               kept_reminded=bool(good) and not plain)

            note = ""
            if good:
                best = min(good, key=lambda t: t["tokens"])
                meta = {"task": task.name, "seed": int(task.name.rsplit("-", 1)[1]), "question": task.question,
                        "model": model, "tokens": best["tokens"], "tries": len(tries), "passed_tries": passed,
                        "reminded": not plain}
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(training_example(best, meta), ensure_ascii=False) + "\n")
                note = f", kept the shortest ({best['tokens']} tokens{', reminder cut out' if not plain else ''})"
            failures = Counter(f for t in tries for f in t["failures"]).most_common(1)
            print(f"{task.name}: {passed}/{len(tries)} tries passed{note}"
                  + (f"  [{failures[0][0]}]" if failures else ""), flush=True)

    print(f"\n{'task type':<16} {'tasks':>5} {'kept':>5} {'of which reminded':>18} {'tries passed':>13}")
    for kind, c in sorted(stats.items()):
        print(f"{kind:<16} {c['tasks']:>5} {c['kept']:>5} {c['kept_reminded']:>18} {c['passed']:>6}/{c['tries']:<6}")
    if not_started:
        print(f"\nTime limit ({args.minutes:g} min) reached: {not_started} tasks weren't started.")
    print(f"\nExamples saved to {out.relative_to(AI_DIR)}")


if __name__ == "__main__":
    main()
