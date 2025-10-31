"""Pydantic models for API requests and responses."""

from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Generic, TypeVar, Any, Union

# Generic type for response data
T = TypeVar('T')


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""
    status: bool
    code: str  # "00" for success, "01" for failure
    message: str
    data: Union[T, dict]  # Can be typed data or empty dict for errors


class SessionInfoResponse(BaseModel):
    """Response model for session information."""
    session_id: str
    last_activity: datetime
    time_remaining_seconds: int
    has_previous_conversation: bool
    follow_up_question: Optional[str] = None


class AskRequest(BaseModel):
    """Request model for asking a question."""
    question: str
    session_id: Optional[str] = None  # Optional session ID for conversation continuity


class AskResponse(BaseModel):
    """Response model for question answers."""
    answer: str
    follow_up_question: Optional[str] = None
    conversation_id: int
    session_id: str  # Session ID for next request


class ConversationResponse(BaseModel):
    """Response model for a single conversation."""
    id: int
    question: str
    answer: str
    follow_up_question: Optional[str] = None
    previous_conversation_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationsListResponse(BaseModel):
    """Response model for a list of conversations."""
    total: int
    conversations: List[ConversationResponse]


# Explicit response types for FastAPI compatibility
class AskAPIResponse(APIResponse[AskResponse]):
    """API response wrapper for ask endpoint."""
    pass


class ConversationsAPIResponse(APIResponse[ConversationsListResponse]):
    """API response wrapper for conversations list endpoint."""
    pass


class ConversationAPIResponse(APIResponse[ConversationResponse]):
    """API response wrapper for single conversation endpoint."""
    pass


class SessionAPIResponse(APIResponse[SessionInfoResponse]):
    """API response wrapper for session endpoint."""
    pass


class RootAPIResponse(APIResponse[dict]):
    """API response wrapper for root endpoint."""
    pass

