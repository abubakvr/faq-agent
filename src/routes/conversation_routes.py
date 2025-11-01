"""Routes for conversation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..types.schemas import ConversationResponse, ConversationsListResponse, APIResponse, ConversationsAPIResponse, ConversationAPIResponse
from ..config.database import get_db
from ..controllers.conversation_controller import ConversationController

router = APIRouter(tags=["Conversations"])


@router.get("/conversations", response_model=ConversationsAPIResponse, status_code=status.HTTP_200_OK)
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
        result = controller.get_conversations(limit, offset)
        return APIResponse(
            status=True,
            code="00",
            message="Response retrieved successfully",
            data=result
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIResponse(
                status=False,
                code="01",
                message=str(e),
                data={}
            ).model_dump()
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIResponse(
                status=False,
                code="01",
                message=f"Error retrieving conversations: {str(e)}",
                data={}
            ).model_dump()
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationAPIResponse, status_code=status.HTTP_200_OK)
async def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a single conversation by its ID.
    """
    controller = ConversationController(db)
    try:
        result = controller.get_conversation(conversation_id)
        return APIResponse(
            status=True,
            code="00",
            message="Response retrieved successfully",
            data=result
        )
    except ValueError as e:
        # Check if it's a "not found" type error
        error_msg = str(e).lower()
        if "not found" in error_msg or "does not exist" in error_msg:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=APIResponse(
                    status=False,
                    code="01",
                    message=str(e),
                    data={}
                ).model_dump()
            )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIResponse(
                status=False,
                code="01",
                message=str(e),
                data={}
            ).model_dump()
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIResponse(
                status=False,
                code="01",
                message=f"Error retrieving conversation: {str(e)}",
                data={}
            ).model_dump()
        )

