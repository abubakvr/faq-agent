"""Controller for handling session requests."""

from datetime import datetime
from ..helpers.session_manager import get_session_storage, SESSION_TIMEOUT_MINUTES


class SessionController:
    """Controller for session management."""
    
    @staticmethod
    def get_session_info(session_id: str) -> dict:
        """
        Get information about a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            Dictionary with session information
            
        Raises:
            ValueError: If session not found
        """
        session_storage = get_session_storage()
        
        if session_id not in session_storage:
            raise ValueError("Session not found or expired")
        
        session_data = session_storage[session_id]
        time_since_activity = (datetime.utcnow() - session_data["last_activity"]).total_seconds()
        time_remaining = (SESSION_TIMEOUT_MINUTES * 60) - time_since_activity
        
        return {
            "session_id": session_id,
            "last_activity": session_data["last_activity"],
            "time_remaining_seconds": max(0, int(time_remaining)),
            "has_previous_conversation": session_data["previous_question"] is not None,
            "follow_up_question": session_data.get("follow_up_question")
        }

