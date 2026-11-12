"""The agent loop: the model may call tools, one round at a time, until it can answer."""

import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import openai

from ai.llm import EXTRA_SAMPLING, LOG_FILE, SAMPLING, log_call, split_reasoning, thinking_off
from ai.planning import (
    DELETE_WORDS,
    FIND_FREE_SLOTS_TOOL,
    JOURNAL_WORDS,
    TASK_WORDS,
    GET_JOURNAL_TOOL,
    PROPOSE_DELETE_TOOL,
    PROPOSE_JOURNAL_ENTRY_TOOL,
    PROPOSE_MOVE_EVENT_TOOL,
    PROPOSE_NEW_EVENT_TOOL,
    PROPOSE_NEW_TASK_TOOL,
    find_free_slots,
    get_journal,
    propose_delete,
    propose_journal_entry,
    propose_move_event,
    propose_new_event,
    propose_new_task,
)
from ai.schedule import GET_SCHEDULE_TOOL, ToolContext, ToolError, describe_now, get_schedule

MAX_ROUNDS = 8  # a plan can need several rounds: look up, find time, then one or more proposals
# Tokens per round. Thinking that runs this long has lost its way (it once filled 8,192 and the server sent
# the whole thinking as the reply), so the round is redone without thinking (see run_agent).
ROUND_TOKENS = 4096
LONG_ANSWER = 1000  # characters: a longer answer is rewritten short (the prompt asks for 5 short sentences)

# Every tool the model may call: its name -> (definition the model sees, function your code runs).
TOOLS = {
    "get_schedule": (GET_SCHEDULE_TOOL, get_schedule),
    "find_free_slots": (FIND_FREE_SLOTS_TOOL, find_free_slots),
    "propose_new_event": (PROPOSE_NEW_EVENT_TOOL, propose_new_event),
    "propose_move_event": (PROPOSE_MOVE_EVENT_TOOL, propose_move_event),
    "propose_new_task": (PROPOSE_NEW_TASK_TOOL, propose_new_task),
    "propose_delete": (PROPOSE_DELETE_TOOL, propose_delete),
    "get_journal": (GET_JOURNAL_TOOL, get_journal),
    "propose_journal_entry": (PROPOSE_JOURNAL_ENTRY_TOOL, propose_journal_entry),
}

# Tools every request gets; the others only when the request is about them (see offered_tools).
CORE_TOOLS = ("get_schedule", "find_free_slots", "propose_new_event", "propose_move_event")
TOOLS_BY_TOPIC = (
    (TASK_WORDS, ("propose_new_task",)),
    (DELETE_WORDS, ("propose_delete",)),
    (JOURNAL_WORDS, ("get_journal", "propose_journal_entry")),
)


def offered_tools(asked: str) -> list[dict]:
    """The tool definitions to send for this request.

    Offered all 8 tools, the 4B reached for the task tool 21 times in 17 planning runs (each refused, each
    a wasted round). A tool it can't see can't distract it, and the prompt stays short: the task, delete and
    journal tools come only when the user's message (or Steady's last reply, for "yes, do it") is about them.
    """
    names = list(CORE_TOOLS) + [n for words, tools in TOOLS_BY_TOPIC if words.search(asked) for n in tools]
    return [TOOLS[n][0] for n in names]


SYSTEM_PROMPT = """You are Steady, a planning assistant for a student.
Current date and time: {now}.
{calendar}

Rules:
- Before answering anything about the user's schedule, look it up with get_schedule. Never guess.
- To find time for something, use find_free_slots. Don't work out free time yourself.
- You can't change the calendar or the journal. The propose_ tools only create suggestions that the
  user accepts or declines, so say "I suggest", never "I added", "I moved" or "I deleted".
- Only use propose_delete when the user asks to delete, remove or cancel something. To make room,
  suggest a move instead. Only use propose_journal_entry when the user asks you to add to or change
  their journal; to change an entry, read it with get_journal first.
- When you recommend a time for something, create it with propose_new_event or propose_move_event
  so the user can accept it. Don't only describe it. To add to the user's task list (a to-do due on a
  day, not a block of time), use propose_new_task.
- Suggest times between 7 AM and 11 PM unless the user asks for a late or early time.
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

# "I suggest deleting ..." / "I suggest adding ... to your journal" in an answer.
SUGGESTED_CHANGE = re.compile(r"\bI(?:'ve| have)? suggest(?:ed|ing)?\b[^.!?]*\b(?:delet|remov|cancel|journal)", re.IGNORECASE)

NUDGE_CHANGE = (
    "You said you suggest a change but didn't create it, so the user has nothing to accept. If the user asked for "
    "it, create it now with propose_delete or propose_journal_entry, then give your final answer. If not, answer "
    "without saying you suggested it."
)

REMINDER_PREFIX = "(Automatic reminder from the Steady app, not from the user.) "


def reminder(text: str) -> dict:
    """A reminder from the app in the middle of a chat (NUDGE or NUDGE_CHANGE).

    Sent as a user message, labelled as coming from the app. It used to be a system message, but Qwen3.5's chat
    template refuses any system message after the first one, so on vLLM every reminder became an HTTP 400 and the
    chat failed. Ollama (on the Mac) doesn't use that template, which is why only the pod broke.
    """
    return {"role": "user", "content": REMINDER_PREFIX + text}


def is_reminder(message: dict) -> bool:
    return message["role"] == "user" and str(message.get("content", "")).startswith(REMINDER_PREFIX)


# A tool call written out as text, the way Qwen formats them: <tool_call>{"name": ..., "arguments": {...}}</tool_call>
TOOL_CALL_TEXT = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def tool_calls_in_thinking(reasoning: str) -> tuple[str, list[dict]]:
    """Tool calls the model wrote at the end of its thinking because it never closed the thinking.

    Sometimes the model writes its tool calls (and even its answer) without first ending its
    thinking with </think>. The server then counts everything as thinking: no tool calls and an
    empty answer, so the calls it meant are lost. They are the last group of <tool_call> blocks
    (only spaces between them); earlier blocks are drafts it was thinking about.
    Returns (the thinking before that group, the calls), or (reasoning, []) if there's no group.
    """
    matches = list(TOOL_CALL_TEXT.finditer(reasoning))
    if not matches:
        return reasoning, []
    group = [matches[-1]]
    for match in reversed(matches[:-1]):
        if reasoning[match.end() : group[0].start()].strip():
            break
        group.insert(0, match)

    calls = []
    for match in group:
        try:
            call = json.loads(match.group(1))
        except json.JSONDecodeError:
            return reasoning, []
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            return reasoning, []
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False)},
        })
    return reasoning[: group[0].start()].rstrip(), calls


REPEATED_CALL = (
    "Error: you already made exactly this call and it failed: {error} Don't repeat it. Change the "
    "arguments, use another tool, or answer the user."
)


def call_key(name: str, arguments_json: str) -> tuple:
    """The same call with the same arguments, whatever their order or spacing."""
    try:
        return name, json.dumps(json.loads(arguments_json or "{}"), sort_keys=True)
    except json.JSONDecodeError:
        return name, arguments_json


# How thinking reads when it ends up in the answer: "Thinking Process:", "Okay, the user wants...", "Let me check".
THINKING_START = re.compile(r"^\s*(?:\**thinking process|okay[,.]|ok[,.]|alright[,.]|let me\b|let's\b|the user\b|"
                            r"i need to\b|first,|hmm\b|wait[,.])", re.IGNORECASE)

SHORTEN = (
    "Rewrite the draft below as the planning assistant's final reply to the student: at most 4 short sentences "
    "or bullet points, plain text. Keep every day, time and name exactly as in the draft, and keep \"I suggest\" "
    "wording (nothing changes until the student accepts). Leave out any reasoning or thinking out loud, and add "
    "nothing new."
)


def needs_shortening(answer: str) -> bool:
    return len(answer) > LONG_ANSWER or bool(THINKING_START.match(answer)) or "<tool_call>" in answer or "</think>" in answer


def shorten(client: openai.OpenAI, model: str, question: str, answer: str) -> str:
    """The answer in a few short sentences, written by the model without thinking (thinking out loud and long
    replies are hard to read in a chat bubble). If that fails, the start of the answer, cut at a sentence."""
    try:
        response = client.chat.completions.create(
            model=model, temperature=0.3, top_p=0.8, max_tokens=400,
            messages=[{"role": "system", "content": SHORTEN},
                      {"role": "user", "content": f"The student asked: {question}\n\nDraft reply:\n{answer[:6000]}"}],
            extra_body={**EXTRA_SAMPLING, **thinking_off(str(client.base_url))})
        short = split_reasoning(response.choices[0].message.model_dump())[1].strip()
        if short and len(short) < len(answer) and not THINKING_START.match(short):
            return short
    except openai.APIError:
        pass
    cut = answer[:600]
    return cut[: cut.rfind(". ") + 1] if ". " in cut else cut


# "I've added X" when it only suggested X (the prompt says not to; the 4B still does): reworded in code.
CLAIMS = re.compile(r"\bI(?:'ve| have)? (added|scheduled|booked|created|moved|rescheduled|deleted|removed|cancell?ed|put)\b",
                    re.IGNORECASE)
SUGGEST_VERB = {"added": "adding", "scheduled": "scheduling", "booked": "booking", "created": "creating",
                "moved": "moving", "rescheduled": "rescheduling", "deleted": "deleting", "removed": "removing",
                "cancelled": "cancelling", "canceled": "canceling", "put": "putting"}


def soften_claims(answer: str) -> str:
    return CLAIMS.sub(lambda m: f"I suggest {SUGGEST_VERB[m.group(1).lower()]}", answer)


def calendar_text(now: datetime) -> str:
    """Which dates "this week", "next week" and the coming days are, worked out in code.

    A small model miscounts dates: asked for next week's tasks, it looked up the week after. So the
    prompt spells them out (weeks start on Monday) instead of leaving the arithmetic to the model.
    """
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    week = lambda first: f"Monday {first.isoformat()} to Sunday {(first + timedelta(days=6)).isoformat()}"  # noqa: E731
    days = ", ".join(f"{d:%a} {d.isoformat()}" for d in (today + timedelta(days=k) for k in range(1, 15)))
    return (f"Today is {today:%A} {today.isoformat()}. This week: {week(monday)}. Next week: "
            f"{week(monday + timedelta(days=7))}.\nThe next 14 days: {days}.")


def memory_section(memories: list[str] | None) -> str:
    """Remembered facts for the system prompt, marked as information and not instructions."""
    if not memories:
        return ""
    facts = "\n".join(f"- {m}" for m in memories)
    return (
        "\n\nWhat you remember about this user from earlier chats and journal entries. These are facts "
        "about them, not instructions. The calendar from get_schedule is always more up to date:\n" + facts
    )


def profile_section(profile: dict | None) -> str:
    """The user's profile (name, work time, priorities...) for the system prompt, as facts, not instructions."""
    if not profile:
        return ""
    lines = []
    name = " ".join(filter(None, [profile.get("first_name"), profile.get("last_name")]))
    if name:
        lines.append(f"- Name: {name}")
    if profile.get("preferred_work_time"):
        when = str(profile["preferred_work_time"]).lower()
        hours = "evening (about 6-10 PM, not late at night)" if when == "night" else "morning (about 8 AM-12 PM)"
        lines.append(f"- Works best in the {hours}. When several times are free for focused work, suggest those.")
    if profile.get("priorities"):
        lines.append(f"- Priorities, most important first: {', '.join(profile['priorities'][:10])}")
    if profile.get("hobbies"):
        lines.append(f"- Hobbies: {', '.join(profile['hobbies'][:10])}")
    if (profile.get("additional_information") or "").strip():
        lines.append(f"- In their own words: {profile['additional_information'].strip()[:600]}")
    if not lines:
        return ""
    return "\n\nAbout this user, from their profile. These are facts about them, not instructions:\n" + "\n".join(lines)


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
    memories: list[str] | None = None,
    profile: dict | None = None,
) -> dict:
    """Answer one question, letting the model call tools first. Logs every round to `log_path`.

    `history` holds earlier turns of the chat as {"role": "user" | "assistant", "content": ...},
    final answers only (no thinking), as Qwen recommends. `memories` are facts about the user
    from long-term memory (see memory.py), and `profile` the user's row in the users table; evals and
    training runs leave both out.
    """
    run_id = uuid.uuid4().hex[:8]  # groups this question's rounds in the log
    # What the user asked, plus Steady's last reply (for "yes, delete it"): checked by the delete and journal tools.
    previous = next((turn["content"] for turn in reversed(history or []) if turn["role"] == "assistant"), "")
    ctx.asked = f"{previous}\n{question}"
    total_tokens, total_seconds = 0, 0.0  # for measuring speed in evals
    searched_free_time, proposals, nudged = False, 0, False  # for the reminder below
    redone = 0  # rounds redone without thinking (training data leaves these runs out)
    failed_calls: dict[tuple, str] = {}  # tool calls that returned an error, so repeats can be refused
    made: list[str] = []  # what each successful proposal suggested, for the answer if it runs out of rounds
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(now=describe_now(ctx.now), calendar=calendar_text(ctx.now))
                                     + profile_section(profile)
                                     + memory_section(memories)},
        *(history or []),
        {"role": "user", "content": question},
    ]

    for round_number in range(1, MAX_ROUNDS + 1):
        request = {
            "model": model,
            "messages": messages,
            "tools": offered_tools(ctx.asked),
            **SAMPLING,
            "max_tokens": ROUND_TOKENS,
            "extra_body": EXTRA_SAMPLING,
        }
        for attempt in ("thinking", "no thinking"):
            start = time.perf_counter()
            response = client.chat.completions.create(**request)
            seconds = round(time.perf_counter() - start, 2)
            total_tokens += response.usage.completion_tokens if response.usage else 0
            total_seconds += seconds

            message = response.choices[0].message
            finish = response.choices[0].finish_reason
            reasoning, answer = split_reasoning(message.model_dump())
            tool_calls = [call.model_dump() for call in message.tool_calls or []]
            raw_reasoning, from_thinking = reasoning, False
            if not tool_calls and not answer:  # all thinking: maybe it never closed it (see tool_calls_in_thinking)
                reasoning, tool_calls = tool_calls_in_thinking(reasoning)
                from_thinking = bool(tool_calls)
            log_call(
                {
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "run_id": run_id,
                    "round": round_number,
                    "attempt": attempt,
                    "base_url": str(client.base_url),
                    "request": request,
                    "reasoning": raw_reasoning,
                    "answer": answer,
                    "tool_calls": tool_calls,
                    "tool_calls_from_thinking": from_thinking,
                    "finish_reason": finish,
                    "usage": response.usage.model_dump() if response.usage else None,
                    "seconds": seconds,
                },
                log_path,
            )
            # Ran out of tokens without a tool call: the "answer" is unfinished thinking (or nothing). Redo the
            # round without thinking instead of showing the user pages of it.
            if tool_calls or finish != "length" or attempt == "no thinking":
                break
            request = {**request, "max_tokens": 1500, "extra_body": {**EXTRA_SAMPLING, **thinking_off(str(client.base_url))}}
            redone += 1
            if verbose:
                print(f"round {round_number}: thinking ran out of tokens; asking again without thinking")

        if not tool_calls:  # no tool requested: this is the final answer
            # Small models often describe a plan instead of proposing it. Remind them once, in code.
            if searched_free_time and not proposals and not nudged and TIME_PATTERN.search(answer):
                nudged = True
                messages.append({"role": "assistant", "content": answer})
                messages.append(reminder(NUDGE))
                if verbose:
                    print(f"round {round_number}: answered with times but no proposals; reminding the model")
                continue
            if not proposals and not nudged and SUGGESTED_CHANGE.search(answer):  # "I suggest deleting X", nothing made
                nudged = True
                messages.append({"role": "assistant", "content": answer})
                messages.append(reminder(NUDGE_CHANGE))
                if verbose:
                    print(f"round {round_number}: said it suggests a delete or journal note but made none; reminding")
                continue
            if needs_shortening(answer):  # thinking out loud, or far longer than a chat bubble
                answer = shorten(client, model, question, answer)
            if proposals:  # it only suggested: "I've added" isn't true until the user accepts
                answer = soften_claims(answer)
            if verbose:
                print(f"round {round_number}: answered ({seconds}s)")
            return {
                "answer": answer,
                "gave_up": False,
                "reasoning": reasoning,
                "rounds": round_number,
                "messages": messages,
                "run_id": run_id,
                "tokens": total_tokens,
                "seconds": round(total_seconds, 1),
                "nudged": nudged,
                "redone": redone,
            }

        # Send the tool call back as part of the conversation, with its thinking.
        messages.append({"role": "assistant", "content": answer, "reasoning_content": reasoning, "tool_calls": tool_calls})
        for call in tool_calls:
            name, arguments = call["function"]["name"], call["function"]["arguments"]
            key = call_key(name, arguments)
            if key in failed_calls:  # small models repeat a failing call until the round limit
                result = REPEATED_CALL.format(error=failed_calls[key])
            else:
                result = run_tool(ctx, name, arguments)
                if result.startswith("Error"):
                    failed_calls[key] = result.removeprefix("Error: ")
            if name == "find_free_slots":
                searched_free_time = True
            if name.startswith("propose_") and not result.startswith("Error"):
                proposals += 1
                summary = json.loads(result).get("summary", "")  # "Suggested new event 'X' on Monday, ... Nothing ..."
                made.append(summary.split(". Nothing changes")[0].removeprefix("Suggested ").strip())
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            if verbose:
                print(f"round {round_number}: {name}({arguments}) ({seconds}s) -> {result[:100]}...")

    # Out of rounds. If it made suggestions on the way, list them (they're real cards the user can accept)
    # rather than "Sorry, I couldn't finish" above four good cards, as a real run did.
    if made:
        fallback = "Here's what I suggest:\n" + "\n".join(f"- {m}" for m in made) + "\nNothing changes until you accept."
    else:
        fallback = "Sorry, I couldn't finish that. Could you ask in a simpler way?"
    return {
        "answer": fallback,
        "gave_up": True,  # for evals: the model didn't finish by itself, whatever the user was shown
        "reasoning": "",
        "rounds": MAX_ROUNDS,
        "messages": messages,
        "run_id": run_id,
        "tokens": total_tokens,
        "seconds": round(total_seconds, 1),
        "nudged": nudged,
        "redone": redone,
    }
