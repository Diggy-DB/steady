"""Score saved eval runs again with the CURRENT checks, without running the model again.

Use it after fixing a check (e.g. a correct phrasing the check didn't accept): the saved answers and
suggestions are re-checked, and the report shows what changed. Runs of cases whose question has changed
since are left out (they have to be run again).

    uv run scripts/rescore_evals.py evals/<results>.jsonl [--out evals/<rescored>.jsonl]
"""

import argparse
import importlib.util
import json
from pathlib import Path

from ai.agent import MAX_ROUNDS
from ai.eval_generated import GENERATED
from ai.eval_suite import SUITE
from ai.evals import Transcript

spec = importlib.util.spec_from_file_location("run_evals", Path(__file__).parent / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)


def rescore(result: dict, scenario) -> dict:
    transcript = Transcript(
        answer=result["answer"],
        tool_calls=[{"name": name, "arguments": "", "result": ""} for name in result["tools"]],
        suggestions=result["suggestions"],
        rounds=result["rounds"],
        gave_up=result["rounds"] >= MAX_ROUNDS and result["answer"].startswith("Sorry, I couldn't finish"),
    )
    failures = [problem for check in scenario.checks if (problem := check(transcript))]
    return {**result, "passed": not failures, "failures": failures, "category": scenario.category}


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-check saved eval runs with the current checks.")
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--skip", nargs="*", default=[], help="cases whose question changed (no question saved)")
    args = parser.parse_args()

    scenarios = {s.name: s for s in SUITE + GENERATED}
    old = [json.loads(line) for line in args.results.read_text().splitlines()]
    new, changed, dropped = [], [], set()
    for r in old:
        scenario = scenarios.get(r["scenario"])
        if scenario is None or r["scenario"] in args.skip or r.get("question", scenario.question) != scenario.question:
            dropped.add(r["scenario"])
            continue
        again = rescore(r, scenario)
        if again["passed"] != r["passed"]:
            changed.append(f"{r['scenario']} run {r.get('run')}: {'FAIL -> PASS' if again['passed'] else 'PASS -> FAIL'}")
        new.append(again)
    print(f"{len(new)} runs re-checked; {len(changed)} changed:" + "".join(f"\n  {c}" for c in changed))
    if dropped:
        print(f"Left out (case changed, run it again): {', '.join(sorted(dropped))}")
    runs = max((r.get("run", 1) for r in new), default=1)
    run_evals.print_report(new, runs)
    if args.out:
        args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new))


if __name__ == "__main__":
    main()
