"""Message handling utilities for agent runtime.

These utilities provide uniform handling of messages across dict (Gradio) and
LangChain message objects, used throughout agent streaming, compression, and
context management.
"""
from __future__ import annotations

from typing import Any


def get_message_content(msg: Any) -> str | None:
    """Extract content from a message (dict or LangChain message object).

    Handles both dict messages (from Gradio) and LangChain message objects.
    Supports Gradio structured content format (list of content blocks).

    Args:
        msg: Message object (dict or LangChain message)

    Returns:
        Message content string, or None if not found

    Example:
        >>> from kg_engine.utils.message_utils import get_message_content
        >>> # Structured content format (Gradio 6)
        >>> msg = {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
        >>> content = get_message_content(msg)
        >>> content == "Hello"
        True
        >>> # String content format
        >>> msg = {"role": "user", "content": "Hello"}
        >>> content = get_message_content(msg)
        >>> content == "Hello"
        True
    """
    if hasattr(msg, "content"):
        content = msg.content
        return str(content) if content is not None else None
    if isinstance(msg, dict):
        content = msg.get("content")
        if content is None:
            return None
        # Handle structured content format (list of content blocks)
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text = block.get("text", "")
                        if text:
                            text_parts.append(str(text))
                    # Handle other block types if needed (e.g., images)
                    elif block_type == "image":
                        # For images, use path or URL if available
                        img_path = block.get("path") or block.get("url", "")
                        if img_path:
                            text_parts.append(f"[Image: {img_path}]")
            return " ".join(text_parts) if text_parts else None
        # Handle plain string content
        return str(content) if content is not None else None
    return None


def get_message_type(msg: Any) -> str | None:
    """Extract type from a message (dict or LangChain message object).

    Args:
        msg: Message object (dict or LangChain message)

    Returns:
        Message type string (e.g., "user", "assistant", "tool"), or None

    Example:
        >>> from kg_engine.utils.message_utils import get_message_type
        >>> msg = {"role": "user", "content": "Hello"}
        >>> msg_type = get_message_type(msg)
        >>> msg_type == "user"
        True
    """
    if hasattr(msg, "type"):
        return str(msg.type) if msg.type else None
    if isinstance(msg, dict):
        # Check both "type" and "role" fields
        msg_type = msg.get("type") or msg.get("role")
        return str(msg_type) if msg_type else None
    return None


def is_tool_message(msg: Any) -> bool:
    """Check if a message is a tool message.

    Args:
        msg: Message object (dict or LangChain message)

    Returns:
        True if message is a tool message, False otherwise

    Example:
        >>> from kg_engine.utils.message_utils import is_tool_message
        >>> msg = {"type": "tool", "content": "{}"}
        >>> is_tool_message(msg)
        True
    """
    msg_type = get_message_type(msg)
    return msg_type == "tool"


def extract_user_question(messages: list) -> str:
    """Extract the most recent user question from messages.

    Finds the first (most recent) user/human message in the list.

    Args:
        messages: List of message objects

    Returns:
        User question string, or empty string if not found

    Example:
        >>> from kg_engine.utils.message_utils import extract_user_question
        >>> messages = [
        ...     {"role": "user", "content": "Hello"},
        ...     {"role": "assistant", "content": "Hi"}
        ... ]
        >>> question = extract_user_question(messages)
        >>> question == "Hello"
        True
    """
    for msg in messages:
        msg_type = get_message_type(msg)
        if msg_type in ("user", "human"):
            content = get_message_content(msg)
            if content:
                return content
    return ""


def normalize_gradio_history_message(msg: dict) -> dict:
    """Normalize Gradio history message to LangChain-compatible format.

    Converts Gradio 6 structured content format (list of content blocks)
    to simple string format expected by LangChain.

    Args:
        msg: Message dict from Gradio history

    Returns:
        Normalized message dict with string content

    Example:
        >>> from kg_engine.utils.message_utils import normalize_gradio_history_message
        >>> # Structured content format
        >>> msg = {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
        >>> normalized = normalize_gradio_history_message(msg)
        >>> normalized == {"role": "user", "content": "Hello"}
        True
        >>> # String content format
        >>> msg = {"role": "user", "content": "Hello"}
        >>> normalized = normalize_gradio_history_message(msg)
        >>> normalized == {"role": "user", "content": "Hello"}
        True
    """
    if not isinstance(msg, dict):
        return msg

    content = msg.get("content")
    if content is None:
        return msg

    # If content is already a string, return as-is
    if isinstance(content, str):
        return msg

    # Handle structured content format (list of content blocks)
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(str(text))
                # Handle other block types if needed
                elif block_type == "image":
                    img_path = block.get("path") or block.get("url", "")
                    if img_path:
                        text_parts.append(f"[Image: {img_path}]")

        # Return normalized message with string content
        normalized_content = " ".join(text_parts) if text_parts else ""
        return {**msg, "content": normalized_content}

    # Fallback: convert to string
    return {**msg, "content": str(content)}


def update_tool_message_content(
    messages: list, index: int, new_json_str: str
) -> list:
    """Update tool message content at specified index.

    Creates a new list with the updated message to avoid mutating the original.

    Args:
        messages: List of message objects
        index: Index of message to update
        new_json_str: New JSON string content

    Returns:
        New list with updated message

    Example:
        >>> from kg_engine.utils.message_utils import update_tool_message_content
        >>> messages = [{"type": "tool", "content": "{}"}]
        >>> updated = update_tool_message_content(messages, 0, '{"articles": []}')
        >>> updated[0]["content"] == '{"articles": []}'
        True
    """
    updated = list(messages)
    if 0 <= index < len(updated):
        msg = updated[index]
        # Handle both dict and LangChain message objects
        if hasattr(msg, "content"):
            msg.content = new_json_str
        else:
            updated[index] = {**msg, "content": new_json_str}
    return updated


