"""Routes for conversation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..types.schemas import ConversationResponse, ConversationsListResponse
from database import get_db
from ..controllers.conversation_controller import ConversationController

router = APIRouter(tags=["Conversations"])


@router.get("/conversations", response_model=ConversationsListResponse)
async def get_conversations(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of conversations to return"),
    offset: int = Query(default=0, ge=0, description="Number of conversations to skip"),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored conversations (questions and answers) from the database.
    
    - **limit**: Maximum number of conversations to return (1-100, default: 50)
    - **offset**: Number of conversations to skip for pagination (default: 0)
    
    Returns conversations ordered by most recent first.
    """
    controller = ConversationController(db)
    try:
        return controller.get_conversations(limit, offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversations: {str(e)}")


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a single conversation by its ID.
    """
    controller = ConversationController(db)
    try:
        return controller.get_conversation(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation: {str(e)}")

