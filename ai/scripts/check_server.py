"""Check that a model server works with the planner. Run it right after deploying (e.g. on RunPod).

It sends one real tool-calling request and checks what has to be right:
  1. the model is served under the name in LLM_MODEL,
  2. the model's thinking comes back separately (vLLM: --reasoning-parser),
  3. a tool call comes back as a structured tool call, not as <tool_call> text (vLLM: --tool-call-parser),
  4. and it reports the speed.

Examples (run from the ai/ folder):
    uv run scripts/check_server.py                    # the server in .env
    uv run scripts/check_server.py --no-thinking      # for an Instruct model
"""

import argparse
import json
import sys
import time

import openai

from ai.llm import EXTRA_SAMPLING, SAMPLING, load_settings, make_client, split_reasoning
from ai.schedule import GET_SCHEDULE_TOOL

HINTS = {
    "model": "Set LLM_MODEL to one of the served names (vLLM: --served-model-name; RunPod Serverless: "
    "OPENAI_SERVED_MODEL_NAME_OVERRIDE or MODEL_NAME).",
    "thinking": "Start vLLM with --reasoning-parser deepseek_r1 (RunPod Serverless: REASONING_PARSER=deepseek_r1).",
    "tools": "Start vLLM with --enable-auto-tool-choice --tool-call-parser hermes "
    "(RunPod Serverless: ENABLE_AUTO_TOOL_CHOICE=true and TOOL_CALL_PARSER=hermes).",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a model server.")
    parser.add_argument("--no-thinking", action="store_true", help="the model doesn't think (e.g. Instruct)")
    args = parser.parse_args()

    settings = load_settings()
    client = make_client(settings)
    print(f"Server: {settings.base_url}\nModel:  {settings.model}\n")
    problems = []

    try:
        served = [m.id for m in client.models.list()]
    except openai.APIConnectionError:
        raise SystemExit("Can't reach the server. Is it running, and is LLM_BASE_URL right?") from None
    except openai.AuthenticationError:
        raise SystemExit("The server refused the API key. Check LLM_API_KEY.") from None
    if settings.model in served:
        print(f"PASS  model is served ({len(served)} model(s) available)")
    else:
        print(f"FAIL  {settings.model!r} isn't served. Available: {served}")
        problems.append("model")

    start = time.perf_counter()
    response = client.chat.completions.create(
        model=settings.model,
        messages=[
            {"role": "system", "content": "Current date and time: Monday, October 5, 2026, 6:30 PM (America/Detroit)."},
            {"role": "user", "content": "What do I have tomorrow?"},
        ],
        tools=[GET_SCHEDULE_TOOL],
        **SAMPLING,
        max_tokens=4096,
        extra_body=EXTRA_SAMPLING,
    )
    seconds = time.perf_counter() - start
    message = response.choices[0].message
    reasoning, answer = split_reasoning(message.model_dump())
    raw_content = message.content or ""

    if args.no_thinking:
        print("SKIP  thinking check (--no-thinking)")
    elif reasoning and "</think>" not in raw_content:
        print(f"PASS  thinking comes back separately ({len(reasoning)} characters)")
    else:
        print("FAIL  thinking is missing or mixed into the answer text")
        problems.append("thinking")

    calls = message.tool_calls or []
    if calls and calls[0].function.name == "get_schedule" and "<tool_call>" not in raw_content:
        arguments = json.loads(calls[0].function.arguments)
        print(f"PASS  tool call is structured: get_schedule({arguments})")
    else:
        print(f"FAIL  no structured tool call (finish_reason={response.choices[0].finish_reason}, "
              f"content starts {raw_content[:80]!r})")
        problems.append("tools")

    tokens = response.usage.completion_tokens if response.usage else 0
    print(f"INFO  {tokens} tokens in {seconds:.1f} s = {tokens / seconds:.1f} tokens/s (includes model loading if it was cold)")

    for problem in problems:
        print(f"\nHow to fix '{problem}': {HINTS[problem]}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
