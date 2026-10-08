"""Stage 1: ask a question; the model can look up the schedule before answering.

The time is fake and fixed (default: Monday Oct 5, 2026, 6:30 PM), so runs
can be compared with each other.

Examples (run from the ai/ folder):
    uv run scripts/stage1_chat.py "What do I have tomorrow?"
    uv run scripts/stage1_chat.py "When should I work on my MTH 133 problem set?" --now "2026-10-07 18:30"
"""

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from ai.agent import run_agent
from ai.llm import load_settings, make_client
from ai.schedule import FixtureStore, ToolContext


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the planning assistant a question.")
    parser.add_argument("question")
    parser.add_argument("--now", default="2026-10-05 18:30", help="fake local time, YYYY-MM-DD HH:MM")
    parser.add_argument("--user", default="user-1")
    parser.add_argument("--model", help="use this model instead of LLM_MODEL from .env")
    args = parser.parse_args()

    settings = load_settings()
    store = FixtureStore()
    timezone = ZoneInfo(store.user(args.user)["timezone"])
    now = datetime.fromisoformat(args.now).replace(tzinfo=timezone)
    ctx = ToolContext(store=store, user_id=args.user, now=now)

    result = run_agent(make_client(settings), args.model or settings.model, ctx, args.question)
    print(f"\n{result['answer']}\n\n(run {result['run_id']}, {result['rounds']} rounds, logged to logs/calls.jsonl)")


if __name__ == "__main__":
    main()
