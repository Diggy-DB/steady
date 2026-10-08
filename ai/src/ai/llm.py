"""Shared helpers for talking to the model server.

These work with any OpenAI-compatible model server.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI

# The ai/ folder. This file is ai/src/ai/llm.py, so it is three levels up.
AI_DIR = Path(__file__).resolve().parents[2]
LOG_FILE = AI_DIR / "logs" / "calls.jsonl"

# Qwen's recommended sampling settings for the thinking model
SAMPLING = {"temperature": 0.6, "top_p": 0.95}
# top_k and min_p aren't part of the OpenAI API, so they travel in extra_body.
# vLLM uses them; Ollama already defaults to the same values for this model.
EXTRA_SAMPLING = {"top_k": 20, "min_p": 0.0}

# A whole <think>...</think> block. DOTALL lets "." match newlines too.
THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL)

@dataclass
class Settings:
    base_url: str
    api_key: str
    model: str

def load_settings() -> Settings:
    """Read the server settings from ai/.env"""
    load_dotenv(dotenv_path=AI_DIR / ".env")
    return Settings(
        base_url = os.getenv("LLM_BASE_URL"),
        model = os.getenv("LLM_MODEL"),
        api_key = os.getenv("LLM_API_KEY"),
    )

def make_client(settings: Settings) -> OpenAI:
    return OpenAI(base_url=settings.base_url, api_key=settings.api_key)

def current_time_text(tz: str) -> str:
    """The current time in a timezone, e.g. 'Monday, October 5, 2026, 2:15 PM (America/Detroit)'."""
    now = datetime.now(ZoneInfo(tz))
    hour = now.hour % 12 or 12
    return f"{now:%A} {now:%B} {now.day}, {now.year}, {hour}:{now:%M} {'AM' if now.hour < 12 else 'PM'} ({tz})"

def split_reasoning(message: dict) -> tuple[str, str]:
    """Return (reasoning, answer) from an assistant message, whichever way the server sent the thinking."""
    content = message.get("content") or ""

    # 1. The server put the thinking in its own field.
    #    Ollama calls it "reasoning"; vLLM calls it "reasoning_content".
    for field in ("reasoning", "reasoning_content"):
        if message.get(field):
            return message[field].strip(), content.strip()

    # 2. The thinking is inside the content, wrapped in <think>...</think>.
    match = THINK_BLOCK.search(content)
    if match:
        answer = content[: match.start()] + content[match.end() :]
        return match.group(1).strip(), answer.strip()

    # 3. Only a closing </think>: the chat template already wrote the opening
    #    tag into the prompt, so it never shows up in the output.
    if "</think>" in content:
        reasoning, answer = content.split("</think>", 1)
        return reasoning.strip(), answer.strip()

    # No thinking at all (e.g. the Instruct model).
    return "", content.strip()

def log_call(record: dict, path: Path = LOG_FILE) -> None:
    """Append one call to the log as a single JSON line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
