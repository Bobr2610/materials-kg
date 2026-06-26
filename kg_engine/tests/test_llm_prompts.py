from __future__ import annotations

from kg_engine.llm.prompts import get_system_prompt


def test_system_prompt_contains_required_instructions():
    # Ensure key constraints and language policy are present in the system prompt
    prompt = get_system_prompt()  # Get base prompt without guidance
    assert "article.php?id=" in prompt
    assert "kb.comindware.ru" in prompt
    assert "Answer in the same language as the user's question" in prompt
    assert "Context" not in prompt  # placeholder added at runtime

