"""Run the eval scenarios several times and print a pass-rate table.

Every run is also saved to evals/<date>-<model>.jsonl, so results can be
compared later (different prompt, different model, RunPod vs Mac).

Examples (run from the ai/ folder):
    uv run scripts/run_evals.py                                   # every scenario, 3 runs each
    uv run scripts/run_evals.py --runs 1 --only tomorrow fixed_lecture
    uv run scripts/run_evals.py --model qwen3:4b-instruct-2507-q8_0
"""

import argparse
import json
from collections import Counter
from datetime import datetime

import openai

from ai.evals import SCENARIOS, run_scenario
from ai.llm import AI_DIR, load_settings, make_client


def print_table(results: list[dict]) -> None:
    print(f"\n{'scenario':<20} {'passed':>7} {'avg tokens':>11} {'avg sec':>8}  most common failure")
    for name in dict.fromkeys(r["scenario"] for r in results):  # keeps the scenario order
        runs = [r for r in results if r["scenario"] == name]
        passed = sum(r["passed"] for r in runs)
        failures = Counter(f for r in runs for f in r["failures"])
        top = failures.most_common(1)[0][0] if failures else ""
        tokens = sum(r["tokens"] for r in runs) / len(runs)
        seconds = sum(r["seconds"] for r in runs) / len(runs)
        print(f"{name:<20} {passed:>3}/{len(runs):<3} {tokens:>11.0f} {seconds:>8.0f}  {top}")
    total = sum(r["passed"] for r in results)
    print(f"{'TOTAL':<20} {total:>3}/{len(results):<3}  ({100 * total / len(results):.0f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval scenarios.")
    parser.add_argument("--runs", type=int, default=3, help="runs per scenario")
    parser.add_argument("--only", nargs="*", help="scenario names to run (default: all)")
    parser.add_argument("--model", help="use this model instead of LLM_MODEL from .env")
    parser.add_argument("--label", default="", help="added to the results file name, e.g. 'fewer-slots'")
    args = parser.parse_args()

    settings = load_settings()
    client = make_client(settings)
    model = args.model or settings.model
    scenarios = [s for s in SCENARIOS if not args.only or s.name in args.only]
    if not scenarios:
        raise SystemExit(f"No scenario matches {args.only}. Names: {[s.name for s in SCENARIOS]}")

    name = "-".join(filter(None, [f"{datetime.now():%Y-%m-%d-%H%M}", model.replace("/", "_").replace(":", "_"), args.label]))
    out = AI_DIR / "evals" / f"{name}.jsonl"
    out.parent.mkdir(exist_ok=True)

    results = []
    for scenario in scenarios:
        for run in range(1, args.runs + 1):
            try:
                result = {"model": model, "base_url": settings.base_url, "label": args.label, **run_scenario(client, model, scenario)}
                del result["messages"], result["reasoning"]  # keep the results file small; the full runs are in logs/evals.jsonl
            except openai.APIConnectionError:
                raise SystemExit(f"Can't reach {settings.base_url}. Is `ollama serve` running?") from None
            results.append(result)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            verdict = "PASS" if result["passed"] else "FAIL: " + "; ".join(result["failures"])
            print(f"{scenario.name} run {run}: {verdict}  ({result['tokens']} tokens, {result['seconds']}s)", flush=True)

    print_table(results)
    print(f"\nSaved to {out.relative_to(AI_DIR)}")


if __name__ == "__main__":
    main()
