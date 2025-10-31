"""Session management helper functions."""

import secrets
import asyncio
from datetime import datetime
from typing import Dict, Optional

# In-memory session storage: session_id -> {last_activity, previous_question, previous_answer, previous_conv_id, follow_up_question, recent_follow_ups}
session_storage: Dict[str, Dict] = {}
SESSION_TIMEOUT_MINUTES = 15


def generate_session_id() -> str:
    """Generate a short session ID (8 characters)."""
    return secrets.token_urlsafe(6)[:8]


def get_or_create_session(session_id: Optional[str]) -> str:
    """Get existing session or create new one."""
    if session_id and session_id in session_storage:
        session_storage[session_id]["last_activity"] = datetime.utcnow()
        return session_id
    new_session_id = generate_session_id()
    session_storage[new_session_id] = {
        "last_activity": datetime.utcnow(),
        "previous_question": None,
        "previous_answer": None,
        "previous_conv_id": None,
        "follow_up_question": None,
        "recent_follow_ups": []  # Track recent follow-ups to avoid repetition
    }
    return new_session_id


def cleanup_expired_sessions() -> int:
    """Remove sessions inactive for more than SESSION_TIMEOUT_MINUTES."""
    now = datetime.utcnow()
    expired_sessions = [
        sid for sid, data in session_storage.items()
        if (now - data["last_activity"]).total_seconds() > SESSION_TIMEOUT_MINUTES * 60
    ]
    for sid in expired_sessions:
        del session_storage[sid]
        print(f"Cleaned up expired session: {sid}")
    return len(expired_sessions)


async def periodic_cleanup():
    """Background task to clean up expired sessions."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        cleaned = cleanup_expired_sessions()
        if cleaned > 0:
            print(f"Cleaned up {cleaned} expired session(s)")


def get_session_storage() -> Dict[str, Dict]:
    """Get the session storage dictionary."""
    return session_storage

