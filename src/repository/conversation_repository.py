"""Repository for conversation database operations."""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime

from database import Conversation  # This is at root level


class ConversationRepository:
    """Repository for managing conversation data."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, question: str, answer: str, follow_up_question: Optional[str] = None,
               previous_conversation_id: Optional[int] = None) -> Conversation:
        """
        Create a new conversation record.
        
        Args:
            question: The user's question
            answer: The generated answer
            follow_up_question: Optional follow-up question
            previous_conversation_id: Optional ID of previous related conversation
            
        Returns:
            The created Conversation object
        """
        conversation = Conversation(
            question=question,
            answer=answer,
            follow_up_question=follow_up_question,
            previous_conversation_id=previous_conversation_id,
            created_at=datetime.utcnow()
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
    
    def get_by_id(self, conversation_id: int) -> Optional[Conversation]:
        """
        Get a conversation by its ID.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            The Conversation object or None if not found
        """
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    def get_all(self, limit: int = 50, offset: int = 0) -> tuple[List[Conversation], int]:
        """
        Get all conversations with pagination.
        
        Args:
            limit: Maximum number of conversations to return
            offset: Number of conversations to skip
            
        Returns:
            Tuple of (conversations list, total count)
        """
        total = self.db.query(Conversation).count()
        conversations = self.db.query(Conversation)\
            .order_by(desc(Conversation.created_at))\
            .offset(offset)\
            .limit(limit)\
            .all()
        return conversations, total

