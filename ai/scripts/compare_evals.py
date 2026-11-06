"""Compare two eval results files case by case: is B really better than A, or is it luck?

Same cases, two models or two versions. A case counts as "right" if it passed most of its runs. Cases
that changed are counted both ways (fixed vs broken), and an exact sign test says how likely a
difference that big would be by chance alone. Rule of thumb: adopt B only if p < 0.05 and nothing
important broke.

    uv run scripts/compare_evals.py evals/<A>.jsonl evals/<B>.jsonl
"""

import argparse
import json
from collections import defaultdict
from math import comb
from pathlib import Path


def load(path: Path) -> dict[str, list[bool]]:
    runs = defaultdict(list)
    for line in path.read_text().splitlines():
        r = json.loads(line)
        runs[r["scenario"]].append(r["passed"])
    return runs


def sign_test(fixed: int, broken: int) -> float:
    """Two-sided exact p-value: chance of a split at least this uneven if A and B were equally good."""
    n = fixed + broken
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(fixed, broken) + 1)) / 2**n
    return min(1.0, 2 * tail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval results files.")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args()

    a, b = load(args.a), load(args.b)
    shared = sorted(set(a) & set(b))
    if not shared:
        raise SystemExit("The files have no cases in common.")
    right = lambda runs: sum(runs) > len(runs) / 2  # noqa: E731
    fixed = [c for c in shared if not right(a[c]) and right(b[c])]
    broken = [c for c in shared if right(a[c]) and not right(b[c])]
    rate = lambda d: sum(sum(d[c]) for c in shared) / sum(len(d[c]) for c in shared)  # noqa: E731

    print(f"{len(shared)} cases in both. Pass rate over all runs: A {rate(a):.0%}, B {rate(b):.0%}")
    print(f"Right in most runs: A {sum(right(a[c]) for c in shared)}, B {sum(right(b[c]) for c in shared)}")
    print(f"B fixed {len(fixed)}: {', '.join(fixed) or '-'}")
    print(f"B broke {len(broken)}: {', '.join(broken) or '-'}")
    p = sign_test(len(fixed), len(broken))
    print(f"Chance of a difference at least this big by luck: p = {p:.3f} -> "
          + ("a real difference" if p < 0.05 else "not enough evidence; could be luck"))


if __name__ == "__main__":
    main()
