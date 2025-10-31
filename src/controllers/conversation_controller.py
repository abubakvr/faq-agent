"""Controller for handling conversation requests."""

from sqlalchemy.orm import Session
from typing import Tuple

from ..types.schemas import ConversationResponse, ConversationsListResponse
from ..validation.validators import validate_pagination_params
from ..repository.conversation_repository import ConversationRepository


class ConversationController:
    """Controller for conversation retrieval."""
    
    def __init__(self, db: Session):
        self.repo = ConversationRepository(db)
    
    def get_conversations(self, limit: int, offset: int) -> ConversationsListResponse:
        """
        Get paginated list of conversations.
        
        Args:
            limit: Maximum number of conversations to return
            offset: Number of conversations to skip
            
        Returns:
            ConversationsListResponse with total and conversations list
        """
        validate_pagination_params(limit, offset)
        
        conversations, total = self.repo.get_all(limit=limit, offset=offset)
        
        return ConversationsListResponse(
            total=total,
            conversations=[ConversationResponse.model_validate(conv) for conv in conversations]
        )
    
    def get_conversation(self, conversation_id: int) -> ConversationResponse:
        """
        Get a single conversation by ID.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            ConversationResponse
            
        Raises:
            ValueError: If conversation not found
        """
        conversation = self.repo.get_by_id(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found")
        return ConversationResponse.model_validate(conversation)

