"""In-memory session store for conversation history with TTL expiry."""

from __future__ import annotations

import logging
import threading
import time

from kg_engine.domain.models import ChatMessage, ConversationSession, utc_now

logger = logging.getLogger(__name__)


class SessionStore:
    """Thread-safe in-memory session store with TTL-based expiry."""

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_messages: int = 50,
    ) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max_messages = max_messages
        self._last_cleanup = time.monotonic()

    def get_or_create(self, session_id: str) -> ConversationSession:
        """Get existing session or create a new one."""
        with self._lock:
            self._maybe_cleanup()
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_active = utc_now()
                return session
            session = ConversationSession(session_id=session_id)
            self._sessions[session_id] = session
            logger.debug("Created session %s", session_id)
            return session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Append a message to a session's history."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = ConversationSession(session_id=session_id)
                self._sessions[session_id] = session
            msg = ChatMessage(
                role=role,
                content=content,
                metadata=metadata or {},
            )
            session.messages.append(msg)
            session.last_active = utc_now()
            if len(session.messages) > self._max_messages:
                excess = len(session.messages) - self._max_messages
                session.messages = session.messages[excess:]
                logger.debug("Trimmed %d old messages from session %s", excess, session_id)

    def get_history(
        self,
        session_id: str,
        last_n: int = 10,
    ) -> list[ChatMessage]:
        """Return the last N messages from a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return list(session.messages[-last_n:])

    def get_context_messages(
        self,
        session_id: str,
        last_n: int = 10,
    ) -> list[dict[str, str]]:
        """Return conversation history formatted for LLM context.

        Returns list of {"role": ..., "content": ...} dicts.
        """
        history = self.get_history(session_id, last_n=last_n)
        return [{"role": msg.role, "content": msg.content} for msg in history]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if session existed."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def clear(self) -> int:
        """Clear all sessions. Returns count of cleared sessions."""
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            return count

    def _maybe_cleanup(self) -> None:
        """Remove expired sessions periodically (called under lock)."""
        now = time.monotonic()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        cutoff = time.time() - self._ttl
        expired = [
            sid
            for sid, session in self._sessions.items()
            if session.last_active.timestamp() < cutoff
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.debug("Cleaned up %d expired sessions", len(expired))

    @property
    def active_count(self) -> int:
        """Number of active (non-expired) sessions."""
        with self._lock:
            self._maybe_cleanup()
            return len(self._sessions)
