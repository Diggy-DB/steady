"""The agent loop: the model may call tools, one round at a time, until it can answer."""

import json
import time
import uuid
from datetime import UTC, datetime

import openai

from ai.llm import EXTRA_SAMPLING, SAMPLING, log_call, split_reasoning
from ai.schedule import GET_SCHEDULE_TOOL, ToolContext, ToolError, describe_now, get_schedule

MAX_ROUNDS = 5

# Every tool the model may call: its name -> (definition the model sees, function your code runs).
TOOLS = {"get_schedule": (GET_SCHEDULE_TOOL, get_schedule)}

SYSTEM_PROMPT = """You are Steady, a planning assistant for a student.
Current date and time: {now}.

Rules:
- Before answering anything about the user's schedule, look it up with get_schedule. Never guess.
- Never suggest a time that is already over.
- Answer in at most 5 short sentences or bullet points. No tables, no emojis.
- Don't invent facts or statistics."""


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


def run_agent(client: openai.OpenAI, model: str, ctx: ToolContext, question: str, verbose: bool = True) -> dict:
    """Answer one question, letting the model call tools first. Logs every round."""
    run_id = uuid.uuid4().hex[:8]  # groups this question's rounds in the log
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(now=describe_now(ctx.now))},
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
            }
        )

        if not tool_calls:  # no tool requested: this is the final answer
            if verbose:
                print(f"round {round_number}: answered ({seconds}s)")
            return {"answer": answer, "rounds": round_number, "messages": messages, "run_id": run_id}

        # Send the tool call back as part of the conversation, with its thinking.
        messages.append({"role": "assistant", "content": answer, "reasoning_content": reasoning, "tool_calls": tool_calls})
        for call in tool_calls:
            name, arguments = call["function"]["name"], call["function"]["arguments"]
            result = run_tool(ctx, name, arguments)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            if verbose:
                print(f"round {round_number}: {name}({arguments}) ({seconds}s) -> {result[:100]}...")

    return {
        "answer": "Sorry, I couldn't finish that. Could you ask in a simpler way?",
        "rounds": MAX_ROUNDS,
        "messages": messages,
        "run_id": run_id,
    }
