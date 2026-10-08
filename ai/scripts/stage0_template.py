"""Stage 0, step 5: print the exact text the model reads.

The server turns your messages and tools into one long string using the
model's chat template. This script builds that string locally, without
running the model, so you can see the tool format, the thinking tags and
how many tokens everything costs.

Run from the ai/ folder:
    uv run scripts/stage0_template.py
"""

import json

from transformers import AutoTokenizer

# The original model on Hugging Face. Ollama's copy uses the same format.
MODEL_ID = "Qwen/Qwen3-4B-Thinking-2507"

# One tool, written in the OpenAI format your script will send in Stage 1.
GET_SCHEDULE = {
    "type": "function",
    "function": {
        "name": "get_schedule",
        "description": "Get the user's events and tasks between two dates (inclusive).",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "First day, YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Last day, YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    },
}

SYSTEM = {"role": "system", "content": "Current date and time: Monday, October 5, 2026, 6:30 PM (America/Detroit)."}
QUESTION = {"role": "user", "content": "What do I have tomorrow?"}

# What the model sends back when it decides to call the tool...
TOOL_CALL = {
    "role": "assistant",
    "content": "",
    "reasoning_content": "Tomorrow is Tuesday, October 6. I need the schedule for that day.",
    "tool_calls": [
        {
            "type": "function",
            "function": {
                "name": "get_schedule",
                "arguments": json.dumps({"start_date": "2026-10-06", "end_date": "2026-10-06"}),
            },
        }
    ],
}
# ...and what your code sends back after running the tool.
TOOL_RESULT = {
    "role": "tool",
    "content": json.dumps([{"name": "Work", "start": "1:00 PM", "end": "5:00 PM", "changeable": False}]),
}


def show(title: str, text: str, tokenizer, start_at: str = "") -> int:
    """Print the rendered text (from `start_at` onward, if given) and return its full token count."""
    tokens = len(tokenizer.encode(text, add_special_tokens=False))
    print(f"\n===== {title}: {tokens} tokens =====")
    print(text[text.index(start_at) :] if start_at else text)
    return tokens

def main() -> None:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    def render(messages: list[dict], tools: list[dict] | None = None) -> str:
        return tokenizer.apply_chat_template(messages, tools=tools, tokenize=False, add_generation_prompt=True)

    # 1. A question with no tools.
    without_tools = show("1. question, no tools", render([SYSTEM, QUESTION]), tokenizer)

    # 2. The same question with one tool: the tool description goes into the system message.
    with_tool = show("2. same question + one tool", render([SYSTEM, QUESTION], [GET_SCHEDULE]), tokenizer)

    # 3. A tool round trip within one turn. The thinking before the tool call is kept.
    show(
        "3. tool call + tool result (system part not repeated)",
        render([SYSTEM, QUESTION, TOOL_CALL, TOOL_RESULT], [GET_SCHEDULE]),
        tokenizer,
        start_at="<|im_start|>user",
    )

    # 4. The next question. The thinking from the earlier turn is dropped.
    answer = {
        "role": "assistant",
        "content": "Tomorrow you work 1–5 PM.",
        "reasoning_content": "The schedule shows work from 1 to 5 PM.",
    }
    follow_up = {"role": "user", "content": "And on Wednesday?"}
    show(
        "4. next question: earlier thinking dropped (system part not repeated)",
        render([SYSTEM, QUESTION, TOOL_CALL, TOOL_RESULT, answer, follow_up], [GET_SCHEDULE]),
        tokenizer,
        start_at="<|im_start|>user",
    )

    print(f"\nOne tool definition adds {with_tool - without_tools} tokens to every request.")


if __name__ == "__main__":
    main()
