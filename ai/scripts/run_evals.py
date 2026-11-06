"""Run the eval suite several times and print pass rates per category, with honest error bars.

Every run is saved to evals/<date>-<model>-<label>.jsonl, so results can be compared later with
scripts/compare_evals.py (same cases, two models or two versions).

    uv run scripts/run_evals.py                                    # the hand-written suite (57 cases), 3 runs each
    uv run scripts/run_evals.py --suite all                        # + the 194 generated cases (251)
    uv run scripts/run_evals.py --suite generated
    uv run scripts/run_evals.py --only lookup move/alex_study_8pm  # categories or case names
    uv run scripts/run_evals.py --suite classic                    # the original 6 scenarios
    uv run scripts/run_evals.py --model qwen3.5:4b --no-think      # thinking off (Qwen3.5)
    uv run scripts/run_evals.py --workers 8                        # 8 runs at once (vLLM on a GPU)

How to read the numbers: "passed" counts runs; the 95% range is where the true pass rate probably is
(Wilson interval: wide when there are few runs). "all 3 runs" counts cases that passed EVERY run: a
planner students rely on has to be right every time, not on average.
"""

import argparse
import json
import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import openai

from ai import agent
from ai.eval_generated import GENERATED
from ai.eval_suite import SUITE
from ai.evals import SCENARIOS, run_scenario
from ai.llm import AI_DIR, load_settings, make_client


def wilson(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% range for a pass rate from `passed` of `total` runs (works for small numbers too)."""
    if total == 0:
        return 0.0, 1.0
    p = passed / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, center - half), min(1.0, center + half)


def print_report(results: list[dict], runs: int) -> None:
    by_case = defaultdict(list)
    for r in results:
        by_case[r["scenario"]].append(r)
    by_category = defaultdict(list)
    for name, case_runs in by_case.items():
        by_category[case_runs[0].get("category") or "-"].append(case_runs)

    print(f"\n{'category':<11} {'passed':>9} {'rate':>5} {'95% range':>11} {f'all {runs} runs':>11} {'tokens':>7} {'sec':>5}  most common failure")
    for category in sorted(by_category):
        flat = [r for case_runs in by_category[category] for r in case_runs]
        passed = sum(r["passed"] for r in flat)
        low, high = wilson(passed, len(flat))
        every = sum(all(r["passed"] for r in case_runs) for case_runs in by_category[category])
        failures = Counter(f for r in flat for f in r["failures"]).most_common(1)
        print(f"{category:<11} {passed:>4}/{len(flat):<4} {passed / len(flat):>5.0%} {low:>5.0%}-{high:<5.0%} "
              f"{every:>4}/{len(by_category[category]):<6} {sum(r['tokens'] for r in flat) / len(flat):>7.0f} "
              f"{sum(r['seconds'] for r in flat) / len(flat):>5.0f}  {failures[0][0][:60] if failures else ''}")
    passed = sum(r["passed"] for r in results)
    low, high = wilson(passed, len(results))
    every = sum(all(r["passed"] for r in case_runs) for case_runs in by_case.values())
    print(f"{'TOTAL':<11} {passed:>4}/{len(results):<4} {passed / len(results):>5.0%} {low:>5.0%}-{high:<5.0%} "
          f"{every:>4}/{len(by_case):<6} (cases right every run)")
    flaky = [name for name, case_runs in by_case.items() if 0 < sum(r["passed"] for r in case_runs) < len(case_runs)]
    never = [name for name, case_runs in by_case.items() if not any(r["passed"] for r in case_runs)]
    if never:
        print(f"\nNever passed ({len(never)}): {', '.join(never)}")
    if flaky:
        print(f"Sometimes passed ({len(flaky)}): {', '.join(flaky)}")


def select(suite: list, only: list[str] | None) -> list:
    if not only:
        return suite
    return [s for s in suite if any(o == s.name or o == s.category or s.name.startswith(o) for o in only)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval suite.")
    parser.add_argument("--runs", type=int, default=3, help="runs per case")
    parser.add_argument("--only", nargs="*", help="categories or case names (default: all)")
    parser.add_argument("--suite", choices=["full", "generated", "all", "classic"], default="full",
                        help="full = the 57 hand-written cases; generated = the 194 generated ones; all = both; "
                             "classic = the original 6 scenarios")
    parser.add_argument("--model", help="use this model instead of LLM_MODEL from .env")
    parser.add_argument("--label", default="", help="added to the results file name, e.g. 'qwen35-nothink'")
    parser.add_argument("--workers", type=int, default=1, help="runs at the same time (Ollama on a laptop: 1)")
    parser.add_argument("--no-think", action="store_true", help="thinking off, for models that can switch (Qwen3.5)")
    args = parser.parse_args()

    settings = load_settings()
    client = make_client(settings)
    model = args.model or settings.model
    if args.no_think:  # said the way each server understands it
        off = {"reasoning_effort": "none"} if ":11434" in settings.base_url else {"chat_template_kwargs": {"enable_thinking": False}}
        agent.EXTRA_SAMPLING = {**agent.EXTRA_SAMPLING, **off}
        agent.SAMPLING = {**agent.SAMPLING, "presence_penalty": 0.0}
    suites = {"full": SUITE, "generated": GENERATED, "all": SUITE + GENERATED, "classic": SCENARIOS}
    scenarios = select(suites[args.suite], args.only)
    if not scenarios:
        raise SystemExit(f"Nothing matches {args.only}.")

    stamp = f"{datetime.now():%Y-%m-%d-%H%M}"
    out = AI_DIR / "evals" / f"{'-'.join(filter(None, [stamp, model.replace('/', '_').replace(':', '_'), args.label]))}.jsonl"
    out.parent.mkdir(exist_ok=True)
    print(f"{len(scenarios)} cases x {args.runs} runs, model {model}{' (thinking off)' if args.no_think else ''}", flush=True)

    def one(scenario, run):
        result = {"model": model, "base_url": settings.base_url, "label": args.label, "run": run,
                  **run_scenario(client, model, scenario)}
        del result["messages"], result["reasoning"]  # the full runs are in logs/evals.jsonl
        return result

    results = []
    jobs = [(s, run) for run in range(1, args.runs + 1) for s in scenarios]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one, s, run): (s, run) for s, run in jobs}
        for future in as_completed(futures):
            scenario, run = futures[future]
            try:
                result = future.result()
            except openai.APIConnectionError:
                raise SystemExit(f"Can't reach {settings.base_url}. Is the model server running?") from None
            results.append(result)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            verdict = "PASS" if result["passed"] else "FAIL: " + "; ".join(result["failures"])
            print(f"[{len(results)}/{len(jobs)}] {scenario.name} run {run}: {verdict}  ({result['tokens']} tokens, "
                  f"{result['seconds']}s)", flush=True)

    print_report(results, args.runs)
    print(f"\nSaved to {out.relative_to(AI_DIR)}")


if __name__ == "__main__":
    main()
