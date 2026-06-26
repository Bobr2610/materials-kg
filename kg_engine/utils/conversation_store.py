from __future__ import annotations

import hashlib

from kg_engine.utils.message_utils import get_message_content


class ConversationStore:
    """Minimal in-memory conversation store keyed by session_id.

    Stores turns as a list of (role, content) tuples. This is per-process and
    resets on restart. Thread-safe access is not implemented; rely on Gradio's
    single-threaded request handling or add locking if needed.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, list[tuple[str, str]]] = {}

    def get(self, session_id: str) -> list[tuple[str, str]]:
        return list(self._sessions.get(session_id, []))

    def set(self, session_id: str, turns: list[tuple[str, str]]) -> None:
        self._sessions[session_id] = list(turns)

    def append(self, session_id: str, role: str, content: str) -> None:
        history = self._sessions.setdefault(session_id, [])
        history.append((role, content))

    def clear(self, session_id: str) -> None:
        """Clear conversation history for a specific session."""
        if session_id in self._sessions:
            del self._sessions[session_id]


def salt_session_id(
    base_session_id: str | None, history: list[dict], current_message: str = ""
) -> str | None:
    """Salt session_id with chat history to isolate memory per chat.

    When Gradio's save_history=True is enabled, different chats share the same
    session_hash. Salting ensures each chat (new or loaded from history) gets
    its own isolated session memory.

    Strategy: Generate deterministically from the first user message.
    - For new chats: uses current_message (first message being sent)
    - For loaded chats: uses first user message from history
    - For continuing same chat: same first message → same salt → same session_id → memory preserved

    This approach is robust because:
    1. The first message is stable across Gradio's save/load cycle
    2. Each distinct chat has a different first message → different session_id
    3. Same chat always generates the same session_id → memory continuity

    Args:
        base_session_id: Base session hash from Gradio request
        history: Current chat history from Gradio (includes loaded chats)
        current_message: Current message being sent (used for new chats)

    Returns:
        Salted session_id or None if base_session_id is None

    Example:
        >>> from kg_engine.utils.conversation_store import salt_session_id
        >>> session_id = salt_session_id("abc123", [], "Hello")
        >>> session_id is not None
        True
    """
    if not base_session_id:
        return None

    # Extract first user message as salt
    # For loaded chats: from history; for new chats: from current_message
    salt = ""
    if history:
        # Loaded or continuing chat: use first user message from history
        for msg in history:
            role = msg.get("role", "")
            if role != "user":
                continue
            # Use centralized message content extraction utility
            text = get_message_content(msg) or ""
            if text:
                salt = text[:100]  # First 100 chars as salt
                break
    elif current_message:
        # New chat: use current message as salt
        salt = str(current_message)[:100]

    # Create salted session_id deterministically
    salted = f"{base_session_id}:{salt}"
    return hashlib.sha256(salted.encode()).hexdigest()[:32]


