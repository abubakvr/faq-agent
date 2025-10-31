"""Pydantic models for API requests and responses."""

from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


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

