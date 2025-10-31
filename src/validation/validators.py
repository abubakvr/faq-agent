"""Input validation functions."""

from typing import Optional


def validate_question(question: str) -> str:
    """
    Validate and clean question input.
    
    Args:
        question: The question string
        
    Returns:
        Cleaned question string
        
    Raises:
        ValueError: If question is invalid
    """
    if not question:
        raise ValueError("Question cannot be empty")
    
    cleaned = question.strip()
    if len(cleaned) < 1:
        raise ValueError("Question cannot be empty")
    
    if len(cleaned) > 1000:
        raise ValueError("Question is too long (max 1000 characters)")
    
    return cleaned


def validate_session_id(session_id: Optional[str]) -> Optional[str]:
    """
    Validate session ID format.
    
    Args:
        session_id: The session ID to validate
        
    Returns:
        Validated session ID or None
    """
    if session_id is None:
        return None
    
    session_id = session_id.strip()
    if not session_id:
        return None
    
    if len(session_id) > 50:
        raise ValueError("Session ID is too long")
    
    return session_id


def validate_pagination_params(limit: int, offset: int) -> tuple[int, int]:
    """
    Validate pagination parameters.
    
    Args:
        limit: Number of items per page
        offset: Number of items to skip
        
    Returns:
        Tuple of (limit, offset)
        
    Raises:
        ValueError: If parameters are invalid
    """
    if limit < 1:
        raise ValueError("Limit must be at least 1")
    if limit > 100:
        raise ValueError("Limit cannot exceed 100")
    if offset < 0:
        raise ValueError("Offset cannot be negative")
    
    return limit, offset


# Affirmative responses that should be treated as "Yes"
AFFIRMATIVE_RESPONSES = [
    "yes", "yeah", "yep", "sure", "okay", "ok", "yup", "absolutely",
    "definitely", "of course", "certainly", "indeed", "correct", "right"
]


def is_affirmative_response(text: str) -> bool:
    """
    Check if a response is an affirmative answer.
    
    Args:
        text: The text to check
        
    Returns:
        True if the text is an affirmative response
    """
    cleaned = text.lower().strip(".,!?")
    return cleaned in AFFIRMATIVE_RESPONSES

