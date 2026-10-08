"""Stage 0: ask the model a question, show its thinking live, and measure it.

Examples (run from the ai/ folder):
    uv run scripts/stage0_chat.py "I have class 10am-12pm. When should I study?"
    uv run scripts/stage0_chat.py "What's the date tomorrow?" --no-date
    uv run scripts/stage0_chat.py "Plan my evening" --runs 5
    uv run scripts/stage0_chat.py "Plan my evening" --model qwen3:4b-instruct-2507-q8_0
"""

import argparse
import sys
import time
from datetime import UTC, datetime

import openai

from ai.llm import (
    EXTRA_SAMPLING,
    SAMPLING,
    current_time_text,
    load_settings,
    log_call,
    make_client,
    split_reasoning,
)

TIMEZONE = "America/Detroit"  # later this comes from the user's profile
GREY, RESET = "\033[2m", "\033[0m"  # terminal codes: dim text on, back to normal

def build_messages(question: str, include_date: bool) -> list[dict]:
    messages = []
    if include_date:
        messages.append({"role": "system", "content": f"Current date and time: {current_time_text(TIMEZONE)}."})
    messages.append({"role": "user", "content": question})
    return messages

def stream_answer(client: openai.OpenAI, request: dict) -> dict:
    """Send one request, print the thinking and answer as they arrive, and time it."""
    start = time.perf_counter()
    first_token = first_answer_token = None
    thinking_parts, answer_parts = [], []
    finish_reason = usage = None
    section = None  # the header printed last: "thinking" or "answer"

    stream = client.chat.completions.create(**request, stream=True, stream_options={"include_usage": True})
    for chunk in stream:
        if chunk.usage:  # the last chunk carries the token counts
            usage = chunk.usage.model_dump()
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        finish_reason = choice.finish_reason or finish_reason
        delta = choice.delta

        # Servers that separate the thinking send it in an extra field on each chunk.
        thinking = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
        if thinking:
            first_token = first_token or time.perf_counter()
            if section != "thinking":
                print(f"{GREY}── thinking ──")
                section = "thinking"
            print(thinking, end="", flush=True)
            thinking_parts.append(thinking)

        if delta.content:
            now = time.perf_counter()
            first_token = first_token or now
            first_answer_token = first_answer_token or now
            if section != "answer":
                print(f"{RESET}\n\n── answer ──")
                section = "answer"
            print(delta.content, end="", flush=True)
            answer_parts.append(delta.content)

    end = time.perf_counter()
    print(RESET)

    # The same function used for non-streamed replies, so <think> tags in the content are handled too.
    reasoning, answer = split_reasoning({"reasoning": "".join(thinking_parts), "content": "".join(answer_parts)})

    def seconds_since_start(moment: float | None) -> float | None:
        return round(moment - start, 2) if moment else None

    completion_tokens = (usage or {}).get("completion_tokens") or 0
    generating_seconds = end - (first_token or start)
    return {
        "reasoning": reasoning,
        "answer": answer,
        "finish_reason": finish_reason,
        "usage": usage,
        # Each streamed chunk is about one token, so the chunk counts show
        # how completion_tokens splits into thinking and answer.
        "thinking_chunks": len(thinking_parts),
        "answer_chunks": len(answer_parts),
        "seconds": {
            "first_token": seconds_since_start(first_token),
            "first_answer_token": seconds_since_start(first_answer_token),
            "total": seconds_since_start(end),
        },
        "tokens_per_second": round(completion_tokens / generating_seconds, 1) if generating_seconds else None,
    }

def print_stats(result: dict) -> None:
    usage = result["usage"] or {}
    seconds = result["seconds"]
    print(
        f"tokens: prompt {usage.get('prompt_tokens')}, completion {usage.get('completion_tokens')} "
        f"(~{result['thinking_chunks']} thinking + ~{result['answer_chunks']} answer)\n"
        f"time: first token {seconds['first_token']}s, answer starts {seconds['first_answer_token']}s, "
        f"total {seconds['total']}s ({result['tokens_per_second']} tokens/s)\n"
        f"finish_reason: {result['finish_reason']}"
    )

def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the model a question and measure the reply.")
    parser.add_argument("question")
    parser.add_argument("--no-date", action="store_true", help="leave the current date/time out of the prompt")
    parser.add_argument("--model", help="use this model instead of LLM_MODEL from .env")
    parser.add_argument("--runs", type=int, default=1, help="ask the same question this many times")
    parser.add_argument("--max-tokens", type=int, default=8192)
    args = parser.parse_args()

    settings = load_settings()
    client = make_client(settings)

    for run in range(1, args.runs + 1):
        if args.runs > 1:
            print(f"\n===== run {run} of {args.runs} =====")
        # Built inside the loop so every run gets the current time.
        request = {
            "model": args.model or settings.model,
            "messages": build_messages(args.question, not args.no_date),
            **SAMPLING,
            "max_tokens": args.max_tokens,
            "extra_body": EXTRA_SAMPLING,
        }
        try:
            result = stream_answer(client, request)
        except openai.APIConnectionError:
            sys.exit(f"Can't reach {settings.base_url}. Is `ollama serve` running?")

        print_stats(result)
        log_call(
            {
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "base_url": settings.base_url,  # never the API key
                "request": request,
                **result,
            }
        )


if __name__ == "__main__":
    main()
