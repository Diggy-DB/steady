"""Score the syllabus import pipeline (src/ai/syllabus.py) end to end: upload -> suggestions.

Every test syllabus goes through the real pipeline (read with a model, checked and fixed in code,
suggestions created), several times, and the suggestions are scored against truth.json. Also counts
the "please check this date" flags: a flag on a wrong item is useful, a flag on a right one is noise.

    uv run scripts/eval_syllabus_import.py --model qwen3.5:4b --runs 2               # photos and scans by vision
    uv run scripts/eval_syllabus_import.py --model qwen3.5:4b --ocr glm-ocr:q8_0     # ... or OCR first
"""

import argparse
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openai

from ai import syllabus
from ai.llm import AI_DIR
from ai.schedule import FixtureStore, ToolContext, ToolError

spec = importlib.util.spec_from_file_location("eval_syllabus", Path(__file__).parent / "eval_syllabus.py")
eval_syllabus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_syllabus)
NOW = datetime(2026, 12, 15, 10, 0, tzinfo=ZoneInfo("America/Detroit"))


def as_answer(suggestions: list[dict]) -> tuple[dict, list[dict]]:
    """Suggestions in eval_syllabus's answer format, plus the flagged ones."""
    items, meetings, flagged = [], [], []
    for s in suggestions:
        change = s["proposed_change"]
        if change.get("recurrence_rule"):
            meetings.append({"days": change["days"], "start": change["start"][11:16], "end": change["end"][11:16]})
        else:
            when = change.get("due") or change["start"]  # deadlines are tasks with a due time
            items.append({"title": change["name"], "date": when[:10], "time": when[11:16]})
            if change.get("needs_check"):
                flagged.append(items[-1])
    return {"items": items, "meetings": meetings}, flagged


def report(results: list[dict], truth: dict, label: str, runs: int) -> None:
    """Print the per-category table and the totals."""
    keys = ("items", "found", "made_up", "timed", "right_time", "meetings", "meetings_right", "meetings_made_up",
            "flagged", "useful_flags", "seconds")
    total = {k: sum(r[k] for r in results) for k in keys}
    perfect = lambda r: r["found"] == r["items"] and r["made_up"] == 0 and r["meetings_made_up"] == 0  # noqa: E731
    print(f"\n{'category':<16} {'found':>9} {'made up':>8} {'times':>9} {'classes':>8} {'perfect runs':>13} {'perfect every run':>18}")
    by_category = {}
    for r in results:
        by_category.setdefault(truth[r["file"]].get("category", "-"), []).append(r)
    for category, rs in sorted(by_category.items()):
        files = sorted({r["file"] for r in rs})
        every = sum(all(perfect(r) for r in rs if r["file"] == f) for f in files)
        print(f"{category:<16} {sum(r['found'] for r in rs):>4}/{sum(r['items'] for r in rs):<4} "
              f"{sum(r['made_up'] + r['meetings_made_up'] for r in rs):>8} {sum(r['right_time'] for r in rs):>4}/{sum(r['timed'] for r in rs):<4} "
              f"{sum(r['meetings_right'] for r in rs):>3}/{sum(r['meetings'] for r in rs):<4} "
              f"{sum(perfect(r) for r in rs):>6}/{len(rs):<6} {every:>9}/{len(files)}")
    files = sorted({r["file"] for r in results})
    print(f"\nTOTAL {label}: found {total['found']}/{total['items']} ({total['found'] / total['items']:.1%}), made up "
          f"{total['made_up']} items + {total['meetings_made_up']} classes, times {total['right_time']}/{total['timed']}, "
          f"classes {total['meetings_right']}/{total['meetings']}, perfect imports {sum(map(perfect, results))}/{len(results)}, "
          f"syllabi perfect in every run {sum(all(perfect(r) for r in results if r['file'] == f) for f in files)}/{len(files)}, "
          f"flags {total['flagged']} ({total['useful_flags']} useful), {total['seconds']:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the syllabus import pipeline.")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--ocr", help="an OCR model for scans and photos, e.g. glm-ocr:q8_0")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()

    client = openai.OpenAI(base_url=args.base_url, api_key="ollama", timeout=1800)
    reader = syllabus.Reader.for_server(client, args.model, ocr_model=args.ocr)
    truth = json.loads((eval_syllabus.FIXTURES / "truth.json").read_text())
    label = f"{args.model}{' + ' + args.ocr if args.ocr else ''}"
    results = []
    for name, expected in truth.items():
        if args.only and name not in args.only:
            continue
        for run in range(1, args.runs + 1):
            ctx = ToolContext(store=FixtureStore(), user_id="user-1", now=NOW)
            try:
                summary = syllabus.import_syllabus(ctx, reader, (eval_syllabus.FIXTURES / name).read_bytes(), name)
            except ToolError as error:
                summary = {"error": str(error), "read_as": "?", "seconds": 0, "fixes": [], "left_out": []}
            answer, flagged = as_answer(ctx.store.suggestions("user-1"))
            s = eval_syllabus.score(expected, answer)
            wrong = {f"{g['title']} {g['date']}" for g in answer["items"]} & set(s["extra"])
            useful_flags = sum(1 for f in flagged if f"{f['title']} {f['date']}" in wrong)
            r = {"file": name, "run": run, **s, "answer": answer, "read_as": summary["read_as"], "seconds": summary["seconds"],
                 "flagged": len(flagged), "useful_flags": useful_flags, "fixes": summary["fixes"],
                 "left_out": summary["left_out"], "error": summary.get("error")}
            results.append(r)
            print(f"{name} run {run} ({r['read_as']}): found {s['found']}/{s['items']}, made up {s['made_up']}, "
                  f"times {s['right_time']}/{s['timed']}, classes {s['meetings_right']}/{s['meetings']}, "
                  f"flagged {len(flagged)} ({useful_flags} on wrong items), {r['seconds']}s"
                  + (f"  [{r['error']}]" if r["error"] else ""), flush=True)
            for line in ([f"   missed: {', '.join(s['missed'])}"] if s["missed"] else []) + \
                        ([f"   made up: {', '.join(s['extra'])}"] if s["extra"] else []) + \
                        ([f"   code fixed: {'; '.join(r['fixes'])}"] if r["fixes"] else []):
                print(line[:400])

    report(results, truth, label, args.runs)
    out = AI_DIR / "evals" / f"{datetime.now():%Y-%m-%d-%H%M}-syllabus-import-{label.replace(':', '_').replace('/', '_').replace(' + ', '+')}.json"
    total = {k: sum(r[k] for r in results) for k in ("items", "found", "made_up", "seconds")}
    out.write_text(json.dumps({"label": label, "args": vars(args), "total": total, "results": results}, indent=2, default=str))


if __name__ == "__main__":
    main()
