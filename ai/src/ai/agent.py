"""The agent loop: the model may call tools, one round at a time, until it can answer."""

import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import openai

from ai.llm import EXTRA_SAMPLING, LOG_FILE, SAMPLING, log_call, split_reasoning
from ai.planning import (
    FIND_FREE_SLOTS_TOOL,
    PROPOSE_MOVE_EVENT_TOOL,
    PROPOSE_NEW_EVENT_TOOL,
    find_free_slots,
    propose_move_event,
    propose_new_event,
)
from ai.schedule import GET_SCHEDULE_TOOL, ToolContext, ToolError, describe_now, get_schedule

MAX_ROUNDS = 8  # a plan can need several rounds: look up, find time, then one or more proposals

# Every tool the model may call: its name -> (definition the model sees, function your code runs).
TOOLS = {
    "get_schedule": (GET_SCHEDULE_TOOL, get_schedule),
    "find_free_slots": (FIND_FREE_SLOTS_TOOL, find_free_slots),
    "propose_new_event": (PROPOSE_NEW_EVENT_TOOL, propose_new_event),
    "propose_move_event": (PROPOSE_MOVE_EVENT_TOOL, propose_move_event),
}

SYSTEM_PROMPT = """You are Steady, a planning assistant for a student.
Current date and time: {now}.

Rules:
- Before answering anything about the user's schedule, look it up with get_schedule. Never guess.
- To find time for something, use find_free_slots. Don't work out free time yourself.
- You can't change the calendar. propose_new_event and propose_move_event only create suggestions
  that the user accepts or declines, so say "I suggest", never "I added" or "I moved".
- When you recommend a time for something, create it with propose_new_event or propose_move_event
  so the user can accept it. Don't only describe it.
- If there isn't enough free time, consider moving an event marked changeable: true, or splitting
  the work into smaller blocks.
- Count what is already on the calendar toward the user's goals (for example, an existing study
  session counts toward "study 4 hours this week").
- If a tool returns an error, fix the request and try again.
- If the request is unclear (for example, which of several events it means), ask instead of guessing.
- Never suggest a time that is already over.
- Answer in at most 5 short sentences or bullet points. No tables, no emojis.
- Don't invent facts or statistics."""

# A recommended time in an answer, like "7 PM", "7:30 pm" or "19:00".
TIME_PATTERN = re.compile(r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b|\b\d{1,2}:\d{2}\b", re.IGNORECASE)

NUDGE = (
    "You recommended times but didn't create any suggestions, so the user has nothing to accept. "
    "Create them now with propose_new_event or propose_move_event, then give your final answer."
)


def run_tool(ctx: ToolContext, name: str, arguments_json: str) -> str:
    """Run one tool call from the model and return the text to send back to it.

    Mistakes the model can fix become an "Error: ..." message it can read.
    Anything else is a bug in our code, so it is allowed to crash.
    """
    if name not in TOOLS:
        return f"Error: there is no tool called {name!r}. Available: {', '.join(TOOLS)}."
    definition, function = TOOLS[name]

    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return "Error: the arguments were not valid JSON."
    if not isinstance(arguments, dict):
        return "Error: the arguments must be a JSON object."

    allowed = definition["function"]["parameters"]["properties"]
    required = definition["function"]["parameters"].get("required", [])
    unknown = [a for a in arguments if a not in allowed]
    missing = [a for a in required if a not in arguments]
    if unknown or missing:
        return f"Error: {name} takes {', '.join(allowed)}. Unknown: {unknown or 'none'}. Missing: {missing or 'none'}."

    try:
        result = function(ctx, **arguments)
    except ToolError as error:
        return f"Error: {error}"
    return json.dumps(result, ensure_ascii=False)


def run_agent(
    client: openai.OpenAI,
    model: str,
    ctx: ToolContext,
    question: str,
    verbose: bool = True,
    log_path: Path = LOG_FILE,
    history: list[dict] | None = None,
) -> dict:
    """Answer one question, letting the model call tools first. Logs every round to `log_path`.

    `history` holds earlier turns of the chat as {"role": "user" | "assistant", "content": ...},
    final answers only (no thinking), as Qwen recommends.
    """
    run_id = uuid.uuid4().hex[:8]  # groups this question's rounds in the log
    total_tokens, total_seconds = 0, 0.0  # for measuring speed in evals
    searched_free_time, proposals, nudged = False, 0, False  # for the reminder below
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(now=describe_now(ctx.now))},
        *(history or []),
        {"role": "user", "content": question},
    ]

    for round_number in range(1, MAX_ROUNDS + 1):
        request = {
            "model": model,
            "messages": messages,
            "tools": [definition for definition, _ in TOOLS.values()],
            **SAMPLING,
            "max_tokens": 8192,
            "extra_body": EXTRA_SAMPLING,
        }
        start = time.perf_counter()
        response = client.chat.completions.create(**request)
        seconds = round(time.perf_counter() - start, 2)
        total_tokens += response.usage.completion_tokens if response.usage else 0
        total_seconds += seconds

        message = response.choices[0].message
        reasoning, answer = split_reasoning(message.model_dump())
        tool_calls = [call.model_dump() for call in message.tool_calls or []]
        log_call(
            {
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "run_id": run_id,
                "round": round_number,
                "base_url": str(client.base_url),
                "request": request,
                "reasoning": reasoning,
                "answer": answer,
                "tool_calls": tool_calls,
                "finish_reason": response.choices[0].finish_reason,
                "usage": response.usage.model_dump() if response.usage else None,
                "seconds": seconds,
            },
            log_path,
        )

        if not tool_calls:  # no tool requested: this is the final answer
            # Small models often describe a plan instead of proposing it. Remind them once, in code.
            if searched_free_time and not proposals and not nudged and TIME_PATTERN.search(answer):
                nudged = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "system", "content": NUDGE})
                if verbose:
                    print(f"round {round_number}: answered with times but no proposals; reminding the model")
                continue
            if verbose:
                print(f"round {round_number}: answered ({seconds}s)")
            return {
                "answer": answer,
                "reasoning": reasoning,
                "rounds": round_number,
                "messages": messages,
                "run_id": run_id,
                "tokens": total_tokens,
                "seconds": round(total_seconds, 1),
                "nudged": nudged,
            }

        # Send the tool call back as part of the conversation, with its thinking.
        messages.append({"role": "assistant", "content": answer, "reasoning_content": reasoning, "tool_calls": tool_calls})
        for call in tool_calls:
            name, arguments = call["function"]["name"], call["function"]["arguments"]
            result = run_tool(ctx, name, arguments)
            if name == "find_free_slots":
                searched_free_time = True
            if name.startswith("propose_") and not result.startswith("Error"):
                proposals += 1
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            if verbose:
                print(f"round {round_number}: {name}({arguments}) ({seconds}s) -> {result[:100]}...")

    return {
        "answer": "Sorry, I couldn't finish that. Could you ask in a simpler way?",
        "reasoning": "",
        "rounds": MAX_ROUNDS,
        "messages": messages,
        "run_id": run_id,
        "tokens": total_tokens,
        "seconds": round(total_seconds, 1),
        "nudged": nudged,
    }
