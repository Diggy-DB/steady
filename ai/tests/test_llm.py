"""Tests for split_reasoning: one per way a server can send the thinking."""

from ai.llm import split_reasoning


def test_separate_reasoning_field():  # Ollama
    message = {"content": "Study at 2 PM.", "reasoning": "Class ends at noon."}
    assert split_reasoning(message) == ("Class ends at noon.", "Study at 2 PM.")


def test_separate_reasoning_content_field():  # vLLM
    message = {"content": "Study at 2 PM.", "reasoning_content": "Class ends at noon."}
    assert split_reasoning(message) == ("Class ends at noon.", "Study at 2 PM.")


def test_inline_think_block():
    message = {"content": "<think>\nClass ends at noon.\n</think>\n\nStudy at 2 PM."}
    assert split_reasoning(message) == ("Class ends at noon.", "Study at 2 PM.")


def test_only_closing_tag():
    message = {"content": "Class ends at noon.\n</think>\n\nStudy at 2 PM."}
    assert split_reasoning(message) == ("Class ends at noon.", "Study at 2 PM.")


def test_no_thinking():  # e.g. the Instruct model
    message = {"content": "Study at 2 PM."}
    assert split_reasoning(message) == ("", "Study at 2 PM.")


def test_missing_content():  # a reply with only tool calls has content=None (Stage 1)
    message = {"content": None, "reasoning": "I should check the calendar."}
    assert split_reasoning(message) == ("I should check the calendar.", "")
