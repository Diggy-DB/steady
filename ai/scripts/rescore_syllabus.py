"""Score saved syllabus-import runs again with the CURRENT scorer (scripts/eval_syllabus.py), without
running the model again. Needs results saved with their answers (runs from Nov 6 on).

    uv run scripts/rescore_syllabus.py evals/<date>-syllabus-import-<model>.json [--out evals/<new>.json]
"""

import argparse
import importlib.util
import json
from pathlib import Path


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score saved syllabus-import runs.")
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    eval_syllabus, eval_import = load("eval_syllabus"), load("eval_syllabus_import")
    saved = json.loads(args.results.read_text())
    truth = json.loads((eval_syllabus.FIXTURES / "truth.json").read_text())
    results, changed = [], 0
    for r in saved["results"]:
        if "answer" not in r:
            raise SystemExit("These results were saved without answers; run the eval again.")
        again = {**r, **eval_syllabus.score(truth[r["file"]], r["answer"])}
        changed += (again["found"], again["made_up"]) != (r["found"], r["made_up"])
        results.append(again)
    print(f"{len(results)} runs re-scored, {changed} changed.")
    eval_import.report(results, truth, saved["label"] + " (re-scored)", max(r["run"] for r in results))
    if args.out:
        args.out.write_text(json.dumps({**saved, "label": saved["label"], "results": results}, indent=2, default=str))


if __name__ == "__main__":
    main()
